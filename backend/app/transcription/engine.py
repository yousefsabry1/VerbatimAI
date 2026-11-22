import os
import sys
import gc
import shutil
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable

from app.core.cuda_init import register_nvidia_dll_directories
register_nvidia_dll_directories()

from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download
from app.transcription.repetition_detector import detect_repetition_in_segment

from app.core.config import (
    MODELS_DIR,
    OUTPUTS_DIR,
    SUPPORTED_MODELS,
    DEFAULT_VOCAB_HINTS,
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


def clear_loaded_models_cache():
    """Explicitly releases all cached models from memory and triggers CUDA cache cleanup."""
    global _LOADED_MODELS_CACHE
    _LOADED_MODELS_CACHE.clear()
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass



def sanitize_name(name: str) -> str:
    return str(name).replace("/", "_").replace("\\", "_").replace(":", "_")


def get_model_dir(model_id: str) -> Path:
    if model_id == "codeswitched-medium-recovery":
        return MODELS_DIR / sanitize_name("codeswitched-medium")
    return MODELS_DIR / sanitize_name(model_id)


def is_model_downloaded(model_id: str) -> bool:
    if model_id in ("hybrid-v1", "hybrid-v2", "hybrid-v3"):
        return is_model_downloaded("codeswitched-medium") and is_model_downloaded("large-v3-turbo")
    if model_id == "codeswitched-medium-recovery":
        return is_model_downloaded("codeswitched-medium")
    if model_id == "qwencleo-asr-4bit":
        target_dir = MODELS_DIR / "qwencleo-asr"
        return (target_dir / "model.safetensors").exists() and (target_dir / "config.json").exists()
    target_dir = get_model_dir(model_id)
    marker = target_dir / ".ready"
    if marker.exists():
        return True
    if (target_dir / "model.bin").exists() and (target_dir / "config.json").exists():
        return True
    if (target_dir / "model.safetensors").exists() and (target_dir / "config.json").exists():
        return True
    return False


def get_model_folder_size_gb(model_id: str) -> float:
    if model_id in ("hybrid-v1", "hybrid-v2", "hybrid-v3"):
        return round(get_model_folder_size_gb("codeswitched-medium") + get_model_folder_size_gb("large-v3-turbo"), 2)
    if model_id == "codeswitched-medium-recovery":
        return get_model_folder_size_gb("codeswitched-medium")
    if model_id == "qwencleo-asr-4bit":
        target_dir = MODELS_DIR / "qwencleo-asr"
    else:
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

    if model_id in ("hybrid-v1", "hybrid-v2", "hybrid-v3"):
        raise RuntimeError(f"Hybrid ASR model {model_id} combines existing installed models and does not require separate download.")

    if model_id == "qwencleo-asr-4bit":
        raise RuntimeError(
            "Auto-download is disabled for experimental QwenCleo 4-bit model. "
            "Please install weights manually into storage/models/qwencleo-asr/."
        )

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
        logger.warning("Standard snapshot_download failed for %s (%s). Attempting resilient TLS 1.2 download...", model_id, e)
        if progress_callback:
            progress_callback(0.10, f"Attempting resilient download for {model_info['name']}...")
        
        try:
            _resilient_download(repo_id, target_dir, progress_callback)
            (target_dir / ".ready").write_text(f"ready={model_id}\nrepo={repo_id}\n", encoding="utf-8")
            if progress_callback:
                progress_callback(1.0, f"Model {model_info['name']} ready")
            return target_dir
        except Exception as e2:
            logger.error("Failed to download model %s: %s | Resilient error: %s", model_id, e, e2)
            raise RuntimeError(f"Model download failed: {e2}")


def _resilient_download(repo_id: str, target_dir: Path, progress_callback: Optional[Callable[[float, str], None]] = None):
    import ssl
    import time
    import urllib.request
    
    ctx = ssl.create_default_context()
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), _NoRedirect)

    def _resolve(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with opener.open(req, timeout=20) as resp:
                return resp.geturl()
        except urllib.error.HTTPError as err:
            if err.code in (301, 302, 303, 307, 308):
                return err.headers.get("Location")
            raise

    # Download required files
    files = [
        (f"https://huggingface.co/{repo_id}/raw/main/config.json", target_dir / "config.json", False),
        (f"https://huggingface.co/{repo_id}/raw/main/vocabulary.json", target_dir / "vocabulary.json", False),
        (f"https://huggingface.co/{repo_id}/raw/main/README.md", target_dir / "README.md", False),
        (f"https://huggingface.co/{repo_id}/resolve/main/model.bin", target_dir / "model.bin", True),
    ]

    for idx, (url, dest, is_lfs) in enumerate(files, 1):
        if dest.exists() and dest.stat().st_size > 0 and not is_lfs:
            continue
        final_url = _resolve(url) if is_lfs else url
        req = urllib.request.Request(final_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            if dest.exists() and total > 0 and dest.stat().st_size == total:
                continue
            part = dest.with_suffix(dest.suffix + ".part")
            downloaded = 0
            with open(part, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 512)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total > 0 and is_lfs:
                        p = 0.10 + 0.85 * (downloaded / total)
                        progress_callback(p, f"Downloading {dest.name}: {downloaded // (1024*1024)}MB / {total // (1024*1024)}MB")
            part.replace(dest)


def get_compute_type(compute_mode: str, device: str) -> str:
    if compute_mode in ("float16", "int8_float16", "int8"):
        return compute_mode
    # Auto logic
    if device == "cuda":
        # int8_float16 provides maximum throughput and uses ~1.0GB VRAM, ideal for 4GB RTX 3050 Laptop GPU
        return "int8_float16"
    return "int8"


def is_cuda_error(err: Exception) -> bool:
    msg = (str(err) + " " + repr(err)).lower()
    keywords = [
        "cublas", "cudnn", "cudart", "cuda", "nvrtc", "driver",
        "out of memory", "oom", "illegal memory access",
        "device-side assert", "failed to load", "not found",
        "ctranslate2::cuda"
    ]
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

    # Force CPU Safe Mode if environment variable is set
    if os.environ.get("VERBATIM_FORCE_CPU") == "1":
        device_mode = "cpu"

    if device_mode == "cpu":
        device_attempts = ["cpu"]
    elif device_mode in ("cuda", "cuda_only"):
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

            # Enforce sequential GPU safety on RTX 3050 (4GB VRAM):
            # Guarantee QwenCleo persistent worker VRAM is 100% released before Whisper allocates CUDA memory
            if device == "cuda":
                try:
                    from app.transcription.qwencleo_client import get_qwencleo_client
                    qw_client = get_qwencleo_client()
                    if qw_client.is_alive():
                        logger.info("Releasing QwenCleo worker VRAM before loading Faster-Whisper on CUDA...")
                        qw_client.shutdown()
                except Exception as qw_rel_err:
                    logger.debug("QwenCleo release check note: %s", qw_rel_err)

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
            if device_mode in ("cuda", "cuda_only"):
                break

    if device_mode == "cuda_only":
        raise RuntimeError(
            f"GPU-Only Diagnostic Mode Failure: CUDA is required but model '{model_id}' failed to load: {last_error}"
        )

    raise RuntimeError(
        f"Unable to load speech recognition model '{model_id}'. "
        f"Last error: {last_error}. Try selecting CPU only with int8 compute."
    )


def log_device_transition(
    job_id: str,
    prev_device: str,
    new_device: str,
    stage: str,
    model_id: str,
    compute_type: str,
    reason: str,
    exception: Optional[Exception] = None,
) -> Dict[str, Any]:
    tb_str = None
    if exception:
        import traceback
        tb_str = traceback.format_exc()

    vram_info = None
    try:
        if shutil.which("nvidia-smi"):
            cmd = ["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                if len(parts) >= 2:
                    vram_info = f"Used: {parts[0]} MB, Free: {parts[1]} MB"
    except Exception:
        pass

    transition_record = {
        "timestamp": datetime.utcnow().isoformat(),
        "job_id": job_id,
        "previous_device": prev_device,
        "new_device": new_device,
        "stage": stage,
        "model_id": model_id,
        "compute_type": compute_type,
        "reason": reason,
        "vram_status": vram_info,
        "exception": str(exception) if exception else None,
        "traceback": tb_str,
        "cpu_fallback_activated": (new_device.startswith("cpu") and prev_device == "cuda"),
    }
    logger.warning("DEVICE TRANSITION [%s -> %s] at stage '%s': %s (VRAM: %s)",
                   prev_device, new_device, stage, reason, vram_info)
    return transition_record


def retry_segment_without_loops(
    model: WhisperModel,
    audio_path: Path,
    start: float,
    end: float,
    target_lang: Optional[str] = None,
    beam_size: int = 5,
    vad_parameters: Optional[Dict[str, Any]] = None,
    job_dir: Optional[Path] = None,
) -> Optional[str]:
    """
    Retries transcribing a problematic segment where a pathological repetition loop was detected.
    Applies aggressive anti-repetition decoding without prompt bias.
    """
    if end <= start:
        return None

    pad_start = max(0.0, start - 0.2)
    pad_duration = max(0.5, (end - start) + 0.4)
    work_dir = job_dir or OUTPUTS_DIR
    slice_file = work_dir / f"loop_retry_{int(start * 1000)}_{int(end * 1000)}.wav"

    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-ss", str(pad_start),
        "-t", str(pad_duration),
        "-i", str(audio_path),
        "-vn", "-ac", "1", "-ar", "16000",
        str(slice_file),
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        gen, _ = model.transcribe(
            str(slice_file),
            language=target_lang,
            initial_prompt=None,
            beam_size=beam_size,
            temperature=[0.2, 0.4],
            repetition_penalty=1.20,
            no_repeat_ngram_size=3,
            compression_ratio_threshold=2.2,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        resolved_parts = [s.text.strip() for s in gen if s.text.strip()]
        return " ".join(resolved_parts)
    except Exception as e:
        logger.warning("Repetition retry failed on [%.2f -> %.2f]: %s", start, end, e)
        return None
    finally:
        slice_file.unlink(missing_ok=True)


def verify_segment_accuracy(
    model: WhisperModel,
    audio_path: Path,
    start: float,
    end: float,
    target_lang: Optional[str] = None,
    job_dir: Optional[Path] = None,
) -> Optional[str]:
    """
    Maximum Accuracy verification: re-evaluates low-confidence segments
    using the active model on the active device without consuming extra VRAM or switching devices.
    """
    if end <= start:
        return None

    pad_start = max(0.0, start - 0.1)
    pad_duration = max(0.4, (end - start) + 0.2)
    work_dir = job_dir or OUTPUTS_DIR
    slice_file = work_dir / f"verify_{int(start * 1000)}_{int(end * 1000)}.wav"

    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-ss", str(pad_start),
        "-t", str(pad_duration),
        "-i", str(audio_path),
        "-vn", "-ac", "1", "-ar", "16000",
        str(slice_file),
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        gen, _ = model.transcribe(
            str(slice_file),
            language=target_lang,
            initial_prompt=None,
            beam_size=5,
            temperature=[0.0, 0.2],
            repetition_penalty=1.10,
            no_repeat_ngram_size=3,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        parts = [s.text.strip() for s in gen if s.text.strip()]
        return " ".join(parts)
    except Exception as e:
        logger.warning("Segment verification failed on [%.2f -> %.2f]: %s", start, end, e)
        return None
    finally:
        slice_file.unlink(missing_ok=True)


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
    model_id: str = "codeswitched-medium",
    language: Optional[str] = None,
    device_mode: str = "auto",
    compute_mode: str = "auto",
    accuracy_mode: str = "balanced",  # "balanced" or "maximum"
    verbatim_mode: str = "strict",     # "strict" or "clean"
    enhance_audio: bool = False,
    vad_filter: bool = True,
    vocabulary_hints: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    Complete high-accuracy transcription pipeline.
    """
    if os.environ.get("VERBATIM_FORCE_CPU") == "1":
        device_mode = "cpu"
        compute_mode = "int8"
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

    # Route Hybrid ASR Models to Dedicated Multi-Model Orchestrator
    if model_id.startswith("hybrid"):
        from app.transcription.hybrid_orchestrator import run_hybrid_transcription
        return run_hybrid_transcription(
            input_path=inference_audio,
            job_id=job_id,
            job_dir=job_dir,
            source_meta=source_meta,
            model_id=model_id,
            language=language,
            device_mode=device_mode,
            accuracy_mode=accuracy_mode,
            verbatim_mode=verbatim_mode,
            enhance_audio=enhance_audio,
            vad_filter=vad_filter,
            vocabulary_hints=vocabulary_hints,
            progress_callback=progress_callback,
        )

    # Route Standalone QwenCleo 4-bit Long-Form ASR
    if model_id == "qwencleo-asr-4bit":
        from app.transcription.hybrid_orchestrator import run_model_isolated
        if progress_callback:
            progress_callback(0.15, "Transcribing with QwenCleo 4-bit Long-Form ASR (NF4)...")
        total_duration = max(float(source_meta.get("duration") or 45.0), 1.0)
        q_res = run_model_isolated(
            model_id="qwencleo-asr-4bit",
            audio_path=inference_audio,
            duration_seconds=total_duration,
            device_mode=device_mode,
        )
        pred_text = q_res.get("text", "").strip()
        segments_list = [{
            "id": 1,
            "start": 0.0,
            "end": total_duration,
            "text": pred_text,
            "original_text": pred_text,
            "confidence": "high",
            "uncertain": False,
            "uncertain_reason": None,
            "avg_logprob": 0.0,
            "no_speech_prob": 0.0,
            "compression_ratio": 1.0,
            "repetition_resolved": False,
            "words": [],
        }]

        timestamped_txt = generate_timestamped_txt(segments_list)
        clean_txt = generate_clean_txt(segments_list)
        srt_content = generate_srt(segments_list)
        vtt_content = generate_vtt(segments_list)

        metadata = {
            "job_id": job_id,
            "input_filename": input_path.name,
            "duration": total_duration,
            "duration_formatted": source_meta.get("duration_formatted", ""),
            "detected_language": "ar",
            "language_probability": 1.0,
            "model_used": model_id,
            "device_used": "cuda" if device_mode != "cpu" else "cpu",
            "compute_used": "4-bit NF4",
            "initial_device": "cuda" if device_mode != "cpu" else "cpu",
            "cuda_fallback": False,
            "accuracy_mode": accuracy_mode,
            "verbatim_mode": verbatim_mode,
            "enhanced": enhance_audio,
            "vad": vad_filter,
            "engine_version": "1.3.0",
            "git_revision": "645b732",
            "processed_at": datetime.utcnow().isoformat(),
            "peak_vram_mb": q_res.get("peak_vram_mb", 0.0),
        }

        json_content = generate_json_export(job_id, segments_list, metadata)

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

        if progress_callback:
            progress_callback(1.0, "Transcription completed successfully")

        return {
            "job_id": job_id,
            "original_text": pred_text,
            "clean_text": clean_txt,
            "segments": segments_list,
            "srt_content": srt_content,
            "vtt_content": vtt_content,
            "output_files": {
                "txt": str(txt_file),
                "clean_txt": str(clean_file),
                "srt": str(srt_file),
                "vtt": str(vtt_file),
                "json": str(json_file),
            },
            "metadata": metadata,
        }

    # Stage C: Load AI Model
    model, actual_device, actual_compute = load_whisper_model(
        model_id=model_id,
        device_mode=device_mode,
        compute_mode=compute_mode,
        progress_callback=progress_callback,
    )

    # Setup Vocabulary Hints & Prompt
    # Clean domain recognition hints only — NEVER forced unless explicitly provided
    if vocabulary_hints and vocabulary_hints.strip():
        prompt = vocabulary_hints.strip()
    else:
        prompt = None

    # Language determination
    # For specialized Egyptian model or Arabic speech, pin target_lang to 'ar' to eliminate foreign script hallucinations
    if model_id in ("codeswitched-medium", "codeswitched-medium-recovery"):
        target_lang = "ar"
    elif language in ("auto", "none", None):
        target_lang = None
    else:
        target_lang = language

    # Inference settings with loop suppression & temperature fallback
    beam_size = 5 if accuracy_mode in ("maximum", "recovery") else 4
    vad_parameters = dict(min_silence_duration_ms=500, speech_pad_ms=300) if vad_filter else None
    condition_prev = False if accuracy_mode == "recovery" else True
    hotwords_param = prompt if (vocabulary_hints and vocabulary_hints.strip()) else None

    if progress_callback:
        progress_callback(0.20, f"Transcribing speech with Faster-Whisper ({actual_device.upper()})...")

    initial_device = actual_device
    initial_compute = actual_compute
    cuda_fallback_occurred = False
    cuda_fallback_error = None
    checkpoint_time = 0.0
    segments_list = []
    total_audio_duration = source_meta["duration"]
    device_transitions: List[Dict[str, Any]] = []
    repetition_loops_detected = 0
    repetition_loops_resolved = 0

    # Run inference with robust lazy generator error handling, repetition resolution, and checkpoint resumption
    try:
        segments_gen, info = model.transcribe(
            str(inference_audio),
            language=target_lang,
            initial_prompt=prompt if accuracy_mode != "recovery" else None,
            hotwords=hotwords_param,
            beam_size=beam_size,
            condition_on_previous_text=condition_prev,
            vad_filter=vad_filter,
            vad_parameters=vad_parameters,
            no_speech_threshold=0.8,
            word_timestamps=False,
        )

        for idx, seg in enumerate(segments_gen, start=1):
            # Test hook for simulating CUDA failure during generator iteration
            if (
                os.environ.get("VERBATIM_SIMULATE_CUDA_ERROR")
                and actual_device == "cuda"
                and len(segments_list) >= 1
            ):
                os.environ.pop("VERBATIM_SIMULATE_CUDA_ERROR", None)
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded (simulated CUDA generator failure)")

            text = seg.text.strip()
            if not text:
                continue

            # Pathological repetition loop detection & adaptive resolution
            rep_info = detect_repetition_in_segment(text)
            orig_loop_text = None
            is_rep_resolved = False
            if rep_info:
                repetition_loops_detected += 1
                logger.warning(
                    "Pathological repetition loop detected in segment [%.2f -> %.2f] ('%s' x%d): %s",
                    seg.start, seg.end, rep_info["pattern"], rep_info["repeats"], text[:60]
                )
                orig_loop_text = text
                retry_text = retry_segment_without_loops(
                    model=model,
                    audio_path=inference_audio,
                    start=seg.start,
                    end=seg.end,
                    target_lang=target_lang,
                    beam_size=beam_size,
                    vad_parameters=vad_parameters,
                    job_dir=job_dir,
                )
                if retry_text and not detect_repetition_in_segment(retry_text):
                    logger.info("Successfully resolved repetition loop: '%s' -> '%s'", text[:50], retry_text[:50])
                    text = retry_text
                    is_rep_resolved = True
                    repetition_loops_resolved += 1

            # Confidence assessment
            avg_logprob = getattr(seg, "avg_logprob", 0.0)
            no_speech_prob = getattr(seg, "no_speech_prob", 0.0)
            compression_ratio = getattr(seg, "compression_ratio", 1.0)

            is_uncertain = False
            confidence = "high"
            if avg_logprob < -1.1 or no_speech_prob > 0.45 or compression_ratio > 2.2 or (rep_info and not is_rep_resolved):
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

            uncertain_reason = None
            if avg_logprob < -1.1:
                uncertain_reason = "low_acoustic_confidence"
            elif no_speech_prob > 0.45:
                uncertain_reason = "potential_background_noise"
            elif compression_ratio > 2.2:
                uncertain_reason = "possible_repetitive_loop"
            elif rep_info and not is_rep_resolved:
                uncertain_reason = "unresolved_repetition_loop"

            segments_list.append({
                "id": len(segments_list) + 1,
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": text,
                "original_text": text,
                "confidence": confidence,
                "uncertain": is_uncertain,
                "uncertain_reason": uncertain_reason,
                "avg_logprob": round(avg_logprob, 3),
                "no_speech_prob": round(no_speech_prob, 3),
                "compression_ratio": round(compression_ratio, 3),
                "repetition_resolved": is_rep_resolved,
                "original_loop_text": orig_loop_text,
                "words": words_data,
            })

            checkpoint_time = round(seg.end, 2)

            if progress_callback and total_audio_duration > 0:
                pct = 0.20 + (0.65 * min(1.0, seg.end / total_audio_duration))
                progress_callback(pct, f"Transcribing audio: {format_duration(seg.end)} / {format_duration(total_audio_duration)}")

    except Exception as e:
        if actual_device == "cuda" and is_cuda_error(e):
            if device_mode == "cuda_only":
                trans = log_device_transition(
                    job_id=job_id,
                    prev_device="cuda",
                    new_device="cuda (FAILED - GPU Only Mode)",
                    stage="lazy_generator_iteration",
                    model_id=model_id,
                    compute_type=actual_compute,
                    reason=f"CUDA failure in GPU-Only diagnostic mode: {e}",
                    exception=e,
                )
                device_transitions.append(trans)
                logger.error("GPU-Only Diagnostic Mode: CUDA failure encountered at t=%.2fs. Halting without CPU fallback: %s", checkpoint_time, e)
                raise RuntimeError(f"GPU-Only Diagnostic Mode Failure at t={checkpoint_time:.2f}s: {e}")

            # Auto mode: Proceed with graceful CPU fallback
            logger.warning(
                "CUDA runtime error encountered during inference at t=%.2fs: %s. Initiating graceful CPU fallback...",
                checkpoint_time, e
            )
            cuda_fallback_occurred = True
            cuda_fallback_error = str(e)

            trans = log_device_transition(
                job_id=job_id,
                prev_device="cuda",
                new_device="cpu",
                stage="lazy_generator_iteration",
                model_id=model_id,
                compute_type="int8",
                reason=f"CUDA error fallback: {e}",
                exception=e,
            )
            device_transitions.append(trans)

            if progress_callback:
                progress_callback(
                    min(0.85, 0.20 + (0.65 * min(1.0, checkpoint_time / max(1.0, total_audio_duration)))),
                    f"CUDA GPU error at {format_duration(checkpoint_time)}. Switching to CPU and resuming..."
                )

            # Release GPU resources safely
            try:
                cache_key = (model_id, "cuda", actual_compute)
                _LOADED_MODELS_CACHE.pop(cache_key, None)
                del model
            except Exception:
                pass
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

            # Load CPU model
            cpu_model, actual_device, actual_compute = load_whisper_model(
                model_id=model_id,
                device_mode="cpu",
                compute_mode="int8",
                progress_callback=progress_callback,
            )

            # Determine remaining audio to transcribe
            remaining_duration = total_audio_duration - checkpoint_time
            if remaining_duration > 0.3:
                logger.info(
                    "Resuming remaining %.2fs audio on CPU from checkpoint t=%.2fs",
                    remaining_duration, checkpoint_time
                )
                remaining_audio = job_dir / f"resumed_from_{int(checkpoint_time * 1000)}ms.wav"
                ffmpeg = find_ffmpeg()
                cmd = [
                    ffmpeg, "-y",
                    "-ss", str(checkpoint_time),
                    "-i", str(inference_audio),
                    "-vn", "-ac", "1", "-ar", "16000",
                    str(remaining_audio),
                ]
                sub_res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
                if sub_res.returncode != 0:
                    logger.error("FFmpeg slice failed: %s", sub_res.stderr)
                    raise RuntimeError(f"Failed to slice audio for fallback: {sub_res.stderr[-200:]}")

                cpu_segments_gen, cpu_info = cpu_model.transcribe(
                    str(remaining_audio),
                    language=target_lang,
                    initial_prompt=prompt if accuracy_mode != "recovery" else None,
                    hotwords=hotwords_param,
                    beam_size=beam_size,
                    condition_on_previous_text=condition_prev,
                    vad_filter=vad_filter,
                    vad_parameters=vad_parameters,
                    no_speech_threshold=0.8,
                    word_timestamps=False,
                )

                if 'info' not in locals():
                    info = cpu_info

                for seg in cpu_segments_gen:
                    text = seg.text.strip()
                    if not text:
                        continue

                    adj_start = round(seg.start + checkpoint_time, 2)
                    adj_end = round(seg.end + checkpoint_time, 2)

                    # Smooth boundary handling: prevent overlap with previous segment
                    if segments_list and adj_start < segments_list[-1]["end"]:
                        if adj_end <= segments_list[-1]["end"]:
                            continue
                        adj_start = segments_list[-1]["end"]

                    # Pathological repetition loop detection on CPU
                    rep_info = detect_repetition_in_segment(text)
                    orig_loop_text = None
                    is_rep_resolved = False
                    if rep_info:
                        repetition_loops_detected += 1
                        logger.warning("Pathological repetition loop in CPU fallback [%.2f -> %.2f]", adj_start, adj_end)
                        orig_loop_text = text
                        retry_text = retry_segment_without_loops(
                            model=cpu_model,
                            audio_path=inference_audio,
                            start=adj_start,
                            end=adj_end,
                            target_lang=target_lang,
                            beam_size=beam_size,
                            vad_parameters=vad_parameters,
                            job_dir=job_dir,
                        )
                        if retry_text and not detect_repetition_in_segment(retry_text):
                            text = retry_text
                            is_rep_resolved = True
                            repetition_loops_resolved += 1

                    avg_logprob = getattr(seg, "avg_logprob", 0.0)
                    no_speech_prob = getattr(seg, "no_speech_prob", 0.0)
                    compression_ratio = getattr(seg, "compression_ratio", 1.0)

                    is_uncertain = False
                    confidence = "high"
                    if avg_logprob < -1.1 or no_speech_prob > 0.45 or compression_ratio > 2.2 or (rep_info and not is_rep_resolved):
                        is_uncertain = True
                        confidence = "low"
                    elif avg_logprob < -0.7 or no_speech_prob > 0.25:
                        confidence = "medium"

                    words_data = []
                    if getattr(seg, "words", None):
                        for w in seg.words:
                            words_data.append({
                                "word": w.word,
                                "start": round(w.start + checkpoint_time, 2),
                                "end": round(w.end + checkpoint_time, 2),
                                "probability": round(getattr(w, "probability", 1.0), 3),
                            })

                    uncertain_reason = None
                    if avg_logprob < -1.1:
                        uncertain_reason = "low_acoustic_confidence"
                    elif no_speech_prob > 0.45:
                        uncertain_reason = "potential_background_noise"
                    elif compression_ratio > 2.2:
                        uncertain_reason = "possible_repetitive_loop"
                    elif rep_info and not is_rep_resolved:
                        uncertain_reason = "unresolved_repetition_loop"

                    segments_list.append({
                        "id": len(segments_list) + 1,
                        "start": adj_start,
                        "end": adj_end,
                        "text": text,
                        "original_text": text,
                        "confidence": confidence,
                        "uncertain": is_uncertain,
                        "uncertain_reason": uncertain_reason,
                        "avg_logprob": round(avg_logprob, 3),
                        "no_speech_prob": round(no_speech_prob, 3),
                        "compression_ratio": round(compression_ratio, 3),
                        "repetition_resolved": is_rep_resolved,
                        "original_loop_text": orig_loop_text,
                        "words": words_data,
                    })

                    if progress_callback and total_audio_duration > 0:
                        pct = 0.20 + (0.65 * min(1.0, adj_end / total_audio_duration))
                        progress_callback(pct, f"Transcribing audio (CPU): {format_duration(adj_end)} / {format_duration(total_audio_duration)}")

                try:
                    remaining_audio.unlink(missing_ok=True)
                except Exception:
                    pass
            else:
                logger.info("CUDA error occurred at end of audio (t=%.2fs). No remaining audio.", checkpoint_time)
        else:
            raise

    # Stage E: Verification Pass (if Maximum Accuracy mode enabled)
    # Re-evaluates uncertain segments using the active model on the active device without device switching
    if accuracy_mode == "maximum" and progress_callback:
        progress_callback(0.88, f"Running Maximum Accuracy verification pass on {actual_device.upper()}...")
        uncertain_segments = [s for s in segments_list if s["uncertain"]]
        logger.info("Maximum Accuracy verification: evaluating %d low-confidence segments on %s...",
                    len(uncertain_segments), actual_device.upper())
        active_model = model if actual_device == "cuda" else cpu_model
        for seg_item in uncertain_segments:
            try:
                verified_text = verify_segment_accuracy(
                    model=active_model,
                    audio_path=inference_audio,
                    start=seg_item["start"],
                    end=seg_item["end"],
                    target_lang=target_lang,
                    job_dir=job_dir,
                )
                if verified_text and verified_text.strip() and not detect_repetition_in_segment(verified_text):
                    logger.info("Segment [%.2f -> %.2f] verified: '%s' -> '%s'",
                                seg_item["start"], seg_item["end"], seg_item["text"][:40], verified_text[:40])
                    seg_item["text"] = verified_text.strip()
                    seg_item["uncertain"] = False
                    seg_item["is_verified"] = True
            except Exception as e:
                logger.warning("Verification error on segment %s: %s", seg_item["id"], e)

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
        "detected_language": getattr(info, "language", "ar") if 'info' in locals() else "ar",
        "language_probability": round(getattr(info, "language_probability", 1.0), 3) if 'info' in locals() else 1.0,
        "model_used": model_id,
        "device_used": actual_device,
        "compute_used": actual_compute,
        "initial_device": initial_device,
        "cuda_fallback": cuda_fallback_occurred,
        "cuda_fallback_error": cuda_fallback_error,
        "cuda_checkpoint_time": checkpoint_time if cuda_fallback_occurred else None,
        "device_transitions": device_transitions,
        "repetition_loops_detected": repetition_loops_detected,
        "repetition_loops_resolved": repetition_loops_resolved,
        "accuracy_mode": accuracy_mode,
        "verbatim_mode": verbatim_mode,
        "enhanced": enhance_audio,
        "vad": vad_filter,
        "engine_version": "1.3.0",
        "git_revision": "645b732",
        "processed_at": datetime.utcnow().isoformat(),
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
