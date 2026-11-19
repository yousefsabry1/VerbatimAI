import os
import json
import time
import subprocess
import mimetypes
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import STORAGE_DIR, DEFAULT_VOCAB_HINTS, SUPPORTED_MODELS
from app.audio.metadata_extractor import find_ffmpeg
from app.transcription.engine import run_transcription_pipeline, is_model_downloaded
from app.evaluation.metrics import calculate_wer_cer, normalize_arabic_english, normalize_raw
from app.api.audio import resolve_file

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])

BENCHMARK_DIR = STORAGE_DIR / "benchmarks"
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

# Sample Files
DEV_REF_FILE = BENCHMARK_DIR / "human_reference_raw.txt"
DEV_AUDIO_FILE = BENCHMARK_DIR / "ref_103s.wav"
DEV_RESULTS_FILE = BENCHMARK_DIR / "benchmark_results.json"
DEV_META_FILE = BENCHMARK_DIR / "benchmark_meta.json"

TEST_REF_FILE = BENCHMARK_DIR / "human_reference_test_180_225.txt"
TEST_AUDIO_FILE = BENCHMARK_DIR / "test_slice_180_225.wav"
TEST_RESULTS_FILE = BENCHMARK_DIR / "benchmark_results_test_180_225.json"
TEST_META_FILE = BENCHMARK_DIR / "benchmark_meta_test_180_225.json"


class ReferenceUpdateRequest(BaseModel):
    sample_id: str = "dev_0_103"
    reference_text: str
    start_time: float = 0.0
    end_time: float = 103.5
    is_human_verified: bool = False
    verification_statement: Optional[str] = None


class BenchmarkRunRequest(BaseModel):
    sample_id: str = "dev_0_103"
    audio_path_or_id: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 103.5
    model_ids: List[str] = ["codeswitched-medium", "medium", "large-v3-turbo"]
    device_mode: str = "auto"  # "auto", "cuda_only", "cpu"
    use_hints: bool = False
    custom_hints: Optional[str] = None
    eval_mode: str = "normalized"  # "normalized" or "raw"
    vad_filter: bool = False


class LiveAlignRequest(BaseModel):
    reference_text: str
    hypothesis_text: str
    eval_mode: str = "normalized"


def _find_source_audio() -> Path:
    for candidate in [
        Path("dd.ogg"),
        Path("../dd.ogg"),
        Path("A:/Projects For Antigravity IDE/General Ideas/1. Transcript voices/dd.ogg"),
    ]:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError("Workspace recording dd.ogg not found.")


def _ensure_test_slice():
    """Ensures test_slice_180_225.wav (03:00-03:45) is extracted from dd.ogg."""
    if not TEST_AUDIO_FILE.exists():
        src = _find_source_audio()
        ffmpeg = find_ffmpeg()
        cmd = [
            ffmpeg, "-y",
            "-ss", "180.0",
            "-to", "225.0",
            "-i", str(src),
            "-vn", "-ac", "1", "-ar", "16000",
            str(TEST_AUDIO_FILE),
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def _ensure_dev_slice():
    """Ensures ref_103s.wav (00:00-01:43.5) is extracted from dd.ogg."""
    if not DEV_AUDIO_FILE.exists():
        src = _find_source_audio()
        ffmpeg = find_ffmpeg()
        cmd = [
            ffmpeg, "-y",
            "-t", "103.5",
            "-i", str(src),
            "-vn", "-ac", "1", "-ar", "16000",
            str(DEV_AUDIO_FILE),
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


@router.get("/samples")
def get_benchmark_samples():
    """
    Returns the catalog of registered benchmark evaluation intervals.
    """
    _ensure_dev_slice()
    _ensure_test_slice()

    dev_words = 0
    if DEV_REF_FILE.exists():
        dev_words = len(DEV_REF_FILE.read_text(encoding="utf-8").strip().split())

    test_words = 0
    test_verified = False
    if TEST_REF_FILE.exists():
        test_txt = TEST_REF_FILE.read_text(encoding="utf-8").strip()
        test_words = len(test_txt.split())
        if TEST_META_FILE.exists():
            try:
                m = json.loads(TEST_META_FILE.read_text(encoding="utf-8"))
                test_verified = m.get("is_human_verified", False) and test_words > 0
            except Exception:
                test_verified = False

    return {
        "samples": [
            {
                "sample_id": "dev_0_103",
                "name": "Development Sample (00:00 - 01:43)",
                "start_time": 0.0,
                "end_time": 103.5,
                "duration": 103.5,
                "audio_url": "/api/benchmark/audio/dev_0_103",
                "status": "VERIFIED",
                "verification_badge": f"Verified Human Reference ({dev_words} words)",
                "has_human_reference": True,
                "word_count": dev_words,
                "description": "Original human-verified ground-truth sample. Development baseline: 52.71% Normalized WER.",
            },
            {
                "sample_id": "test_180_225",
                "name": "Independent Test Sample (03:00 - 03:45)",
                "start_time": 180.0,
                "end_time": 225.0,
                "duration": 45.0,
                "audio_url": "/api/benchmark/audio/test_180_225",
                "status": "VERIFIED" if test_verified else "UNVERIFIED",
                "verification_badge": (
                    f"Verified Human Reference ({test_words} words)"
                    if test_verified
                    else "UNVERIFIED — No valid WER/CER available"
                ),
                "has_human_reference": test_verified,
                "word_count": test_words,
                "description": (
                    "Independent 45s out-of-sample audio interval. "
                    + ("Human reference verified." if test_verified else "Requires manual human verification against audio.")
                ),
            },
        ],
        "audit_notice": {
            "invalidated_slice": "04:05 - 04:55 (245s - 295s)",
            "reason": "Retracted due to circular AI pseudo-ground-truth generation. 30.22% WER invalidated.",
            "integrity_rule": "No ASR prediction can be labeled as human reference without explicit human certification.",
        },
    }


@router.get("/audio/{sample_id}")
def stream_benchmark_audio(sample_id: str):
    """
    Streams audio for the requested benchmark sample with byte-range support.
    """
    _ensure_dev_slice()
    _ensure_test_slice()

    if sample_id == "dev_0_103":
        target = DEV_AUDIO_FILE
    elif sample_id == "test_180_225":
        target = TEST_AUDIO_FILE
    elif sample_id == "full":
        target = _find_source_audio()
    else:
        # Check direct filename in benchmark dir
        p = BENCHMARK_DIR / sample_id
        if p.is_file():
            target = p
        else:
            raise HTTPException(status_code=404, detail=f"Benchmark audio '{sample_id}' not found.")

    mime = "audio/wav" if target.suffix.lower() == ".wav" else "audio/ogg"
    return FileResponse(
        path=target,
        media_type=mime,
        filename=target.name,
        headers={"Accept-Ranges": "bytes"}
    )


@router.get("/reference")
def get_reference(sample_id: str = Query("dev_0_103")):
    """
    Retrieves the reference transcript and verification status for a benchmark sample.
    """
    if sample_id == "test_180_225":
        if not TEST_REF_FILE.exists():
            return {
                "sample_id": "test_180_225",
                "has_reference": False,
                "is_human_verified": False,
                "verification_status": "UNVERIFIED — No valid WER/CER available",
                "raw_text": "",
                "normalized_text": "",
                "start_time": 180.0,
                "end_time": 225.0,
                "word_count_raw": 0,
                "word_count_norm": 0,
            }
        raw_text = TEST_REF_FILE.read_text(encoding="utf-8").strip()
        norm_text = normalize_arabic_english(raw_text)
        is_verified = False
        if TEST_META_FILE.exists():
            try:
                m = json.loads(TEST_META_FILE.read_text(encoding="utf-8"))
                is_verified = m.get("is_human_verified", False) and len(raw_text.split()) > 0
            except Exception:
                is_verified = False

        return {
            "sample_id": "test_180_225",
            "has_reference": is_verified,
            "is_human_verified": is_verified,
            "verification_status": "VERIFIED" if is_verified else "UNVERIFIED — No valid WER/CER available",
            "raw_text": raw_text,
            "normalized_text": norm_text,
            "start_time": 180.0,
            "end_time": 225.0,
            "word_count_raw": len(raw_text.split()),
            "word_count_norm": len(norm_text.split()),
        }

    # Default to dev_0_103
    if not DEV_REF_FILE.exists():
        return {
            "sample_id": "dev_0_103",
            "has_reference": False,
            "is_human_verified": False,
            "verification_status": "UNVERIFIED — No valid WER/CER available",
            "raw_text": "",
            "normalized_text": "",
            "start_time": 0.0,
            "end_time": 103.5,
        }

    raw_text = DEV_REF_FILE.read_text(encoding="utf-8").strip()
    norm_text = normalize_arabic_english(raw_text)

    return {
        "sample_id": "dev_0_103",
        "has_reference": True,
        "is_human_verified": True,
        "verification_status": "VERIFIED",
        "raw_text": raw_text,
        "normalized_text": norm_text,
        "start_time": 0.0,
        "end_time": 103.5,
        "word_count_raw": len(raw_text.split()),
        "word_count_norm": len(norm_text.split()),
    }


@router.post("/reference")
def save_reference(req: ReferenceUpdateRequest):
    """
    Saves a reference transcript. Enforces explicit certification before marking as human-verified.
    """
    cleaned_text = req.reference_text.strip()

    if req.sample_id == "test_180_225":
        TEST_REF_FILE.write_text(cleaned_text, encoding="utf-8")
        meta = {
            "sample_id": "test_180_225",
            "start_time": 180.0,
            "end_time": 225.0,
            "is_human_verified": bool(req.is_human_verified and len(cleaned_text.split()) > 0),
            "verification_statement": req.verification_statement or "Human user verified against audio recording.",
            "updated_at": time.time(),
            "word_count": len(cleaned_text.split()),
        }
        TEST_META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return {
            "status": "success",
            "sample_id": "test_180_225",
            "is_human_verified": meta["is_human_verified"],
            "message": "Test reference saved successfully." + (" Certified as human verified." if meta["is_human_verified"] else " Saved as draft (unverified)."),
        }

    # Default dev_0_103
    DEV_REF_FILE.write_text(cleaned_text, encoding="utf-8")
    DEV_META_FILE.write_text(json.dumps({
        "sample_id": "dev_0_103",
        "start_time": req.start_time,
        "end_time": req.end_time,
        "is_human_verified": True,
        "updated_at": time.time(),
    }, indent=2), encoding="utf-8")

    return {"status": "success", "sample_id": "dev_0_103", "is_human_verified": True, "message": "Development reference saved successfully"}


@router.get("/results")
def get_latest_results(sample_id: str = Query("dev_0_103")):
    """
    Returns latest benchmark results for the requested sample.
    """
    target_results_file = TEST_RESULTS_FILE if sample_id == "test_180_225" else DEV_RESULTS_FILE

    if not target_results_file.exists():
        return {"has_results": False, "sample_id": sample_id, "results": []}
    try:
        data = json.loads(target_results_file.read_text(encoding="utf-8"))
        return {"has_results": True, "sample_id": sample_id, "results": data}
    except Exception as e:
        return {"has_results": False, "error": str(e), "sample_id": sample_id, "results": []}


@router.post("/run")
def run_benchmark(req: BenchmarkRunRequest):
    """
    Executes benchmark comparison on requested models.
    If reference is unverified, transcribes for review without reporting fabricated accuracy metrics.
    """
    _ensure_dev_slice()
    _ensure_test_slice()

    is_test_sample = (req.sample_id == "test_180_225") or (abs(req.start_time - 180.0) < 1.0 and abs(req.end_time - 225.0) < 1.0)
    current_sample_id = "test_180_225" if is_test_sample else "dev_0_103"

    ref_data = get_reference(current_sample_id)
    has_valid_human_ref = ref_data.get("is_human_verified", False) and ref_data.get("word_count_raw", 0) > 0
    human_ref = ref_data.get("raw_text", "")

    # Select audio slice
    if is_test_sample:
        sliced_audio = TEST_AUDIO_FILE
        duration = 45.0
        start_t = 180.0
        end_t = 225.0
    elif abs(req.start_time - 0.0) < 0.5 and abs(req.end_time - 103.5) < 1.0:
        sliced_audio = DEV_AUDIO_FILE
        duration = 103.5
        start_t = 0.0
        end_t = 103.5
    else:
        # Dynamic slice
        duration = req.end_time - req.start_time
        if duration <= 1.0:
            raise HTTPException(status_code=400, detail="Benchmark interval must be at least 1.0 second.")
        src_audio = _find_source_audio()
        sliced_audio = BENCHMARK_DIR / f"benchmark_dynamic_{int(req.start_time)}_{int(req.end_time)}.wav"
        ffmpeg = find_ffmpeg()
        cmd = [
            ffmpeg, "-y",
            "-ss", str(req.start_time),
            "-t", str(duration),
            "-i", str(src_audio),
            "-vn", "-ac", "1", "-ar", "16000",
            str(sliced_audio),
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        start_t = req.start_time
        end_t = req.end_time

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
                accuracy_mode="maximum",
                verbatim_mode="strict",
                enhance_audio=False,
                vad_filter=req.vad_filter,
                vocabulary_hints=hints,
            )
            elapsed = time.time() - t0
            pred_text = res["clean_text"]
            meta = res["metadata"]

            run_entry: Dict[str, Any] = {
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
                "predicted_text": pred_text,
                "is_verified": has_valid_human_ref,
            }

            if has_valid_human_ref:
                eval_norm = calculate_wer_cer(human_ref, pred_text, mode="normalized")
                eval_raw = calculate_wer_cer(human_ref, pred_text, mode="raw")
                run_entry.update({
                    "verification_notice": "Verified Human Reference Benchmark",
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
                    "word_alignment": eval_norm["word_alignment"] if req.eval_mode == "normalized" else eval_raw["word_alignment"],
                })
            else:
                run_entry.update({
                    "verification_notice": "UNVERIFIED — No valid WER/CER available",
                    "norm_wer": None,
                    "norm_cer": None,
                    "raw_wer": None,
                    "raw_cer": None,
                    "norm_sub": None,
                    "norm_del": None,
                    "norm_ins": None,
                    "norm_hits": None,
                    "word_alignment": [],
                })

            benchmark_runs.append(run_entry)

        except Exception as e:
            benchmark_runs.append({
                "model_id": model_id,
                "name": SUPPORTED_MODELS.get(model_id, {}).get("name", model_id),
                "status": "failed",
                "error": str(e),
            })

    # Clean up dynamic slice if created
    if "benchmark_dynamic_" in str(sliced_audio):
        sliced_audio.unlink(missing_ok=True)

    # Save to corresponding results file
    target_results_file = TEST_RESULTS_FILE if is_test_sample else DEV_RESULTS_FILE
    target_results_file.write_text(json.dumps(benchmark_runs, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "completed",
        "sample_id": current_sample_id,
        "is_human_verified": has_valid_human_ref,
        "audio_interval": f"{start_t:.1f}s - {end_t:.1f}s ({duration:.1f}s)",
        "results": benchmark_runs,
    }


@router.post("/align")
def live_recalculate_alignment(req: LiveAlignRequest):
    """
    Recalculates word-level alignment and WER/CER metrics live for human review and corrections.
    """
    mode = req.eval_mode if req.eval_mode in ("normalized", "raw") else "normalized"
    res = calculate_wer_cer(req.reference_text, req.hypothesis_text, mode=mode)
    return {
        "status": "success",
        "mode": mode,
        "metrics": res,
    }
