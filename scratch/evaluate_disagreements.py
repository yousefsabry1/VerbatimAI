"""
Diagnostic Disagreement Evaluation & Oracle Upper Bound Analysis
Evaluates the 3 certified human reference samples across:
- Primary Model: Egyptian Code-Switched Whisper Medium
- Alternative Model 1: Whisper Large-v3-Turbo
- Alternative Model 2: QwenCleo-ASR 1.7B 4-bit NF4
Calculates disagreement rate, disagreement scores, and Oracle Upper Bound.
"""
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.evaluation.diff_engine import compute_transcript_diff
from app.evaluation.metrics import calculate_wer_cer
from app.core.config import STORAGE_DIR

BENCHMARKS_DIR = STORAGE_DIR / "benchmarks"

def load_data():
    whisper_file = BENCHMARKS_DIR / "fair_whisper_benchmark_results.json"
    qwencleo_file = BENCHMARKS_DIR / "qwencleo_4bit_benchmark_results.json"

    whisper_data = json.loads(whisper_file.read_text(encoding="utf-8"))
    qwencleo_data = json.loads(qwencleo_file.read_text(encoding="utf-8"))

    return whisper_data, qwencleo_data

def evaluate():
    whisper_data, qwencleo_data = load_data()

    print("=" * 80)
    print("VERBATIM AI — DIAGNOSTIC DISAGREEMENT & ORACLE UPPER BOUND EVALUATION")
    print("=" * 80)

    # Filter to unfiltered 'none' runs
    whisper_unfiltered = [r for r in whisper_data if r.get("filter") == "none"]

    sample_meta = {
        "dev_0_103": {"name": "Development Sample (00:00 - 01:43.5)", "duration": 103.5, "ref_words": 203},
        "test_180_225": {"name": "Independent Test Sample (03:00 - 03:45)", "duration": 45.0, "ref_words": 111},
        "holdout_300_345": {"name": "Independent Holdout Sample (05:00 - 05:45)", "duration": 45.0, "ref_words": 89},
    }

    summary_table = []

    for sid in ["dev_0_103", "test_180_225", "holdout_300_345"]:
        meta = sample_meta[sid]

        # Primary: codeswitched-medium
        cs_res = next((r for r in whisper_unfiltered if r["sample_id"] == sid and r["model_id"] == "codeswitched-medium"), None)
        # Alt 1: large-v3-turbo
        turbo_res = next((r for r in whisper_unfiltered if r["sample_id"] == sid and r["model_id"] == "large-v3-turbo"), None)
        # Alt 2: qwencleo-asr-4bit
        qwen_res = next((r for r in qwencleo_data if r["sample_id"] == sid), None)

        cs_text = cs_res["predicted_text"] if cs_res else ""
        turbo_text = turbo_res["predicted_text"] if turbo_res else ""
        qwen_text = qwen_res.get("predicted_text", "") if qwen_res else ""

        cs_wer = cs_res["norm_wer"] if cs_res else 0.0
        cs_cer = cs_res["norm_cer"] if cs_res else 0.0

        turbo_wer = turbo_res["norm_wer"] if turbo_res else 0.0
        turbo_cer = turbo_res["norm_cer"] if turbo_res else 0.0

        qwen_wer = qwen_res["norm_wer"] if qwen_res else 0.0
        qwen_cer = qwen_res["norm_cer"] if qwen_res else 0.0

        # Disagreements between Primary and Alternatives
        diff_turbo = compute_transcript_diff(cs_text, turbo_text)
        diff_qwen = compute_transcript_diff(cs_text, qwen_text)

        # Oracle Best for this sample
        candidates = [
            ("codeswitched-medium", cs_wer, cs_cer),
            ("large-v3-turbo", turbo_wer, turbo_cer),
            ("qwencleo-asr-4bit", qwen_wer, qwen_cer),
        ]
        best_cand = min(candidates, key=lambda c: c[1])
        oracle_model, oracle_wer, oracle_cer = best_cand

        item = {
            "sample_id": sid,
            "sample_name": meta["name"],
            "duration": meta["duration"],
            "ref_words": meta["ref_words"],
            "codeswitched_wer": cs_wer,
            "codeswitched_cer": cs_cer,
            "turbo_wer": turbo_wer,
            "turbo_cer": turbo_cer,
            "turbo_disagreement": diff_turbo["disagreement_score"],
            "qwen_wer": qwen_wer,
            "qwen_cer": qwen_cer,
            "qwen_disagreement": diff_qwen["disagreement_score"],
            "oracle_model": oracle_model,
            "oracle_wer": oracle_wer,
            "oracle_cer": oracle_cer,
        }
        summary_table.append(item)

        print(f"\n--- Sample: {meta['name']} ---")
        print(f"Duration: {meta['duration']}s | Reference Words: {meta['ref_words']}")
        print(f"Primary (Specialized Medium): WER = {cs_wer:.2f}% | CER = {cs_cer:.2f}%")
        print(f"Alternative 1 (Whisper Turbo):  WER = {turbo_wer:.2f}% | CER = {turbo_cer:.2f}% | Disagreement = {diff_turbo['disagreement_score'] * 100:.1f}%")
        print(f"Alternative 2 (QwenCleo 4-bit): WER = {qwen_wer:.2f}% | CER = {qwen_cer:.2f}% | Disagreement = {diff_qwen['disagreement_score'] * 100:.1f}%")
        print(f"Sample Oracle Upper Bound:   WER = {oracle_wer:.2f}% (Selected: {oracle_model})")

    avg_cs_wer = sum(x["codeswitched_wer"] for x in summary_table) / len(summary_table)
    avg_cs_cer = sum(x["codeswitched_cer"] for x in summary_table) / len(summary_table)
    avg_turbo_wer = sum(x["turbo_wer"] for x in summary_table) / len(summary_table)
    avg_turbo_cer = sum(x["turbo_cer"] for x in summary_table) / len(summary_table)
    avg_qwen_wer = sum(x["qwen_wer"] for x in summary_table) / len(summary_table)
    avg_qwen_cer = sum(x["qwen_cer"] for x in summary_table) / len(summary_table)
    avg_oracle_wer = sum(x["oracle_wer"] for x in summary_table) / len(summary_table)
    avg_oracle_cer = sum(x["oracle_cer"] for x in summary_table) / len(summary_table)

    avg_turbo_disagreement = sum(x["turbo_disagreement"] for x in summary_table) / len(summary_table)
    avg_qwen_disagreement = sum(x["qwen_disagreement"] for x in summary_table) / len(summary_table)

    headroom = avg_cs_wer - avg_oracle_wer

    print("\n" + "=" * 80)
    print("SUMMARY COMPARISON & ACCURACY CEILING:")
    print("=" * 80)
    print(f"• Primary Production Default (Codeswitched Medium): {avg_cs_wer:.2f}% WER | {avg_cs_cer:.2f}% CER")
    print(f"• Alternative Model 1 (Whisper Large-v3-Turbo):     {avg_turbo_wer:.2f}% WER | {avg_turbo_cer:.2f}% CER | Avg Disagreement: {avg_turbo_disagreement * 100:.1f}%")
    print(f"• Alternative Model 2 (QwenCleo-ASR 1.7B 4-bit):    {avg_qwen_wer:.2f}% WER | {avg_qwen_cer:.2f}% CER | Avg Disagreement: {avg_qwen_disagreement * 100:.1f}%")
    print(f"• Theoretical Oracle Upper Bound (Sample-level):    {avg_oracle_wer:.2f}% WER | {avg_oracle_cer:.2f}% CER")
    print(f"• Potential Maximum Headroom over Primary:          -{headroom:.2f}% WER points")
    print("=" * 80)
    print("\nNOTE ON ORACLE UPPER BOUND:")
    print("The Oracle Upper Bound represents the theoretical ceiling achieved IF an omniscient")
    print("decision mechanism chose the superior hypothesis for every evaluation interval.")
    print("In real-world deployment, automated model routing can suffer from calibration errors,")
    print("so providing human reviewers with audio-grounded verification is the safest path to quality.")

    # Save output to JSON
    out_file = Path(__file__).resolve().parent / "disagreement_oracle_evaluation.json"
    out_file.write_text(json.dumps({
        "samples": summary_table,
        "averages": {
            "codeswitched_medium": {"wer": round(avg_cs_wer, 2), "cer": round(avg_cs_cer, 2)},
            "large_v3_turbo": {"wer": round(avg_turbo_wer, 2), "cer": round(avg_turbo_cer, 2), "disagreement": round(avg_turbo_disagreement, 3)},
            "qwencleo_4bit": {"wer": round(avg_qwen_wer, 2), "cer": round(avg_qwen_cer, 2), "disagreement": round(avg_qwen_disagreement, 3)},
            "oracle_upper_bound": {"wer": round(avg_oracle_wer, 2), "cer": round(avg_oracle_cer, 2)},
            "potential_headroom_points": round(headroom, 2),
        }
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWritten detailed evaluation metrics to: {out_file}")

if __name__ == "__main__":
    evaluate()
