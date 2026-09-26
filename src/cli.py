"""Command-line interface for mommy-pulsy."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from .audio_backend import AudioBackend
    from .mommy_logger import get_logger
    from .mommy_pulsy import MommyPulsy
    from .snapshot_manager import SnapshotManager
    from .system_audio_capture import SystemAudioCapture
except ImportError:
    from audio_backend import AudioBackend
    from mommy_logger import get_logger
    from mommy_pulsy import MommyPulsy
    from snapshot_manager import SnapshotManager
    from system_audio_capture import SystemAudioCapture

VERSION = "0.3.0"


def cmd_run(args) -> int:
    app = MommyPulsy()
    if not app.start():
        return 1
    app.run()
    return 0


def cmd_snapshots(args) -> int:
    logger = get_logger()
    manager = SnapshotManager()
    snapshots = manager.list_snapshots(include_invalid=True)
    valid_count, total_count = manager.get_snapshot_count()
    logger.info(f"Snapshots: {valid_count} valid, {total_count} total")
    if not snapshots:
        logger.reassurance("No snapshots yet, darling.")
        return 0
    for path, valid in snapshots:
        logger.info(f"  {'✓' if valid else '✗'} {path.name}")
    return 0


def cmd_restore(args) -> int:
    logger = get_logger()
    manager = SnapshotManager()
    if not args.snapshot:
        logger.concern("You need to specify which snapshot to restore, honey.")
        return 1
    path = manager.snapshots_dir / args.snapshot
    if not path.is_file() or path.parent.resolve() != manager.snapshots_dir.resolve():
        logger.concern(f"I couldn't find snapshot '{args.snapshot}', honey.")
        return 1
    if not manager.restore_snapshot(path):
        logger.concern("That snapshot isn't valid or couldn't be restored, darling.")
        return 1
    logger.success("Snapshot restored successfully.")
    return 0


def cmd_undo(args) -> int:
    logger = get_logger()
    manager = SnapshotManager()
    snapshots = [path for path, valid in manager.list_snapshots() if valid]
    if len(snapshots) < 1:
        logger.concern("I couldn't find any valid snapshots to undo to, darling.")
        return 1
    if not manager.restore_snapshot(snapshots[0]):
        logger.concern("I couldn't undo the change, honey.")
        return 1
    logger.success("Undone successfully.")
    return 0


def cmd_version(args) -> int:
    get_logger().info(f"mommy-pulsy version {VERSION}")
    return 0


def cmd_audio_info(args) -> int:
    """Report real, verified capture state -- never a guess or simulated status."""
    logger = get_logger()
    logger.info("Looking for your real system playback audio, sweetheart. ♡")
    backend = AudioBackend()
    backend.print_audio_info()

    if not backend.find_system_monitor():
        logger.concern("I couldn't find a monitor for the current output device, darling.")
        logger.info("On PipeWire, make sure pipewire-pulse is available; on PulseAudio, make sure pactl/parec are installed.")
        return 1

    logger.success("Playback monitor found.")
    logger.info("Checking whether real samples are actually arriving...")

    capture = SystemAudioCapture(backend=backend.preferred)
    if not capture.start():
        logger.concern("I found the monitor, but couldn't open the capture stream, darling.")
        if capture.last_error:
            logger.error(f"  capture error: {capture.last_error}")
        return 1

    import time as _time
    deadline = _time.monotonic() + 2.0
    receiving = False
    while _time.monotonic() < deadline:
        capture.read_chunk(timeout=0.1)
        if capture.is_receiving_audio():
            receiving = True
            break
    capture.stop()

    if receiving:
        logger.info(f"  amplitude: {capture.get_audio_level():.4f}")
        logger.success("State: receiving audio")
        return 0

    logger.info("I found your system audio, honey.")
    logger.concern("But I'm not receiving samples yet.")
    logger.reassurance("Play something and I'll listen")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="mommy-pulsy",
        description="Terminal-only ECG-style system-audio visualizer ♡",
    )
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    parser.add_argument("--audio-info", action="store_true", help="Show detected system playback monitor")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="Run the visualizer").set_defaults(func=cmd_run)
    subparsers.add_parser("snapshots", help="List configuration snapshots").set_defaults(func=cmd_snapshots)
    restore = subparsers.add_parser("restore", help="Restore a snapshot")
    restore.add_argument("snapshot")
    restore.set_defaults(func=cmd_restore)
    subparsers.add_parser("undo", help="Restore the latest valid configuration snapshot").set_defaults(func=cmd_undo)
    subparsers.add_parser("version", help="Show version information").set_defaults(func=cmd_version)

    args = parser.parse_args()
    if args.version:
        return cmd_version(args)
    if args.audio_info:
        return cmd_audio_info(args)
    return getattr(args, "func", cmd_run)(args)


if __name__ == "__main__":
    raise SystemExit(main())
