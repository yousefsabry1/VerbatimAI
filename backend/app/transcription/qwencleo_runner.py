import os
import sys
import time
import json
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Run QwenCleo 4-bit inference in isolated environment")
    parser.add_argument("--audio", required=True, help="Path to input audio WAV file")
    parser.add_argument("--output", required=True, help="Path to write JSON result")
    parser.add_argument("--device", default="cuda", help="Target device (cuda or cpu)")
    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    output_path = Path(args.output).resolve()

    if not audio_path.exists():
        err_res = {"status": "error", "error": f"Audio file not found: {audio_path}"}
        output_path.write_text(json.dumps(err_res, ensure_ascii=False, indent=2), encoding="utf-8")
        sys.exit(1)

    try:
        import torch
        from qwen_asr import Qwen3ASRModel
        from transformers import BitsAndBytesConfig

        backend_dir = Path(__file__).resolve().parent.parent.parent
        model_dir = backend_dir / "storage" / "models" / "qwencleo-asr"

        if not model_dir.exists():
            raise FileNotFoundError(f"QwenCleo model weights not found at {model_dir}")

        use_cuda = args.device.startswith("cuda") and torch.cuda.is_available()

        if use_cuda:
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()

        # 4-bit NF4 configuration matching verified setup
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )

        t0_load = time.time()
        model = Qwen3ASRModel.from_pretrained(
            str(model_dir),
            quantization_config=bnb_config if use_cuda else None,
            device_map="cuda:0" if use_cuda else "cpu",
        )
        load_time = time.time() - t0_load

        if use_cuda:
            torch.cuda.reset_peak_memory_stats()

        t0_infer = time.time()
        # Safe long-form transcription engine with silence-aware chunking and dynamic budgeting
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        from app.transcription.qwencleo_longform import transcribe_qwencleo_longform

        longform_res = transcribe_qwencleo_longform(
            model=model,
            audio_path=str(audio_path),
            language="Arabic",
            device="cuda" if use_cuda else "cpu",
        )
        infer_time = time.time() - t0_infer

        hyp_text = longform_res.get("text", "").strip()
        peak_vram_mb = longform_res.get("peak_vram_mb", 0.0)

        result = {
            "status": "success",
            "text": hyp_text,
            "load_time_seconds": round(load_time, 2),
            "elapsed_seconds": round(infer_time, 2),
            "peak_vram_mb": round(peak_vram_mb, 1),
            "device": "cuda" if use_cuda else "cpu",
            "compute": "4-bit NF4",
            "mode": longform_res.get("mode", "silence_aware_chunking"),
            "chunks_count": longform_res.get("chunks_count", 1),
        }
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    except Exception as e:
        err_res = {"status": "error", "error": str(e)}
        output_path.write_text(json.dumps(err_res, ensure_ascii=False, indent=2), encoding="utf-8")
        sys.exit(1)

if __name__ == "__main__":
    main()
