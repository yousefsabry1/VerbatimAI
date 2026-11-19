from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["app"] == "Verbatim AI"


def test_api_hardware():
    res = client.get("/api/hardware")
    assert res.status_code == 200
    data = res.json()
    assert "cpu_cores" in data
    assert "cuda_available" in data
    assert "recommended" in data


def test_api_models():
    res = client.get("/api/models")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data
    model_ids = [m["id"] for m in data["models"]]
    assert "codeswitched-medium" in model_ids
    assert "large-v3-turbo" in model_ids


def test_api_benchmark_reference():
    res = client.get("/api/benchmark/reference")
    assert res.status_code == 200
    data = res.json()
    assert "has_reference" in data
    assert "raw_text" in data


def test_api_benchmark_live_align():
    res = client.post("/api/benchmark/align", json={
        "reference_text": "مساء الفل يا صبري",
        "hypothesis_text": "مساء الفل يا صبري",
        "eval_mode": "normalized"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["metrics"]["wer_percent"] == 0.0
    assert data["metrics"]["hits"] == 4


def test_api_conversion_formats():
    res = client.get("/api/conversion/formats")
    assert res.status_code == 200
    data = res.json()
    assert "mp3" in data["formats"]
    assert "wav" in data["formats"]
    assert len(data["presets"]) >= 3
