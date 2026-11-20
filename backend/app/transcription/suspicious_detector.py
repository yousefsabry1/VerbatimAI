import re
from typing import List, Dict, Any, Optional

from app.transcription.repetition_detector import detect_repetition_in_segment


def analyze_segment_for_review(
    segment: Dict[str, Any],
    prev_segment: Optional[Dict[str, Any]] = None,
    alternative_hypothesis: Optional[Dict[str, Any]] = None,
    review_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluates acoustic, structural, and disagreement signals for a single transcript segment.
    Returns:
      {
        "segment_id": int,
        "is_flagged": bool,
        "flag_reasons": List[str],
        "flag_label": str,
        "severity": "high" | "medium" | "low" | "none",
        "signals": Dict[str, Any]
      }
    """
    seg_id = segment.get("id", 0)
    text = segment.get("text", "").strip()
    flag_reasons: List[str] = []
    signals: Dict[str, Any] = {}

    # Signal 1: Repetition loop detection
    is_rep_resolved = bool(segment.get("repetition_resolved", False))
    rep_analysis = detect_repetition_in_segment(text)
    is_repeated = bool(rep_analysis) or is_rep_resolved

    if is_repeated:
        flag_reasons.append("repetition_suspected")
        signals["repetition"] = {
            "resolved": is_rep_resolved,
            "phrase": rep_analysis.get("pattern") if rep_analysis else None,
            "count": rep_analysis.get("repeats") if rep_analysis else None,
        }

    # Signal 2: Acoustic confidence & logprob
    try:
        avg_logprob = float(segment.get("avg_logprob")) if segment.get("avg_logprob") is not None else None
    except (ValueError, TypeError):
        avg_logprob = None

    try:
        confidence = float(segment.get("confidence")) if segment.get("confidence") is not None else None
    except (ValueError, TypeError):
        confidence = None

    if avg_logprob is not None and avg_logprob < -0.85:
        flag_reasons.append("low_confidence")
        signals["low_logprob"] = avg_logprob
    elif confidence is not None and confidence < 0.60:
        flag_reasons.append("low_confidence")
        signals["low_confidence"] = confidence

    # Signal 3: Timing gaps and silence/speech mismatch
    if prev_segment is not None:
        try:
            s_start = float(segment.get("start", 0.0))
            p_end = float(prev_segment.get("end", 0.0))
            gap = round(s_start - p_end, 2)
            if gap > 2.0:
                flag_reasons.append("timing_gap")
                signals["timing_gap_seconds"] = gap
        except (ValueError, TypeError):
            pass

    try:
        no_speech_prob = float(segment.get("no_speech_prob")) if segment.get("no_speech_prob") is not None else None
    except (ValueError, TypeError):
        no_speech_prob = None

    if no_speech_prob is not None and no_speech_prob > 0.60 and len(text) > 0:
        flag_reasons.append("speech_silence_mismatch")
        signals["no_speech_prob"] = no_speech_prob

    # Signal 4: Decoder artifacts & compression ratio
    try:
        comp_ratio = float(segment.get("compression_ratio")) if segment.get("compression_ratio") is not None else None
    except (ValueError, TypeError):
        comp_ratio = None

    if comp_ratio is not None and comp_ratio > 2.4:
        flag_reasons.append("decoder_artifact")
        signals["compression_ratio"] = comp_ratio

    # Multiple trailing or repeated symbols
    if re.search(r"([^\w\s])\1{3,}", text):
        flag_reasons.append("symbol_artifact")

    # Signal 5: Boundary anomaly (hanging on dangling particles)
    dangling_particles = (" في", " من", " على", " ال", " و", " and", " to", " with", " of", " the")
    if any(text.endswith(p) for p in dangling_particles):
        flag_reasons.append("boundary_anomaly")

    # Signal 6: Model disagreement if an alternative hypothesis has been computed
    if alternative_hypothesis is not None:
        disagreement_score = alternative_hypothesis.get("disagreement_score", 0.0)
        signals["disagreement_score"] = disagreement_score
        if disagreement_score >= 0.25:
            flag_reasons.append("model_disagreement")

    # Signal 7: Manually flagged by user
    if review_status and "manually_flagged" in review_status.get("flag_reasons", []):
        flag_reasons.append("manually_flagged")

    # Signal 8: Speech coverage anomaly / Possible Missing Speech
    seg_s = float(segment.get("start", 0.0))
    seg_e = float(segment.get("end", 0.0))
    seg_dur = seg_e - seg_s
    word_count = len(text.split())
    if seg_dur >= 4.0 and (word_count / max(0.5, seg_dur)) < 0.75 and word_count > 0:
        flag_reasons.append("possible_missing_speech")
        signals["sparse_word_density"] = {
            "duration": round(seg_dur, 2),
            "words": word_count,
            "words_per_sec": round(word_count / max(0.5, seg_dur), 2),
        }

    # Determine priority label and severity
    is_flagged = len(flag_reasons) > 0
    flag_label = "Verified" if not is_flagged else "Review Suggested"
    severity = "none"

    if "model_disagreement" in flag_reasons:
        flag_label = "Model Disagreement"
        severity = "high"
    elif "possible_missing_speech" in flag_reasons:
        flag_label = "Possible Missing Speech"
        severity = "high"
    elif "repetition_suspected" in flag_reasons:
        flag_label = "Repetition Suspected"
        severity = "high"
    elif "low_confidence" in flag_reasons:
        flag_label = "Low Acoustic Confidence"
        severity = "medium"
    elif "timing_gap" in flag_reasons:
        flag_label = "Timing Gap"
        severity = "medium"
    elif "manually_flagged" in flag_reasons:
        flag_label = "Manually Flagged"
        severity = "medium"
    elif is_flagged:
        flag_label = "Review Suggested"
        severity = "low"

    return {
        "segment_id": seg_id,
        "is_flagged": is_flagged,
        "flag_reasons": flag_reasons,
        "flag_label": flag_label,
        "severity": severity,
        "signals": signals,
    }


def detect_suspicious_segments(
    segments: List[Dict[str, Any]],
    alternative_hypotheses: Optional[List[Dict[str, Any]]] = None,
    reviews_map: Optional[Dict[int, Dict[str, Any]]] = None,
    audio_path: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Runs suspicious-region detection across all segments in a transcript.
    Returns list of segment diagnostic objects.
    """
    from app.audio.coverage_detector import detect_speech_coverage_gaps

    alt_map: Dict[int, Dict[str, Any]] = {}
    if alternative_hypotheses:
        for alt in alternative_hypotheses:
            s_id = alt.get("segment_id")
            if s_id is not None:
                alt_map[s_id] = alt

    # Detect coverage gaps if audio_path exists
    coverage_issues = []
    if audio_path:
        try:
            from pathlib import Path
            p = Path(audio_path) if not isinstance(audio_path, Path) else audio_path
            if p.exists():
                coverage_issues = detect_speech_coverage_gaps(p, segments)
        except Exception:
            coverage_issues = []

    results = []
    prev_seg = None
    for s in segments:
        s_id = s.get("id")
        alt = alt_map.get(s_id)
        rev = reviews_map.get(s_id) if reviews_map else None

        diag = analyze_segment_for_review(
            segment=s,
            prev_segment=prev_seg,
            alternative_hypothesis=alt,
            review_status=rev,
        )

        for cov in coverage_issues:
            if cov.get("segment_id") == s_id or (
                float(s.get("start", 0)) <= cov.get("end", 0)
                and float(s.get("end", 0)) >= cov.get("start", 0)
            ):
                if "possible_missing_speech" not in diag["flag_reasons"]:
                    diag["flag_reasons"].append("possible_missing_speech")
                    diag["is_flagged"] = True
                    diag["flag_label"] = "Possible Missing Speech"
                    diag["severity"] = "high"
                diag["signals"]["coverage_issue"] = cov

        results.append(diag)
        prev_seg = s

    return results
