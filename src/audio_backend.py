"""Audio backend detection and system-playback monitor discovery."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .mommy_logger import get_logger
except ImportError:  # direct module execution/tests with src on PYTHONPATH
    from mommy_logger import get_logger


class AudioBackend:
    """Detect PipeWire/PulseAudio and locate a monitor of the default output."""

    def __init__(self, preferred: str = "auto"):
        self.logger = get_logger()
        self.preferred = preferred
        self.backend_type = self._detect_backend(preferred)
        self.sample_rate = 48000
        self.channels = 2

    @staticmethod
    def _which(command: str) -> Optional[str]:
        return shutil.which(command)

    def _run(self, argv: List[str], timeout: float = 3.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)

    def _detect_backend(self, preferred: str) -> str:
        if preferred in {"pipewire", "pulseaudio"}:
            if preferred == "pipewire" and self._check_pipewire():
                return "pipewire"
            if preferred == "pulseaudio" and self._check_pulseaudio():
                return "pulseaudio"
            return "unknown"
        if self._check_pipewire():
            return "pipewire"
        if self._check_pulseaudio():
            return "pulseaudio"
        if self._check_alsa():
            return "alsa"
        return "unknown"

    def _check_pipewire(self) -> bool:
        if self._which("pw-cli"):
            try:
                result = self._run(["pw-cli", "info", "0"])
                if result.returncode == 0:
                    return True
            except (OSError, subprocess.SubprocessError):
                pass
        if self._which("pipewire"):
            try:
                result = self._run(["pgrep", "-x", "pipewire"])
                if result.returncode == 0:
                    return True
            except (OSError, subprocess.SubprocessError):
                pass
        if self._which("pactl"):
            try:
                result = self._run(["pactl", "info"])
                if result.returncode == 0 and "pipewire" in result.stdout.lower():
                    return True
            except (OSError, subprocess.SubprocessError):
                pass
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if runtime and Path(runtime, "pipewire-0").exists():
            return True
        return False

    def _check_pulseaudio(self) -> bool:
        if not self._which("pactl"):
            return False
        try:
            return self._run(["pactl", "info"]).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _check_alsa(self) -> bool:
        if not self._which("aplay"):
            return False
        try:
            return self._run(["aplay", "-l"]).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def find_system_monitor(self) -> Optional[Dict[str, Any]]:
        """Return the source that mirrors the current system output."""
        if self.backend_type in {"pipewire", "pulseaudio"}:
            monitor = self._find_pulse_compat_monitor()
            if monitor:
                return monitor
            if self.backend_type == "pipewire":
                return self._find_pipewire_monitor()
        return None

    def _find_pulse_compat_monitor(self) -> Optional[Dict[str, Any]]:
        if not self._which("pactl"):
            return None
        try:
            default_result = self._run(["pactl", "get-default-sink"])
            if default_result.returncode != 0:
                return None
            sink_name = default_result.stdout.strip()
            if not sink_name:
                return None

            short_sources = self._run(["pactl", "list", "short", "sources"])
            if short_sources.returncode == 0:
                exact_name = f"{sink_name}.monitor"
                for line in short_sources.stdout.splitlines():
                    fields = line.split("\t")
                    source_name = fields[1] if len(fields) > 1 else ""
                    if source_name == exact_name:
                        return {
                            "backend": self.backend_type,
                            "type": "monitor",
                            "name": source_name,
                            "source_name": sink_name,
                            "description": fields[1] if len(fields) > 1 else "System output monitor",
                            "id": fields[0] if fields and fields[0].isdigit() else source_name,
                        }

            detailed = self._run(["pactl", "list", "sources"])
            if detailed.returncode == 0:
                block_name = None
                description = None
                source_index = None
                for line in detailed.stdout.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("Name:"):
                        block_name = stripped.split(":", 1)[1].strip()
                        description = None
                        source_index = None
                    elif stripped.startswith("Description:"):
                        description = stripped.split(":", 1)[1].strip()
                    elif stripped.startswith("Source #"):
                        source_index = stripped.split("#", 1)[1].strip()
                    if block_name == f"{sink_name}.monitor":
                        return {
                            "backend": self.backend_type,
                            "type": "monitor",
                            "name": block_name,
                            "source_name": sink_name,
                            "description": description or "System output monitor",
                            "id": source_index or block_name,
                        }
        except (OSError, subprocess.SubprocessError):
            return None
        return None

    def _find_pipewire_monitor(self) -> Optional[Dict[str, Any]]:
        """Try native PipeWire node inspection when Pulse compatibility is absent."""
        if not self._which("pw-dump"):
            return None
        try:
            result = self._run(["pw-dump"], timeout=5.0)
            if result.returncode != 0:
                return None
            objects = json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return None

        candidates: List[Dict[str, Any]] = []
        for obj in objects if isinstance(objects, list) else []:
            if not isinstance(obj, dict) or obj.get("type") != "PipeWire:Interface:Node":
                continue
            props = obj.get("info", {}).get("props", {})
            name = props.get("node.name")
            media_class = props.get("media.class", "")
            description = props.get("node.description", name or "")
            if not name or "Audio/Source" not in str(media_class):
                continue
            lowered = f"{name} {description}".lower()
            if "monitor" not in lowered:
                continue
            candidates.append({
                "backend": "pipewire",
                "type": "monitor",
                "name": str(name),
                "source_name": str(props.get("node.name")),
                "description": str(description),
                "id": str(obj.get("id", name)),
            })

        return candidates[0] if candidates else None

    def get_audio_info(self) -> Dict[str, Any]:
        monitor = self.find_system_monitor()
        return {
            "backend": self.backend_type,
            "monitor_found": monitor is not None,
            "monitor_name": monitor.get("name") if monitor else None,
            "source_device": monitor.get("source_name") if monitor else None,
            "description": monitor.get("description") if monitor else None,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
        }

    def print_audio_info(self) -> None:
        info = self.get_audio_info()
        self.logger.info(f"Audio backend: {info['backend']}")
        if info["monitor_found"]:
            self.logger.info(f"Output device: {info['source_device']}")
            self.logger.info(f"Monitor source: {info['monitor_name']}")
            self.logger.info(f"Description: {info['description']}")
        else:
            self.logger.concern("No system output monitor found, darling.")
        self.logger.info(f"Sample rate: {info['sample_rate']} Hz")
        self.logger.info(f"Channels: {info['channels']}")
