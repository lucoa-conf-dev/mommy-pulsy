"""Operating-system and distribution detection for the installer."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


class SystemDetector:
    def __init__(self):
        self.os_type = self._detect_os_type()
        self.distribution, self.id_like = self._detect_distribution()
        self.is_arch_based = self._is_arch_based()

    def _detect_os_type(self) -> str:
        if sys.platform == "win32":
            return "windows"
        if sys.platform == "darwin":
            return "darwin"
        if sys.platform.startswith("linux"):
            return "linux"
        return "unknown"

    def _detect_distribution(self) -> Tuple[str, str]:
        if self.os_type != "linux":
            return self.os_type, ""
        values = {}
        path = Path("/etc/os-release")
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    values[key] = value.strip().strip('"')
            except OSError:
                pass
        return values.get("ID", "unknown").lower(), values.get("ID_LIKE", "").lower()

    def _is_arch_based(self) -> bool:
        if self.os_type != "linux":
            return False
        # Distribution metadata is authoritative. Do not infer Arch from pacman alone:
        # pacman can be installed on unrelated distributions.
        if self.distribution == "arch":
            return True
        if "arch" in self.id_like.split():
            return True
        return Path("/etc/arch-release").exists()

    def get_package_manager(self) -> Optional[str]:
        if self.is_arch_based and shutil.which("pacman"):
            return "pacman"
        mapping = {
            "debian": "apt", "ubuntu": "apt", "linuxmint": "apt",
            "fedora": "dnf", "rhel": "dnf", "centos": "dnf", "rocky": "dnf", "almalinux": "dnf",
            "opensuse": "zypper", "sles": "zypper",
            "darwin": "brew",
        }
        return mapping.get(self.distribution)

    def check_command(self, command: str) -> bool:
        return shutil.which(command) is not None

    def get_python_version(self) -> Tuple[int, int, int]:
        try:
            result = subprocess.run(["python3", "--version"], capture_output=True, text=True, timeout=5, check=False)
            text = (result.stdout or result.stderr).strip()
            version = text.split()[-1]
            major, minor, *rest = version.split(".")
            patch = int(rest[0].split("+")[0]) if rest else 0
            return int(major), int(minor), patch
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return 0, 0, 0

    def check_python_module(self, module: str) -> bool:
        try:
            result = subprocess.run(["python3", "-c", f"import {module}"], capture_output=True, timeout=5, check=False)
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def get_system_info(self) -> dict:
        return {
            "os_type": self.os_type,
            "distribution": self.distribution,
            "id_like": self.id_like,
            "is_arch_based": self.is_arch_based,
            "package_manager": self.get_package_manager(),
            "python_version": self.get_python_version(),
        }
