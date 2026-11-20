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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alternative_hypotheses (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        segment_id INTEGER NOT NULL,
        model_id TEXT NOT NULL,
        model_name TEXT NOT NULL,
        start_time REAL NOT NULL,
        end_time REAL NOT NULL,
        extracted_start REAL NOT NULL,
        extracted_end REAL NOT NULL,
        context_padding REAL DEFAULT 0.0,
        hypothesis_text TEXT NOT NULL,
        cleaned_hypothesis TEXT NOT NULL,
        primary_text TEXT NOT NULL,
        diff_json TEXT,
        disagreement_score REAL DEFAULT 0.0,
        device_used TEXT,
        compute_used TEXT,
        elapsed_seconds REAL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS segment_reviews (
        id TEXT PRIMARY KEY, -- job_id + "_" + segment_id
        job_id TEXT NOT NULL,
        segment_id INTEGER NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'unreviewed', -- 'unreviewed', 'review_suggested', 'alternative_available', 'human_reviewed'
        flag_reasons_json TEXT DEFAULT '[]', -- JSON array of strings
        selected_alternative_id TEXT,
        human_notes TEXT,
        reviewed_at TEXT,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS understanding_briefs (
        job_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        topic_overview TEXT NOT NULL,
        brief_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS benchmark_samples (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        source_job_id TEXT,
        source_filename TEXT NOT NULL,
        source_path TEXT NOT NULL,
        start_time REAL NOT NULL,
        end_time REAL NOT NULL,
        duration REAL NOT NULL,
        audio_file_path TEXT NOT NULL,
        ref_file_path TEXT NOT NULL,
        results_file_path TEXT NOT NULL,
        meta_file_path TEXT NOT NULL,
        is_verified INTEGER DEFAULT 0,
        description TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    try:
        cursor.execute("ALTER TABLE benchmark_samples ADD COLUMN is_verified INTEGER DEFAULT 0")
    except Exception:
        pass

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


# Alternative Hypothesis CRUD helpers
def save_alternative_hypothesis(
    hypothesis_id: str,
    job_id: str,
    segment_id: int,
    model_id: str,
    model_name: str,
    start_time: float,
    end_time: float,
    extracted_start: float,
    extracted_end: float,
    context_padding: float,
    hypothesis_text: str,
    cleaned_hypothesis: str,
    primary_text: str,
    diff_data: List[Dict[str, Any]],
    disagreement_score: float = 0.0,
    device_used: Optional[str] = None,
    compute_used: Optional[str] = None,
    elapsed_seconds: Optional[float] = None,
) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    cursor.execute("""
    INSERT OR REPLACE INTO alternative_hypotheses (
        id, job_id, segment_id, model_id, model_name,
        start_time, end_time, extracted_start, extracted_end, context_padding,
        hypothesis_text, cleaned_hypothesis, primary_text, diff_json,
        disagreement_score, device_used, compute_used, elapsed_seconds, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        hypothesis_id, job_id, segment_id, model_id, model_name,
        start_time, end_time, extracted_start, extracted_end, context_padding,
        hypothesis_text, cleaned_hypothesis, primary_text,
        json.dumps(diff_data, ensure_ascii=False),
        disagreement_score, device_used, compute_used, elapsed_seconds, now
    ))
    conn.commit()
    conn.close()
    return hypothesis_id


def get_alternative_hypotheses(job_id: str, segment_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if segment_id is not None:
        cursor.execute(
            "SELECT * FROM alternative_hypotheses WHERE job_id = ? AND segment_id = ? ORDER BY created_at DESC",
            (job_id, segment_id)
        )
    else:
        cursor.execute(
            "SELECT * FROM alternative_hypotheses WHERE job_id = ? ORDER BY segment_id ASC, created_at DESC",
            (job_id,)
        )
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["diff"] = json.loads(d["diff_json"] or "[]")
        result.append(d)
    return result


def get_alternative_hypothesis_by_id(hypothesis_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alternative_hypotheses WHERE id = ?", (hypothesis_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["diff"] = json.loads(d["diff_json"] or "[]")
    return d


def delete_alternative_hypothesis(hypothesis_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alternative_hypotheses WHERE id = ?", (hypothesis_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


# Segment Review CRUD helpers
def save_segment_review(
    job_id: str,
    segment_id: int,
    review_status: str = "unreviewed",
    flag_reasons: Optional[List[str]] = None,
    selected_alternative_id: Optional[str] = None,
    human_notes: Optional[str] = None,
) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    review_id = f"{job_id}_{segment_id}"
    reasons_json = json.dumps(flag_reasons or [], ensure_ascii=False)
    reviewed_at = now if review_status == "human_reviewed" else None

    cursor.execute("""
    INSERT INTO segment_reviews (
        id, job_id, segment_id, review_status, flag_reasons_json,
        selected_alternative_id, human_notes, reviewed_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        review_status = excluded.review_status,
        flag_reasons_json = excluded.flag_reasons_json,
        selected_alternative_id = COALESCE(excluded.selected_alternative_id, segment_reviews.selected_alternative_id),
        human_notes = COALESCE(excluded.human_notes, segment_reviews.human_notes),
        reviewed_at = COALESCE(excluded.reviewed_at, segment_reviews.reviewed_at),
        updated_at = excluded.updated_at
    """, (
        review_id, job_id, segment_id, review_status, reasons_json,
        selected_alternative_id, human_notes, reviewed_at, now
    ))
    conn.commit()
    conn.close()
    return review_id


def get_segment_reviews(job_id: str) -> Dict[int, Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM segment_reviews WHERE job_id = ?", (job_id,))
    rows = cursor.fetchall()
    conn.close()

    result: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        d = dict(r)
        d["flag_reasons"] = json.loads(d["flag_reasons_json"] or "[]")
        result[d["segment_id"]] = d
    return result


def update_segment_review_status(
    job_id: str,
    segment_id: int,
    review_status: str,
    selected_alternative_id: Optional[str] = None,
    human_notes: Optional[str] = None,
) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    review_id = f"{job_id}_{segment_id}"
    reviewed_at = now if review_status == "human_reviewed" else None

    cursor.execute("""
    INSERT INTO segment_reviews (
        id, job_id, segment_id, review_status, flag_reasons_json,
        selected_alternative_id, human_notes, reviewed_at, updated_at
    ) VALUES (?, ?, ?, ?, '[]', ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        review_status = excluded.review_status,
        selected_alternative_id = COALESCE(excluded.selected_alternative_id, segment_reviews.selected_alternative_id),
        human_notes = COALESCE(excluded.human_notes, segment_reviews.human_notes),
        reviewed_at = COALESCE(excluded.reviewed_at, segment_reviews.reviewed_at),
        updated_at = excluded.updated_at
    """, (
        review_id, job_id, segment_id, review_status,
        selected_alternative_id, human_notes, reviewed_at, now
    ))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


# Understanding Brief CRUD helpers
def save_understanding_brief(
    job_id: str,
    title: str,
    topic_overview: str,
    brief_data: Dict[str, Any],
) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    brief_json = json.dumps(brief_data, ensure_ascii=False)

    cursor.execute("""
    INSERT INTO understanding_briefs (
        job_id, title, topic_overview, brief_json, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(job_id) DO UPDATE SET
        title = excluded.title,
        topic_overview = excluded.topic_overview,
        brief_json = excluded.brief_json,
        updated_at = excluded.updated_at
    """, (
        job_id, title, topic_overview, brief_json, now, now
    ))
    conn.commit()
    conn.close()
    return job_id


def get_understanding_brief(job_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM understanding_briefs WHERE job_id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["brief"] = json.loads(d["brief_json"] or "{}")
    return d


def delete_understanding_brief(job_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM understanding_briefs WHERE job_id = ?", (job_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


# Benchmark Sample CRUD helpers
def create_benchmark_sample(sample_data: Dict[str, Any]) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO benchmark_samples (
        id, name, source_job_id, source_filename, source_path,
        start_time, end_time, duration,
        audio_file_path, ref_file_path, results_file_path, meta_file_path,
        description, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sample_data["id"],
        sample_data["name"],
        sample_data.get("source_job_id"),
        sample_data["source_filename"],
        sample_data["source_path"],
        float(sample_data["start_time"]),
        float(sample_data["end_time"]),
        float(sample_data["duration"]),
        sample_data["audio_file_path"],
        sample_data["ref_file_path"],
        sample_data["results_file_path"],
        sample_data["meta_file_path"],
        sample_data.get("description", ""),
        now,
        now,
    ))
    conn.commit()
    conn.close()
    return sample_data["id"]


def get_benchmark_sample(sample_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM benchmark_samples WHERE id = ?", (sample_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def list_benchmark_samples() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM benchmark_samples ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_benchmark_sample(sample_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM benchmark_samples WHERE id = ?", (sample_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def update_benchmark_sample_verification(sample_id: str, is_verified: bool) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute(
        "UPDATE benchmark_samples SET is_verified = ?, updated_at = ? WHERE id = ?",
        (1 if is_verified else 0, now, sample_id)
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def list_source_recordings() -> List[Dict[str, Any]]:
    """
    Returns distinct completed audio recordings available for creating benchmark samples.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, input_filename, input_path, input_duration, input_format, created_at
    FROM jobs
    WHERE status = 'completed' AND input_duration > 0
    ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    recordings = []
    seen_paths = set()
    for r in rows:
        d = dict(r)
        p = d.get("input_path", "")
        if p and p not in seen_paths:
            file_path = Path(p)
            try:
                if not file_path.is_file() or file_path.stat().st_size < 1024:
                    continue
            except Exception:
                continue
            seen_paths.add(p)
            dur = d.get("input_duration", 0.0)
            mins = int(dur // 60)
            secs = int(dur % 60)
            recordings.append({
                "job_id": d["id"],
                "filename": d["input_filename"],
                "path": p,
                "duration": dur,
                "duration_formatted": f"{mins:02d}:{secs % 60:02d}",
                "format": d.get("input_format", ""),
                "created_at": d["created_at"],
            })
    return recordings

