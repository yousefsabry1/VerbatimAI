import os
import zipfile
import io
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.core.database import get_job
from app.services.job_manager import submit_conversion_job
from app.api.audio import resolve_file
from app.core.config import SUPPORTED_OUTPUT_FORMATS

router = APIRouter(prefix="/api/conversion", tags=["conversion"])


class ConversionRequest(BaseModel):
    file_id: str
    target_format: str
    preset: str = "balanced"  # smaller, balanced, high, custom
    bitrate: Optional[str] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None


class BatchConversionRequest(BaseModel):
    items: List[ConversionRequest]


class ZipDownloadRequest(BaseModel):
    job_ids: List[str]


@router.get("/formats")
def get_supported_formats():
    return {
        "formats": SUPPORTED_OUTPUT_FORMATS,
        "presets": [
            {"id": "smaller", "name": "Smaller File", "description": "Highly compressed, smaller file size"},
            {"id": "balanced", "name": "Balanced (Recommended)", "description": "Standard high quality, balanced size"},
            {"id": "high", "name": "High Quality", "description": "Maximum bitrate / lossless compression"},
            {"id": "custom", "name": "Custom Settings", "description": "Manual bitrate, sample rate, and channels"},
        ]
    }


@router.post("/submit")
def submit_single_conversion(req: ConversionRequest):
    fmt = req.target_format.lower().lstrip(".")
    if fmt not in SUPPORTED_OUTPUT_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported target format: {fmt}")

    input_path = resolve_file(req.file_id)

    job_id = submit_conversion_job(
        input_path=input_path,
        input_filename=input_path.name,
        target_format=fmt,
        preset=req.preset,
        bitrate=req.bitrate,
        sample_rate=req.sample_rate,
        channels=req.channels,
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "message": f"Conversion to {fmt.upper()} queued successfully",
    }


@router.post("/batch")
def submit_batch_conversion(batch: BatchConversionRequest):
    if not batch.items:
        raise HTTPException(status_code=400, detail="Batch list is empty")

    job_ids = []
    for req in batch.items:
        fmt = req.target_format.lower().lstrip(".")
        if fmt not in SUPPORTED_OUTPUT_FORMATS:
            continue
        try:
            input_path = resolve_file(req.file_id)
            jid = submit_conversion_job(
                input_path=input_path,
                input_filename=input_path.name,
                target_format=fmt,
                preset=req.preset,
                bitrate=req.bitrate,
                sample_rate=req.sample_rate,
                channels=req.channels,
            )
            job_ids.append(jid)
        except Exception:
            pass

    return {
        "submitted_count": len(job_ids),
        "job_ids": job_ids,
    }


@router.get("/{job_id}/download")
def download_converted_file(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job has not completed yet")

    out_files = job.get("output_files", {})
    converted_path = out_files.get("converted")
    if not converted_path or not Path(converted_path).exists():
        raise HTTPException(status_code=404, detail="Converted file not found on disk")

    filename = out_files.get("filename", Path(converted_path).name)

    return FileResponse(
        path=converted_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@router.post("/download-zip")
def download_converted_zip(req: ZipDownloadRequest):
    if not req.job_ids:
        raise HTTPException(status_code=400, detail="No job IDs specified")

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        added = 0
        for jid in req.job_ids:
            job = get_job(jid)
            if not job or job.get("status") != "completed":
                continue
            out_files = job.get("output_files", {})
            p = out_files.get("converted")
            if p and Path(p).exists():
                arcname = out_files.get("filename", Path(p).name)
                zf.write(p, arcname=arcname)
                added += 1

    if added == 0:
        raise HTTPException(status_code=404, detail="None of the specified jobs contain completed files")

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=verbatim_converted_audio.zip"}
    )
