"""Main mommy-pulsy application."""

from __future__ import annotations

import sys
import threading
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from .audio_capture import AudioCapture
    from .config_loader import ConfigLoadError, ConfigLoader
    from .pulse_generator import PulseGenerator
    from .recovery_manager import RecoveryManager
    from .signal_processor import SignalProcessor
    from .visualizer import TerminalECGVisualizer
    from .config_watcher import ConfigWatcher
    from .mommy_logger import get_logger
except ImportError:
    from audio_capture import AudioCapture
    from config_loader import ConfigLoadError, ConfigLoader
    from pulse_generator import PulseGenerator
    from recovery_manager import RecoveryManager
    from signal_processor import SignalProcessor
    from visualizer import TerminalECGVisualizer
    from config_watcher import ConfigWatcher
    from mommy_logger import get_logger


@dataclass(frozen=True)
class RuntimeBundle:
    """A complete, fully-built processing configuration.

    The reference itself is swapped atomically under ``_runtime_lock`` so audio
    processing never observes a half-updated sensitivity/smoothing/frequency set.
    """

    config: dict
    signal_processor: SignalProcessor
    pulse_generator: PulseGenerator


class MommyPulsy:
    def __init__(self, config_path: Optional[Path] = None):
        self.logger = get_logger()
        self.config_path = (
            Path(config_path)
            if config_path
            else Path.home() / ".config" / "mommy-pulsy" / "mommie.lua"
        )
        self.config_dir = self.config_path.parent
        self._runtime_lock = threading.Lock()
        self._config_watcher: Optional[ConfigWatcher] = None

        try:
            self.recovery_manager = RecoveryManager(self.config_dir)
            self.config_loader = ConfigLoader(self.config_path)
            self.config, was_recovered = self.recovery_manager.load_with_recovery()
        except ConfigLoadError as exc:
            self.logger.error(str(exc))
            self.config = {}
            was_recovered = False

        if was_recovered:
            self.logger.pride("I fixed it for you, darling.")

        self.config = self._complete_config(self.config)
        self._runtime = self._build_runtime(self.config)

        audio_cfg = self.config["audio"]
        self.audio_capture = AudioCapture(
            sample_rate=int(audio_cfg["sample_rate"]),
            chunk_size=int(audio_cfg["chunk_size"]),
            channels=int(audio_cfg["channels"]),
            queue_size=int(audio_cfg["queue_size"]),
            backend=str(audio_cfg["backend"]),
        )
        self.visualizer = TerminalECGVisualizer(
            width=80,
            height=24,
            fps=int(self.config["fps"]),
        )
        self._is_running = False
        # We must never claim "alive" until we have actually received a real
        # sample from system playback -- a started capture process only means
        # the pipe is open, not that audio is flowing through it yet.
        self._pulse_confirmed = False

    @staticmethod
    def _default_config() -> dict:
        return {
            # The previous FFT scale produced values around 0.001-0.01 for
            # ordinary PCM. The new RMS+dB mapping makes 1.6 a responsive default
            # while retaining useful headroom for strong playback.
            "sensitivity": 1.6,
            "smoothing": 0.60,
            "decay": 0.85,
            "fps": 120,
            "audio": {
                "sample_rate": 48000,
                "channels": 2,
                "chunk_size": 1024,
                "queue_size": 8,
                "backend": "auto",
            },
            "pulse": {
                "attack": 0.02,
                "decay": 0.18,
                "height": 1.5,
                "threshold": PulseGenerator.DEFAULT_NOISE_FLOOR_RMS,
                "transient_gain": 1.8,
                "bass_weight": 0.35,
                "event_threshold": 0.45,
                "overshoot_ratio": 0.38,
            },
            "frequency": {"min": 20, "max": 20000, "curve": "logarithmic"},
            "recovery": {"enabled": True, "auto_restore": True},
        }

    @classmethod
    def _complete_config(cls, config: dict) -> dict:
        """Return an independent, fully-populated runtime config."""
        result = deepcopy(config) if isinstance(config, dict) else {}
        defaults = cls._default_config()
        for key, value in defaults.items():
            if key not in result:
                result[key] = deepcopy(value)
            elif isinstance(value, dict):
                current = result.get(key)
                if not isinstance(current, dict):
                    result[key] = deepcopy(value)
                    continue
                for nested_key, nested_value in value.items():
                    current.setdefault(nested_key, deepcopy(nested_value))
        return result

    def _build_runtime(self, config: dict) -> RuntimeBundle:
        audio_cfg = config["audio"]
        active_sample_rate = int(self.audio_capture.sample_rate) if hasattr(self, "audio_capture") else int(audio_cfg["sample_rate"])

        freq = config["frequency"]
        effective_max = min(int(freq["max"]), active_sample_rate // 2)
        effective_min = int(freq["min"])
        if effective_min >= effective_max:
            raise ValueError(
                f"frequency range {effective_min}-{effective_max} Hz is unusable at "
                f"{active_sample_rate} Hz sample rate"
            )

        signal_processor = SignalProcessor(
            sample_rate=active_sample_rate,
            fft_size=2048,
            frequency_min=effective_min,
            frequency_max=effective_max,
            curve=freq["curve"],
        )

        pulse = config["pulse"]
        pulse_generator = PulseGenerator(
            attack=float(pulse["attack"]),
            decay=float(pulse["decay"]),
            height=float(pulse["height"]),
            smoothing=float(config["smoothing"]),
            sensitivity=float(config["sensitivity"]),
            threshold=float(pulse.get("threshold", PulseGenerator.DEFAULT_NOISE_FLOOR_RMS)),
            global_decay=float(config["decay"]),
            sample_rate=int(config["fps"]),
            transient_gain=float(pulse.get("transient_gain", 1.8)),
            bass_weight=float(pulse.get("bass_weight", 0.35)),
            event_threshold=float(pulse.get("event_threshold", 0.45)),
            overshoot_ratio=float(pulse.get("overshoot_ratio", 0.38)),
        )

        # Preserve the current waveform position/history across a live config swap
        # so changing sensitivity does not blank the terminal for a frame.
        if hasattr(self, "_runtime"):
            pulse_generator.copy_runtime_state_from(self._runtime.pulse_generator)

        return RuntimeBundle(
            config=deepcopy(config),
            signal_processor=signal_processor,
            pulse_generator=pulse_generator,
        )

    def _reload_config(self) -> None:
        """Reload mommie.lua and atomically replace the processing bundle."""
        config, valid, error = self.config_loader.load_detailed()
        if not valid:
            self.logger.concern("your configuration needs a little cuddle. ♡")
            if error:
                self.logger.error(f"Invalid configuration: {error}")
            self.logger.info("Keeping the previous valid configuration.")
            return

        new_config = self._complete_config(config)

        try:
            with self._runtime_lock:
                old_runtime = self._runtime
                if new_config == old_runtime.config:
                    return

                # Build everything before swapping the live reference. A bad value
                # can therefore never leave partially-updated processing state.
                new_runtime = self._build_runtime(new_config)

                # Keep the current valid config recoverable before accepting a
                # changed file. Invalid edits never reach this point and never get
                # snapshotted.
                snapshot_manager = self.recovery_manager.snapshot_manager
                snapshot = snapshot_manager.create_config_snapshot(old_runtime.config)
                if snapshot is not None:
                    snapshot_manager.cleanup_old_snapshots()
                self._runtime = new_runtime
                self.config = new_runtime.config

            self.visualizer.set_fps(int(new_config["fps"]))

            if new_config.get("audio") != old_runtime.config.get("audio"):
                self.logger.warn(
                    "Audio capture settings are kept on the current playback stream; "
                    "they will take effect after the next start."
                )
            self.logger.success("I reread mommie.lua and applied the new settings.")
        except (TypeError, ValueError, KeyError) as exc:
            self.logger.concern("your configuration needs a little cuddle. ♡")
            self.logger.error(f"Invalid runtime configuration: {exc}")
            self.logger.info("Keeping the previous valid configuration.")

    def _start_config_watcher(self) -> None:
        if self._config_watcher is None:
            self._config_watcher = ConfigWatcher(self.config_path, self._reload_config)
        self._config_watcher.start()

    def _stop_config_watcher(self) -> None:
        if self._config_watcher is not None:
            self._config_watcher.stop()

    def start(self) -> bool:
        self.logger.greet()
        if not self.visualizer.initialize():
            self.logger.concern("I couldn't start the display, darling.")
            return False
        self.logger.info("Looking for your system audio, sweetheart. ♡")
        if not self.audio_capture.start():
            self.logger.concern("I couldn't connect to system playback, honey.")
            self.visualizer.shutdown()
            return False
        self._is_running = True
        self._pulse_confirmed = False
        self._start_config_watcher()
        self.logger.info("Waiting for real samples... play something and I'll listen. ♡")
        return True

    def run(self) -> None:
        if not self._is_running:
            return
        try:
            while self._is_running and self.visualizer.is_running():
                audio_data = self.audio_capture.read_chunk(timeout=0.02)
                with self._runtime_lock:
                    runtime = self._runtime

                if audio_data is not None and len(audio_data):
                    if not self._pulse_confirmed:
                        self._pulse_confirmed = True
                        self.logger.success("Your little pulse is alive. ♪")
                    features = runtime.signal_processor.process_audio(audio_data)
                    pulse = runtime.pulse_generator.process_audio_features(features)
                else:
                    pulse = runtime.pulse_generator.process_audio_features(
                        {"total_energy": 0.0, "spectral_centroid": 0.0}
                    )
                self.visualizer.add_sample(pulse)
                self.visualizer.update_status(self.audio_capture.get_capture_info())
                if not self.visualizer.render():
                    break
        except KeyboardInterrupt:
            self.logger.info("Interrupted by user.")
        except Exception as exc:
            self.logger.concern("Something went wrong, darling.")
            self.logger.error(f"Error: {exc}")
        finally:
            self.stop()

    def stop(self) -> None:
        was_running = self._is_running
        self._is_running = False
        try:
            self._stop_config_watcher()
            self.audio_capture.stop()
            self.visualizer.shutdown()
        finally:
            if was_running:
                self.logger.goodbye()


def main() -> int:
    app = MommyPulsy()
    if app.start():
        app.run()
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
