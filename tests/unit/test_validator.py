import pytest
from app.audio.validator import sanitize_filename, validate_upload_file


def test_sanitize_filename_simple():
    assert sanitize_filename("audio.mp3") == "audio.mp3"


def test_sanitize_filename_traversal():
    # Path traversal patterns must be flattened to bare filename
    result = sanitize_filename("../../etc/passwd/test.wav")
    assert ".." not in result
    assert "/" not in result
    assert "\\" not in result
    assert result.endswith("test.wav")


def test_sanitize_filename_arabic():
    # Arabic letters must be preserved
    result = sanitize_filename("تسجيل_صوتي_1.ogg")
    assert "تسجيل_صوتي_1" in result
    assert result.endswith(".ogg")


def test_validate_upload_file_valid():
    ok, err = validate_upload_file("meeting.ogg", 1024 * 1024)
    assert ok is True
    assert err == ""

    ok, err = validate_upload_file("whatsapp_voice.opus", 500 * 1024)
    assert ok is True

    ok, err = validate_upload_file("recording.mp3", 2 * 1024 * 1024)
    assert ok is True


def test_validate_upload_file_invalid_ext():
    ok, err = validate_upload_file("malicious.exe", 1024)
    assert ok is False
    assert "Unsupported file type" in err


def test_validate_upload_file_too_large():
    too_large = 600 * 1024 * 1024  # 600 MB
    ok, err = validate_upload_file("large.wav", too_large)
    assert ok is False
    assert "exceeds maximum" in err
