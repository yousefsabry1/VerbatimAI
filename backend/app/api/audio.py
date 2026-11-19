import os
import uuid
import mimetypes
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from app.core.config import UPLOADS_DIR, OUTPUTS_DIR
from app.audio.validator import sanitize_filename, validate_upload_file
from app.audio.metadata_extractor import extract_metadata

router = APIRouter(prefix="/api/audio", tags=["audio"])


def resolve_file(file_id: str) -> Path:
    # Look in uploads
    for p in UPLOADS_DIR.glob(f"{file_id}_*"):
        if p.is_file():
            return p
    # Look directly by filename in uploads
    direct = UPLOADS_DIR / file_id
    if direct.is_file():
        return direct

    # Look in outputs or jobs
    for p in OUTPUTS_DIR.rglob(file_id):
        if p.is_file():
            return p

    raise HTTPException(status_code=404, detail="Audio file not found")


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
def stream_audio_file(file_id: str):
    path = resolve_file(file_id)
    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        ext = path.suffix.lower()
        if ext in (".ogg", ".opus"):
            mime = "audio/ogg"
        elif ext == ".mp3":
            mime = "audio/mpeg"
        elif ext == ".wav":
            mime = "audio/wav"
        elif ext == ".m4a":
            mime = "audio/mp4"
        elif ext == ".flac":
            mime = "audio/flac"
        else:
            mime = "application/octet-stream"

    return FileResponse(
        path=path,
        media_type=mime,
        filename=path.name,
        headers={"Accept-Ranges": "bytes"}
    )
