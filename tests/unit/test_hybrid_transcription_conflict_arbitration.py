"""
VerbatimAI - Unit Tests for Conflict-Triggered QwenCleo Arbitration & Truthful Reporting
Verifies:
1. When conflict is detected and QwenCleo is unconfigured:
   - Graceful fallback to dual-model consensus
   - hybrid_tier is truthfully reported as "dual_model_consensus"
   - models_participated contains ONLY ["codeswitched-medium", "large-v3-turbo"]
   - qwen_status documents unconfigured resolution reason
2. When conflict is detected and QwenCleo runs successfully:
   - hybrid_tier is reported as "full_tri_model"
   - models_participated contains all 3 models
   - qwen_status is "invoked_and_adjudicated"
3. When models agree (no conflict):
   - QwenCleo is skipped
   - qwen_status is "skipped_high_agreement"
   - hybrid_tier is "dual_model_consensus"
"""

import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from app.core.config import STORAGE_DIR
from app.transcription.hybrid_orchestrator import run_hybrid_transcription


class DummySegment:
    def __init__(self, text, start=0.0, end=2.0):
        self.text = text
        self.start = start
        self.end = end


class DummyWhisperModel:
    def __init__(self, segments):
        self._segments = segments

    def transcribe(self, *args, **kwargs):
        return iter(self._segments), None


@pytest.fixture
def mock_twin_models_conflict():
    """Generates a code-switch conflict between specialized and turbo."""
    # Specialized: has English code-switching
    spec_segs = [DummySegment("احنا عايزين ال logo بتاع ال CIS ده", 0.0, 3.0)]
    # Turbo: has transliteration / mismatch
    turbo_segs = [DummySegment("احنا عايزين ترجمة نانسي قنقر نفسه ده", 0.0, 3.0)]
    return spec_segs, turbo_segs


@pytest.fixture
def mock_twin_models_agreement():
    """Generates strong agreement between specialized and turbo."""
    spec_segs = [DummySegment("صباح الخير يا فندم أهلا بيك", 0.0, 2.0)]
    turbo_segs = [DummySegment("صباح الخير يا فندم اهلا بيك", 0.0, 2.0)]
    return spec_segs, turbo_segs


def test_conflict_with_qwen_unconfigured_fallback_truthful(tmp_path, mock_twin_models_conflict):
    """When conflict occurs but QwenCleo is unconfigured, truthfully report dual-model execution."""
    spec_segs, turbo_segs = mock_twin_models_conflict
    audio_path = STORAGE_DIR / "benchmarks" / "test_slice_0_12.wav"
    job_id = f"test_truth_{uuid.uuid4().hex[:6]}"
    job_dir = tmp_path / f"job_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)

    dummy_meta = {
        "duration": 3.0,
        "duration_formatted": "00:03",
        "sha256": "fakehash123",
    }

    mock_avail = {
        "ready": False,
        "status": "env_missing",
        "reason": "Isolated experimental_venv missing",
    }

    with patch("app.transcription.hybrid_orchestrator.is_model_downloaded", return_value=True), \
         patch("app.transcription.hybrid_orchestrator.load_whisper_model") as mock_load, \
         patch("app.transcription.hybrid_orchestrator.check_qwencleo_availability", return_value=mock_avail):

        # Return spec model on first call, turbo model on second call
        mock_load.side_effect = [
            (DummyWhisperModel(spec_segs), "cuda", "float16"),
            (DummyWhisperModel(turbo_segs), "cuda", "float16"),
        ]

        result = run_hybrid_transcription(
            input_path=audio_path,
            job_id=job_id,
            job_dir=job_dir,
            source_meta=dummy_meta,
            model_id="hybrid-v3",
        )

        meta = result["metadata"]["hybrid_metadata"]
        assert meta["code_switch_conflict_detected"] is True
        assert meta["qwen_invoked"] is False
        assert meta["hybrid_tier"] == "dual_model_consensus", "Must report dual_model_consensus when Qwen did not run"
        assert meta["models_participated"] == ["codeswitched-medium", "large-v3-turbo"], "Must list only models that ran"
        assert "unconfigured_dual_model_resolution" in meta["qwen_status"]


def test_conflict_with_qwen_adjudicated_truthful(tmp_path, mock_twin_models_conflict):
    """When conflict occurs and QwenCleo adjudicates, report full tri-model execution."""
    spec_segs, turbo_segs = mock_twin_models_conflict
    audio_path = STORAGE_DIR / "benchmarks" / "test_slice_0_12.wav"
    job_id = f"test_qwen_{uuid.uuid4().hex[:6]}"
    job_dir = tmp_path / f"job_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)

    dummy_meta = {
        "duration": 3.0,
        "duration_formatted": "00:03",
        "sha256": "fakehash456",
    }

    mock_avail = {
        "ready": True,
        "status": "ready",
        "reason": "QwenCleo ready on GPU",
    }

    mock_qwen_res = {
        "status": "ok",
        "text": "احنا عايزين اللوجو بتاع ال CIS ده",
        "peak_vram_mb": 2100.0,
    }

    with patch("app.transcription.hybrid_orchestrator.is_model_downloaded", return_value=True), \
         patch("app.transcription.hybrid_orchestrator.load_whisper_model") as mock_load, \
         patch("app.transcription.hybrid_orchestrator.check_qwencleo_availability", return_value=mock_avail), \
         patch("app.api.benchmark.run_qwencleo_benchmark", return_value=mock_qwen_res):

        mock_load.side_effect = [
            (DummyWhisperModel(spec_segs), "cuda", "float16"),
            (DummyWhisperModel(turbo_segs), "cuda", "float16"),
        ]

        result = run_hybrid_transcription(
            input_path=audio_path,
            job_id=job_id,
            job_dir=job_dir,
            source_meta=dummy_meta,
            model_id="hybrid-v3",
        )

        meta = result["metadata"]["hybrid_metadata"]
        assert meta["code_switch_conflict_detected"] is True
        assert meta["qwen_invoked"] is True
        assert meta["hybrid_tier"] == "full_tri_model", "Must report full_tri_model when Qwen adjudicated"
        assert meta["models_participated"] == ["codeswitched-medium", "large-v3-turbo", "qwencleo-asr-4bit"]
        assert meta["qwen_status"] == "invoked_and_adjudicated"


def test_high_agreement_skips_qwen_truthful(tmp_path, mock_twin_models_agreement):
    """When twin models agree, QwenCleo is safely skipped and reported truthfully."""
    spec_segs, turbo_segs = mock_twin_models_agreement
    audio_path = STORAGE_DIR / "benchmarks" / "test_slice_0_12.wav"
    job_id = f"test_agree_{uuid.uuid4().hex[:6]}"
    job_dir = tmp_path / f"job_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)

    dummy_meta = {
        "duration": 2.0,
        "duration_formatted": "00:02",
        "sha256": "fakehash789",
    }

    mock_avail = {
        "ready": True,
        "status": "ready",
        "reason": "QwenCleo ready on GPU",
    }

    with patch("app.transcription.hybrid_orchestrator.is_model_downloaded", return_value=True), \
         patch("app.transcription.hybrid_orchestrator.load_whisper_model") as mock_load, \
         patch("app.transcription.hybrid_orchestrator.check_qwencleo_availability", return_value=mock_avail):

        mock_load.side_effect = [
            (DummyWhisperModel(spec_segs), "cuda", "float16"),
            (DummyWhisperModel(turbo_segs), "cuda", "float16"),
        ]

        result = run_hybrid_transcription(
            input_path=audio_path,
            job_id=job_id,
            job_dir=job_dir,
            source_meta=dummy_meta,
            model_id="hybrid-v3",
        )

        meta = result["metadata"]["hybrid_metadata"]
        assert meta["code_switch_conflict_detected"] is False
        assert meta["qwen_invoked"] is False
        assert meta["hybrid_tier"] == "dual_model_consensus"
        assert meta["models_participated"] == ["codeswitched-medium", "large-v3-turbo"]
        assert meta["qwen_status"] == "skipped_high_agreement"
