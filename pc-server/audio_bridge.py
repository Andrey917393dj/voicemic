"""
VoiceMic Audio Bridge
Writes received audio into a shared memory ring buffer that the
VoiceMic virtual audio driver reads from. This makes the audio
appear as a standard Windows microphone input device.

Falls back to regular audio playback if the driver is not installed.
"""
import ctypes
import ctypes.wintypes
import struct
import logging

log = logging.getLogger("VoiceMic.AudioBridge")

# Windows API constants
FILE_MAP_ALL_ACCESS = 0x000F001F
PAGE_READWRITE = 0x04
INVALID_HANDLE_VALUE = ctypes.wintypes.HANDLE(-1)
EVENT_MODIFY_STATE = 0x0002

# Shared memory layout matches driver's VOICEMIC_RING_BUFFER
RING_HEADER_SIZE = 64
RING_BUFFER_SIZE = 48000 * 2 * 2  # 1 sec stereo 16-bit
SHARED_MEM_NAME = "VoiceMicAudioBuffer"
EVENT_NAME = "VoiceMicAudioEvent"

# Header offsets (all LONG = 4 bytes)
OFF_WRITE_OFFSET = 0
OFF_READ_OFFSET = 4
OFF_SAMPLE_RATE = 8
OFF_CHANNELS = 12
OFF_BITS_PER_SAMPLE = 16
OFF_ACTIVE = 20
OFF_BUFFER_SIZE = 24


class AudioBridge:
    """Writes audio to shared memory for the VoiceMic virtual audio driver."""

    def __init__(self):
        self._handle = None
        self._view = None
        self._event = None
        self._available = False
        self._sample_rate = 48000
        self._channels = 1

    @property
    def available(self) -> bool:
        return self._available

    def open(self, sample_rate: int = 48000, channels: int = 1) -> bool:
        """Create/open shared memory section. Returns True on success."""
        self._sample_rate = sample_rate
        self._channels = channels

        try:
            kernel32 = ctypes.windll.kernel32

            # Create file mapping (shared memory)
            total_size = RING_HEADER_SIZE + RING_BUFFER_SIZE
            self._handle = kernel32.CreateFileMappingW(
                INVALID_HANDLE_VALUE,
                None,
                PAGE_READWRITE,
                0,
                total_size,
                SHARED_MEM_NAME,
            )
            if not self._handle:
                log.warning("Failed to create shared memory: %d", kernel32.GetLastError())
                return False

            # Map view
            self._view = kernel32.MapViewOfFile(
                self._handle,
                FILE_MAP_ALL_ACCESS,
                0, 0, total_size,
            )
            if not self._view:
                log.warning("Failed to map view: %d", kernel32.GetLastError())
                kernel32.CloseHandle(self._handle)
                self._handle = None
                return False

            # Create event for signaling
            self._event = kernel32.CreateEventW(None, False, False, EVENT_NAME)

            # Initialize header
            self._write_long(OFF_WRITE_OFFSET, 0)
            self._write_long(OFF_READ_OFFSET, 0)
            self._write_long(OFF_SAMPLE_RATE, sample_rate)
            self._write_long(OFF_CHANNELS, channels)
            self._write_long(OFF_BITS_PER_SAMPLE, 16)
            self._write_long(OFF_ACTIVE, 1)
            self._write_long(OFF_BUFFER_SIZE, RING_BUFFER_SIZE)

            self._available = True
            log.info("Audio bridge opened: %dHz %dch", sample_rate, channels)
            return True

        except Exception as e:
            log.error("AudioBridge open failed: %s", e)
            return False

    def write(self, pcm_data: bytes):
        """Write PCM audio data to the ring buffer."""
        if not self._available or not self._view:
            return

        data_len = len(pcm_data)
        if data_len == 0:
            return

        write_off = self._read_long(OFF_WRITE_OFFSET)
        buf_size = RING_BUFFER_SIZE

        # Write data to ring buffer (handle wrap-around)
        data_start = RING_HEADER_SIZE
        offset = write_off % buf_size

        first_chunk = min(data_len, buf_size - offset)
        ctypes.memmove(self._view + data_start + offset, pcm_data[:first_chunk], first_chunk)

        if data_len > first_chunk:
            remainder = data_len - first_chunk
            ctypes.memmove(self._view + data_start, pcm_data[first_chunk:], remainder)

        # Update write offset
        new_write = (write_off + data_len) % buf_size
        self._write_long(OFF_WRITE_OFFSET, new_write)

        # Signal event
        if self._event:
            ctypes.windll.kernel32.SetEvent(self._event)

    def set_format(self, sample_rate: int, channels: int):
        """Update audio format in shared memory header."""
        if not self._available:
            return
        self._sample_rate = sample_rate
        self._channels = channels
        self._write_long(OFF_SAMPLE_RATE, sample_rate)
        self._write_long(OFF_CHANNELS, channels)

    def close(self):
        """Release shared memory and event."""
        if self._view:
            self._write_long(OFF_ACTIVE, 0)
            ctypes.windll.kernel32.UnmapViewOfFile(self._view)
            self._view = None
        if self._handle:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
        if self._event:
            ctypes.windll.kernel32.CloseHandle(self._event)
            self._event = None
        self._available = False
        log.info("Audio bridge closed")

    def _write_long(self, offset: int, value: int):
        """Write a 32-bit int to shared memory at offset."""
        ctypes.memmove(self._view + offset, struct.pack('<i', value), 4)

    def _read_long(self, offset: int) -> int:
        """Read a 32-bit int from shared memory at offset."""
        buf = (ctypes.c_char * 4)()
        ctypes.memmove(buf, self._view + offset, 4)
        return struct.unpack('<i', bytes(buf))[0]

    def __del__(self):
        self.close()
