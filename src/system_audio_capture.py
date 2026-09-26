"""Low-latency capture of real system playback audio."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from typing import Optional, Dict, Any

import numpy as np

try:
    from .audio_backend import AudioBackend
    from .mommy_logger import get_logger
except ImportError:
    from audio_backend import AudioBackend
    from mommy_logger import get_logger


class SystemAudioCapture:
    """Capture the output monitor of the current default sink."""

    def __init__(self, sample_rate: int = 48000, channels: int = 2, chunk_size: int = 1024, queue_size: int = 8, backend: str = "auto"):
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.chunk_size = int(chunk_size)
        self.logger = get_logger()
        self.backend = AudioBackend(preferred=backend)
        self.monitor_info = self.backend.find_system_monitor()
        self.recording_process: Optional[subprocess.Popen[bytes]] = None
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=queue_size)
        self._is_running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._error_thread: Optional[threading.Thread] = None
        self.last_audio_level = 0.0
        self.samples_received = 0
        self.last_audio_timestamp = 0.0
        self.last_error = ""
        self._backend_command = ""

    def start(self) -> bool:
        if self._is_running:
            return True
        if not self.monitor_info:
            self.logger.concern("I couldn't find a system output monitor, darling.")
            self.logger.error("Please make sure PipeWire/PulseAudio is running and an output device exists.")
            return False
        try:
            if self.backend.backend_type not in {"pipewire", "pulseaudio"}:
                self.logger.concern(f"Audio backend '{self.backend.backend_type}' cannot provide system monitoring yet, honey.")
                return False
            for starter in (self._start_parec, self._start_pw_cat):
                if starter(self.monitor_info["name"]):
                    self._is_running = True
                    self._capture_thread = threading.Thread(target=self._capture_loop, name="mommy-pulsy-audio", daemon=True)
                    self._capture_thread.start()
                    self.logger.success("Found the playback monitor.")
                    self.logger.info("Listening to the system output...")
                    return True
            self.logger.concern("I couldn't open the system playback stream, darling.")
            if self.last_error:
                self.logger.error(self.last_error)
            return False
        except Exception as exc:
            self._cleanup_process()
            self.logger.concern("I had trouble starting audio capture, darling.")
            self.logger.error(f"Error: {exc}")
            return False

    def _start_parec(self, monitor_name: str) -> bool:
        if not self._command_exists("parec"):
            return False
        cmd = [
            "parec", "--device", monitor_name,
            "--rate", str(self.sample_rate),
            "--channels", str(self.channels),
            "--format", "float32le",
            "--latency-msec", "20",
        ]
        return self._spawn_capture(cmd, "parec")

    def _start_pw_cat(self, monitor_name: str) -> bool:
        if not self._command_exists("pw-cat"):
            return False
        cmd = [
            "pw-cat", "--record",
            "--target", monitor_name,
            "--raw",
            "--rate", str(self.sample_rate),
            "--channels", str(self.channels),
            "--format", "f32",
            "--latency", "20ms",
            "-",
        ]
        return self._spawn_capture(cmd, "pw-cat")

    def _spawn_capture(self, cmd: list[str], backend_name: str) -> bool:
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.last_error = f"{backend_name}: {exc}"
            return False
        self.recording_process = process
        self._backend_command = backend_name
        self._error_thread = threading.Thread(target=self._drain_stderr, args=(process,), name="mommy-pulsy-audio-stderr", daemon=True)
        self._error_thread.start()
        time.sleep(0.15)
        if process.poll() is not None:
            self._cleanup_process()
            return False
        return True

    @staticmethod
    def _command_exists(command: str) -> bool:
        from shutil import which
        return which(command) is not None

    def _drain_stderr(self, process: subprocess.Popen[bytes]) -> None:
        if process.stderr is None:
            return
        try:
            for raw in iter(process.stderr.readline, b""):
                if raw:
                    self.last_error = raw.decode("utf-8", errors="replace").strip()
                if process.poll() is not None:
                    break
        except (OSError, ValueError):
            pass

    def _capture_loop(self) -> None:
        # Keep a local process reference. ``stop()``/error cleanup may clear
        # ``self.recording_process`` concurrently; dereferencing the attribute
        # inside this thread can otherwise race with cleanup and become None.
        process = self.recording_process
        if process is None or process.stdout is None:
            return
        frame_bytes = self.channels * 4
        chunk_bytes = self.chunk_size * frame_bytes
        buffer = bytearray()
        stdout = process.stdout
        try:
            while self._is_running:
                data = stdout.read(chunk_bytes)
                if not data:
                    if process.poll() is not None:
                        break
                    time.sleep(0.002)
                    continue
                buffer.extend(data)
                complete = (len(buffer) // frame_bytes) * frame_bytes
                if complete == 0:
                    continue
                raw = bytes(buffer[:complete])
                del buffer[:complete]
                samples = np.frombuffer(raw, dtype="<f4")
                if self.channels > 1:
                    usable = (len(samples) // self.channels) * self.channels
                    if usable == 0:
                        continue
                    samples = samples[:usable].reshape(-1, self.channels).mean(axis=1, dtype=np.float32)
                samples = np.asarray(samples, dtype=np.float32)
                if samples.size == 0:
                    continue
                level = float(np.sqrt(np.mean(np.square(samples, dtype=np.float32))))
                if not np.isfinite(level):
                    level = 0.0
                self.last_audio_level = level
                self.samples_received += int(samples.size)
                self.last_audio_timestamp = time.monotonic()
                self._push_chunk(samples)
        except (OSError, ValueError) as exc:
            if self._is_running:
                self.last_error = str(exc)
        finally:
            if self._is_running and process.poll() is not None:
                self._is_running = False

    def _push_chunk(self, samples: np.ndarray) -> None:
        while True:
            try:
                self.audio_queue.put_nowait(samples)
                return
            except queue.Full:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    return

    def read_chunk(self, timeout: float = 0.05) -> Optional[np.ndarray]:
        if not self._is_running:
            return None
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        self._is_running = False
        self._cleanup_process()
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        if self._error_thread and self._error_thread.is_alive():
            self._error_thread.join(timeout=0.25)
        self._capture_thread = None
        self._error_thread = None
        self._clear_queue()

    def _cleanup_process(self) -> None:
        process = self.recording_process
        self.recording_process = None
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.75)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=0.75)
        except (OSError, subprocess.SubprocessError):
            pass

    def _clear_queue(self) -> None:
        while True:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def get_audio_level(self) -> float:
        return float(self.last_audio_level)

    def is_receiving_audio(self, stale_after: float = 0.5) -> bool:
        return self.samples_received > 0 and (time.monotonic() - self.last_audio_timestamp) <= stale_after and self.last_audio_level > 0.0005

    def get_capture_info(self) -> Dict[str, Any]:
        return {
            "backend": self.backend.backend_type,
            "capture_method": self._backend_command or None,
            "monitor_name": self.monitor_info.get("name") if self.monitor_info else None,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "chunk_size": self.chunk_size,
            "is_running": self._is_running,
            "samples_received": self.samples_received,
            "current_level": self.last_audio_level,
            "is_receiving": self.is_receiving_audio(),
            "error": self.last_error or None,
        }

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass
