"""
Targeted Tests for Robust Tokenization and Hallucination Loop Suppression
========================================================================
Verifies:
1. Punctuation-joined hallucination loops (e.g., 'موسيقى.موسيقى.موسيقى.', 'لا،لا،لا', 'hello.hello.hello').
2. Strict verbatim preservation of genuine human spoken repetitions (e.g., 'لا لا', 'هو هو', 'في في', 'وزارة الشباب وزارة الشباب').
3. Protection of decimal numbers (3.14, 10,000, 12.5%), Arabic digits (٣.١٤, ١٠,٠٠٠), abbreviations (U.S.A., A.I., e.g., i.e.), URLs, and hyphenated terms.
4. Pathological long tokens joined by punctuation.
5. Consensus alignment and duplicate suppression under ROVER confusion networks.
6. Timestamp projection and segment formatting integrity.
7. Deterministic fusion behavior.
8. Exact reproduction and resolution of cs_hardware_73.
"""

import pytest
import re
from app.transcription.hybrid_fusion import (
    robust_split_transcript,
    tokenize_transcript,
    fuse_rover_v3,
    fuse_hybrid_v3,
    fuse_conservative_agreement,
    project_fused_words_to_segments,
)
from app.transcription.repetition_detector import (
    find_repeated_ngrams,
    detect_repetition_in_segment,
)
from app.evaluation.metrics import normalize_arabic_english, calculate_wer_cer


def test_punctuation_joined_tokens_splitting():
    """Verify that tokens joined by punctuation without whitespace are properly split."""
    # Arabic period
    t1 = robust_split_transcript("موسيقى.موسيقى.موسيقى.")
    assert t1 == ["موسيقى.", "موسيقى.", "موسيقى."]

    # Arabic comma
    t2 = robust_split_transcript("لا،لا،لا")
    assert t2 == ["لا،", "لا،", "لا"]

    # English period
    t3 = robust_split_transcript("hello.hello.hello")
    assert t3 == ["hello.", "hello.", "hello"]

    # Exclamation mark
    t4 = robust_split_transcript("نعم!نعم!نعم")
    assert t4 == ["نعم!", "نعم!", "نعم"]

    # Slash
    t5 = robust_split_transcript("أه/أه/أه")
    assert t5 == ["أه/", "أه/", "أه"]


def test_decimals_and_abbreviations_protection():
    """Verify that numbers, decimals, abbreviations, and URLs are never incorrectly split."""
    # English and Arabic decimals & percentages
    samples = [
        "3.14",
        "10,000",
        "12.5%",
        "0.5",
        "٣.١٤",
        "١٠,٠٠٠",
        "U.S.A.",
        "A.I.",
        "e.g.",
        "i.e.",
        "Dr.",
        "Ph.D.",
        "verbatim.ai",
        "https://google.com/test",
        "user@example.com",
        "code-switching",
        "large-v3-turbo",
    ]
    for s in samples:
        res = robust_split_transcript(s)
        assert res == [s], f"Protection failed for '{s}': got {res}"


def test_tokenize_transcript_structure():
    """Verify structured token dictionaries for code-switching and punctuation tokens."""
    tokens = tokenize_transcript("الـ 3.14 في U.S.A. وتقنية code-switching تمام")
    surfaces = [t["surface"] for t in tokens]
    assert "3.14" in surfaces
    assert "U.S.A." in surfaces
    assert "code-switching" in surfaces

    cs_tok = next(t for t in tokens if t["surface"] == "code-switching")
    assert cs_tok["is_latin"] is True
    assert cs_tok["has_latin"] is True


def test_punctuation_loop_suppression_in_rover_v3():
    """Verify that single-model uncorroborated punctuation loops are completely eliminated."""
    hyps_loop = [
        {"model_id": "codeswitched-medium", "text": "موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى."},
        {"model_id": "large-v3-turbo", "text": ""},
        {"model_id": "qwencleo-asr-4bit", "text": ""},
    ]
    res = fuse_rover_v3(hyps_loop)
    assert res["fused_text"] == "", f"Loop should be completely suppressed, got: {res['fused_text']}"


def test_genuine_repeated_words_preserved_in_rover_v3():
    """Verify strict verbatim preservation of genuine human spoken repetitions."""
    # Case 1: Short word repetition (stutter / emphasis)
    hyps1 = [
        {"model_id": "codeswitched-medium", "text": "لا لا مش هينفع خالص"},
        {"model_id": "large-v3-turbo", "text": "لا لا مش هينفع خالص"},
        {"model_id": "qwencleo-asr-4bit", "text": "لا لا مش هينفع خالص"},
    ]
    res1 = fuse_rover_v3(hyps1)
    assert "لا لا" in res1["fused_text"], "Genuine repetition 'لا لا' must be preserved"

    # Case 2: Multi-word phrase repetition
    hyps2 = [
        {"model_id": "codeswitched-medium", "text": "وزارة الشباب وزارة الشباب والرياضة"},
        {"model_id": "large-v3-turbo", "text": "وزارة الشباب وزارة الشباب والرياضة"},
        {"model_id": "qwencleo-asr-4bit", "text": "وزارة الشباب وزارة الشباب والرياضة"},
    ]
    res2 = fuse_rover_v3(hyps2)
    norm_fused = normalize_arabic_english(res2["fused_text"])
    assert "وزاره الشباب وزاره الشباب" in norm_fused, "Multi-word repetition must be preserved"


def test_repetition_detector_catches_punctuation_loops():
    """Verify that detect_repetition_in_segment flags punctuation-joined loops."""
    # Punctuation-joined loop
    loop_text = "موسيقى.موسيقى.موسيقى.موسيقى.موسيقى."
    info = detect_repetition_in_segment(loop_text)
    assert info is not None
    assert info["has_repetition_loop"] is True
    assert "موسيقى" in info["pattern"]

    # Natural speech must NOT be flagged
    clean_text = "لا لا يا فندم هو هو نفس الشخص بالضبط"
    clean_info = detect_repetition_in_segment(clean_text)
    assert clean_info is None


def test_cs_hardware_73_pathological_loop_eliminated():
    """Verify exact reproduction and complete elimination of the cs_hardware_73 loop."""
    hyp_spec = "أما بالنسبة لل project بتاعي أنا شغال mainly برضه حاجة hardware, أما برضه حاجة hardware موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.موسيقى.م"
    hyp_turbo = "اما بالنسبة للبروجيكت بتاعي انا شغال مين لبرضو حاجة هاردوير"
    hyp_qwen = "أما بالنسبة للبروجكت بتاعي أنا شغال mainly برضه حاجة hardware"
    ref = "أما بالنسبة لل project بتاعى، أنا شغال حاجة mainly برضه حاجة Hardware"

    fused = fuse_hybrid_v3(
        hyp_spec=hyp_spec,
        hyp_turbo=hyp_turbo,
        hyp_qwen=hyp_qwen,
        duration_seconds=3.98,
    )
    fused_text = fused["fused_text"]

    # 1. Zero occurrences of 'موسيقى' in fused text
    assert "موسيقى" not in fused_text, f"'موسيقى' must not appear in fused text: {fused_text}"

    # 2. Total word error count must be <= 5 (down from 42!)
    m = calculate_wer_cer(ref, fused_text, mode="normalized")
    total_errors = m["substitutions"] + m["deletions"] + m["insertions"]
    assert total_errors <= 5, f"Expected <= 5 errors, got {total_errors} ({m})"
    assert m["insertions"] <= 2, f"Expected <= 2 insertions, got {m['insertions']}"


def test_deterministic_fusion_behavior():
    """Verify that fusion is completely deterministic across repeated executions."""
    hyp_spec = "أما بالنسبة لل project بتاعي أنا شغال mainly برضه حاجة hardware, موسيقى.موسيقى."
    hyp_turbo = "اما بالنسبة للبروجيكت بتاعي انا شغال مين لبرضو حاجة هاردوير"
    hyp_qwen = "أما بالنسبة للبروجكت بتاعي أنا شغال mainly برضه حاجة hardware"

    results = set()
    for _ in range(10):
        res = fuse_hybrid_v3(hyp_spec, hyp_turbo, hyp_qwen)
        results.add(res["fused_text"])

    assert len(results) == 1, f"Fusion must be 100% deterministic, got multiple results: {results}"


def test_segment_projection_and_timestamps():
    """Verify that fused tokens map cleanly onto segment timestamps without NaN or backward steps."""
    spec_segments = [
        {"id": 0, "start": 0.0, "end": 2.5, "text": "أما بالنسبة لل project بتاعي"},
        {"id": 1, "start": 2.5, "end": 4.0, "text": "أنا شغال mainly برضه حاجة hardware"},
    ]
    fused_text = "أما بالنسبة project بتاعي أنا شغال mainly hardware"

    proj = project_fused_words_to_segments(spec_segments, fused_text)
    assert len(proj) == 2
    for s in proj:
        assert s["start"] >= 0.0
        assert s["end"] >= s["start"]
        assert len(s["text"].strip()) > 0
