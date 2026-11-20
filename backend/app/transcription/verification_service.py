import os
import sys
import time
import json
import uuid
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

from app.core.config import STORAGE_DIR, SUPPORTED_MODELS
from app.core.database import (
    get_job,
    get_transcript,
    save_alternative_hypothesis,
    get_alternative_hypotheses,
    save_segment_review,
    get_segment_reviews,
)
from app.audio.segment_extractor import extract_audio_slice
from app.evaluation.diff_engine import compute_transcript_diff
from app.transcription.engine import run_transcription_pipeline, is_model_downloaded
from app.api.benchmark import run_qwencleo_benchmark

logger = logging.getLogger("verbatim.verification_service")

# Sequential GPU lock to guarantee never running multiple heavy models simultaneously on the 4GB RTX 3050 GPU
_GPU_VERIFICATION_LOCK = threading.Lock()


def run_segment_verification(
    job_id: str,
    segment_id: int,
    model_id: str = "qwencleo-asr-4bit",
    context_padding: float = 1.0,
    device_mode: str = "cuda_only",
    force_recompute: bool = False,
) -> Dict[str, Any]:
    """
    Executes an audio-grounded second-pass verification on a specific transcript segment.
    - Retrieves original audio file from job record.
    - Checks cache to avoid duplicate GPU runs.
    - Extracts context-padded audio slice from original audio.
    - Executes target model sequentially under GPU lock.
    - Computes Unicode-aware text diff and disagreement score against primary ASR text.
    - Persists alternative hypothesis to database.
    - Updates segment review status.
    - Frees all temporary audio and releases GPU memory.
    """
    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")

    tr = get_transcript(job_id)
    if not tr:
        raise ValueError(f"Transcript data not found for job: {job_id}")

    segments = tr.get("segments", [])
    target_segment = next((s for s in segments if s.get("id") == segment_id), None)
    if not target_segment:
        raise ValueError(f"Segment #{segment_id} not found in transcript for job {job_id}")

    source_audio = Path(job["input_path"]).resolve()
    if not source_audio.is_file():
        raise FileNotFoundError(f"Original source audio not found at {source_audio}")

    start_t = float(target_segment.get("start", 0.0))
    end_t = float(target_segment.get("end", 0.0))
    seg_duration = max(0.2, end_t - start_t)
    primary_text = target_segment.get("original_text") or target_segment.get("text", "")

    # Validate target model
    if model_id not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported verification model: {model_id}")

    if not is_model_downloaded(model_id):
        raise ValueError(f"Model '{model_id}' is not downloaded locally.")

    model_info = SUPPORTED_MODELS[model_id]
    model_name = model_info.get("name", model_id)

    # Check cache for existing hypothesis on identical boundaries & model
    if not force_recompute:
        existing_hyps = get_alternative_hypotheses(job_id, segment_id)
        for h in existing_hyps:
            if (
                h.get("model_id") == model_id
                and abs(h.get("context_padding", 0.0) - context_padding) < 0.05
                and abs(h.get("start_time", 0.0) - start_t) < 0.05
                and abs(h.get("end_time", 0.0) - end_t) < 0.05
            ):
                logger.info(f"Returning cached alternative hypothesis for job {job_id} seg #{segment_id} model {model_id}")
                return {
                    "status": "success",
                    "is_cached": True,
                    "hypothesis_id": h["id"],
                    "job_id": job_id,
                    "segment_id": segment_id,
                    "model_id": model_id,
                    "model_name": model_name,
                    "start_time": start_t,
                    "end_time": end_t,
                    "extracted_start": h["extracted_start"],
                    "extracted_end": h["extracted_end"],
                    "context_padding": context_padding,
                    "hypothesis_text": h["hypothesis_text"],
                    "primary_text": h["primary_text"],
                    "diff": h.get("diff", []),
                    "disagreement_score": h.get("disagreement_score", 0.0),
                    "device_used": h.get("device_used"),
                    "compute_used": h.get("compute_used"),
                    "elapsed_seconds": h.get("elapsed_seconds", 0.0),
                }

    # Extract audio slice
    temp_slice, extracted_start, extracted_end = extract_audio_slice(
        source_audio_path=source_audio,
        start=start_t,
        end=end_t,
        padding=context_padding,
    )
    extracted_duration = extracted_end - extracted_start

    # Run inference sequentially under GPU lock
    t0 = time.time()
    hyp_text = ""
    device_used = "cuda"
    compute_used = "auto"
    peak_vram_mb = 0.0

    try:
        with _GPU_VERIFICATION_LOCK:
            logger.info(f"Acquired GPU lock for verification: job {job_id} seg #{segment_id} with {model_id}")

            if model_id == "qwencleo-asr-4bit":
                qwen_res = run_qwencleo_benchmark(
                    active_audio=temp_slice,
                    duration=extracted_duration,
                    device_mode=device_mode,
                )
                hyp_text = qwen_res.get("text", "")
                device_used = qwen_res.get("device", "cuda")
                compute_used = qwen_res.get("compute", "4-bit NF4")
                peak_vram_mb = qwen_res.get("peak_vram_mb", 0.0)
            else:
                # Faster-Whisper pipeline
                res = run_transcription_pipeline(
                    input_path=temp_slice,
                    job_id=f"verify_{job_id[:6]}_{segment_id}_{int(time.time())}",
                    model_id=model_id,
                    language="ar",
                    device_mode=device_mode,
                    compute_mode="auto",
                    accuracy_mode="maximum",
                    verbatim_mode="strict",
                    enhance_audio=False,
                    vad_filter=False,
                    vocabulary_hints=None,
                )
                hyp_text = res["clean_text"]
                meta = res.get("metadata", {})
                device_used = meta.get("device_used", "cuda")
                compute_used = meta.get("compute_used", "auto")

    finally:
        # Cleanup temporary audio slice immediately
        if temp_slice.exists():
            temp_slice.unlink(missing_ok=True)

    elapsed = round(time.time() - t0, 2)

    # Compute text diff and disagreement score
    diff_res = compute_transcript_diff(primary_text, hyp_text)
    disagreement_score = diff_res["disagreement_score"]
    diff_chunks = diff_res["chunks"]

    # Persist alternative hypothesis
    hyp_id = f"hyp_{uuid.uuid4().hex[:12]}"
    save_alternative_hypothesis(
        hypothesis_id=hyp_id,
        job_id=job_id,
        segment_id=segment_id,
        model_id=model_id,
        model_name=model_name,
        start_time=start_t,
        end_time=end_t,
        extracted_start=extracted_start,
        extracted_end=extracted_end,
        context_padding=context_padding,
        hypothesis_text=hyp_text,
        cleaned_hypothesis=hyp_text,
        primary_text=primary_text,
        diff_data=diff_chunks,
        disagreement_score=disagreement_score,
        device_used=device_used,
        compute_used=compute_used,
        elapsed_seconds=elapsed,
    )

    # Update segment review status
    flags = []
    if disagreement_score >= 0.25:
        flags.append("model_disagreement")

    existing_reviews = get_segment_reviews(job_id)
    prev_rev = existing_reviews.get(segment_id)
    if prev_rev:
        prev_flags = prev_rev.get("flag_reasons", [])
        for pf in prev_flags:
            if pf not in flags:
                flags.append(pf)

    new_status = "alternative_available"
    if prev_rev and prev_rev.get("review_status") == "human_reviewed":
        new_status = "human_reviewed"

    save_segment_review(
        job_id=job_id,
        segment_id=segment_id,
        review_status=new_status,
        flag_reasons=flags,
        selected_alternative_id=hyp_id,
    )

    return {
        "status": "success",
        "is_cached": False,
        "hypothesis_id": hyp_id,
        "job_id": job_id,
        "segment_id": segment_id,
        "model_id": model_id,
        "model_name": model_name,
        "start_time": start_t,
        "end_time": end_t,
        "extracted_start": extracted_start,
        "extracted_end": extracted_end,
        "context_padding": context_padding,
        "hypothesis_text": hyp_text,
        "primary_text": primary_text,
        "diff": diff_chunks,
        "disagreement_score": disagreement_score,
        "device_used": device_used,
        "compute_used": compute_used,
        "elapsed_seconds": elapsed,
        "peak_vram_mb": peak_vram_mb,
    }
