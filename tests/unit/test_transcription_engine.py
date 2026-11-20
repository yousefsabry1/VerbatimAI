import pytest
from pathlib import Path
from app.core.config import SUPPORTED_MODELS, DEFAULT_VOCAB_HINTS
from app.transcription.engine import is_model_downloaded, get_model_dir
from app.exports.formatters import generate_clean_txt, generate_srt

def test_codeswitched_model_registered():
    assert "codeswitched-medium" in SUPPORTED_MODELS
    info = SUPPORTED_MODELS["codeswitched-medium"]
    assert "Seif-Eldeen-Sameh" in info["repo"]
    assert info["approx_download_gb"] < 1.0

def test_default_vocab_hints_contains_key_terms():
    assert "IEEE" in DEFAULT_VOCAB_HINTS
    assert "CIS" in DEFAULT_VOCAB_HINTS
    assert "Proposal" in DEFAULT_VOCAB_HINTS
    assert "Event" in DEFAULT_VOCAB_HINTS
    # Assert benchmark evaluation reference terms are strictly excluded to prevent contamination
    for term in ["Volunteers", "Committees", "Instructors", "Registration"]:
        assert term not in DEFAULT_VOCAB_HINTS, f"Contamination risk: {term} found in DEFAULT_VOCAB_HINTS"
    # Assert harmful conversational bias words are NOT in the default hints
    assert "meeting, team, project, deadline" not in DEFAULT_VOCAB_HINTS

def test_codeswitched_model_downloaded():
    # Verify the model files are present and recognized by the engine
    target_dir = get_model_dir("codeswitched-medium")
    assert target_dir.exists()
    assert is_model_downloaded("codeswitched-medium") is True

def test_codeswitched_segments_formatting():
    segments = [
        {
            "id": 1,
            "start": 0.4,
            "end": 5.2,
            "text": "دي الجزئية بتاع ال Proposal وال Logo بتاع CIS",
            "confidence": "high",
            "uncertain": False,
        },
        {
            "id": 2,
            "start": 5.5,
            "end": 9.8,
            "text": "وضح ال event title وال instructors",
            "confidence": "high",
            "uncertain": False,
        }
    ]
    clean_txt = generate_clean_txt(segments)
    assert "Proposal" in clean_txt
    assert "Logo" in clean_txt
    assert "CIS" in clean_txt
    assert "instructors" in clean_txt

    srt = generate_srt(segments)
    assert "00:00:00,400 --> 00:00:05,200" in srt
    assert "00:00:05,500 --> 00:00:09,800" in srt
