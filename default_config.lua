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
        -- Attack/release envelope for changes in real playback energy.
        attack = 0.02,
        decay = 0.18,
        height = 1.5,
        threshold = 0.00398107,
        -- Extra response to real spectral/energy changes (not a beat timer).
        transient_gain = 1.8,
        -- Weight low-frequency/sub-bass/bass energy in ECG event intensity.
        -- It does not create events by itself.
        bass_weight = 0.35,
        -- Retained for configuration compatibility; ECG events are no longer
        -- gated by a threshold or scheduled by a pulse clock.
        event_threshold = 0.45,
        -- Negative excursion as a fraction of the positive peak.
        overshoot_ratio = 0.38,
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
