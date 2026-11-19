import json
from typing import List, Dict, Any


def seconds_to_srt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def seconds_to_vtt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def seconds_to_readable(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def generate_srt(segments: List[Dict[str, Any]]) -> str:
    blocks = []
    for idx, seg in enumerate(segments, start=1):
        text = seg.get("text", "").strip()
        if not text:
            continue
        start_str = seconds_to_srt_time(seg.get("start", 0.0))
        end_str = seconds_to_srt_time(seg.get("end", 0.0))
        blocks.append(f"{idx}\n{start_str} --> {end_str}\n{text}")
    return "\n\n".join(blocks)


def generate_vtt(segments: List[Dict[str, Any]]) -> str:
    blocks = ["WEBVTT", ""]
    for idx, seg in enumerate(segments, start=1):
        text = seg.get("text", "").strip()
        if not text:
            continue
        start_str = seconds_to_vtt_time(seg.get("start", 0.0))
        end_str = seconds_to_vtt_time(seg.get("end", 0.0))
        blocks.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")
    return "\n".join(blocks)


def generate_timestamped_txt(segments: List[Dict[str, Any]]) -> str:
    lines = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        start_str = seconds_to_readable(seg.get("start", 0.0))
        end_str = seconds_to_readable(seg.get("end", 0.0))
        lines.append(f"[{start_str} - {end_str}] {text}")
    return "\n".join(lines)


def generate_clean_txt(segments: List[Dict[str, Any]], min_chars: int = 1500, max_chars: int = 2500) -> str:
    paragraphs = []
    current_parts = []
    current_length = 0
    punctuation = tuple(".!?;:\u060c\u061b\u061f")

    for seg in segments:
        text = " ".join(str(seg.get("text", "")).strip().split())
        if not text:
            continue

        current_parts.append(text)
        current_length += len(text) + (1 if current_length else 0)

        can_break = current_length >= min_chars and text.endswith(punctuation)
        must_break = current_length >= max_chars
        if can_break or must_break:
            paragraphs.append(" ".join(current_parts))
            current_parts = []
            current_length = 0

    if current_parts:
        paragraphs.append(" ".join(current_parts))

    return "\n\n".join(paragraphs)


def generate_json_export(job_id: str, segments: List[Dict[str, Any]], metadata: Dict[str, Any]) -> str:
    payload = {
        "verbatim_version": "1.0.0",
        "job_id": job_id,
        "metadata": metadata,
        "segments_count": len(segments),
        "segments": segments,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
