"""
VoiceMic Software Noise Suppression
Simple spectral gating noise filter for PCM audio.
"""
import numpy as np


class NoiseFilter:
    """Simple noise gate + spectral subtraction filter."""

    def __init__(self, sample_rate=48000, channels=1, gate_threshold_db=-40.0):
        self.sample_rate = sample_rate
        self.channels = channels
        self.gate_threshold = 10 ** (gate_threshold_db / 20.0) * 32768
        self.enabled = False

        # Noise profile (running average of noise floor)
        self._noise_floor = None
        self._alpha = 0.02  # smoothing factor for noise estimation
        self._frame_count = 0
        self._calibration_frames = 20  # first N frames used to estimate noise

    def enable(self, enabled: bool):
        self.enabled = enabled
        if enabled:
            self._noise_floor = None
            self._frame_count = 0

    def process(self, pcm_bytes: bytes) -> bytes:
        """Process a PCM16 audio frame. Returns filtered PCM16 bytes."""
        if not self.enabled:
            return pcm_bytes

        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)

        if len(samples) == 0:
            return pcm_bytes

        # Simple noise gate
        rms = np.sqrt(np.mean(samples ** 2))

        # Build noise profile from quiet frames
        self._frame_count += 1
        if self._noise_floor is None:
            self._noise_floor = rms
        elif self._frame_count <= self._calibration_frames:
            self._noise_floor = self._noise_floor * 0.8 + rms * 0.2
        else:
            # Only update noise floor when signal is quiet
            if rms < self._noise_floor * 2.0:
                self._noise_floor = self._noise_floor * (1 - self._alpha) + rms * self._alpha

        # Noise gate: suppress if below threshold
        gate_level = max(self.gate_threshold, self._noise_floor * 1.5)
        if rms < gate_level:
            # Soft mute — fade to near-zero
            samples *= 0.05
        else:
            # Spectral subtraction (simplified)
            if len(samples) >= 256:
                fft = np.fft.rfft(samples)
                magnitude = np.abs(fft)
                phase = np.angle(fft)

                # Estimate noise magnitude from noise floor ratio
                noise_mag = magnitude * min(1.0, (self._noise_floor / (rms + 1e-10)))
                clean_mag = np.maximum(magnitude - noise_mag * 0.7, magnitude * 0.1)

                fft_clean = clean_mag * np.exp(1j * phase)
                samples = np.fft.irfft(fft_clean, n=len(samples))

        np.clip(samples, -32768, 32767, out=samples)
        return samples.astype(np.int16).tobytes()
