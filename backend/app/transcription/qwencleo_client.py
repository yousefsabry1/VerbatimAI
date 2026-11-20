"""
Verbatim QwenCleo Managed Persistent Worker Client
===================================================
Orchestrates communication with the isolated QwenCleoWorker subprocess.
Uses non-blocking queue-based I/O pump threads to prevent Windows pipe deadlocks,
ensures strict timeout enforcement, and guarantees sequential GPU resource handoff.
"""

import os
import sys
import time
import json
import queue
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger("verbatim.qwencleo_client")


class QwenCleoClient:
    _instance: Optional["QwenCleoClient"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.backend_dir = Path(__file__).resolve().parent.parent.parent
        self.project_root = self.backend_dir.parent
        self.exp_py = self.project_root / "experimental_venv" / "Scripts" / "python.exe"
        self.worker_py = self.backend_dir / "app" / "transcription" / "qwencleo_worker.py"
        self.req_counter = 0
        self.comm_lock = threading.Lock()
        self.is_ready = False
        self._msg_queue: queue.Queue = queue.Queue()
        self._stderr_lines: List[str] = []

    @classmethod
    def get_instance(cls) -> "QwenCleoClient":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _start_io_pump_threads(self):
        self._msg_queue = queue.Queue()
        self._stderr_lines = []

        def _stdout_reader():
            try:
                while self.proc and self.proc.stdout:
                    line = self.proc.stdout.readline()
                    if not line:
                        break
                    self._msg_queue.put(line)
            except Exception:
                pass

        def _stderr_reader():
            try:
                while self.proc and self.proc.stderr:
                    line = self.proc.stderr.readline()
                    if not line:
                        break
                    line_s = line.strip()
                    if line_s:
                        self._stderr_lines.append(line_s)
                        if len(self._stderr_lines) > 50:
                            self._stderr_lines.pop(0)
                        logger.debug("[WorkerStderr] %s", line_s)
            except Exception:
                pass

        t_out = threading.Thread(target=_stdout_reader, daemon=True)
        t_err = threading.Thread(target=_stderr_reader, daemon=True)
        t_out.start()
        t_err.start()

    def start(self, device: str = "cuda") -> bool:
        with self.comm_lock:
            if self.is_alive():
                return True

            if not self.exp_py.exists():
                raise RuntimeError(f"Experimental python environment not found at {self.exp_py}")
            if not self.worker_py.exists():
                raise RuntimeError(f"QwenCleo worker script not found at {self.worker_py}")

            logger.info("Spawning QwenCleo managed persistent worker...")
            self.proc = subprocess.Popen(
                [str(self.exp_py), str(self.worker_py)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            self._start_io_pump_threads()

            # Send init command
            req = {"command": "init", "device": device, "request_id": "init_req"}
            self._send_raw(req)
            resp = self._recv_raw(timeout=90.0)

            if resp.get("status") in ("ready", "already_loaded"):
                self.is_ready = True
                logger.info("QwenCleo persistent worker ready. Load time: %ss", resp.get("load_time_seconds", 0.0))
                return True
            else:
                logger.error("Failed to initialize QwenCleo worker: %s", resp)
                self.shutdown()
                raise RuntimeError(f"Worker init failed: {resp.get('error', 'unknown error')}")

    def _send_raw(self, req: dict):
        if not self.is_alive() or not self.proc.stdin:
            raise RuntimeError("QwenCleo worker process is not running")
        line = json.dumps(req, ensure_ascii=False) + "\n"
        self.proc.stdin.write(line)
        self.proc.stdin.flush()

    def _recv_raw(self, timeout: float = 60.0) -> dict:
        try:
            raw_line = self._msg_queue.get(timeout=timeout)
            raw_line = raw_line.strip()
            if not raw_line:
                raise RuntimeError("Empty response received from worker")
            return json.loads(raw_line)
        except queue.Empty:
            recent_err = "\n".join(self._stderr_lines[-5:])
            logger.error("QwenCleo worker timed out after %ss. Recent stderr: %s", timeout, recent_err)
            self.shutdown()
            raise TimeoutError(f"Worker response timed out after {timeout} seconds: {recent_err}")
        except json.JSONDecodeError as err:
            logger.error("JSON decode error from worker: %s", err)
            raise RuntimeError(f"Invalid JSON from worker: {err}")

    def ping(self) -> bool:
        with self.comm_lock:
            if not self.is_alive():
                return False
            try:
                self._send_raw({"command": "ping", "request_id": "ping_req"})
                resp = self._recv_raw(timeout=5.0)
                return resp.get("status") == "pong"
            except Exception as e:
                logger.warning("Worker ping failed: %s", e)
                return False

    def transcribe(self, audio_path: str, context: str = "", language: str = "Arabic") -> dict:
        with self.comm_lock:
            if not self.is_alive():
                self.start(device="cuda")

            self.req_counter += 1
            req_id = f"tx_{self.req_counter}_{int(time.time()*1000)}"
            req = {
                "command": "transcribe",
                "request_id": req_id,
                "audio_path": str(Path(audio_path).resolve()),
                "context": context,
                "language": language or "Arabic",
            }
            self._send_raw(req)
            resp = self._recv_raw(timeout=90.0)

            if resp.get("status") != "success":
                raise RuntimeError(resp.get("error", "Unknown transcription error in worker"))
            return resp

    def transcribe_batch(self, audio_paths: List[str], language: str = "Arabic") -> dict:
        with self.comm_lock:
            if not self.is_alive():
                self.start(device="cuda")

            self.req_counter += 1
            req_id = f"batch_{self.req_counter}_{int(time.time()*1000)}"
            req = {
                "command": "transcribe_batch",
                "request_id": req_id,
                "audio_paths": [str(Path(p).resolve()) for p in audio_paths],
                "language": language or "Arabic",
            }
            self._send_raw(req)
            resp = self._recv_raw(timeout=120.0)

            if resp.get("status") != "success":
                raise RuntimeError(resp.get("error", "Unknown batch transcription error in worker"))
            return resp

    def release_gpu(self) -> bool:
        with self.comm_lock:
            if not self.is_alive():
                return True
            try:
                self._send_raw({"command": "release_gpu", "request_id": "rel_req"})
                resp = self._recv_raw(timeout=10.0)
                self.is_ready = False
                return resp.get("status") == "released"
            except Exception as e:
                logger.warning("Worker release_gpu failed: %s", e)
                self.shutdown()
                return True

    def shutdown(self):
        with self.comm_lock:
            if not self.is_alive():
                self.proc = None
                self.is_ready = False
                return

            logger.info("Shutting down QwenCleo persistent worker...")
            try:
                self._send_raw({"command": "shutdown", "request_id": "shut_req"})
                self.proc.wait(timeout=3.0)
            except Exception:
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=2.0)
                except Exception:
                    self.proc.kill()
            finally:
                self.proc = None
                self.is_ready = False


def get_qwencleo_client() -> QwenCleoClient:
    return QwenCleoClient.get_instance()
