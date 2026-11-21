import os
import sys
import time
import json
import gc
import random
from pathlib import Path
from typing import Dict, List, Any

# Ensure backend is on sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.evaluation.metrics import normalize_arabic_english, calculate_wer_cer
from app.transcription.engine import load_whisper_model, clear_loaded_models_cache
from app.transcription.qwencleo_client import get_qwencleo_client
from app.transcription.hybrid_fusion import fuse_hybrid_v2, fuse_hybrid_v3

eval_dir = backend_dir / "storage" / "research_eval"
manifest_path = eval_dir / "manifest.json"
audio_dir = eval_dir / "audio"

with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)

print(f"Loaded manifest with {len(manifest)} evaluation clips.")

raw_predictions_path = eval_dir / "predictions_raw.json"
if raw_predictions_path.exists():
    try:
        with open(raw_predictions_path, "r", encoding="utf-8") as f:
            all_predictions = json.load(f)
        print("Loaded existing raw predictions from disk.")
    except Exception:
        all_predictions = {}
else:
    all_predictions = {}

def is_model_complete(model_key):
    return all(sample["sample_id"] in all_predictions and model_key in all_predictions[sample["sample_id"]] for sample in manifest)

# =========================================================================
# PHASE 5A: Model A — Specialized Whisper Medium
# =========================================================================
if not is_model_complete("codeswitched-medium"):
    print("\n>>> Running Model A: Specialized Whisper Medium (codeswitched-medium) on CUDA...")
    model, device, compute_type = load_whisper_model("codeswitched-medium")
    for i, item in enumerate(manifest):
        sid = item["sample_id"]
        if sid not in all_predictions:
            all_predictions[sid] = {}
        if "codeswitched-medium" in all_predictions[sid]:
            continue
        
        wav_file = str(audio_dir / item["audio_filename"])
        t0 = time.time()
        segments, info = model.transcribe(
            wav_file,
            beam_size=5,
            language="ar",
            temperature=0.0,
            word_timestamps=True
        )
        seg_list = []
        for s in segments:
            seg_dict = {
                "start": s.start,
                "end": s.end,
                "text": s.text.strip(),
                "words": [{"word": w.word, "start": w.start, "end": w.end, "probability": w.probability} for w in (s.words or [])]
            }
            seg_list.append(seg_dict)
        elapsed = time.time() - t0
        full_text = " ".join(s["text"] for s in seg_list).strip()
        all_predictions[sid]["codeswitched-medium"] = {
            "text": full_text,
            "segments": seg_list,
            "elapsed_seconds": round(elapsed, 2)
        }
        print(f"  [{i+1}/{len(manifest)}] Specialized -> {sid} ({elapsed:.2f}s): {full_text[:60]}...")
    clear_loaded_models_cache()
    gc.collect()
    print("Model A completed. VRAM cleared.")

# =========================================================================
# PHASE 5B: Model B — Whisper Large-v3-Turbo
# =========================================================================
if not is_model_complete("large-v3-turbo"):
    print("\n>>> Running Model B: Whisper Large-v3-Turbo (large-v3-turbo) on CUDA...")
    model, device, compute_type = load_whisper_model("large-v3-turbo")
    for i, item in enumerate(manifest):
        sid = item["sample_id"]
        if sid not in all_predictions:
            all_predictions[sid] = {}
        if "large-v3-turbo" in all_predictions[sid]:
            continue
        
        wav_file = str(audio_dir / item["audio_filename"])
        t0 = time.time()
        segments, info = model.transcribe(
            wav_file,
            beam_size=5,
            language="ar",
            temperature=0.0,
            word_timestamps=True
        )
        seg_list = []
        for s in segments:
            seg_dict = {
                "start": s.start,
                "end": s.end,
                "text": s.text.strip(),
                "words": [{"word": w.word, "start": w.start, "end": w.end, "probability": w.probability} for w in (s.words or [])]
            }
            seg_list.append(seg_dict)
        elapsed = time.time() - t0
        full_text = " ".join(s["text"] for s in seg_list).strip()
        all_predictions[sid]["large-v3-turbo"] = {
            "text": full_text,
            "segments": seg_list,
            "elapsed_seconds": round(elapsed, 2)
        }
        print(f"  [{i+1}/{len(manifest)}] Turbo -> {sid} ({elapsed:.2f}s): {full_text[:60]}...")
    clear_loaded_models_cache()
    gc.collect()
    print("Model B completed. VRAM cleared.")

# =========================================================================
# PHASE 5C: Model C — QwenCleo-ASR 1.7B (4-bit NF4)
# =========================================================================
if not is_model_complete("qwencleo-asr-4bit"):
    print("\n>>> Running Model C: QwenCleo-ASR 1.7B (4-bit NF4) via managed persistent worker...")
    client = get_qwencleo_client()
    ok = client.start()
    if not ok:
        raise RuntimeError("Failed to start QwenCleo persistent worker")
    print("QwenCleo persistent worker is online.")
    
    for i, item in enumerate(manifest):
        sid = item["sample_id"]
        if sid not in all_predictions:
            all_predictions[sid] = {}
        if "qwencleo-asr-4bit" in all_predictions[sid]:
            continue
        
        wav_file = str(audio_dir / item["audio_filename"])
        t0 = time.time()
        res = client.transcribe(wav_file, language="Arabic")
        elapsed = time.time() - t0
        pred_text = res.get("text", "").strip()
        all_predictions[sid]["qwencleo-asr-4bit"] = {
            "text": pred_text,
            "elapsed_seconds": round(elapsed, 2),
            "peak_vram_mb": res.get("peak_vram_mb", 0.0)
        }
        print(f"  [{i+1}/{len(manifest)}] QwenCleo -> {sid} ({elapsed:.2f}s): {pred_text[:60]}...")
    client.shutdown()
    print("Model C completed. Worker shutdown and VRAM released.")

# Save raw base predictions
with open(raw_predictions_path, "w", encoding="utf-8") as f:
    json.dump(all_predictions, f, ensure_ascii=False, indent=2)
print("\nRaw base model predictions saved to predictions_raw.json.")

# =========================================================================
# PHASE 5D & 5E: Model D (Hybrid V2) & Model E (Hybrid V3) Fusion
# =========================================================================
print("\n>>> Running Multi-Model Fusion: Hybrid V2 and Hybrid V3 Audited Verbatim...")
for i, item in enumerate(manifest):
    sid = item["sample_id"]
    preds = all_predictions[sid]
    
    med_text = preds["codeswitched-medium"]["text"]
    tur_text = preds["large-v3-turbo"]["text"]
    qwen_text = preds["qwencleo-asr-4bit"]["text"]
    dur = item.get("duration_seconds", 10.0)
    
    # Run Hybrid V2
    t0 = time.time()
    v2_fused = fuse_hybrid_v2(med_text, tur_text, qwen_text, duration_seconds=dur)
    v2_elapsed = time.time() - t0
    preds["hybrid-v2"] = {
        "text": v2_fused.get("fused_text", ""),
        "confidence": v2_fused.get("confidence", 0.0),
        "elapsed_seconds": round(v2_elapsed, 4)
    }
    
    # Run Hybrid V3 Audited Verbatim
    t1 = time.time()
    v3_fused = fuse_hybrid_v3(med_text, tur_text, qwen_text, duration_seconds=dur)
    v3_elapsed = time.time() - t1
    preds["hybrid-v3"] = {
        "text": v3_fused.get("fused_text", ""),
        "confidence": v3_fused.get("confidence", 0.0),
        "elapsed_seconds": round(v3_elapsed, 4),
        "dropped_stutters": v3_fused.get("dropped_stutters", 0),
        "preserved_repetitions": v3_fused.get("preserved_repetitions", 0)
    }

# Save all predictions including fusions
with open(raw_predictions_path, "w", encoding="utf-8") as f:
    json.dump(all_predictions, f, ensure_ascii=False, indent=2)
print("All 5 models evaluated and stored cleanly.")

# =========================================================================
# PHASE 6: Compute Scientific Accuracy Metrics
# =========================================================================
print("\n>>> Computing Scientific Accuracy Metrics...")

models_to_score = [
    ("Specialized Whisper Medium", "codeswitched-medium"),
    ("Whisper Large-v3-Turbo", "large-v3-turbo"),
    ("QwenCleo-ASR 1.7B (4-bit NF4)", "qwencleo-asr-4bit"),
    ("Hybrid ASR V2 (Performance Optimized)", "hybrid-v2"),
    ("Hybrid ASR V3 (Audited Strict Verbatim)", "hybrid-v3"),
]

def score_predictions(norm_func=None):
    results = {}
    for label, key in models_to_score:
        tot_ref_words = 0
        tot_ref_chars = 0
        tot_errors = 0
        tot_subs = 0
        tot_dels = 0
        tot_inss = 0
        tot_char_errors = 0
        
        sample_wers = []
        sample_cers = []
        per_sample_details = []
        
        # Category breakdowns
        cat_stats = {
            "CAT_A_CONV": {"ref_words": 0, "errors": 0, "sample_wers": []},
            "CAT_B_CODESWITCH": {"ref_words": 0, "errors": 0, "sample_wers": []},
            "CAT_C_CHALLENGING": {"ref_words": 0, "errors": 0, "sample_wers": []},
            "CAT_D_ACADEMIC": {"ref_words": 0, "errors": 0, "sample_wers": []},
        }

        for item in manifest:
            sid = item["sample_id"]
            cat = item["category"]
            raw_ref = item["reference_text"]
            raw_hyp = all_predictions[sid][key]["text"]
            
            if norm_func:
                ref = norm_func(raw_ref)
                hyp = norm_func(raw_hyp)
            else:
                ref = " ".join(raw_ref.strip().split())
                hyp = " ".join(raw_hyp.strip().split())
            
            metrics = calculate_wer_cer(ref, hyp)
            r_words = max(1, metrics["ref_words_count"])
            r_chars = max(1, metrics["ref_chars_count"])
            word_errs = metrics["substitutions"] + metrics["deletions"] + metrics["insertions"]
            char_errs = round(metrics["cer"] * r_chars)
            
            tot_ref_words += r_words
            tot_ref_chars += r_chars
            tot_errors += word_errs
            tot_subs += metrics["substitutions"]
            tot_dels += metrics["deletions"]
            tot_inss += metrics["insertions"]
            tot_char_errors += char_errs
            
            sample_wers.append(metrics["wer"])
            sample_cers.append(metrics["cer"])
            
            cat_stats[cat]["ref_words"] += r_words
            cat_stats[cat]["errors"] += word_errs
            cat_stats[cat]["sample_wers"].append(metrics["wer"])
            
            per_sample_details.append({
                "sample_id": sid,
                "category": cat,
                "ref": ref,
                "hyp": hyp,
                "wer": round(metrics["wer"] * 100, 2),
                "cer": round(metrics["cer"] * 100, 2),
                "errors": word_errs,
                "subs": metrics["substitutions"],
                "dels": metrics["deletions"],
                "inss": metrics["insertions"]
            })
            
        micro_wer = (tot_errors / tot_ref_words) * 100
        macro_wer = (sum(sample_wers) / len(sample_wers)) * 100
        micro_cer = (tot_char_errors / tot_ref_chars) * 100
        macro_cer = (sum(sample_cers) / len(sample_cers)) * 100
        
        # Category summaries
        categories_summary = {}
        for c_name, c_data in cat_stats.items():
            c_micro = (c_data["errors"] / max(1, c_data["ref_words"])) * 100
            c_macro = (sum(c_data["sample_wers"]) / max(1, len(c_data["sample_wers"]))) * 100
            categories_summary[c_name] = {
                "ref_words": c_data["ref_words"],
                "errors": c_data["errors"],
                "micro_wer": round(c_micro, 2),
                "macro_wer": round(c_macro, 2),
            }

        results[label] = {
            "key": key,
            "total_ref_words": tot_ref_words,
            "total_ref_chars": tot_ref_chars,
            "total_errors": tot_errors,
            "substitutions": tot_subs,
            "deletions": tot_dels,
            "insertions": tot_inss,
            "micro_wer": round(micro_wer, 2),
            "macro_wer": round(macro_wer, 2),
            "micro_cer": round(micro_cer, 2),
            "macro_cer": round(macro_cer, 2),
            "categories": categories_summary,
            "sample_details": per_sample_details
        }
    return results

# 1. Normalized Scoring (Standard Arabic & English normalization)
norm_results = score_predictions(normalize_arabic_english)

# 2. Strict Unnormalized Scoring (Literal surface characters)
strict_results = score_predictions(None)

# =========================================================================
# PHASE 7: Statistical Analysis & Bootstrap Clustered CI
# =========================================================================
print("\n>>> Performing Statistical Bootstrap Analysis (B=1000)...")
random.seed(42)
B = 1000
# Cluster by video_id to avoid intra-speaker correlation
video_clusters = {}
for idx, item in enumerate(manifest):
    v = item["video_id"]
    if v not in video_clusters:
        video_clusters[v] = []
    video_clusters[v].append(idx)
cluster_keys = list(video_clusters.keys())

bootstrap_ci = {}
for label, key in models_to_score:
    boot_wers = []
    for _ in range(B):
        resampled_clusters = random.choices(cluster_keys, k=len(cluster_keys))
        sample_indices = [idx for c in resampled_clusters for idx in video_clusters[c]]
        
        b_ref_words = 0
        b_errors = 0
        for idx in sample_indices:
            item = manifest[idx]
            sid = item["sample_id"]
            ref = normalize_arabic_english(item["reference_text"])
            hyp = normalize_arabic_english(all_predictions[sid][key]["text"])
            metrics = calculate_wer_cer(ref, hyp)
            r_words = max(1, metrics["ref_words_count"])
            b_ref_words += r_words
            b_errors += (metrics["substitutions"] + metrics["deletions"] + metrics["insertions"])
        boot_wers.append((b_errors / b_ref_words) * 100)
    boot_wers.sort()
    ci_lower = boot_wers[int(0.025 * B)]
    ci_upper = boot_wers[int(0.975 * B)]
    bootstrap_ci[label] = {
        "ci_95_lower": round(ci_lower, 2),
        "ci_95_upper": round(ci_upper, 2),
    }

# =========================================================================
# Consolidate Final Evaluation Results
# =========================================================================
final_evaluation_report = {
    "evaluation_phase": "INDEPENDENT_ACCURACY_VALIDATION",
    "git_commit": "7090c3b",
    "total_samples": len(manifest),
    "total_reference_words": norm_results["Specialized Whisper Medium"]["total_ref_words"],
    "total_reference_chars": norm_results["Specialized Whisper Medium"]["total_ref_chars"],
    "categories": {
        "CAT_A_CONV": "Egyptian Arabic Conversational Speech (6 clips)",
        "CAT_B_CODESWITCH": "Egyptian Arabic-English Code-Switching (8 clips)",
        "CAT_C_CHALLENGING": "Challenging Acoustic Conditions & Spoken Repetitions (5 clips)",
        "CAT_D_ACADEMIC": "Technical & Academic Egyptian Speech (5 clips)",
    },
    "normalized_results": norm_results,
    "strict_unnormalized_results": strict_results,
    "bootstrap_confidence_intervals": bootstrap_ci,
}

eval_results_path = eval_dir / "evaluation_results.json"
with open(eval_results_path, "w", encoding="utf-8") as f:
    json.dump(final_evaluation_report, f, ensure_ascii=False, indent=2)

print("\n" + "="*80)
print("INDEPENDENT ACCURACY EVALUATION RESULTS (Normalized)")
print("="*80)
print(f"{'Model':<40} | {'Errors':<8} | {'Micro WER':<10} | {'Macro WER':<10} | {'Micro CER':<10} | {'95% CI':<15}")
print("-" * 100)
for label, key in models_to_score:
    res = norm_results[label]
    ci = bootstrap_ci[label]
    ci_str = f"[{ci['ci_95_lower']}%, {ci['ci_95_upper']}%]"
    print(f"{label:<40} | {res['total_errors']:<8} | {res['micro_wer']:<9}% | {res['macro_wer']:<9}% | {res['micro_cer']:<9}% | {ci_str:<15}")

print("\n" + "="*80)
print("CATEGORY-BY-CATEGORY BREAKDOWN (Micro WER)")
print("="*80)
cat_keys = ["CAT_A_CONV", "CAT_B_CODESWITCH", "CAT_C_CHALLENGING", "CAT_D_ACADEMIC"]
header = f"{'Model':<35} | " + " | ".join(f"{c:<16}" for c in cat_keys)
print(header)
print("-" * len(header))
for label, key in models_to_score:
    row_cats = [f"{norm_results[label]['categories'][c]['micro_wer']}% ({norm_results[label]['categories'][c]['errors']})" for c in cat_keys]
    print(f"{label:<35} | " + " | ".join(f"{rc:<16}" for rc in row_cats))

print("\nResults successfully saved to:", eval_results_path)
