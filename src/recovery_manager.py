"""Automatic configuration recovery for mommy-pulsy."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

try:
    from .config_loader import ConfigLoadError, ConfigLoader, _LuaDataParser
    from .mommy_logger import get_logger
    from .snapshot_manager import SnapshotManager
except ImportError:
    from config_loader import ConfigLoadError, ConfigLoader, _LuaDataParser
    from mommy_logger import get_logger
    from snapshot_manager import SnapshotManager


class RecoveryManager:
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = Path(config_dir) if config_dir else Path.home() / ".config" / "mommy-pulsy"
        self.config_loader = ConfigLoader(self.config_dir / "mommie.lua")
        self.snapshot_manager = SnapshotManager(self.config_dir)
        self.logger = get_logger()

    def load_with_recovery(self) -> Tuple[dict, bool]:
        config_path = self.config_dir / "mommie.lua"
        config, is_valid, error = self.config_loader.load_detailed()
        if is_valid:
            # A valid configuration with recovery disabled is still a valid configuration.
            # Recovery is only relevant when the file is missing/broken.
            return config, False

        raw_config = {}
        if config_path.exists():
            self.logger.concern("There's a little problem with mommie.lua.")
            self.logger.error("The configuration file is invalid, honey.")
            if error:
                self.logger.error(f"Diagnostic: {error}")
            try:
                raw_config = _LuaDataParser(config_path.read_text(encoding="utf-8")).parse()
            except Exception:
                raw_config = {}
        else:
            self.logger.concern("I can't find mommie.lua...")

        if not self._check_recovery_enabled(raw_config) or not self._check_auto_restore(raw_config):
            raise ConfigLoadError("Automatic configuration recovery is disabled")
        return self._attempt_recovery(), True

    @staticmethod
    def _check_recovery_enabled(config: dict) -> bool:
        return bool(config.get("recovery", {}).get("enabled", True)) if isinstance(config.get("recovery", {}), dict) else True

    @staticmethod
    def _check_auto_restore(config: dict) -> bool:
        return bool(config.get("recovery", {}).get("auto_restore", True)) if isinstance(config.get("recovery", {}), dict) else True

    def _attempt_recovery(self) -> dict:
        self.logger.reassurance("Don't worry, sweetheart.")
        self.logger.reassurance("Mommy kept a copy. ♡")
        latest = self.snapshot_manager.get_latest_valid_snapshot()
        if latest is None:
            self.logger.concern("I couldn't find any valid snapshots, darling.")
            raise ConfigLoadError("No valid snapshots available for recovery")
        self.logger.success(f"Found a healthy snapshot: {latest.name}")
        if not self.snapshot_manager.restore_snapshot(latest):
            raise ConfigLoadError("Snapshot restoration failed")
        config, valid = self.config_loader.load()
        if not valid:
            raise ConfigLoadError("Restored snapshot is invalid")
        self.logger.success("There we go. All better.")
        return config

    def create_snapshot_before_change(self) -> bool:
        return self.snapshot_manager.create_snapshot(self.config_dir / "mommie.lua") is not None

    def save_with_snapshot(self, config: dict) -> None:
        self.create_snapshot_before_change()
        self.config_loader.save_atomic(config)
        self.snapshot_manager.cleanup_old_snapshots()
