"""
Tests for snapshot management.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from src.snapshot_manager import SnapshotManager
from src.config_loader import ConfigLoader


class TestSnapshotManager:
    """Test snapshot manager."""

    def test_create_snapshot(self):
        """Test creating a snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "mommie.lua"

            # Create a valid config file
            config_file.write_text('return { fps = 120 }')

            manager = SnapshotManager(config_dir)
            snapshot_path = manager.create_snapshot()

            assert snapshot_path is not None
            assert snapshot_path.exists()
            assert snapshot_path.parent == config_dir / "snapshots"

    def test_create_snapshot_no_config(self):
        """Test creating snapshot when config doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            manager = SnapshotManager(config_dir)
            snapshot_path = manager.create_snapshot()

            assert snapshot_path is None

    def test_validate_valid_snapshot(self):
        """Test validating a valid snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create a valid snapshot
            snapshot_path = snapshots_dir / "2026-09-25_21-30-12.lua"
            snapshot_path.write_text('return { fps = 120 }')

            manager = SnapshotManager(config_dir)
            is_valid = manager.validate_snapshot(snapshot_path)

            assert is_valid

    def test_validate_invalid_snapshot(self):
        """Test validating an invalid snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create an invalid snapshot
            snapshot_path = snapshots_dir / "2026-09-25_21-30-12.lua"
            snapshot_path.write_text('return { fps = "invalid" }')

            manager = SnapshotManager(config_dir)
            is_valid = manager.validate_snapshot(snapshot_path)

            assert not is_valid

    def test_validate_nonexistent_snapshot(self):
        """Test validating a nonexistent snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshot_path = snapshots_dir / "nonexistent.lua"

            manager = SnapshotManager(config_dir)
            is_valid = manager.validate_snapshot(snapshot_path)

            assert not is_valid

    def test_list_snapshots(self):
        """Test listing snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create multiple snapshots
            (snapshots_dir / "2026-09-25_21-30-12.lua").write_text('return { fps = 120 }')
            (snapshots_dir / "2026-09-25_21-35-47.lua").write_text('return { fps = 60 }')
            (snapshots_dir / "2026-09-25_21-40-00.lua").write_text('return { fps = "invalid" }')

            manager = SnapshotManager(config_dir)
            snapshots = manager.list_snapshots(include_invalid=False)

            # Should return 2 valid snapshots
            assert len(snapshots) == 2
            assert all(is_valid for _, is_valid in snapshots)

    def test_list_snapshots_with_invalid(self):
        """Test listing snapshots including invalid ones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create snapshots
            (snapshots_dir / "2026-09-25_21-30-12.lua").write_text('return { fps = 120 }')
            (snapshots_dir / "2026-09-25_21-35-47.lua").write_text('return { fps = "invalid" }')

            manager = SnapshotManager(config_dir)
            snapshots = manager.list_snapshots(include_invalid=True)

            # Should return all snapshots
            assert len(snapshots) == 2

    def test_get_latest_valid_snapshot(self):
        """Test getting the latest valid snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create snapshots with different timestamps
            (snapshots_dir / "2026-09-25_21-30-12.lua").write_text('return { fps = 120 }')
            (snapshots_dir / "2026-09-25_21-35-47.lua").write_text('return { fps = 60 }')

            manager = SnapshotManager(config_dir)
            latest = manager.get_latest_valid_snapshot()

            assert latest is not None
            # Should be the second one (newer timestamp)
            assert latest.name == "2026-09-25_21-35-47.lua"

    def test_get_latest_valid_snapshot_none(self):
        """Test getting latest valid snapshot when none exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create only invalid snapshot
            (snapshots_dir / "2026-09-25_21-30-12.lua").write_text('return { fps = "invalid" }')

            manager = SnapshotManager(config_dir)
            latest = manager.get_latest_valid_snapshot()

            assert latest is None

    def test_restore_snapshot(self):
        """Test restoring a snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create a snapshot
            snapshot_path = snapshots_dir / "2026-09-25_21-30-12.lua"
            snapshot_path.write_text('return { fps = 60 }')

            manager = SnapshotManager(config_dir)
            success = manager.restore_snapshot(snapshot_path)

            assert success

            # Verify config was restored
            config_file = config_dir / "mommie.lua"
            assert config_file.exists()

            loader = ConfigLoader(config_file)
            config, is_valid = loader.load()

            assert is_valid
            assert config['fps'] == 60

    def test_restore_invalid_snapshot(self):
        """Test restoring an invalid snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create an invalid snapshot
            snapshot_path = snapshots_dir / "2026-09-25_21-30-12.lua"
            snapshot_path.write_text('return { fps = "invalid" }')

            manager = SnapshotManager(config_dir)
            success = manager.restore_snapshot(snapshot_path)

            assert not success

    def test_delete_snapshot(self):
        """Test deleting a snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create a snapshot
            snapshot_path = snapshots_dir / "2026-09-25_21-30-12.lua"
            snapshot_path.write_text('return { fps = 120 }')

            manager = SnapshotManager(config_dir)
            success = manager.delete_snapshot(snapshot_path)

            assert success
            assert not snapshot_path.exists()

    def test_cleanup_old_snapshots(self):
        """Test cleaning up old snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create many snapshots
            for i in range(15):
                snapshot_path = snapshots_dir / f"2026-09-25_{i:02d}-00-00.lua"
                snapshot_path.write_text('return { fps = 120 }')

            manager = SnapshotManager(config_dir)
            deleted = manager.cleanup_old_snapshots(keep_count=10)

            # Should delete 5 (15 - 10)
            assert deleted == 5

            # Verify we still have at least 10
            valid_count, total_count = manager.get_snapshot_count()
            assert valid_count >= 10

    def test_cleanup_keeps_minimum(self):
        """Test that cleanup never deletes all snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create only 3 snapshots
            for i in range(3):
                snapshot_path = snapshots_dir / f"2026-09-25_{i:02d}-00-00.lua"
                snapshot_path.write_text('return { fps = 120 }')

            manager = SnapshotManager(config_dir)
            deleted = manager.cleanup_old_snapshots(keep_count=10)

            # Should delete 0 (we have fewer than keep_count)
            assert deleted == 0

            # All should still exist
            valid_count, total_count = manager.get_snapshot_count()
            assert valid_count == 3

    def test_get_snapshot_count(self):
        """Test getting snapshot count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create snapshots
            (snapshots_dir / "2026-09-25_21-30-12.lua").write_text('return { fps = 120 }')
            (snapshots_dir / "2026-09-25_21-35-47.lua").write_text('return { fps = "invalid" }')

            manager = SnapshotManager(config_dir)
            valid_count, total_count = manager.get_snapshot_count()

            assert valid_count == 1
            assert total_count == 2

    def test_snapshot_before_restore_creates_backup(self):
        """Test that restoring creates a snapshot of existing config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            snapshots_dir = config_dir / "snapshots"
            snapshots_dir.mkdir(parents=True)

            # Create existing config
            config_file = config_dir / "mommie.lua"
            config_file.write_text('return { fps = 120 }')

            # Create a snapshot to restore
            snapshot_path = snapshots_dir / "2026-09-25_21-30-12.lua"
            snapshot_path.write_text('return { fps = 60 }')

            manager = SnapshotManager(config_dir)
            manager.restore_snapshot(snapshot_path)

            # Should have created a snapshot of the old config
            snapshots = manager.list_snapshots(include_invalid=True)
            assert len(snapshots) >= 2  # Original + backup
