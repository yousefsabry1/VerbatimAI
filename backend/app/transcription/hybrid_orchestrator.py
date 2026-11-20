"""
Verbatim Hybrid ASR Orchestrator V1
===================================
Coordinates sequential inference across multiple local ASR models on NVIDIA RTX 3050 (4GB VRAM):
- Enforces strict sequential model loading and explicit VRAM release between models.
- Integrates Specialized Whisper Medium, Whisper Large-v3-Turbo, and QwenCleo-ASR 4-bit.
- Features disk-based hypothesis caching to prevent redundant GPU execution.
- Generates unified multi-algorithm fusion candidates.
"""

import os
import gc
import json
import time
import shutil
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from app.core.config import STORAGE_DIR, MODELS_DIR

BENCHMARK_DIR = STORAGE_DIR / "benchmarks"
from app.audio.metadata_extractor import find_ffmpeg
from app.transcription.engine import (
    load_whisper_model,
    clear_loaded_models_cache,
    is_model_downloaded,
)
from app.transcription.hybrid_fusion import (
    fuse_conservative_agreement,
    fuse_rover,
    fuse_weighted,
    route_contextual_segments,
    fuse_selective_three_model,
    calculate_oracle_upper_bound,
)

logger = logging.getLogger("verbatim.hybrid_orchestrator")

HYBRID_CACHE_DIR = STORAGE_DIR / "hybrid_cache"
HYBRID_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_gpu_vram_mb() -> float:
    """Queries current NVIDIA GPU memory usage via nvidia-smi."""
    try:
        if shutil.which("nvidia-smi"):
            cmd = ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip().split("\n")[0])
    except Exception:
        pass
    return 0.0


def _compute_audio_hash(audio_path: Path) -> str:
    """Computes SHA-256 hash of the audio file header and size for caching."""
    hasher = hashlib.sha256()
    size = audio_path.stat().st_size
    hasher.update(str(size).encode())
    with open(audio_path, "rb") as f:
        # Hash first 64KB and last 64KB
        hasher.update(f.read(65536))
        if size > 131072:
            f.seek(-65536, os.SEEK_END)
            hasher.update(f.read(65536))
    return hasher.hexdigest()[:16]


def run_model_inference_cached(
    audio_path: Path,
    model_id: str,
    device_mode: str = "auto",
    language: Optional[str] = None,
    beam_size: int = 5,
    condition_on_previous_text: bool = False,
    vad_filter: bool = False,
) -> Dict[str, Any]:
    """
    Executes inference for a single model with disk caching and GPU memory isolation.
    """
    audio_hash = _compute_audio_hash(audio_path)
    cache_key = f"{audio_hash}_{model_id}_{device_mode}_b{beam_size}_vad{int(vad_filter)}_cprev{int(condition_on_previous_text)}"
    cache_file = HYBRID_CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        try:
            cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
            logger.info("Loaded cached hypothesis for %s on %s", model_id, audio_path.name)
            return cached_data
        except Exception as e:
            logger.warning("Cache read failed for %s: %s", cache_file.name, e)

    # Isolated execution based on model type
    t0 = time.time()
    vram_before = _get_gpu_vram_mb()

    if model_id == "qwencleo-asr-4bit":
        # QwenCleo runs in isolated subprocess via experimental_venv
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        exp_py = project_root / "experimental_venv" / "Scripts" / "python.exe"
        runner_py = project_root / "backend" / "app" / "transcription" / "qwencleo_runner.py"
        temp_out = HYBRID_CACHE_DIR / f"temp_qwen_{int(time.time() * 1000)}.json"

        target_device = "cuda" if device_mode != "cpu" else "cpu"
        cmd = [
            str(exp_py),
            str(runner_py),
            "--audio", str(audio_path),
            "--output", str(temp_out),
            "--device", target_device,
        ]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
            if proc.returncode != 0 or not temp_out.exists():
                err = proc.stderr.strip() or proc.stdout.strip()
                raise RuntimeError(f"QwenCleo execution failed: {err}")
            qwen_res = json.loads(temp_out.read_text(encoding="utf-8"))
            pred_text = qwen_res.get("text", "")
            peak_vram = qwen_res.get("peak_vram_mb", 0.0)
            elapsed = qwen_res.get("elapsed_seconds", round(time.time() - t0, 2))
            segments = [{"start": 0.0, "end": 45.0, "text": pred_text}]
        finally:
            if temp_out.exists():
                temp_out.unlink(missing_ok=True)
    else:
        # Faster-Whisper model
        # Explicitly unload any other models first
        clear_loaded_models_cache()

        whisper_model, actual_device, actual_compute = load_whisper_model(
            model_id=model_id,
            device_mode=device_mode,
            compute_mode="auto",
        )

        lang_arg = "ar" if "codeswitched" in model_id else language

        generator, info = whisper_model.transcribe(
            str(audio_path),
            language=lang_arg,
            beam_size=beam_size,
            condition_on_previous_text=condition_on_previous_text,
            vad_filter=vad_filter,
            repetition_penalty=1.10,
            no_repeat_ngram_size=3,
        )

        segments = []
        full_text_parts = []
        for s in generator:
            txt = s.text.strip()
            if txt:
                full_text_parts.append(txt)
                segments.append({
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": txt,
                    "avg_logprob": round(getattr(s, "avg_logprob", 0.0), 3),
                    "compression_ratio": round(getattr(s, "compression_ratio", 1.0), 2),
                    "no_speech_prob": round(getattr(s, "no_speech_prob", 0.0), 3),
                })

        pred_text = " ".join(full_text_parts).strip()
        elapsed = round(time.time() - t0, 2)
        vram_after = _get_gpu_vram_mb()
        peak_vram = max(vram_after, vram_before)

        # Unload model immediately to guarantee VRAM hygiene for the next model
        clear_loaded_models_cache()

    result = {
        "model_id": model_id,
        "predicted_text": pred_text,
        "segments": segments,
        "elapsed_seconds": elapsed,
        "peak_vram_mb": peak_vram,
        "device": device_mode,
        "word_count": len(pred_text.split()),
    }

    # Save to disk cache
    try:
        cache_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to save cache for %s: %s", cache_file.name, e)

    return result


def run_hybrid_asr_pipeline(
    audio_path: Path,
    duration_seconds: float = 45.0,
    device_mode: str = "auto",
    include_qwencleo: bool = False,
    reference_text: Optional[str] = None,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Executes the full Verbatim Hybrid ASR V1 pipeline:
    1. Sequential execution of Specialized Whisper and Large-v3-Turbo
    2. Optional execution of QwenCleo 4-bit
    3. Multi-algorithm fusion synthesis:
       - Baseline Specialized
       - Baseline Turbo
       - Conservative Agreement Fusion
       - ROVER Confusion Network Fusion
       - Calibrated Weighted Fusion
       - Contextual Segment Routing
       - Selective Three-Model Fusion (if QwenCleo included)
       - Theoretical Oracle Upper Bound (if reference provided; labeled ORACLE — NOT DEPLOYABLE)
    """
    t_start = time.time()
    results: Dict[str, Any] = {
        "audio_file": audio_path.name,
        "duration_seconds": duration_seconds,
        "models": {},
        "fusion_hypotheses": {},
    }

    # 1. Model 1: Specialized Whisper
    logger.info("Running Model 1 (codeswitched-medium)...")
    res_spec = run_model_inference_cached(
        audio_path=audio_path,
        model_id="codeswitched-medium",
        device_mode=device_mode,
        condition_on_previous_text=False,
    )
    results["models"]["codeswitched-medium"] = res_spec

    # 2. Model 2: Large-v3-Turbo
    logger.info("Running Model 2 (large-v3-turbo)...")
    res_turbo = run_model_inference_cached(
        audio_path=audio_path,
        model_id="large-v3-turbo",
        device_mode=device_mode,
        condition_on_previous_text=False,
    )
    results["models"]["large-v3-turbo"] = res_turbo

    # 3. Model 3 (Optional): QwenCleo 4-bit
    res_qwen = None
    if include_qwencleo:
        try:
            logger.info("Running Model 3 (qwencleo-asr-4bit)...")
            res_qwen = run_model_inference_cached(
                audio_path=audio_path,
                model_id="qwencleo-asr-4bit",
                device_mode=device_mode,
            )
            results["models"]["qwencleo-asr-4bit"] = res_qwen
        except Exception as e:
            logger.warning("QwenCleo inference failed: %s", e)

    txt_spec = res_spec["predicted_text"]
    txt_turbo = res_turbo["predicted_text"]
    txt_qwen = res_qwen["predicted_text"] if res_qwen else ""

    # Synthesize Fusion Candidates

    # A. Baselines
    results["fusion_hypotheses"]["specialized_baseline"] = {
        "algorithm": "specialized_baseline",
        "name": "Specialized Whisper Baseline",
        "text": txt_spec,
        "is_oracle": False,
    }
    results["fusion_hypotheses"]["turbo_baseline"] = {
        "algorithm": "turbo_baseline",
        "name": "Whisper Large-v3-Turbo Baseline",
        "text": txt_turbo,
        "is_oracle": False,
    }

    # B. Conservative Agreement Fusion
    cons_res = fuse_conservative_agreement(txt_spec, txt_turbo, duration_seconds=duration_seconds)
    results["fusion_hypotheses"]["conservative_agreement"] = {
        "algorithm": "conservative_agreement",
        "name": "Conservative Agreement Fusion",
        "text": cons_res["fused_text"],
        "metadata": cons_res,
        "is_oracle": False,
    }

    # C. ROVER Confusion Network Fusion
    rover_hyps = [
        {"model_id": "codeswitched-medium", "text": txt_spec},
        {"model_id": "large-v3-turbo", "text": txt_turbo},
    ]
    if txt_qwen:
        rover_hyps.append({"model_id": "qwencleo-asr-4bit", "text": txt_qwen})

    rover_res = fuse_rover(rover_hyps, weights=weights)
    results["fusion_hypotheses"]["rover_confusion_network"] = {
        "algorithm": "rover_confusion_network",
        "name": "ROVER Confusion Network",
        "text": rover_res["fused_text"],
        "metadata": rover_res,
        "is_oracle": False,
    }

    # D. Calibrated Weighted Fusion
    w_spec = weights.get("codeswitched-medium", 1.20) if weights else 1.20
    w_turbo = weights.get("large-v3-turbo", 1.0) if weights else 1.0
    weighted_res = fuse_weighted(txt_spec, txt_turbo, weight_spec=w_spec, weight_turbo=w_turbo, duration_seconds=duration_seconds)
    results["fusion_hypotheses"]["weighted_fusion"] = {
        "algorithm": "weighted_fusion",
        "name": f"Calibrated Weighted Fusion ({w_spec}:{w_turbo})",
        "text": weighted_res["fused_text"],
        "metadata": weighted_res,
        "is_oracle": False,
    }

    # E. Contextual Segment Routing
    seg_routing_res = route_contextual_segments(res_spec["segments"], res_turbo["segments"])
    results["fusion_hypotheses"]["contextual_segment_routing"] = {
        "algorithm": "contextual_segment_routing",
        "name": "Contextual Segment-Level Routing",
        "text": seg_routing_res["fused_text"],
        "metadata": seg_routing_res,
        "is_oracle": False,
    }

    # F. Selective Three-Model Fusion (if QwenCleo available)
    if txt_qwen:
        three_res = fuse_selective_three_model(txt_spec, txt_turbo, hyp_qwen=txt_qwen, duration_seconds=duration_seconds)
        results["fusion_hypotheses"]["selective_three_model"] = {
            "algorithm": "selective_three_model",
            "name": "Selective Three-Model Fusion (Spec + Turbo + QwenCleo)",
            "text": three_res["fused_text"],
            "metadata": three_res,
            "is_oracle": False,
        }

    # G. Theoretical Oracle Upper Bound (Strictly for diagnostic limit analysis)
    if reference_text:
        cand_dict = {
            "codeswitched-medium": txt_spec,
            "large-v3-turbo": txt_turbo,
        }
        if txt_qwen:
            cand_dict["qwencleo-asr-4bit"] = txt_qwen
        oracle_res = calculate_oracle_upper_bound(cand_dict, reference_text)
        results["fusion_hypotheses"]["oracle_upper_bound"] = {
            "algorithm": "oracle_upper_bound",
            "name": "ORACLE — NOT DEPLOYABLE (Theoretical Upper Bound)",
            "text": oracle_res.get("oracle_text", ""),
            "metadata": oracle_res,
            "is_oracle": True,
        }

    results["total_elapsed_seconds"] = round(time.time() - t_start, 2)
    return results
