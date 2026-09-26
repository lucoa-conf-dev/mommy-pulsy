import struct
import subprocess
from types import SimpleNamespace

import numpy as np

from src.audio_backend import AudioBackend
from src.system_audio_capture import SystemAudioCapture


def test_pulse_monitor_prefers_default_sink(monkeypatch):
    backend = AudioBackend.__new__(AudioBackend)
    backend.logger = SimpleNamespace()
    backend.backend_type = "pipewire"
    backend.sample_rate = 48000
    backend.channels = 2

    monkeypatch.setattr(backend, "_which", lambda cmd: "/bin/true")

    def fake_run(argv, timeout=3.0):
        if argv == ["pactl", "get-default-sink"]:
            return subprocess.CompletedProcess(argv, 0, "alsa_output.pci-0000_00_1f.3.analog-stereo\n", "")
        if argv[:4] == ["pactl", "list", "short", "sources"]:
            output = "12\talsa_input.pci-0000_00_1f.3.analog-stereo\tPipeWire\n"
            output += "13\talsa_output.pci-0000_00_1f.3.analog-stereo.monitor\tPipeWire\n"
            return subprocess.CompletedProcess(argv, 0, output, "")
        raise AssertionError(argv)

    monkeypatch.setattr(backend, "_run", fake_run)
    monitor = backend._find_pulse_compat_monitor()
    assert monitor["name"].endswith(".monitor")
    assert monitor["source_name"] == "alsa_output.pci-0000_00_1f.3.analog-stereo"


def test_system_capture_reads_float32_and_mixes_stereo(monkeypatch):
    capture = SystemAudioCapture.__new__(SystemAudioCapture)
    capture.sample_rate = 48000
    capture.channels = 2
    capture.chunk_size = 2
    capture.audio_queue = __import__("queue").Queue(maxsize=2)
    capture._is_running = True
    capture.recording_process = SimpleNamespace()
    payload = struct.pack("<ffff", 0.5, -0.5, 1.0, 1.0)

    class FakeStdout:
        def __init__(self):
            self.calls = 0
        def read(self, n):
            self.calls += 1
            return payload if self.calls == 1 else b""

    capture.recording_process.stdout = FakeStdout()
    capture.recording_process.poll = lambda: 0
    capture.last_audio_level = 0.0
    capture.samples_received = 0
    capture.last_audio_timestamp = 0.0
    capture.last_error = ""
    capture.logger = SimpleNamespace()

    capture._capture_loop()
    samples = capture.audio_queue.get_nowait()
    np.testing.assert_allclose(samples, np.array([0.0, 1.0], dtype=np.float32))
    assert capture.samples_received == 2
    assert capture.last_audio_level > 0.7


def test_capture_queue_is_bounded():
    capture = SystemAudioCapture.__new__(SystemAudioCapture)
    capture.audio_queue = __import__("queue").Queue(maxsize=2)
    a = np.array([1.0], dtype=np.float32)
    b = np.array([2.0], dtype=np.float32)
    c = np.array([3.0], dtype=np.float32)
    capture._push_chunk(a)
    capture._push_chunk(b)
    capture._push_chunk(c)
    assert capture.audio_queue.qsize() == 2
    assert capture.audio_queue.get_nowait()[0] == 2.0
    assert capture.audio_queue.get_nowait()[0] == 3.0


def test_audio_capture_forwards_timeout(monkeypatch):
    from src.audio_capture import AudioCapture

    capture = AudioCapture.__new__(AudioCapture)
    capture._is_running = True
    expected = np.array([0.1, 0.2], dtype=np.float32)

    class FakeSystemCapture:
        def __init__(self):
            self.timeout = None
        def read_chunk(self, timeout=0.05):
            self.timeout = timeout
            return expected

    capture.system_capture = FakeSystemCapture()
    result = capture.read_chunk(timeout=0.02)
    assert result is expected
    assert capture.system_capture.timeout == 0.02


def test_capture_loop_survives_process_reference_cleanup_race():
    import queue

    capture = SystemAudioCapture.__new__(SystemAudioCapture)
    capture.sample_rate = 48000
    capture.channels = 2
    capture.chunk_size = 2
    capture.audio_queue = queue.Queue(maxsize=2)
    capture._is_running = True
    capture.last_audio_level = 0.0
    capture.samples_received = 0
    capture.last_audio_timestamp = 0.0
    capture.last_error = ""

    payload = struct.pack("<ffff", 0.25, 0.25, 0.5, 0.5)

    class FakeStdout:
        def __init__(self):
            self.calls = 0
        def read(self, n):
            self.calls += 1
            if self.calls == 1:
                return payload
            capture._is_running = False
            return b""

    process = SimpleNamespace()
    process.stdout = FakeStdout()
    process.poll = lambda: None
    capture.recording_process = process

    capture._capture_loop()
    samples = capture.audio_queue.get_nowait()
    np.testing.assert_allclose(samples, np.array([0.25, 0.5], dtype=np.float32))
