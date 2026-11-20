"""
Verbatim Hybrid ASR Fusion V1 Core Engine
==========================================
Combines complementary speech recognition hypotheses from Specialized Whisper,
Large-v3-Turbo, and optionally QwenCleo-ASR without ground-truth leakage.

Features:
- Dynamic programming alignment for code-switched Egyptian Arabic and English
- Conservative Agreement Fusion
- ROVER-style Confusion Network Fusion
- Calibrated Weighted Fusion
- Contextual Segment-Level Routing
- Selective Three-Model Fusion (with QwenCleo 4-bit)
- Theoretical Oracle Upper Bound (Strictly for evaluation/diagnostic limits)
"""

import re
import math
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from app.evaluation.metrics import normalize_arabic_english

logger = logging.getLogger("verbatim.hybrid_fusion")

LATIN_WORD_RE = re.compile(r"^[a-zA-Z0-9_\-\.\:\/]+$")
HAS_LATIN_RE = re.compile(r"[a-zA-Z]")
ARABIC_CLITIC_PREFIXES = ("ال", "وال", "فال", "كال", "بال", "لل", "و", "ف")


def is_latin_word(token: str) -> bool:
    """Returns True if token is predominantly Latin script."""
    clean = re.sub(r"[^\w]", "", token)
    return bool(LATIN_WORD_RE.match(clean)) if clean else False


def has_latin_chars(token: str) -> bool:
    return bool(HAS_LATIN_RE.search(token))


def strip_arabic_clitics(token: str) -> Tuple[str, str]:
    """
    Separates common Egyptian Arabic proclitics (e.g. 'ال', 'و', 'ف')
    from the base word, particularly for mixed code-switched terms (e.g. 'الevent' -> 'ال', 'event').
    """
    for pref in ("وال", "فال", "كال", "بال", "لل", "ال"):
        if token.startswith(pref) and len(token) > len(pref):
            return pref, token[len(pref):]
    for pref in ("و", "ف"):
        if token.startswith(pref) and len(token) > len(pref) and has_latin_chars(token[len(pref):]):
            return pref, token[len(pref):]
    return "", token


def tokenize_transcript(text: str) -> List[Dict[str, Any]]:
    """
    Splits text into structured tokens with surface and normalized representations.
    """
    if not text:
        return []
    raw_tokens = text.strip().split()
    tokens = []
    for idx, raw in enumerate(raw_tokens):
        norm = normalize_arabic_english(raw)
        prefix, stem = strip_arabic_clitics(raw)
        norm_prefix, norm_stem = strip_arabic_clitics(norm)
        tokens.append({
            "index": idx,
            "surface": raw,
            "norm": norm,
            "prefix": prefix,
            "stem": stem,
            "norm_stem": norm_stem,
            "is_latin": is_latin_word(stem or raw),
            "has_latin": has_latin_chars(raw),
        })
    return tokens


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Standard Levenshtein distance for fuzzy matching."""
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1] * (len(s2) + 1)
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr[j + 1] = min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost)
        prev = curr
    return prev[len(s2)]


def token_match_cost(t1: Dict[str, Any], t2: Dict[str, Any]) -> float:
    """
    Computes distance cost between two tokens for alignment.
    Returns 0.0 for exact normalized match, 0.25-0.5 for close stem/code-switching match,
    and 1.0 for mismatch.
    """
    if t1["norm"] == t2["norm"]:
        return 0.0
    
    # Check stem equality (e.g. 'الevent' vs 'event')
    if t1["norm_stem"] and t2["norm_stem"] and t1["norm_stem"] == t2["norm_stem"]:
        return 0.2

    # Check fuzzy Latin match (e.g. 'proposer' vs 'proposers')
    if t1["is_latin"] and t2["is_latin"]:
        dist = _levenshtein_distance(t1["norm_stem"], t2["norm_stem"])
        max_len = max(len(t1["norm_stem"]), len(t2["norm_stem"]), 1)
        if dist <= 2 and (dist / max_len) <= 0.35:
            return 0.25 + 0.1 * dist

    return 1.0


def align_hypotheses_pairwise(
    tokens_a: List[Dict[str, Any]], tokens_b: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Needleman-Wunsch / Levenshtein dynamic programming alignment between two token lists.
    Returns list of aligned slots.
    """
    n = len(tokens_a)
    m = len(tokens_b)

    dp = [[0.0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        dp[i][0] = float(i)
    for j in range(m + 1):
        dp[0][j] = float(j)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = token_match_cost(tokens_a[i - 1], tokens_b[j - 1])
            dp[i][j] = min(
                dp[i - 1][j - 1] + cost,    # match or substitution
                dp[i - 1][j] + 1.0,         # deletion in b / insertion in a
                dp[i][j - 1] + 1.0,         # insertion in b / deletion in a
            )

    # Backtrace
    i, j = n, m
    slots = []

    while i > 0 or j > 0:
        cost = token_match_cost(tokens_a[i - 1], tokens_b[j - 1]) if (i > 0 and j > 0) else 999.0
        if i > 0 and j > 0 and math.isclose(dp[i][j], dp[i - 1][j - 1] + cost, abs_tol=1e-4):
            slots.append({
                "type": "match" if cost < 0.5 else "substitute",
                "cost": cost,
                "a": tokens_a[i - 1],
                "b": tokens_b[j - 1],
            })
            i -= 1
            j -= 1
        elif i > 0 and math.isclose(dp[i][j], dp[i - 1][j] + 1.0, abs_tol=1e-4):
            slots.append({
                "type": "delete_b",  # Present in a, missing in b
                "cost": 1.0,
                "a": tokens_a[i - 1],
                "b": None,
            })
            i -= 1
        else:
            slots.append({
                "type": "delete_a",  # Missing in a, present in b
                "cost": 1.0,
                "a": None,
                "b": tokens_b[j - 1],
            })
            j -= 1

    slots.reverse()
    return slots


def fuse_conservative_agreement(
    hyp_spec: str,
    hyp_turbo: str,
    duration_seconds: float = 45.0,
) -> Dict[str, Any]:
    """
    Conservative Agreement Fusion:
    - Where Specialized and Turbo agree, preserve the shared token (bedrock truth).
    - When they disagree:
      - Preserve English technical code-switched terms (Specialized strength).
      - Suppress pathological repetition loops (Turbo strength).
      - Retain content words if Turbo's speaking rate indicates severe speech omission.
    """
    tokens_spec = tokenize_transcript(hyp_spec)
    tokens_turbo = tokenize_transcript(hyp_turbo)

    if not tokens_spec:
        return {"fused_text": hyp_turbo, "method": "conservative_agreement", "agreement_ratio": 0.0}
    if not tokens_turbo:
        return {"fused_text": hyp_spec, "method": "conservative_agreement", "agreement_ratio": 0.0}

    slots = align_hypotheses_pairwise(tokens_spec, tokens_turbo)

    # Calculate speaking rates (words per second)
    wps_spec = len(tokens_spec) / max(duration_seconds, 1.0)
    wps_turbo = len(tokens_turbo) / max(duration_seconds, 1.0)
    turbo_under_generating = wps_turbo < 1.85 and (len(tokens_spec) - len(tokens_turbo) >= 8)
    spec_over_generating = wps_spec > 2.75 and (len(tokens_spec) - len(tokens_turbo) >= 12)

    fused_tokens: List[str] = []
    agreed_count = 0
    total_slots = len(slots)

    for idx, slot in enumerate(slots):
        stype = slot["type"]
        ta = slot["a"]  # Specialized token
        tb = slot["b"]  # Turbo token

        if stype == "match":
            agreed_count += 1
            # Prefer surface form that is cleaner
            if ta and tb:
                # If one is Latin and properly cased, keep Latin
                if ta["is_latin"] and not tb["is_latin"]:
                    fused_tokens.append(ta["surface"])
                elif tb["is_latin"] and not ta["is_latin"]:
                    fused_tokens.append(tb["surface"])
                else:
                    fused_tokens.append(ta["surface"])
            elif ta:
                fused_tokens.append(ta["surface"])
            elif tb:
                fused_tokens.append(tb["surface"])

        elif stype == "substitute":
            # Models output different words at the same position
            # Rule 1: Code-switching preservation
            if ta and tb:
                if ta["has_latin"] and not tb["has_latin"]:
                    # Specialized preserved an English term (e.g. Proposer, Potential, Joint)
                    fused_tokens.append(ta["surface"])
                elif tb["has_latin"] and not ta["has_latin"]:
                    fused_tokens.append(tb["surface"])
                elif spec_over_generating and not ta["is_latin"]:
                    # Specialized is running hot/drifting, trust Turbo's standard Arabic fluency
                    fused_tokens.append(tb["surface"])
                else:
                    # Default: Specialized Whisper has higher domain fidelity
                    fused_tokens.append(ta["surface"])

        elif stype == "delete_b":
            # Token present in Specialized, deleted in Turbo
            if ta:
                # Check for repetition loop (e.g. duplicate of previous token)
                is_repetition = False
                if fused_tokens:
                    prev_norm = normalize_arabic_english(fused_tokens[-1])
                    if ta["norm"] == prev_norm and len(ta["norm"]) > 2:
                        is_repetition = True

                if is_repetition:
                    # Drop hallucinated/repeated token
                    continue

                if ta["has_latin"]:
                    # Always retain genuine English loanwords
                    fused_tokens.append(ta["surface"])
                elif turbo_under_generating:
                    # Turbo dropped speech; keep Specialized word
                    fused_tokens.append(ta["surface"])
                elif spec_over_generating:
                    # Specialized is bloating with filler words; omit
                    continue
                else:
                    # Retain token
                    fused_tokens.append(ta["surface"])

        elif stype == "delete_a":
            # Token present in Turbo, missing in Specialized
            if tb:
                # If Specialized dropped a valid Arabic word and Turbo captured it
                if not spec_over_generating:
                    fused_tokens.append(tb["surface"])

    fused_text = " ".join(fused_tokens).strip()
    # Clean up double punctuation or weird spaces
    fused_text = re.sub(r"\s+", " ", fused_text)
    agreement_ratio = agreed_count / max(total_slots, 1)

    return {
        "fused_text": fused_text,
        "method": "conservative_agreement",
        "agreement_ratio": round(agreement_ratio, 4),
        "total_slots": total_slots,
        "agreed_slots": agreed_count,
        "wps_spec": round(wps_spec, 2),
        "wps_turbo": round(wps_turbo, 2),
    }


def fuse_rover(
    hypotheses: List[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
    latin_boost: float = 0.35,
) -> Dict[str, Any]:
    """
    ROVER Confusion Network (Word Confusion Network) Fusion:
    Builds a confusion network from multiple aligned hypotheses (e.g. Specialized, Turbo, QwenCleo)
    and evaluates weighted voting across candidate words per slot.
    """
    if not hypotheses:
        return {"fused_text": "", "method": "rover"}
    if len(hypotheses) == 1:
        return {"fused_text": hypotheses[0]["text"], "method": "rover"}

    if not weights:
        # Default balanced weights favoring Specialized domain accuracy
        weights = {
            "codeswitched-medium": 1.15,
            "large-v3-turbo": 1.0,
            "qwencleo-asr-4bit": 0.90,
        }

    # Tokenize all hypotheses
    token_lists = []
    for h in hypotheses:
        m_id = h.get("model_id", "unknown")
        txt = h.get("text", "")
        toks = tokenize_transcript(txt)
        token_lists.append({"model_id": m_id, "tokens": toks})

    # Progressive alignment to form confusion network
    # Start with base hypothesis (codeswitched-medium or first)
    base_idx = 0
    for idx, tl in enumerate(token_lists):
        if "codeswitched" in tl["model_id"]:
            base_idx = idx
            break

    base = token_lists[base_idx]
    # Initialize network slots with base hypothesis tokens
    # Each slot is a list of candidate entries: {"model_id": ..., "token": ...}
    network: List[List[Dict[str, Any]]] = []
    for t in base["tokens"]:
        network.append([{"model_id": base["model_id"], "token": t}])

    # Align each subsequent hypothesis into the network
    for idx, tl in enumerate(token_lists):
        if idx == base_idx:
            continue
        m_id = tl["model_id"]
        other_tokens = tl["tokens"]

        # Form a representative token list from current network slots
        net_tokens = []
        for slot in network:
            # pick first non-null token in slot
            first_tok = next((c["token"] for c in slot if c["token"] is not None), None)
            net_tokens.append(first_tok if first_tok else {"norm": "", "norm_stem": "", "is_latin": False})

        slots_align = align_hypotheses_pairwise(net_tokens, other_tokens)

        # Merge other_tokens into network based on alignment
        new_network: List[List[Dict[str, Any]]] = []
        net_ptr = 0

        for sa in slots_align:
            satype = sa["type"]
            ta = sa["a"]
            tb = sa["b"]

            if satype in ("match", "substitute"):
                if net_ptr < len(network):
                    slot = network[net_ptr]
                    slot.append({"model_id": m_id, "token": tb})
                    new_network.append(slot)
                    net_ptr += 1
                else:
                    new_network.append([{"model_id": m_id, "token": tb}])
            elif satype == "delete_b":
                # Present in network, missing in other
                if net_ptr < len(network):
                    slot = network[net_ptr]
                    slot.append({"model_id": m_id, "token": None})
                    new_network.append(slot)
                    net_ptr += 1
            elif satype == "delete_a":
                # Missing in network, present in other (insertion)
                new_network.append([{"model_id": m_id, "token": tb}])

        # Append any remaining network slots
        while net_ptr < len(network):
            slot = network[net_ptr]
            slot.append({"model_id": m_id, "token": None})
            new_network.append(slot)
            net_ptr += 1

        network = new_network

    # Decode winning candidate per network slot
    fused_tokens: List[str] = []
    for slot in network:
        # Score candidates by normalized token
        norm_scores: Dict[str, float] = {}
        surface_map: Dict[str, str] = {}
        null_score = 0.0

        for cand in slot:
            m_id = cand["model_id"]
            tok = cand["token"]
            w = weights.get(m_id, 1.0)

            if tok is None:
                null_score += w
            else:
                n = tok["norm"]
                boost = latin_boost if tok["has_latin"] else 0.0
                score = w + boost
                norm_scores[n] = norm_scores.get(n, 0.0) + score
                if n not in surface_map or tok["has_latin"]:
                    surface_map[n] = tok["surface"]

        if not norm_scores:
            continue

        best_norm, best_score = max(norm_scores.items(), key=lambda x: x[1])
        if best_score > null_score:
            # Token wins over deletion
            # Check repetition
            surface = surface_map[best_norm]
            if fused_tokens and normalize_arabic_english(fused_tokens[-1]) == best_norm and len(best_norm) > 2:
                # Skip duplicate
                continue
            fused_tokens.append(surface)

    fused_text = " ".join(fused_tokens).strip()
    return {
        "fused_text": fused_text,
        "method": "rover_confusion_network",
        "num_models": len(hypotheses),
        "num_slots": len(network),
    }


def fuse_weighted(
    hyp_spec: str,
    hyp_turbo: str,
    weight_spec: float = 1.20,
    weight_turbo: float = 1.0,
    duration_seconds: float = 45.0,
) -> Dict[str, Any]:
    """
    Weighted Fusion with calibrated model error-rate priors.
    """
    hyps = [
        {"model_id": "codeswitched-medium", "text": hyp_spec},
        {"model_id": "large-v3-turbo", "text": hyp_turbo},
    ]
    weights = {
        "codeswitched-medium": weight_spec,
        "large-v3-turbo": weight_turbo,
    }
    res = fuse_rover(hyps, weights=weights)
    res["method"] = "weighted_fusion"
    res["weight_spec"] = weight_spec
    res["weight_turbo"] = weight_turbo
    return res


def score_segment_hypothesis(
    text: str, duration_seconds: float, expected_wps: float = 2.1
) -> float:
    """
    Computes an objective, non-oracle quality score for a candidate segment.
    Penalizes severe under-generation (speech omission) and over-generation (repetition/hallucination).
    Awards bonuses for clean Latin code-switching entities.
    """
    tokens = text.strip().split()
    if not tokens:
        return -100.0

    word_count = len(tokens)
    actual_wps = word_count / max(duration_seconds, 1.0)

    # 1. Speaking rate Gaussian-like penalty
    # Natural rate 1.8 - 2.5 wps
    wps_diff = abs(actual_wps - expected_wps)
    wps_score = - (wps_diff ** 2) * 2.0

    # 2. Severe omission penalty: if wps < 1.4 on longer interval
    if duration_seconds >= 10.0 and actual_wps < 1.4:
        wps_score -= 8.0

    # 3. Repetition penalty
    norm_tokens = [normalize_arabic_english(t) for t in tokens]
    repeated_bigrams = 0
    bigrams = set()
    for i in range(len(norm_tokens) - 1):
        bg = (norm_tokens[i], norm_tokens[i + 1])
        if bg in bigrams:
            repeated_bigrams += 1
        bigrams.add(bg)

    rep_penalty = repeated_bigrams * 3.5

    # 4. Code-switching bonus (genuine English loanwords)
    latin_words = [t for t in tokens if is_latin_word(t)]
    code_switch_bonus = len(latin_words) * 1.5

    return 10.0 + wps_score - rep_penalty + code_switch_bonus


def route_contextual_segments(
    segments_spec: List[Dict[str, Any]],
    segments_turbo: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Contextual Segment-Level Routing:
    For each corresponding segment/time slice, selects between Specialized and Turbo
    based on speaking rate density, repetition avoidance, and code-switching presence.
    """
    # If segment lists are empty, fallback
    if not segments_spec and not segments_turbo:
        return {"fused_text": "", "method": "contextual_segment_routing", "routed_segments": []}
    if not segments_spec:
        txt = " ".join(s.get("text", "").strip() for s in segments_turbo)
        return {"fused_text": txt, "method": "contextual_segment_routing", "routed_segments": []}
    if not segments_turbo:
        txt = " ".join(s.get("text", "").strip() for s in segments_spec)
        return {"fused_text": txt, "method": "contextual_segment_routing", "routed_segments": []}

    # Evaluate full-text score or segment-wise score
    # In benchmark slices (e.g. 45s), we evaluate both overall and per segment
    routed_parts = []
    # If 1 segment each:
    if len(segments_spec) == 1 and len(segments_turbo) == 1:
        s_spec = segments_spec[0]
        s_turbo = segments_turbo[0]
        dur = max(s_spec.get("end", 45.0) - s_spec.get("start", 0.0), 1.0)

        score_spec = score_segment_hypothesis(s_spec.get("text", ""), dur)
        score_turbo = score_segment_hypothesis(s_turbo.get("text", ""), dur)

        winner = "codeswitched-medium" if score_spec >= score_turbo else "large-v3-turbo"
        win_text = s_spec.get("text", "") if winner == "codeswitched-medium" else s_turbo.get("text", "")

        return {
            "fused_text": win_text.strip(),
            "method": "contextual_segment_routing",
            "winner": winner,
            "score_spec": round(score_spec, 2),
            "score_turbo": round(score_turbo, 2),
        }

    # Multi-segment alignment by timestamp overlap
    # We can perform conservative fusion on the segments or route segment by segment
    txt_spec = " ".join(s.get("text", "").strip() for s in segments_spec)
    txt_turbo = " ".join(s.get("text", "").strip() for s in segments_turbo)
    total_dur = max(segments_spec[-1].get("end", 45.0) - segments_spec[0].get("start", 0.0), 1.0)

    score_spec = score_segment_hypothesis(txt_spec, total_dur)
    score_turbo = score_segment_hypothesis(txt_turbo, total_dur)

    winner = "codeswitched-medium" if score_spec >= score_turbo else "large-v3-turbo"
    win_text = txt_spec if winner == "codeswitched-medium" else txt_turbo

    return {
        "fused_text": win_text.strip(),
        "method": "contextual_segment_routing",
        "winner": winner,
        "score_spec": round(score_spec, 2),
        "score_turbo": round(score_turbo, 2),
    }


def fuse_selective_three_model(
    hyp_spec: str,
    hyp_turbo: str,
    hyp_qwen: Optional[str] = None,
    disagreement_threshold: float = 0.30,
    duration_seconds: float = 45.0,
) -> Dict[str, Any]:
    """
    Selective Three-Model Fusion:
    - First evaluates Specialized Whisper and Large-v3-Turbo.
    - If disagreement ratio <= threshold, uses Conservative Agreement between the two.
    - If disagreement > threshold (or if QwenCleo is available), employs 3-model ROVER
      where QwenCleo acts as the independent code-switched tiebreaker.
    """
    tokens_spec = tokenize_transcript(hyp_spec)
    tokens_turbo = tokenize_transcript(hyp_turbo)

    if not hyp_qwen or not hyp_qwen.strip():
        # Fall back to 2-model conservative agreement
        return fuse_conservative_agreement(hyp_spec, hyp_turbo, duration_seconds=duration_seconds)

    slots = align_hypotheses_pairwise(tokens_spec, tokens_turbo)
    mismatches = sum(1 for s in slots if s["type"] != "match")
    disagreement_ratio = mismatches / max(len(slots), 1)

    if disagreement_ratio < disagreement_threshold:
        # High agreement between Spec and Turbo -> safe conservative fusion
        res = fuse_conservative_agreement(hyp_spec, hyp_turbo, duration_seconds=duration_seconds)
        res["three_model_invoked"] = False
        res["disagreement_ratio"] = round(disagreement_ratio, 4)
        return res

    # High disagreement -> invoke 3-model ROVER with QwenCleo
    hyps = [
        {"model_id": "codeswitched-medium", "text": hyp_spec},
        {"model_id": "large-v3-turbo", "text": hyp_turbo},
        {"model_id": "qwencleo-asr-4bit", "text": hyp_qwen},
    ]
    weights = {
        "codeswitched-medium": 1.15,
        "large-v3-turbo": 1.05,
        "qwencleo-asr-4bit": 0.95,
    }
    rover_res = fuse_rover(hyps, weights=weights, latin_boost=0.40)
    rover_res["three_model_invoked"] = True
    rover_res["disagreement_ratio"] = round(disagreement_ratio, 4)
    rover_res["method"] = "selective_three_model"
    return rover_res


def calculate_oracle_upper_bound(
    candidate_hypotheses: Dict[str, str],
    reference_text: str,
) -> Dict[str, Any]:
    """
    Theoretical Oracle Upper Bound:
    Evaluates both Segment-Level Oracle and Token-Level Oracle.
    STRICTLY FOR RESEARCH ANALYSIS — NOT DEPLOYABLE IN PRODUCTION (Requires Ground Truth).
    """
    from app.evaluation.metrics import calculate_wer_cer

    if not reference_text or not candidate_hypotheses:
        return {
            "status": "error",
            "label": "ORACLE — NOT DEPLOYABLE (Theoretical Upper Bound)",
            "oracle_wer": None,
            "oracle_cer": None,
        }

    # 1. Segment-level Oracle (best single model transcript)
    model_evals = {}
    for m_id, hyp in candidate_hypotheses.items():
        if not hyp:
            continue
        ev = calculate_wer_cer(reference_text, hyp, mode="normalized")
        model_evals[m_id] = {
            "wer": ev["wer_percent"],
            "cer": ev["cer_percent"],
            "subs": ev["substitutions"],
            "dels": ev["deletions"],
            "inss": ev["insertions"],
            "hits": ev["hits"],
            "text": hyp,
        }

    if not model_evals:
        return {
            "status": "error",
            "label": "ORACLE — NOT DEPLOYABLE (Theoretical Upper Bound)",
            "oracle_wer": None,
            "oracle_cer": None,
        }

    best_model_name, best_model_stats = min(model_evals.items(), key=lambda x: x[1]["wer"])

    # 2. Token-level Oracle across all candidates
    ref_norm_tokens = normalize_arabic_english(reference_text).split()
    ref_norm_set = set(ref_norm_tokens)

    # Align primary candidates (Spec and Turbo, plus Qwen if available)
    spec_txt = candidate_hypotheses.get("codeswitched-medium", "")
    turbo_txt = candidate_hypotheses.get("large-v3-turbo", "")

    if spec_txt and turbo_txt:
        slots = align_hypotheses_pairwise(
            tokenize_transcript(spec_txt),
            tokenize_transcript(turbo_txt)
        )
        oracle_tokens = []
        for s in slots:
            ta = s["a"]
            tb = s["b"]
            na = ta["norm"] if ta else None
            nb = tb["norm"] if tb else None

            if na == nb:
                if ta:
                    oracle_tokens.append(ta["surface"])
            elif na in ref_norm_set and nb not in ref_norm_set:
                oracle_tokens.append(ta["surface"])
            elif nb in ref_norm_set and na not in ref_norm_set:
                oracle_tokens.append(tb["surface"])
            else:
                # pick candidate closest to reference
                if ta and na:
                    oracle_tokens.append(ta["surface"])
                elif tb:
                    oracle_tokens.append(tb["surface"])

        token_oracle_txt = " ".join(oracle_tokens)
        ev_token = calculate_wer_cer(reference_text, token_oracle_txt, mode="normalized")
        token_oracle_wer = ev_token["wer_percent"]
        token_oracle_cer = ev_token["cer_percent"]
    else:
        token_oracle_txt = best_model_stats["text"]
        token_oracle_wer = best_model_stats["wer"]
        token_oracle_cer = best_model_stats["cer"]

    # Overall oracle is the minimum of segment-oracle and token-oracle
    if token_oracle_wer <= best_model_stats["wer"]:
        final_oracle_wer = token_oracle_wer
        final_oracle_cer = token_oracle_cer
        final_oracle_txt = token_oracle_txt
        oracle_type = "token_level"
    else:
        final_oracle_wer = best_model_stats["wer"]
        final_oracle_cer = best_model_stats["cer"]
        final_oracle_txt = best_model_stats["text"]
        oracle_type = f"segment_level ({best_model_name})"

    return {
        "status": "success",
        "label": "ORACLE — NOT DEPLOYABLE (Theoretical Upper Bound)",
        "oracle_type": oracle_type,
        "oracle_wer": final_oracle_wer,
        "oracle_cer": final_oracle_cer,
        "best_individual_model": best_model_name,
        "best_individual_wer": best_model_stats["wer"],
        "oracle_text": final_oracle_txt,
    }
