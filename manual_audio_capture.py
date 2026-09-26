#!/usr/bin/env python3
"""
Test script for audio capture validation.
"""

import sys
import time
sys.path.insert(0, 'src')

from system_audio_capture import SystemAudioCapture
from audio_backend import AudioBackend
from mommy_logger import get_logger

def test_audio_capture():
    """Test audio capture with real system audio."""
    logger = get_logger()

    logger.info("Testing audio capture system...")
    logger.info("Please play some audio on your system now!")
    logger.reassurance("I'll listen for 10 seconds. ♡")
    print("")

    # Initialize backend
    backend = AudioBackend()
    logger.info(f"Audio backend: {backend.backend_type}")

    monitor = backend.find_system_monitor()
    if monitor:
        logger.success(f"Monitor found: {monitor['name']}")
    else:
        logger.concern("No monitor found!")
        return False

    # Start capture
    capture = SystemAudioCapture(sample_rate=44100, channels=2, chunk_size=1024)

    if not capture.start():
        logger.concern("Failed to start capture!")
        return False

    logger.info("Listening for audio...")
    print("")

    # Listen for 10 seconds
    start_time = time.time()
    max_level = 0.0
    samples_received = 0

    while time.time() - start_time < 10:
        chunk = capture.read_chunk()
        if chunk is not None:
            level = capture.get_audio_level()
            max_level = max(max_level, level)
            samples_received += len(chunk)

            if level > 0.001:
                logger.info(f"Audio level: {level:.4f} | Samples: {samples_received}")

        time.sleep(0.1)

    capture.stop()

    print("")
    logger.info(f"Test complete!")
    logger.info(f"Total samples received: {samples_received}")
    logger.info(f"Maximum audio level: {max_level:.4f}")

    if max_level > 0.001:
        logger.success("Audio capture is working! ♪")
        return True
    else:
        logger.concern("No audio detected, honey.")
        logger.info("Make sure audio is playing on your system.")
        return False

if __name__ == "__main__":
    success = test_audio_capture()
    sys.exit(0 if success else 1)
