"""
Tests for:
  * TerminalECGVisualizer's compact status line (backend/state/amplitude/fps)
  * MommyPulsy's rule that "Your little pulse is alive" is only announced
    after a real audio sample has actually been received -- never right
    after the capture process merely starts.
"""

from types import SimpleNamespace
import threading

from src.visualizer import TerminalECGVisualizer


class TestVisualizerStatusLine:
    def test_status_line_before_any_update_does_not_claim_audio(self):
        viz = TerminalECGVisualizer(width=80, height=24)
        line = viz._build_status_line()
        assert "LIVE" not in line
        assert "connecting" in line

    def test_status_line_reflects_receiving_state(self):
        viz = TerminalECGVisualizer(width=80, height=24)
        viz.update_status({
            "backend": "pipewire",
            "is_receiving": True,
            "current_level": 0.1234,
            "sample_rate": 48000,
        })
        line = viz._build_status_line()
        assert "pipewire" in line
        assert "LIVE" in line
        assert "0.123" in line
        assert "48kHz" in line

    def test_status_line_reflects_silent_state_honestly(self):
        viz = TerminalECGVisualizer(width=80, height=24)
        viz.update_status({
            "backend": "pipewire",
            "is_receiving": False,
            "current_level": 0.0,
            "sample_rate": 48000,
        })
        line = viz._build_status_line()
        assert "SILENT" in line
        assert "LIVE" not in line

    def test_add_sample_clamps_range(self):
        viz = TerminalECGVisualizer(width=80, height=24)
        viz.add_sample(5.0)
        viz.add_sample(-5.0)
        trace = viz.get_trace()
        assert trace[-2] == 1.0
        assert trace[-1] == -1.0


class TestPulseAliveAnnouncementRule:
    """mommy-pulsy must never say the pulse is 'alive' before real samples arrive."""

    def _make_app(self):
        # Build a MommyPulsy-like object without running its heavy __init__
        # (which touches real config/audio/visualizer construction).
        from src.mommy_pulsy import MommyPulsy
        app = MommyPulsy.__new__(MommyPulsy)
        app.logger = SimpleNamespace(messages=[])
        app.logger.success = lambda msg: app.logger.messages.append(("success", msg))
        app.logger.info = lambda msg: app.logger.messages.append(("info", msg))
        app.logger.concern = lambda msg: app.logger.messages.append(("concern", msg))
        app.logger.error = lambda msg: app.logger.messages.append(("error", msg))
        app._pulse_confirmed = False
        app._is_running = True
        app._runtime_lock = threading.Lock()
        app._runtime = SimpleNamespace(
            signal_processor=SimpleNamespace(process_audio=lambda x: {}),
            pulse_generator=SimpleNamespace(process_audio_features=lambda f: 0.0),
        )
        return app

    def test_no_alive_claim_when_no_audio_chunk(self, monkeypatch):
        app = self._make_app()
        app.audio_capture = SimpleNamespace(read_chunk=lambda timeout: None, get_capture_info=lambda: {})
        app.signal_processor = SimpleNamespace(process_audio=lambda x: {})
        app.pulse_generator = SimpleNamespace(process_audio_features=lambda f: 0.0)
        app._runtime = SimpleNamespace(
            signal_processor=app.signal_processor,
            pulse_generator=app.pulse_generator,
        )
        app.visualizer = SimpleNamespace(
            is_running=lambda: True if not hasattr(app, "_ticks") else False,
            add_sample=lambda v: None,
            update_status=lambda info: None,
            render=lambda: False,  # stop after one iteration
            shutdown=lambda: None,
        )
        app.stop = lambda: None
        app.run()
        assert not app._pulse_confirmed
        assert not any("alive" in msg for _, msg in app.logger.messages)

    def test_alive_claim_only_after_real_chunk(self):
        import numpy as np
        app = self._make_app()
        real_chunk = np.array([0.1, 0.2], dtype=np.float32)
        app.audio_capture = SimpleNamespace(read_chunk=lambda timeout: real_chunk, get_capture_info=lambda: {})
        app.signal_processor = SimpleNamespace(process_audio=lambda x: {"total_energy": 0.1, "spectral_centroid": 100.0})
        app.pulse_generator = SimpleNamespace(process_audio_features=lambda f: 0.5)
        app._runtime = SimpleNamespace(
            signal_processor=app.signal_processor,
            pulse_generator=app.pulse_generator,
        )
        app.visualizer = SimpleNamespace(
            is_running=lambda: False,  # only one loop iteration needed to observe the chunk
            add_sample=lambda v: None,
            update_status=lambda info: None,
            render=lambda: True,
            shutdown=lambda: None,
        )
        app.stop = lambda: None
        # Manually drive one iteration the same way run() would, since
        # is_running() is False means the while-loop body never executes;
        # instead call the inner logic directly via run() with a running
        # flag flipped after the first pass.
        calls = {"n": 0}

        def is_running_toggle():
            calls["n"] += 1
            return calls["n"] == 1

        app.visualizer.is_running = is_running_toggle
        app.run()
        assert app._pulse_confirmed
        assert any("alive" in msg for _, msg in app.logger.messages)
