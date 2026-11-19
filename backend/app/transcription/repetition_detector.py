import re
from typing import Optional, Dict, Any, List, Tuple


def find_repeated_ngrams(tokens: List[str], min_n: int = 1, max_n: int = 4, min_repeats: int = 4) -> Optional[Dict[str, Any]]:
    """
    Scans a token sequence for consecutive pathological repetition loops.
    For n=1 (single word), requires at least `min_repeats` (default 4) consecutive occurrences.
    For n>=2 (multi-word phrase), requires at least 3 consecutive occurrences.
    
    This preserves genuine conversational repetitions (e.g., 'لا لا', 'مش مشكلة', 'طبعا طبعا')
    while detecting pathological ASR hallucinations (e.g., 'مشي ومشي ومشي ومشي ومشي...' 20+ times).
    """
    if not tokens or len(tokens) < min_repeats:
        return None

    # Clean tokens of punctuation for detection comparison
    cleaned_tokens = [re.sub(r"[^\w\s]", "", t).strip().lower() for t in tokens]

    # Check for single word repetition
    current_word = None
    count = 0
    start_idx = 0

    for idx, tok in enumerate(cleaned_tokens):
        if not tok:
            continue
        if tok == current_word:
            count += 1
            if count >= min_repeats:
                return {
                    "pattern_type": "single_word",
                    "phrase": current_word,
                    "repeats": count,
                    "token_start_idx": start_idx,
                    "token_end_idx": idx,
                }
        else:
            current_word = tok
            count = 1
            start_idx = idx

    # Check for phrase / n-gram repetition (n=2 to 4)
    num_tokens = len(cleaned_tokens)
    for n in range(2, min(max_n + 1, num_tokens // 2 + 1)):
        for i in range(num_tokens - n * 2 + 1):
            pattern = cleaned_tokens[i:i + n]
            if not any(pattern):
                continue
            
            # Count how many times this pattern repeats consecutively
            repeats = 1
            curr_pos = i + n
            while curr_pos + n <= num_tokens:
                next_slice = cleaned_tokens[curr_pos:curr_pos + n]
                if next_slice == pattern:
                    repeats += 1
                    curr_pos += n
                else:
                    break

            if repeats >= 3:  # 3 consecutive phrases is pathological
                return {
                    "pattern_type": f"{n}_gram",
                    "phrase": " ".join(tokens[i:i + n]),
                    "repeats": repeats,
                    "token_start_idx": i,
                    "token_end_idx": curr_pos - 1,
                }

    return None


def detect_repetition_in_segment(text: str) -> Optional[Dict[str, Any]]:
    """
    Analyzes segment text for pathological repetition loops.
    Returns loop metadata if detected, otherwise None.
    """
    if not text:
        return None

    words = text.split()
    loop_info = find_repeated_ngrams(words, min_n=1, max_n=4, min_repeats=4)
    if loop_info:
        return {
            "has_repetition_loop": True,
            "pattern": loop_info["phrase"],
            "repeats": loop_info["repeats"],
            "type": loop_info["pattern_type"],
            "raw_text": text,
        }

    # Also check for character-level loops (e.g. 'اي اي اي اي اي اي اي')
    char_match = re.search(r"(\b\w{1,3}\b[\s,،]*){6,}", text)
    if char_match:
        matched_str = char_match.group(0).strip()
        tokens = matched_str.split()
        if len(tokens) >= 5 and len(set(tokens)) <= 2:
            return {
                "has_repetition_loop": True,
                "pattern": tokens[0],
                "repeats": len(tokens),
                "type": "short_word_loop",
                "raw_text": text,
            }

    return None
