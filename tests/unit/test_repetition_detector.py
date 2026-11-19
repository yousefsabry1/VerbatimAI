import pytest
from app.transcription.repetition_detector import (
    find_repeated_ngrams,
    detect_repetition_in_segment,
)


def test_natural_speech_not_flagged():
    # Natural emphasis must NOT be flagged as a pathological loop
    text1 = "لا لا يا صبري مش مشكلة تمام تمام"
    assert detect_repetition_in_segment(text1) is None

    text2 = "يعني احنا بنحاول نعمل ده طبعا طبعا"
    assert detect_repetition_in_segment(text2) is None


def test_single_word_pathological_loop():
    text = "دي كلها مشي ومشي ومشي ومشي ومشي ومشي ومشي ومشي ومشي ومشي"
    res = detect_repetition_in_segment(text)
    assert res is not None
    assert res["has_repetition_loop"] is True
    assert "مشي" in res["pattern"]


def test_ngram_pathological_loop():
    text = "IEEE, CIS, IEEE, CIS, IEEE, CIS, IEEE, CIS"
    res = detect_repetition_in_segment(text)
    assert res is not None
    assert res["has_repetition_loop"] is True
    assert "ieee" in res["pattern"].lower() or "cis" in res["pattern"].lower()


def test_short_word_stuck_loop():
    text = "الميكينج اي اي اي اي اي اي اي اي اي اي اي"
    res = detect_repetition_in_segment(text)
    assert res is not None
    assert res["has_repetition_loop"] is True
