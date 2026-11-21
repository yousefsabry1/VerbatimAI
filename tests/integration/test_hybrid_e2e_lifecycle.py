"""
End-to-End Integration Test for Hybrid ASR V2 Lifecycle
Verifies:
- Model availability in /api/models
- Hybrid V2 execution on actual audio slice
- Timestamp alignment & segment projection
- Database persistence in verbatim.db
- History retrieval via /api/history
- Transcript Editor data retrieval via /api/transcription/{job_id}/result
- Segment edits and autosave via PUT /api/transcription/{job_id}/segments
- Formatted exports generation (TXT, SRT, VTT, JSON)
- Clean deletion via DELETE /api/history/{job_id}
"""

import uuid
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import STORAGE_DIR
from app.core.database import get_job, get_transcript, save_transcript, create_job, complete_job, delete_job
from app.transcription.hybrid_orchestrator import run_hybrid_transcription
from app.audio.metadata_extractor import extract_metadata

client = TestClient(app)


def test_hybrid_models_exposed_in_api():
    res = client.get("/api/models")
    assert res.status_code == 200
    data = res.json()
    model_ids = [m["id"] for m in data.get("models", [])]
    assert "hybrid-v1" in model_ids, "hybrid-v1 must be exposed in API"
    assert "hybrid-v2" in model_ids, "hybrid-v2 must be exposed in API"
    assert "hybrid-v3" in model_ids, "hybrid-v3 must be exposed in API"
    
    # Verify metadata
    v2_info = next(m for m in data["models"] if m["id"] == "hybrid-v2")
    assert v2_info.get("is_experimental") is True
    assert "Hybrid" in v2_info.get("name", "")

    v3_info = next(m for m in data["models"] if m["id"] == "hybrid-v3")
    assert v3_info.get("is_experimental") is True
    assert "Hybrid" in v3_info.get("name", "")


def test_hybrid_v2_end_to_end_lifecycle(tmp_path):
    audio_path = STORAGE_DIR / "benchmarks" / "test_slice_0_12.wav"
    assert audio_path.exists(), f"Benchmark test slice missing at {audio_path}"

    test_job_id = f"test_e2e_{uuid.uuid4().hex[:8]}"
    job_dir = tmp_path / f"job_{test_job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)

    source_meta = extract_metadata(audio_path)
    assert source_meta["duration"] > 0

    # 1. Create Job in DB
    job_data = {
        "id": test_job_id,
        "job_type": "transcription",
        "status": "processing",
        "progress": 0.05,
        "stage": "Hybrid Processing",
        "input_filename": audio_path.name,
        "input_path": str(audio_path),
        "input_duration": source_meta.get("duration"),
        "input_size": source_meta.get("size"),
        "input_format": source_meta.get("format"),
        "model_used": "hybrid-v2",
        "device_used": "cuda",
        "compute_used": "float16",
        "language": "ar",
        "output_files": {},
        "metadata": {
            "accuracy_mode": "balanced",
            "verbatim_mode": "strict",
            "enhanced": False,
            "vad": False,
        }
    }
    create_job(job_data)

    # 2. Execute Hybrid Transcription Pipeline
    progress_updates = []
    def on_progress(p, s):
        progress_updates.append((p, s))

    res = run_hybrid_transcription(
        input_path=audio_path,
        job_id=test_job_id,
        job_dir=job_dir,
        source_meta=source_meta,
        model_id="hybrid-v2",
        language="ar",
        device_mode="cuda",
        accuracy_mode="balanced",
        verbatim_mode="strict",
        enhance_audio=False,
        vad_filter=False,
        vocabulary_hints=None,
        progress_callback=on_progress,
    )

    # Assertions on pipeline result
    assert res["job_id"] == test_job_id
    assert res["original_text"]
    assert res["clean_text"]
    assert len(res["segments"]) >= 1
    assert "srt_content" in res and res["srt_content"]
    assert "vtt_content" in res and res["vtt_content"]
    assert "output_files" in res
    assert "hybrid_metadata" in res["metadata"]

    # Check timestamps on segments
    for seg in res["segments"]:
        assert "start" in seg and "end" in seg and "text" in seg
        assert seg["end"] >= seg["start"]
        assert seg["text"].strip() != ""

    # 3. Save transcript to DB & Mark complete
    save_transcript(
        job_id=test_job_id,
        original_text=res["original_text"],
        clean_text=res["clean_text"],
        srt_content=res["srt_content"],
        vtt_content=res["vtt_content"],
        segments=res["segments"],
    )
    complete_job(test_job_id, res["output_files"], metadata=res["metadata"])

    # 4. Verify DB Persistence
    persisted_job = get_job(test_job_id)
    assert persisted_job is not None
    assert persisted_job["status"] == "completed"
    assert persisted_job["model_used"] == "hybrid-v2"
    assert persisted_job["metadata"]["hybrid_metadata"]["fusion_method"] in ("rover_confusion_network_v2", "hybrid_v2")

    persisted_tr = get_transcript(test_job_id)
    assert persisted_tr is not None
    assert len(persisted_tr["segments"]) == len(res["segments"])

    # 5. Verify API History Retrieval
    hist_res = client.get("/api/history")
    assert hist_res.status_code == 200
    jobs = hist_res.json().get("jobs", [])
    found_in_history = any(j["id"] == test_job_id for j in jobs)
    assert found_in_history, "Job must appear in history list"

    # 6. Verify API Transcription Result (Editor View)
    result_res = client.get(f"/api/transcription/{test_job_id}/result")
    assert result_res.status_code == 200
    rdata = result_res.json()
    assert rdata["is_complete"] is True
    assert len(rdata["segments"]) == len(res["segments"])
    assert rdata["clean_text"] == res["clean_text"]

    # 7. Verify Manual Human Edit & Autosave
    updated_segments = list(res["segments"])
    updated_segments[0]["text"] = updated_segments[0]["text"] + " [تم التعديل يدويًا]"
    updated_clean = "\n".join(s["text"] for s in updated_segments)

    edit_res = client.put(
        f"/api/transcription/{test_job_id}/segments",
        json={"clean_text": updated_clean, "segments": updated_segments}
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["status"] == "updated"

    # Verify edit was saved in DB
    edited_tr = get_transcript(test_job_id)
    assert edited_tr["is_edited"] == 1
    assert "[تم التعديل يدويًا]" in edited_tr["segments"][0]["text"]
    assert "[تم التعديل يدويًا]" in edited_tr["srt_content"]

    # 8. Verify Format Exports
    # TXT (timestamped)
    exp_txt = client.get(f"/api/exports/{test_job_id}/txt?version=edited")
    assert exp_txt.status_code == 200
    assert "[تم التعديل يدويًا]" in exp_txt.text
    assert "attachment;" in exp_txt.headers.get("content-disposition", "")

    # TXT (original)
    exp_txt_orig = client.get(f"/api/exports/{test_job_id}/txt?version=original")
    assert exp_txt_orig.status_code == 200
    assert "[تم التعديل يدويًا]" not in exp_txt_orig.text

    # SRT
    exp_srt = client.get(f"/api/exports/{test_job_id}/srt?version=edited")
    assert exp_srt.status_code == 200
    assert "-->" in exp_srt.text
    assert "[تم التعديل يدويًا]" in exp_srt.text

    # VTT
    exp_vtt = client.get(f"/api/exports/{test_job_id}/vtt?version=edited")
    assert exp_vtt.status_code == 200
    assert "WEBVTT" in exp_vtt.text
    assert "-->" in exp_vtt.text

    # JSON
    exp_json = client.get(f"/api/exports/{test_job_id}/json?version=edited")
    assert exp_json.status_code == 200
    json_data = exp_json.json()
    assert json_data["job_id"] == test_job_id
    assert len(json_data["segments"]) == len(updated_segments)
    assert json_data["metadata"]["is_edited"] is True

    # 9. Clean Deletion
    del_res = client.delete(f"/api/history/{test_job_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Confirm deleted from DB
    assert get_job(test_job_id) is None
    assert get_transcript(test_job_id) is None


def test_hybrid_v3_end_to_end_lifecycle(tmp_path):
    audio_path = STORAGE_DIR / "benchmarks" / "test_slice_0_12.wav"
    assert audio_path.exists(), f"Benchmark test slice missing at {audio_path}"

    test_job_id = f"test_e2e_v3_{uuid.uuid4().hex[:8]}"
    job_dir = tmp_path / f"job_{test_job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)

    source_meta = extract_metadata(audio_path)
    assert source_meta["duration"] > 0

    # 1. Create Job in DB
    job_data = {
        "id": test_job_id,
        "job_type": "transcription",
        "status": "processing",
        "progress": 0.05,
        "stage": "Hybrid V3 Processing",
        "input_filename": audio_path.name,
        "input_path": str(audio_path),
        "input_duration": source_meta.get("duration"),
        "input_size": source_meta.get("size"),
        "input_format": source_meta.get("format"),
        "model_used": "hybrid-v3",
        "device_used": "cuda",
        "compute_used": "float16",
        "language": "ar",
        "output_files": {},
        "metadata": {
            "accuracy_mode": "balanced",
            "verbatim_mode": "strict",
            "enhanced": False,
            "vad": False,
        }
    }
    create_job(job_data)

    progress_updates = []
    def on_progress(p, s):
        progress_updates.append((p, s))

    # 2. Execute Hybrid V3 Pipeline on actual audio slice
    res = run_hybrid_transcription(
        input_path=audio_path,
        job_id=test_job_id,
        job_dir=job_dir,
        source_meta=source_meta,
        model_id="hybrid-v3",
        language="ar",
        device_mode="cuda",
        accuracy_mode="balanced",
        verbatim_mode="strict",
        enhance_audio=False,
        vad_filter=False,
        vocabulary_hints=None,
        progress_callback=on_progress,
    )

    assert res["clean_text"]
    assert len(res["segments"]) > 0

    # 3. Verify timestamps integrity
    for seg in res["segments"]:
        assert seg["start"] >= 0.0
        assert seg["end"] >= seg["start"]
        assert len(seg["text"].strip()) > 0

    # Save transcript to DB & Mark complete
    save_transcript(
        job_id=test_job_id,
        original_text=res["original_text"],
        clean_text=res["clean_text"],
        srt_content=res["srt_content"],
        vtt_content=res["vtt_content"],
        segments=res["segments"],
    )
    complete_job(test_job_id, res["output_files"], metadata=res["metadata"])

    # 4. Verify DB Persistence & Model Recorded
    job = get_job(test_job_id)
    assert job is not None
    assert job["status"] == "completed"
    assert job["model_used"] == "hybrid-v3"

    tr = get_transcript(test_job_id)
    assert tr is not None
    assert tr["clean_text"] == res["clean_text"]

    # 5. Clean Deletion
    del_res = client.delete(f"/api/history/{test_job_id}")
    assert del_res.status_code == 200
    assert get_job(test_job_id) is None

