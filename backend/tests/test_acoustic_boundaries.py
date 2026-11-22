import pytest
import numpy as np
from app.transcription.qwencleo_longform import (
    detect_silence_split_points,
    merge_overlapping_chunk_texts,
)

def test_plateau_silence_detection_prefers_long_pauses():
    """
    Verify that plateau-centered silence detection selects the center of a true
    conversational pause rather than an instantaneous plosive dip mid-sentence.
    """
    sr = 16000
    # Create 35 seconds of synthetic speech
    duration = 35.0
    num_samples = int(duration * sr)
    # Background speech (moderate amplitude)
    audio = np.random.normal(0, 0.1, num_samples).astype(np.float32)

    # Place a brief 40ms plosive closure dip at t = 22.0s (RMS = 0.0001)
    plosive_start = int(22.0 * sr)
    plosive_end = int(22.04 * sr)
    audio[plosive_start:plosive_end] = 0.0001

    # Place a genuine 1.2-second conversational pause at t = 26.0s - 27.2s (RMS = 0.001)
    pause_start = int(26.0 * sr)
    pause_end = int(27.2 * sr)
    audio[pause_start:pause_end] = 0.001

    splits = detect_silence_split_points(
        audio, sr=sr, target_interval=25.0, min_interval=18.0, max_interval=32.0, method="plateau"
    )
    assert len(splits) == 3  # [0.0, split_point, 35.0]
    split_point = splits[1]

    # The split point MUST be placed within the real conversational pause (around 26.6s)
    # NOT in the 40ms plosive closure dip at 22.0s!
    assert 25.5 <= split_point <= 27.5, f"Split placed at {split_point}s instead of within real pause (26.0s-27.2s)"

def test_boundary_preservation_for_code_switched_terms():
    """Verify that boundary deduplication handles Arabic-English code-switched phrases cleanly."""
    c1 = "إحنا عندنا حوالي 25 شخص في التيم منهم 7 شغالين على الـContent"
    c2 = "على الـContent وخمسة على الـDesign والباقي متقسمين بين الـDevelopment والـOperations"

    merged = merge_overlapping_chunk_texts([c1, c2])
    # Verify 'Content' is not duplicated
    words = merged.split()
    content_count = sum(1 for w in words if "content" in w.lower())
    assert content_count == 1, f"Expected 1 instance of Content, got {content_count} in '{merged}'"
    assert "والـOperations" in merged or "الـOperations" in merged

def test_timestamp_continuity_multi_chunk():
    """Verify that multiple chunks form a continuous, non-overlapping partition of the audio."""
    sr = 16000
    duration = 75.0
    audio = np.random.normal(0, 0.05, int(duration * sr)).astype(np.float32)

    # Insert silent pauses every ~24 seconds
    for t in [24.0, 48.0]:
        audio[int(t * sr) : int((t + 1.0) * sr)] = 0.0001

    splits = detect_silence_split_points(audio, sr=sr, target_interval=25.0, min_interval=15.0, max_interval=35.0)

    assert splits[0] == 0.0
    assert abs(splits[-1] - duration) < 0.05
    for i in range(len(splits) - 1):
        assert splits[i + 1] > splits[i], f"Split {i} ({splits[i]}) not less than next ({splits[i+1]})"
        chunk_dur = splits[i + 1] - splits[i]
        assert chunk_dur >= 5.0, f"Chunk {i} too short: {chunk_dur}s"

def test_boundary_overlap_deduplication_preserves_hesitations():
    """Verify that genuine spoken repetitions ('لا لا', 'في في') are preserved across boundaries."""
    c1 = "وفي نقطة تانية مهمة جدا لا لا"
    c2 = "استنى أنا قصدي إن الـDeadline يوم الخميس"

    merged = merge_overlapping_chunk_texts([c1, c2])
    assert "لا لا" in merged, f"Spoken repetition was erroneously removed: '{merged}'"

def test_no_dropped_speech_on_clean_boundaries():
    """Verify that clean boundaries with no overlapping tokens are simply joined with a space."""
    c1 = "الجزء الأول من المحاضرة خلص."
    c2 = "ندخل دلوقتي على الجزء التاني."

    merged = merge_overlapping_chunk_texts([c1, c2])
    expected = "الجزء الأول من المحاضرة خلص. ندخل دلوقتي على الجزء التاني."
    assert merged == expected
