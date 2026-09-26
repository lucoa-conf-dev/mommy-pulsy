"""Configuration snapshots and safe restoration."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from .config_loader import ConfigLoadError, ConfigLoader
except ImportError:
    from config_loader import ConfigLoadError, ConfigLoader


class SnapshotManager:
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = Path(config_dir) if config_dir else Path.home() / ".config" / "mommy-pulsy"
        self.snapshots_dir = self.config_dir / "snapshots"
        self.config_loader = ConfigLoader(self.config_dir / "mommie.lua")

    def _ensure_snapshot_dir(self) -> None:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def _snapshot_filename(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f.lua")
        return now

    def create_snapshot(self, config_path: Optional[Path] = None) -> Optional[Path]:
        source = Path(config_path) if config_path else self.config_dir / "mommie.lua"
        if not source.is_file():
            return None
        self._ensure_snapshot_dir()
        destination = self.snapshots_dir / self._snapshot_filename()
        while destination.exists():
            destination = self.snapshots_dir / self._snapshot_filename()
        try:
            shutil.copy2(source, destination)
            return destination
        except OSError:
            return None

    def create_config_snapshot(self, config: dict) -> Optional[Path]:
        """Persist a validated in-memory config as a recovery snapshot."""
        try:
            validated = self.config_loader.validate_config(config)
        except Exception:
            return None

        self._ensure_snapshot_dir()
        destination = self.snapshots_dir / self._snapshot_filename()
        while destination.exists():
            destination = self.snapshots_dir / self._snapshot_filename()

        try:
            ConfigLoader(destination).save_atomic(validated)
            return destination
        except (OSError, ConfigLoadError):
            return None

    def validate_snapshot(self, snapshot_path: Path) -> bool:
        path = Path(snapshot_path)
        if not path.is_file() or path.parent.resolve() != self.snapshots_dir.resolve():
            return False
        loader = ConfigLoader(path)
        _, valid = loader.load()
        return valid

    def list_snapshots(self, include_invalid: bool = False) -> List[Tuple[Path, bool]]:
        if not self.snapshots_dir.exists():
            return []
        result: List[Tuple[Path, bool]] = []
        for path in sorted(self.snapshots_dir.glob("*.lua"), key=lambda p: p.stat().st_mtime_ns, reverse=True):
            valid = self.validate_snapshot(path)
            if include_invalid or valid:
                result.append((path, valid))
        return result

    def get_latest_valid_snapshot(self) -> Optional[Path]:
        for path, valid in self.list_snapshots(include_invalid=True):
            if valid:
                return path
        return None

    def restore_snapshot(self, snapshot_path: Path) -> bool:
        path = Path(snapshot_path)
        if not self.validate_snapshot(path):
            return False
        target = self.config_dir / "mommie.lua"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if target.exists():
            self.create_snapshot(target)
        temp_path: Optional[str] = None
        try:
            fd, temp_path = tempfile.mkstemp(prefix=".mommie.restore.", suffix=".tmp", dir=self.config_dir)
            os.close(fd)
            shutil.copyfile(path, temp_path)
            os.replace(temp_path, target)
            temp_path = None
            return True
        except OSError:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            return False

    def delete_snapshot(self, snapshot_path: Path) -> bool:
        try:
            Path(snapshot_path).unlink()
            return True
        except OSError:
            return False

    def cleanup_old_snapshots(self, keep_count: int = 10) -> int:
        keep_count = max(1, int(keep_count))
        all_snapshots = self.list_snapshots(include_invalid=True)
        deleted = 0
        # Invalid snapshots are safe to remove only after there are valid recovery points.
        for path, valid in all_snapshots:
            if not valid and self.delete_snapshot(path):
                deleted += 1
        valid_paths = [path for path, valid in self.list_snapshots(include_invalid=False)]
        for path in valid_paths[keep_count:]:
            if self.delete_snapshot(path):
                deleted += 1
        return deleted

    def get_snapshot_count(self) -> Tuple[int, int]:
        snapshots = self.list_snapshots(include_invalid=True)
        return sum(valid for _, valid in snapshots), len(snapshots)
