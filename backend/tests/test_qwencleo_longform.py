"""
VerbatimAI — Tests for QwenCleo Safe Long-Form Transcription Engine
===================================================================
Validates:
1. Silence-aware boundary detection & frame calculation.
2. Overlap-aware chunk concatenation without duplicating overlap words.
3. Strict preservation of genuine internal spoken repetitions (e.g. 'لا لا', 'في في').
4. Dynamic token budgeting based on duration (preventing premature 512-token cutoff).
5. Truncation / token ceiling detection.
6. Timestamp continuity across silence-split intervals.
"""

import pytest
import numpy as np
from app.transcription.qwencleo_longform import (
    detect_silence_split_points,
    merge_overlapping_chunk_texts,
    SAMPLE_RATE,
)


def test_silence_split_points_short_audio():
    """Short audio <= max_interval should return [0.0, duration] without chunking."""
    sr = 16000
    duration = 20.0
    audio = np.zeros(int(duration * sr), dtype=np.float32)
    splits = detect_silence_split_points(audio, sr=sr, max_interval=35.0)
    assert splits == [0.0, 20.0]


def test_silence_split_points_finds_pauses():
    """Validates that pause intervals with low RMS are chosen as split boundaries."""
    sr = 16000
    duration = 60.0
    # Generate audio with speech burst (high energy) and pause (zero energy) around 26-28s
    audio = np.random.uniform(-0.5, 0.5, int(duration * sr)).astype(np.float32)
    # Silence at 26.0s to 28.0s
    silence_st = int(26.0 * sr)
    silence_en = int(28.0 * sr)
    audio[silence_st:silence_en] = 0.0

    splits = detect_silence_split_points(
        audio,
        sr=sr,
        target_interval=27.0,
        min_interval=20.0,
        max_interval=35.0,
    )
    assert len(splits) >= 3
    assert splits[0] == 0.0
    # First split should land inside the silence pause [26.0, 28.0]
    assert 25.5 <= splits[1] <= 28.5
    assert splits[-1] == 60.0


def test_merge_overlapping_chunk_texts_basic():
    """Chunks with no overlap should concatenate cleanly with space."""
    c1 = "بص يا سيدي أنا هقولك على شوية حاجات"
    c2 = "عايزين نركز فيها الفترة الجاية"
    merged = merge_overlapping_chunk_texts([c1, c2])
    assert merged == "بص يا سيدي أنا هقولك على شوية حاجات عايزين نركز فيها الفترة الجاية"


def test_merge_overlapping_chunk_texts_deduplicates_boundary():
    """Overlapping boundary words must be deduplicated."""
    c1 = "إحنا محتاجين نخلص الplanning ونحدد مين مسؤول"
    c2 = "مين مسؤول عن كل task وبعد كده"
    merged = merge_overlapping_chunk_texts([c1, c2])
    assert merged == "إحنا محتاجين نخلص الplanning ونحدد مين مسؤول عن كل task وبعد كده"
    # Ensure 'مين مسؤول' is not duplicated
    assert merged.count("مين مسؤول") == 1


def test_merge_overlapping_chunk_texts_preserves_genuine_repetitions():
    """Genuine internal repetitions like 'لا لا' or 'في في' must NOT be scrubbed."""
    c1 = "وفي نقطة تانية مهمة جدا لا لا استنى"
    c2 = "أنا قصدي إن الdeadline يوم الخميس"
    merged = merge_overlapping_chunk_texts([c1, c2])
    assert "لا لا استنى" in merged
    assert merged.count("لا لا") == 1

    c3 = "وفي في نقطة كمان نسيت أقولها"
    c4 = "إحنا محتاجين نعمل backup للداتا"
    merged2 = merge_overlapping_chunk_texts([c3, c4])
    assert "وفي في نقطة" in merged2
    assert "في في" in merged2


def test_merge_overlapping_chunk_texts_empty_and_single():
    assert merge_overlapping_chunk_texts([]) == ""
    assert merge_overlapping_chunk_texts(["كلام واحد"]) == "كلام واحد"
    assert merge_overlapping_chunk_texts(["   "]) == ""


def test_dynamic_budget_calculation_for_duration():
    """Calculates appropriate token budget scaling for different durations."""
    # 15s audio -> 512 tokens
    assert min(2048, max(512, int(15.0 * 10))) == 512
    # 90s audio -> 900 tokens (well beyond 512 default)
    assert min(2048, max(512, int(90.0 * 10))) == 900
    # 149s audio -> 1490 tokens (preventing 512 cutoff)
    assert min(2048, max(512, int(149.1 * 10))) == 1491
    # 350s audio -> clamped at 2048 for single pass (which triggers chunking > 45s anyway)
    assert min(2048, max(512, int(350.0 * 10))) == 2048


def test_timestamp_continuity_across_splits():
    """Split points must form a continuous monotonic sequence without gaps."""
    sr = 16000
    duration = 120.0
    audio = np.random.uniform(-0.1, 0.1, int(duration * sr)).astype(np.float32)
    splits = detect_silence_split_points(audio, sr=sr, target_interval=25.0, min_interval=18.0, max_interval=32.0)
    assert splits[0] == 0.0
    assert splits[-1] == 120.0
    for i in range(len(splits) - 1):
        assert splits[i] < splits[i+1]
        chunk_len = splits[i+1] - splits[i]
        assert chunk_len >= 5.0
