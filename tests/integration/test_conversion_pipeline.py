import subprocess
from pathlib import Path
import pytest
from app.audio.metadata_extractor import find_ffmpeg, extract_metadata
from app.conversion.converter_engine import convert_audio_file


@pytest.fixture(scope="module")
def synthetic_audio(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("audio_fixtures")
    wav_path = tmp_dir / "synthetic_tone.wav"

    ffmpeg = find_ffmpeg()
    # Generate 1 second 44.1kHz sine tone
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=1000:duration=1",
        "-ar", "44100",
        "-ac", "1",
        str(wav_path)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert wav_path.exists()
    return wav_path


def test_convert_synthetic_to_mp3(synthetic_audio, tmp_path):
    out_dir = tmp_path / "outputs"
    res = convert_audio_file(synthetic_audio, out_dir, "mp3", preset="balanced")
    assert Path(res["output_path"]).exists()
    assert res["output_filename"].endswith(".mp3")
    assert res["converted_metadata"]["format"] == "mp3"
    assert abs(res["converted_metadata"]["duration"] - 1.0) < 0.2


def test_convert_synthetic_to_flac(synthetic_audio, tmp_path):
    out_dir = tmp_path / "outputs_flac"
    res = convert_audio_file(synthetic_audio, out_dir, "flac", preset="high")
    assert Path(res["output_path"]).exists()
    assert res["converted_metadata"]["codec"] == "flac"
