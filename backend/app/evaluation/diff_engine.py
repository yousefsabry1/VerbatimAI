import re
from typing import List, Dict, Any, Tuple


def _normalize_token_for_diff(token: str) -> str:
    """
    Normalizes a token for comparison purposes without altering original surface rendering.
    - Lowercases Latin characters.
    - Unifies Arabic alef variants (أ, إ, آ -> ا).
    - Unifies teh marbuta / heh (ة -> ه).
    - Unifies Persian/Urdu kaf/yeh variants if present.
    - Strips Arabic tashkeel (diacritics) and tatweel.
    - Strips punctuation surrounding the word.
    """
    t = token.lower().strip()
    # Strip common punctuation attached to words
    t = re.sub(r"^[^\w\s]+|[^\w\s]+$", "", t, flags=re.UNICODE)

    # Arabic diacritics / tashkeel & tatweel
    t = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", t)

    # Alef normalization
    t = re.sub(r"[إأآٱ]", "ا", t)
    # Teh marbuta / heh
    t = re.sub(r"ة", "ه", t)
    # Yeh normalization (ى -> ي)
    t = re.sub(r"ى", "ي", t)

    return t


def tokenize_mixed_text(text: str) -> List[str]:
    """
    Splits mixed Arabic, English, and numeric text into words.
    Preserves exact tokens for rendering.
    """
    if not text:
        return []
    # Split on whitespace while keeping words intact
    tokens = [t.strip() for t in text.split() if t.strip()]
    return tokens


def compute_transcript_diff(primary_text: str, alternative_text: str) -> Dict[str, Any]:
    """
    Computes a word-level diff between primary ASR text and alternative ASR text.
    Uses dynamic programming (Levenshtein / LCS alignment) with Unicode-aware normalization.
    Returns:
      - chunks: list of diff objects with type in ('equal', 'substitute', 'insert', 'delete')
      - disagreement_score: float in [0.0, 1.0+]
      - stats: counts of matches, substitutions, deletions, insertions
    """
    prim_tokens = tokenize_mixed_text(primary_text)
    alt_tokens = tokenize_mixed_text(alternative_text)

    prim_norm = [_normalize_token_for_diff(t) for t in prim_tokens]
    alt_norm = [_normalize_token_for_diff(t) for t in alt_tokens]

    n = len(prim_norm)
    m = len(alt_norm)

    if n == 0 and m == 0:
        return {
            "disagreement_score": 0.0,
            "stats": {"equal": 0, "substitute": 0, "delete": 0, "insert": 0},
            "chunks": [],
        }

    # Levenshtein distance matrix with backpointers
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    ops = [[""] * (m + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        dp[i][0] = i
        ops[i][0] = "del"

    for j in range(1, m + 1):
        dp[0][j] = j
        ops[0][j] = "ins"

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if prim_norm[i - 1] == alt_norm[j - 1] and prim_norm[i - 1] != "":
                cost = 0
                match_op = "eq"
            else:
                cost = 1
                match_op = "sub"

            sub_val = dp[i - 1][j - 1] + cost
            del_val = dp[i - 1][j] + 1
            ins_val = dp[i][j - 1] + 1

            best_val = sub_val
            best_op = match_op

            if del_val < best_val:
                best_val = del_val
                best_op = "del"

            if ins_val < best_val:
                best_val = ins_val
                best_op = "ins"

            dp[i][j] = best_val
            ops[i][j] = best_op

    # Backtrace path
    i = n
    j = m
    aligned_chunks: List[Dict[str, Any]] = []

    stats = {"equal": 0, "substitute": 0, "delete": 0, "insert": 0}

    while i > 0 or j > 0:
        curr_op = ops[i][j]
        if curr_op == "eq":
            aligned_chunks.append({
                "type": "equal",
                "primary": prim_tokens[i - 1],
                "alternative": alt_tokens[j - 1],
            })
            stats["equal"] += 1
            i -= 1
            j -= 1
        elif curr_op == "sub":
            aligned_chunks.append({
                "type": "substitute",
                "primary": prim_tokens[i - 1],
                "alternative": alt_tokens[j - 1],
            })
            stats["substitute"] += 1
            i -= 1
            j -= 1
        elif curr_op == "del":
            aligned_chunks.append({
                "type": "delete",
                "primary": prim_tokens[i - 1],
                "alternative": None,
            })
            stats["delete"] += 1
            i -= 1
        elif curr_op == "ins":
            aligned_chunks.append({
                "type": "insert",
                "primary": None,
                "alternative": alt_tokens[j - 1],
            })
            stats["insert"] += 1
            j -= 1
        else:
            break

    aligned_chunks.reverse()

    # Disagreement score: proportion of non-matching words relative to primary length
    total_ref_words = max(1, len(prim_tokens))
    disagreement_count = stats["substitute"] + stats["delete"] + stats["insert"]
    disagreement_score = round(min(1.0, disagreement_count / total_ref_words), 3)

    return {
        "disagreement_score": disagreement_score,
        "stats": stats,
        "chunks": aligned_chunks,
    }
