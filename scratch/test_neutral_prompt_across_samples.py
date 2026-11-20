"""
Test Neutral Context Prompt across all 3 Certified Human Reference Samples:
- dev_0_103 (00:00 - 01:43.5)
- test_180_225 (03:00 - 03:45)
- holdout_300_345 (05:00 - 05:45)
Compares:
1. Baseline (Unprompted, codeswitched-medium, CUDA int8_float16)
2. Neutral Domain Prompt (Egyptian Arabic & English technical meeting context)
"""
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.cuda_init import register_nvidia_dll_directories
register_nvidia_dll_directories()

from faster_whisper import WhisperModel
from app.core.config import MODELS_DIR, STORAGE_DIR
from app.evaluation.metrics import calculate_wer_cer

BENCHMARKS_DIR = STORAGE_DIR / "benchmarks"

SAMPLES = [
    {
        "id": "dev_0_103",
        "name": "Dev Sample (00:00 - 01:43.5)",
        "audio": BENCHMARKS_DIR / "ref_103s.wav",
        "ref": (BENCHMARKS_DIR / "human_reference_raw.txt").read_text(encoding="utf-8").strip(),
    },
    {
        "id": "test_180_225",
        "name": "Test Sample (03:00 - 03:45)",
        "audio": BENCHMARKS_DIR / "test_slice_180_225.wav",
        "ref": (BENCHMARKS_DIR / "human_reference_test_180_225.txt").read_text(encoding="utf-8").strip(),
    },
    {
        "id": "holdout_300_345",
        "name": "Holdout Sample (05:00 - 05:45)",
        "audio": BENCHMARKS_DIR / "holdout_300_345.wav",
        "ref": (BENCHMARKS_DIR / "human_reference_holdout_300_345.txt").read_text(encoding="utf-8").strip(),
    },
]

NEUTRAL_PROMPT = "تسجيل صوتي بالعامية المصرية مع مصطلحات تقنية باللغة الإنجليزية في سياق عمل واجتماعات ومقترحات مشاريع."

def run():
    model_dir = MODELS_DIR / "codeswitched-medium"
    print(f"Loading Specialized Whisper Medium from: {model_dir}")
    model = WhisperModel(str(model_dir), device="cuda", compute_type="int8_float16")

    comparison = []

    for s in SAMPLES:
        sid = s["id"]
        sname = s["name"]
        audio_path = s["audio"]
        ref_text = s["ref"]

        print(f"\n========================================================")
        print(f"Evaluating: {sname} ({sid})")
        print(f"========================================================")

        # 1. Unprompted Baseline
        segs_base, _ = model.transcribe(
            str(audio_path),
            language="ar",
            initial_prompt=None,
            beam_size=5,
            condition_on_previous_text=True,
            vad_filter=False,
            no_speech_threshold=0.8,
        )
        base_text = " ".join([seg.text.strip() for seg in segs_base if seg.text.strip()])
        base_metrics = calculate_wer_cer(ref_text, base_text)

        # 2. Neutral Domain Prompt
        segs_prompt, _ = model.transcribe(
            str(audio_path),
            language="ar",
            initial_prompt=NEUTRAL_PROMPT,
            beam_size=5,
            condition_on_previous_text=True,
            vad_filter=False,
            no_speech_threshold=0.8,
        )
        prompt_text = " ".join([seg.text.strip() for seg in segs_prompt if seg.text.strip()])
        prompt_metrics = calculate_wer_cer(ref_text, prompt_text)

        delta_wer = prompt_metrics["wer_percent"] - base_metrics["wer_percent"]
        delta_cer = prompt_metrics["cer_percent"] - base_metrics["cer_percent"]

        item = {
            "sample_id": sid,
            "sample_name": sname,
            "base_wer": base_metrics["wer_percent"],
            "base_cer": base_metrics["cer_percent"],
            "base_sub": base_metrics["substitutions"],
            "base_del": base_metrics["deletions"],
            "base_ins": base_metrics["insertions"],
            "prompt_wer": prompt_metrics["wer_percent"],
            "prompt_cer": prompt_metrics["cer_percent"],
            "prompt_sub": prompt_metrics["substitutions"],
            "prompt_del": prompt_metrics["deletions"],
            "prompt_ins": prompt_metrics["insertions"],
            "delta_wer": round(delta_wer, 2),
            "delta_cer": round(delta_cer, 2),
        }
        comparison.append(item)

        print(f"Baseline:       WER = {base_metrics['wer_percent']:.2f}% | CER = {base_metrics['cer_percent']:.2f}% (S:{base_metrics['substitutions']} D:{base_metrics['deletions']} I:{base_metrics['insertions']})")
        print(f"Neutral Prompt: WER = {prompt_metrics['wer_percent']:.2f}% | CER = {prompt_metrics['cer_percent']:.2f}% (S:{prompt_metrics['substitutions']} D:{prompt_metrics['deletions']} I:{prompt_metrics['insertions']})")
        print(f"Delta:          {'Improvement' if delta_wer < 0 else 'Degradation'}: {delta_wer:+.2f}% WER | {delta_cer:+.2f}% CER")

    # Averages
    avg_base_wer = sum(x["base_wer"] for x in comparison) / len(comparison)
    avg_base_cer = sum(x["base_cer"] for x in comparison) / len(comparison)
    avg_prompt_wer = sum(x["prompt_wer"] for x in comparison) / len(comparison)
    avg_prompt_cer = sum(x["prompt_cer"] for x in comparison) / len(comparison)

    print("\n" + "=" * 80)
    print("MACRO AVERAGE COMPARISON ACROSS ALL 3 HUMAN SAMPLES:")
    print("=" * 80)
    print(f"Baseline Unprompted:    WER = {avg_base_wer:.2f}% | CER = {avg_base_cer:.2f}%")
    print(f"Neutral Domain Prompt:  WER = {avg_prompt_wer:.2f}% | CER = {avg_prompt_cer:.2f}%")
    print(f"Overall Net Delta:      {avg_prompt_wer - avg_base_wer:+.2f}% WER | {avg_prompt_cer - avg_base_cer:+.2f}% CER")
    print("=" * 80)

    # Save to json
    out_file = Path(__file__).resolve().parent / "neutral_prompt_comparison.json"
    out_file.write_text(json.dumps({
        "prompt": NEUTRAL_PROMPT,
        "samples": comparison,
        "averages": {
            "baseline": {"wer": round(avg_base_wer, 2), "cer": round(avg_base_cer, 2)},
            "neutral_prompt": {"wer": round(avg_prompt_wer, 2), "cer": round(avg_prompt_cer, 2)},
            "delta_wer": round(avg_prompt_wer - avg_base_wer, 2),
            "delta_cer": round(avg_prompt_cer - avg_base_cer, 2),
        }
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved comparison to: {out_file}")

if __name__ == "__main__":
    run()
