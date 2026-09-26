"""Safe polling watcher for mommy-pulsy configuration files."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional, Tuple


class ConfigWatcher:
    """Watch one config file and call a callback once its on-disk signature changes."""

    def __init__(self, config_path: Path, on_change: Callable[[], None], poll_interval: float = 0.25):
        self.config_path = Path(config_path)
        self.on_change = on_change
        self.poll_interval = max(0.05, float(poll_interval))
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_signature: Optional[Tuple[int, int, int]] = self._signature()

    def _signature(self) -> Optional[Tuple[int, int, int]]:
        try:
            stat = self.config_path.stat()
        except OSError:
            return None
        return (int(stat.st_mtime_ns), int(stat.st_size), int(getattr(stat, "st_ino", 0)))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._last_signature = self._signature()
        self._thread = threading.Thread(target=self._run, name="mommy-pulsy-config", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.wait(self.poll_interval):
            signature = self._signature()
            if signature == self._last_signature:
                continue
            self._last_signature = signature
            try:
                self.on_change()
            except Exception:
                # The application owns error reporting. The watcher must never die
                # because one configuration reload failed.
                continue

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            # The callback is local and synchronous; wait for it to finish so
            # mommy-pulsy never leaves a watcher thread behind on shutdown.
            thread.join()
        self._thread = None
