import os
import shutil
import subprocess
import multiprocessing
from fastapi import APIRouter

from app.core.cuda_init import register_nvidia_dll_directories
register_nvidia_dll_directories()

router = APIRouter(prefix="/api/hardware", tags=["hardware"])


@router.get("")
def get_hardware_info():
    cpu_count = multiprocessing.cpu_count()
    cuda_available = False
    cuda_devices = 0
    gpu_name = None
    vram_total_mb = None
    vram_used_mb = None
    driver_version = None

    # Check ctranslate2 CUDA device count
    try:
        import ctranslate2
        cuda_devices = ctranslate2.get_cuda_device_count()
        cuda_available = cuda_devices > 0
    except Exception:
        cuda_available = False

    # Check nvidia-smi for GPU details
    if shutil.which("nvidia-smi"):
        try:
            cmd = ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,driver_version", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, errors="replace")
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split("\n")[0].split(",")]
                if len(parts) >= 4:
                    gpu_name = parts[0]
                    vram_total_mb = int(parts[1])
                    vram_used_mb = int(parts[2])
                    driver_version = parts[3]
        except Exception:
            pass

    force_cpu = os.environ.get("VERBATIM_FORCE_CPU") == "1"

    # Recommendation logic
    if force_cpu:
        cuda_available = False
        cuda_devices = 0
        recommended_model = "small"
        recommended_device = "cpu"
        recommended_compute = "int8"
    elif cuda_available and vram_total_mb:
        if vram_total_mb >= 7500:
            recommended_model = "large-v3"
            recommended_device = "cuda"
            recommended_compute = "float16"
        elif vram_total_mb >= 3500:
            recommended_model = "medium"
            recommended_device = "cuda"
            recommended_compute = "int8_float16"
        else:
            recommended_model = "small"
            recommended_device = "cuda"
            recommended_compute = "int8_float16"
    else:
        recommended_model = "small"
        recommended_device = "cpu"
        recommended_compute = "int8"

    return {
        "force_cpu": force_cpu,
        "cuda_available": cuda_available,
        "cuda_device_count": cuda_devices,
        "gpu_name": gpu_name or ("NVIDIA GPU" if cuda_available else "Not detected / CPU only"),
        "vram_total_mb": vram_total_mb,
        "vram_used_mb": vram_used_mb,
        "vram_free_mb": (vram_total_mb - vram_used_mb) if (vram_total_mb and vram_used_mb is not None) else None,
        "driver_version": driver_version,
        "cpu_cores": cpu_count,
        "recommended": {
            "model": recommended_model,
            "device": recommended_device,
            "compute": recommended_compute,
        }
    }
