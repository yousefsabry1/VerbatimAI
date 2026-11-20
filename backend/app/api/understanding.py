"""
REST API for Evidence-Grounded Speech Understanding & Actionable Briefs.
"""
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel

from app.core.database import (
    get_job,
    get_transcript,
    save_understanding_brief,
    get_understanding_brief,
    delete_understanding_brief,
)
from app.understanding.instruction_extractor import (
    extract_instructions_from_segments,
    format_brief_as_markdown,
)

router = APIRouter(prefix="/api/understanding", tags=["understanding"])


class GenerateBriefRequest(BaseModel):
    prefer_human_corrected: bool = True
    custom_title: Optional[str] = None


@router.post("/{job_id}/generate")
def generate_job_understanding_brief(job_id: str, req: GenerateBriefRequest):
    """
    Extracts an evidence-grounded action brief from the transcript segments.
    Strictly preserves traceability to audio timestamps.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    tr = get_transcript(job_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript data not found")

    segments = tr.get("segments", [])
    if not segments:
        raise HTTPException(status_code=400, detail="Transcript has no segments to analyze")

    brief_data = extract_instructions_from_segments(
        job_id=job_id,
        segments=segments,
        job_title=req.custom_title or f"موجز التوجيهات المنطوقة — {job.get('input_filename', 'Recording')}",
    )

    save_understanding_brief(
        job_id=job_id,
        title=brief_data["title"],
        topic_overview=brief_data["topic_overview"],
        brief_data=brief_data,
    )

    return {
        "status": "success",
        "job_id": job_id,
        "brief": brief_data,
    }


@router.get("/{job_id}")
def get_job_understanding_brief(job_id: str):
    """
    Retrieves the persisted understanding brief for a job.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    rec = get_understanding_brief(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="No understanding brief generated for this job yet")

    return {
        "status": "success",
        "job_id": job_id,
        "title": rec["title"],
        "topic_overview": rec["topic_overview"],
        "brief": rec["brief"],
        "created_at": rec["created_at"],
        "updated_at": rec["updated_at"],
    }


@router.get("/{job_id}/export/markdown")
def export_understanding_brief_markdown(job_id: str):
    """
    Exports the actionable brief as a formatted Markdown report.
    """
    rec = get_understanding_brief(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Understanding brief not found")

    md_content = format_brief_as_markdown(rec["brief"])
    filename = f"understanding_brief_{job_id}.md"

    return PlainTextResponse(
        content=md_content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/export/json")
def export_understanding_brief_json(job_id: str):
    """
    Exports the actionable brief as structured JSON data.
    """
    rec = get_understanding_brief(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Understanding brief not found")

    filename = f"understanding_brief_{job_id}.json"
    return JSONResponse(
        content=rec["brief"],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
