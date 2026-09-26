"""Terminal-only ECG visualizer."""

from __future__ import annotations

import shutil
import sys
import threading
import time
from collections import deque
from typing import List

try:
    from .mommy_logger import get_logger
except ImportError:
    from mommy_logger import get_logger


class TerminalECGVisualizer:
    def __init__(self, width: int = 80, height: int = 24, fps: int = 120, line_char: str = "●", grid_char: str = "·"):
        self.width = max(20, width)
        self.height = max(8, height)
        self.fps = max(1, int(fps))
        self.line_char = line_char
        self.grid_char = grid_char
        self.logger = get_logger()
        self._is_running = False
        self.trace = deque(maxlen=self.width - 2)
        self._last_render = time.monotonic()
        self.frame_time = 1.0 / self.fps
        self.HOME = "\033[H"
        self.CLEAR = "\033[2J"
        self.RESET = "\033[0m"
        self.GREEN = "\033[32m"
        self.RED = "\033[31m"
        self.DIM = "\033[2m"
        self.HIDE_CURSOR = "\033[?25l"
        self.SHOW_CURSOR = "\033[?25h"
        self._status: dict = {}
        self._fps_lock = threading.Lock()
        self._frame_count = 0
        self._fps_window_start = time.monotonic()
        self._measured_fps = 0.0

    def set_fps(self, fps: int) -> None:
        """Apply a new render rate safely while the visualizer is running."""
        fps = max(1, int(fps))
        with self._fps_lock:
            self.fps = fps
            self.frame_time = 1.0 / fps

    def update_status(self, capture_info: dict) -> None:
        """Feed the latest real capture info (backend, level, receiving state)."""
        self._status = dict(capture_info or {})

    def initialize(self) -> bool:
        try:
            size = shutil.get_terminal_size((self.width, self.height))
            self.width = max(20, size.columns)
            self.height = max(8, size.lines)
            self.trace = deque(self.trace, maxlen=max(10, self.width - 2))
            self._is_running = True
            if sys.stdout.isatty():
                sys.stdout.write(self.HIDE_CURSOR + self.CLEAR + self.HOME)
                sys.stdout.flush()
            else:
                self.logger.warn("I'm not attached to a TTY, darling; using text test output instead.")
            return True
        except OSError as exc:
            self.logger.error(f"Terminal error: {exc}")
            return False

    def add_sample(self, value: float) -> None:
        self.trace.append(max(-1.0, min(float(value), 1.0)))

    def render(self) -> bool:
        if not self._is_running:
            return False
        now = time.monotonic()
        with self._fps_lock:
            frame_time = self.frame_time
        delay = frame_time - (now - self._last_render)
        if delay > 0:
            time.sleep(delay)
        self._last_render = time.monotonic()
        self._frame_count += 1
        elapsed = now - self._fps_window_start
        if elapsed >= 1.0:
            self._measured_fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_window_start = now
        if sys.stdout.isatty():
            self._poll_key()
            if not self._is_running:
                return False
            sys.stdout.write(self.HOME + self._build_display())
            sys.stdout.flush()
            return True
        return True

    def _poll_key(self) -> None:
        try:
            import select
            if select.select([sys.stdin], [], [], 0)[0]:
                key = sys.stdin.read(1)
                if key in {"q", "Q", "\x1b"}:
                    self._is_running = False
        except (OSError, ValueError):
            pass

    def _build_display(self) -> str:
        height = max(4, self.height - 3)
        center = height // 2
        screen = [[" " for _ in range(self.width)] for _ in range(height)]
        for y in range(height):
            if y % 4 == 0:
                for x in range(self.width):
                    screen[y][x] = self.grid_char
        for x in range(0, self.width, 10):
            for y in range(height):
                if screen[y][x] == " ":
                    screen[y][x] = self.grid_char
        for x in range(self.width):
            screen[center][x] = "─"
        values = list(self.trace)
        if len(values) > 1:
            for i in range(1, len(values)):
                x0, x1 = i, i + 1
                y0 = center - int(values[i - 1] * (height // 2 - 1))
                y1 = center - int(values[i] * (height // 2 - 1))
                steps = max(1, abs(y1 - y0))
                for step in range(steps + 1):
                    y = round(y0 + (y1 - y0) * step / steps)
                    if 0 <= x0 < self.width and 0 <= y < height:
                        screen[y][x0] = self.line_char
                if x1 < self.width:
                    screen[y1][x1] = self.line_char
            last_x = min(len(values), self.width - 1)
            for y in range(max(0, center - 2), min(height, center + 3)):
                screen[y][last_x] = "│"
        title = " mommy-pulsy ♡  ECG / SYSTEM AUDIO "
        footer = " q / ESC  quit "
        lines = [title.center(self.width), self._build_status_line().center(self.width)]
        for row in screen:
            rendered = "".join(row)
            rendered = rendered[: self.width]
            lines.append(f"{self.DIM}{rendered}{self.RESET}")
        lines.append(footer.center(self.width))
        return "\n".join(lines)

    def _build_status_line(self) -> str:
        info = self._status
        if not info:
            return " connecting... "
        backend = info.get("backend") or "?"
        is_receiving = bool(info.get("is_receiving"))
        state = "LIVE ♪" if is_receiving else "SILENT"
        level = float(info.get("current_level") or 0.0)
        rate = info.get("sample_rate") or 0
        parts = [
            backend,
            state,
            f"amp {level:.3f}",
            f"{rate // 1000}kHz" if rate else "",
            f"{self._measured_fps:0.0f}fps",
        ]
        return " " + "  ·  ".join(p for p in parts if p) + " "

    def shutdown(self) -> None:
        self._is_running = False
        if sys.stdout.isatty():
            try:
                sys.stdout.write(self.SHOW_CURSOR + self.RESET + "\n")
                sys.stdout.flush()
            except OSError:
                pass

    def is_running(self) -> bool:
        return self._is_running

    def get_trace(self) -> List[float]:
        return list(self.trace)

    def clear_trace(self) -> None:
        self.trace.clear()
