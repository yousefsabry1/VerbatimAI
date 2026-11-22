"""
Verbatim QwenCleo Managed Persistent Worker
============================================
A persistent worker running in experimental_venv communicating over stdin/stdout via JSON lines.
Reuses loaded 4-bit NF4 model weights across multiple sequential requests,
reducing per-request cold-start latency from ~43s down to raw inference time (~3.8s - 15.6s).

Key Reliability & Safety Features:
- Explicit lifecycle commands: init, ping, transcribe, transcribe_batch, release_gpu, shutdown
- Auto-shutdown on stdin close / EOF (no zombie subprocesses)
- Idle timeout watchdog (auto-exits after inactivity)
- Explicit VRAM tracking & GPU memory hygiene
- Isolated in experimental_venv (zero dependency collision with Faster-Whisper)
"""

import os
import sys
import time
import json
import select
import threading
from pathlib import Path

# Unbuffered stdout for immediate JSON-line streaming
sys.stdout.reconfigure(line_buffering=True)


def log_stderr(msg: str):
    sys.stderr.write(f"[QwenCleoWorker] {msg}\n")
    sys.stderr.flush()


class QwenCleoWorker:
    def __init__(self, idle_timeout: float = 180.0):
        self.idle_timeout = idle_timeout
        self.model = None
        self.device = "cuda"
        self.is_loaded = False
        self.last_active_time = time.time()
        self.backend_dir = Path(__file__).resolve().parent.parent.parent
        self.model_dir = self.backend_dir / "storage" / "models" / "qwencleo-asr"
        self._shutdown_event = threading.Event()

    def start_watchdog(self):
        def _watchdog():
            while not self._shutdown_event.is_set():
                time.sleep(5.0)
                if self.is_loaded and (time.time() - self.last_active_time > self.idle_timeout):
                    log_stderr(f"Idle timeout reached ({self.idle_timeout}s). Shutting down worker to free resources.")
                    self.shutdown()
                    os._exit(0)
        t = threading.Thread(target=_watchdog, daemon=True)
        t.start()

    def load_model(self, device: str = "cuda"):
        if self.is_loaded and self.model is not None:
            return {"status": "already_loaded", "device": self.device}

        t0 = time.perf_counter()
        import torch
        from transformers import BitsAndBytesConfig
        from qwen_asr import Qwen3ASRModel

        if not self.model_dir.exists():
            raise FileNotFoundError(f"Model directory not found at {self.model_dir}")

        use_cuda = device.startswith("cuda") and torch.cuda.is_available()
        self.device = "cuda" if use_cuda else "cpu"

        if use_cuda:
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )

        self.model = Qwen3ASRModel.from_pretrained(
            str(self.model_dir),
            quantization_config=bnb_config if use_cuda else None,
            device_map="cuda:0" if use_cuda else "cpu",
        )
        load_time = time.perf_counter() - t0
        self.is_loaded = True
        self.last_active_time = time.time()

        peak_vram_mb = torch.cuda.max_memory_allocated() / (1024**2) if use_cuda else 0.0
        return {
            "status": "ready",
            "load_time_seconds": round(load_time, 2),
            "device": self.device,
            "compute": "4-bit NF4",
            "peak_vram_mb": round(peak_vram_mb, 1),
        }

    def transcribe(self, audio_path: str, context: str = "", language: str = "Arabic") -> dict:
        self.last_active_time = time.time()
        if not self.is_loaded or self.model is None:
            self.load_model(device=self.device)

        path_obj = Path(audio_path).resolve()
        if not path_obj.exists():
            raise FileNotFoundError(f"Audio file not found: {path_obj}")

        import torch
        if self.device == "cuda":
            torch.cuda.reset_peak_memory_stats()

        t0 = time.perf_counter()
        if str(self.backend_dir) not in sys.path:
            sys.path.insert(0, str(self.backend_dir))
        from app.transcription.qwencleo_longform import transcribe_qwencleo_longform

        longform_res = transcribe_qwencleo_longform(
            model=self.model,
            audio_path=str(path_obj),
            context=context,
            language=language or "Arabic",
            device=self.device,
        )
        elapsed = time.perf_counter() - t0
        self.last_active_time = time.time()

        hyp_text = longform_res.get("text", "").strip()
        peak_vram_mb = longform_res.get("peak_vram_mb", 0.0)

        return {
            "status": "success",
            "text": hyp_text,
            "elapsed_seconds": round(elapsed, 2),
            "peak_vram_mb": round(peak_vram_mb, 1),
            "device": self.device,
            "mode": longform_res.get("mode", "silence_aware_chunking"),
            "chunks_count": longform_res.get("chunks_count", 1),
        }

    def transcribe_batch(self, audio_paths: list, language: str = "Arabic") -> dict:
        self.last_active_time = time.time()
        if not self.is_loaded or self.model is None:
            self.load_model(device=self.device)

        valid_paths = []
        for p in audio_paths:
            resolved = Path(p).resolve()
            if not resolved.exists():
                raise FileNotFoundError(f"Audio file not found: {resolved}")
            valid_paths.append(str(resolved))

        import torch
        if self.device == "cuda":
            torch.cuda.reset_peak_memory_stats()

        t0 = time.perf_counter()
        batch_results = self.model.transcribe(
            audio=valid_paths,
            language=language or "Arabic",
        )
        elapsed = time.perf_counter() - t0
        self.last_active_time = time.time()

        peak_vram_mb = torch.cuda.max_memory_allocated() / (1024**2) if self.device == "cuda" else 0.0
        results_list = []
        for r in batch_results:
            results_list.append(r.text.strip() if hasattr(r, "text") else str(r))

        return {
            "status": "success",
            "count": len(results_list),
            "texts": results_list,
            "elapsed_seconds": round(elapsed, 2),
            "avg_per_item": round(elapsed / max(1, len(results_list)), 2),
            "peak_vram_mb": round(peak_vram_mb, 1),
        }

    def release_gpu(self):
        log_stderr("Releasing GPU memory...")
        import gc
        try:
            import torch
            del self.model
            self.model = None
            self.is_loaded = False
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return {"status": "released", "vram_free": True}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def shutdown(self):
        self._shutdown_event.set()
        self.release_gpu()
        return {"status": "shutdown"}

    def run_loop(self):
        self.start_watchdog()
        log_stderr("QwenCleo persistent worker ready for commands on stdin.")
        
        while not self._shutdown_event.is_set():
            try:
                line = sys.stdin.readline()
                if not line:
                    log_stderr("Received EOF on stdin. Exiting cleanly.")
                    break
                line = line.strip()
                if not line:
                    continue

                req = json.loads(line)
                cmd = req.get("command")
                req_id = req.get("request_id")

                if cmd == "ping":
                    res = {"status": "pong", "is_ready": self.is_loaded}
                elif cmd == "init":
                    device = req.get("device", "cuda")
                    res = self.load_model(device=device)
                elif cmd == "transcribe":
                    audio = req.get("audio_path")
                    context = req.get("context", "")
                    lang = req.get("language", "Arabic")
                    res = self.transcribe(audio, context=context, language=lang)
                elif cmd == "transcribe_batch":
                    audios = req.get("audio_paths", [])
                    lang = req.get("language", "Arabic")
                    res = self.transcribe_batch(audios, language=lang)
                elif cmd == "release_gpu":
                    res = self.release_gpu()
                elif cmd == "shutdown":
                    res = self.shutdown()
                    if req_id:
                        res["request_id"] = req_id
                    sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                    sys.stdout.flush()
                    break
                else:
                    res = {"status": "error", "error": f"Unknown command: {cmd}"}

                if req_id:
                    res["request_id"] = req_id

                sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                sys.stdout.flush()

            except Exception as e:
                err_payload = {"status": "error", "error": str(e)}
                if "req_id" in locals() and req_id:
                    err_payload["request_id"] = req_id
                sys.stdout.write(json.dumps(err_payload, ensure_ascii=False) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    worker = QwenCleoWorker()
    worker.run_loop()
