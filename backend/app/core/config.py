import os
import shutil
import sys
from pathlib import Path

# Application Root Paths
APP_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
STORAGE_DIR = BACKEND_DIR / "storage"

UPLOADS_DIR = STORAGE_DIR / "uploads"
OUTPUTS_DIR = STORAGE_DIR / "outputs"
PREVIEWS_DIR = STORAGE_DIR / "previews"
MODELS_DIR = STORAGE_DIR / "models"
DB_PATH = STORAGE_DIR / "verbatim.db"
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"

# Ensure all critical storage directories exist
for d in [STORAGE_DIR, UPLOADS_DIR, OUTPUTS_DIR, PREVIEWS_DIR, MODELS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Hardware and Model Configurations
SUPPORTED_MODELS = {
    "codeswitched-medium": {
        "id": "codeswitched-medium",
        "name": "Egyptian Arabic & English (Specialized)",
        "repo": "Seif-Eldeen-Sameh/whisper-medium-arabic-codeswitched-ct2",
        "approx_vram_gb": 3.0,
        "approx_download_gb": 0.78,
        "recommended_for": "Fine-tuned specifically for Egyptian colloquial Arabic mixed with English technical terms",
    },
    "small": {
        "id": "small",
        "name": "Fast — small",
        "repo": "Systran/faster-whisper-small",
        "approx_vram_gb": 1.5,
        "approx_download_gb": 0.48,
        "recommended_for": "Quick transcripts on laptops or older hardware",
    },
    "medium": {
        "id": "medium",
        "name": "Balanced — medium",
        "repo": "Systran/faster-whisper-medium",
        "approx_vram_gb": 3.0,
        "approx_download_gb": 1.5,
        "recommended_for": "Standard Whisper multilingual model for general speech",
    },
    "large-v3-turbo": {
        "id": "large-v3-turbo",
        "name": "State-of-the-Art — large-v3-turbo",
        "repo": "deepdml/faster-whisper-large-v3-turbo-ct2",
        "approx_vram_gb": 2.5,
        "approx_download_gb": 1.6,
        "recommended_for": "Latest OpenAI Whisper Large-v3-Turbo architecture (800M params, 128 mel bins, 4x faster)",
    },
    "large-v3": {
        "id": "large-v3",
        "name": "Maximum Quality — large-v3",
        "repo": "Systran/faster-whisper-large-v3",
        "approx_vram_gb": 5.5,
        "approx_download_gb": 3.1,
        "recommended_for": "Highest accuracy for difficult audio, accents, and mixed speech",
    },
    "qwen3-asr-0.6b-hf": {
        "id": "qwen3-asr-0.6b-hf",
        "name": "Qwen3-ASR 0.6B (Experimental Multilingual)",
        "repo": "Qwen/Qwen3-ASR-0.6B-hf",
        "approx_vram_gb": 2.2,
        "approx_download_gb": 1.46,
        "recommended_for": "Experimental Qwen3 foundation ASR (0.6B parameters, audio-LLM architecture, 52 languages)",
    },
}

SUPPORTED_AUDIO_EXTENSIONS = {
    ".ogg", ".opus", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".wma", ".aiff", ".webm",
    ".mp4", ".mov", ".mkv", ".avi"  # Media containers for audio extraction
}

SUPPORTED_OUTPUT_FORMATS = [
    "mp3", "wav", "ogg", "opus", "m4a", "aac", "flac", "aiff", "webm"
]

# Neutral, clean vocabulary hints without meta-explanatory sentences
DEFAULT_VOCAB_HINTS = (
    "IEEE, CIS, IEEE Egypt Section, Branch, Chapter, Proposal, Event, "
    "Instructors, Certified Instructors, Academy, Hosting, Closing Ceremony, STEM, AI, Volunteers, Huawei"
)

MAX_UPLOAD_SIZE_BYTES = 1024 * 1024 * 500  # 500 MB max file size for local desktop app
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
