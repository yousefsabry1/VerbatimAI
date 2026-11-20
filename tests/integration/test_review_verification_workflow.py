"""
Test Review Verification Workflow, Diff Engine, Suspicious Detector, and Review APIs.
"""
import pytest
import os
import tempfile
import wave
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.evaluation.diff_engine import compute_transcript_diff, tokenize_mixed_text
from app.transcription.suspicious_detector import detect_suspicious_segments
from app.audio.segment_extractor import extract_audio_slice
from app.core.database import (
    save_alternative_hypothesis,
    get_alternative_hypotheses,
    save_segment_review,
    get_segment_reviews,
)

client = TestClient(app)


def test_diff_engine_tokenization_and_alignment():
    # Egyptian Arabic + English code-switching
    primary = "إحنا شغالين على الـ backend والـ frontend مع بعض"
    alt = "احنا شغالين على ال backend والـ frontend سوا"

    diff_res = compute_transcript_diff(primary, alt)
    assert "chunks" in diff_res
    assert "disagreement_score" in diff_res
    assert isinstance(diff_res["disagreement_score"], float)
    assert 0.0 <= diff_res["disagreement_score"] <= 1.0

    # Ensure tokens are parsed cleanly
    tokens = tokenize_mixed_text(primary)
    assert "backend" in tokens
    assert "frontend" in tokens
    assert len(tokens) >= 7


def test_suspicious_detector_signals():
    segments = [
        {"id": 1, "start": 0.0, "end": 4.0, "text": "صباح الخير يا شباب", "avg_logprob": -0.2, "confidence": 0.95},
        {"id": 2, "start": 4.0, "end": 8.0, "text": "أنا سامع صوت وش في المايك", "avg_logprob": -1.8, "confidence": 0.35},  # low conf
        {"id": 3, "start": 15.0, "end": 20.0, "text": "تمام تمام تمام تمام تمام تمام تمام تمام تمام تمام", "avg_logprob": -0.3, "confidence": 0.88},  # repetition
        {"id": 4, "start": 28.0, "end": 32.0, "text": "نكمل على طول", "avg_logprob": -0.2, "confidence": 0.92},  # gap from 20.0 to 28.0 (8s)
    ]

    diagnostics = detect_suspicious_segments(segments, alternative_hypotheses=[], reviews_map={})
    assert len(diagnostics) == 4

    # Segment 1: clean
    assert not diagnostics[0]["is_flagged"]

    # Segment 2: low confidence
    assert diagnostics[1]["is_flagged"]
    assert any("confidence" in r.lower() or "logprob" in r.lower() for r in diagnostics[1]["flag_reasons"])

    # Segment 3: repetition loop
    assert diagnostics[2]["is_flagged"]
    assert any("repetition" in r.lower() for r in diagnostics[2]["flag_reasons"])

    # Segment 4: timing gap before it (8 seconds gap)
    assert diagnostics[3]["is_flagged"]
    assert any("gap" in r.lower() for r in diagnostics[3]["flag_reasons"])


def test_audio_segment_extractor_clamping():
    # Create a dummy 5-second 16kHz mono audio file using standard library wave
    sr = 16000
    duration = 5.0
    num_frames = int(sr * duration)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_audio_path = f.name

    try:
        with wave.open(temp_audio_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(b'\x00\x00' * num_frames)

        # Slice 1.0 to 3.0 with 2.0s context padding
        # Clamped should be start: max(0, 1.0 - 2.0) = 0.0, end: min(5.0, 3.0 + 2.0) = 5.0
        out_wav_path, clamped_start, clamped_end = extract_audio_slice(
            source_audio_path=Path(temp_audio_path),
            start=1.0,
            end=3.0,
            padding=2.0,
        )

        assert clamped_start == 0.0
        assert clamped_end == 5.0
        assert out_wav_path.exists()

        # Verify output audio file is readable with wave
        with wave.open(str(out_wav_path), 'rb') as out_wf:
            assert out_wf.getframerate() == 16000
            assert out_wf.getnchannels() == 1

        # Clean up sliced file
        if out_wav_path.exists():
            out_wav_path.unlink()
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)


def test_database_review_crud_operations():
    test_job_id = "test_job_integration_review_999"
    seg_id = 42

    # 1. Save and retrieve alternative hypothesis
    hyp_id = save_alternative_hypothesis(
        hypothesis_id="test_hyp_int_999",
        job_id=test_job_id,
        segment_id=seg_id,
        model_id="qwencleo-asr-4bit",
        model_name="QwenCleo-ASR 1.7B 4-bit NF4",
        start_time=12.0,
        end_time=15.0,
        extracted_start=11.0,
        extracted_end=16.0,
        context_padding=1.0,
        hypothesis_text="تجربة نموذج بديل للتحقق",
        cleaned_hypothesis="تجربة نموذج بديل للتحقق",
        primary_text="تجربة نموذج اولي",
        diff_data=[{"type": "substitute", "primary": "اولي", "alternative": "بديل للتحقق"}],
        disagreement_score=0.45,
        device_used="cuda",
        compute_used="int8_float16",
        elapsed_seconds=3.2,
    )
    assert hyp_id == "test_hyp_int_999"

    hyps = get_alternative_hypotheses(test_job_id, seg_id)
    assert len(hyps) >= 1
    assert hyps[0]["model_id"] == "qwencleo-asr-4bit"
    assert hyps[0]["disagreement_score"] == 0.45

    # 2. Save and retrieve segment review status
    rev_id = save_segment_review(
        job_id=test_job_id,
        segment_id=seg_id,
        review_status="human_reviewed",
        flag_reasons=["low_confidence"],
        selected_alternative_id=hyp_id,
        human_notes="Approved with alternative suggestion",
    )
    assert rev_id is not None

    reviews = get_segment_reviews(test_job_id)
    assert seg_id in reviews
    assert reviews[seg_id]["review_status"] == "human_reviewed"
    assert reviews[seg_id]["human_notes"] == "Approved with alternative suggestion"


def test_review_status_api_endpoint():
    # Test updating status via API
    test_job_id = "818483f608"  # existing completed job in db
    res = client.post(
        f"/api/review/{test_job_id}/segment/1/status",
        json={
            "review_status": "human_reviewed",
            "flag_reasons": ["manual_approval"],
            "human_notes": "Verified by QA test",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["review_status"] == "human_reviewed"

    # Query reviews for this job
    rev_res = client.get(f"/api/review/{test_job_id}/reviews")
    assert rev_res.status_code == 200
    catalog = rev_res.json()
    assert catalog["job_id"] == test_job_id
    assert "total_segments" in catalog
    assert "flagged_count" in catalog
    assert "reviewed_count" in catalog
    assert len(catalog["items"]) == catalog["total_segments"]

    # Check segment 1 review item
    seg1 = next((item for item in catalog["items"] if item["segment_id"] == 1), None)
    assert seg1 is not None
    assert seg1["review_status"] == "human_reviewed"
