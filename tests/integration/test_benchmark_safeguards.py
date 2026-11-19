import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_benchmark_samples():
    response = client.get("/api/benchmark/samples")
    assert response.status_code == 200
    data = response.json()
    assert "samples" in data
    assert len(data["samples"]) >= 2

    # Check dev sample
    dev = next((s for s in data["samples"] if s["sample_id"] == "dev_0_103"), None)
    assert dev is not None
    assert dev["status"] == "VERIFIED"
    assert dev["word_count"] == 203

    # Check test sample
    test_samp = next((s for s in data["samples"] if s["sample_id"] == "test_180_225"), None)
    assert test_samp is not None
    assert test_samp["duration"] == 45.0
    assert test_samp["status"] == "VERIFIED"
    assert test_samp["word_count"] == 111


def test_verified_test_sample_reference_status():
    response = client.get("/api/benchmark/reference?sample_id=test_180_225")
    assert response.status_code == 200
    data = response.json()
    assert data["sample_id"] == "test_180_225"
    assert data["is_human_verified"] is True
    assert data["word_count_raw"] == 111


def test_verified_dev_sample_reference_status():
    response = client.get("/api/benchmark/reference?sample_id=dev_0_103")
    assert response.status_code == 200
    data = response.json()
    assert data["sample_id"] == "dev_0_103"
    assert data["is_human_verified"] is True
    assert data["word_count_raw"] == 203


def test_benchmark_audio_streaming():
    response = client.get("/api/benchmark/audio/test_180_225")
    assert response.status_code == 200
    assert response.headers.get("accept-ranges") == "bytes"
    assert "audio/" in response.headers.get("content-type", "")
    assert len(response.content) > 100000  # 45s WAV is ~1.4MB
