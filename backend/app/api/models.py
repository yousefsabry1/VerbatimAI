import shutil
import threading
from pathlib import Path
from typing import Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.core.config import SUPPORTED_MODELS, MODELS_DIR
from app.transcription.engine import (
    is_model_downloaded,
    get_model_folder_size_gb,
    download_model,
    get_model_dir,
)

router = APIRouter(prefix="/api/models", tags=["models"])

# Tracking active model downloads
_DOWNLOADING_MODELS: Dict[str, Dict[str, Any]] = {}


class QwenCleoSetupRequest(BaseModel):
    confirm_download: bool = False


def get_gpu_hardware_info() -> Dict[str, Any]:
    """
    Detects NVIDIA GPU presence, model name, and total VRAM in MB.
    Uses nvidia-smi first, then falls back to torch or ctranslate2.
    """
    import subprocess
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = res.stdout.strip().split("\n")[0].split(",")
            return {
                "has_cuda": True,
                "gpu_name": parts[0].strip(),
                "vram_mb": float(parts[1].strip()),
            }
    except Exception:
        pass

    try:
        import torch
        if torch.cuda.is_available():
            return {
                "has_cuda": True,
                "gpu_name": torch.cuda.get_device_name(0),
                "vram_mb": round(torch.cuda.get_device_properties(0).total_memory / (1024 * 1024), 1),
            }
    except Exception:
        pass

    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return {
                "has_cuda": True,
                "gpu_name": "NVIDIA CUDA Device",
                "vram_mb": 4096.0,
            }
    except Exception:
        pass

    return {
        "has_cuda": False,
        "gpu_name": None,
        "vram_mb": 0.0,
    }


def check_qwencleo_readiness(verify_runtime: bool = False) -> Dict[str, Any]:
    """
    Evaluates runtime and hardware readiness of QwenCleo 4-bit arbiter.
    Verifies isolated experimental_venv, quantized model weights, and NVIDIA CUDA GPU.
    Optionally performs active runtime import check in experimental_venv.
    """
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    exp_py = project_root / "experimental_venv" / "Scripts" / "python.exe"
    env_ready = exp_py.exists()

    model_dir = MODELS_DIR / "qwencleo-asr"
    model_ready = (model_dir / "model.safetensors").exists() and (model_dir / "config.json").exists()

    gpu_info = get_gpu_hardware_info()
    has_cuda = gpu_info["has_cuda"]
    vram_mb = gpu_info["vram_mb"]
    gpu_name = gpu_info["gpu_name"]

    gpu_supported = has_cuda and (vram_mb >= 3500)
    ready = env_ready and model_ready and gpu_supported

    runtime_verified = False
    runtime_error_msg = None

    if ready and verify_runtime:
        import subprocess
        try:
            cmd = [
                str(exp_py),
                "-c",
                "import sys, torch; from transformers import BitsAndBytesConfig; import qwen_asr; print('VERIFY_QWEN_OK')",
            ]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if p.returncode == 0 and "VERIFY_QWEN_OK" in p.stdout:
                runtime_verified = True
            else:
                ready = False
                err_detail = (p.stderr.strip() or p.stdout.strip())[:250]
                runtime_error_msg = err_detail
        except Exception as e:
            ready = False
            runtime_error_msg = str(e)[:250]

    if ready:
        status = "ready"
        reason = f"QwenCleo 4-bit arbiter is fully configured on {gpu_name} ({vram_mb} MB VRAM)."
    elif not gpu_supported:
        status = "gpu_unsupported"
        reason = f"Requires an NVIDIA GPU with >= 4GB VRAM. (Detected: {gpu_name or 'None'}, VRAM: {vram_mb} MB). 4-bit NF4 quantization cannot execute on CPU."
    elif not env_ready:
        status = "env_missing"
        reason = f"Isolated experimental_venv not found at {exp_py}. Run scripts/setup_qwencleo.bat to install."
    elif not model_ready:
        status = "model_missing"
        reason = f"Model weights not found at {model_dir}. Run scripts/setup_qwencleo.bat to download (~3.8 GB)."
    elif runtime_error_msg:
        status = "runtime_error"
        reason = f"QwenCleo runtime dependency check failed in experimental_venv: {runtime_error_msg}"
    else:
        status = "unconfigured"
        reason = "QwenCleo optional components not fully configured."

    return {
        "ready": ready,
        "environment_ready": env_ready,
        "model_downloaded": model_ready,
        "gpu_supported": gpu_supported,
        "gpu_name": gpu_name,
        "vram_mb": vram_mb,
        "status": status,
        "reason": reason,
        "runtime_verified": runtime_verified,
        "disk_requirement_gb": 6.5,
        "vram_requirement_mb": 4096,
    }


@router.get("")
def list_models():
    results = []
    qwen_info = check_qwencleo_readiness()

    for m_id, info in SUPPORTED_MODELS.items():
        downloaded = is_model_downloaded(m_id)
        size_gb = get_model_folder_size_gb(m_id) if downloaded else 0.0
        is_downloading = _DOWNLOADING_MODELS.get(m_id, {}).get("active", False)
        download_progress = _DOWNLOADING_MODELS.get(m_id, {}).get("progress", 0.0)
        status_msg = _DOWNLOADING_MODELS.get(m_id, {}).get("message", "")

        approx_download_gb = info.get("approx_download_gb", 0.0)
        item = {
            **info,
            "approx_download_gb": approx_download_gb,
            "is_downloaded": downloaded,
            "folder_size_gb": size_gb,
            "is_downloading": is_downloading,
            "download_progress": download_progress,
            "status_message": status_msg,
        }

        if m_id in ("hybrid-v1", "hybrid-v2", "hybrid-v3"):
            cs_size = SUPPORTED_MODELS.get("codeswitched-medium", {}).get("approx_download_gb", 0.78)
            tb_size = SUPPORTED_MODELS.get("large-v3-turbo", {}).get("approx_download_gb", 1.6)
            item["approx_download_gb"] = round(cs_size + tb_size, 2)

            twin_ready = is_model_downloaded("codeswitched-medium") and is_model_downloaded("large-v3-turbo")
            if not twin_ready:
                tier = "needs_download"
                tier_label = "Requires Twin Whisper Models"
            elif qwen_info["ready"]:
                tier = "full_tri_model"
                tier_label = "Full Tri-Model Consensus (Twin Models + QwenCleo 4-bit Arbiter)"
            else:
                tier = "dual_model_consensus"
                tier_label = "Dual-Model Consensus (Twin Models Baseline)"

            item["hybrid_readiness"] = {
                "tier": tier,
                "tier_label": tier_label,
                "twin_models_ready": twin_ready,
                "qwencleo_ready": qwen_info["ready"],
                "qwencleo_details": qwen_info,
            }

        if m_id == "qwencleo-asr-4bit":
            item["qwencleo_readiness"] = qwen_info

        results.append(item)
    return {"models": results}


@router.get("/qwencleo/status")
def get_qwencleo_status():
    """Returns real-time readiness and diagnostic metrics for QwenCleo 4-bit arbiter."""
    return check_qwencleo_readiness()


@router.post("/qwencleo-asr-4bit/setup")
def setup_qwencleo(req: QwenCleoSetupRequest):
    """
    Safe, managed, on-demand setup for QwenCleo 4-bit arbiter.
    Requires explicit user consent due to ~6.5 GB disk space and ~3.8 GB download size.
    Validates hardware support (NVIDIA GPU with >= 4GB VRAM) before execution.
    """
    if not req.confirm_download:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "QwenCleo setup requires explicit user confirmation. "
                    "This model requires ~6.5 GB disk space (~3.8 GB download) and an NVIDIA GPU with at least 4 GB VRAM. "
                    "Set confirm_download: true to proceed."
                ),
                "requirements": {
                    "disk_gb": 6.5,
                    "download_gb": 3.8,
                    "vram_gb": 4.0,
                    "gpu_required": True,
                }
            }
        )

    readiness = check_qwencleo_readiness()
    if not readiness["gpu_supported"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot setup QwenCleo: Hardware incompatible. {readiness['reason']}"
        )

    if _DOWNLOADING_MODELS.get("qwencleo-asr-4bit", {}).get("active"):
        return {"status": "downloading", "message": "QwenCleo setup is already in progress."}

    _DOWNLOADING_MODELS["qwencleo-asr-4bit"] = {
        "active": True,
        "progress": 0.05,
        "message": "Initializing QwenCleo setup...",
    }

    def _do_setup():
        try:
            _DOWNLOADING_MODELS["qwencleo-asr-4bit"] = {
                "active": True,
                "progress": 0.10,
                "message": "Configuring isolated experimental_venv...",
            }
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            exp_venv = project_root / "experimental_venv"
            exp_py = exp_venv / "Scripts" / "python.exe"

            import sys
            import subprocess
            if not exp_py.exists():
                subprocess.run([sys.executable, "-m", "venv", str(exp_venv)], check=True)

            _DOWNLOADING_MODELS["qwencleo-asr-4bit"] = {
                "active": True,
                "progress": 0.30,
                "message": "Installing experimental dependencies (torch, transformers, qwen-asr)...",
            }
            req_file = project_root / "requirements-experimental.txt"
            if req_file.exists():
                subprocess.run(
                    [str(exp_py), "-m", "pip", "install", "-r", str(req_file)],
                    check=True,
                    timeout=900,
                )

            _DOWNLOADING_MODELS["qwencleo-asr-4bit"] = {
                "active": True,
                "progress": 0.60,
                "message": "Downloading QwenCleo 4-bit weights (~3.8 GB)...",
            }
            target_dir = MODELS_DIR / "qwencleo-asr"
            target_dir.mkdir(parents=True, exist_ok=True)
            from huggingface_hub import snapshot_download
            snapshot_download(
                repo_id="mohammedaly22/QwenCleo-ASR",
                local_dir=str(target_dir),
                local_dir_use_symlinks=False,
                resume_download=True,
            )

            _DOWNLOADING_MODELS["qwencleo-asr-4bit"] = {
                "active": False,
                "progress": 1.0,
                "message": "QwenCleo setup complete. Full Tri-Model Consensus is active.",
            }
        except Exception as e:
            _DOWNLOADING_MODELS["qwencleo-asr-4bit"] = {
                "active": False,
                "progress": 0.0,
                "message": f"Setup failed: {e}",
            }

    threading.Thread(target=_do_setup, daemon=True).start()
    return {"status": "started", "message": "QwenCleo managed setup started in background."}


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
