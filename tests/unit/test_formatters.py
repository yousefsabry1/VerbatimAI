import json
import pytest
from app.exports.formatters import (
    seconds_to_srt_time,
    seconds_to_vtt_time,
    seconds_to_readable,
    generate_srt,
    generate_vtt,
    generate_timestamped_txt,
    generate_clean_txt,
    generate_json_export,
)


def test_seconds_to_srt_time():
    assert seconds_to_srt_time(0.0) == "00:00:00,000"
    assert seconds_to_srt_time(65.123) == "00:01:05,123"
    assert seconds_to_srt_time(3661.050) == "01:01:01,050"


def test_seconds_to_vtt_time():
    assert seconds_to_vtt_time(0.0) == "00:00:00.000"
    assert seconds_to_vtt_time(65.123) == "00:01:05.123"


def test_seconds_to_readable():
    assert seconds_to_readable(45) == "00:45"
    assert seconds_to_readable(125) == "02:05"
    assert seconds_to_readable(3665) == "01:01:05"


def test_generate_srt():
    sample_segments = [
        {"id": 1, "start": 0.0, "end": 2.5, "text": "Hello world"},
        {"id": 2, "start": 2.5, "end": 5.0, "text": "مرحبا بك"},
    ]
    srt = generate_srt(sample_segments)
    assert "1\n00:00:00,000 --> 00:00:02,500\nHello world" in srt
    assert "2\n00:00:02,500 --> 00:00:05,000\nمرحبا بك" in srt


def test_generate_vtt():
    sample_segments = [
        {"id": 1, "start": 1.0, "end": 3.0, "text": "First subtitle"},
    ]
    vtt = generate_vtt(sample_segments)
    assert vtt.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:03.000" in vtt
    assert "First subtitle" in vtt


def test_generate_timestamped_txt():
    sample_segments = [
        {"id": 1, "start": 0.0, "end": 4.0, "text": "This is a test"},
    ]
    txt = generate_timestamped_txt(sample_segments)
    assert "[00:00 - 00:04] This is a test" in txt


def test_generate_clean_txt():
    sample_segments = [
        {"id": 1, "start": 0.0, "end": 2.0, "text": "Paragraph one part one."},
        {"id": 2, "start": 2.0, "end": 4.0, "text": "Paragraph one part two."},
    ]
    clean = generate_clean_txt(sample_segments)
    assert "Paragraph one part one. Paragraph one part two." in clean


def test_generate_json_export():
    sample_segments = [{"id": 1, "start": 0.0, "end": 1.0, "text": "test"}]
    meta = {"job_id": "test_1", "duration": 1.0}
    raw_json = generate_json_export("test_1", sample_segments, meta)
    data = json.loads(raw_json)
    assert data["verbatim_version"] == "1.0.0"
    assert data["job_id"] == "test_1"
    assert len(data["segments"]) == 1
