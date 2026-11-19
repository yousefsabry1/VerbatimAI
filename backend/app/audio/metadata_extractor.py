import json
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def find_ffprobe() -> str:
    path = shutil.which("ffprobe")
    if path:
        return path
    # Check default common Windows paths or imageio_ffmpeg
    try:
        import imageio_ffmpeg
        ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        ffprobe_exe = ffmpeg_exe.parent / "ffprobe.exe"
        if ffprobe_exe.exists():
            return str(ffprobe_exe)
    except Exception:
        pass
    raise RuntimeError("ffprobe was not found on system PATH. Please ensure FFmpeg is installed.")


def find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise RuntimeError("ffmpeg was not found on system PATH. Please ensure FFmpeg is installed.")


def extract_metadata(file_path: Path) -> Dict[str, Any]:
    """
    Extract technical audio/video metadata using ffprobe.
    Returns:
        dict with keys: format, codec, duration, sample_rate, channels, bitrate, size, is_valid_audio
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ffprobe = find_ffprobe()
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(file_path)
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            raise RuntimeError(f"FFprobe failed to inspect file: {res.stderr.strip()}")

        data = json.loads(res.stdout)
    except Exception as e:
        logger.error("Error inspecting audio file %s: %s", file_path, e)
        raise RuntimeError(f"Could not read media file metadata: {e}")

    fmt = data.get("format", {})
    streams = data.get("streams", [])

    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)

    if not audio_stream:
        return {
            "is_valid_audio": False,
            "error": "No audio stream found in media file",
            "format": fmt.get("format_name", "unknown"),
            "size": file_path.stat().st_size,
            "has_video": video_stream is not None,
        }

    duration = float(fmt.get("duration") or audio_stream.get("duration") or 0.0)
    sample_rate = int(audio_stream.get("sample_rate") or 0)
    channels = int(audio_stream.get("channels") or 1)
    bitrate = int(fmt.get("bit_rate") or audio_stream.get("bit_rate") or 0)
    codec = audio_stream.get("codec_name", "unknown")
    container = fmt.get("format_name", file_path.suffix.lstrip("."))

    return {
        "is_valid_audio": True,
        "format": container,
        "codec": codec,
        "duration": round(duration, 3),
        "duration_formatted": format_seconds(duration),
        "sample_rate": sample_rate,
        "channels": channels,
        "channel_layout": "Stereo" if channels == 2 else ("Mono" if channels == 1 else f"{channels}ch"),
        "bitrate": bitrate,
        "bitrate_kbps": round(bitrate / 1000) if bitrate > 0 else None,
        "size": file_path.stat().st_size,
        "size_formatted": format_size(file_path.stat().st_size),
        "has_video": video_stream is not None,
    }


def format_seconds(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
