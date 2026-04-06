"""
VoiceMic Opus Decoder
Decodes Opus-encoded audio frames back to PCM on the PC side.
Uses opuslib if available, otherwise falls back to treating data as raw PCM.
"""
import struct

try:
    import opuslib
    HAS_OPUSLIB = True
except ImportError:
    HAS_OPUSLIB = False

try:
    import ctypes
    import ctypes.util
    _opus_lib = ctypes.util.find_library("opus")
    HAS_OPUS_NATIVE = _opus_lib is not None
except Exception:
    HAS_OPUS_NATIVE = False


class OpusDecoder:
    """Opus audio decoder with fallback."""

    def __init__(self, sample_rate=48000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._decoder = None
        self._available = False
        self._init_decoder()

    def _init_decoder(self):
        """Try to initialize Opus decoder."""
        if HAS_OPUSLIB:
            try:
                self._decoder = opuslib.Decoder(self.sample_rate, self.channels)
                self._available = True
                return
            except Exception as e:
                print(f"opuslib decoder init failed: {e}")

        self._available = False

    @property
    def available(self):
        return self._available

    def decode(self, opus_data: bytes) -> bytes:
        """
        Decode Opus data to PCM16.
        If Opus is not available, returns the data as-is (assumes PCM fallback).
        """
        if not self._available or self._decoder is None:
            return opus_data

        try:
            # opuslib decode returns PCM bytes
            frame_size = self.sample_rate // 50  # 20ms
            pcm = self._decoder.decode(opus_data, frame_size)
            return pcm
        except Exception:
            # If decoding fails, return raw data (might be PCM anyway)
            return opus_data

    def reset(self):
        """Reset decoder state."""
        if self._available:
            self._init_decoder()

    def close(self):
        """Release decoder resources."""
        self._decoder = None
        self._available = False
