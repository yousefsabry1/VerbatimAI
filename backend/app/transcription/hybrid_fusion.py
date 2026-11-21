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


def robust_split_transcript(text: str) -> List[str]:
    """
    Robust transcript word splitter that separates punctuation-joined tokens
    (e.g., 'موسيقى.موسيقى.موسيقى.', 'لا،لا،لا', 'hello.hello.hello')
    while strictly protecting:
    - Decimal numbers, percentages, thousands separators (e.g., 3.14, 10,000, 12.5%, ٣.١٤)
    - Standard abbreviations (e.g., U.S.A., A.I., e.g., i.e., Dr., Ph.D.)
    - URLs, domains, emails (e.g., verbatim.ai, https://..., test@example.com)
    - Hyphenated compound terms (e.g., code-switching, large-v3-turbo)
    """
    if not text:
        return []

    raw_tokens = text.strip().split()
    final_tokens: List[str] = []
    tlds = {"com", "org", "net", "edu", "gov", "io", "ai", "dev", "app", "me"}

    for raw in raw_tokens:
        # 1. Decimal numbers, percentages, thousands separators (Arabic and English digits)
        if re.fullmatch(r"[\d\u0660-\u0669]+([.,][\d\u0660-\u0669]+)+%?", raw):
            final_tokens.append(raw)
            continue

        # 2. English abbreviations (e.g., U.S.A., A.I., e.g., i.e., Dr., Ph.D.)
        if re.fullmatch(r"([A-Za-z]\.)+|e\.g\.|i\.e\.|Ph\.D\.|Dr\.", raw, re.IGNORECASE):
            final_tokens.append(raw)
            continue

        # 3. URLs, domains, emails
        if re.search(r"https?://|www\.|@", raw) or any(raw.lower().endswith("." + tld) for tld in tlds):
            final_tokens.append(raw)
            continue

        # 4. Hyphenated compound words (e.g., code-switching, large-v3-turbo)
        if re.fullmatch(r"[A-Za-z0-9]+(-[A-Za-z0-9]+)+", raw):
            final_tokens.append(raw)
            continue

        # 5. Intra-token punctuation splitting (Arabic & English punctuation)
        # Delimiters: . , ، ! ? ؟ ; ؛ / :
        parts = re.split(r"([.,!?;:\u060C\u061B\u061F/]+)", raw)
        sub_tokens: List[str] = []
        for p in parts:
            if not p:
                continue
            if re.fullmatch(r"[.,!?;:\u060C\u061B\u061F/]+", p):
                if sub_tokens:
                    sub_tokens[-1] += p
                else:
                    sub_tokens.append(p)
            else:
                if sub_tokens and re.fullmatch(r"[.,!?;:\u060C\u061B\u061F/]+", sub_tokens[-1]):
                    sub_tokens[-1] += p
                else:
                    sub_tokens.append(p)
        final_tokens.extend(sub_tokens)

    return final_tokens


def tokenize_transcript(text: str) -> List[Dict[str, Any]]:
    """
    Splits text into structured tokens with surface and normalized representations.
    Recognizes punctuation-joined token boundaries while protecting numbers, decimals,
    abbreviations, URLs, and hyphenated terms.
    """
    if not text:
        return []
    raw_tokens = robust_split_transcript(text)
    tokens = []
    for idx, raw in enumerate(raw_tokens):
        # Ignore tokens that are pure punctuation with no alphanumeric or Arabic characters
        if not re.search(r"[\w\u0600-\u06FF]", raw):
            continue
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
    tokens = robust_split_transcript(text)
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


# ============================================================================
# HYBRID ASR V2 ENHANCEMENTS: TRANSLITERATION MAPPING, MISSING-WORD PROTECTION
# & SELECTIVE ARBITER FUSION
# ============================================================================

# Known Egyptian English transliteration equivalents commonly observed in tech talks
TRANSLITERATION_MAP = {
    "بروفايد": "provide",
    "بروفايت": "provide",
    "الفاند": "fund",
    "فاند": "fund",
    "هيفامد": "fund",
    "هيفاند": "fund",
    "البرانش": "branch",
    "برانش": "branch",
    "اللوجو": "logo",
    "لوجو": "logo",
    "الويبسايت": "website",
    "ويبسايت": "website",
    "الاكونت": "account",
    "اكونت": "account",
    "مينتور": "mentor",
    "مينتورشيب": "mentorship",
    "ارجانيز": "organize",
    "اورجانيزر": "organizer",
    "الاتماد": "teamate",
    "تيم": "team",
    "التيم": "team",
    "تكتور": "tech",
    "سستم": "system",
    "السيستم": "system",
    "ايفنت": "event",
    "الايفنت": "event",
    "فولنتيرز": "volunteers",
    "الفولنتيرز": "volunteers",
    "هننقاوتيتش": "outreach",
    "اوتريتش": "outreach",
    "اوتريش": "outreach",
    "accessability": "accessibility",
    "accesability": "accessibility",
}

# HYBRID ASR V3 ENHANCEMENTS: EXPANDED DOMAIN TECHNICAL CANONICALIZATION
TRANSLITERATION_MAP_V3: Dict[str, str] = dict(TRANSLITERATION_MAP)
TRANSLITERATION_MAP_V3.update({
    "شابتر": "chapter",
    "الشابطه": "chapter",
    "الشابطة": "chapter",
    "شوطه": "chapter",
    "الوجو": "logo",
    "انستراكتورز": "instructors",
    "نستراكتورز": "instructors",
    "انستركتورز": "instructors",
    "انستركتر": "instructors",
    "هوست": "host",
    "يهوست": "host",
    "اكسسبلتي": "accessibility",
    "اللقسه": "accessibility",
    "اللقسة": "accessibility",
    "سيستم": "system",
    "هيستوري": "history",
    "الهيسترو": "history",
    "الهيستور": "history",
    "داتابيز": "database",
    "الداتابيز": "database",
})



def is_transliteration_match(tok_a: Dict[str, Any], tok_b: Dict[str, Any]) -> bool:
    """Checks if one token is a known Egyptian Arabic transliteration of an English token."""
    na = tok_a.get("norm_stem") or tok_a.get("norm", "")
    nb = tok_b.get("norm_stem") or tok_b.get("norm", "")

    if TRANSLITERATION_MAP.get(na) == nb or TRANSLITERATION_MAP.get(nb) == na:
        return True
    if tok_a.get("has_latin") and not tok_b.get("has_latin"):
        if TRANSLITERATION_MAP.get(nb) == tok_a.get("norm_stem"):
            return True
    elif tok_b.get("has_latin") and not tok_a.get("has_latin"):
        if TRANSLITERATION_MAP.get(na) == tok_b.get("norm_stem"):
            return True
    return False


def soft_arabic_distance(s1: str, s2: str) -> float:
    """Computes soft distance allowing common colloquial phonetic confusions."""
    if s1 == s2:
        return 0.0
    rep = [("ص", "س"), ("ط", "ت"), ("ظ", "ز"), ("ض", "د"), ("ة", "ه"), ("ى", "ي"), ("أ", "ا"), ("إ", "ا"), ("آ", "ا")]
    for a, b in rep:
        s1 = s1.replace(a, b)
        s2 = s2.replace(a, b)
    if s1 == s2:
        return 0.15
    d = _levenshtein_distance(s1, s2)
    max_l = max(len(s1), len(s2), 1)
    if d == 1 and max_l >= 4:
        return 0.35
    return 1.0


def enhanced_token_match_cost(t1: Dict[str, Any], t2: Dict[str, Any]) -> float:
    """
    Enhanced distance cost between two tokens for Hybrid V2 alignment:
    - 0.0 for exact normalized match
    - 0.15 for stem equality
    - 0.25 for known transliteration match
    - 0.25-0.35 for fuzzy Latin match
    - 0.15-0.35 for soft Arabic phonetic match
    - 1.0 for mismatch
    """
    if t1["norm"] == t2["norm"]:
        return 0.0

    if t1.get("norm_stem") and t2.get("norm_stem") and t1["norm_stem"] == t2["norm_stem"]:
        return 0.15

    if is_transliteration_match(t1, t2):
        return 0.25

    if t1.get("is_latin") and t2.get("is_latin"):
        dist = _levenshtein_distance(t1["norm_stem"], t2["norm_stem"])
        max_len = max(len(t1["norm_stem"]), len(t2["norm_stem"]), 1)
        if dist <= 2 and (dist / max_len) <= 0.35:
            return 0.25 + 0.1 * dist

    if not t1.get("has_latin") and not t2.get("has_latin"):
        soft_d = soft_arabic_distance(t1.get("norm_stem", ""), t2.get("norm_stem", ""))
        if soft_d < 0.5:
            return soft_d

    return 1.0


def align_hypotheses_pairwise_v2(
    tokens_a: List[Dict[str, Any]], tokens_b: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Needleman-Wunsch alignment using enhanced Hybrid V2 match costs."""
    n = len(tokens_a)
    m = len(tokens_b)
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        dp[i][0] = float(i)
    for j in range(m + 1):
        dp[0][j] = float(j)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = enhanced_token_match_cost(tokens_a[i - 1], tokens_b[j - 1])
            dp[i][j] = min(
                dp[i - 1][j - 1] + cost,
                dp[i - 1][j] + 1.0,
                dp[i][j - 1] + 1.0,
            )

    i, j = n, m
    slots = []
    while i > 0 or j > 0:
        cost = enhanced_token_match_cost(tokens_a[i - 1], tokens_b[j - 1]) if (i > 0 and j > 0) else 999.0
        if i > 0 and j > 0 and math.isclose(dp[i][j], dp[i - 1][j - 1] + cost, abs_tol=1e-4):
            slots.append({
                "type": "match" if cost < 0.45 else "substitute",
                "cost": cost,
                "a": tokens_a[i - 1],
                "b": tokens_b[j - 1],
            })
            i -= 1
            j -= 1
        elif i > 0 and math.isclose(dp[i][j], dp[i - 1][j] + 1.0, abs_tol=1e-4):
            slots.append({"type": "delete_b", "cost": 1.0, "a": tokens_a[i - 1], "b": None})
            i -= 1
        else:
            slots.append({"type": "delete_a", "cost": 1.0, "a": None, "b": tokens_b[j - 1]})
            j -= 1

    slots.reverse()
    return slots


def detect_critical_code_switch_conflict(txt_spec: str, txt_turbo: str) -> Tuple[bool, str]:
    """
    Detects whether Specialized Whisper and Large-v3-Turbo have critical code-switching
    conflicts or severe speech omission that warrants invoking the heavy QwenCleo arbiter.
    """
    toks_spec = tokenize_transcript(txt_spec)
    toks_turbo = tokenize_transcript(txt_turbo)

    len_diff = abs(len(toks_spec) - len(toks_turbo))
    if len_diff >= 12:
        return True, f"length_disparity_{len_diff}"

    slots = align_hypotheses_pairwise_v2(toks_spec, toks_turbo)

    code_switch_mismatches = 0
    substitutions = 0
    deletions = 0

    for s in slots:
        stype = s["type"]
        ta = s["a"]
        tb = s["b"]

        if stype == "substitute":
            substitutions += 1
            if ta and tb:
                if (ta.get("has_latin") != tb.get("has_latin")) or (ta.get("has_latin") and ta.get("norm") != tb.get("norm")):
                    code_switch_mismatches += 1
        elif stype in ("delete_a", "delete_b"):
            deletions += 1
            if (ta and ta.get("has_latin")) or (tb and tb.get("has_latin")):
                code_switch_mismatches += 1

    total_slots = max(len(slots), 1)
    disagreement_rate = (substitutions + deletions) / total_slots

    if code_switch_mismatches >= 2:
        return True, f"code_switch_mismatches_{code_switch_mismatches}"
    if disagreement_rate > 0.40 and code_switch_mismatches >= 1:
        return True, f"high_disagreement_{disagreement_rate:.2f}"

    return False, f"low_conflict_rate_{disagreement_rate:.2f}"


def fuse_rover_v2(
    hypotheses: List[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
    latin_boost: float = 0.45,
) -> Dict[str, Any]:
    """
    Hybrid ASR V2 ROVER Fusion:
    - Smarter pairwise alignment with transliteration and phonetic normalization
    - Asymmetric missing-word protection (penalizes Turbo deletions due to under-generation)
    - Transliteration canonical grouping
    - Clean surface form preservation for low CER
    """
    if not hypotheses:
        return {"fused_text": "", "num_models": 0, "num_slots": 0}
    if len(hypotheses) == 1:
        return {"fused_text": hypotheses[0]["text"].strip(), "num_models": 1, "num_slots": len(hypotheses[0]["text"].split())}

    if weights is None:
        weights = {"codeswitched-medium": 1.25, "large-v3-turbo": 1.0, "qwencleo-asr-4bit": 0.95}

    base_toks = tokenize_transcript(hypotheses[0]["text"])
    base_id = hypotheses[0]["model_id"]
    network: List[List[Dict[str, Any]]] = []
    for t in base_toks:
        network.append([{"model_id": base_id, "token": t}])

    for h in hypotheses[1:]:
        m_id = h["model_id"]
        other_tokens = tokenize_transcript(h["text"])
        if not other_tokens:
            for slot in network:
                slot.append({"model_id": m_id, "token": None})
            continue

        net_tokens = []
        for slot in network:
            first_tok = None
            for cand in slot:
                if cand["token"] is not None:
                    first_tok = cand["token"]
                    break
            net_tokens.append(first_tok if first_tok else {"norm": "", "norm_stem": "", "is_latin": False, "has_latin": False})

        slots_align = align_hypotheses_pairwise_v2(net_tokens, other_tokens)
        new_network: List[List[Dict[str, Any]]] = []
        net_ptr = 0

        for sa in slots_align:
            satype = sa["type"]
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
                if net_ptr < len(network):
                    slot = network[net_ptr]
                    slot.append({"model_id": m_id, "token": None})
                    new_network.append(slot)
                    net_ptr += 1
            elif satype == "delete_a":
                new_network.append([{"model_id": m_id, "token": tb}])

        while net_ptr < len(network):
            slot = network[net_ptr]
            slot.append({"model_id": m_id, "token": None})
            new_network.append(slot)
            net_ptr += 1

        network = new_network

    fused_tokens: List[str] = []
    for slot in network:
        norm_scores: Dict[str, float] = {}
        surface_map: Dict[str, str] = {}
        null_score = 0.0

        for cand in slot:
            m_id = cand["model_id"]
            tok = cand["token"]
            w = weights.get(m_id, 1.0)

            if tok is None:
                if m_id == "large-v3-turbo":
                    null_score += (w * 0.70)
                else:
                    null_score += w
            else:
                n = tok["norm"]
                if not tok.get("has_latin") and n in TRANSLITERATION_MAP:
                    mapped = TRANSLITERATION_MAP[n]
                    n = mapped

                boost = latin_boost if (tok.get("has_latin") or n in TRANSLITERATION_MAP.values()) else 0.0
                score = w + boost
                norm_scores[n] = norm_scores.get(n, 0.0) + score
                if tok.get("has_latin"):
                    surface_map[n] = tok["surface"]
                elif n not in surface_map:
                    surface_map[n] = tok["surface"]

        if not norm_scores:
            continue

        best_norm, best_score = max(norm_scores.items(), key=lambda x: x[1])
        if best_score > null_score:
            surface = surface_map.get(best_norm, best_norm)
            if fused_tokens and normalize_arabic_english(fused_tokens[-1]) == normalize_arabic_english(surface) and len(surface) > 2:
                continue
            fused_tokens.append(surface)

    fused_text = " ".join(fused_tokens).strip()
    return {
        "fused_text": fused_text,
        "method": "rover_confusion_network_v2",
        "num_models": len(hypotheses),
        "num_slots": len(network),
    }


def fuse_hybrid_v2(
    hyp_spec: str,
    hyp_turbo: str,
    hyp_qwen: Optional[str] = None,
    duration_seconds: float = 45.0,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Main entry point for Verbatim Hybrid ASR V2:
    - Evaluates code-switching conflict between Specialized Whisper and Large-v3-Turbo
    - If QwenCleo is available, synthesizes 3-model ROVER V2 with transliteration preservation
    - If QwenCleo is not provided, uses Conservative Agreement V2
    """
    is_conflict, reason = detect_critical_code_switch_conflict(hyp_spec, hyp_turbo)

    if hyp_qwen and hyp_qwen.strip():
        hyps = [
            {"model_id": "codeswitched-medium", "text": hyp_spec},
            {"model_id": "large-v3-turbo", "text": hyp_turbo},
            {"model_id": "qwencleo-asr-4bit", "text": hyp_qwen},
        ]
        res = fuse_rover_v2(hyps, weights=weights)
        res["code_switch_conflict_detected"] = is_conflict
        res["conflict_reason"] = reason
        res["qwen_invoked"] = True
        return res
    else:
        # Fallback to Conservative Agreement
        res = fuse_conservative_agreement(hyp_spec, hyp_turbo, duration_seconds=duration_seconds)
        res["code_switch_conflict_detected"] = is_conflict
        res["conflict_reason"] = reason
        res["qwen_invoked"] = False
        return res


def fuse_rover_v3(
    hypotheses: List[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
    latin_boost: float = 0.35,
    turbo_null_factor: float = 0.70,
    qwen_null_factor: float = 1.0,
    dedup_all: bool = True,
) -> Dict[str, Any]:
    """
    Hybrid ASR V3 ROVER Fusion — Accuracy First:
    - Calibrated optimal weights (Spec: 1.25, Turbo: 0.90, Qwen: 0.90)
    - Full-spectrum particle and stutter deduplication (removes repetition loops without token length threshold)
    - Expanded domain technical code-switching transliteration canonicalization (TRANSLITERATION_MAP_V3)
    - Asymmetric deletion penalty for under-generating models
    - Clean surface form preservation
    """
    if not hypotheses:
        return {"fused_text": "", "num_models": 0, "num_slots": 0}
    if len(hypotheses) == 1:
        return {"fused_text": hypotheses[0]["text"].strip(), "num_models": 1, "num_slots": len(hypotheses[0]["text"].split())}

    if weights is None:
        weights = {"codeswitched-medium": 1.25, "large-v3-turbo": 0.90, "qwencleo-asr-4bit": 0.90}

    base_toks = tokenize_transcript(hypotheses[0]["text"])
    base_id = hypotheses[0]["model_id"]
    network: List[List[Dict[str, Any]]] = []
    for t in base_toks:
        network.append([{"model_id": base_id, "token": t}])

    for h in hypotheses[1:]:
        m_id = h["model_id"]
        other_tokens = tokenize_transcript(h["text"])
        if not other_tokens:
            for slot in network:
                slot.append({"model_id": m_id, "token": None})
            continue

        net_tokens = []
        for slot in network:
            first_tok = None
            for cand in slot:
                if cand["token"] is not None:
                    first_tok = cand["token"]
                    break
            net_tokens.append(first_tok if first_tok else {"norm": "", "norm_stem": "", "is_latin": False, "has_latin": False})

        slots_align = align_hypotheses_pairwise_v2(net_tokens, other_tokens)
        new_network: List[List[Dict[str, Any]]] = []
        net_ptr = 0

        for sa in slots_align:
            satype = sa["type"]
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
                if net_ptr < len(network):
                    slot = network[net_ptr]
                    slot.append({"model_id": m_id, "token": None})
                    new_network.append(slot)
                    net_ptr += 1
            elif satype == "delete_a":
                new_network.append([{"model_id": m_id, "token": tb}])

        while net_ptr < len(network):
            slot = network[net_ptr]
            slot.append({"model_id": m_id, "token": None})
            new_network.append(slot)
            net_ptr += 1

        network = new_network

    fused_tokens: List[str] = []
    for slot in network:
        cluster_scores: Dict[str, float] = {}
        cluster_surfaces: Dict[str, Dict[str, float]] = {}
        cluster_supporting_models: Dict[str, List[str]] = {}
        null_score = 0.0

        for cand in slot:
            m_id = cand["model_id"]
            tok = cand["token"]
            w = weights.get(m_id, 1.0)

            if tok is None:
                if m_id == "large-v3-turbo":
                    null_score += (w * turbo_null_factor)
                elif m_id == "qwencleo-asr-4bit":
                    null_score += (w * qwen_null_factor)
                else:
                    null_score += w
            else:
                n = tok["norm"]
                # Transliteration mapping is used strictly for clustering/alignment
                cluster_key = TRANSLITERATION_MAP_V3.get(n, n)

                boost = latin_boost if (tok.get("has_latin") or n in TRANSLITERATION_MAP_V3.values()) else 0.0
                score = w + boost
                cluster_scores[cluster_key] = cluster_scores.get(cluster_key, 0.0) + score

                if cluster_key not in cluster_supporting_models:
                    cluster_supporting_models[cluster_key] = []
                cluster_supporting_models[cluster_key].append(m_id)

                if cluster_key not in cluster_surfaces:
                    cluster_surfaces[cluster_key] = {}
                surface = tok["surface"]
                cluster_surfaces[cluster_key][surface] = cluster_surfaces[cluster_key].get(surface, 0.0) + score

        if not cluster_scores:
            continue

        best_cluster, best_score = max(cluster_scores.items(), key=lambda x: x[1])
        if best_score > null_score:
            # Evidence-based surface selection: pick the surface form with the highest model vote!
            best_surface = max(cluster_surfaces[best_cluster].items(), key=lambda x: x[1])[0]

            # Verbatim-safe deduplication:
            # If the current word repeats the immediately preceding word:
            # Is it supported by MULTIPLE models (genuine repetition)? Or only ONE model (stutter loop)?
            num_supporters = len(cluster_supporting_models[best_cluster])
            if fused_tokens and normalize_arabic_english(fused_tokens[-1]) == normalize_arabic_english(best_surface):
                # If only 1 model produced this repeated token while others were null, it is an unconfirmed hallucination loop!
                # If 2 or more models agreed on this repetition, it is genuine spoken speech!
                if num_supporters < 2:
                    continue

            fused_tokens.append(best_surface)

    fused_text = " ".join(fused_tokens).strip()
    return {
        "fused_text": fused_text,
        "method": "rover_confusion_network_v3",
        "num_models": len(hypotheses),
        "num_slots": len(network),
    }


def fuse_hybrid_v3(
    hyp_spec: str,
    hyp_turbo: str,
    hyp_qwen: Optional[str] = None,
    duration_seconds: float = 45.0,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Main entry point for Verbatim Hybrid ASR V3 — Accuracy First:
    - If QwenCleo is available, synthesizes 3-model ROVER V3 with technical code-switching canonicalization and full particle deduplication
    - If QwenCleo is not provided, uses Conservative Agreement V2
    """
    is_conflict, reason = detect_critical_code_switch_conflict(hyp_spec, hyp_turbo)

    if hyp_qwen and hyp_qwen.strip():
        hyps = [
            {"model_id": "codeswitched-medium", "text": hyp_spec},
            {"model_id": "large-v3-turbo", "text": hyp_turbo},
            {"model_id": "qwencleo-asr-4bit", "text": hyp_qwen},
        ]
        res = fuse_rover_v3(hyps, weights=weights)
        res["code_switch_conflict_detected"] = is_conflict
        res["conflict_reason"] = reason
        res["qwen_invoked"] = True
        return res
    else:
        # Fallback to Conservative Agreement
        res = fuse_conservative_agreement(hyp_spec, hyp_turbo, duration_seconds=duration_seconds)
        res["code_switch_conflict_detected"] = is_conflict
        res["conflict_reason"] = reason
        res["qwen_invoked"] = False
        return res



def project_fused_words_to_segments(
    spec_segments: List[Dict[str, Any]], fused_text: str
) -> List[Dict[str, Any]]:
    """
    Projects global fused words onto Specialized Whisper segment timestamps
    to preserve precise playback and UI timeline alignment.
    """
    if not spec_segments:
        return [{"id": 1, "start": 0.0, "end": 45.0, "text": fused_text, "confidence": "high", "uncertain": False}]

    fused_words = fused_text.strip().split()
    if not fused_words:
        return []

    spec_tok_objs = []
    for s_idx, s in enumerate(spec_segments):
        words = s.get("text", "").strip().split()
        for w in words:
            spec_tok_objs.append({
                "surface": w,
                "norm": normalize_arabic_english(w),
                "norm_stem": normalize_arabic_english(w),
                "is_latin": is_latin_word(w),
                "has_latin": has_latin_chars(w),
                "seg_idx": s_idx,
            })

    fused_tok_objs = []
    for w in fused_words:
        fused_tok_objs.append({
            "surface": w,
            "norm": normalize_arabic_english(w),
            "norm_stem": normalize_arabic_english(w),
            "is_latin": is_latin_word(w),
            "has_latin": has_latin_chars(w),
        })

    if not spec_tok_objs:
        return [{
            "id": 1,
            "start": spec_segments[0].get("start", 0.0),
            "end": spec_segments[-1].get("end", 45.0),
            "text": fused_text,
            "confidence": "high",
            "uncertain": False,
        }]

    slots = align_hypotheses_pairwise_v2(spec_tok_objs, fused_tok_objs)

    seg_words: Dict[int, List[str]] = {i: [] for i in range(len(spec_segments))}
    cur_seg_idx = 0

    for slot in slots:
        ta = slot.get("a")
        tb = slot.get("b")
        if ta and "seg_idx" in ta:
            cur_seg_idx = ta["seg_idx"]
        if tb:
            seg_words[cur_seg_idx].append(tb["surface"])

    result_segments = []
    for s_idx, s in enumerate(spec_segments):
        seg_text = " ".join(seg_words[s_idx]).strip()
        result_segments.append({
            "id": s_idx + 1,
            "start": s.get("start", 0.0),
            "end": s.get("end", 0.0),
            "text": seg_text,
            "original_text": seg_text,
            "confidence": "high",
            "uncertain": False,
            "uncertain_reason": None,
            "words": [],
        })

    non_empty = [s for s in result_segments if s["text"]]
    return non_empty if non_empty else result_segments


