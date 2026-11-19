import re
from pathlib import Path
from typing import Tuple
from app.core.config import SUPPORTED_AUDIO_EXTENSIONS, MAX_UPLOAD_SIZE_BYTES


def sanitize_filename(name: str) -> str:
    """
    Sanitize filename to prevent directory traversal or invalid Windows/Unix characters.
    """
    # Remove directory separators
    name = Path(name).name
    # Replace non-safe chars with underscore
    sanitized = re.sub(r'[^a-zA-Z0-9_\-\. \u0600-\u06FF]', '_', name)
    # Strip leading/trailing dots or spaces
    sanitized = sanitized.strip(". ")
    if not sanitized:
        sanitized = "audio_file"
    return sanitized


def validate_upload_file(filename: str, file_size: int) -> Tuple[bool, str]:
    """
    Validates uploaded file extension and size.
    Returns (is_valid, error_message).
    """
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_AUDIO_EXTENSIONS:
        return False, f"Unsupported file type: '{ext}'. Supported formats: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}"

    if file_size > MAX_UPLOAD_SIZE_BYTES:
        max_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        return False, f"File size exceeds maximum allowed limit of {max_mb} MB"

    return True, ""
