import re
import unicodedata
from typing import Dict, Any, List, Tuple, Optional


def normalize_arabic_english(text: str) -> str:
    """
    Standard documented normalization for Egyptian Arabic mixed with English.
    Preserves all semantic words while standardizing common orthographic variants:
    - Unicode NFKC normalization
    - Removes Arabic Tashkeel (harakat / diacritics) and Tatweel (kashida)
    - Normalizes Alef variants: [إأآٱ] -> ا
    - Normalizes Teh Marbuta: ة -> ه
    - Normalizes Alef Maksura: ى -> ي
    - Removes punctuation (both Arabic and ASCII)
    - Lowercases English characters
    - Collapses multiple whitespace
    """
    if not text:
        return ""

    # 1. Unicode NFKC
    text = unicodedata.normalize("NFKC", text)

    # 2. Remove Tatweel (kashida)
    text = text.replace("\u0640", "")

    # 3. Remove Arabic Tashkeel (diacritics: fatha, damma, kasra, sukun, tanwin, shadda)
    tashkeel_regex = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0653-\u065F]")
    text = tashkeel_regex.sub("", text)

    # 4. Standardize Alef variants
    text = re.sub(r"[إأآٱ]", "ا", text)

    # 5. Standardize Teh Marbuta
    text = re.sub(r"ة", "ه", text)

    # 6. Standardize Alef Maksura to Yeh
    text = re.sub(r"ى", "ي", text)

    # 7. Lowercase Latin characters
    text = text.lower()

    # 8. Remove punctuation (Arabic and standard)
    punctuation_regex = re.compile(r"[\.,!?:;\-\–\—_\"\'\(\)\[\]\{\}«»“”؟،؛…\/\\|*&^%$#@~`+=<>]+")
    text = punctuation_regex.sub(" ", text)

    # 9. Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def normalize_raw(text: str) -> str:
    """
    Raw normalization: preserves punctuation, letter variants, and casing,
    only collapsing consecutive whitespace and linebreaks.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def align_sequences(
    ref_tokens: List[str], hyp_tokens: List[str]
) -> Tuple[int, int, int, int, List[Dict[str, Any]]]:
    """
    Wagner-Fischer Dynamic Programming alignment for computing:
    Substitutions (S), Deletions (D), Insertions (I), Hits (H),
    and the explicit sequence alignment operations.
    """
    n = len(ref_tokens)
    m = len(hyp_tokens)

    # dp[i][j] = cost of transforming ref_tokens[:i] into hyp_tokens[:j]
    dp = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_tokens[i - 1] == hyp_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j - 1],  # Substitution
                    dp[i - 1][j],      # Deletion
                    dp[i][j - 1],      # Insertion
                )

    # Backtrace to find optimal alignment
    i, j = n, m
    alignment_ops = []

    substitutions = 0
    deletions = 0
    insertions = 0
    hits = 0

    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref_tokens[i - 1] == hyp_tokens[j - 1]:
            alignment_ops.append({
                "type": "equal",
                "ref": ref_tokens[i - 1],
                "hyp": hyp_tokens[j - 1],
            })
            hits += 1
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            alignment_ops.append({
                "type": "substitute",
                "ref": ref_tokens[i - 1],
                "hyp": hyp_tokens[j - 1],
            })
            substitutions += 1
            i -= 1
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            alignment_ops.append({
                "type": "delete",
                "ref": ref_tokens[i - 1],
                "hyp": None,
            })
            deletions += 1
            i -= 1
        else:
            alignment_ops.append({
                "type": "insert",
                "ref": None,
                "hyp": hyp_tokens[j - 1],
            })
            insertions += 1
            j -= 1

    alignment_ops.reverse()
    return substitutions, deletions, insertions, hits, alignment_ops


def calculate_wer_cer(
    reference: str, hypothesis: str, mode: str = "normalized"
) -> Dict[str, Any]:
    """
    Computes Word Error Rate (WER) and Character Error Rate (CER),
    with full alignment and breakdown.
    mode: "normalized" or "raw"
    """
    if mode == "normalized":
        clean_ref = normalize_arabic_english(reference)
        clean_hyp = normalize_arabic_english(hypothesis)
    else:
        clean_ref = normalize_raw(reference)
        clean_hyp = normalize_raw(hypothesis)

    ref_words = clean_ref.split() if clean_ref else []
    hyp_words = clean_hyp.split() if clean_hyp else []

    # Word-level alignment
    sub_w, del_w, ins_w, hits_w, word_ops = align_sequences(ref_words, hyp_words)
    total_ref_words = len(ref_words)
    total_hyp_words = len(hyp_words)

    wer = (sub_w + del_w + ins_w) / max(1, total_ref_words)

    # Character-level alignment (excluding spaces)
    ref_chars = [c for c in clean_ref if not c.isspace()]
    hyp_chars = [c for c in clean_hyp if not c.isspace()]
    sub_c, del_c, ins_c, hits_c, char_ops = align_sequences(ref_chars, hyp_chars)
    total_ref_chars = len(ref_chars)
    total_hyp_chars = len(hyp_chars)

    cer = (sub_c + del_c + ins_c) / max(1, total_ref_chars)

    return {
        "mode": mode,
        "wer": round(wer, 4),
        "wer_percent": round(wer * 100, 2),
        "cer": round(cer, 4),
        "cer_percent": round(cer * 100, 2),
        "substitutions": sub_w,
        "deletions": del_w,
        "insertions": ins_w,
        "hits": hits_w,
        "ref_words_count": total_ref_words,
        "hyp_words_count": total_hyp_words,
        "ref_chars_count": total_ref_chars,
        "hyp_chars_count": total_hyp_chars,
        "clean_reference": clean_ref,
        "clean_hypothesis": clean_hyp,
        "word_alignment": word_ops,
    }
