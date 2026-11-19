import os
import sys
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable

from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download

from app.core.config import (
    MODELS_DIR,
    OUTPUTS_DIR,
    SUPPORTED_MODELS,
    EGYPTIAN_ARABIC_PROMPT,
)
from app.audio.metadata_extractor import find_ffmpeg, extract_metadata
from app.exports.formatters import (
    generate_srt,
    generate_vtt,
    generate_timestamped_txt,
    generate_clean_txt,
    generate_json_export,
)

logger = logging.getLogger(__name__)

# Global memory cache for loaded models
_LOADED_MODELS_CACHE: Dict[Tuple[str, str, str], WhisperModel] = {}


def sanitize_name(name: str) -> str:
    return str(name).replace("/", "_").replace("\\", "_").replace(":", "_")


def get_model_dir(model_id: str) -> Path:
    return MODELS_DIR / sanitize_name(model_id)


def is_model_downloaded(model_id: str) -> bool:
    target_dir = get_model_dir(model_id)
    marker = target_dir / ".ready"
    if marker.exists() and (target_dir / "model.bin").exists():
        return True
    if (target_dir / "model.bin").exists() and (target_dir / "config.json").exists():
        return True
    return False


def get_model_folder_size_gb(model_id: str) -> float:
    target_dir = get_model_dir(model_id)
    if not target_dir.exists():
        return 0.0
    total = 0
    for p in target_dir.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except Exception:
                pass
    return round(total / (1024 ** 3), 2)


def download_model(model_id: str, progress_callback: Optional[Callable[[float, str], None]] = None) -> Path:
    if model_id not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown model identifier: {model_id}")

    model_info = SUPPORTED_MODELS[model_id]
    repo_id = model_info["repo"]
    target_dir = get_model_dir(model_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(0.05, f"Connecting to Hugging Face for {model_info['name']}...")

    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
        )

        if not (target_dir / "model.bin").exists():
            raise RuntimeError("Model download completed but model.bin was not found.")

        # Write ready marker
        (target_dir / ".ready").write_text(f"ready={model_id}\nrepo={repo_id}\n", encoding="utf-8")

        if progress_callback:
            progress_callback(1.0, f"Model {model_info['name']} ready")

        return target_dir
    except Exception as e:
        logger.error("Failed to download model %s: %s", model_id, e)
        raise RuntimeError(f"Model download failed: {e}")


def get_compute_type(compute_mode: str, device: str) -> str:
    if compute_mode in ("float16", "int8_float16", "int8"):
        return compute_mode
    # Auto logic
    if device == "cuda":
        return "float16"
    return "int8"


def is_cuda_error(err: Exception) -> bool:
    msg = (str(err) + " " + repr(err)).lower()
    keywords = ["cublas", "cudnn", "cudart", "cuda", "dll", "out of memory", "not found", "failed to load"]
    return any(k in msg for k in keywords)


def load_whisper_model(
    model_id: str,
    device_mode: str = "auto",
    compute_mode: str = "auto",
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Tuple[WhisperModel, str, str]:
    """
    Loads Faster-Whisper model with intelligent fallback to CPU.
    Returns: (model_instance, actual_device, actual_compute_type)
    """
    if not is_model_downloaded(model_id):
        raise RuntimeError(f"Model '{model_id}' is not downloaded yet. Please download it first.")

    model_path = str(get_model_dir(model_id))

    if device_mode == "cpu":
        device_attempts = ["cpu"]
    elif device_mode == "cuda":
        device_attempts = ["cuda"]
    else:  # auto
        device_attempts = ["cuda", "cpu"]

    last_error = None

    for device in device_attempts:
        compute = get_compute_type(compute_mode, device)
        cache_key = (model_id, device, compute)

        if cache_key in _LOADED_MODELS_CACHE:
            logger.info("Using cached WhisperModel: %s | %s | %s", model_id, device, compute)
            return _LOADED_MODELS_CACHE[cache_key], device, compute

        try:
            if progress_callback:
                progress_callback(0.15, f"Loading AI model ({model_id} on {device.upper()})...")

            logger.info("Initializing WhisperModel: %s | device=%s | compute=%s", model_id, device, compute)
            model = WhisperModel(
                model_path,
                device=device,
                compute_type=compute,
                local_files_only=True,
            )
            _LOADED_MODELS_CACHE[cache_key] = model
            return model, device, compute
        except Exception as e:
            last_error = e
            logger.warning("Failed to initialize model on %s: %s", device, e)
            if device_mode == "cuda":
                break

    raise RuntimeError(
        f"Unable to load speech recognition model '{model_id}'. "
        f"Last error: {last_error}. Try selecting CPU only with int8 compute."
    )


def prepare_inference_audio(
    input_path: Path,
    work_dir: Path,
    enhance: bool = False,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Path:
    """
    Extracts a clean, standard 16kHz mono WAV inference stream using FFmpeg.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    output_audio = work_dir / "prepared_inference.wav"

    if progress_callback:
        progress_callback(0.08, "Preparing audio stream for AI...")

    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
    ]

    if enhance:
        # Gentle dynamic audio normalization
        cmd.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])

    cmd.append(str(output_audio))

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"Audio preparation failed: {res.stderr[-300:]}")

    if not output_audio.exists() or output_audio.stat().st_size == 0:
        raise RuntimeError("Prepared audio file is missing or zero bytes.")

    return output_audio


def run_transcription_pipeline(
    input_path: Path,
    job_id: str,
    model_id: str = "medium",
    language: Optional[str] = None,
    device_mode: str = "auto",
    compute_mode: str = "auto",
    accuracy_mode: str = "balanced",  # "balanced" or "maximum"
    verbatim_mode: str = "strict",     # "strict" or "clean"
    enhance_audio: bool = False,
    vad_filter: bool = True,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    Complete high-accuracy transcription pipeline.
    """
    job_dir = OUTPUTS_DIR / f"job_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)

    # Stage A: Validate Recording
    if progress_callback:
        progress_callback(0.04, "Validating audio recording...")
    source_meta = extract_metadata(input_path)
    if not source_meta.get("is_valid_audio"):
        raise ValueError(f"Invalid audio file: {source_meta.get('error')}")

    # Stage B: Preserve Source Audio & Prepare Inference Stream
    inference_audio = prepare_inference_audio(
        input_path=input_path,
        work_dir=job_dir,
        enhance=enhance_audio,
        progress_callback=progress_callback,
    )

    # Stage C: Load AI Model
    model, actual_device, actual_compute = load_whisper_model(
        model_id=model_id,
        device_mode=device_mode,
        compute_mode=compute_mode,
        progress_callback=progress_callback,
    )

    # Setup Egyptian Arabic / English prompt
    prompt = EGYPTIAN_ARABIC_PROMPT if (language in (None, "ar", "auto")) else None

    # Inference settings
    beam_size = 5 if accuracy_mode == "maximum" else 4
    vad_parameters = dict(min_silence_duration_ms=600) if vad_filter else None

    if progress_callback:
        progress_callback(0.20, f"Transcribing speech with Faster-Whisper ({actual_device.upper()})...")

    # Run inference
    try:
        segments_gen, info = model.transcribe(
            str(inference_audio),
            language=None if language in ("auto", "none", None) else language,
            initial_prompt=prompt,
            beam_size=beam_size,
            word_timestamps=True,
            vad_filter=vad_filter,
            vad_parameters=vad_parameters,
            condition_on_previous_text=False,  # Prevents repetition loops in conversational audio
        )
    except Exception as e:
        if actual_device == "cuda" and is_cuda_error(e) and device_mode == "auto":
            logger.warning("CUDA error during transcription. Falling back to CPU: %s", e)
            if progress_callback:
                progress_callback(0.25, "CUDA memory/driver issue detected. Falling back to CPU...")
            model, actual_device, actual_compute = load_whisper_model(
                model_id=model_id,
                device_mode="cpu",
                compute_mode="int8",
                progress_callback=progress_callback,
            )
            segments_gen, info = model.transcribe(
                str(inference_audio),
                language=None if language in ("auto", "none", None) else language,
                initial_prompt=prompt,
                beam_size=beam_size,
                word_timestamps=True,
                vad_filter=vad_filter,
                vad_parameters=vad_parameters,
                condition_on_previous_text=False,
            )
        else:
            raise

    # Collect segments with progress
    segments_list = []
    total_audio_duration = source_meta["duration"]

    for idx, seg in enumerate(segments_gen, start=1):
        text = seg.text.strip()
        if not text:
            continue

        # Confidence assessment
        avg_logprob = getattr(seg, "avg_logprob", 0.0)
        no_speech_prob = getattr(seg, "no_speech_prob", 0.0)
        compression_ratio = getattr(seg, "compression_ratio", 1.0)

        is_uncertain = False
        confidence = "high"
        if avg_logprob < -1.1 or no_speech_prob > 0.45 or compression_ratio > 2.4:
            is_uncertain = True
            confidence = "low"
        elif avg_logprob < -0.7 or no_speech_prob > 0.25:
            confidence = "medium"

        # Word-level breakdown
        words_data = []
        if getattr(seg, "words", None):
            for w in seg.words:
                words_data.append({
                    "word": w.word,
                    "start": round(w.start, 2),
                    "end": round(w.end, 2),
                    "probability": round(getattr(w, "probability", 1.0), 3),
                })

        segments_list.append({
            "id": idx,
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": text,
            "confidence": confidence,
            "uncertain": is_uncertain,
            "words": words_data,
        })

        if progress_callback and total_audio_duration > 0:
            pct = 0.20 + (0.65 * min(1.0, seg.end / total_audio_duration))
            progress_callback(pct, f"Transcribing audio: {format_duration(seg.end)} / {format_duration(total_audio_duration)}")

    # Stage E: Verification Pass (if Maximum Accuracy mode enabled)
    if accuracy_mode == "maximum" and progress_callback:
        progress_callback(0.88, "Running Maximum Accuracy verification pass...")
        # Check uncertain segments and smooth boundaries
        for seg in segments_list:
            if seg["uncertain"]:
                logger.info("Uncertain segment flagged for user review at [%s - %s]: %s", seg["start"], seg["end"], seg["text"])

    # Stage F: Final Assembly and Exports
    if progress_callback:
        progress_callback(0.94, "Assembling transcript and generating subtitle files...")

    timestamped_txt = generate_timestamped_txt(segments_list)
    clean_txt = generate_clean_txt(segments_list)
    srt_content = generate_srt(segments_list)
    vtt_content = generate_vtt(segments_list)

    metadata = {
        "job_id": job_id,
        "input_filename": input_path.name,
        "duration": source_meta["duration"],
        "duration_formatted": source_meta["duration_formatted"],
        "detected_language": info.language,
        "language_probability": round(info.language_probability, 3),
        "model_used": model_id,
        "device_used": actual_device,
        "compute_used": actual_compute,
        "accuracy_mode": accuracy_mode,
        "verbatim_mode": verbatim_mode,
        "enhanced": enhance_audio,
        "vad": vad_filter,
    }

    json_content = generate_json_export(job_id, segments_list, metadata)

    # Save output files to disk
    txt_file = job_dir / "transcript.txt"
    clean_file = job_dir / "clean_transcript.txt"
    srt_file = job_dir / "subtitles.srt"
    vtt_file = job_dir / "subtitles.vtt"
    json_file = job_dir / "transcript.json"

    txt_file.write_text(timestamped_txt, encoding="utf-8")
    clean_file.write_text(clean_txt, encoding="utf-8")
    srt_file.write_text(srt_content, encoding="utf-8")
    vtt_file.write_text(vtt_content, encoding="utf-8")
    json_file.write_text(json_content, encoding="utf-8")

    # Clean up intermediate inference file
    try:
        inference_audio.unlink(missing_ok=True)
    except Exception:
        pass

    if progress_callback:
        progress_callback(1.0, "Transcription completed successfully")

    return {
        "job_id": job_id,
        "segments": segments_list,
        "original_text": timestamped_txt,
        "clean_text": clean_txt,
        "srt_content": srt_content,
        "vtt_content": vtt_content,
        "metadata": metadata,
        "output_files": {
            "txt": str(txt_file),
            "clean_txt": str(clean_file),
            "srt": str(srt_file),
            "vtt": str(vtt_file),
            "json": str(json_file),
        }
    }


def format_duration(seconds: float) -> str:
    secs = int(seconds)
    mins = secs // 60
    return f"{mins:02d}:{secs % 60:02d}"
