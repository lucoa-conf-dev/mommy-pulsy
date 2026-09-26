"""
Tests for recovery manager.
"""

import pytest
import tempfile
from pathlib import Path
from src.recovery_manager import RecoveryManager
from src.config_loader import ConfigLoadError


class TestRecoveryManager:
    """Test recovery manager."""

    def test_load_valid_config_no_recovery(self):
        """Test loading valid config without recovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "mommie.lua"

            # Create valid config
            config_file.write_text('return { fps = 120 }')

            manager = RecoveryManager(config_dir)
            config, was_recovered = manager.load_with_recovery()

            assert not was_recovered
            assert config['fps'] == 120

    def test_load_invalid_config_with_recovery(self):
        """Test loading invalid config with recovery enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "mommie.lua"
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create invalid config
            config_file.write_text('return { fps = "invalid" }')

            # Create a valid snapshot
            snapshot_path = snapshots_dir / "2026-09-25_21-30-12.lua"
            snapshot_path.write_text('return { fps = 60 }')

            manager = RecoveryManager(config_dir)
            config, was_recovered = manager.load_with_recovery()

            assert was_recovered
            assert config['fps'] == 60

    def test_load_missing_config_with_recovery(self):
        """Test loading missing config with recovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # No config file, but have snapshot
            snapshot_path = snapshots_dir / "2026-09-25_21-30-12.lua"
            snapshot_path.write_text('return { fps = 60 }')

            manager = RecoveryManager(config_dir)
            config, was_recovered = manager.load_with_recovery()

            assert was_recovered
            assert config['fps'] == 60

    def test_load_no_config_no_snapshot(self):
        """Test loading when no config or snapshot exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            manager = RecoveryManager(config_dir)

            with pytest.raises(ConfigLoadError):
                manager.load_with_recovery()

    def test_load_invalid_config_recovery_disabled(self):
        """Test that recovery is disabled when config specifies it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "mommie.lua"
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create config with recovery disabled
            config_file.write_text('return { recovery = { enabled = false } }')

            # Create a valid snapshot (should not be used)
            snapshot_path = snapshots_dir / "2026-09-25_21-30-12.lua"
            snapshot_path.write_text('return { fps = 60 }')

            manager = RecoveryManager(config_dir)

            config, recovered = manager.load_with_recovery()
            assert config["recovery"]["enabled"] is False
            assert recovered is False

    def test_create_snapshot_before_change(self):
        """Test creating snapshot before config change."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "mommie.lua"

            # Create config
            config_file.write_text('return { fps = 120 }')

            manager = RecoveryManager(config_dir)
            created = manager.create_snapshot_before_change()

            assert created

            # Verify snapshot exists
            snapshots_dir = config_dir / "snapshots"
            assert snapshots_dir.exists()
            assert len(list(snapshots_dir.glob("*.lua"))) > 0

    def test_create_snapshot_before_change_no_config(self):
        """Test snapshot creation when config doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            manager = RecoveryManager(config_dir)
            created = manager.create_snapshot_before_change()

            assert not created

    def test_save_with_snapshot(self):
        """Test saving config with automatic snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "mommie.lua"

            # Create initial config
            config_file.write_text('return { fps = 120 }')

            manager = RecoveryManager(config_dir)

            # Save new config
            new_config = {'fps': 60}
            manager.save_with_snapshot(new_config)

            # Verify new config is saved
            loader = manager.config_loader
            config, is_valid = loader.load()

            assert is_valid
            assert config['fps'] == 60

            # Verify snapshot was created
            snapshots_dir = config_dir / "snapshots"
            assert snapshots_dir.exists()
            assert len(list(snapshots_dir.glob("*.lua"))) > 0

    def test_save_with_snapshot_creates_directory(self):
        """Test that save creates config directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            manager = RecoveryManager(config_dir)

            # Save config
            config = {'fps': 120}
            manager.save_with_snapshot(config)

            # Verify directory was created
            assert config_dir.exists()
            assert (config_dir / "mommie.lua").exists()

    def test_check_recovery_enabled_default(self):
        """Test that recovery is enabled by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            manager = RecoveryManager(config_dir)

            # Empty config should default to enabled
            enabled = manager._check_recovery_enabled({})
            assert enabled

    def test_check_recovery_enabled_explicit(self):
        """Test explicit recovery enabled setting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            manager = RecoveryManager(config_dir)

            enabled = manager._check_recovery_enabled({'recovery': {'enabled': True}})
            assert enabled

            disabled = manager._check_recovery_enabled({'recovery': {'enabled': False}})
            assert not disabled

    def test_check_auto_restore_default(self):
        """Test that auto-restore is enabled by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            manager = RecoveryManager(config_dir)

            # Empty config should default to enabled
            enabled = manager._check_auto_restore({})
            assert enabled

    def test_check_auto_restore_explicit(self):
        """Test explicit auto-restore setting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            manager = RecoveryManager(config_dir)

            enabled = manager._check_auto_restore({'recovery': {'auto_restore': True}})
            assert enabled

            disabled = manager._check_auto_restore({'recovery': {'auto_restore': False}})
            assert not disabled
