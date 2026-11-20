import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.api.benchmark import BENCHMARK_DIR, SAMPLE_CONFIGS

client = TestClient(app)


def test_list_source_recordings():
    """Verify source recordings from history are listed with duration and format."""
    res = client.get("/api/benchmark/source-recordings")
    assert res.status_code == 200
    data = res.json()
    assert "recordings" in data
    recordings = data["recordings"]
    assert len(recordings) > 0

    # Ensure new dd.ogg is discovered
    found_new_dd = any("new dd.ogg" in r["filename"] for r in recordings)
    assert found_new_dd, "Recording 'new dd.ogg' must be discoverable in source recordings catalog"


def test_preview_source_interval():
    """Verify audio preview extraction works for valid intervals and rejects invalid boundaries."""
    # 1. Get first available recording
    recs_res = client.get("/api/benchmark/source-recordings")
    rec = recs_res.json()["recordings"][0]

    # 2. Valid preview
    prev_res = client.get(
        f"/api/benchmark/preview-source?source_path_or_id={rec['job_id']}&start_time=5.0&end_time=15.0"
    )
    assert prev_res.status_code == 200
    assert prev_res.headers.get("content-type") == "audio/wav"
    assert len(prev_res.content) > 1000

    # 3. Invalid: end_time <= start_time
    inv_res = client.get(
        f"/api/benchmark/preview-source?source_path_or_id={rec['job_id']}&start_time=15.0&end_time=10.0"
    )
    assert inv_res.status_code == 400


def test_dynamic_benchmark_sample_lifecycle():
    """Complete dynamic sample lifecycle: create -> verify initial state -> stream audio -> save reference -> delete."""
    # 1. Identify new dd.ogg or first valid recording
    recs_res = client.get("/api/benchmark/source-recordings")
    recordings = recs_res.json()["recordings"]
    target_rec = next((r for r in recordings if "new dd.ogg" in r["filename"]), recordings[0])

    # 2. Test boundary validation: end_time > total duration
    bad_res = client.post("/api/benchmark/sample", json={
        "name": "Invalid Sample",
        "source_path_or_id": target_rec["job_id"],
        "start_time": 0.0,
        "end_time": target_rec["duration"] + 100.0,
    })
    assert bad_res.status_code == 400

    # 3. Test boundary validation: interval too short
    short_res = client.post("/api/benchmark/sample", json={
        "name": "Too Short Sample",
        "source_path_or_id": target_rec["job_id"],
        "start_time": 10.0,
        "end_time": 10.5,
    })
    assert short_res.status_code == 400

    # 4. Create valid dynamic benchmark sample
    create_res = client.post("/api/benchmark/sample", json={
        "name": "E2E Test Evaluation Interval (00:30 - 01:15)",
        "source_path_or_id": target_rec["job_id"],
        "start_time": 30.0,
        "end_time": 75.0,
        "description": "Integration test dynamic benchmark sample from new dd.ogg",
    })
    assert create_res.status_code == 200
    create_data = create_res.json()
    assert create_data["status"] == "created"
    sample = create_data["sample"]
    sample_id = sample["sample_id"]
    assert sample["is_dynamic"] is True
    assert sample["status"] == "UNVERIFIED"
    assert sample["duration"] == 45.0

    # 5. Verify sample appears in catalog alongside predefined samples
    cat_res = client.get("/api/benchmark/samples")
    assert cat_res.status_code == 200
    catalog = cat_res.json()["samples"]
    cat_ids = [s["sample_id"] for s in catalog]
    assert "dev_0_103" in cat_ids
    assert "test_180_225" in cat_ids
    assert "holdout_300_345" in cat_ids
    assert "eval_400_445" in cat_ids
    assert sample_id in cat_ids

    # 6. Verify isolated WAV file streaming
    audio_res = client.get(f"/api/benchmark/audio/{sample_id}")
    assert audio_res.status_code == 200
    assert audio_res.headers.get("content-type") == "audio/wav"
    assert len(audio_res.content) > 1000

    # 7. Verify reference starts completely empty (zero AI contamination)
    ref_res = client.get(f"/api/benchmark/reference?sample_id={sample_id}")
    assert ref_res.status_code == 200
    ref_data = ref_res.json()
    assert ref_data["raw_text"] == ""
    assert ref_data["is_human_verified"] is False
    assert ref_data["verification_status"] == "NO_REFERENCE"

    # 8. Save draft reference
    draft_res = client.post("/api/benchmark/reference", json={
        "sample_id": sample_id,
        "reference_text": "دي مسوده تجريبيه لاختبار العينات الديناميكيه",
        "action": "save_draft",
    })
    assert draft_res.status_code == 200
    assert draft_res.json()["is_human_verified"] is False
    assert draft_res.json()["verification_status"] == "DRAFT"

    # 9. Certify human reference
    cert_res = client.post("/api/benchmark/reference", json={
        "sample_id": sample_id,
        "reference_text": "دي مسوده تجريبيه لاختبار العينات الديناميكيه معتمده",
        "action": "save_and_verify",
        "is_human_verified": True,
        "verification_statement": "Manual human verification from audio.",
    })
    assert cert_res.status_code == 200
    assert cert_res.json()["is_human_verified"] is True
    assert cert_res.json()["verification_status"] == "HUMAN_VERIFIED"

    # 10. Verify cannot delete static sample
    del_static = client.delete("/api/benchmark/sample/dev_0_103")
    assert del_static.status_code == 400

    # 11. Delete dynamic sample
    del_res = client.delete(f"/api/benchmark/sample/{sample_id}")
    assert del_res.status_code == 200

    # Verify removed from catalog
    cat_after = client.get("/api/benchmark/samples").json()["samples"]
    assert sample_id not in [s["sample_id"] for s in cat_after]
