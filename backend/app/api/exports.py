from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, PlainTextResponse
from app.core.database import get_job, get_transcript
from app.exports.formatters import (
    generate_srt,
    generate_vtt,
    generate_timestamped_txt,
    generate_clean_txt,
    generate_json_export,
)

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/{job_id}/{format}")
def export_transcript(
    job_id: str,
    format: str,
    version: str = Query("edited", description="edited, clean, or original")
):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    tr = get_transcript(job_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript not found")

    fmt = format.lower().lstrip(".")
    segments = tr.get("segments", [])
    base_name = Path(job["input_filename"]).stem

    # Build segment collections based on requested version
    is_original_version = (version.lower() == "original")

    if is_original_version:
        # Reconstruct original segments using immutable ASR output
        target_segments = [
            {
                **s,
                "text": s.get("original_text", s["text"]),
            }
            for s in segments
        ]
        label = "original"
    else:
        # Human-corrected / edited segments
        target_segments = segments
        label = "corrected"

    if fmt == "txt":
        if version == "clean":
            content = generate_clean_txt(target_segments)
        elif is_original_version:
            content = tr.get("original_text") or generate_timestamped_txt(target_segments)
        else:
            # Human-corrected timestamped transcript
            content = generate_timestamped_txt(target_segments)

        return PlainTextResponse(
            content=content,
            headers={
                "Content-Disposition": f'attachment; filename="{base_name}_transcript_{label}.txt"',
                "Content-Type": "text/plain; charset=utf-8",
            }
        )

    elif fmt == "srt":
        content = generate_srt(target_segments)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{base_name}_{label}_subtitles.srt"'
            }
        )

    elif fmt == "vtt":
        content = generate_vtt(target_segments)
        return Response(
            content=content,
            media_type="text/vtt; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{base_name}_{label}_subtitles.vtt"'
            }
        )

    elif fmt == "json":
        metadata = dict(job.get("metadata", {}))
        metadata["input_filename"] = job.get("input_filename")
        metadata["duration"] = job.get("input_duration")
        metadata["is_edited"] = bool(tr.get("is_edited", 0))
        metadata["export_version"] = label
        content = generate_json_export(job_id, target_segments, metadata)
        return Response(
            content=content,
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{base_name}_{label}_transcript.json"'
            }
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported export format: {fmt}. Supported: txt, srt, vtt, json")
