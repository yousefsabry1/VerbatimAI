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
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable

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
    fuse_rover_v2,
    fuse_hybrid_v2,
    fuse_rover_v3,
    fuse_hybrid_v3,
    detect_critical_code_switch_conflict,
    project_fused_words_to_segments,
)
from app.exports.formatters import (
    generate_timestamped_txt,
    generate_clean_txt,
    generate_srt,
    generate_vtt,
    generate_json_export,
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
    condition_on_previous_text: bool = True,
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
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
            if proc.returncode != 0 or not temp_out.exists():
                err = proc.stderr.strip() or proc.stdout.strip()
                raise RuntimeError(f"QwenCleo execution failed: {err}")
            qwen_res = json.loads(temp_out.read_text(encoding="utf-8"))
            pred_text = qwen_res.get("text", "")
            peak_vram = qwen_res.get("peak_vram_mb", 0.0)
            elapsed = qwen_res.get("elapsed_seconds", round(time.time() - t0, 2))
            audio_dur = qwen_res.get("duration_seconds", 0.0)
            segments = [{"start": 0.0, "end": audio_dur if audio_dur > 0 else 600.0, "text": pred_text}]
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


def run_model_isolated(
    model_id: str,
    audio_path: Path,
    duration_seconds: float = 45.0,
    device_mode: str = "auto",
) -> Dict[str, Any]:
    """
    Executes a single model in complete isolation with VRAM hygiene and disk caching.
    """
    res = run_model_inference_cached(
        audio_path=audio_path,
        model_id=model_id,
        device_mode=device_mode,
    )
    return {
        "text": res.get("predicted_text", ""),
        "segments": res.get("segments", []),
        "elapsed_seconds": res.get("elapsed_seconds", 0.0),
        "peak_vram_mb": res.get("peak_vram_mb", 0.0),
    }


def check_qwencleo_availability() -> Dict[str, Any]:
    """Checks whether QwenCleo 4-bit arbiter environment, weights, and GPU are operational."""
    from app.api.models import check_qwencleo_readiness
    return check_qwencleo_readiness()


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
        condition_on_previous_text=True,
    )
    results["models"]["codeswitched-medium"] = res_spec

    # 2. Model 2: Large-v3-Turbo
    logger.info("Running Model 2 (large-v3-turbo)...")
    res_turbo = run_model_inference_cached(
        audio_path=audio_path,
        model_id="large-v3-turbo",
        device_mode=device_mode,
        condition_on_previous_text=True,
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

    # C. ROVER Confusion Network Fusion (Pure 2-Model: Spec + Turbo)
    w_spec = weights.get("codeswitched-medium", 1.20) if weights else 1.20
    w_turbo = weights.get("large-v3-turbo", 1.0) if weights else 1.0
    rover_2m_hyps = [
        {"model_id": "codeswitched-medium", "text": txt_spec},
        {"model_id": "large-v3-turbo", "text": txt_turbo},
    ]
    rover_2m_weights = {"codeswitched-medium": w_spec, "large-v3-turbo": w_turbo}
    rover_2m_res = fuse_rover(rover_2m_hyps, weights=rover_2m_weights)
    results["fusion_hypotheses"]["rover_confusion_network"] = {
        "algorithm": "rover_confusion_network",
        "name": "ROVER Confusion Network (2-Model: Spec + Turbo)",
        "text": rover_2m_res["fused_text"],
        "metadata": rover_2m_res,
        "is_oracle": False,
    }

    # D. Calibrated Weighted Fusion
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

    # F. Three-Model ROVER & Selective Fusion (if QwenCleo available)
    if txt_qwen:
        rover_3m_hyps = [
            {"model_id": "codeswitched-medium", "text": txt_spec},
            {"model_id": "large-v3-turbo", "text": txt_turbo},
            {"model_id": "qwencleo-asr-4bit", "text": txt_qwen},
        ]
        w_qwen = weights.get("qwencleo-asr-4bit", 0.90) if weights else 0.90
        rover_3m_weights = {
            "codeswitched-medium": w_spec,
            "large-v3-turbo": w_turbo,
            "qwencleo-asr-4bit": w_qwen,
        }
        rover_3m_res = fuse_rover(rover_3m_hyps, weights=rover_3m_weights)
        results["fusion_hypotheses"]["rover_three_model"] = {
            "algorithm": "rover_three_model",
            "name": "ROVER Fusion (3-Model: Spec + Turbo + QwenCleo)",
            "text": rover_3m_res["fused_text"],
            "metadata": rover_3m_res,
            "is_oracle": False,
        }

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

    # H. Verbatim Hybrid ASR V2
    hybrid_v2_res = fuse_hybrid_v2(
        txt_spec, txt_turbo, hyp_qwen=txt_qwen, duration_seconds=duration_seconds, weights=weights
    )
    results["fusion_hypotheses"]["hybrid_v2"] = {
        "algorithm": "hybrid_v2",
        "name": "Verbatim Hybrid ASR V2 (Optimized Multi-Model Fusion)",
        "text": hybrid_v2_res["fused_text"],
        "metadata": hybrid_v2_res,
        "is_oracle": False,
    }

    # I. Verbatim Hybrid ASR V3 (Accuracy-First)
    hybrid_v3_res = fuse_hybrid_v3(
        txt_spec, txt_turbo, hyp_qwen=txt_qwen, duration_seconds=duration_seconds, weights=weights
    )
    results["fusion_hypotheses"]["hybrid_v3"] = {
        "algorithm": "hybrid_v3",
        "name": "Verbatim Hybrid ASR V3 (Accuracy-First Multi-Model Fusion)",
        "text": hybrid_v3_res["fused_text"],
        "metadata": hybrid_v3_res,
        "is_oracle": False,
    }

    results["total_elapsed_seconds"] = round(time.time() - t_start, 2)
    return results


def run_hybrid_transcription(
    input_path: Path,
    job_id: str,
    job_dir: Path,
    source_meta: Dict[str, Any],
    model_id: str = "hybrid-v1",
    language: Optional[str] = None,
    device_mode: str = "auto",
    accuracy_mode: str = "balanced",
    verbatim_mode: str = "strict",
    enhance_audio: bool = False,
    vad_filter: bool = True,
    vocabulary_hints: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    End-to-end production transcription pipeline for Verbatim Hybrid ASR (V1 and V2).
    Coordinates sequential model inference, VRAM hygiene, hypothesis fusion,
    timestamp projection, and multi-format subtitle generation.
    """
    from app.api.benchmark import run_qwencleo_benchmark

    t_start = time.time()
    total_duration = max(float(source_meta.get("duration") or 45.0), 1.0)
    prompt = vocabulary_hints.strip() if (vocabulary_hints and vocabulary_hints.strip()) else None

    # Verify required twin models are downloaded before inference begins
    missing_models = []
    if not is_model_downloaded("codeswitched-medium"):
        missing_models.append("codeswitched-medium (Egyptian Specialized)")
    if not is_model_downloaded("large-v3-turbo"):
        missing_models.append("large-v3-turbo (Whisper Large Turbo)")
    if missing_models:
        raise RuntimeError(
            f"Hybrid mode ({model_id}) requires twin models to be downloaded first: "
            f"{', '.join(missing_models)}. Please download them from the Model Selection panel before transcribing."
        )

    # Step 1: Model 1 — Specialized Whisper Medium
    if progress_callback:
        progress_callback(0.12, "Hybrid Pass 1/3: Transcribing with Specialized Whisper Medium (CUDA)...")

    clear_loaded_models_cache()
    model_spec, act_dev, act_comp = load_whisper_model(
        model_id="codeswitched-medium",
        device_mode=device_mode,
        compute_mode="auto",
        progress_callback=progress_callback,
    )

    gen_spec, info_spec = model_spec.transcribe(
        str(input_path),
        language="ar",
        initial_prompt=prompt,
        beam_size=5,
        condition_on_previous_text=True,
        vad_filter=vad_filter,
        repetition_penalty=1.10,
        no_repeat_ngram_size=3,
    )

    spec_segments = []
    spec_text_parts = []
    for s in gen_spec:
        txt = s.text.strip()
        if txt:
            spec_text_parts.append(txt)
            spec_segments.append({
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": txt,
            })
    spec_text = " ".join(spec_text_parts).strip()

    # Step 2: Model 2 — Large-v3-Turbo
    if progress_callback:
        progress_callback(0.42, "Hybrid Pass 2/3: Transcribing with Whisper Large-v3-Turbo (CUDA)...")

    clear_loaded_models_cache()
    model_turbo, _, _ = load_whisper_model(
        model_id="large-v3-turbo",
        device_mode=device_mode,
        compute_mode="auto",
        progress_callback=progress_callback,
    )

    gen_turbo, _ = model_turbo.transcribe(
        str(input_path),
        language="ar",
        initial_prompt=prompt,
        beam_size=4,
        condition_on_previous_text=True,
        vad_filter=vad_filter,
        repetition_penalty=1.10,
        no_repeat_ngram_size=3,
    )

    turbo_segments = []
    turbo_text_parts = []
    for s in gen_turbo:
        txt = s.text.strip()
        if txt:
            turbo_text_parts.append(txt)
            turbo_segments.append({
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": txt,
            })
    turbo_text = " ".join(turbo_text_parts).strip()
    clear_loaded_models_cache()

    # Step 3: Model 3 — QwenCleo 4-bit (Adaptive / Selective)
    qwen_text = ""
    is_conflict = False
    conflict_reason = "none"
    qwen_status = "not_invoked"

    qwen_avail = check_qwencleo_availability()

    if model_id in ("hybrid-v2", "hybrid-v3"):
        # Hybrid V2/V3: Intelligent Selective Arbiter
        is_conflict, conflict_reason = detect_critical_code_switch_conflict(spec_text, turbo_text)
        if is_conflict:
            if not qwen_avail["ready"]:
                qwen_status = f"unconfigured_dual_model_resolution ({qwen_avail['status']}: {qwen_avail['reason']})"
                logger.info(
                    "Code-switch conflict detected (%s), but QwenCleo is unavailable (%s). "
                    "Resolving via calibrated dual-model consensus.",
                    conflict_reason, qwen_avail["status"]
                )
                if progress_callback:
                    progress_callback(
                        0.72,
                        f"Conflict detected: Resolving via calibrated dual-model consensus (QwenCleo: {qwen_avail['status']})..."
                    )
            else:
                if progress_callback:
                    progress_callback(0.70, "Hybrid Pass 3/3: Evaluating code-switching with QwenCleo-ASR (4-bit)...")
                try:
                    qwen_res = run_qwencleo_benchmark(str(input_path), total_duration, "cuda")
                    if qwen_res.get("status") == "error" or not qwen_res.get("text"):
                        err_msg = qwen_res.get("error", "Empty text returned")
                        logger.warning("QwenCleo selective inference returned error: %s. Falling back to dual-model resolution.", err_msg)
                        qwen_status = f"execution_error_fallback ({err_msg})"
                        qwen_text = ""
                    else:
                        qwen_text = qwen_res.get("text", "")
                        qwen_status = "invoked_and_adjudicated"
                except Exception as e:
                    logger.warning("QwenCleo selective inference encountered exception: %s. Falling back to dual-model resolution.", e)
                    qwen_status = f"execution_exception_fallback ({e})"
                    qwen_text = ""
        else:
            qwen_status = "skipped_high_agreement"
            if progress_callback:
                progress_callback(0.75, "High Model Agreement Confirmed: Skipping secondary QwenCleo pass...")
    else:
        # Hybrid V1: Full Three-Model Execution
        is_conflict = True
        conflict_reason = "hybrid_v1_full"
        if not qwen_avail["ready"]:
            qwen_status = f"unconfigured_dual_model_resolution ({qwen_avail['status']}: {qwen_avail['reason']})"
            logger.info("Hybrid V1 requested, but QwenCleo unavailable (%s). Resolving via dual models.", qwen_avail["status"])
        else:
            if progress_callback:
                progress_callback(0.70, "Hybrid Pass 3/3: Evaluating code-switching with QwenCleo-ASR (4-bit)...")
            try:
                qwen_res = run_qwencleo_benchmark(str(input_path), total_duration, "cuda")
                if qwen_res.get("status") == "error" or not qwen_res.get("text"):
                    err_msg = qwen_res.get("error", "Empty text returned")
                    logger.warning("QwenCleo inference returned error: %s. Falling back to dual models.", err_msg)
                    qwen_status = f"execution_error_fallback ({err_msg})"
                    qwen_text = ""
                else:
                    qwen_text = qwen_res.get("text", "")
                    qwen_status = "invoked_and_adjudicated"
            except Exception as e:
                logger.warning("QwenCleo inference encountered exception: %s. Falling back to dual models.", e)
                qwen_status = f"execution_exception_fallback ({e})"
                qwen_text = ""

    # Step 4: Multi-Model Fusion Synthesis
    if progress_callback:
        progress_callback(0.88, "Synthesizing multi-model fusion & aligning segments...")

    if model_id == "hybrid-v3":
        fusion_res = fuse_hybrid_v3(
            spec_text, turbo_text, hyp_qwen=qwen_text, duration_seconds=total_duration
        )
        fused_text = fusion_res["fused_text"]
    elif model_id == "hybrid-v2":
        fusion_res = fuse_hybrid_v2(
            spec_text, turbo_text, hyp_qwen=qwen_text, duration_seconds=total_duration
        )
        fused_text = fusion_res["fused_text"]
    else:
        if qwen_text:
            hyps = [
                {"model_id": "codeswitched-medium", "text": spec_text},
                {"model_id": "large-v3-turbo", "text": turbo_text},
                {"model_id": "qwencleo-asr-4bit", "text": qwen_text},
            ]
            w = {"codeswitched-medium": 1.20, "large-v3-turbo": 1.0, "qwencleo-asr-4bit": 0.90}
            fusion_res = fuse_rover(hyps, weights=w)
        else:
            hyps = [
                {"model_id": "codeswitched-medium", "text": spec_text},
                {"model_id": "large-v3-turbo", "text": turbo_text},
            ]
            w = {"codeswitched-medium": 1.20, "large-v3-turbo": 1.0}
            fusion_res = fuse_rover(hyps, weights=w)
        fused_text = fusion_res["fused_text"]

    # Step 5: Project Fused Words to Natural Segments
    segments_list = project_fused_words_to_segments(spec_segments, fused_text)
    if not segments_list:
        segments_list = [{
            "id": 1,
            "start": 0.0,
            "end": total_duration,
            "text": fused_text,
            "original_text": fused_text,
            "confidence": "high",
            "uncertain": False,
            "uncertain_reason": None,
            "words": [],
        }]

    # Step 6: Assembly & Export File Generation
    if progress_callback:
        progress_callback(0.94, "Formatting subtitle files & exports...")

    timestamped_txt = generate_timestamped_txt(segments_list)
    clean_txt = generate_clean_txt(segments_list)
    srt_content = generate_srt(segments_list)
    vtt_content = generate_vtt(segments_list)

    models_participated = ["codeswitched-medium", "large-v3-turbo"]
    if qwen_text:
        models_participated.append("qwencleo-asr-4bit")
        effective_tier = "full_tri_model"
    else:
        effective_tier = "dual_model_consensus"

    metadata = {
        "job_id": job_id,
        "input_filename": input_path.name,
        "duration": total_duration,
        "duration_formatted": source_meta.get("duration_formatted", ""),
        "detected_language": "ar",
        "language_probability": 1.0,
        "model_used": model_id,
        "device_used": act_dev,
        "compute_used": act_comp,
        "initial_device": act_dev,
        "cuda_fallback": False,
        "accuracy_mode": accuracy_mode,
        "verbatim_mode": verbatim_mode,
        "enhanced": enhance_audio,
        "vad": vad_filter,
        "engine_version": "1.3.0-hybrid-v3",
        "git_revision": "645b732",
        "fusion_config": "rover_v3_multi_cand_null_guard_v3",
        "audio_sha256": source_meta.get("sha256") or hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "processed_at": datetime.utcnow().isoformat(),
        "hybrid_metadata": {
            "hybrid_tier": effective_tier,
            "models_participated": models_participated,
            "fusion_method": fusion_res.get("method", "hybrid_fusion"),
            "code_switch_conflict_detected": is_conflict,
            "conflict_reason": conflict_reason,
            "qwen_status": qwen_status,
            "qwen_invoked": bool(qwen_text),
            "models_raw": {
                "codeswitched-medium": spec_text,
                "large-v3-turbo": turbo_text,
                "qwencleo-asr-4bit": qwen_text,
            },
        },
    }

    json_content = generate_json_export(job_id, segments_list, metadata)

    txt_file = job_dir / "transcript.txt"
    clean_file = job_dir / "clean_transcript.txt"
    srt_file = job_dir / "subtitles.srt"
    vtt_file = job_dir / "subtitles.vtt"
    json_file = job_dir / "transcript.json"

    txt_file.write_text(timestamped_txt, encoding="utf-8")
    clean_file.write_text(clean_txt, encoding="utf-8")
    srt_file.write_text(srt_content, encoding="utf-8")
    vtt_file.write_text(vtt_content, encoding="utf-8")
    json_file.write_text(json_content, encoding="utf-8")

    return {
        "job_id": job_id,
        "original_text": fused_text,
        "clean_text": clean_txt,
        "segments": segments_list,
        "srt_content": srt_content,
        "vtt_content": vtt_content,
        "output_files": {
            "txt": str(txt_file),
            "clean_txt": str(clean_file),
            "srt": str(srt_file),
            "vtt": str(vtt_file),
            "json": str(json_file),
        },
        "metadata": metadata,
    }

