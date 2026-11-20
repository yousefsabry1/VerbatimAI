import os
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import STORAGE_DIR, SUPPORTED_MODELS
from app.core.database import (
    get_job,
    get_transcript,
    get_alternative_hypotheses,
    get_segment_reviews,
    save_segment_review,
    update_segment_review_status,
)
from app.transcription.verification_service import run_segment_verification
from app.transcription.suspicious_detector import detect_suspicious_segments
from app.audio.segment_extractor import extract_audio_slice

logger = logging.getLogger("verbatim.review_api")
router = APIRouter(prefix="/api/review", tags=["review"])


class VerifySegmentRequest(BaseModel):
    model_id: str = "qwencleo-asr-4bit"
    context_padding: float = 1.0
    device_mode: str = "cuda_only"
    force_recompute: bool = False


class UpdateReviewStatusRequest(BaseModel):
    review_status: str  # "human_reviewed", "review_suggested", "unreviewed", "alternative_available"
    selected_alternative_id: Optional[str] = None
    human_notes: Optional[str] = None
    flag_reasons: Optional[List[str]] = None


@router.post("/{job_id}/segment/{segment_id}/verify")
def verify_segment(job_id: str, segment_id: int, req: VerifySegmentRequest):
    """
    On-demand audio-grounded verification of a specific segment with an alternative ASR model.
    """
    try:
        res = run_segment_verification(
            job_id=job_id,
            segment_id=segment_id,
            model_id=req.model_id,
            context_padding=req.context_padding,
            device_mode=req.device_mode,
            force_recompute=req.force_recompute,
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except FileNotFoundError as fe:
        raise HTTPException(status_code=404, detail=str(fe))
    except Exception as e:
        logger.exception(f"Verification failed for job {job_id} segment #{segment_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {e}")


@router.get("/{job_id}/segment/{segment_id}/alternatives")
def get_segment_alternatives(job_id: str, segment_id: int):
    """
    Returns all alternative hypotheses generated for a specific segment.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    hyps = get_alternative_hypotheses(job_id, segment_id)
    return {
        "job_id": job_id,
        "segment_id": segment_id,
        "count": len(hyps),
        "hypotheses": hyps,
    }


@router.get("/{job_id}/reviews")
def get_job_reviews(job_id: str):
    """
    Returns the comprehensive review state for all segments in a job, including
    review status, flags, alternative count, and suspicious region analysis.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    tr = get_transcript(job_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript data missing")

    segments = tr.get("segments", [])
    reviews_map = get_segment_reviews(job_id)
    all_hyps = get_alternative_hypotheses(job_id)

    # Run suspicious-region detector across segments with speech coverage analysis
    job_input_path = None
    if job.get("input_path") and Path(job["input_path"]).exists():
        job_input_path = Path(job["input_path"])

    diagnostics = detect_suspicious_segments(
        segments=segments,
        alternative_hypotheses=all_hyps,
        reviews_map=reviews_map,
        audio_path=job_input_path,
    )

    # Merge into structured segment review catalog
    review_queue = []
    hyps_by_seg: Dict[int, List[Dict[str, Any]]] = {}
    for h in all_hyps:
        s_id = h["segment_id"]
        if s_id not in hyps_by_seg:
            hyps_by_seg[s_id] = []
        hyps_by_seg[s_id].append(h)

    for idx, s in enumerate(segments):
        s_id = s.get("id", idx)
        diag = diagnostics[idx] if idx < len(diagnostics) else {}
        rev = reviews_map.get(s_id, {})
        alt_list = hyps_by_seg.get(s_id, [])

        status = rev.get("review_status") or ("alternative_available" if alt_list else ("review_suggested" if diag.get("is_flagged") else "unreviewed"))
        flags = list(set(diag.get("flag_reasons", []) + rev.get("flag_reasons", [])))

        review_queue.append({
            "segment_id": s_id,
            "start": s.get("start", 0.0),
            "end": s.get("end", 0.0),
            "text": s.get("text", ""),
            "original_text": s.get("original_text") or s.get("text", ""),
            "review_status": status,
            "is_flagged": diag.get("is_flagged", False) or len(flags) > 0,
            "flag_label": diag.get("flag_label", "Verified"),
            "flag_reasons": flags,
            "severity": diag.get("severity", "none"),
            "alternatives_count": len(alt_list),
            "latest_alternative": alt_list[0] if alt_list else None,
            "human_notes": rev.get("human_notes"),
            "reviewed_at": rev.get("reviewed_at"),
        })

    flagged_count = sum(1 for item in review_queue if item["is_flagged"])
    reviewed_count = sum(1 for item in review_queue if item["review_status"] == "human_reviewed")

    return {
        "job_id": job_id,
        "total_segments": len(segments),
        "flagged_count": flagged_count,
        "reviewed_count": reviewed_count,
        "items": review_queue,
    }


@router.post("/{job_id}/segment/{segment_id}/status")
def update_review_status(job_id: str, segment_id: int, req: UpdateReviewStatusRequest):
    """
    Updates the human review status for a specific transcript segment.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    save_segment_review(
        job_id=job_id,
        segment_id=segment_id,
        review_status=req.review_status,
        flag_reasons=req.flag_reasons,
        selected_alternative_id=req.selected_alternative_id,
        human_notes=req.human_notes,
    )

    return {
        "status": "success",
        "job_id": job_id,
        "segment_id": segment_id,
        "review_status": req.review_status,
        "message": "Review status updated successfully",
    }


@router.get("/{job_id}/segment/{segment_id}/audio")
def stream_segment_audio(job_id: str, segment_id: int, padding: float = Query(1.0, ge=0.0, le=5.0)):
    """
    Streams the exact extracted audio slice for focused listening and comparison in the review UI.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    tr = get_transcript(job_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript data missing")

    segments = tr.get("segments", [])
    target = next((s for s in segments if s.get("id") == segment_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Segment #{segment_id} not found")

    source_path = Path(job["input_path"]).resolve()
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="Source audio file not found on disk")

    slice_path, _, _ = extract_audio_slice(
        source_audio_path=source_path,
        start=float(target["start"]),
        end=float(target["end"]),
        padding=padding,
    )

    return FileResponse(
        str(slice_path),
        media_type="audio/wav",
        filename=slice_path.name,
    )
