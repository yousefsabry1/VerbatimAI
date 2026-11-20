import os
import subprocess
import logging
from pathlib import Path
from typing import Tuple, Optional

from app.audio.metadata_extractor import find_ffmpeg, extract_metadata
from app.core.config import STORAGE_DIR

logger = logging.getLogger("verbatim.segment_extractor")

TEMP_SLICES_DIR = STORAGE_DIR / "temp" / "slices"
TEMP_SLICES_DIR.mkdir(parents=True, exist_ok=True)


def extract_audio_slice(
    source_audio_path: Path,
    start: float,
    end: float,
    padding: float = 1.0,
    output_filename: Optional[str] = None,
) -> Tuple[Path, float, float]:
    """
    Extracts an audio slice with clamped context padding.
    - Clamps start >= 0.0.
    - Clamps end <= total_duration.
    - Exports 16kHz mono PCM WAV.
    Returns: (output_wav_path, clamped_start, clamped_end)
    """
    source_audio_path = Path(source_audio_path).resolve()
    if not source_audio_path.is_file():
        raise FileNotFoundError(f"Source audio file not found at {source_audio_path}")

    # Inspect total duration
    meta = extract_metadata(source_audio_path)
    total_duration = float(meta.get("duration", 0.0))
    if total_duration <= 0.0:
        total_duration = max(end + padding + 1.0, 3600.0)

    # Validate segment bounds
    seg_start = max(0.0, float(start))
    seg_end = min(total_duration, float(end))
    if seg_end <= seg_start:
        seg_end = min(total_duration, seg_start + 1.0)

    # Apply padding and clamp
    clamped_start = max(0.0, seg_start - float(padding))
    clamped_end = min(total_duration, seg_end + float(padding))
    slice_duration = max(0.2, clamped_end - clamped_start)

    ffmpeg = find_ffmpeg()
    if not output_filename:
        safe_stem = source_audio_path.stem[:12]
        output_filename = f"slice_{safe_stem}_{int(clamped_start*100)}_{int(clamped_end*100)}.wav"

    output_path = TEMP_SLICES_DIR / output_filename

    cmd = [
        ffmpeg, "-y",
        "-ss", f"{clamped_start:.3f}",
        "-t", f"{slice_duration:.3f}",
        "-i", str(source_audio_path),
        "-vn", "-ac", "1", "-ar", "16000",
        str(output_path),
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as err:
        err_msg = err.stderr.decode("utf-8", errors="replace")
        logger.error(f"FFmpeg slice extraction failed: {err_msg}")
        raise RuntimeError(f"Audio slice extraction failed: {err_msg}")

    return output_path, clamped_start, clamped_end
