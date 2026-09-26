"""Public audio-capture wrapper; captures system playback, never the microphone."""

from __future__ import annotations

from typing import Optional

import numpy as np

try:
    from .system_audio_capture import SystemAudioCapture
except ImportError:
    from system_audio_capture import SystemAudioCapture


class AudioCapture:
    def __init__(self, sample_rate: int = 48000, chunk_size: int = 1024, channels: int = 2,
                 device_index: Optional[int] = None, queue_size: int = 8, backend: str = "auto"):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.device_index = device_index
        self.backend = backend
        self.system_capture = SystemAudioCapture(sample_rate, 2, chunk_size, queue_size, backend)
        self._is_running = False

    def start(self) -> bool:
        started = self.system_capture.start()
        self._is_running = started
        return started

    def read_chunk(self, timeout: float = 0.05) -> Optional[np.ndarray]:
        """Read one system-playback chunk, waiting up to ``timeout`` seconds."""
        if not self._is_running:
            return None
        return self.system_capture.read_chunk(timeout=timeout)

    def stop(self) -> None:
        self.system_capture.stop()
        self._is_running = False

    def get_audio_level(self) -> float:
        return self.system_capture.get_audio_level()

    def is_receiving_audio(self) -> bool:
        return self.system_capture.is_receiving_audio()

    def get_capture_info(self) -> dict:
        return self.system_capture.get_capture_info()

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass
