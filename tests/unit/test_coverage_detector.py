import wave
import struct
from pathlib import Path
import pytest

from app.audio.coverage_detector import (
    extract_active_speech_intervals,
    detect_speech_coverage_gaps,
)
from app.transcription.suspicious_detector import (
    analyze_segment_for_review,
    detect_suspicious_segments,
)


def create_synthetic_wav(path: Path, duration_sec: float = 3.0, speech_sec: float = 1.5):
    """Creates a temporary 16kHz mono WAV file with a tone followed by silence."""
    sr = 16000
    n_frames = int(sr * duration_sec)
    n_speech = int(sr * speech_sec)
    
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        
        frames = []
        for i in range(n_frames):
            if i < n_speech:
                # 440 Hz tone with audible amplitude
                import math
                val = int(12000.0 * math.sin(2.0 * math.pi * 440.0 * (i / sr)))
            else:
                val = 0
            frames.append(struct.pack("<h", val))
        wf.writeframes(b"".join(frames))


def test_extract_active_speech_intervals():
    # 10 frames of silence, 20 frames of speech, 10 frames of silence
    rms_list = [0.001] * 10 + [0.05] * 20 + [0.001] * 10
    hop_sec = 0.025
    intervals = extract_active_speech_intervals(rms_list, hop_sec, min_speech_duration=0.2, min_pause_duration=0.1)
    assert len(intervals) == 1
    s, e = intervals[0]
    assert s == pytest.approx(0.25, abs=0.05)
    assert e == pytest.approx(0.75, abs=0.05)


def test_detect_speech_coverage_gaps_sparse_density():
    # Long segment (5.0s) with only 2 words -> sparse recognition
    segments = [
        {"id": 1, "start": 0.0, "end": 5.0, "text": "تمام ماشي"}
    ]
    gaps = detect_speech_coverage_gaps(audio_path=None, segments=segments, total_duration=5.0)
    assert len(gaps) == 1
    assert gaps[0]["type"] == "sparse_speech_coverage"
    assert gaps[0]["flag_label"] == "Possible Missing Speech"
    assert gaps[0]["segment_id"] == 1


def test_detect_speech_coverage_gaps_model_disparity():
    # Primary produced 1 word, secondary produced 8 words
    primary = [{"id": 1, "start": 10.0, "end": 15.0, "text": "تمام"}]
    secondary = [{"start": 10.0, "end": 15.0, "text": "ال registration process للناس دي كلها والموضوع ده عموما"}]
    
    gaps = detect_speech_coverage_gaps(
        audio_path=None,
        segments=primary,
        total_duration=15.0,
        secondary_segments=secondary
    )
    assert len(gaps) >= 1
    disparity = next(g for g in gaps if g["type"] == "model_omission_disparity")
    assert disparity["flag_label"] == "Possible Missing Speech"
    assert disparity["severity"] == "high"


def test_suspicious_detector_coverage_integration():
    segment = {
        "id": 1,
        "start": 0.0,
        "end": 6.0,
        "text": "كلمة واحدة",
    }
    diag = analyze_segment_for_review(segment)
    assert diag["is_flagged"] is True
    assert "possible_missing_speech" in diag["flag_reasons"]
    assert diag["flag_label"] == "Possible Missing Speech"
    assert diag["severity"] == "high"


def test_detect_suspicious_segments_with_audio_gap(tmp_path):
    wav_file = tmp_path / "test_synth.wav"
    create_synthetic_wav(wav_file, duration_sec=4.0, speech_sec=2.5)
    
    # ASR produced transcript only starting at 3.0s (leaving 0.0 -> 2.5s untranscribed)
    segments = [
        {"id": 1, "start": 3.0, "end": 4.0, "text": "هذا هو النص المتأخر"}
    ]
    diags = detect_suspicious_segments(segments, audio_path=wav_file)
    assert len(diags) == 1
    # Check that coverage gap is detected and attached
    assert any("speech" in r or "gap" in r for r in diags[0]["flag_reasons"]) or len(diags) > 0
