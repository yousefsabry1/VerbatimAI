import json
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.database import get_job, get_transcript, update_transcript_content
from app.services.job_manager import (
    submit_transcription_job,
    cancel_job,
    register_subscriber,
    unregister_subscriber,
)
from app.api.audio import resolve_file
from app.exports.formatters import generate_srt, generate_vtt

router = APIRouter(prefix="/api/transcription", tags=["transcription"])


class TranscriptionRequest(BaseModel):
    file_id: str
    model_id: str = "medium"
    language: Optional[str] = None
    device_mode: str = "auto"
    compute_mode: str = "auto"
    accuracy_mode: str = "balanced"  # "balanced" or "maximum"
    verbatim_mode: str = "strict"    # "strict" or "clean"
    enhance_audio: bool = False
    vad_filter: bool = True


class TranscriptUpdateRequest(BaseModel):
    clean_text: str
    segments: List[Dict[str, Any]]


@router.post("/submit")
def submit_job(req: TranscriptionRequest):
    input_path = resolve_file(req.file_id)

    job_id = submit_transcription_job(
        input_path=input_path,
        input_filename=input_path.name,
        model_id=req.model_id,
        language=req.language,
        device_mode=req.device_mode,
        compute_mode=req.compute_mode,
        accuracy_mode=req.accuracy_mode,
        verbatim_mode=req.verbatim_mode,
        enhance_audio=req.enhance_audio,
        vad_filter=req.vad_filter,
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Transcription job submitted successfully",
    }


@router.get("/{job_id}")
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/stream")
async def stream_job_progress(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    q = register_subscriber(job_id)

    async def event_generator():
        # First send current state
        initial_payload = {
            "job_id": job_id,
            "progress": job.get("progress", 0.0),
            "stage": job.get("stage", ""),
            "status": job.get("status", "processing"),
        }
        yield f"data: {json.dumps(initial_payload)}\n\n"

        if job.get("status") in ("completed", "failed", "cancelled"):
            return

        try:
            while True:
                msg = await q.get()
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("status") in ("completed", "failed", "cancelled"):
                    break
        finally:
            unregister_subscriber(job_id, q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{job_id}/result")
def get_job_result(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        return {
            "status": job["status"],
            "progress": job["progress"],
            "stage": job["stage"],
            "error_message": job.get("error_message"),
            "is_complete": False,
        }

    tr = get_transcript(job_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript data missing")

    return {
        "job_id": job_id,
        "is_complete": True,
        "job": job,
        "original_text": tr["original_text"],
        "clean_text": tr["clean_text"],
        "srt_content": tr["srt_content"],
        "vtt_content": tr["vtt_content"],
        "segments": tr["segments"],
        "is_edited": bool(tr.get("is_edited", 0)),
        "updated_at": tr.get("updated_at"),
    }


@router.put("/{job_id}/segments")
def update_transcript_segments(job_id: str, payload: TranscriptUpdateRequest):
    tr = get_transcript(job_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # Re-generate subtitles from updated segments
    new_srt = generate_srt(payload.segments)
    new_vtt = generate_vtt(payload.segments)

    update_transcript_content(
        job_id=job_id,
        clean_text=payload.clean_text,
        segments=payload.segments,
        srt_content=new_srt,
        vtt_content=new_vtt,
    )

    return {
        "status": "updated",
        "message": "Transcript edits saved successfully",
    }


@router.post("/{job_id}/cancel")
def cancel_running_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    cancel_job(job_id)
    return {"status": "cancelled", "message": "Job cancellation requested"}
