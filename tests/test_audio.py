"""
Tests for audio processing.
"""

import pytest
import numpy as np
from src.signal_processor import SignalProcessor, FrequencyCurve
from src.pulse_generator import PulseGenerator


class TestSignalProcessor:
    """Test signal processor."""

    def test_initialization(self):
        """Test processor initialization."""
        processor = SignalProcessor(
            sample_rate=44100,
            fft_size=2048,
            frequency_min=20,
            frequency_max=20000,
            curve="logarithmic"
        )

        assert processor.sample_rate == 44100
        assert processor.fft_size == 2048
        assert processor.frequency_min == 20
        assert processor.frequency_max == 20000
        assert processor.curve == FrequencyCurve.LOGARITHMIC

    def test_compute_fft(self):
        """Test FFT computation."""
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)

        # Create a simple sine wave
        audio_data = np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 1024))

        fft_magnitude = processor.compute_fft(audio_data)

        assert fft_magnitude is not None
        assert len(fft_magnitude) > 0
        assert all(m >= 0 for m in fft_magnitude)  # Magnitudes should be non-negative

    def test_compute_fft_silence(self):
        """Test FFT with silence."""
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)

        # Create silence
        audio_data = np.zeros(1024)

        fft_magnitude = processor.compute_fft(audio_data)

        assert fft_magnitude is not None
        # Should be very small (close to zero)
        assert np.mean(fft_magnitude) < 0.01

    def test_compute_band_energy(self):
        """Test frequency band energy computation."""
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)

        # Create audio data
        audio_data = np.random.randn(1024) * 0.1
        fft_magnitude = processor.compute_fft(audio_data)

        band_energies = processor.compute_band_energy(fft_magnitude)

        assert band_energies is not None
        assert len(band_energies) > 0
        # All energies should be non-negative
        assert all(e >= 0 for e in band_energies.values())

    def test_compute_total_energy(self):
        """Test total energy computation."""
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)

        # Create audio data
        audio_data = np.random.randn(1024) * 0.1
        fft_magnitude = processor.compute_fft(audio_data)

        total_energy = processor.compute_total_energy(fft_magnitude)

        assert total_energy >= 0
        assert isinstance(total_energy, (int, float))

    def test_compute_spectral_centroid(self):
        """Test spectral centroid computation."""
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)

        # Create audio data
        audio_data = np.random.randn(1024) * 0.1
        fft_magnitude = processor.compute_fft(audio_data)

        centroid = processor.compute_spectral_centroid(fft_magnitude)

        assert centroid >= 0
        assert isinstance(centroid, (int, float))

    def test_compute_spectral_centroid_zero_energy(self):
        """Test spectral centroid with zero energy."""
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)

        # Zero FFT magnitude
        fft_magnitude = np.zeros(100)

        centroid = processor.compute_spectral_centroid(fft_magnitude)

        assert centroid == 0.0

    def test_process_audio(self):
        """Test complete audio processing."""
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)

        # Create audio data
        audio_data = np.random.randn(1024) * 0.1

        features = processor.process_audio(audio_data)

        assert 'total_energy' in features
        assert 'spectral_centroid' in features
        assert 'sub_bass' in features
        assert 'bass' in features
        assert 'mid' in features
        assert 'spectral_motion' in features

        assert features['total_energy'] >= 0
        assert features['spectral_centroid'] >= 0

    def test_low_frequency_signal(self):
        """Test processing low frequency signal."""
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)

        # Create low frequency sine wave (100 Hz)
        audio_data = np.sin(2 * np.pi * 100 * np.linspace(0, 0.1, 1024))

        features = processor.process_audio(audio_data)

        # Low frequency bands should have more energy
        assert features['sub_bass'] > 0 or features['bass'] > 0

    def test_high_frequency_signal(self):
        """Test processing high frequency signal."""
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)

        # Create high frequency sine wave (5000 Hz)
        audio_data = np.sin(2 * np.pi * 5000 * np.linspace(0, 0.1, 1024))

        features = processor.process_audio(audio_data)

        # High frequency bands should have energy
        assert features['high_mid'] > 0 or features['presence'] > 0 or features['brilliance'] > 0

    def test_sudden_energy_change(self):
        """Test processing sudden energy changes."""
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)

        # Create quiet signal
        quiet = np.random.randn(1024) * 0.01
        features_quiet = processor.process_audio(quiet)

        # Create loud signal
        loud = np.random.randn(1024) * 0.5
        features_loud = processor.process_audio(loud)

        # Loud should have more energy
        assert features_loud['total_energy'] > features_quiet['total_energy']

    def test_continuous_audio(self):
        """Test processing continuous audio stream."""
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)

        # Process multiple chunks
        energies = []
        for _ in range(10):
            audio_data = np.random.randn(1024) * 0.1
            features = processor.process_audio(audio_data)
            energies.append(features['total_energy'])

        # All should have energy
        assert all(e > 0 for e in energies)

    def test_temporal_features_follow_real_audio_changes(self):
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)
        quiet = np.sin(2 * np.pi * 440 * np.arange(1024) / 44100.0) * 0.01
        loud = np.sin(2 * np.pi * 440 * np.arange(1024) / 44100.0) * 0.2

        first = processor.process_audio(quiet)
        second = processor.process_audio(loud)

        assert first['energy_delta'] == pytest.approx(first['total_energy'])
        assert second['energy_delta'] > 0.0
        assert second['spectral_flux'] >= 0.0

    def test_spectral_motion_catches_real_texture_changes(self):
        processor = SignalProcessor(sample_rate=44100, fft_size=1024)
        low = np.sin(2 * np.pi * 440 * np.arange(1024) / 44100.0) * 0.05
        high = np.sin(2 * np.pi * 5000 * np.arange(1024) / 44100.0) * 0.05

        first = processor.process_audio(low)
        second = processor.process_audio(high)

        assert first['spectral_motion'] == pytest.approx(0.0)
        assert second['spectral_motion'] > 0.0


    def test_frequency_weights_logarithmic(self):
        """Test logarithmic frequency weights."""
        processor = SignalProcessor(
            sample_rate=44100,
            fft_size=1024,
            curve="logarithmic"
        )

        weights = processor.get_frequency_weights()

        assert weights is not None
        assert len(weights) > 0
        # Lower frequencies should have higher weights
        assert weights[0] > weights[-1]

    def test_frequency_weights_linear(self):
        """Test linear frequency weights."""
        processor = SignalProcessor(
            sample_rate=44100,
            fft_size=1024,
            curve="linear"
        )

        weights = processor.get_frequency_weights()

        assert weights is not None
        assert len(weights) > 0
        # Linear should be more uniform
        assert all(w > 0 for w in weights)


class TestPulseGenerator:
    """Test pulse generator."""

    def test_initialization(self):
        """Test pulse generator initialization."""
        generator = PulseGenerator(
            attack=0.02,
            decay=0.18,
            height=1.5,
            smoothing=0.75,
            sensitivity=1.0,
            sample_rate=120,
            transient_gain=1.8,
            bass_weight=0.35,
            event_threshold=0.45,
            overshoot_ratio=0.38
        )

        assert generator.attack == 0.02
        assert generator.decay == 0.18
        assert generator.height == 1.5
        assert generator.smoothing == 0.75
        assert generator.sensitivity == 1.0
        assert generator.sample_rate == 120
        assert generator.transient_gain == 1.8
        assert generator.bass_weight == 0.35
        assert generator.event_threshold == 0.45
        assert generator.overshoot_ratio == 0.38

    def test_process_audio_features(self):
        """Test processing audio features into pulse."""
        generator = PulseGenerator(sample_rate=120)

        features = {
            'total_energy': 0.5,
            'spectral_centroid': 1000,
        }

        pulse_value = generator.process_audio_features(features)

        assert isinstance(pulse_value, (int, float))
        assert -10 <= pulse_value <= 10  # Reasonable range

    def test_process_silence(self):
        """Test processing silence (zero energy)."""
        generator = PulseGenerator(sample_rate=120)

        features = {
            'total_energy': 0.0,
            'spectral_centroid': 0.0,
        }

        pulse_value = generator.process_audio_features(features)

        # Should be close to zero
        assert abs(pulse_value) < 0.1

    def test_process_loud_audio(self, monkeypatch):
        """A real energy jump produces a larger two-sided ECG event."""
        generator = PulseGenerator(sample_rate=120, transient_gain=2.5)
        clock = iter([1.0 + i / 120.0 for i in range(100)])
        monkeypatch.setattr("src.pulse_generator.time.monotonic", lambda: next(clock))
        generator._last_update = 1.0

        values = []
        for i in range(100):
            if i < 30:
                energy, delta = 0.03, 0.0
            elif i == 30:
                energy, delta = 0.30, 0.27
            else:
                energy, delta = 0.10, 0.0
            values.append(generator.process_audio_features({
                'total_energy': energy,
                'spectral_centroid': 2000,
                'energy_delta': delta,
            }))

        peak_index = max(range(len(values)), key=lambda i: values[i])
        trough_after_peak = min(values[peak_index + 1:])
        assert max(values) > 0.20
        assert trough_after_peak < -0.05

    def test_smoothing(self):
        """Test that smoothing works."""
        generator = PulseGenerator(smoothing=0.9, sample_rate=120)

        features = {'total_energy': 0.5, 'spectral_centroid': 1000}

        # Process same features multiple times
        values = []
        for _ in range(5):
            pulse_value = generator.process_audio_features(features)
            values.append(pulse_value)

        # Values should converge (become more similar)
        assert max(values) - min(values) < 0.5

    def test_sensitivity(self):
        """Sensitivity still controls audio level mapping."""
        generator_low = PulseGenerator(sensitivity=0.5, sample_rate=120)
        generator_high = PulseGenerator(sensitivity=2.0, sample_rate=120)

        low_level = generator_low._energy_to_pulse(0.5, 1000)
        high_level = generator_high._energy_to_pulse(0.5, 1000)

        assert high_level > low_level

    def test_get_history(self):
        """Test getting pulse history."""
        generator = PulseGenerator(sample_rate=120)

        features = {'total_energy': 0.5, 'spectral_centroid': 1000}

        # Process some audio
        for _ in range(10):
            generator.process_audio_features(features)

        history = generator.get_history()

        assert len(history) > 0
        assert len(history) <= generator.history_length

    def test_reset(self):
        """Test resetting the generator."""
        generator = PulseGenerator(sample_rate=120)

        features = {'total_energy': 0.5, 'spectral_centroid': 1000}

        # Process some audio
        for _ in range(10):
            generator.process_audio_features(features)

        # Reset
        generator.reset()

        # History should be empty
        assert len(generator.get_history()) == 0

    def test_continuous_audio_variation_keeps_ecg_alive_without_kicks(self, monkeypatch):
        generator = PulseGenerator(sample_rate=120)
        clock = iter([1.0 + i / 120.0 for i in range(260)])
        monkeypatch.setattr("src.pulse_generator.time.monotonic", lambda: next(clock))
        generator._last_update = 1.0

        # Irregular musical-level changes with no kick/onset classification.
        energies = [
            0.080, 0.081, 0.078, 0.084, 0.079, 0.088, 0.083, 0.081, 0.086, 0.077,
            0.085, 0.080, 0.089, 0.082, 0.087, 0.079, 0.084, 0.081, 0.088, 0.078,
        ] * 12
        values = [
            generator.process_audio_features({"total_energy": energy, "spectral_centroid": 1000.0})
            for energy in energies
        ]

        assert max(values) > 0.02
        assert min(values) < -0.01
        assert sum(value > 0.005 for value in values) > 10
        assert sum(value < -0.005 for value in values) > 10

    def test_small_energy_jitter_does_not_create_full_pulses(self, monkeypatch):
        generator = PulseGenerator(sample_rate=120, event_threshold=0.45)
        clock = iter([1.0 + i / 120.0 for i in range(260)])
        monkeypatch.setattr("src.pulse_generator.time.monotonic", lambda: next(clock))
        generator._last_update = 1.0

        values = []
        max_event = 0.0
        for energy in [0.03, 0.032, 0.031, 0.034, 0.032] * 48:
            values.append(generator.process_audio_features({"total_energy": energy}))
            max_event = max(max_event, generator.event_score)

        # Small jitter still permits gentle movement, but does not become a full
        # transient event.
        assert max_event < 0.10
        assert max(abs(value) for value in values) < 0.13

    def test_audio_event_has_positive_peak_negative_overshoot_and_recovery(self, monkeypatch):
        generator = PulseGenerator(sample_rate=120, event_threshold=0.40, overshoot_ratio=0.40, transient_gain=2.5)
        clock = iter([1.0 + i / 120.0 for i in range(110)])
        monkeypatch.setattr("src.pulse_generator.time.monotonic", lambda: next(clock))
        generator._last_update = 1.0

        values = []
        for i in range(100):
            if i < 30:
                energy, delta = 0.03, 0.0
            elif i == 30:
                energy, delta = 0.30, 0.27
            else:
                energy, delta = 0.30, 0.0
            values.append(generator.process_audio_features({
                "total_energy": energy,
                "spectral_centroid": 1000.0,
                "energy_delta": delta,
            }))

        positive_peak = max(values[30:])
        peak_index = values.index(positive_peak)
        negative = min(values[peak_index + 1:])

        assert positive_peak > 0.20
        assert negative < -0.08
        negative_index = values.index(negative)
        assert peak_index < negative_index
        assert values[-1] > negative

    def test_steady_audio_settles_instead_of_generating_periodic_pulses(self, monkeypatch):
        generator = PulseGenerator(sample_rate=120)
        clock = iter([1.0 + i / 120.0 for i in range(230)])
        monkeypatch.setattr("src.pulse_generator.time.monotonic", lambda: next(clock))
        generator._last_update = 1.0

        values = [
            generator.process_audio_features({"total_energy": energy})
            for energy in [0.03] * 8 + [0.25] * 192
        ]

        # A steady signal gets one physically-shaped response and then returns to
        # baseline. No hidden phase/timer keeps creating new beats.
        assert max(values[8:70]) > 0.10
        assert min(values[8:120]) < -0.04
        assert max(abs(value) for value in values[150:]) < 0.015

    def test_audio_changes_drive_transients(self, monkeypatch):
        generator = PulseGenerator(sample_rate=120, transient_gain=2.5)
        clock = iter([1.0 + i / 120.0 for i in range(170)])
        monkeypatch.setattr("src.pulse_generator.time.monotonic", lambda: next(clock))
        generator._last_update = 1.0

        samples = []
        for i in range(160):
            if i < 60:
                energy, delta = 0.08, 0.0
            elif i == 60:
                energy, delta = 0.30, 0.22
            else:
                energy, delta = 0.12, 0.0
            samples.append(generator.process_audio_features({
                "total_energy": energy,
                "spectral_centroid": 1000.0,
                "energy_delta": delta,
            }))

        calm_peak = max(abs(v) for v in samples[:60])
        event_peak = max(abs(v) for v in samples[60:110])
        assert event_peak > calm_peak * 1.5
        assert max(samples[60:110]) > 0.15
        assert min(samples[60:130]) < -0.05

    def test_bass_content_changes_the_audio_response(self, monkeypatch):
        generator = PulseGenerator(sample_rate=120, bass_weight=0.8)
        clock = iter([1.0 + i / 120.0 for i in range(4)])
        monkeypatch.setattr("src.pulse_generator.time.monotonic", lambda: next(clock))
        generator._last_update = 1.0

        high_band = {"total_energy": 0.08, "spectral_centroid": 5000.0, "sub_bass": 0.0, "bass": 0.0, "low_mid": 0.0}
        bass = {"total_energy": 0.08, "spectral_centroid": 80.0, "sub_bass": 0.04, "bass": 0.03, "low_mid": 0.0}
        generator.process_audio_features(high_band)
        generator.process_audio_features(bass)
        bass_event = generator.event_score
        assert bass_event > 0.25

    def test_spectral_flux_reinforces_real_attacks(self, monkeypatch):
        generator = PulseGenerator(sample_rate=120, transient_gain=2.0)
        clock = iter([1.0, 1.0 + 1 / 120.0, 1.0 + 2 / 120.0])
        monkeypatch.setattr("src.pulse_generator.time.monotonic", lambda: next(clock))
        generator._last_update = 1.0

        calm = {"total_energy": 0.08, "spectral_centroid": 500.0, "spectral_flux": 0.0}
        attack = {"total_energy": 0.08, "spectral_centroid": 500.0, "spectral_flux": 0.9}
        generator.process_audio_features(calm)
        generator.process_audio_features(attack)
        assert generator.event_score > 0.18

    def test_generate_ecg_trace_uses_live_audio_response(self, monkeypatch):
        generator = PulseGenerator(sample_rate=120)
        clock = iter([1.0 + i / 120.0 for i in range(8)])
        monkeypatch.setattr("src.pulse_generator.time.monotonic", lambda: next(clock))
        generator._last_update = 1.0
        first = generator.generate_ecg_trace(0.01)
        second = generator.generate_ecg_trace(0.5)
        third = generator.generate_ecg_trace(0.5)
        assert isinstance(first, (int, float))
        assert abs(second) > abs(first)
        assert abs(third) >= abs(first)


class TestCalibratedPulseResponse:
    def test_quiet_audio_is_visible_but_silence_is_not(self):
        generator = PulseGenerator(sensitivity=1.6, sample_rate=120)
        assert generator._energy_to_pulse(0.0, 0.0) == 0.0
        assert generator._energy_to_pulse(0.001, 0.0) == 0.0
        assert generator._energy_to_pulse(0.01, 0.0) > 0.1

    def test_response_has_headroom_for_strong_audio(self):
        generator = PulseGenerator(sensitivity=1.6, sample_rate=120)
        quiet = generator._energy_to_pulse(0.01, 0.0)
        normal = generator._energy_to_pulse(0.05, 0.0)
        strong = generator._energy_to_pulse(0.20, 0.0)
        peak = generator._energy_to_pulse(0.50, 0.0)

        assert 0.0 < quiet < normal < strong < peak < 1.0
        assert strong < 0.90

    def test_sensitivity_changes_response(self):
        features = {'total_energy': 0.05, 'spectral_centroid': 1000}
        low = PulseGenerator(sensitivity=0.5, sample_rate=120)
        high = PulseGenerator(sensitivity=3.0, sample_rate=120)
        high_value = high._energy_to_pulse(features['total_energy'], features['spectral_centroid'])
        low_value = low._energy_to_pulse(features['total_energy'], features['spectral_centroid'])
        assert high_value > low_value

    def test_total_energy_is_pcm_rms(self):
        processor = SignalProcessor(sample_rate=48000, fft_size=2048)
        t = np.arange(1024) / 48000.0
        amplitude = 0.1
        audio = amplitude * np.sin(2 * np.pi * 440 * t)
        features = processor.process_audio(audio)
        expected_rms = float(np.sqrt(np.mean(audio ** 2)))
        assert features['total_energy'] == pytest.approx(expected_rms, rel=0.02)


    def test_top_level_decay_controls_release_retention(self, monkeypatch):
        fast = PulseGenerator(global_decay=0.2, sample_rate=120)
        slow = PulseGenerator(global_decay=0.95, sample_rate=120)
        monkeypatch.setattr("src.pulse_generator.time.monotonic", lambda: 1.0)
        fast._last_update = 0.0
        slow._last_update = 0.0
        fast_value = fast._apply_response(0.8, 0.2)
        slow_value = slow._apply_response(0.8, 0.2)
        assert slow_value > fast_value
