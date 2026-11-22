import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
from app.transcription.hybrid_fusion import (
    is_transliteration_match,
    soft_arabic_distance,
    enhanced_token_match_cost,
    detect_critical_code_switch_conflict,
    fuse_rover_v2,
    fuse_hybrid_v2,
    project_fused_words_to_segments,
)


def test_transliteration_matching():
    tok_ar = {"surface": "بروفايد", "norm": "بروفايد", "norm_stem": "بروفايد", "is_latin": False, "has_latin": False}
    tok_en = {"surface": "provide", "norm": "provide", "norm_stem": "provide", "is_latin": True, "has_latin": True}
    assert is_transliteration_match(tok_ar, tok_en)
    assert is_transliteration_match(tok_en, tok_ar)

    tok_fund_ar = {"surface": "الفاند", "norm": "الفاند", "norm_stem": "فاند", "is_latin": False, "has_latin": False}
    tok_fund_en = {"surface": "fund", "norm": "fund", "norm_stem": "fund", "is_latin": True, "has_latin": True}
    assert is_transliteration_match(tok_fund_ar, tok_fund_en)


def test_soft_arabic_distance():
    # Misspellings involving saad vs seen
    assert soft_arabic_distance("المسرح", "المصرح") < 0.20
    # Misspellings involving taa vs tehh
    assert soft_arabic_distance("ازبط", "اظبط") < 0.20
    # Unrelated words should have high distance
    assert soft_arabic_distance("جامعة", "طيران") == 1.0


def test_fuse_rover_v2_transliteration_resolution():
    # Specialized outputs English, Turbo outputs Arabic transliteration, Qwen outputs English
    hyps = [
        {"model_id": "codeswitched-medium", "text": "محتاج توضح provide ال fund"},
        {"model_id": "large-v3-turbo", "text": "محتاج توضح بروفايد الفاند"},
        {"model_id": "qwencleo-asr-4bit", "text": "محتاج توضح provide fund"},
    ]
    res = fuse_rover_v2(hyps)
    fused = res["fused_text"]
    assert "provide" in fused
    assert "fund" in fused
    assert "بروفايد" not in fused
    assert "الفاند" not in fused


def test_detect_critical_code_switch_conflict():
    # Disagreement on code-switched technical terms
    spec_text = "اول حاجة هن out teach لل media"
    turbo_text = "اول حاجة هننقاوتيتش للميديا"
    is_conflict, reason = detect_critical_code_switch_conflict(spec_text, turbo_text)
    assert is_conflict is True

    # Complete agreement
    agree_spec = "نبدأ من تحت بيخدم الطلاب في ايه"
    agree_turbo = "نبدأ من تحت بيخدم الطلاب في ايه"
    is_conflict_agree, _ = detect_critical_code_switch_conflict(agree_spec, agree_turbo)
    assert is_conflict_agree is False


def test_project_fused_words_to_segments():
    spec_segs = [
        {"start": 0.0, "end": 4.5, "text": "المصرح بتاعها ان هو يعني"},
        {"start": 4.5, "end": 9.0, "text": "هفط ال event نفسه واللقسة"},
    ]
    fused_text = "المسرح بتاعها ان هو يعني host event نفسه والaccessibility"
    out_segs = project_fused_words_to_segments(spec_segs, fused_text)
    assert len(out_segs) == 2
    assert out_segs[0]["start"] == 0.0
    assert out_segs[0]["end"] == 4.5
    assert "المسرح" in out_segs[0]["text"]
    assert out_segs[1]["start"] == 4.5
    assert out_segs[1]["end"] == 9.0
    assert "host event" in out_segs[1]["text"]
    assert "accessibility" in out_segs[1]["text"]
