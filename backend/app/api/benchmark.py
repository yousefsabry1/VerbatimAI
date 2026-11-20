import os
import json
import time
import uuid
import hashlib
import logging
import subprocess
import mimetypes
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import STORAGE_DIR, DEFAULT_VOCAB_HINTS, SUPPORTED_MODELS
from app.audio.metadata_extractor import find_ffmpeg, extract_metadata
from app.transcription.engine import run_transcription_pipeline, is_model_downloaded
from app.evaluation.metrics import calculate_wer_cer, normalize_arabic_english, normalize_raw
from app.api.audio import resolve_file
from app.core.database import (
    create_benchmark_sample,
    get_benchmark_sample,
    list_benchmark_samples,
    delete_benchmark_sample,
    update_benchmark_sample_verification,
    list_source_recordings,
    get_job,
)

logger = logging.getLogger("verbatim.benchmark")
router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])

BENCHMARK_DIR = STORAGE_DIR / "benchmarks"
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

# Sample Storage Paths
DEV_REF_FILE = BENCHMARK_DIR / "human_reference_raw.txt"
DEV_AUDIO_FILE = BENCHMARK_DIR / "ref_103s.wav"
DEV_RESULTS_FILE = BENCHMARK_DIR / "benchmark_results.json"
DEV_META_FILE = BENCHMARK_DIR / "benchmark_meta.json"

TEST_REF_FILE = BENCHMARK_DIR / "human_reference_test_180_225.txt"
TEST_AUDIO_FILE = BENCHMARK_DIR / "test_slice_180_225.wav"
TEST_RESULTS_FILE = BENCHMARK_DIR / "benchmark_results_test_180_225.json"
TEST_META_FILE = BENCHMARK_DIR / "benchmark_meta_test_180_225.json"

HOLDOUT_REF_FILE = BENCHMARK_DIR / "human_reference_holdout_300_345.txt"
HOLDOUT_AUDIO_FILE = BENCHMARK_DIR / "holdout_300_345.wav"
HOLDOUT_RESULTS_FILE = BENCHMARK_DIR / "benchmark_results_holdout_300_345.json"
HOLDOUT_META_FILE = BENCHMARK_DIR / "benchmark_meta_holdout_300_345.json"

EVAL_400_445_REF_FILE = BENCHMARK_DIR / "human_reference_eval_400_445.txt"
EVAL_400_445_AUDIO_FILE = BENCHMARK_DIR / "eval_slice_400_445.wav"
EVAL_400_445_RESULTS_FILE = BENCHMARK_DIR / "benchmark_results_eval_400_445.json"
EVAL_400_445_META_FILE = BENCHMARK_DIR / "benchmark_meta_eval_400_445.json"


class ReferenceUpdateRequest(BaseModel):
    sample_id: str = "dev_0_103"
    reference_text: str
    action: Optional[str] = "save_draft"  # "save_draft" or "save_and_verify"
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    is_human_verified: bool = False
    verification_statement: Optional[str] = None


class CalculateAccuracyRequest(BaseModel):
    sample_id: str
    eval_mode: str = "normalized"  # "normalized" or "raw"


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
    audio_filter: Optional[str] = "none"  # "none" or "highpass_gain"


class LiveAlignRequest(BaseModel):
    reference_text: str
    hypothesis_text: str
    eval_mode: str = "normalized"


class CreateSampleRequest(BaseModel):
    name: str
    source_path_or_id: str
    start_time: float
    end_time: float
    description: Optional[str] = None


def _find_source_audio() -> Path:
    for candidate in [
        Path("dd.ogg"),
        Path("../dd.ogg"),
        Path("A:/Projects For Antigravity IDE/General Ideas/1. Transcript voices/dd.ogg"),
        BENCHMARK_DIR / "dd.ogg",
    ]:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError("Workspace recording dd.ogg not found.")


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


def _ensure_holdout_slice():
    """Ensures holdout_300_345.wav (05:00-05:45) is extracted from dd.ogg."""
    if not HOLDOUT_AUDIO_FILE.exists():
        src = _find_source_audio()
        ffmpeg = find_ffmpeg()
        cmd = [
            ffmpeg, "-y",
            "-ss", "300.0",
            "-to", "345.0",
            "-i", str(src),
            "-vn", "-ac", "1", "-ar", "16000",
            str(HOLDOUT_AUDIO_FILE),
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def _ensure_eval_400_445_slice():
    """Ensures eval_slice_400_445.wav (06:40-07:25) is extracted from dd.ogg."""
    if not EVAL_400_445_AUDIO_FILE.exists():
        src = _find_source_audio()
        ffmpeg = find_ffmpeg()
        cmd = [
            ffmpeg, "-y",
            "-ss", "400.0",
            "-to", "445.0",
            "-i", str(src),
            "-vn", "-ac", "1", "-ar", "16000",
            str(EVAL_400_445_AUDIO_FILE),
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def _resolve_benchmark_source_audio(source_path_or_id: str) -> Tuple[Path, Optional[str], Optional[str]]:
    """
    Resolves source audio for benchmark sample creation.
    Returns: (resolved_path, source_job_id, source_filename)
    """
    clean_id = source_path_or_id.strip()

    # 1. Try resolving via get_job
    try:
        job = get_job(clean_id)
        if job and job.get("input_path"):
            p = Path(job["input_path"])
            if p.is_file():
                return p, job["id"], job.get("input_filename", p.name)
    except Exception:
        pass

    # 2. Try resolve_file from audio api
    try:
        resolved = resolve_file(clean_id)
        if resolved.is_file():
            return resolved, None, resolved.name
    except Exception:
        pass

    # 3. Direct path check
    cand = Path(clean_id)
    if cand.is_file():
        return cand.resolve(), None, cand.name

    # 4. Search in uploads and workspace
    for search_dir in [STORAGE_DIR / "uploads", Path("."), Path("..")]:
        direct = search_dir / clean_id
        if direct.is_file():
            return direct.resolve(), None, direct.name
        for matched in search_dir.glob(f"*{clean_id}*"):
            if matched.is_file():
                return matched.resolve(), None, matched.name

    raise HTTPException(status_code=404, detail=f"Source recording '{source_path_or_id}' could not be resolved.")


# Canonical static baseline sample configurations
SAMPLE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "dev_0_103": {
        "sample_id": "dev_0_103",
        "name": "Development Sample (00:00 - 01:43)",
        "start_time": 0.0,
        "end_time": 103.5,
        "duration": 103.5,
        "ref_file": DEV_REF_FILE,
        "audio_file": DEV_AUDIO_FILE,
        "results_file": DEV_RESULTS_FILE,
        "meta_file": DEV_META_FILE,
        "ensure_fn": _ensure_dev_slice,
        "default_verified": True,
        "is_dynamic": False,
        "description": "Original human ground-truth transcript provided by the user. Baseline: 52.71% Normalized WER.",
    },
    "test_180_225": {
        "sample_id": "test_180_225",
        "name": "Independent Test Sample (03:00 - 03:45)",
        "start_time": 180.0,
        "end_time": 225.0,
        "duration": 45.0,
        "ref_file": TEST_REF_FILE,
        "audio_file": TEST_AUDIO_FILE,
        "results_file": TEST_RESULTS_FILE,
        "meta_file": TEST_META_FILE,
        "ensure_fn": _ensure_test_slice,
        "default_verified": True,
        "is_dynamic": False,
        "description": "Independent 45s out-of-sample audio interval. Personally transcribed by the user from original audio.",
    },
    "holdout_300_345": {
        "sample_id": "holdout_300_345",
        "name": "Unseen Holdout Sample (05:00 - 05:45)",
        "start_time": 300.0,
        "end_time": 345.0,
        "duration": 45.0,
        "ref_file": HOLDOUT_REF_FILE,
        "audio_file": HOLDOUT_AUDIO_FILE,
        "results_file": HOLDOUT_RESULTS_FILE,
        "meta_file": HOLDOUT_META_FILE,
        "ensure_fn": _ensure_holdout_slice,
        "default_verified": False,
        "is_dynamic": False,
        "description": "Strict unseen out-of-sample holdout audio interval (05:00 - 05:45). Reference manually transcribed by user.",
    },
    "eval_400_445": {
        "sample_id": "eval_400_445",
        "name": "Untouched Holdout Sample (06:40 - 07:25)",
        "start_time": 400.0,
        "end_time": 445.0,
        "duration": 45.0,
        "ref_file": EVAL_400_445_REF_FILE,
        "audio_file": EVAL_400_445_AUDIO_FILE,
        "results_file": EVAL_400_445_RESULTS_FILE,
        "meta_file": EVAL_400_445_META_FILE,
        "ensure_fn": _ensure_eval_400_445_slice,
        "default_verified": False,
        "is_dynamic": False,
        "description": "New independent untouched holdout interval (06:40 - 07:25). Reference left empty for human verification. Never contains synthetic ground truth.",
    },
}

STATIC_SAMPLE_CONFIGS = SAMPLE_CONFIGS


def get_sample_config(sample_id: str) -> Dict[str, Any]:
    if sample_id in SAMPLE_CONFIGS:
        return SAMPLE_CONFIGS[sample_id]

    sample = get_benchmark_sample(sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail=f"Unknown benchmark sample '{sample_id}'.")

    return {
        "sample_id": sample["id"],
        "name": sample["name"],
        "source_job_id": sample.get("source_job_id"),
        "source_filename": sample.get("source_filename"),
        "start_time": float(sample["start_time"]),
        "end_time": float(sample["end_time"]),
        "duration": float(sample["duration"]),
        "ref_file": Path(sample["ref_file_path"]),
        "audio_file": Path(sample["audio_file_path"]),
        "results_file": Path(sample["results_file_path"]),
        "meta_file": Path(sample["meta_file_path"]),
        "ensure_fn": lambda: None,
        "default_verified": False,
        "is_dynamic": True,
        "description": sample.get("description") or f"Dynamic benchmark sample from {sample.get('source_filename', 'recording')} ({sample['start_time']:.1f}s - {sample['end_time']:.1f}s).",
    }


def get_all_sample_configs() -> Dict[str, Dict[str, Any]]:
    configs = dict(SAMPLE_CONFIGS)
    try:
        db_samples = list_benchmark_samples()
        for sample in db_samples:
            s_id = sample["id"]
            configs[s_id] = {
                "sample_id": s_id,
                "name": sample["name"],
                "source_job_id": sample.get("source_job_id"),
                "source_filename": sample.get("source_filename"),
                "start_time": float(sample["start_time"]),
                "end_time": float(sample["end_time"]),
                "duration": float(sample["duration"]),
                "ref_file": Path(sample["ref_file_path"]),
                "audio_file": Path(sample["audio_file_path"]),
                "results_file": Path(sample["results_file_path"]),
                "meta_file": Path(sample["meta_file_path"]),
                "ensure_fn": lambda: None,
                "default_verified": False,
                "is_dynamic": True,
                "description": sample.get("description") or f"Dynamic benchmark sample from {sample.get('source_filename', 'recording')} ({sample['start_time']:.1f}s - {sample['end_time']:.1f}s).",
            }
    except Exception as e:
        logger.error("Failed to load dynamic benchmark samples: %s", e)
    return configs


@router.get("/samples")
def get_benchmark_samples():
    """
    Returns the catalog of registered benchmark evaluation intervals with their canonical metadata.
    """
    catalog = []
    configs = get_all_sample_configs()
    for s_id, cfg in configs.items():
        cfg["ensure_fn"]()
        raw_text = ""
        if cfg["ref_file"].exists():
            raw_text = cfg["ref_file"].read_text(encoding="utf-8").strip()
        word_count = len(raw_text.split())

        is_verified = False
        if cfg["meta_file"].exists():
            try:
                m = json.loads(cfg["meta_file"].read_text(encoding="utf-8"))
                is_verified = bool(m.get("is_human_verified", False) and word_count > 0)
            except Exception:
                is_verified = False
        else:
            is_verified = bool(cfg["default_verified"] and word_count > 0)

        badge = (
            f"Verified Human Reference ({word_count} words)"
            if is_verified
            else (f"Draft Saved ({word_count} words) — Unverified" if word_count > 0 else "UNVERIFIED — Pending Human Transcription")
        )

        catalog.append({
            "sample_id": s_id,
            "name": cfg["name"],
            "source_filename": cfg.get("source_filename"),
            "start_time": cfg["start_time"],
            "end_time": cfg["end_time"],
            "duration": cfg["duration"],
            "audio_url": f"/api/benchmark/audio/{s_id}",
            "status": "VERIFIED" if is_verified else "UNVERIFIED",
            "verification_badge": badge,
            "has_human_reference": word_count > 0,
            "is_human_verified": is_verified,
            "word_count": word_count,
            "is_dynamic": bool(cfg.get("is_dynamic", False)),
            "description": cfg["description"],
        })

    return {
        "samples": catalog,
        "audit_notice": {
            "invalidated_slice": "04:05 - 04:55 (245s - 295s)",
            "reason": "Retracted due to circular AI pseudo-ground-truth generation. 30.22% WER invalidated.",
            "integrity_rule": "No ASR prediction can be labeled as human reference without explicit human certification.",
        },
    }


@router.get("/source-recordings")
def get_benchmark_source_recordings():
    """
    Returns available source recordings from History to create benchmark samples.
    """
    recordings = list_source_recordings()
    return {"recordings": recordings}


@router.get("/preview-source")
def preview_source_interval(
    source_path_or_id: str = Query(...),
    start_time: float = Query(...),
    end_time: float = Query(...),
):
    """
    Extracts and streams a temporary preview slice from any recording to listen before creating a benchmark sample.
    """
    source_path, _, _ = _resolve_benchmark_source_audio(source_path_or_id)
    if start_time < 0:
        start_time = 0.0
    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="End time must be greater than start time.")
    if (end_time - start_time) > 180.0:
        end_time = start_time + 180.0

    preview_dir = BENCHMARK_DIR / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    hash_str = hashlib.md5(f"{source_path}_{start_time:.2f}_{end_time:.2f}".encode()).hexdigest()[:16]
    preview_file = preview_dir / f"prev_{hash_str}.wav"

    if not preview_file.exists() or preview_file.stat().st_size == 0:
        ffmpeg = find_ffmpeg()
        cmd = [
            ffmpeg, "-y",
            "-ss", str(start_time),
            "-to", str(end_time),
            "-i", str(source_path),
            "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(preview_file),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0 or not preview_file.exists():
            raise HTTPException(status_code=500, detail="Failed to extract audio preview.")

    return FileResponse(
        path=preview_file,
        media_type="audio/wav",
        filename=f"preview_{start_time:.0f}_{end_time:.0f}.wav",
        headers={"Accept-Ranges": "bytes"}
    )


@router.post("/sample")
def create_sample(req: CreateSampleRequest):
    """
    Creates a new dynamic benchmark evaluation sample from any uploaded recording.
    Extracts an isolated 16kHz mono WAV slice to prevent deletion on temporary upload cleanup.
    """
    clean_name = req.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Sample name is required.")

    source_path, source_job_id, source_filename = _resolve_benchmark_source_audio(req.source_path_or_id)

    # Validate audio with extract_metadata
    meta = extract_metadata(source_path)
    if not meta.get("is_valid_audio"):
        raise HTTPException(status_code=400, detail=f"Source file is not a valid audio recording: {meta.get('error')}")

    total_duration = meta.get("duration", 0.0)
    if total_duration <= 0:
        raise HTTPException(status_code=400, detail="Cannot determine duration of source audio.")

    start_t = round(float(req.start_time), 2)
    end_t = round(float(req.end_time), 2)

    if start_t < 0:
        raise HTTPException(status_code=400, detail="Start time must be >= 0.0s.")
    if end_t <= start_t:
        raise HTTPException(status_code=400, detail=f"End time ({end_t}s) must be greater than start time ({start_t}s).")
    if end_t > (total_duration + 1.0):
        raise HTTPException(
            status_code=400,
            detail=f"End time ({end_t:.1f}s) exceeds total recording duration ({total_duration:.1f}s)."
        )

    interval_duration = round(min(end_t, total_duration) - start_t, 2)
    if interval_duration < 2.0:
        raise HTTPException(status_code=400, detail="Evaluation interval must be at least 2.0 seconds.")
    if interval_duration > 600.0:
        raise HTTPException(status_code=400, detail="Evaluation interval cannot exceed 10 minutes.")

    # Unique sample ID
    sample_id = f"sample_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    # Target files
    target_audio = BENCHMARK_DIR / f"{sample_id}.wav"
    ref_file = BENCHMARK_DIR / f"{sample_id}_ref.txt"
    meta_file = BENCHMARK_DIR / f"{sample_id}_meta.json"
    results_file = BENCHMARK_DIR / f"{sample_id}_results.json"

    # Extract isolated 16kHz mono 16-bit PCM WAV slice
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-ss", str(start_t),
        "-to", str(end_t),
        "-i", str(source_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(target_audio),
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0 or not target_audio.exists() or target_audio.stat().st_size == 0:
        err = res.stderr.decode("utf-8", errors="replace")[-300:]
        raise HTTPException(status_code=500, detail=f"FFmpeg audio extraction failed: {err}")

    # Initialize empty reference (never copy ASR predictions)
    ref_file.write_text("", encoding="utf-8")

    # Initialize meta file
    sample_meta = {
        "sample_id": sample_id,
        "sample_name": clean_name,
        "source_job_id": source_job_id,
        "source_filename": source_filename,
        "source_path": str(source_path),
        "start_time": start_t,
        "end_time": end_t,
        "duration": interval_duration,
        "is_human_verified": False,
        "verification_status": "NO_REFERENCE",
        "verification_statement": None,
        "verification_timestamp": None,
        "verification_method": None,
        "created_at": time.time(),
        "updated_at": time.time(),
        "word_count": 0,
        "revisions": [],
    }
    meta_file.write_text(json.dumps(sample_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # Initialize empty results
    results_file.write_text("[]", encoding="utf-8")

    # Insert into database
    create_benchmark_sample({
        "id": sample_id,
        "name": clean_name,
        "source_job_id": source_job_id,
        "source_filename": source_filename,
        "source_path": str(source_path),
        "start_time": start_t,
        "end_time": end_t,
        "duration": interval_duration,
        "audio_file_path": str(target_audio),
        "ref_file_path": str(ref_file),
        "results_file_path": str(results_file),
        "meta_file_path": str(meta_file),
        "description": req.description or f"Dynamic benchmark sample from {source_filename} ({start_t:.1f}s - {end_t:.1f}s).",
    })

    return {
        "status": "created",
        "sample": {
            "sample_id": sample_id,
            "name": clean_name,
            "source_filename": source_filename,
            "start_time": start_t,
            "end_time": end_t,
            "duration": interval_duration,
            "audio_url": f"/api/benchmark/audio/{sample_id}",
            "status": "UNVERIFIED",
            "verification_badge": "UNVERIFIED — Pending Human Transcription",
            "has_human_reference": False,
            "is_human_verified": False,
            "word_count": 0,
            "is_dynamic": True,
            "description": req.description or f"Dynamic benchmark sample from {source_filename} ({start_t:.1f}s - {end_t:.1f}s).",
        }
    }


@router.delete("/sample/{sample_id}")
def delete_sample(sample_id: str):
    """
    Deletes a dynamic benchmark sample and its isolated audio/reference files.
    Predefined baseline samples cannot be deleted.
    """
    if sample_id in SAMPLE_CONFIGS:
        raise HTTPException(status_code=400, detail="Cannot delete predefined benchmark sample.")

    sample = get_benchmark_sample(sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail=f"Benchmark sample '{sample_id}' not found.")

    for p_key in ["audio_file_path", "ref_file_path", "results_file_path", "meta_file_path"]:
        path_str = sample.get(p_key)
        if path_str:
            Path(path_str).unlink(missing_ok=True)

    delete_benchmark_sample(sample_id)
    return {"status": "deleted", "sample_id": sample_id}


@router.get("/audio/{sample_id}")
def stream_benchmark_audio(sample_id: str):
    """
    Streams audio for the requested benchmark sample with byte-range support.
    """
    if sample_id == "full":
        target = _find_source_audio()
    else:
        try:
            cfg = get_sample_config(sample_id)
            cfg["ensure_fn"]()
            target = cfg["audio_file"]
        except Exception:
            p = BENCHMARK_DIR / sample_id
            if p.is_file():
                target = p
            else:
                raise HTTPException(status_code=404, detail=f"Benchmark audio '{sample_id}' not found.")

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Benchmark audio file for '{sample_id}' does not exist on disk.")

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
    Retrieves the reference transcript, revision hash, and verification metadata for a benchmark sample.
    """
    cfg = get_sample_config(sample_id)
    cfg["ensure_fn"]()

    raw_text = ""
    if cfg["ref_file"].exists():
        raw_text = cfg["ref_file"].read_text(encoding="utf-8").strip()

    word_count_raw = len(raw_text.split())
    norm_text = normalize_arabic_english(raw_text) if raw_text else ""
    word_count_norm = len(norm_text.split()) if norm_text else 0

    meta: Dict[str, Any] = {}
    if cfg["meta_file"].exists():
        try:
            meta = json.loads(cfg["meta_file"].read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    is_verified = False
    if "is_human_verified" in meta:
        is_verified = bool(meta.get("is_human_verified", False) and word_count_raw > 0)
    else:
        is_verified = bool(cfg["default_verified"] and word_count_raw > 0)

    if word_count_raw == 0:
        v_status = "NO_REFERENCE"
        v_badge = "UNVERIFIED — Pending Human Transcription"
    elif is_verified:
        v_status = "HUMAN_VERIFIED"
        v_badge = f"Verified Human Reference ({word_count_raw} words)"
    else:
        v_status = "DRAFT"
        v_badge = f"Draft Saved ({word_count_raw} words) — Unverified"

    rev_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:12] if raw_text else ""

    return {
        "sample_id": sample_id,
        "sample_name": cfg["name"],
        "source_filename": cfg.get("source_filename"),
        "has_reference": word_count_raw > 0,
        "is_human_verified": is_verified,
        "verification_status": v_status,
        "verification_badge": v_badge,
        "verification_statement": meta.get("verification_statement"),
        "verification_timestamp": meta.get("verification_timestamp"),
        "verification_method": meta.get("verification_method"),
        "reference_revision": rev_hash,
        "raw_text": raw_text,
        "normalized_text": norm_text,
        "start_time": cfg["start_time"],
        "end_time": cfg["end_time"],
        "duration": cfg["duration"],
        "word_count_raw": word_count_raw,
        "word_count_norm": word_count_norm,
        "updated_at": meta.get("updated_at"),
    }


@router.post("/reference")
def save_reference(req: ReferenceUpdateRequest):
    """
    Saves a reference transcript. Supports saving as unverified draft or certifying as human-verified.
    """
    cfg = get_sample_config(req.sample_id)
    cleaned_text = req.reference_text.strip()
    if not cleaned_text:
        raise HTTPException(status_code=400, detail="Reference text cannot be empty.")

    is_certifying = req.action == "save_and_verify" or req.is_human_verified

    if is_certifying:
        if not req.is_human_verified:
            raise HTTPException(
                status_code=400,
                detail="Integrity Safeguard: You must certify that you personally listened to the audio and manually verified this transcript before certifying."
            )
        is_verified = True
        v_status = "HUMAN_VERIFIED"
        v_method = "explicit_human_certification"
        v_stmt = req.verification_statement or "I confirm that I personally listened to the original audio and manually verified this transcript against what was actually spoken."
        v_time = time.time()
        msg = "Human reference verified successfully. Accuracy evaluation is now available."
    else:
        is_verified = False
        v_status = "DRAFT"
        v_method = None
        v_stmt = None
        v_time = None
        msg = "Reference draft saved successfully. Verification is still required before accuracy metrics can be calculated."

    # Write raw reference file
    cfg["ref_file"].write_text(cleaned_text, encoding="utf-8")
    rev_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()[:12]

    # Load existing meta to preserve audit history
    prev_meta = {}
    if cfg["meta_file"].exists():
        try:
            prev_meta = json.loads(cfg["meta_file"].read_text(encoding="utf-8"))
        except Exception:
            prev_meta = {}

    revisions = prev_meta.get("revisions", [])
    if prev_meta.get("reference_revision") and prev_meta.get("reference_revision") != rev_hash:
        revisions.append({
            "revision": prev_meta.get("reference_revision"),
            "is_human_verified": prev_meta.get("is_human_verified", False),
            "updated_at": prev_meta.get("updated_at"),
            "word_count": prev_meta.get("word_count", 0),
        })

    meta = {
        "sample_id": req.sample_id,
        "reference_revision": rev_hash,
        "start_time": cfg["start_time"],
        "end_time": cfg["end_time"],
        "duration": cfg["duration"],
        "is_human_verified": is_verified,
        "verification_status": v_status,
        "verification_statement": v_stmt,
        "verification_method": v_method,
        "verification_timestamp": v_time,
        "updated_at": time.time(),
        "word_count": len(cleaned_text.split()),
        "revisions": revisions[-10:],
    }
    cfg["meta_file"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    if cfg.get("is_dynamic"):
        try:
            update_benchmark_sample_verification(req.sample_id, is_verified)
        except Exception as e:
            logger.warning("Could not update verification status in DB for %s: %s", req.sample_id, e)

    # Invalidate or auto-evaluate cached predictions in results_file
    if cfg["results_file"].exists():
        try:
            runs = json.loads(cfg["results_file"].read_text(encoding="utf-8"))
            if not is_verified:
                # Mark all existing metrics as unverified draft
                for r in runs:
                    r["is_verified"] = False
                    r["verification_notice"] = "UNVERIFIED — Reference is currently an unverified draft"
                    r["norm_wer"] = None
                    r["norm_cer"] = None
                    r["raw_wer"] = None
                    r["raw_cer"] = None
                    r["norm_sub"] = None
                    r["norm_del"] = None
                    r["norm_ins"] = None
                    r["norm_hits"] = None
                cfg["results_file"].write_text(json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8")
            else:
                # Certified human reference: calculate WER/CER for existing valid predictions
                updated = False
                for r in runs:
                    if r.get("status") == "success" and r.get("predicted_text"):
                        pred_text = r["predicted_text"]
                        eval_norm = calculate_wer_cer(cleaned_text, pred_text, mode="normalized")
                        eval_raw = calculate_wer_cer(cleaned_text, pred_text, mode="raw")
                        r["sample_id"] = req.sample_id
                        r["sample_name"] = cfg["name"]
                        r["is_verified"] = True
                        r["verification_notice"] = "Verified Human Reference Benchmark"
                        r["norm_wer"] = eval_norm["wer_percent"]
                        r["norm_cer"] = eval_norm["cer_percent"]
                        r["norm_sub"] = eval_norm["substitutions"]
                        r["norm_del"] = eval_norm["deletions"]
                        r["norm_ins"] = eval_norm["insertions"]
                        r["norm_hits"] = eval_norm["hits"]
                        r["raw_wer"] = eval_raw["wer_percent"]
                        r["raw_cer"] = eval_raw["cer_percent"]
                        r["raw_sub"] = eval_raw["substitutions"]
                        r["raw_del"] = eval_raw["deletions"]
                        r["raw_ins"] = eval_raw["insertions"]
                        r["word_alignment"] = eval_norm["word_alignment"]
                        r["reference_revision"] = rev_hash
                        r["evaluated_at"] = time.time()
                        updated = True
                if updated:
                    cfg["results_file"].write_text(json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    return {
        "status": "success",
        "sample_id": req.sample_id,
        "sample_name": cfg["name"],
        "is_human_verified": is_verified,
        "verification_status": v_status,
        "word_count": len(cleaned_text.split()),
        "reference_revision": rev_hash,
        "message": msg,
    }


@router.post("/calculate-accuracy")
def calculate_benchmark_accuracy(req: CalculateAccuracyRequest):
    """
    Evaluates existing candidate model predictions against the certified human reference without re-running models.
    """
    cfg = get_sample_config(req.sample_id)
    if not cfg["ref_file"].exists():
        raise HTTPException(status_code=400, detail="Cannot calculate accuracy: No reference text found.")

    human_ref = cfg["ref_file"].read_text(encoding="utf-8").strip()
    if not human_ref:
        raise HTTPException(status_code=400, detail="Cannot calculate accuracy: Reference text is empty.")

    meta = {}
    if cfg["meta_file"].exists():
        try:
            meta = json.loads(cfg["meta_file"].read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    is_verified = bool(meta.get("is_human_verified", False) or (cfg["default_verified"] and len(human_ref.split()) > 0))
    if not is_verified:
        raise HTTPException(
            status_code=400,
            detail="Cannot calculate accuracy: Human reference is marked as DRAFT. Please certify the reference as manually verified first."
        )

    if not cfg["results_file"].exists():
        raise HTTPException(status_code=400, detail="No candidate predictions found for this sample. Please run candidate models first.")

    try:
        runs = json.loads(cfg["results_file"].read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load candidate predictions: {e}")

    rev_hash = hashlib.sha256(human_ref.encode("utf-8")).hexdigest()[:12]
    eval_mode = req.eval_mode if req.eval_mode in ("normalized", "raw") else "normalized"

    evaluated_count = 0
    for r in runs:
        if r.get("status") == "success" and r.get("predicted_text"):
            pred_text = r["predicted_text"]
            eval_norm = calculate_wer_cer(human_ref, pred_text, mode="normalized")
            eval_raw = calculate_wer_cer(human_ref, pred_text, mode="raw")
            r["sample_id"] = req.sample_id
            r["sample_name"] = cfg["name"]
            r["is_verified"] = True
            r["verification_notice"] = "Verified Human Reference Benchmark"
            r["norm_wer"] = eval_norm["wer_percent"]
            r["norm_cer"] = eval_norm["cer_percent"]
            r["norm_sub"] = eval_norm["substitutions"]
            r["norm_del"] = eval_norm["deletions"]
            r["norm_ins"] = eval_norm["insertions"]
            r["norm_hits"] = eval_norm["hits"]
            r["raw_wer"] = eval_raw["wer_percent"]
            r["raw_cer"] = eval_raw["cer_percent"]
            r["raw_sub"] = eval_raw["substitutions"]
            r["raw_del"] = eval_raw["deletions"]
            r["raw_ins"] = eval_raw["insertions"]
            r["word_alignment"] = eval_norm["word_alignment"] if eval_mode == "normalized" else eval_raw["word_alignment"]
            r["reference_revision"] = rev_hash
            r["evaluated_at"] = time.time()
            evaluated_count += 1

    cfg["results_file"].write_text(json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "status": "success",
        "sample_id": req.sample_id,
        "sample_name": cfg["name"],
        "is_human_verified": True,
        "eval_mode": eval_mode,
        "evaluated_models": evaluated_count,
        "results": runs,
    }


@router.get("/results")
def get_latest_results(sample_id: str = Query("dev_0_103")):
    """
    Returns latest benchmark results for the requested sample with verified sample identity.
    """
    try:
        cfg = get_sample_config(sample_id)
    except Exception:
        sample_id = "dev_0_103"
        cfg = get_sample_config(sample_id)

    target_results_file = cfg["results_file"]

    is_verified = cfg["default_verified"]
    if cfg["meta_file"].exists():
        try:
            m = json.loads(cfg["meta_file"].read_text(encoding="utf-8"))
            is_verified = bool(m.get("is_human_verified", False))
        except Exception:
            pass

    if not target_results_file.exists():
        return {
            "has_results": False,
            "sample_id": sample_id,
            "sample_name": cfg["name"],
            "is_human_verified": is_verified,
            "results": [],
        }

    try:
        data = json.loads(target_results_file.read_text(encoding="utf-8"))
        # Enforce canonical sample identity on all result objects
        for item in data:
            item["sample_id"] = sample_id
            item["sample_name"] = cfg["name"]
        return {
            "has_results": True,
            "sample_id": sample_id,
            "sample_name": cfg["name"],
            "is_human_verified": is_verified,
            "results": data,
        }
    except Exception as e:
        return {
            "has_results": False,
            "error": str(e),
            "sample_id": sample_id,
            "sample_name": cfg["name"],
            "is_human_verified": is_verified,
            "results": [],
        }


def run_qwencleo_benchmark(active_audio: Path, duration: float, device_mode: str) -> Dict[str, Any]:
    """
    Executes QwenCleo 4-bit inference in an isolated subprocess using experimental_venv.
    Guarantees zero dependency collision with production Faster-Whisper and complete VRAM release.
    """
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    exp_py = project_root / "experimental_venv" / "Scripts" / "python.exe"
    runner_py = project_root / "backend" / "app" / "transcription" / "qwencleo_runner.py"

    if not exp_py.exists():
        raise RuntimeError(f"Isolated experimental python environment not found at {exp_py}")
    if not runner_py.exists():
        raise RuntimeError(f"QwenCleo runner script not found at {runner_py}")

    temp_out = BENCHMARK_DIR / f"qwencleo_run_{int(time.time() * 1000)}.json"
    target_device = "cuda" if device_mode != "cpu" else "cpu"

    cmd = [
        str(exp_py),
        str(runner_py),
        "--audio", str(active_audio),
        "--output", str(temp_out),
        "--device", target_device,
    ]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        if proc.returncode != 0 or not temp_out.exists():
            err_msg = proc.stderr.strip() or proc.stdout.strip() or f"Process exited with code {proc.returncode}"
            raise RuntimeError(f"QwenCleo execution failed: {err_msg}")

        result_data = json.loads(temp_out.read_text(encoding="utf-8"))
        if result_data.get("status") == "error":
            raise RuntimeError(result_data.get("error", "Unknown error in QwenCleo runner"))

        return result_data
    finally:
        if temp_out.exists():
            temp_out.unlink(missing_ok=True)


@router.post("/run")
def run_benchmark(req: BenchmarkRunRequest):
    """
    Executes benchmark comparison on requested models.
    If reference is unverified, transcribes for review without reporting fabricated accuracy metrics.
    """
    configs = get_all_sample_configs()
    if req.sample_id in configs:
        current_sample_id = req.sample_id
    elif abs(req.start_time - 300.0) < 1.0:
        current_sample_id = "holdout_300_345"
    elif abs(req.start_time - 180.0) < 1.0:
        current_sample_id = "test_180_225"
    elif abs(req.start_time - 400.0) < 1.0:
        current_sample_id = "eval_400_445"
    else:
        current_sample_id = "dev_0_103"

    cfg = get_sample_config(current_sample_id)
    cfg["ensure_fn"]()

    ref_data = get_reference(current_sample_id)
    has_valid_human_ref = ref_data.get("is_human_verified", False) and ref_data.get("word_count_raw", 0) > 0
    human_ref = ref_data.get("raw_text", "")
    rev_hash = ref_data.get("reference_revision", "")

    # Handle audio slice & optional audio preprocessing filter
    base_audio = cfg["audio_file"]
    duration = cfg["duration"]
    start_t = cfg["start_time"]
    end_t = cfg["end_time"]
    temp_filtered_audio: Optional[Path] = None

    if req.audio_filter == "highpass_gain":
        temp_filtered_audio = BENCHMARK_DIR / f"temp_{current_sample_id}_highpass_gain_{int(time.time())}.wav"
        ffmpeg = find_ffmpeg()
        cmd = [
            ffmpeg, "-y",
            "-i", str(base_audio),
            "-af", "highpass=f=80,volume=3dB",
            "-ac", "1", "-ar", "16000",
            str(temp_filtered_audio),
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        active_audio = temp_filtered_audio
    else:
        active_audio = base_audio

    benchmark_runs = []

    for model_id in req.model_ids:
        if not is_model_downloaded(model_id):
            benchmark_runs.append({
                "sample_id": current_sample_id,
                "sample_name": cfg["name"],
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
            if model_id == "qwencleo-asr-4bit":
                qwen_res = run_qwencleo_benchmark(active_audio, duration, req.device_mode)
                elapsed = qwen_res.get("elapsed_seconds", time.time() - t0)
                pred_text = qwen_res.get("text", "")
                device_used = qwen_res.get("device", "cuda")
                compute_used = qwen_res.get("compute", "4-bit NF4")
                cuda_fallback = False
                dev_transitions = []
                rep_detected = 0
                rep_resolved = 0
            elif model_id == "hybrid-v1":
                from app.transcription.hybrid_orchestrator import run_hybrid_asr_pipeline
                hybrid_res = run_hybrid_asr_pipeline(
                    audio_path=active_audio,
                    duration_seconds=duration,
                    device_mode=req.device_mode,
                    include_qwencleo=False,
                )
                elapsed = time.time() - t0
                pred_text = hybrid_res["fusion_hypotheses"]["conservative_agreement"]["text"]
                device_used = "cuda"
                compute_used = "Hybrid Fusion (Specialized + Turbo)"
                cuda_fallback = False
                dev_transitions = []
                rep_detected = 0
                rep_resolved = 0
            elif model_id == "codeswitched-medium-recovery":
                res = run_transcription_pipeline(
                    input_path=active_audio,
                    job_id=job_id,
                    model_id="codeswitched-medium",
                    language="ar",
                    device_mode=req.device_mode,
                    compute_mode="auto",
                    accuracy_mode="recovery",
                    verbatim_mode="strict",
                    enhance_audio=False,
                    vad_filter=req.vad_filter,
                    vocabulary_hints=hints,
                )
                elapsed = time.time() - t0
                pred_text = res["clean_text"]
                meta = res["metadata"]
                device_used = meta.get("device_used")
                compute_used = meta.get("compute_used")
                cuda_fallback = meta.get("cuda_fallback", False)
                dev_transitions = meta.get("device_transitions", [])
                rep_detected = meta.get("repetition_loops_detected", 0)
                rep_resolved = meta.get("repetition_loops_resolved", 0)
            else:
                res = run_transcription_pipeline(
                    input_path=active_audio,
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
                device_used = meta.get("device_used")
                compute_used = meta.get("compute_used")
                cuda_fallback = meta.get("cuda_fallback", False)
                dev_transitions = meta.get("device_transitions", [])
                rep_detected = meta.get("repetition_loops_detected", 0)
                rep_resolved = meta.get("repetition_loops_resolved", 0)

            run_entry: Dict[str, Any] = {
                "sample_id": current_sample_id,
                "sample_name": cfg["name"],
                "audio_filter": req.audio_filter or "none",
                "model_id": model_id,
                "name": SUPPORTED_MODELS.get(model_id, {}).get("name", model_id),
                "status": "success",
                "device": device_used,
                "compute": compute_used,
                "cuda_fallback": cuda_fallback,
                "device_transitions": dev_transitions,
                "repetition_loops_detected": rep_detected,
                "repetition_loops_resolved": rep_resolved,
                "elapsed_seconds": round(elapsed, 2),
                "speedup": round(duration / max(0.1, elapsed), 2),
                "predicted_text": pred_text,
                "is_verified": has_valid_human_ref,
                "reference_revision": rev_hash,
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
                "sample_id": current_sample_id,
                "sample_name": cfg["name"],
                "model_id": model_id,
                "name": SUPPORTED_MODELS.get(model_id, {}).get("name", model_id),
                "status": "failed",
                "error": str(e),
            })

    # Cleanup temp filtered audio
    if temp_filtered_audio and temp_filtered_audio.exists():
        temp_filtered_audio.unlink(missing_ok=True)

    # Save to canonical results file
    cfg["results_file"].write_text(json.dumps(benchmark_runs, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "completed",
        "sample_id": current_sample_id,
        "sample_name": cfg["name"],
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
