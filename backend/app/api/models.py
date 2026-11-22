import shutil
import threading
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.core.config import SUPPORTED_MODELS
from app.transcription.engine import (
    is_model_downloaded,
    get_model_folder_size_gb,
    download_model,
    get_model_dir,
)

router = APIRouter(prefix="/api/models", tags=["models"])

# Tracking active model downloads
_DOWNLOADING_MODELS = {}


@router.get("")
def list_models():
    results = []
    for m_id, info in SUPPORTED_MODELS.items():
        downloaded = is_model_downloaded(m_id)
        size_gb = get_model_folder_size_gb(m_id) if downloaded else 0.0
        is_downloading = _DOWNLOADING_MODELS.get(m_id, {}).get("active", False)
        download_progress = _DOWNLOADING_MODELS.get(m_id, {}).get("progress", 0.0)
        status_msg = _DOWNLOADING_MODELS.get(m_id, {}).get("message", "")

        approx_download_gb = info.get("approx_download_gb", 0.0)
        if m_id in ("hybrid-v1", "hybrid-v2", "hybrid-v3"):
            cs_size = SUPPORTED_MODELS.get("codeswitched-medium", {}).get("approx_download_gb", 0.78)
            tb_size = SUPPORTED_MODELS.get("large-v3-turbo", {}).get("approx_download_gb", 1.6)
            approx_download_gb = round(cs_size + tb_size, 2)

        results.append({
            **info,
            "approx_download_gb": approx_download_gb,
            "is_downloaded": downloaded,
            "folder_size_gb": size_gb,
            "is_downloading": is_downloading,
            "download_progress": download_progress,
            "status_message": status_msg,
        })
    return {"models": results}


@router.post("/{model_id}/download")
def start_model_download(model_id: str, background_tasks: BackgroundTasks):
    if model_id not in SUPPORTED_MODELS:
        raise HTTPException(status_code=404, detail="Model not supported")

    if is_model_downloaded(model_id):
        return {"status": "already_downloaded", "message": f"Model {model_id} is already downloaded."}

    if _DOWNLOADING_MODELS.get(model_id, {}).get("active"):
        return {"status": "downloading", "message": f"Model {model_id} is already being downloaded."}

    _DOWNLOADING_MODELS[model_id] = {
        "active": True,
        "progress": 0.05,
        "message": "Initializing download...",
    }

    def _do_download():
        def _cb(p: float, msg: str):
            _DOWNLOADING_MODELS[model_id] = {
                "active": True,
                "progress": p,
                "message": msg,
            }

        try:
            download_model(model_id, progress_callback=_cb)
            _DOWNLOADING_MODELS[model_id] = {
                "active": False,
                "progress": 1.0,
                "message": "Download complete",
            }
        except Exception as e:
            _DOWNLOADING_MODELS[model_id] = {
                "active": False,
                "progress": 0.0,
                "message": f"Error: {e}",
            }

    threading.Thread(target=_do_download, daemon=True).start()
    return {"status": "started", "message": f"Download started for {model_id}"}


@router.delete("/{model_id}")
def delete_model(model_id: str):
    if model_id not in SUPPORTED_MODELS:
        raise HTTPException(status_code=404, detail="Model not supported")

    target_dir = get_model_dir(model_id)
    if not target_dir.exists():
        return {"status": "not_found", "message": "Model directory does not exist"}

    try:
        shutil.rmtree(target_dir)
        return {"status": "deleted", "message": f"Model {model_id} files deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete model files: {e}")
