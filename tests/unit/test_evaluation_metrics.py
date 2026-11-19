import pytest
from app.evaluation.metrics import (
    normalize_arabic_english,
    normalize_raw,
    calculate_wer_cer,
    align_sequences,
)


def test_normalize_arabic_english():
    sample = "ااه مَسَاءُ الفُل يا صَبْري! طبعاً يعني الـ Propsal 100%"
    norm = normalize_arabic_english(sample)
    # Check diacritics removed
    assert "َ" not in norm
    assert "ُ" not in norm
    # Check lowercase
    assert "propsal" in norm
    # Check punctuation removed
    assert "!" not in norm
    assert "%" not in norm
    assert "طبعا" in norm


def test_align_sequences_exact_match():
    ref = ["hello", "world"]
    hyp = ["hello", "world"]
    sub, d, ins, hits, ops = align_sequences(ref, hyp)
    assert (sub, d, ins, hits) == (0, 0, 0, 2)
    assert len(ops) == 2
    assert all(op["type"] == "equal" for op in ops)


def test_align_sequences_mismatches():
    ref = ["the", "quick", "brown", "fox"]
    hyp = ["the", "fast", "brown", "fox", "jumps"]
    # "quick" -> "fast" (sub=1), "jumps" (ins=1), hits=3
    sub, d, ins, hits, ops = align_sequences(ref, hyp)
    assert sub == 1
    assert d == 0
    assert ins == 1
    assert hits == 3


def test_calculate_wer_cer():
    ref = "مساء الفل يا صبري"
    hyp = "مساء النور يا صبري"
    res = calculate_wer_cer(ref, hyp, mode="normalized")
    assert res["substitutions"] == 1
    assert res["hits"] == 3
    assert res["ref_words_count"] == 4
    assert res["wer"] == 0.25
    assert res["wer_percent"] == 25.0
