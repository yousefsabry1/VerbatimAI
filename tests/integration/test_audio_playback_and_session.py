import uuid
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import create_job, save_transcript, complete_job, get_job, get_transcript
from app.api.audio import resolve_file, get_or_create_preview
from app.core.config import UPLOADS_DIR, PREVIEWS_DIR

client = TestClient(app)


@pytest.fixture
def mock_audio_job(tmp_path):
    job_id = f"test_job_{uuid.uuid4().hex[:8]}"
    fake_audio = UPLOADS_DIR / f"{job_id}_test_audio.wav"
    # Write a simple RIFF WAVE header (44 bytes) + some dummy PCM samples
    riff_header = (
        b"RIFF" + (36 + 1000).to_bytes(4, "little") + b"WAVE" +
        b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") +
        (1).to_bytes(2, "little") + (16000).to_bytes(4, "little") +
        (32000).to_bytes(4, "little") + (2).to_bytes(2, "little") +
        (16).to_bytes(2, "little") + b"data" + (1000).to_bytes(4, "little") +
        b"\x00" * 1000
    )
    fake_audio.write_bytes(riff_header)

    create_job({
        "id": job_id,
        "job_type": "transcription",
        "input_filename": fake_audio.name,
        "input_path": str(fake_audio),
        "input_duration": 611.593,
        "model_used": "codeswitched-medium",
        "language": "ar",
        "device_used": "cuda",
        "compute_used": "int8_float16",
        "status": "completed",
        "progress": 1.0,
        "stage": "Transcription Completed",
    })
    complete_job(job_id, output_files={})

    initial_segments = [
        {"id": 1, "start": 0.0, "end": 30.0, "text": "مساء الفل يا صبري", "original_text": "مساء الفل يا صبري"}
    ]
    save_transcript(
        job_id=job_id,
        original_text="مساء الفل يا صبري",
        clean_text="مساء الفل يا صبري",
        srt_content="1\n00:00:00,000 --> 00:00:30,000\nمساء الفل يا صبري\n",
        vtt_content="WEBVTT\n\n00:00:00.000 --> 00:00:30.000\nمساء الفل يا صبري\n",
        segments=initial_segments
    )

    yield job_id

    # Teardown
    fake_audio.unlink(missing_ok=True)


def test_resolve_file_by_job_id(mock_audio_job):
    job_id = mock_audio_job
    resolved = resolve_file(job_id)
    assert resolved.is_file()
    assert resolved.name.startswith(job_id)


def test_stream_audio_by_job_id_and_range(mock_audio_job):
    job_id = mock_audio_job

    # Full request
    res = client.get(f"/api/audio/stream/{job_id}?preview=false")
    assert res.status_code == 200
    assert "audio/" in res.headers.get("content-type", "")
    assert res.headers.get("accept-ranges") == "bytes"

    # Range request for seeking
    range_res = client.get(
        f"/api/audio/stream/{job_id}?preview=false",
        headers={"Range": "bytes=0-100"}
    )
    assert range_res.status_code == 206
    assert range_res.headers.get("content-range") is not None
    assert len(range_res.content) == 101


def test_transcription_result_hydrates_job_metadata(mock_audio_job):
    job_id = mock_audio_job
    res = client.get(f"/api/transcription/{job_id}/result")
    assert res.status_code == 200
    data = res.json()
    assert data["job_id"] == job_id
    assert data["is_complete"] is True
    assert data["job"]["input_duration"] == 611.593
    assert len(data["segments"]) == 1
    assert data["segments"][0]["original_text"] == "مساء الفل يا صبري"


def test_update_segments_persists_durable_edits(mock_audio_job):
    job_id = mock_audio_job

    # Update transcript with human corrections
    new_text = "مساء الفل يا صبري - تعديل موثق"
    put_res = client.put(
        f"/api/transcription/{job_id}/segments",
        json={
            "clean_text": new_text,
            "segments": [
                {
                    "id": 1,
                    "start": 0.0,
                    "end": 30.0,
                    "text": new_text,
                    "original_text": "مساء الفل يا صبري"
                }
            ]
        }
    )
    assert put_res.status_code == 200
    assert put_res.json()["status"] == "updated"

    # Fetch result again to verify persistence
    updated = client.get(f"/api/transcription/{job_id}/result").json()
    assert updated["is_edited"] is True
    assert updated["clean_text"] == new_text
    assert updated["segments"][0]["text"] == new_text
    # Original ASR remains immutable
    assert updated["segments"][0]["original_text"] == "مساء الفل يا صبري"
    assert updated["original_text"] == "مساء الفل يا صبري"


def test_preview_endpoint_alias(mock_audio_job):
    job_id = mock_audio_job
    res = client.get(f"/api/audio/preview/{job_id}")
    assert res.status_code in (200, 206)
    assert res.headers.get("accept-ranges") == "bytes"
