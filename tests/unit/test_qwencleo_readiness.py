"""
VerbatimAI - Unit Tests for QwenCleo Readiness & Tier Reporting
Verifies:
1. Structured diagnostics returned by check_qwencleo_readiness()
2. Hybrid V3 operational tier exposure in /api/models
3. Strict user-consent enforcement on POST /api/models/qwencleo-asr-4bit/setup
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.models import check_qwencleo_readiness, get_gpu_hardware_info
from app.transcription.hybrid_orchestrator import check_qwencleo_availability

client = TestClient(app)


def test_get_gpu_hardware_info():
    info = get_gpu_hardware_info()
    assert isinstance(info, dict)
    assert "has_cuda" in info
    assert "gpu_name" in info
    assert "vram_mb" in info
    assert isinstance(info["has_cuda"], bool)


def test_check_qwencleo_readiness_schema():
    readiness = check_qwencleo_readiness()
    assert isinstance(readiness, dict)
    required_keys = [
        "ready",
        "environment_ready",
        "model_downloaded",
        "gpu_supported",
        "vram_mb",
        "status",
        "reason",
        "disk_requirement_gb",
        "vram_requirement_mb",
    ]
    for k in required_keys:
        assert k in readiness, f"Missing key '{k}' in readiness dict"

    assert isinstance(readiness["ready"], bool)
    assert isinstance(readiness["environment_ready"], bool)
    assert isinstance(readiness["model_downloaded"], bool)
    assert isinstance(readiness["gpu_supported"], bool)
    assert readiness["disk_requirement_gb"] >= 6.0
    assert readiness["vram_requirement_mb"] >= 3500


def test_check_qwencleo_status_endpoint():
    res = client.get("/api/models/qwencleo/status")
    assert res.status_code == 200
    data = res.json()
    assert "ready" in data
    assert "status" in data
    assert "reason" in data


def test_list_models_hybrid_readiness_exposure():
    res = client.get("/api/models")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data

    hv3 = next((m for m in data["models"] if m["id"] == "hybrid-v3"), None)
    assert hv3 is not None, "hybrid-v3 model must be exposed"
    assert "hybrid_readiness" in hv3, "hybrid_readiness metadata must be present"

    h_readiness = hv3["hybrid_readiness"]
    assert h_readiness["tier"] in ("needs_download", "dual_model_consensus", "full_tri_model")
    assert "tier_label" in h_readiness
    assert "twin_models_ready" in h_readiness
    assert "qwencleo_ready" in h_readiness


def test_setup_qwencleo_rejects_without_explicit_confirmation():
    # Attempting setup without confirm_download=True must return 400 Bad Request
    res = client.post("/api/models/qwencleo-asr-4bit/setup", json={"confirm_download": False})
    assert res.status_code == 400
    err_detail = res.json().get("detail", {})
    assert "explicit user confirmation" in str(err_detail).lower() or "confirm_download" in str(err_detail).lower()


def test_check_qwencleo_availability_matches():
    avail = check_qwencleo_availability()
    readiness = check_qwencleo_readiness()
    assert avail["ready"] == readiness["ready"]
    assert avail["status"] == readiness["status"]
