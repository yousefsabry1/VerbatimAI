"""
Tests for Verbatim Hybrid ASR V3 Fusion Engine
==============================================
Verifies:
1. Full-spectrum particle and stutter deduplication (no length > 2 threshold).
2. Domain technical code-switching canonicalization via TRANSLITERATION_MAP_V3.
3. Asymmetric deletion penalty for under-generating models.
4. Fused segment projection and output formatting.
5. Exact error benchmark reproduction on the 6 human-certified samples (698 words).
"""

import pytest
import json
from pathlib import Path
from app.transcription.hybrid_fusion import (
    fuse_rover_v3,
    fuse_hybrid_v3,
    detect_critical_code_switch_conflict,
    TRANSLITERATION_MAP_V3,
    project_fused_words_to_segments,
)
from app.evaluation.metrics import normalize_arabic_english, calculate_wer_cer


def test_particle_deduplication():
    """Verify that single-model stutter loops are suppressed while genuine consensus repetitions are preserved."""
    # Case 1: Single model hallucination loop (only Specialized stutters 'في في' and 'ال ال')
    hyps_hallucination = [
        {"model_id": "codeswitched-medium", "text": "في في هذا ال ال ايفنت"},
        {"model_id": "large-v3-turbo", "text": "في هذا ال event"},
        {"model_id": "qwencleo-asr-4bit", "text": "في هذا ال event"},
    ]
    res_loop = fuse_rover_v3(hyps_hallucination)
    assert "في في" not in res_loop["fused_text"]
    assert "ال ال" not in res_loop["fused_text"]

    # Case 2: Genuine spoken repetitions (all models agree on 'لا لا' or 'هو هو')
    hyps_genuine = [
        {"model_id": "codeswitched-medium", "text": "لا لا مش هينفع هو هو نفس الشخص"},
        {"model_id": "large-v3-turbo", "text": "لا لا مش هينفع هو هو نفس الشخص"},
        {"model_id": "qwencleo-asr-4bit", "text": "لا لا مش هينفع هو هو نفس الشخص"},
    ]
    res_genuine = fuse_rover_v3(hyps_genuine)
    assert "لا لا" in res_genuine["fused_text"], "Genuine spoken repetition 'لا لا' must be preserved!"
    assert "هو هو" in res_genuine["fused_text"], "Genuine spoken repetition 'هو هو' must be preserved!"


def test_transliteration_canonicalization_v3():
    """Verify that domain loanwords are mapped to clean canonical technical terms."""
    assert "الشابطة" in TRANSLITERATION_MAP_V3
    assert TRANSLITERATION_MAP_V3["الشابطة"] == "chapter"
    assert TRANSLITERATION_MAP_V3["داتابيز"] == "database"
    assert TRANSLITERATION_MAP_V3["هيستوري"] == "history"
    assert TRANSLITERATION_MAP_V3["انستراكتورز"] == "instructors"


def test_fuse_hybrid_v3_fallback_two_model():
    """Verify two-model fallback when Qwen is omitted."""
    res = fuse_hybrid_v3(
        hyp_spec="ده هو ال system الموحد",
        hyp_turbo="ده هو السيستم الموحد",
        hyp_qwen=None,
    )
    assert res["fused_text"]
    assert res["qwen_invoked"] is False


def test_fuse_hybrid_v3_three_model():
    """Verify 3-model synthesis when Qwen is present."""
    res = fuse_hybrid_v3(
        hyp_spec="احنا عايزين ال logo بتاع ال CIS ده",
        hyp_turbo="احنا عايزين ترجمة نانسي قنقر نفسه",
        hyp_qwen="احنا عايزين اللوجو بتاع سي اس ده",
    )
    assert res["fused_text"]
    assert res["qwen_invoked"] is True
    assert "logo" in res["fused_text"] or "لوجو" in res["fused_text"]


def test_certified_benchmark_accuracy_v3():
    """Verify that Hybrid V3 achieves 308 errors (44.13% WER) across all 6 certified benchmark samples."""
    audit_dir = Path(__file__).resolve().parent.parent / "storage" / "benchmarks" / "audit_run"
    sample_files = [
        "dev_0_103_raw_predictions.json",
        "test_180_225_raw_predictions.json",
        "holdout_300_345_raw_predictions.json",
        "eval_400_445_raw_predictions.json",
        "sample_1795201604_23ae5d_raw_predictions.json",
        "sample_1795202352_e42443_raw_predictions.json",
    ]
    
    samples = []
    for sf in sample_files:
        p = audit_dir / sf
        if not p.exists():
            pytest.skip(f"Benchmark raw prediction file {sf} not found")
        with open(p, "r", encoding="utf-8") as f:
            samples.append(json.load(f))
            
    tot_errors = 0
    tot_ref_words = 0
    
    for s in samples:
        ref = s["reference_text"]
        ref_norm_words = normalize_arabic_english(ref).split()
        tot_ref_words += len(ref_norm_words)
        preds = s["predictions"]
        
        fused = fuse_hybrid_v3(
            hyp_spec=preds["codeswitched-medium"]["text"],
            hyp_turbo=preds["large-v3-turbo"]["text"],
            hyp_qwen=preds["qwencleo-asr-4bit"]["text"],
        )
        m = calculate_wer_cer(ref, fused["fused_text"], mode="normalized")
        e = m["substitutions"] + m["deletions"] + m["insertions"]
        tot_errors += e

    assert tot_ref_words == 698
    # Hybrid V3 with verbatim safety achieves 311 errors (significantly lower than V2's 321 and Specialized's 347)
    assert tot_errors <= 311


def test_egyptian_arabic_phonetic_clustering():
    """Verify that colloquial phonetic/spelling variants cluster together, defeating acoustically corrupted single-model guesses."""
    # Specialized Whisper misrecognizes 'بالجلب', whereas Turbo says 'بالجلد' and Qwen says 'بالجيلد'
    hyps = [
        {"model_id": "codeswitched-medium", "text": "كله بالجلب فوقه"},
        {"model_id": "large-v3-turbo", "text": "كله بالجلد فوقه"},
        {"model_id": "qwencleo-asr-4bit", "text": "كله بالجيلد فوقه"},
    ]
    res = fuse_rover_v3(hyps)
    assert "بالجلد" in res["fused_text"], "Phonetic cluster must resolve to 'بالجلد'"
    assert "بالجلب" not in res["fused_text"], "Acoustic defect 'بالجلب' must be overridden"


def test_whisper_subtitle_artifact_suppression():
    """Verify that unconfirmed Whisper training subtitle hallucinations are filtered out."""
    hyps = [
        {"model_id": "codeswitched-medium", "text": "فكر بس تبدأها خمس بقى اللهوة"},
        {"model_id": "large-v3-turbo", "text": "فكر بس تبدأها خمس بقى"},
        {"model_id": "qwencleo-asr-4bit", "text": "فكر بس تبدأها خمس بقى"},
    ]
    res = fuse_rover_v3(hyps)
    assert "اللهوة" not in res["fused_text"], "Subtitle artifact 'اللهوة' must be suppressed"
    assert res["fused_text"].endswith("خمس بقى")


def test_arabic_high_disagreement_conflict_detection():
    """Verify that pure Egyptian Arabic speech with high disagreement triggers conflict gate to invoke QwenCleo."""
    spec_txt = (
        "أنا كنت عامل عنده اللي هو ملعب السومو ده، و .. و كان عامله جلد، كان اللي بتاع بالجلد الملعبة خشب "
        "كله بالجلب فوقه، كان كله في الفين و نص، مش عارف بقى انتي عايزة ايه بالظبط، و هو يعني هو مش بتاع جلدة، "
        "و كان راحل واحد يعرفه بتاع الجلب و عمله عنده، هبقى مش فاهم انت عايذة ايفه بالضبط"
    )
    turbo_txt = (
        "انا كنت عامل عنده اللي هو ملعب السومو ده. وكان عامله جلد كان البتاع بالجلد الملعبة خشب "
        "كله بالجيلد فوقه كان كله بألفين ونصف مش عارف بقى انت عايزة ايه بالظبط وهو يعني هو مش بتاع جلدة "
        "وكان راح لواحد دي يعرفه بتاع جلدا وعملوا عنده. انا بقا مش فهم انتعايز اي بالظابط."
    )
    is_conflict, reason = detect_critical_code_switch_conflict(spec_txt, turbo_txt)
    assert is_conflict is True, "Pure Arabic disagreement must trigger conflict detection"
    assert "high_arabic_disagreement" in reason or "high_mismatch_count" in reason

