import wave
import math
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from app.audio.metadata_extractor import find_ffmpeg

logger = logging.getLogger(__name__)


def compute_audio_energy_profile(
    audio_path: Path,
    frame_ms: float = 50.0,
    hop_ms: float = 25.0,
) -> Tuple[List[float], float, float]:
    """
    Computes RMS energy profile across audio frames.
    Returns: (frame_rms_values, hop_seconds, duration_seconds)
    """
    ffmpeg = find_ffmpeg()
    # Ensure 16kHz mono 16-bit PCM WAV for consistent processing
    temp_wav = audio_path.parent / f"cov_tmp_{audio_path.stem}.wav"
    try:
        cmd = [
            ffmpeg, "-y",
            "-i", str(audio_path),
            "-vn", "-ac", "1", "-ar", "16000",
            str(temp_wav),
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        with wave.open(str(temp_wav), "rb") as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        # Convert 16-bit PCM bytes to signed integers
        import array
        samples = array.array("h")
        samples.frombytes(raw)
        
        n_samples = len(samples)
        dur = n_samples / float(sr)
        frame_len = int(sr * (frame_ms / 1000.0))
        hop_len = int(sr * (hop_ms / 1000.0))

        rms_list = []
        for i in range(0, n_samples - frame_len, hop_len):
            chunk = samples[i : i + frame_len]
            # RMS computation
            sum_sq = sum(s * s for s in chunk)
            rms = math.sqrt(sum_sq / float(frame_len)) / 32768.0
            rms_list.append(rms)

        return rms_list, hop_ms / 1000.0, dur
    except Exception as e:
        logger.warning("Energy profile computation error for %s: %s", audio_path, e)
        return [], hop_ms / 1000.0, 0.0
    finally:
        temp_wav.unlink(missing_ok=True)


def extract_active_speech_intervals(
    rms_list: List[float],
    hop_sec: float,
    min_speech_duration: float = 0.40,
    min_pause_duration: float = 0.25,
) -> List[Tuple[float, float]]:
    """
    Extracts continuous speech activity intervals based on adaptive RMS thresholding.
    """
    if not rms_list:
        return []

    sorted_rms = sorted(rms_list)
    # Estimate baseline noise floor from bottom 25% percentile
    noise_floor_idx = int(len(sorted_rms) * 0.25)
    noise_floor = sorted_rms[noise_floor_idx] if sorted_rms else 0.001
    
    # Adaptive threshold: above noise floor and minimum audible energy
    threshold = max(0.008, noise_floor * 2.5)

    is_active = [r >= threshold for r in rms_list]

    # Bridge short pauses (< min_pause_duration)
    bridge_hops = int(min_pause_duration / hop_sec)
    n = len(is_active)
    i = 0
    while i < n:
        if not is_active[i]:
            pause_start = i
            while i < n and not is_active[i]:
                i += 1
            pause_end = i
            if (pause_end - pause_start) <= bridge_hops:
                for k in range(pause_start, pause_end):
                    is_active[k] = True
        else:
            i += 1

    # Extract contiguous intervals
    intervals = []
    in_interval = False
    start_hop = 0
    min_hops = int(min_speech_duration / hop_sec)

    for idx, act in enumerate(is_active):
        if act and not in_interval:
            in_interval = True
            start_hop = idx
        elif not act and in_interval:
            in_interval = False
            if (idx - start_hop) >= min_hops:
                intervals.append((round(start_hop * hop_sec, 2), round(idx * hop_sec, 2)))

    if in_interval and (len(is_active) - start_hop) >= min_hops:
        intervals.append((round(start_hop * hop_sec, 2), round(len(is_active) * hop_sec, 2)))

    return intervals


def detect_speech_coverage_gaps(
    audio_path: Optional[Path],
    segments: List[Dict[str, Any]],
    total_duration: Optional[float] = None,
    secondary_segments: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Speech Coverage Recovery: detects regions where audio energy indicates speech,
    but ASR output is sparse, missing, or omitted.
    Flags regions as 'Possible Missing Speech'.
    """
    coverage_issues: List[Dict[str, Any]] = []

    # 1. Acoustic Energy Gaps (if audio file provided)
    if audio_path and audio_path.exists():
        rms_list, hop_sec, audio_dur = compute_audio_energy_profile(audio_path)
        active_spans = extract_active_speech_intervals(rms_list, hop_sec)
        effective_dur = total_duration or audio_dur

        for act_s, act_e in active_spans:
            act_dur = act_e - act_s
            if act_dur < 1.0:
                continue

            # Check overlap with any recognized segment
            covered_duration = 0.0
            for seg in segments:
                seg_s = float(seg.get("start", 0.0))
                seg_e = float(seg.get("end", 0.0))
                # Compute overlap
                ov_s = max(act_s, seg_s)
                ov_e = min(act_e, seg_e)
                if ov_e > ov_s:
                    covered_duration += (ov_e - ov_s)

            coverage_ratio = covered_duration / act_dur if act_dur > 0 else 1.0
            # If an active speech span of >=1.2s has < 25% transcript coverage
            if act_dur >= 1.2 and coverage_ratio < 0.25:
                coverage_issues.append({
                    "type": "acoustic_energy_gap",
                    "flag_label": "Possible Missing Speech",
                    "start": act_s,
                    "end": act_e,
                    "duration": round(act_dur, 2),
                    "covered_duration": round(covered_duration, 2),
                    "coverage_ratio": round(coverage_ratio, 2),
                    "severity": "high" if act_dur >= 2.5 else "medium",
                    "reason": "acoustic_energy_detected_without_transcript",
                    "suggested_action": "targeted_acoustic_redecoding",
                })

    # 2. Segment-Level Sparse Speech Analysis
    for seg in segments:
        seg_s = float(seg.get("start", 0.0))
        seg_e = float(seg.get("end", 0.0))
        seg_dur = seg_e - seg_s
        text = seg.get("text", "").strip()
        word_count = len(text.split())

        # Anomaly A: Long segment (> 4.0s) with extremely low word density (< 0.8 words/s)
        words_per_sec = word_count / max(0.5, seg_dur)
        if seg_dur >= 4.0 and words_per_sec < 0.75 and word_count > 0:
            coverage_issues.append({
                "type": "sparse_speech_coverage",
                "segment_id": seg.get("id"),
                "flag_label": "Possible Missing Speech",
                "start": round(seg_s, 2),
                "end": round(seg_e, 2),
                "duration": round(seg_dur, 2),
                "word_count": word_count,
                "words_per_second": round(words_per_sec, 2),
                "severity": "medium",
                "reason": "unusually_sparse_text_for_acoustic_duration",
                "suggested_action": "context_window_redecoding",
            })

    # 3. Model Disparity Analysis (if secondary model results available)
    if secondary_segments:
        # Cross-reference secondary segments to find omissions
        for sec_seg in secondary_segments:
            sec_s = float(sec_seg.get("start", 0.0))
            sec_e = float(sec_seg.get("end", 0.0))
            sec_text = sec_seg.get("text", "").strip()
            sec_words = len(sec_text.split())

            if sec_words < 4:
                continue

            # Check overlap in primary segments
            prim_overlap_words = 0
            for prim_seg in segments:
                p_s = float(prim_seg.get("start", 0.0))
                p_e = float(prim_seg.get("end", 0.0))
                ov_s = max(sec_s, p_s)
                ov_e = min(sec_e, p_e)
                if ov_e > ov_s:
                    prim_overlap_words += len(prim_seg.get("text", "").split())

            # If secondary model produced significantly more text (> 3x) in this interval
            if sec_words >= 6 and prim_overlap_words <= 2:
                coverage_issues.append({
                    "type": "model_omission_disparity",
                    "flag_label": "Possible Missing Speech",
                    "start": round(sec_s, 2),
                    "end": round(sec_e, 2),
                    "duration": round(sec_e - sec_s, 2),
                    "secondary_word_count": sec_words,
                    "primary_word_count": prim_overlap_words,
                    "secondary_text": sec_text[:80],
                    "severity": "high",
                    "reason": "secondary_model_detected_speech_omitted_by_primary",
                    "suggested_action": "review_alternative_hypothesis",
                })

    return coverage_issues
