"""
Signal processing module for mommy-pulsy.

Handles FFT analysis, frequency bands, and energy extraction.
"""

import numpy as np
from typing import Dict, List, Tuple
from enum import Enum


class FrequencyCurve(Enum):
    """Frequency curve types."""
    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"


class SignalProcessor:
    """Processes audio signals for visualization."""

    def __init__(self,
                 sample_rate: int = 44100,
                 fft_size: int = 2048,
                 frequency_min: int = 20,
                 frequency_max: int = 20000,
                 curve: str = "logarithmic"):
        """
        Initialize the signal processor.

        Args:
            sample_rate: Audio sample rate in Hz
            fft_size: FFT size (power of 2 recommended)
            frequency_min: Minimum frequency to analyze
            frequency_max: Maximum frequency to analyze
            curve: Frequency curve type ("linear" or "logarithmic")
        """
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self.frequency_min = frequency_min
        self.frequency_max = frequency_max
        self.curve = FrequencyCurve(curve)

        # Calculate frequency bins
        self._calculate_frequency_bins()

        # Define frequency bands (sub-bass, bass, low-mid, mid, high-mid, presence, brilliance)
        self.frequency_bands = self._create_frequency_bands()
        self._previous_rms = 0.0
        self._previous_band_energies = None
        self._previous_centroid = 0.0

    def _calculate_frequency_bins(self) -> None:
        """Calculate FFT frequency bins."""
        self.freq_bins = np.fft.rfftfreq(self.fft_size, 1.0 / self.sample_rate)

        # Filter to our frequency range
        self.mask = (self.freq_bins >= self.frequency_min) & (self.freq_bins <= self.frequency_max)
        self.filtered_freq_bins = self.freq_bins[self.mask]
        self.mask_indices = np.where(self.mask)[0]

    def _create_frequency_bands(self) -> List[Tuple[float, float]]:
        """
        Create frequency bands for analysis.

        Returns:
            List of (min_freq, max_freq) tuples
        """
        if self.curve == FrequencyCurve.LOGARITHMIC:
            # Logarithmic bands (more bands in lower frequencies)
            bands = [
                (20, 60),      # Sub-bass
                (60, 250),     # Bass
                (250, 500),    # Low-mid
                (500, 2000),   # Mid
                (2000, 4000),  # High-mid
                (4000, 6000),  # Presence
                (6000, 20000), # Brilliance
            ]
        else:
            # Linear bands
            num_bands = 7
            step = (self.frequency_max - self.frequency_min) / num_bands
            bands = []
            for i in range(num_bands):
                min_f = self.frequency_min + i * step
                max_f = self.frequency_min + (i + 1) * step
                bands.append((min_f, max_f))

        return bands

    def compute_fft(self, audio_data: np.ndarray) -> np.ndarray:
        """
        Compute FFT of audio data.

        Args:
            audio_data: Audio samples

        Returns:
            FFT magnitude spectrum
        """
        # Apply window function to reduce spectral leakage
        window = np.hanning(len(audio_data))
        windowed = audio_data * window

        # Compute FFT
        fft_result = np.fft.rfft(windowed, n=self.fft_size)

        # Get magnitude
        magnitude = np.abs(fft_result)

        # Normalize
        magnitude = magnitude / (len(audio_data) / 2)

        # Filter to our frequency range
        return magnitude[self.mask]

    def compute_rms(self, audio_data: np.ndarray) -> float:
        """Return the true time-domain RMS amplitude of the captured PCM.

        System playback capture is normalized float PCM. Using RMS here avoids the
        arbitrary FFT-bin scaling that previously made ordinary playback look almost
        silent to the pulse generator.
        """
        samples = np.asarray(audio_data, dtype=np.float32)
        if samples.size == 0:
            return 0.0
        finite = samples[np.isfinite(samples)]
        if finite.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(np.square(finite, dtype=np.float32), dtype=np.float32)))
        return rms if np.isfinite(rms) else 0.0

    def compute_band_energy(self, fft_magnitude: np.ndarray) -> Dict[str, float]:
        """
        Compute energy in each frequency band.

        Args:
            fft_magnitude: FFT magnitude spectrum

        Returns:
            Dictionary mapping band names to energy values
        """
        band_energies = {}

        for i, (min_f, max_f) in enumerate(self.frequency_bands):
            # Find indices in the frequency range
            band_mask = (self.filtered_freq_bins >= min_f) & (self.filtered_freq_bins <= max_f)
            band_magnitude = fft_magnitude[band_mask]

            # Compute RMS energy
            if len(band_magnitude) > 0:
                energy = np.sqrt(np.mean(band_magnitude ** 2))
            else:
                energy = 0.0

            band_names = ["sub_bass", "bass", "low_mid", "mid", "high_mid", "presence", "brilliance"]
            if i < len(band_names):
                band_energies[band_names[i]] = energy

        return band_energies

    def compute_total_energy(self, fft_magnitude: np.ndarray) -> float:
        """
        Compute total energy across all frequencies.

        Args:
            fft_magnitude: FFT magnitude spectrum

        Returns:
            Total energy value
        """
        if len(fft_magnitude) == 0:
            return 0.0

        return np.sqrt(np.mean(fft_magnitude ** 2))

    def compute_spectral_centroid(self, fft_magnitude: np.ndarray) -> float:
        """
        Compute spectral centroid (brightness indicator).

        Args:
            fft_magnitude: FFT magnitude spectrum

        Returns:
            Spectral centroid in Hz
        """
        if len(fft_magnitude) == 0 or np.sum(fft_magnitude) == 0:
            return 0.0

        # Weighted mean of frequencies
        weighted_freqs = self.filtered_freq_bins * fft_magnitude
        centroid = np.sum(weighted_freqs) / np.sum(fft_magnitude)

        return centroid

    def process_audio(self, audio_data: np.ndarray) -> Dict[str, float]:
        """
        Process audio data and extract features.

        Args:
            audio_data: Audio samples

        Returns:
            Dictionary with extracted features:
            - total_energy: Total energy across all frequencies
            - spectral_centroid: Spectral centroid in Hz
            - band_<name>: Energy in each frequency band
        """
        # Compute FFT
        fft_magnitude = self.compute_fft(audio_data)

        # Compute features
        features = {
            # total_energy is intentionally the real PCM RMS amplitude. The FFT remains
            # the source for spectral information, but its bin magnitude is no longer
            # used as the amplitude scale for the ECG.
            'total_energy': self.compute_rms(audio_data),
            'spectral_centroid': self.compute_spectral_centroid(fft_magnitude),
        }

        # Add band energies
        band_energies = self.compute_band_energy(fft_magnitude)
        features.update(band_energies)

        # Temporal features are derived from successive real PCM/FFT frames.
        # They are informational only; no beat clock or periodic trigger is created.
        previous_rms = self._previous_rms
        rms_delta = features["total_energy"] - previous_rms
        features["energy_delta"] = rms_delta

        band_order = ["sub_bass", "bass", "low_mid", "mid", "high_mid", "presence", "brilliance"]
        current_bands = np.asarray([band_energies.get(name, 0.0) for name in band_order], dtype=np.float32)
        if self._previous_band_energies is None:
            spectral_flux = 0.0
            band_motion = 0.0
            centroid_motion = 0.0
        else:
            rises = np.maximum(current_bands - self._previous_band_energies, 0.0)
            spectral_flux = float(np.sum(rises) / max(float(np.sum(current_bands)), 1e-8))
            spectral_flux = min(max(spectral_flux, 0.0), 1.0)

            # Unlike one-sided flux, band_motion also catches real spectral falls
            # and texture changes (vocal consonants, chord changes, synth movement,
            # cymbals, guitar/piano attacks, etc.). It remains derived entirely from
            # consecutive FFT frames.
            band_difference = float(np.sum(np.abs(current_bands - self._previous_band_energies)))
            band_reference = float(np.sum(current_bands + self._previous_band_energies))
            band_motion = min(max(band_difference / max(band_reference, 1e-8), 0.0), 1.0)

            centroid_difference = abs(float(features["spectral_centroid"]) - self._previous_centroid)
            centroid_reference = max(float(features["spectral_centroid"]), self._previous_centroid, 400.0)
            centroid_motion = min(max(centroid_difference / centroid_reference, 0.0), 1.0)

        spectral_motion = min(
            max(0.60 * spectral_flux + 0.28 * band_motion + 0.12 * centroid_motion, 0.0),
            1.0,
        )
        features["spectral_flux"] = spectral_flux
        features["spectral_motion"] = spectral_motion

        self._previous_rms = float(features["total_energy"])
        self._previous_band_energies = current_bands
        self._previous_centroid = float(features["spectral_centroid"])
        return features

    def get_frequency_weights(self) -> np.ndarray:
        """
        Get frequency weights for visualization.

        Returns:
            Array of weights for each frequency bin
        """
        if self.curve == FrequencyCurve.LOGARITHMIC:
            # Logarithmic weighting (more weight to lower frequencies)
            return 1.0 / (np.log10(self.filtered_freq_bins + 1) + 1)
        else:
            # Linear weighting
            return np.ones_like(self.filtered_freq_bins)
