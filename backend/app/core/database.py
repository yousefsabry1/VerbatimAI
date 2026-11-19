import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from app.core.config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        job_type TEXT NOT NULL, -- 'transcription' or 'conversion'
        status TEXT NOT NULL, -- 'queued', 'processing', 'completed', 'failed', 'cancelled'
        progress REAL DEFAULT 0.0,
        stage TEXT DEFAULT '',
        error_message TEXT,
        input_filename TEXT NOT NULL,
        input_path TEXT NOT NULL,
        input_duration REAL,
        input_size INTEGER,
        input_format TEXT,
        model_used TEXT,
        device_used TEXT,
        compute_used TEXT,
        language TEXT,
        output_files_json TEXT, -- JSON dictionary of output file paths
        metadata_json TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transcripts (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL UNIQUE,
        original_text TEXT NOT NULL,
        clean_text TEXT,
        srt_content TEXT,
        vtt_content TEXT,
        segments_json TEXT NOT NULL,
        is_edited INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully at %s", DB_PATH)


# Job CRUD helpers
def create_job(job_data: Dict[str, Any]) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    cursor.execute("""
    INSERT INTO jobs (
        id, job_type, status, progress, stage, error_message,
        input_filename, input_path, input_duration, input_size, input_format,
        model_used, device_used, compute_used, language, output_files_json, metadata_json,
        created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_data["id"],
        job_data["job_type"],
        job_data.get("status", "queued"),
        job_data.get("progress", 0.0),
        job_data.get("stage", "Initializing"),
        job_data.get("error_message"),
        job_data["input_filename"],
        job_data["input_path"],
        job_data.get("input_duration"),
        job_data.get("input_size"),
        job_data.get("input_format"),
        job_data.get("model_used"),
        job_data.get("device_used"),
        job_data.get("compute_used"),
        job_data.get("language"),
        json.dumps(job_data.get("output_files", {})),
        json.dumps(job_data.get("metadata", {})),
        now
    ))
    conn.commit()
    conn.close()
    return job_data["id"]


def update_job_progress(job_id: str, progress: float, stage: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET progress = ?, stage = ? WHERE id = ?",
        (progress, stage, job_id)
    )
    conn.commit()
    conn.close()


def update_job_device(job_id: str, device: str, compute: Optional[str] = None, stage: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "UPDATE jobs SET device_used = ?"
    params = [device]
    if compute:
        query += ", compute_used = ?"
        params.append(compute)
    if stage:
        query += ", stage = ?"
        params.append(stage)
    query += " WHERE id = ?"
    params.append(job_id)
    cursor.execute(query, params)
    conn.commit()
    conn.close()


def complete_job(job_id: str, output_files: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    query = """
    UPDATE jobs
    SET status = 'completed', progress = 1.0, stage = 'Completed',
        output_files_json = ?, completed_at = ?
    """
    params = [json.dumps(output_files), now]

    if metadata is not None:
        query += ", metadata_json = ?"
        params.append(json.dumps(metadata))
        if "device_used" in metadata:
            query += ", device_used = ?"
            params.append(metadata["device_used"])
        if "compute_used" in metadata:
            query += ", compute_used = ?"
            params.append(metadata["compute_used"])

    query += " WHERE id = ?"
    params.append(job_id)

    cursor.execute(query, params)
    conn.commit()
    conn.close()


def fail_job(job_id: str, error_message: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute("""
    UPDATE jobs
    SET status = 'failed', stage = 'Failed', error_message = ?, completed_at = ?
    WHERE id = ?
    """, (error_message, now, job_id))
    conn.commit()
    conn.close()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    res = dict(row)
    res["output_files"] = json.loads(res["output_files_json"] or "{}")
    res["metadata"] = json.loads(res["metadata_json"] or "{}")
    return res


def list_jobs(limit: int = 50, job_type: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if job_type:
        cursor.execute(
            "SELECT * FROM jobs WHERE job_type = ? ORDER BY created_at DESC LIMIT ?",
            (job_type, limit)
        )
    else:
        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["output_files"] = json.loads(d["output_files_json"] or "{}")
        d["metadata"] = json.loads(d["metadata_json"] or "{}")
        result.append(d)
    return result


def delete_job(job_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transcripts WHERE job_id = ?", (job_id,))
    cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def clear_all_jobs() -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transcripts")
    cursor.execute("DELETE FROM jobs")
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


# Transcript CRUD helpers
def save_transcript(job_id: str, original_text: str, clean_text: str,
                    srt_content: str, vtt_content: str, segments: List[Dict[str, Any]]):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    t_id = f"tr_{job_id}"

    cursor.execute("""
    INSERT OR REPLACE INTO transcripts (
        id, job_id, original_text, clean_text, srt_content, vtt_content,
        segments_json, is_edited, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
    """, (
        t_id, job_id, original_text, clean_text, srt_content, vtt_content,
        json.dumps(segments, ensure_ascii=False), now
    ))
    conn.commit()
    conn.close()


def get_transcript(job_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transcripts WHERE job_id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["segments"] = json.loads(d["segments_json"] or "[]")
    return d


def update_transcript_content(job_id: str, clean_text: str, segments: List[Dict[str, Any]],
                              srt_content: str, vtt_content: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute("""
    UPDATE transcripts
    SET clean_text = ?, segments_json = ?, srt_content = ?, vtt_content = ?, is_edited = 1, updated_at = ?
    WHERE job_id = ?
    """, (clean_text, json.dumps(segments, ensure_ascii=False), srt_content, vtt_content, now, job_id))
    conn.commit()
    conn.close()
