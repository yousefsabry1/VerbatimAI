"""
Controlled Acoustic & Decoding Experiments on Certified Human Reference A (00:00 - 01:43.5).
Evaluates:
1. Baseline (current parameters)
2. Lead-in onset padding (+250ms silence pad at start to preserve clipped WhatsApp onsets)
3. condition_on_previous_text=False (prevents error cascade)
4. Temperature schedule [0.0, 0.2, 0.4]
5. Neutral domain prompt (technical voice note in Egyptian Arabic & English)
"""
import sys
import subprocess
import tempfile
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.cuda_init import register_nvidia_dll_directories
register_nvidia_dll_directories()

from faster_whisper import WhisperModel
from app.core.config import MODELS_DIR, STORAGE_DIR
from app.audio.metadata_extractor import find_ffmpeg
from app.evaluation.metrics import calculate_wer_cer, normalize_arabic_english

BENCHMARKS_DIR = STORAGE_DIR / "benchmarks"
REF_AUDIO = BENCHMARKS_DIR / "ref_103s.wav"
REF_TEXT_FILE = BENCHMARKS_DIR / "human_reference_raw.txt"

def load_reference():
    raw = REF_TEXT_FILE.read_text(encoding="utf-8").strip()
    return raw

def run_experiment():
    ref_raw = load_reference()
    ref_norm = normalize_arabic_english(ref_raw)
    ref_words = ref_norm.split()
    print(f"Reference words: {len(ref_words)}")

    model_dir = MODELS_DIR / "codeswitched-medium"
    print(f"Loading model from: {model_dir}")
    model = WhisperModel(str(model_dir), device="cuda", compute_type="int8_float16")

    ffmpeg = find_ffmpeg()

    experiments = [
        {
            "name": "Exp 1: Baseline (current default)",
            "audio": REF_AUDIO,
            "condition_on_previous_text": True,
            "prompt": None,
            "temperature": 0.0,
            "beam_size": 5,
        },
        {
            "name": "Exp 2: Condition on previous text = False",
            "audio": REF_AUDIO,
            "condition_on_previous_text": False,
            "prompt": None,
            "temperature": 0.0,
            "beam_size": 5,
        },
        {
            "name": "Exp 3: Lead-in Silence Pad (+250ms onset pre-roll)",
            "audio": "padded_onset",
            "condition_on_previous_text": True,
            "prompt": None,
            "temperature": 0.0,
            "beam_size": 5,
        },
        {
            "name": "Exp 4: Temperature Fallback [0.0, 0.2, 0.4]",
            "audio": REF_AUDIO,
            "condition_on_previous_text": True,
            "prompt": None,
            "temperature": [0.0, 0.2, 0.4],
            "beam_size": 5,
        },
        {
            "name": "Exp 5: Neutral Context Prompt (No benchmark leakage)",
            "audio": REF_AUDIO,
            "condition_on_previous_text": True,
            "prompt": "تسجيل صوتي بالعامية المصرية مع مصطلحات تقنية باللغة الإنجليزية في سياق عمل واجتماعات ومقترحات مشاريع.",
            "temperature": 0.0,
            "beam_size": 5,
        },
        {
            "name": "Exp 6: Combined Lead-in Pad + Neutral Prompt",
            "audio": "padded_onset",
            "condition_on_previous_text": True,
            "prompt": "تسجيل صوتي بالعامية المصرية مع مصطلحات تقنية باللغة الإنجليزية في سياق عمل واجتماعات ومقترحات مشاريع.",
            "temperature": 0.0,
            "beam_size": 5,
        },
    ]

    # Create padded onset audio
    padded_wav = BENCHMARKS_DIR / "temp_padded_onset_103s.wav"
    # Prepend 250ms of silence using anullsrc filter
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-t", "0.25", "-i", "anullsrc=r=16000:cl=mono",
        "-i", str(REF_AUDIO),
        "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
        "-map", "[out]",
        "-ar", "16000", "-ac", "1",
        str(padded_wav)
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    results = []

    try:
        for exp in experiments:
            audio_path = padded_wav if exp["audio"] == "padded_onset" else exp["audio"]
            print(f"\nRunning {exp['name']}...")
            
            segs, info = model.transcribe(
                str(audio_path),
                language="ar",
                initial_prompt=exp["prompt"],
                beam_size=exp["beam_size"],
                condition_on_previous_text=exp["condition_on_previous_text"],
                temperature=exp["temperature"],
                vad_filter=False,
                no_speech_threshold=0.8,
            )
            text_parts = [s.text.strip() for s in segs if s.text.strip()]
            hyp_raw = " ".join(text_parts)
            
            # Compute WER/CER against certified human reference
            metrics = calculate_wer_cer(ref_raw, hyp_raw)
            
            res_item = {
                "experiment": exp["name"],
                "norm_wer": metrics["wer_percent"],
                "norm_cer": metrics["cer_percent"],
                "norm_sub": metrics["substitutions"],
                "norm_del": metrics["deletions"],
                "norm_ins": metrics["insertions"],
                "first_50_chars": hyp_raw[:60],
            }
            results.append(res_item)
            print(f"  Result: Norm WER = {metrics['wer_percent']}% | Norm CER = {metrics['cer_percent']}% | Subs = {metrics['substitutions']} | Dels = {metrics['deletions']} | Ins = {metrics['insertions']}")
            print(f"  Onset output: {hyp_raw[:60]}")
    finally:
        if padded_wav.exists():
            padded_wav.unlink()

    print("\n" + "=" * 80)
    print("CONTROLLED EXPERIMENT SUMMARY TABLE:")
    print("=" * 80)
    for r in results:
        print(f"{r['experiment']:<50} | WER: {r['norm_wer']}% | CER: {r['norm_cer']}% | Subs: {r['norm_sub']} | Ins: {r['norm_ins']}")
    print("=" * 80)

if __name__ == "__main__":
    run_experiment()
