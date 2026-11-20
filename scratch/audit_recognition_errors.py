"""
Deep Audit of Current Recognition Errors on Certified Human References.
Analyzes error distributions across Egyptian Arabic colloquialisms,
English technical code-switching, negations, and acoustic boundary drops.
"""
import json
import re
from pathlib import Path
from collections import Counter

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent / "backend" / "storage" / "benchmarks"
WHISPER_RESULTS = BENCHMARKS_DIR / "fair_whisper_benchmark_results.json"
QWEN_RESULTS = BENCHMARKS_DIR / "qwencleo_4bit_benchmark_results.json"

def classify_word(word: str) -> str:
    w = word.strip().lower()
    # Check if English / Latin script
    if re.search(r'[a-zA-Z]', w):
        return "english_technical"
    
    # Check Egyptian colloquial negations
    if w in ["مش", "ملهمش", "ما", "بلاش", "لا", "مش_عارف"]:
        return "egyptian_negation"
    
    # Check Egyptian colloquial verbs / discourse markers
    if w in ["فببص", "ببص", "عايزين", "حط", "نشيلها", "شيل", "شوف", "تلاقيه", "باعتهالك", "استنى", "قايل", "نظبط", "هتبعت"]:
        return "egyptian_colloquial_verb"
    
    # Check Egyptian colloquial particles / demonstratives / fillers
    if w in ["كدا", "كده", "دا", "دي", "الي", "اهوت", "خالص", "ااه", "تمام", "ماشي", "بردو", "برضه", "سوا", "اي"]:
        return "egyptian_particle_filler"
    
    # Common formal / general Arabic
    return "general_arabic"

def audit():
    whisper_data = json.loads(WHISPER_RESULTS.read_text(encoding="utf-8"))
    
    print("=" * 80)
    print("VERBATIM AI — DEEP RECOGNITION ERROR AUDIT (CODESWITCHED-MEDIUM)")
    print("=" * 80)
    
    # Collect results for codeswitched-medium unfiltered
    cs_runs = [r for r in whisper_data if r.get("model_id") == "codeswitched-medium" and r.get("filter") == "none"]
    
    category_errors = Counter()
    total_substitutions = 0
    total_deletions = 0
    total_insertions = 0
    
    detailed_error_log = []
    
    for run in cs_runs:
        sid = run["sample_id"]
        sname = run.get("sample_name", sid)
        alignment = run.get("word_alignment", [])
        
        print(f"\n--- Sample: {sname} ({sid}) ---")
        print(f"Norm WER: {run['norm_wer']}% | Subs: {run['norm_sub']} | Dels: {run['norm_del']} | Ins: {run['norm_ins']}")
        
        subs = [a for a in alignment if a["type"] == "substitute"]
        dels = [a for a in alignment if a["type"] == "delete"]
        ins = [a for a in alignment if a["type"] == "insert"]
        
        total_substitutions += len(subs)
        total_deletions += len(dels)
        total_insertions += len(ins)
        
        print("\nNotable Linguistic Errors in this Sample:")
        for a in subs[:15]:
            ref_w = a.get("ref", "")
            hyp_w = a.get("hyp", "")
            cat = classify_word(ref_w)
            category_errors[cat] += 1
            detailed_error_log.append((sid, "substitution", ref_w, hyp_w, cat))
            print(f"  • [SUB] Ref: '{ref_w}' -> Hyp: '{hyp_w}' (Class: {cat})")
            
        for a in dels[:10]:
            ref_w = a.get("ref", "")
            cat = classify_word(ref_w)
            category_errors[f"del_{cat}"] += 1
            detailed_error_log.append((sid, "deletion", ref_w, "", cat))
            print(f"  • [DEL] Ref: '{ref_w}' dropped completely (Class: {cat})")
            
        for a in ins[:5]:
            hyp_w = a.get("hyp", "")
            category_errors["insertion"] += 1
            print(f"  • [INS] Inserted hallucinated: '{hyp_w}'")
            
    print("\n" + "=" * 80)
    print("ERROR CATEGORY BREAKDOWN ACROSS ALL 3 HUMAN SAMPLES:")
    print("=" * 80)
    for cat, count in category_errors.most_common():
        print(f"  • {cat.replace('_', ' ').title()}: {count} errors")
        
    print(f"\nTotal Substitutions: {total_substitutions}")
    print(f"Total Deletions (Omissions): {total_deletions}")
    print(f"Total Insertions (Hallucinations): {total_insertions}")
    print("=" * 80)

if __name__ == "__main__":
    audit()
