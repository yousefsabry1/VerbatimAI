import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import create_job, save_transcript, complete_job

client = TestClient(app)


@pytest.fixture
def sample_review_job():
    job_id = f"test_rev_{uuid.uuid4().hex[:8]}"
    create_job({
        "id": job_id,
        "job_type": "transcription",
        "input_filename": "test_audio.ogg",
        "input_path": "A:/dummy/test_audio.ogg",
        "input_duration": 10.0,
        "model_used": "codeswitched-medium",
        "language": "ar",
        "device_used": "cuda",
        "compute_used": "int8_float16",
        "status": "completed",
        "progress": 1.0,
        "stage": "Completed",
    })
    complete_job(job_id, output_files={})

    original_segments = [
        {
            "id": 1,
            "start": 0.0,
            "end": 3.5,
            "text": "بس هي فول صبي",
            "original_text": "بس هي فول صبي",
            "words": [
                {"word": "بس", "start": 0.0, "end": 0.5, "probability": 0.85},
                {"word": "هي", "start": 0.5, "end": 1.0, "probability": 0.88},
                {"word": "فول", "start": 1.0, "end": 1.8, "probability": 0.90},
                {"word": "صبي", "start": 1.8, "end": 3.5, "probability": 0.92},
            ]
        },
        {
            "id": 2,
            "start": 3.5,
            "end": 7.0,
            "text": "في أول page خرس",
            "original_text": "في أول page خرس",
            "words": [
                {"word": "في", "start": 3.5, "end": 4.0, "probability": 0.85},
                {"word": "أول", "start": 4.0, "end": 4.8, "probability": 0.88},
                {"word": "page", "start": 4.8, "end": 5.8, "probability": 0.90},
                {"word": "خرس", "start": 5.8, "end": 7.0, "probability": 0.82},
            ]
        }
    ]

    original_clean = "بس هي فول صبي في أول page خرس"
    save_transcript(
        job_id=job_id,
        original_text=original_clean,
        clean_text=original_clean,
        srt_content="1\n00:00:00,000 --> 00:00:03,500\nبس هي فول صبي\n\n2\n00:00:03,500 --> 00:00:07,000\nفي أول page خرس\n",
        vtt_content="WEBVTT\n\n00:00:00.000 --> 00:00:03.500\nبس هي فول صبي\n\n00:00:03.500 --> 00:00:07.000\nفي أول page خرس\n",
        segments=original_segments
    )
    return job_id


def test_update_transcript_and_versioned_exports(sample_review_job):
    job_id = sample_review_job

    # 1. Verify initial state returns original text
    res = client.get(f"/api/transcription/{job_id}/result")
    assert res.status_code == 200
    data = res.json()
    assert data["is_edited"] is False
    assert data["segments"][0]["text"] == "بس هي فول صبي"
    assert data["segments"][0]["original_text"] == "بس هي فول صبي"

    # 2. Update transcript with human corrections
    corrected_segments = [
        {
            "id": 1,
            "start": 0.0,
            "end": 3.5,
            "text": "مساء الفل يا صبري",
            "original_text": "بس هي فول صبي",
            "words": data["segments"][0].get("words", [])
        },
        {
            "id": 2,
            "start": 3.5,
            "end": 7.0,
            "text": "في أول جزء خالص",
            "original_text": "في أول page خرس",
            "words": data["segments"][1].get("words", [])
        }
    ]
    corrected_clean = "مساء الفل يا صبري في أول جزء خالص"

    put_res = client.put(
        f"/api/transcription/{job_id}/segments",
        json={
            "clean_text": corrected_clean,
            "segments": corrected_segments
        }
    )
    assert put_res.status_code == 200
    assert put_res.json()["status"] == "updated"

    # Verify updated transcript in DB
    updated = client.get(f"/api/transcription/{job_id}/result").json()
    assert updated["is_edited"] is True
    assert updated["clean_text"] == corrected_clean
    assert updated["segments"][0]["text"] == "مساء الفل يا صبري"
    assert updated["segments"][0]["original_text"] == "بس هي فول صبي"

    # 3. Test TXT exports: edited vs original
    txt_edited = client.get(f"/api/exports/{job_id}/txt?version=edited")
    assert txt_edited.status_code == 200
    assert "مساء الفل يا صبري" in txt_edited.text
    assert "في أول جزء خالص" in txt_edited.text

    txt_original = client.get(f"/api/exports/{job_id}/txt?version=original")
    assert txt_original.status_code == 200
    assert "بس هي فول صبي" in txt_original.text
    assert "في أول page خرس" in txt_original.text

    # 4. Test SRT exports: edited vs original
    srt_edited = client.get(f"/api/exports/{job_id}/srt?version=edited")
    assert srt_edited.status_code == 200
    assert "00:00:00,000 --> 00:00:03,500" in srt_edited.text
    assert "مساء الفل يا صبري" in srt_edited.text

    srt_original = client.get(f"/api/exports/{job_id}/srt?version=original")
    assert srt_original.status_code == 200
    assert "00:00:00,000 --> 00:00:03,500" in srt_original.text
    assert "بس هي فول صبي" in srt_original.text

    # 5. Test VTT exports: edited vs original
    vtt_edited = client.get(f"/api/exports/{job_id}/vtt?version=edited")
    assert vtt_edited.status_code == 200
    assert "WEBVTT" in vtt_edited.text
    assert "00:00:00.000 --> 00:00:03.500" in vtt_edited.text
    assert "مساء الفل يا صبري" in vtt_edited.text

    vtt_original = client.get(f"/api/exports/{job_id}/vtt?version=original")
    assert vtt_original.status_code == 200
    assert "WEBVTT" in vtt_original.text
    assert "بس هي فول صبي" in vtt_original.text

    # 6. Test JSON exports: edited vs original
    json_edited = client.get(f"/api/exports/{job_id}/json?version=edited")
    assert json_edited.status_code == 200
    data_edited = json_edited.json()
    assert data_edited["metadata"]["export_version"] == "corrected"
    assert data_edited["segments"][0]["text"] == "مساء الفل يا صبري"
    assert len(data_edited["segments"][0]["words"]) == 4

    json_original = client.get(f"/api/exports/{job_id}/json?version=original")
    assert json_original.status_code == 200
    data_orig = json_original.json()
    assert data_orig["metadata"]["export_version"] == "original"
    assert data_orig["segments"][0]["text"] == "بس هي فول صبي"


def test_suggest_alternative_endpoint_not_found():
    res = client.post(
        "/api/transcription/suggest-alternative",
        json={
            "job_id": "non_existent_job_999",
            "start": 0.0,
            "end": 3.0,
            "model_id": "large-v3-turbo"
        }
    )
    assert res.status_code == 404


def test_suggest_alternative_endpoint_success(sample_review_job, tmp_path):
    job_id = sample_review_job
    fake_audio = tmp_path / "fake_input.ogg"
    fake_audio.write_bytes(b"RIFFdummydata")

    # Update job with existing fake audio file
    from app.core.database import get_connection
    conn = get_connection()
    conn.cursor().execute("UPDATE jobs SET input_path = ? WHERE id = ?", (str(fake_audio), job_id))
    conn.commit()
    conn.close()

    with patch("subprocess.run") as mock_subproc, \
         patch("app.api.transcription.is_model_downloaded", return_value=True), \
         patch("app.api.transcription.run_transcription_pipeline") as mock_pipeline:

        mock_subproc.return_value = MagicMock(returncode=0)
        mock_pipeline.return_value = {
            "clean_text": "مساء الفل يا صبري مقترح بديل",
            "segments": [
                {
                    "id": 1,
                    "start": 0.0,
                    "end": 3.5,
                    "text": "مساء الفل يا صبري مقترح بديل"
                }
            ]
        }

        res = client.post(
            "/api/transcription/suggest-alternative",
            json={
                "job_id": job_id,
                "start": 0.0,
                "end": 3.5,
                "model_id": "large-v3-turbo"
            }
        )

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "large-v3-turbo" in data["model_name"]
        assert data["suggested_text"] == "مساء الفل يا صبري مقترح بديل"
        assert data["start"] == 0.0
        assert data["end"] == 3.5
