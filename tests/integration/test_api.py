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
    assert len(data["models"]) >= 3


def test_api_conversion_formats():
    res = client.get("/api/conversion/formats")
    assert res.status_code == 200
    data = res.json()
    assert "mp3" in data["formats"]
    assert "wav" in data["formats"]
    assert len(data["presets"]) >= 3
