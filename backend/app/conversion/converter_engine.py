import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from app.audio.metadata_extractor import find_ffmpeg, extract_metadata
from app.core.config import OUTPUTS_DIR

logger = logging.getLogger(__name__)

# Codec mappings for each container format
FORMAT_CODEC_MAP = {
    "mp3": ("libmp3lame", "mp3"),
    "wav": ("pcm_s16le", "wav"),
    "ogg": ("libvorbis", "ogg"),
    "opus": ("libopus", "opus"),
    "m4a": ("aac", "ipod"),
    "aac": ("aac", "adts"),
    "flac": ("flac", "flac"),
    "aiff": ("pcm_s16be", "aiff"),
    "webm": ("libopus", "webm"),
}


def build_ffmpeg_args(
    input_path: Path,
    output_path: Path,
    target_format: str,
    preset: str = "balanced",
    bitrate: Optional[str] = None,
    sample_rate: Optional[int] = None,
    channels: Optional[int] = None,
) -> list[str]:
    ffmpeg = find_ffmpeg()
    target_format = target_format.lower().lstrip(".")
    if target_format not in FORMAT_CODEC_MAP:
        raise ValueError(f"Unsupported target format: {target_format}")

    codec, container_fmt = FORMAT_CODEC_MAP[target_format]

    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-vn",  # strip video if present
    ]

    # Handle preset vs custom settings
    if preset == "custom":
        if codec != "copy":
            cmd.extend(["-c:a", codec])
        if bitrate and target_format not in ("wav", "flac", "aiff"):
            cmd.extend(["-b:a", bitrate])
        if sample_rate:
            cmd.extend(["-ar", str(sample_rate)])
        if channels:
            cmd.extend(["-ac", str(channels)])
    elif preset == "smaller":
        if target_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100"])
        elif target_format == "opus":
            cmd.extend(["-c:a", "libopus", "-b:a", "64k", "-ar", "48000"])
        elif target_format in ("m4a", "aac"):
            cmd.extend(["-c:a", "aac", "-b:a", "128k", "-ar", "44100"])
        elif target_format == "ogg":
            cmd.extend(["-c:a", "libvorbis", "-q:a", "3", "-ar", "44100"])
        elif target_format == "wav":
            cmd.extend(["-c:a", "pcm_s16le", "-ar", "22050", "-ac", "1"])
        elif target_format == "flac":
            cmd.extend(["-c:a", "flac", "-compression_level", "8"])
        elif target_format == "webm":
            cmd.extend(["-c:a", "libopus", "-b:a", "64k", "-ar", "48000"])
        else:
            cmd.extend(["-c:a", codec])
    elif preset == "high":
        if target_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k", "-ar", "48000"])
        elif target_format == "opus":
            cmd.extend(["-c:a", "libopus", "-b:a", "160k", "-ar", "48000"])
        elif target_format in ("m4a", "aac"):
            cmd.extend(["-c:a", "aac", "-b:a", "320k", "-ar", "48000"])
        elif target_format == "ogg":
            cmd.extend(["-c:a", "libvorbis", "-q:a", "8", "-ar", "48000"])
        elif target_format == "wav":
            cmd.extend(["-c:a", "pcm_s24le", "-ar", "48000"])
        elif target_format == "flac":
            cmd.extend(["-c:a", "flac", "-compression_level", "0", "-ar", "48000"])
        elif target_format == "webm":
            cmd.extend(["-c:a", "libopus", "-b:a", "160k", "-ar", "48000"])
        else:
            cmd.extend(["-c:a", codec])
    else:  # balanced (default)
        if target_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100"])
        elif target_format == "opus":
            cmd.extend(["-c:a", "libopus", "-b:a", "96k", "-ar", "48000"])
        elif target_format in ("m4a", "aac"):
            cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ar", "44100"])
        elif target_format == "ogg":
            cmd.extend(["-c:a", "libvorbis", "-q:a", "5", "-ar", "44100"])
        elif target_format == "wav":
            cmd.extend(["-c:a", "pcm_s16le", "-ar", "44100"])
        elif target_format == "flac":
            cmd.extend(["-c:a", "flac", "-compression_level", "5"])
        elif target_format == "webm":
            cmd.extend(["-c:a", "libopus", "-b:a", "96k", "-ar", "48000"])
        else:
            cmd.extend(["-c:a", codec])

    # Format-specific container flags
    if container_fmt:
        cmd.extend(["-f", container_fmt])

    cmd.append(str(output_path))
    return cmd


def convert_audio_file(
    input_path: Path,
    output_dir: Path,
    target_format: str,
    preset: str = "balanced",
    bitrate: Optional[str] = None,
    sample_rate: Optional[int] = None,
    channels: Optional[int] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    Executes genuine FFmpeg conversion, verifies output, and returns conversion statistics.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    target_format = target_format.lower().lstrip(".")
    output_filename = f"{input_path.stem}.{target_format}"
    output_path = output_dir / output_filename

    # Avoid overwriting input directly if in same folder
    if output_path.resolve() == input_path.resolve():
        output_filename = f"{input_path.stem}_converted.{target_format}"
        output_path = output_dir / output_filename

    if progress_callback:
        progress_callback(0.1, "Inspecting original audio...")

    source_meta = extract_metadata(input_path)
    if not source_meta.get("is_valid_audio"):
        raise ValueError(f"Input file contains no valid audio streams: {source_meta.get('error')}")

    if progress_callback:
        progress_callback(0.3, f"Converting audio to {target_format.upper()}...")

    cmd = build_ffmpeg_args(
        input_path=input_path,
        output_path=output_path,
        target_format=target_format,
        preset=preset,
        bitrate=bitrate,
        sample_rate=sample_rate,
        channels=channels,
    )

    logger.info("Executing conversion: %s", " ".join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")

    if proc.returncode != 0:
        logger.error("FFmpeg error: %s", proc.stderr)
        raise RuntimeError(f"FFmpeg conversion failed: {proc.stderr[-500:]}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Conversion failed: Output file was not created or is 0 bytes.")

    if progress_callback:
        progress_callback(0.85, "Verifying converted audio stream...")

    converted_meta = extract_metadata(output_path)
    if not converted_meta.get("is_valid_audio"):
        raise RuntimeError("Converted file failed audio integrity validation.")

    # Calculate size comparison
    orig_size = source_meta["size"]
    new_size = converted_meta["size"]
    size_diff = orig_size - new_size
    diff_pct = (size_diff / orig_size) * 100 if orig_size > 0 else 0

    if progress_callback:
        progress_callback(1.0, "Conversion completed successfully")

    return {
        "output_path": str(output_path),
        "output_filename": output_filename,
        "source_metadata": source_meta,
        "converted_metadata": converted_meta,
        "size_change_bytes": size_diff,
        "size_change_percent": round(diff_pct, 1),
        "preset": preset,
    }
