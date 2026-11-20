import pytest
from app.transcription.hybrid_fusion import (
    tokenize_transcript,
    align_hypotheses_pairwise,
    fuse_conservative_agreement,
    fuse_rover,
    fuse_weighted,
    route_contextual_segments,
    fuse_selective_three_model,
    calculate_oracle_upper_bound,
    is_latin_word,
    strip_arabic_clitics,
)


def test_tokenize_and_clitics():
    tokens = tokenize_transcript("ال Proposer وال event بتاعنا تمام")
    assert len(tokens) == 6
    assert tokens[1]["is_latin"] is True
    assert tokens[1]["stem"] == "Proposer"


def test_align_pairwise_identical():
    text = "ده تسجيل تجريبي لاختبار النظام"
    t1 = tokenize_transcript(text)
    t2 = tokenize_transcript(text)
    slots = align_hypotheses_pairwise(t1, t2)
    assert len(slots) == len(t1)
    for s in slots:
        assert s["type"] == "match"


def test_conservative_agreement_code_switch_priority():
    # Model A outputs English term 'Proposer'
    # Model B outputs Arabic phonetic 'برجوزر'
    spec = "يعني بتاع ال Proposer عليه"
    turbo = "يعني بتاع البرجوزر عليه"
    res = fuse_conservative_agreement(spec, turbo, duration_seconds=10.0)
    assert "Proposer" in res["fused_text"]
    assert res["agreed_slots"] >= 3


def test_conservative_agreement_repetition_suppression():
    # Spec has hallucinated repetition 'يعني يعني يعني'
    # Turbo has clean 'يعني'
    spec = "هو يعني يعني يعني كويس"
    turbo = "هو يعني كويس"
    res = fuse_conservative_agreement(spec, turbo, duration_seconds=10.0)
    # The duplicate 'يعني' should be suppressed
    assert "يعني يعني یعنی" not in res["fused_text"]


def test_rover_confusion_network():
    h1 = {"model_id": "codeswitched-medium", "text": "هو راح ال conference امبارح"}
    h2 = {"model_id": "large-v3-turbo", "text": "هو راح المؤتمر امبارح"}
    h3 = {"model_id": "qwencleo-asr-4bit", "text": "هو راح ال conference امبارح"}
    res = fuse_rover([h1, h2, h3])
    # 2 out of 3 agree on conference
    assert "conference" in res["fused_text"]
    assert res["num_models"] == 3


def test_weighted_fusion():
    spec = "النظام شغال تمام"
    turbo = "النظام شغال تمام جدا"
    res = fuse_weighted(spec, turbo, weight_spec=1.5, weight_turbo=1.0)
    assert res["method"] == "weighted_fusion"
    assert "النظام شغال تمام" in res["fused_text"]


def test_contextual_segment_routing():
    # Segment where Turbo under-generated severely (e.g. 2 words in 45s)
    seg_spec = [{"start": 0.0, "end": 45.0, "text": "ده كلام كتير جدا ومهم ومكتوب ومسجل بالكامل عشان نختبر النظام"}]
    seg_turbo = [{"start": 0.0, "end": 45.0, "text": "ده كلام"}]
    res = route_contextual_segments(seg_spec, seg_turbo)
    assert res["winner"] == "codeswitched-medium"


def test_selective_three_model():
    spec = "ده event كبير"
    turbo = "ده ايفنت كبير"
    qwen = "ده event كبير"
    res = fuse_selective_three_model(spec, turbo, hyp_qwen=qwen, disagreement_threshold=0.1)
    assert "event" in res["fused_text"]


def test_oracle_upper_bound():
    ref = "المسرح بتاعها ان هو يهوست الايفنت نفسه وال accesability أن الطلبه دي كلها تيجي"
    candidates = {
        "codeswitched-medium": "المصرح بتاعها ان هو يعني هفط ال event نفسه و اللقسة التي الناس ان الطلبه دي كلها تيجي",
        "large-v3-turbo": "المسرح بتاعها ان هو يعني نفسه والطلبه دي كلها تيجي",
    }
    oracle = calculate_oracle_upper_bound(candidates, ref)
    assert oracle["status"] == "success"
    assert "ORACLE — NOT DEPLOYABLE" in oracle["label"]
    assert oracle["oracle_wer"] is not None
    # Oracle WER should be strictly lower than or equal to either candidate
    assert oracle["oracle_wer"] <= oracle["best_individual_wer"]
