import os
import json
import time
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import STORAGE_DIR, DEFAULT_VOCAB_HINTS, SUPPORTED_MODELS
from app.audio.metadata_extractor import find_ffmpeg
from app.transcription.engine import run_transcription_pipeline, is_model_downloaded
from app.evaluation.metrics import calculate_wer_cer, normalize_arabic_english, normalize_raw
from app.api.audio import resolve_file

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])

BENCHMARK_DIR = STORAGE_DIR / "benchmarks"
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

REF_FILE = BENCHMARK_DIR / "human_reference_raw.txt"
RESULTS_FILE = BENCHMARK_DIR / "benchmark_results.json"
META_FILE = BENCHMARK_DIR / "benchmark_meta.json"


class ReferenceUpdateRequest(BaseModel):
    reference_text: str
    start_time: float = 0.0
    end_time: float = 103.0


class BenchmarkRunRequest(BaseModel):
    audio_path_or_id: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 103.0
    model_ids: List[str] = ["codeswitched-medium", "medium"]
    device_mode: str = "auto"  # "auto", "cuda_only", "cpu"
    use_hints: bool = False
    custom_hints: Optional[str] = None
    eval_mode: str = "normalized"  # "normalized" or "raw"


@router.get("/reference")
def get_reference():
    if not REF_FILE.exists():
        return {
            "has_reference": False,
            "raw_text": "",
            "normalized_text": "",
            "start_time": 0.0,
            "end_time": 103.0,
        }
    raw_text = REF_FILE.read_text(encoding="utf-8").strip()
    norm_text = normalize_arabic_english(raw_text)

    start_time = 0.0
    end_time = 103.0
    if META_FILE.exists():
        try:
            m = json.loads(META_FILE.read_text(encoding="utf-8"))
            start_time = m.get("start_time", 0.0)
            end_time = m.get("end_time", 103.0)
        except Exception:
            pass

    return {
        "has_reference": True,
        "raw_text": raw_text,
        "normalized_text": norm_text,
        "start_time": start_time,
        "end_time": end_time,
        "word_count_raw": len(raw_text.split()),
        "word_count_norm": len(norm_text.split()),
    }


@router.post("/reference")
def save_reference(req: ReferenceUpdateRequest):
    REF_FILE.write_text(req.reference_text.strip(), encoding="utf-8")
    META_FILE.write_text(json.dumps({
        "start_time": req.start_time,
        "end_time": req.end_time,
        "updated_at": time.time(),
    }, indent=2), encoding="utf-8")
    return {"status": "success", "message": "Reference saved successfully"}


@router.get("/results")
def get_latest_results():
    if not RESULTS_FILE.exists():
        return {"has_results": False, "results": []}
    try:
        data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        return {"has_results": True, "results": data}
    except Exception as e:
        return {"has_results": False, "error": str(e), "results": []}


@router.post("/run")
def run_benchmark(req: BenchmarkRunRequest):
    if not REF_FILE.exists():
        raise HTTPException(status_code=400, detail="Human reference not set. Save a reference first.")

    human_ref = REF_FILE.read_text(encoding="utf-8").strip()

    # Determine input audio
    target_audio = None
    if req.audio_path_or_id:
        try:
            target_audio = resolve_file(req.audio_path_or_id)
        except Exception:
            p = Path(req.audio_path_or_id)
            if p.exists():
                target_audio = p
    if not target_audio or not target_audio.exists():
        # Fallback to dd.ogg in workspace root
        for candidate in [
            Path("dd.ogg"),
            Path("../dd.ogg"),
            Path("A:/Projects For Antigravity IDE/General Ideas/1. Transcript voices/dd.ogg"),
        ]:
            if candidate.exists():
                target_audio = candidate.resolve()
                break

    if not target_audio or not target_audio.exists():
        raise HTTPException(status_code=404, detail="Benchmark audio dd.ogg not found.")

    # Slice the exact evaluation interval using FFmpeg
    duration = req.end_time - req.start_time
    if duration <= 1.0:
        raise HTTPException(status_code=400, detail="Benchmark interval must be at least 1.0 second.")

    sliced_audio = BENCHMARK_DIR / f"benchmark_eval_{int(req.start_time)}_{int(req.end_time)}.wav"
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-ss", str(req.start_time),
        "-t", str(duration),
        "-i", str(target_audio),
        "-vn", "-ac", "1", "-ar", "16000",
        str(sliced_audio),
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as err:
        raise HTTPException(status_code=500, detail=f"Audio slicing failed: {err.stderr.decode('utf-8', errors='replace')}")

    benchmark_runs = []

    for model_id in req.model_ids:
        if not is_model_downloaded(model_id):
            benchmark_runs.append({
                "model_id": model_id,
                "name": SUPPORTED_MODELS.get(model_id, {}).get("name", model_id),
                "status": "skipped",
                "reason": "Model is not downloaded locally yet.",
            })
            continue

        hints = None
        if req.use_hints:
            hints = req.custom_hints or DEFAULT_VOCAB_HINTS

        job_id = f"bench_{int(time.time())}_{model_id[:6]}"
        t0 = time.time()

        try:
            res = run_transcription_pipeline(
                input_path=sliced_audio,
                job_id=job_id,
                model_id=model_id,
                language="ar",
                device_mode=req.device_mode,
                compute_mode="auto",
                accuracy_mode="balanced",
                verbatim_mode="strict",
                vocabulary_hints=hints,
            )
            elapsed = time.time() - t0
            pred_text = res["clean_text"]

            eval_norm = calculate_wer_cer(human_ref, pred_text, mode="normalized")
            eval_raw = calculate_wer_cer(human_ref, pred_text, mode="raw")

            meta = res["metadata"]

            benchmark_runs.append({
                "model_id": model_id,
                "name": SUPPORTED_MODELS.get(model_id, {}).get("name", model_id),
                "status": "success",
                "device": meta.get("device_used"),
                "compute": meta.get("compute_used"),
                "cuda_fallback": meta.get("cuda_fallback", False),
                "device_transitions": meta.get("device_transitions", []),
                "repetition_loops_detected": meta.get("repetition_loops_detected", 0),
                "repetition_loops_resolved": meta.get("repetition_loops_resolved", 0),
                "elapsed_seconds": round(elapsed, 2),
                "speedup": round(duration / max(0.1, elapsed), 2),
                "norm_wer": eval_norm["wer_percent"],
                "norm_cer": eval_norm["cer_percent"],
                "norm_sub": eval_norm["substitutions"],
                "norm_del": eval_norm["deletions"],
                "norm_ins": eval_norm["insertions"],
                "norm_hits": eval_norm["hits"],
                "raw_wer": eval_raw["wer_percent"],
                "raw_cer": eval_raw["cer_percent"],
                "raw_sub": eval_raw["substitutions"],
                "raw_del": eval_raw["deletions"],
                "raw_ins": eval_raw["insertions"],
                "predicted_text": pred_text,
                "word_alignment": eval_norm["word_alignment"] if req.eval_mode == "normalized" else eval_raw["word_alignment"],
            })

        except Exception as e:
            benchmark_runs.append({
                "model_id": model_id,
                "name": SUPPORTED_MODELS.get(model_id, {}).get("name", model_id),
                "status": "failed",
                "error": str(e),
            })

    # Clean up intermediate slice
    sliced_audio.unlink(missing_ok=True)

    # Save to disk
    RESULTS_FILE.write_text(json.dumps(benchmark_runs, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "completed",
        "audio_interval": f"{req.start_time:.1f}s - {req.end_time:.1f}s ({duration:.1f}s)",
        "results": benchmark_runs,
    }
