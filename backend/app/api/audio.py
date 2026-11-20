import os
import uuid
import mimetypes
import logging
import subprocess
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from app.core.config import UPLOADS_DIR, OUTPUTS_DIR, PREVIEWS_DIR
from app.core.database import get_job
from app.audio.validator import sanitize_filename, validate_upload_file
from app.audio.metadata_extractor import extract_metadata, find_ffmpeg

logger = logging.getLogger("verbatim.audio")
router = APIRouter(prefix="/api/audio", tags=["audio"])


def resolve_file(file_id: str) -> Path:
    """
    Resolves an audio file from job_id, upload file_id prefix, or direct filename.
    """
    # 1. Check if file_id is a job_id in SQLite
    try:
        job = get_job(file_id)
        if job and job.get("input_path"):
            p = Path(job["input_path"])
            if p.is_file():
                return p
    except Exception as e:
        logger.debug(f"Job lookup for audio resolution failed: {e}")

    # 2. Look in uploads directory by file_id prefix
    for p in UPLOADS_DIR.glob(f"{file_id}_*"):
        if p.is_file():
            return p

    # 3. Look directly by filename in uploads
    direct = UPLOADS_DIR / file_id
    if direct.is_file():
        return direct

    # 4. Look in outputs or jobs directories
    for p in OUTPUTS_DIR.rglob(file_id):
        if p.is_file():
            return p

    # 5. Look in previews directory
    prev = PREVIEWS_DIR / file_id
    if prev.is_file():
        return prev

    raise HTTPException(status_code=404, detail=f"Audio file '{file_id}' not found")


def get_or_create_preview(source_path: Path, identifier: str) -> Path:
    """
    Returns a browser-compatible, byte-range seekable MP3 preview of the source audio.
    Caches the preview so conversion happens only once per source file.
    """
    if not source_path.is_file():
        raise HTTPException(status_code=404, detail="Source audio file not found")

    ext = source_path.suffix.lower()
    # Standard MP3 files are already 100% browser-compatible
    if ext == ".mp3":
        return source_path

    # Use source filename stem to identify the cached preview
    preview_name = f"prev_{source_path.stem}.mp3"
    preview_path = PREVIEWS_DIR / preview_name

    # If cached preview exists and is non-empty, reuse it
    if preview_path.is_file() and preview_path.stat().st_size > 1000:
        return preview_path

    # Generate preview via local FFmpeg
    try:
        ffmpeg = find_ffmpeg()
        cmd = [
            ffmpeg, "-y",
            "-i", str(source_path),
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "64k",
            "-ar", "44100",
            str(preview_path),
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        logger.info(f"Generated browser preview at {preview_path}")
        return preview_path
    except Exception as err:
        logger.warning(f"Could not generate MP3 preview for {source_path}: {err}. Serving source directly.")
        return source_path


@router.post("/upload")
async def upload_audio_file(file: UploadFile = File(...)):
    raw_filename = file.filename or "recording.wav"
    clean_name = sanitize_filename(raw_filename)

    file_id = uuid.uuid4().hex[:12]
    stored_name = f"{file_id}_{clean_name}"
    target_path = UPLOADS_DIR / stored_name

    # Save uploaded file
    file_size = 0
    with target_path.open("wb") as buffer:
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            file_size += len(chunk)
            buffer.write(chunk)

    # Validate
    is_valid, err_msg = validate_upload_file(clean_name, file_size)
    if not is_valid:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=err_msg)

    # Extract metadata
    try:
        meta = extract_metadata(target_path)
    except Exception as e:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to read audio file: {e}")

    # Eagerly start preview generation in background or return
    return {
        "file_id": file_id,
        "filename": clean_name,
        "stored_path": str(target_path),
        "metadata": meta,
    }


@router.get("/metadata/{file_id}")
def get_file_metadata(file_id: str):
    path = resolve_file(file_id)
    return extract_metadata(path)


@router.get("/stream/{file_id}")
def stream_audio_file(file_id: str, preview: bool = Query(True, description="Serve browser-compatible MP3 preview")):
    source_path = resolve_file(file_id)

    target_path = source_path
    if preview:
        target_path = get_or_create_preview(source_path, identifier=file_id)

    mime, _ = mimetypes.guess_type(str(target_path))
    if not mime:
        ext = target_path.suffix.lower()
        if ext == ".mp3":
            mime = "audio/mpeg"
        elif ext in (".ogg", ".opus"):
            mime = "audio/ogg"
        elif ext == ".wav":
            mime = "audio/wav"
        elif ext == ".m4a":
            mime = "audio/mp4"
        elif ext == ".flac":
            mime = "audio/flac"
        else:
            mime = "application/octet-stream"

    return FileResponse(
        path=target_path,
        media_type=mime,
        filename=target_path.name,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=86400",
        }
    )


@router.get("/preview/{file_id}")
def get_audio_preview(file_id: str):
    """Explicit endpoint alias for browser playback preview."""
    return stream_audio_file(file_id, preview=True)
