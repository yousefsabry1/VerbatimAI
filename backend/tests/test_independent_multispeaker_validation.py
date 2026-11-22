import json
from pathlib import Path
import pytest

@pytest.fixture
def eval_data():
    backend_dir = Path(__file__).resolve().parent.parent
    eval_dir = backend_dir / "storage" / "independent_eval"
    manifest = json.loads((eval_dir / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((eval_dir / "evaluation_results.json").read_text(encoding="utf-8"))
    predictions = json.loads((eval_dir / "predictions_raw.json").read_text(encoding="utf-8"))
    return manifest, results, predictions

def test_independent_eval_manifest_integrity(eval_data):
    manifest, results, predictions = eval_data
    assert len(manifest) == 24
    assert sum(m["word_count"] for m in manifest) == 511
    # Verify no overlap with historical test_by_me or historical dev slices
    for m in manifest:
        assert "test by me" not in m["audio_filename"]
        assert "test_180_225" not in m["audio_filename"]
        assert "holdout_300_345" not in m["audio_filename"]

def test_hybrid_v3_accuracy_on_independent_speakers(eval_data):
    manifest, results, predictions = eval_data
    systems = results["systems_evaluated"]
    hybrid = systems["Hybrid ASR V3 (Accuracy-First)"]
    # Verify Hybrid V3 outperforms standalone Whisper Turbo and Specialized Whisper
    assert hybrid["micro_wer"] <= 35.0, f"Expected Hybrid V3 micro WER <= 35%, got {hybrid['micro_wer']}%"
    assert hybrid["micro_wer"] < systems["Whisper Large-v3-Turbo"]["micro_wer"]
    assert hybrid["micro_wer"] < systems["Specialized Whisper Medium"]["micro_wer"]

def test_hybrid_v3_suppresses_pathological_hallucinations(eval_data):
    manifest, results, predictions = eval_data
    # In mgb3_fashion14_18, Specialized Whisper had a 30+ word 'اشترك في القناة' loop
    spec_text = predictions["mgb3_fashion14_18"]["codeswitched-medium"]["text"]
    assert "اشترك في القناة" in spec_text
    
    # Hybrid V3 must completely eliminate the loop
    hybrid_text = predictions["mgb3_fashion14_18"]["hybrid-v3"]["text"]
    assert "اشترك في القناة" not in hybrid_text
    
    # In mgb3_cooking24_10, Specialized Whisper had a massive 'ترجع' loop
    spec_text_cooking = predictions["mgb3_cooking24_10"]["codeswitched-medium"]["text"]
    assert spec_text_cooking.count("ترجع") > 20
    hybrid_text_cooking = predictions["mgb3_cooking24_10"]["hybrid-v3"]["text"]
    assert hybrid_text_cooking.count("ترجع") <= 1

def test_code_switching_accuracy_priority(eval_data):
    manifest, results, predictions = eval_data
    systems = results["systems_evaluated"]
    hybrid = systems["Hybrid ASR V3 (Accuracy-First)"]
    cs_cat = hybrid["categories"]["CAT_B_CODESWITCH"]
    # Code-switching micro WER should be around ~20%
    assert cs_cat["micro_wer"] <= 25.0, f"Expected CS micro WER <= 25%, got {cs_cat['micro_wer']}%"

def test_genuine_repetition_preservation(eval_data):
    manifest, results, predictions = eval_data
    # cs_rg1_repetition_22 contains 'أخر أخر'
    hybrid_text = predictions["cs_rg1_repetition_22"]["hybrid-v3"]["text"]
    assert "أخر أخر" in hybrid_text or "آخر آخر" in hybrid_text
