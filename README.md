# mommy-pulsy

**mommy-pulsy** is a terminal-only real-time audio visualizer with an ECG/heartbeat aesthetic. It listens to the **real system playback audio** (browser, Spotify, games, videos, players, etc.) through the system audio server and renders a continuous pulse in the terminal.

There is no GUI and no microphone capture by default.

## Installation

From a Git checkout:

```bash
git clone <your-repository>
cd mommy-pulsy
./install.sh
```

Remote installer:

```bash
MOMMY_PULSY_REPO='https://github.com/<you>/mommy-pulsy.git' \
  curl -fsSL <your-raw-installer-url> | sh
```

On Arch-based systems the installer creates an isolated Python `venv`. On other systems it uses the normal user-level Python package installation path.

## System audio

The visualizer targets the **monitor of the current default playback sink**, not your microphone. On PipeWire/PulseAudio systems the installer/application uses the PulseAudio compatibility layer when available and can fall back to native PipeWire node discovery.

Check detection before launching the visualizer:

```bash
mommy-pulsy --audio-info
```

You want to see a monitor source whose name ends in `.monitor` or an equivalent PipeWire monitor node.

## Configuration

The config lives at:

```text
~/.config/mommy-pulsy/mommie.lua
```

It is a data-only Lua format. Example:

```lua
return {
    sensitivity = 1.6,
    smoothing = 0.60,
    decay = 0.85,
    fps = 120,

    audio = {
        sample_rate = 48000,
        channels = 2,
        chunk_size = 1024,
        queue_size = 8,
        backend = "auto",
    },

    pulse = {
        attack = 0.02,
        decay = 0.18,
        height = 1.5,
        threshold = 0.00398107,
        transient_gain = 1.8,
        bass_weight = 0.35,
    },

    frequency = {
        min = 20,
        max = 20000,
        curve = "logarithmic",
    },

    recovery = {
        enabled = true,
        auto_restore = true,
    },
}
```

The loader does not execute arbitrary Lua code; it accepts configuration data only.

### Live configuration reload

While `mommy-pulsy run` is active, changes to `mommie.lua` are checked automatically.
A valid change is parsed, validated, fully built, and then swapped into the running
processor as one complete runtime bundle. An invalid edit leaves the last valid
configuration active and prints the specific field/error.

The audio capture stream itself is not replaced during a reload. Changes to the
`audio` section are recorded for the next start so the already-working playback
monitor is never interrupted.

The pulse is continuously driven by the current playback frame. The amplitude starts
from captured PCM RMS, with low-frequency bands contributing through `pulse.bass_weight`;
real changes between frames and spectral flux reinforce attacks/transients through
`pulse.transient_gain`. There is no BPM clock, fixed pulse interval, cooldown, or
internal waveform phase advancing on its own. `pulse.attack` controls how quickly
real audio increases reach the envelope, and `pulse.decay` controls the release.
`sensitivity` still uses the calibrated reciprocal power curve, so `1.0` is the
reference response and higher values lift quieter audio without changing the capture
backend.

## Snapshots and recovery

Configuration changes use atomic writes and preserve the previous configuration in:

```text
~/.config/mommy-pulsy/snapshots/
```

When `mommie.lua` is missing or invalid and automatic recovery is enabled, mommy-pulsy searches snapshots from newest to oldest and restores the newest **valid** one.

```bash
mommy-pulsy snapshots
mommy-pulsy restore <snapshot>
mommy-pulsy undo
```

## Development

Runtime dependency:

```text
numpy
```

Development dependencies:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

For a real system playback test, use:

```bash
python3 manual_audio_capture.py
```

Play audio in another application while the script listens.

## License

MIT
