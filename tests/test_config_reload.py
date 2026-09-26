import threading
import time
from pathlib import Path
from types import SimpleNamespace

from src.config_loader import ConfigLoader
from src.config_watcher import ConfigWatcher
from src.mommy_pulsy import MommyPulsy


class TestConfigReload:
    def _make_app(self, config_path: Path):
        app = MommyPulsy.__new__(MommyPulsy)
        app.logger = SimpleNamespace(
            events=[],
            concern=lambda msg: app.logger.events.append(("concern", msg)),
            error=lambda msg: app.logger.events.append(("error", msg)),
            info=lambda msg: app.logger.events.append(("info", msg)),
            success=lambda msg: app.logger.events.append(("success", msg)),
            warn=lambda msg: app.logger.events.append(("warn", msg)),
            pride=lambda msg: app.logger.events.append(("pride", msg)),
        )
        app.config_path = config_path
        app.config_dir = config_path.parent
        app.config_loader = ConfigLoader(config_path)
        app.audio_capture = SimpleNamespace(sample_rate=48000)
        snapshots = []
        app.recovery_manager = SimpleNamespace(
            snapshot_manager=SimpleNamespace(
                create_config_snapshot=lambda config: snapshots.append(config.copy()) or Path("snapshot.lua"),
                cleanup_old_snapshots=lambda: 0,
            )
        )
        app._runtime_lock = threading.Lock()

        initial = app._complete_config({"sensitivity": 1.6})
        initial_runtime = app._build_runtime(initial)
        app._runtime = initial_runtime
        app.config = initial_runtime.config
        app.visualizer = SimpleNamespace(set_fps=lambda fps: setattr(app.visualizer, "fps", fps))
        app.snapshot_calls = snapshots
        return app

    def test_valid_sensitivity_reload_is_applied(self, tmp_path):
        config_path = tmp_path / "mommie.lua"
        config_path.write_text("return { sensitivity = 1.6 }\n", encoding="utf-8")
        app = self._make_app(config_path)

        config_path.write_text("return { sensitivity = 3.0, fps = 60 }\n", encoding="utf-8")
        app._reload_config()

        assert app._runtime.pulse_generator.sensitivity == 3.0
        assert app._runtime.pulse_generator.sample_rate == 60
        assert app.visualizer.fps == 60
        assert app.config["sensitivity"] == 3.0
        assert len(app.snapshot_calls) == 1
        assert app.snapshot_calls[0]["sensitivity"] == 1.6

    def test_invalid_reload_keeps_previous_valid_runtime(self, tmp_path):
        config_path = tmp_path / "mommie.lua"
        config_path.write_text("return { sensitivity = 1.6 }\n", encoding="utf-8")
        app = self._make_app(config_path)

        config_path.write_text("return { sensitivity = 3.0 }\n", encoding="utf-8")
        app._reload_config()
        snapshot_count = len(app.snapshot_calls)

        config_path.write_text('return { sensitivity = "banana" }\n', encoding="utf-8")
        app._reload_config()

        assert app._runtime.pulse_generator.sensitivity == 3.0
        assert app.config["sensitivity"] == 3.0
        assert len(app.snapshot_calls) == snapshot_count
        assert any("sensitivity" in message for level, message in app.logger.events if level == "error")
        assert any("previous valid configuration" in message for level, message in app.logger.events if level == "info")

    def test_missing_reload_keeps_previous_valid_runtime(self, tmp_path):
        config_path = tmp_path / "mommie.lua"
        config_path.write_text("return { sensitivity = 2.0 }\n", encoding="utf-8")
        app = self._make_app(config_path)

        config_path.unlink()
        app._reload_config()

        assert app._runtime.pulse_generator.sensitivity == 1.6
        assert app.config["sensitivity"] == 1.6


def test_config_watcher_detects_file_change(tmp_path):
    config_path = tmp_path / "mommie.lua"
    config_path.write_text("return { sensitivity = 1.0 }\n", encoding="utf-8")
    seen = []
    watcher = ConfigWatcher(
        config_path,
        lambda: seen.append(config_path.read_text(encoding="utf-8")),
        poll_interval=0.05,
    )

    try:
        watcher.start()
        config_path.write_text("return { sensitivity = 3.0 }\n", encoding="utf-8")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not seen:
            time.sleep(0.02)
        assert seen
        assert "3.0" in seen[-1]
    finally:
        watcher.stop()
        assert watcher._thread is None
