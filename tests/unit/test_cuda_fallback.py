import os
import sys
import pytest
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.cuda_init import register_nvidia_dll_directories
from app.transcription.engine import (
    is_cuda_error,
    get_compute_type,
    run_transcription_pipeline,
)


def test_is_cuda_error():
    assert is_cuda_error(RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"))
    assert is_cuda_error(RuntimeError("CUDA failed with error out of memory"))
    assert is_cuda_error(RuntimeError("cudnn64_9.dll error: CUDNN_STATUS_INTERNAL_ERROR"))
    assert is_cuda_error(RuntimeError("ctranslate2::cuda device error"))
    assert is_cuda_error(RuntimeError("NVIDIA driver not available"))

    # Unrelated errors must return False
    assert not is_cuda_error(FileNotFoundError("No such file: audio.wav"))
    assert not is_cuda_error(ValueError("Invalid language selected"))
    assert not is_cuda_error(KeyError("missing_key"))


def test_get_compute_type_efficiency():
    # CUDA should default to int8_float16 for 4GB VRAM safety & throughput
    assert get_compute_type("auto", "cuda") == "int8_float16"
    assert get_compute_type("auto", "cpu") == "int8"
    # Explicit preferences respected
    assert get_compute_type("float16", "cuda") == "float16"
    assert get_compute_type("int8", "cpu") == "int8"


def test_register_nvidia_dll_directories_idempotent():
    dirs1 = register_nvidia_dll_directories()
    assert isinstance(dirs1, list)
    dirs2 = register_nvidia_dll_directories()
    assert dirs2 == []  # second call is idempotent


def test_simulated_cuda_generator_fallback(tmp_path):
    """
    Verifies that when a CUDA error occurs during lazy generator iteration,
    the pipeline catches it, frees GPU resources, loads the CPU model,
    slices and transcribes the remaining audio from the checkpoint,
    and returns a combined transcript without losing committed segments.
    """
    slice_path = Path(r"C:\Users\youse\.gemini\antigravity\brain\3e1f44d8-52f9-4a36-9ba0-e8ea39fa92d5\scratch\slices\slice1_00_45.wav")
    if not slice_path.exists():
        pytest.skip("Test audio slice1_00_45.wav not found in scratch directory")

    # Set the test simulation hook
    os.environ["VERBATIM_SIMULATE_CUDA_ERROR"] = "1"

    job_id = f"test_fb_{os.getpid()}"
    res = run_transcription_pipeline(
        input_path=slice_path,
        job_id=job_id,
        model_id="codeswitched-medium",
        device_mode="cuda",
        compute_mode="auto",
    )

    meta = res["metadata"]
    assert meta["cuda_fallback"] is True, "Expected cuda_fallback to be True"
    assert meta["initial_device"] == "cuda"
    assert meta["device_used"] == "cpu"
    assert "cublas64_12.dll" in meta["cuda_fallback_error"]
    assert meta["cuda_checkpoint_time"] is not None
    assert meta["cuda_checkpoint_time"] > 0

    segments = res["segments"]
    assert len(segments) >= 2, f"Expected at least 2 segments, got {len(segments)}"

    # Ensure first segment came before checkpoint and was preserved
    assert segments[0]["end"] <= meta["cuda_checkpoint_time"] + 0.1

    # Ensure timestamps are monotonic and non-overlapping
    for i in range(1, len(segments)):
        prev_seg = segments[i - 1]
        curr_seg = segments[i]
        assert curr_seg["start"] >= prev_seg["end"] - 0.05, (
            f"Segment {curr_seg['id']} start {curr_seg['start']} overlapped prev end {prev_seg['end']}"
        )
        assert curr_seg["end"] > curr_seg["start"]


def test_cuda_only_diagnostic_mode_halts_without_fallback():
    """
    Verifies that when device_mode='cuda_only', any CUDA failure halts immediately
    and raises an error without silently switching to CPU.
    """
    slice_path = Path(r"C:\Users\youse\.gemini\antigravity\brain\3e1f44d8-52f9-4a36-9ba0-e8ea39fa92d5\scratch\slices\slice1_00_45.wav")
    if not slice_path.exists():
        pytest.skip("Test audio slice1_00_45.wav not found in scratch directory")

    os.environ["VERBATIM_SIMULATE_CUDA_ERROR"] = "1"
    job_id = f"test_cuda_only_{os.getpid()}"

    with pytest.raises(RuntimeError) as exc_info:
        run_transcription_pipeline(
            input_path=slice_path,
            job_id=job_id,
            model_id="codeswitched-medium",
            device_mode="cuda_only",
            compute_mode="auto",
        )

    assert "GPU-Only Diagnostic Mode" in str(exc_info.value)
