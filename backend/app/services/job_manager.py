import os
import uuid
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List

from app.core.database import (
    create_job,
    update_job_progress,
    complete_job,
    fail_job,
    get_job,
    save_transcript,
)
from app.audio.metadata_extractor import extract_metadata
from app.transcription.engine import run_transcription_pipeline
from app.conversion.converter_engine import convert_audio_file
from app.core.config import OUTPUTS_DIR

logger = logging.getLogger(__name__)

# Controlled background thread pool (max 2 concurrent heavy jobs)
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="VerbatimWorker")

# In-memory progress subscribers for SSE streaming
# job_id -> list of asyncio.Queue
_JOB_SUBSCRIBERS: Dict[str, List[asyncio.Queue]] = {}
_ACTIVE_CANCELLATIONS: set[str] = set()


def register_subscriber(job_id: str) -> asyncio.Queue:
    q = asyncio.Queue()
    if job_id not in _JOB_SUBSCRIBERS:
        _JOB_SUBSCRIBERS[job_id] = []
    _JOB_SUBSCRIBERS[job_id].append(q)
    return q


def unregister_subscriber(job_id: str, q: asyncio.Queue):
    if job_id in _JOB_SUBSCRIBERS:
        try:
            _JOB_SUBSCRIBERS[job_id].remove(q)
            if not _JOB_SUBSCRIBERS[job_id]:
                del _JOB_SUBSCRIBERS[job_id]
        except ValueError:
            pass


def broadcast_progress(job_id: str, progress: float, stage: str, status: str = "processing"):
    update_job_progress(job_id, progress, stage)
    if job_id in _JOB_SUBSCRIBERS:
        msg = {
            "job_id": job_id,
            "progress": round(progress, 3),
            "stage": stage,
            "status": status,
        }
        for q in list(_JOB_SUBSCRIBERS[job_id]):
            try:
                q.put_nowait(msg)
            except Exception:
                pass


def cancel_job(job_id: str) -> bool:
    _ACTIVE_CANCELLATIONS.add(job_id)
    fail_job(job_id, "Job was cancelled by user.")
    broadcast_progress(job_id, 0.0, "Cancelled", status="cancelled")
    return True


def submit_transcription_job(
    input_path: Path,
    input_filename: str,
    model_id: str = "medium",
    language: Optional[str] = None,
    device_mode: str = "auto",
    compute_mode: str = "auto",
    accuracy_mode: str = "balanced",
    verbatim_mode: str = "strict",
    enhance_audio: bool = False,
    vad_filter: bool = True,
) -> str:
    job_id = uuid.uuid4().hex[:10]
    meta = extract_metadata(input_path)

    job_data = {
        "id": job_id,
        "job_type": "transcription",
        "status": "queued",
        "progress": 0.0,
        "stage": "Queued",
        "input_filename": input_filename,
        "input_path": str(input_path),
        "input_duration": meta.get("duration"),
        "input_size": meta.get("size"),
        "input_format": meta.get("format"),
        "model_used": model_id,
        "device_used": device_mode,
        "compute_used": compute_mode,
        "language": language or "auto",
        "output_files": {},
        "metadata": {
            "accuracy_mode": accuracy_mode,
            "verbatim_mode": verbatim_mode,
            "enhanced": enhance_audio,
            "vad": vad_filter,
        }
    }
    create_job(job_data)

    def _worker():
        try:
            if job_id in _ACTIVE_CANCELLATIONS:
                return

            def on_progress(p: float, s: str):
                if job_id in _ACTIVE_CANCELLATIONS:
                    raise RuntimeError("Job cancelled")
                broadcast_progress(job_id, p, s, status="processing")

            broadcast_progress(job_id, 0.02, "Starting transcription job...", status="processing")

            res = run_transcription_pipeline(
                input_path=input_path,
                job_id=job_id,
                model_id=model_id,
                language=language,
                device_mode=device_mode,
                compute_mode=compute_mode,
                accuracy_mode=accuracy_mode,
                verbatim_mode=verbatim_mode,
                enhance_audio=enhance_audio,
                vad_filter=vad_filter,
                progress_callback=on_progress,
            )

            # Save transcript to DB
            save_transcript(
                job_id=job_id,
                original_text=res["original_text"],
                clean_text=res["clean_text"],
                srt_content=res["srt_content"],
                vtt_content=res["vtt_content"],
                segments=res["segments"],
            )

            # Mark job complete
            complete_job(job_id, res["output_files"], metadata=res["metadata"])
            broadcast_progress(job_id, 1.0, "Transcription Completed", status="completed")

        except Exception as e:
            if job_id in _ACTIVE_CANCELLATIONS:
                logger.info("Job %s cancelled", job_id)
            else:
                logger.error("Job %s failed: %s", job_id, e, exc_info=True)
                fail_job(job_id, str(e))
                broadcast_progress(job_id, 0.0, f"Error: {e}", status="failed")

    _EXECUTOR.submit(_worker)
    return job_id


def submit_conversion_job(
    input_path: Path,
    input_filename: str,
    target_format: str,
    preset: str = "balanced",
    bitrate: Optional[str] = None,
    sample_rate: Optional[int] = None,
    channels: Optional[int] = None,
) -> str:
    job_id = uuid.uuid4().hex[:10]
    meta = extract_metadata(input_path)

    job_data = {
        "id": job_id,
        "job_type": "conversion",
        "status": "queued",
        "progress": 0.0,
        "stage": "Queued",
        "input_filename": input_filename,
        "input_path": str(input_path),
        "input_duration": meta.get("duration"),
        "input_size": meta.get("size"),
        "input_format": meta.get("format"),
        "output_files": {},
        "metadata": {
            "target_format": target_format,
            "preset": preset,
            "bitrate": bitrate,
            "sample_rate": sample_rate,
            "channels": channels,
        }
    }
    create_job(job_data)

    output_dir = OUTPUTS_DIR / f"conversion_{job_id}"

    def _worker():
        try:
            if job_id in _ACTIVE_CANCELLATIONS:
                return

            def on_progress(p: float, s: str):
                if job_id in _ACTIVE_CANCELLATIONS:
                    raise RuntimeError("Job cancelled")
                broadcast_progress(job_id, p, s, status="processing")

            broadcast_progress(job_id, 0.05, "Starting audio conversion...", status="processing")

            res = convert_audio_file(
                input_path=input_path,
                output_dir=output_dir,
                target_format=target_format,
                preset=preset,
                bitrate=bitrate,
                sample_rate=sample_rate,
                channels=channels,
                progress_callback=on_progress,
            )

            out_files = {
                "converted": res["output_path"],
                "filename": res["output_filename"],
            }
            meta_update = {
                "source_metadata": res["source_metadata"],
                "converted_metadata": res["converted_metadata"],
                "size_change_bytes": res["size_change_bytes"],
                "size_change_percent": res["size_change_percent"],
                "preset": res["preset"],
                "output_filename": res["output_filename"],
            }
            complete_job(job_id, out_files, metadata=meta_update)
            broadcast_progress(job_id, 1.0, "Conversion Completed", status="completed")

        except Exception as e:
            if job_id in _ACTIVE_CANCELLATIONS:
                logger.info("Conversion job %s cancelled", job_id)
            else:
                logger.error("Conversion job %s failed: %s", job_id, e, exc_info=True)
                fail_job(job_id, str(e))
                broadcast_progress(job_id, 0.0, f"Error: {e}", status="failed")

    _EXECUTOR.submit(_worker)
    return job_id
