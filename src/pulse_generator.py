"""Audio-driven continuous ECG generation."""

from __future__ import annotations

from collections import deque
import math
import time
from typing import Dict, List


class PulseGenerator:
    """Turn continuous playback dynamics into a living, baseline-centered ECG.

    The ECG is a stateful, causal biphasic envelope rather than a beat clock.
    Continuous playback features drive its state, while real spectral/energy
    changes make the same ECG morphology larger and sharper. Silence settles to
    the baseline.
    """

    DEFAULT_NOISE_FLOOR_RMS = 10 ** (-48.0 / 20.0)  # -48 dBFS
    REFERENCE_RMS = 10 ** (-6.0 / 20.0)             # -6 dBFS RMS

    def __init__(
        self,
        attack: float = 0.02,
        decay: float = 0.18,
        height: float = 1.5,
        smoothing: float = 0.60,
        sensitivity: float = 1.5,
        threshold: float = DEFAULT_NOISE_FLOOR_RMS,
        global_decay: float = 0.85,
        sample_rate: int = 120,
        transient_gain: float = 1.8,
        bass_weight: float = 0.35,
        event_threshold: float = 0.45,
        overshoot_ratio: float = 0.38,
    ):
        self.attack = max(float(attack), 0.001)
        self.decay = max(float(decay), 0.001)
        self.height = float(height)
        self.smoothing = min(max(float(smoothing), 0.0), 1.0)
        self.sensitivity = max(float(sensitivity), 0.0)
        self.threshold = max(float(threshold), 0.0)
        self.global_decay = min(max(float(global_decay), 0.0), 1.0)
        self.sample_rate = max(1, int(sample_rate))
        self.transient_gain = max(float(transient_gain), 0.0)
        self.bass_weight = min(max(float(bass_weight), 0.0), 1.0)
        self.event_threshold = min(max(float(event_threshold), 0.0), 1.0)
        self.overshoot_ratio = min(max(float(overshoot_ratio), 0.0), 1.0)

        # Continuous audio envelopes used to describe the current musical state.
        self.level_fast = 0.0
        self.level_slow = 0.0
        self.low_fast = 0.0
        self.low_slow = 0.0
        self.spectral_flux = 0.0
        self.event_score = 0.0
        self._armed = True
        self._analysis_initialized = False

        # Continuous ECG dynamics. There is no clocked beat phase here. Audio
        # changes drive a causal biphasic response: fast activation followed by a
        # slower refractory state, which produces the positive spike, baseline
        # crossing, negative overshoot and gradual recovery.
        self._ecg_drive = 0.0
        self._ecg_activation = 0.0
        self._ecg_recovery = 0.0
        self._previous_level = 0.0

        # Kept for compatibility with older callers/tests that inspect these names.
        self.current_value = 0.0
        self._pulse_elapsed = 0.0
        self._pulse_amplitude = 0.0
        self._pulse_active = False
        self.previous_smoothed = 0.0
        self.previous_drive = 0.0
        self.transient_fast = 0.0
        self.transient_slow = 0.0
        self.drop_response = 0.0

        self.history_length = max(8, int(self.sample_rate * 2))
        self.pulse_history = deque(maxlen=self.history_length)
        self._last_update = time.monotonic()

    @staticmethod
    def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return min(max(float(value), lower), upper)

    def _step_dt(self) -> float:
        now = time.monotonic()
        dt = max(1e-4, now - self._last_update)
        self._last_update = now
        return min(dt, 0.25)

    @staticmethod
    def _follow(current: float, target: float, tau: float, dt: float) -> float:
        tau = max(float(tau), 0.001)
        alpha = 1.0 - math.exp(-dt / tau)
        return current + (target - current) * alpha

    def process_audio_features(self, features: Dict[str, float]) -> float:
        """Turn continuously changing playback features into one ECG sample.

        The generator is a causal, audio-driven biphasic envelope rather than a
        beat clock. Every analysis frame contributes to the drive; real changes in
        energy/spectrum increase the drive and therefore the excursion. The
        waveform itself is produced by different attack/release time constants, so
        an excitation rises quickly, falls through zero, overshoots negative and
        recovers gradually without requiring a periodic timer.
        """
        dt = self._step_dt()

        energy = max(0.0, float(features.get("total_energy", 0.0)))
        centroid = max(0.0, float(features.get("spectral_centroid", 0.0)))
        spectral_flux = self._clamp(features.get("spectral_flux", 0.0))
        spectral_motion = self._clamp(features.get("spectral_motion", spectral_flux))
        energy_delta = float(features.get("energy_delta", 0.0))
        energy_delta = energy_delta if math.isfinite(energy_delta) else 0.0

        level = self._energy_to_pulse(energy, centroid)
        bass_ratio = self._bass_ratio(features, energy)
        low_level = self._clamp(level * bass_ratio)

        # Fast/slow energy envelopes are temporal evidence only. They never gate
        # whether the ECG exists, and bass is just one contributor to intensity.
        fast_tau = min(self.attack * 1.8, 0.08)
        slow_tau = max(self.decay * 1.35, fast_tau * 3.0, 0.10)
        was_analysis_initialized = self._analysis_initialized
        if not self._analysis_initialized:
            self.level_fast = level
            self.level_slow = level
            self.low_fast = low_level
            self.low_slow = low_level
            self._analysis_initialized = True
            self.event_score = 0.0
        else:
            self.level_fast = self._follow(self.level_fast, level, fast_tau, dt)
            self.level_slow = self._follow(self.level_slow, level, slow_tau, dt)
            self.low_fast = self._follow(self.low_fast, low_level, fast_tau, dt)
            self.low_slow = self._follow(self.low_slow, low_level, slow_tau, dt)

        level_motion = self._clamp(abs(self.level_fast - self.level_slow) / 0.12)
        low_motion = self._clamp(abs(self.low_fast - self.low_slow) / 0.10)
        level_delta = self._clamp(abs(level - self._previous_level) / 0.10) if was_analysis_initialized else 0.0
        delta_scale = max(self.REFERENCE_RMS * 0.10, 1e-5)
        energy_motion = self._clamp(abs(energy_delta) / delta_scale) if was_analysis_initialized else 0.0
        self._previous_level = level

        # Threshold-free audio motion: small musical changes make small ECG
        # excursions, while strong transients make the same morphology larger and
        # faster. The trigger is based on real feature changes, never on a beat clock.
        motion_score = self._clamp(
            0.30 * level_delta
            + 0.25 * energy_motion
            + 0.30 * spectral_motion
            + 0.15 * low_motion * self.bass_weight
        )

        onset = max(0.0, self.level_fast - self.level_slow)
        low_onset = max(0.0, self.low_fast - self.low_slow)
        onset_score = self._clamp(onset / 0.18)
        low_score = self._clamp(low_onset / 0.12)
        self.event_score = self._clamp(
            0.35 * level_delta
            + 0.15 * onset_score
            + 0.15 * low_score
            + 0.25 * spectral_motion
            + 0.10 * energy_motion
        )
        self.spectral_flux = spectral_flux

        # Baseline is always zero. Current level provides a tiny continuous body,
        # while temporal change and real transients dominate visible movement.
        continuous_body = 0.06 * level + 0.03 * low_level
        transient_scale = 0.35 + (0.65 * min(self.transient_gain / 1.8, 2.0))
        change_drive = transient_scale * ((0.68 * motion_score) + (0.26 * self.event_score) + (0.06 * spectral_flux))
        target_drive = self._clamp(continuous_body + change_drive) if energy > self.threshold else 0.0
        self._ecg_drive = self._follow(
            self._ecg_drive, target_drive, max(self.attack * 0.35, 0.006), dt
        )

        # Two cascaded leaky states form the ECG morphology. Activation attacks
        # quickly and releases sharply; recovery lags behind it. That lag itself
        # produces the negative overshoot, so negative values remain first-class.
        activation_attack_tau = max(self.attack * (0.45 + 0.20 * self.smoothing), 0.006)
        activation_release_tau = max(self.attack * (1.20 + 0.25 * self.smoothing), 0.024)
        recovery_rise_tau = max(activation_attack_tau * 4.0, 0.035)
        recovery_fall_tau = max(self.decay * (0.80 + 0.25 * self.smoothing), 0.12)
        activation_tau = (
            activation_attack_tau
            if self._ecg_drive > self._ecg_activation
            else activation_release_tau
        )
        self._ecg_activation = self._follow(
            self._ecg_activation, self._ecg_drive, activation_tau, dt
        )
        recovery_tau = (
            recovery_rise_tau
            if self._ecg_activation > self._ecg_recovery
            else recovery_fall_tau
        )
        self._ecg_recovery = self._follow(
            self._ecg_recovery, self._ecg_activation, recovery_tau, dt
        )

        raw = self._ecg_activation - self._ecg_recovery
        if raw < 0.0:
            raw *= 1.0 + (2.8 * self.overshoot_ratio)

        # Silence releases the same physical state toward zero. It never creates
        # another animation state and never shifts the baseline.
        if energy <= self.threshold:
            self._ecg_drive = self._follow(self._ecg_drive, 0.0, recovery_fall_tau, dt)

        output = self._clamp(raw, -1.0, 1.0)
        self.current_value = output

        # Compatibility/status fields describe continuous state, not a separate
        # pulse lifecycle. None of them gates waveform output.
        self.previous_smoothed = self.level_slow
        self.previous_drive = self.level_fast
        self.transient_fast = onset_score
        self.transient_slow = level_motion
        self.drop_response = max(0.0, -output)
        self._pulse_amplitude = max(abs(self._ecg_activation), abs(self._ecg_recovery))
        self._pulse_active = energy > self.threshold and self._pulse_amplitude > 0.001

        self.pulse_history.append(float(output))
        return float(output)

    def _next_cycle_variation(self, level: float, spectral_flux: float) -> float:
        """Legacy compatibility helper; the ECG no longer uses cycle timing."""
        del level, spectral_flux
        return 1.0

    def _update_event_gate(self) -> None:
        """Compatibility helper for older integrations; the gate no longer drives output."""
        settle_threshold = self.event_threshold * 0.32
        if self._armed:
            return
        if self.event_score <= settle_threshold and abs(self.level_fast - self.level_slow) < 0.045:
            self._armed = True

    def _start_pulse(self, event_strength: float) -> None:
        """Compatibility helper: transient boosts now modulate the continuous ECG."""
        self._ecg_transient = max(self._ecg_transient, self._clamp(event_strength))
        self._pulse_amplitude = self._ecg_amplitude
        self._pulse_elapsed = 0.0
        self._pulse_active = True

    def _advance_pulse(self, dt: float) -> float:
        """Compatibility helper for older callers; advance the continuous ECG state."""
        del dt
        return float(self.current_value)

    def _bass_ratio(self, features: Dict[str, float], total_energy: float) -> float:
        """Return a bounded low-frequency contribution from the current FFT frame."""
        if total_energy <= self.threshold:
            return 0.0
        band_keys = ("sub_bass", "bass", "low_mid")
        if not any(key in features for key in band_keys):
            return 1.0
        sub_bass = max(0.0, float(features.get("sub_bass", 0.0)))
        bass = max(0.0, float(features.get("bass", 0.0)))
        low_mid = max(0.0, float(features.get("low_mid", 0.0)))
        ratio = (1.15 * sub_bass + bass + 0.45 * low_mid) / max(total_energy, 1e-7)
        return self._clamp(ratio)

    def _energy_to_pulse(self, energy: float, spectral_centroid: float) -> float:
        """Map PCM RMS to a calibrated level in [0, 1]."""
        if not math.isfinite(energy) or energy <= 0.0 or self.sensitivity <= 0.0:
            return 0.0

        rms = float(energy)
        noise_floor = max(self.threshold, 1e-7)
        reference = max(self.REFERENCE_RMS, noise_floor * 1.01)

        if rms <= noise_floor:
            normalized = 0.0
        else:
            floor_db = 20.0 * math.log10(noise_floor)
            ref_db = 20.0 * math.log10(reference)
            level_db = 20.0 * math.log10(max(rms, noise_floor))
            normalized = (level_db - floor_db) / max(ref_db - floor_db, 1e-9)
            normalized = self._clamp(normalized)

        shaped = normalized ** (1.0 / self.sensitivity) if normalized > 0.0 else 0.0
        brightness = self._clamp(spectral_centroid / 6000.0)
        shape_factor = 0.92 + brightness * 0.08
        return self._clamp(shaped * (self.height / 1.5) * shape_factor)

    def _apply_response(self, current: float, target: float, dt: float | None = None) -> float:
        """Compatibility helper for callers that still use the old envelope method."""
        if dt is None:
            dt = 1.0 / self.sample_rate
        tau = self.attack if target > current else self.decay
        value = self._follow(current, target, tau, max(dt, 1e-4))
        if target < current and self.global_decay < 1.0:
            value *= self.global_decay ** dt
        return self._clamp(value)

    def generate_ecg_trace(self, energy: float) -> float:
        """Compatibility helper: feed a scalar energy value through the live detector."""
        return self.process_audio_features({"total_energy": float(energy)})

    def copy_runtime_state_from(self, previous: "PulseGenerator") -> None:
        """Carry live waveform/detector state across a configuration swap."""
        if not isinstance(previous, PulseGenerator):
            return
        self.level_fast = float(previous.level_fast)
        self.level_slow = float(previous.level_slow)
        self.low_fast = float(previous.low_fast)
        self.low_slow = float(previous.low_slow)
        self.event_score = float(previous.event_score)
        self.spectral_flux = float(previous.spectral_flux)
        self._armed = bool(previous._armed)
        self._analysis_initialized = bool(previous._analysis_initialized)
        self._ecg_drive = float(previous._ecg_drive)
        self._ecg_activation = float(previous._ecg_activation)
        self._ecg_recovery = float(previous._ecg_recovery)
        self._previous_level = float(previous._previous_level)
        self.current_value = float(previous.current_value)
        self._pulse_elapsed = float(previous._pulse_elapsed)
        self._pulse_amplitude = float(previous._pulse_amplitude)
        self._pulse_active = bool(previous._pulse_active)
        self.previous_smoothed = float(previous.previous_smoothed)
        self.previous_drive = float(previous.previous_drive)
        self.transient_fast = float(previous.transient_fast)
        self.transient_slow = float(previous.transient_slow)
        self.drop_response = float(previous.drop_response)
        self.pulse_history.extend(previous.pulse_history)
        self._last_update = time.monotonic()

    def get_history(self) -> List[float]:
        return list(self.pulse_history)

    def reset(self) -> None:
        self.level_fast = 0.0
        self.level_slow = 0.0
        self.low_fast = 0.0
        self.low_slow = 0.0
        self.spectral_flux = 0.0
        self.event_score = 0.0
        self._armed = True
        self._analysis_initialized = False
        self._ecg_drive = 0.0
        self._ecg_activation = 0.0
        self._ecg_recovery = 0.0
        self._previous_level = 0.0
        self.current_value = 0.0
        self._pulse_elapsed = 0.0
        self._pulse_amplitude = 0.0
        self._pulse_active = False
        self.previous_smoothed = 0.0
        self.previous_drive = 0.0
        self.transient_fast = 0.0
        self.transient_slow = 0.0
        self.drop_response = 0.0
        self.pulse_history.clear()
        self._last_update = time.monotonic()
