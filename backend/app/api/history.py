import shutil
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.core.database import list_jobs, get_job, delete_job, clear_all_jobs
from app.core.config import OUTPUTS_DIR

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
def get_history(limit: int = 50, type: Optional[str] = None):
    return {"jobs": list_jobs(limit=limit, job_type=type)}


@router.get("/{job_id}")
def get_history_item(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/{job_id}")
def delete_history_item(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Clean up disk files
    try:
        # Check job directory
        job_dir = OUTPUTS_DIR / f"job_{job_id}"
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        conv_dir = OUTPUTS_DIR / f"conversion_{job_id}"
        if conv_dir.exists():
            shutil.rmtree(conv_dir, ignore_errors=True)
    except Exception:
        pass

    delete_job(job_id)
    return {"status": "deleted", "message": f"Job {job_id} deleted successfully"}


@router.delete("")
def clear_all_history():
    # Clean up outputs directory
    for item in OUTPUTS_DIR.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            elif item.is_file():
                item.unlink(missing_ok=True)
        except Exception:
            pass

    count = clear_all_jobs()
    return {"status": "cleared", "deleted_count": count}
