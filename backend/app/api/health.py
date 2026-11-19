import shutil
import subprocess
from fastapi import APIRouter
from app.audio.metadata_extractor import find_ffmpeg, find_ffprobe

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def get_health():
    return {
        "status": "ok",
        "app": "Verbatim AI",
        "version": "1.0.0",
        "tagline": "Every Word Matters.",
    }


@router.get("/system")
def get_system():
    ffmpeg_ok = False
    ffmpeg_ver = "Not found"
    ffprobe_ok = False
    ffprobe_ver = "Not found"

    try:
        ffmpeg_bin = find_ffmpeg()
        proc = subprocess.run([ffmpeg_bin, "-version"], stdout=subprocess.PIPE, text=True, errors="replace")
        if proc.returncode == 0:
            ffmpeg_ok = True
            ffmpeg_ver = proc.stdout.split("\n")[0]
    except Exception as e:
        ffmpeg_ver = str(e)

    try:
        ffprobe_bin = find_ffprobe()
        proc = subprocess.run([ffprobe_bin, "-version"], stdout=subprocess.PIPE, text=True, errors="replace")
        if proc.returncode == 0:
            ffprobe_ok = True
            ffprobe_ver = proc.stdout.split("\n")[0]
    except Exception as e:
        ffprobe_ver = str(e)

    return {
        "ffmpeg": {
            "available": ffmpeg_ok,
            "version": ffmpeg_ver,
        },
        "ffprobe": {
            "available": ffprobe_ok,
            "version": ffprobe_ver,
        }
    }
