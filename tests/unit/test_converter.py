from pathlib import Path
import pytest
from app.conversion.converter_engine import build_ffmpeg_args


def test_build_ffmpeg_args_mp3():
    in_file = Path("test.ogg")
    out_file = Path("test.mp3")
    args = build_ffmpeg_args(in_file, out_file, "mp3", preset="balanced")
    cmd_str = " ".join(args)
    assert "-c:a libmp3lame" in cmd_str
    assert "-b:a 192k" in cmd_str
    assert "-vn" in cmd_str


def test_build_ffmpeg_args_smaller_preset():
    in_file = Path("voice.wav")
    out_file = Path("voice.opus")
    args = build_ffmpeg_args(in_file, out_file, "opus", preset="smaller")
    cmd_str = " ".join(args)
    assert "-c:a libopus" in cmd_str
    assert "-b:a 64k" in cmd_str


def test_build_ffmpeg_args_custom():
    in_file = Path("input.mp4")
    out_file = Path("output.mp3")
    args = build_ffmpeg_args(
        in_file,
        out_file,
        "mp3",
        preset="custom",
        bitrate="256k",
        sample_rate=48000,
        channels=1,
    )
    cmd_str = " ".join(args)
    assert "-b:a 256k" in cmd_str
    assert "-ar 48000" in cmd_str
    assert "-ac 1" in cmd_str
