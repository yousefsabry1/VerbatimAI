import os
import json
import pytest
import shutil
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.api.benchmark import SAMPLE_CONFIGS, BENCHMARK_DIR

client = TestClient(app)


@pytest.fixture
def isolated_benchmark_env(tmp_path, monkeypatch):
    """
    Creates an isolated copy of the benchmark directory for testing
    to protect actual user files and references from test mutations.
    """
    test_bench_dir = tmp_path / "benchmarks"
    test_bench_dir.mkdir(parents=True, exist_ok=True)

    # Copy files from real BENCHMARK_DIR to test_bench_dir
    for item in BENCHMARK_DIR.glob("*.*"):
        if item.is_file() and not item.name.endswith(".wav"):
            shutil.copy2(item, test_bench_dir / item.name)

    # Patch paths in SAMPLE_CONFIGS
    patched_configs = {}
    for s_id, cfg in SAMPLE_CONFIGS.items():
        c = dict(cfg)
        c["ref_file"] = test_bench_dir / cfg["ref_file"].name
        c["results_file"] = test_bench_dir / cfg["results_file"].name
        c["meta_file"] = test_bench_dir / cfg["meta_file"].name
        # Keep real audio file pointers
        patched_configs[s_id] = c

    monkeypatch.setattr("app.api.benchmark.BENCHMARK_DIR", test_bench_dir)
    monkeypatch.setattr("app.api.benchmark.SAMPLE_CONFIGS", patched_configs)
    return test_bench_dir, patched_configs


def test_get_benchmark_samples_catalog(isolated_benchmark_env):
    """Verifies that all 3 canonical samples are registered and have expected metadata."""
    res = client.get("/api/benchmark/samples")
    assert res.status_code == 200
    data = res.json()
    assert "samples" in data
    assert len(data["samples"]) >= 3

    ids = [s["sample_id"] for s in data["samples"]]
    assert "dev_0_103" in ids
    assert "test_180_225" in ids
    assert "holdout_300_345" in ids
    assert "eval_400_445" in ids


def test_reject_empty_reference(isolated_benchmark_env):
    """Requirements 5: Reject saving an empty reference."""
    res = client.post("/api/benchmark/reference", json={
        "sample_id": "holdout_300_345",
        "reference_text": "   ",
        "action": "save_draft",
    })
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_save_reference_draft_workflow(isolated_benchmark_env):
    """Requirements 1, 2, 10, 12: Save reference as draft, verify status and suppression of WER."""
    test_bench_dir, configs = isolated_benchmark_env
    draft_text = "دي تجربه لكتابه مرجع مسوده بدون توثيق بشري"

    # Save as draft
    res = client.post("/api/benchmark/reference", json={
        "sample_id": "holdout_300_345",
        "reference_text": draft_text,
        "action": "save_draft",
        "is_human_verified": False,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["is_human_verified"] is False
    assert data["verification_status"] == "DRAFT"
    assert data["word_count"] == len(draft_text.split())

    # Retrieve reference and check persistence
    get_res = client.get("/api/benchmark/reference?sample_id=holdout_300_345")
    assert get_res.status_code == 200
    ref_data = get_res.json()
    assert ref_data["raw_text"] == draft_text
    assert ref_data["is_human_verified"] is False
    assert ref_data["verification_status"] == "DRAFT"
    assert ref_data["has_reference"] is True


def test_reject_verification_without_explicit_certification(isolated_benchmark_env):
    """Requirement 4: Reject save_and_verify when certification checkbox is false."""
    res = client.post("/api/benchmark/reference", json={
        "sample_id": "holdout_300_345",
        "reference_text": "نص بدون تعليم صندوق التوثيق",
        "action": "save_and_verify",
        "is_human_verified": False,
    })
    assert res.status_code == 400
    assert "certify" in res.json()["detail"].lower()


def test_explicit_human_verification_and_persistence(isolated_benchmark_env):
    """Requirements 3, 6, 9: Save and explicitly certify human reference."""
    verified_text = "المسرح بتاعها ان هو يهوست الايفنت نفسه وال accessibility تمام"

    res = client.post("/api/benchmark/reference", json={
        "sample_id": "holdout_300_345",
        "reference_text": verified_text,
        "action": "save_and_verify",
        "is_human_verified": True,
        "verification_statement": "I confirm that I personally listened to the audio and manually verified this transcript.",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["is_human_verified"] is True
    assert data["verification_status"] == "HUMAN_VERIFIED"
    assert "reference_revision" in data

    # Verify retrieval
    get_res = client.get("/api/benchmark/reference?sample_id=holdout_300_345")
    assert get_res.status_code == 200
    ref_data = get_res.json()
    assert ref_data["is_human_verified"] is True
    assert ref_data["verification_status"] == "HUMAN_VERIFIED"
    assert ref_data["raw_text"] == verified_text


def test_updating_verified_reference_invalidates_metrics(isolated_benchmark_env):
    """Requirements 7, 8: Editing a verified reference as draft invalidates metrics."""
    test_bench_dir, configs = isolated_benchmark_env

    # 1. First save as verified
    client.post("/api/benchmark/reference", json={
        "sample_id": "holdout_300_345",
        "reference_text": "النص الاول موثق تماما",
        "action": "save_and_verify",
        "is_human_verified": True,
    })

    # 2. Simulate existing results in results_file
    results_file = configs["holdout_300_345"]["results_file"]
    results_file.write_text(json.dumps([
        {
            "model_id": "codeswitched-medium",
            "name": "Egyptian Arabic & English (Specialized)",
            "status": "success",
            "predicted_text": "النص الاول موثق تماما",
            "is_verified": True,
            "norm_wer": 0.0,
        }
    ]), encoding="utf-8")

    # 3. User edits reference as draft
    edit_res = client.post("/api/benchmark/reference", json={
        "sample_id": "holdout_300_345",
        "reference_text": "النص المعدل كمسوده غير موثقه",
        "action": "save_draft",
        "is_human_verified": False,
    })
    assert edit_res.status_code == 200

    # 4. Check that results_file now has metrics invalidated (None)
    saved_runs = json.loads(results_file.read_text(encoding="utf-8"))
    assert saved_runs[0]["is_verified"] is False
    assert saved_runs[0]["norm_wer"] is None


def test_calculate_accuracy_from_cached_predictions(isolated_benchmark_env):
    """Requirements 11, 16, 17: Recalculate WER/CER from cached predictions without running models."""
    test_bench_dir, configs = isolated_benchmark_env

    # 1. Establish verified reference
    ref_text = "المسرح بتاعها ان هو يهوست الايفنت نفسه والجامعه توفر شهادات"
    client.post("/api/benchmark/reference", json={
        "sample_id": "holdout_300_345",
        "reference_text": ref_text,
        "action": "save_and_verify",
        "is_human_verified": True,
    })

    # 2. Inject cached predictions (simulating prior model run while unverified)
    results_file = configs["holdout_300_345"]["results_file"]
    results_file.write_text(json.dumps([
        {
            "model_id": "codeswitched-medium",
            "name": "Egyptian Arabic & English (Specialized)",
            "status": "success",
            "predicted_text": "المسرح بتاعها ان هو يهوست الايفنت نفسه والجامعه توفر شهادات للطلبه",
            "is_verified": False,
            "norm_wer": None,
            "norm_cer": None,
        }
    ]), encoding="utf-8")

    # 3. Call calculate-accuracy endpoint
    calc_res = client.post("/api/benchmark/calculate-accuracy", json={
        "sample_id": "holdout_300_345",
        "eval_mode": "normalized",
    })
    assert calc_res.status_code == 200
    data = calc_res.json()
    assert data["status"] == "success"
    assert data["is_human_verified"] is True
    assert data["evaluated_models"] == 1
    assert data["results"][0]["is_verified"] is True
    assert isinstance(data["results"][0]["norm_wer"], float)
    assert data["results"][0]["norm_wer"] >= 0.0


def test_calculate_accuracy_rejected_if_unverified(isolated_benchmark_env):
    """Requirement 12: Cannot calculate accuracy if reference is draft."""
    client.post("/api/benchmark/reference", json={
        "sample_id": "holdout_300_345",
        "reference_text": "مسودة غير موثقة",
        "action": "save_draft",
        "is_human_verified": False,
    })

    calc_res = client.post("/api/benchmark/calculate-accuracy", json={
        "sample_id": "holdout_300_345",
        "eval_mode": "normalized",
    })
    assert calc_res.status_code == 400
    assert "draft" in calc_res.json()["detail"].lower()


def test_reject_cross_sample_and_unknown_sample(isolated_benchmark_env):
    """Requirements 13, 14, 19: Reject unknown sample ID."""
    res = client.get("/api/benchmark/reference?sample_id=invalid_sample_xyz")
    assert res.status_code == 404

    post_res = client.post("/api/benchmark/calculate-accuracy", json={
        "sample_id": "nonexistent_sample",
    })
    assert post_res.status_code == 404


def test_results_endpoint_enforces_sample_identity(isolated_benchmark_env):
    """Requirements 13, 15: Results endpoint enforces canonical sample ID and returns sample_name."""
    test_bench_dir, configs = isolated_benchmark_env

    res = client.get("/api/benchmark/results?sample_id=holdout_300_345")
    assert res.status_code == 200
    data = res.json()
    assert data["sample_id"] == "holdout_300_345"
    assert "sample_name" in data
    assert "results" in data
    for r in data["results"]:
        assert r["sample_id"] == "holdout_300_345"


def test_qwencleo_experimental_model_registration_and_safeguards(isolated_benchmark_env):
    """
    Verifies that QwenCleo 4-bit is registered as an experimental benchmark-only model,
    auto-download is safely prevented, and it is recognized as locally ready.
    """
    # 1. Models catalog check
    res = client.get("/api/models")
    assert res.status_code == 200
    models = res.json()["models"]
    qwen = next((m for m in models if m["id"] == "qwencleo-asr-4bit"), None)
    assert qwen is not None
    assert qwen["is_experimental"] is True
    assert qwen["benchmark_only"] is True
    assert qwen["is_downloaded"] is True

    # 2. Download endpoint must reject auto-download for experimental models
    from app.transcription.engine import download_model
    with pytest.raises(RuntimeError) as exc_info:
        download_model("qwencleo-asr-4bit")
    assert "auto-download is disabled" in str(exc_info.value).lower()

