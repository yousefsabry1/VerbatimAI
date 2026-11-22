import pytest
from app.transcription.hybrid_fusion import (
    tokenize_transcript,
    is_transliteration_match,
    enhanced_token_match_cost,
    fuse_rover_v3,
    TRANSLITERATION_MAP_V3,
)
from app.evaluation.metrics import normalize_arabic_english

def test_transliteration_matching_core_technical_terms():
    """Verify that common Egyptian-English code-switched technical terms match bidirectionally."""
    pairs = [
        ("data", "داتا"),
        ("data", "الداتا"),
        ("database", "داتابيز"),
        ("database", "الداتابيز"),
        ("marketing", "ماركتنج"),
        ("marketing", "الماركتنج"),
        ("operations", "اوبريشنز"),
        ("operations", "الاوبريشنز"),
        ("dashboard", "داشبورد"),
        ("dashboard", "الداشبورد"),
        ("feedback", "فيدباك"),
        ("feedback", "الفيدباك"),
        ("meeting", "ميتنج"),
        ("planning", "بلانينج"),
        ("task", "تاسك"),
        ("task", "تسق"),
    ]
    for en, ar in pairs:
        t_en = tokenize_transcript(en)[0]
        t_ar = tokenize_transcript(ar)[0]
        assert is_transliteration_match(t_en, t_ar), f"Failed match for {en} vs {ar}"
        assert is_transliteration_match(t_ar, t_en), f"Failed reverse match for {ar} vs {en}"
        assert enhanced_token_match_cost(t_en, t_ar) <= 0.25, f"Match cost too high for {en} vs {ar}"

def test_negative_controls_prevent_false_transliterations():
    """Verify that common Arabic non-technical words and negations NEVER match unrelated English words."""
    neg_pairs = [
        ("not", "مش"),
        ("no", "لا"),
        ("never", "ابدا"),
        ("from", "من"),
        ("in", "في"),
        ("all", "كل"),
        ("said", "قال"),
        ("this", "ده"),
        ("that", "دي"),
        ("door", "باب"),
        ("book", "كتاب"),
    ]
    for en, ar in neg_pairs:
        t_en = tokenize_transcript(en)[0]
        t_ar = tokenize_transcript(ar)[0]
        assert not is_transliteration_match(t_en, t_ar), f"False positive transliteration: {en} vs {ar}"
        assert enhanced_token_match_cost(t_en, t_ar) == 1.0, f"False cost discount: {en} vs {ar}"

def test_surface_form_preservation_in_rover_v3():
    """Verify that ROVER V3 preserves the majority model's surface form (whether Arabic or English)."""
    # Case 1: Majority voted English -> English surface form wins
    hyps_en_majority = [
        {"model_id": "codeswitched-medium", "text": "محتاجين نعمل backup لل data"},
        {"model_id": "large-v3-turbo", "text": "محتاجين نعمل باك اب للداتا"},
        {"model_id": "qwencleo-asr-4bit", "text": "محتاجين نعمل backup لل data"},
    ]
    res_en = fuse_rover_v3(hyps_en_majority)
    assert "data" in res_en["fused_text"]

    # Case 2: Majority voted Arabic transliteration -> Arabic surface form wins (No forced English rewriting!)
    hyps_ar_majority = [
        {"model_id": "codeswitched-medium", "text": "محتاجين نعمل باك اب للداتا"},
        {"model_id": "large-v3-turbo", "text": "محتاجين نعمل باك اب للداتا"},
        {"model_id": "qwencleo-asr-4bit", "text": "محتاجين نعمل backup لل data"},
    ]
    res_ar = fuse_rover_v3(hyps_ar_majority)
    assert "للداتا" in res_ar["fused_text"]

def test_proclitic_transparency():
    """Verify that proclitics like 'للـ' or 'الـ' do not block transliteration matching."""
    t_en = tokenize_transcript("database")[0]
    t_ar = tokenize_transcript("للداتابيز")[0]
    assert is_transliteration_match(t_en, t_ar)
    assert enhanced_token_match_cost(t_en, t_ar) <= 0.25

def test_genuine_repetitions_protected_with_transliteration():
    """Verify that real spoken repetitions (e.g., 'واحدة واحدة') are preserved and not deduplicated."""
    hyps = [
        {"model_id": "codeswitched-medium", "text": "نخلص الحاجات دي واحدة واحدة"},
        {"model_id": "large-v3-turbo", "text": "نخلص الحاجات دي واحدة واحدة"},
        {"model_id": "qwencleo-asr-4bit", "text": "نخلص الحاجات دي واحده واحده"},
    ]
    res = fuse_rover_v3(hyps)
    words = res["fused_text"].split()
    assert "واحدة واحدة" in res["fused_text"] or "واحده واحده" in res["fused_text"]
