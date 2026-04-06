"""
VoiceMic Audio Player
Handles audio output to system audio devices (virtual audio cable or speakers).
"""
import threading
import queue
import numpy as np

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False


class AudioPlayer:
    """Plays received audio data through a system audio output device."""

    def __init__(self, sample_rate=48000, channels=1, frames_per_buffer=960,
                 device_name="", volume=100):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frames_per_buffer = frames_per_buffer
        self.device_name = device_name
        self.volume = volume / 100.0
        self._queue = queue.Queue(maxsize=100)
        self._running = False
        self._thread = None
        self._stream = None
        self._pa = None
        self._use_sounddevice = False
        self._level = 0.0  # current audio level 0-1

    def get_output_devices(self):
        """Return list of available output audio devices."""
        devices = []
        if HAS_PYAUDIO:
            pa = pyaudio.PyAudio()
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info["maxOutputChannels"] > 0:
                    devices.append({
                        "index": i,
                        "name": info["name"],
                        "channels": info["maxOutputChannels"],
                        "sample_rate": int(info["defaultSampleRate"]),
                    })
            pa.terminate()
        elif HAS_SOUNDDEVICE:
            for i, dev in enumerate(sd.query_devices()):
                if dev["max_output_channels"] > 0:
                    devices.append({
                        "index": i,
                        "name": dev["name"],
                        "channels": dev["max_output_channels"],
                        "sample_rate": int(dev["default_samplerate"]),
                    })
        return devices

    def _find_device_index(self):
        """Find device index by name."""
        if not self.device_name:
            return None
        devices = self.get_output_devices()
        for d in devices:
            if self.device_name.lower() in d["name"].lower():
                return d["index"]
        return None

    def start(self):
        """Start audio playback."""
        if self._running:
            return
        self._running = True

        # Clear queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        device_index = self._find_device_index()

        if HAS_PYAUDIO:
            self._use_sounddevice = False
            self._pa = pyaudio.PyAudio()
            kwargs = {
                "format": pyaudio.paInt16,
                "channels": self.channels,
                "rate": self.sample_rate,
                "output": True,
                "frames_per_buffer": self.frames_per_buffer,
                "stream_callback": self._pyaudio_callback,
            }
            if device_index is not None:
                kwargs["output_device_index"] = device_index
            try:
                self._stream = self._pa.open(**kwargs)
                self._stream.start_stream()
                return
            except Exception as e:
                print(f"PyAudio failed: {e}, trying sounddevice...")
                self._pa.terminate()
                self._pa = None

        if HAS_SOUNDDEVICE:
            self._use_sounddevice = True
            self._thread = threading.Thread(target=self._sd_playback_loop, daemon=True)
            self._thread.start()
            return

        print("ERROR: No audio backend available. Install pyaudio or sounddevice.")
        self._running = False

    def _pyaudio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio stream callback."""
        import pyaudio as pa
        try:
            data = self._queue.get_nowait()
            # Apply volume
            if self.volume != 1.0:
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                samples *= self.volume
                np.clip(samples, -32768, 32767, out=samples)
                # Calculate level
                self._level = min(1.0, np.abs(samples).mean() / 16384.0)
                data = samples.astype(np.int16).tobytes()
            else:
                samples = np.frombuffer(data, dtype=np.int16)
                self._level = min(1.0, np.abs(samples.astype(np.float32)).mean() / 16384.0)

            # Pad or truncate to match frame_count
            needed = frame_count * self.channels * 2
            if len(data) < needed:
                data += b'\x00' * (needed - len(data))
            elif len(data) > needed:
                data = data[:needed]

            return (data, pa.paContinue)
        except queue.Empty:
            self._level = 0.0
            return (b'\x00' * frame_count * self.channels * 2, pa.paContinue)

    def _sd_playback_loop(self):
        """Sounddevice playback loop."""
        device_index = self._find_device_index()
        try:
            with sd.OutputStream(samplerate=self.sample_rate, channels=self.channels,
                                 dtype='int16', blocksize=self.frames_per_buffer,
                                 device=device_index) as stream:
                while self._running:
                    try:
                        data = self._queue.get(timeout=0.1)
                        samples = np.frombuffer(data, dtype=np.int16)
                        if self.volume != 1.0:
                            float_samples = samples.astype(np.float32) * self.volume
                            np.clip(float_samples, -32768, 32767, out=float_samples)
                            self._level = min(1.0, np.abs(float_samples).mean() / 16384.0)
                            samples = float_samples.astype(np.int16)
                        else:
                            self._level = min(1.0, np.abs(samples.astype(np.float32)).mean() / 16384.0)

                        if self.channels == 1:
                            samples = samples.reshape(-1, 1)
                        stream.write(samples)
                    except queue.Empty:
                        self._level = 0.0
                        continue
        except Exception as e:
            print(f"Sounddevice error: {e}")
        finally:
            self._running = False

    def stop(self):
        """Stop audio playback."""
        self._running = False
        self._level = 0.0
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def feed(self, audio_data: bytes):
        """Feed audio data into the playback queue."""
        if not self._running:
            return
        try:
            self._queue.put_nowait(audio_data)
        except queue.Full:
            # Drop oldest frame to avoid latency buildup
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(audio_data)
            except queue.Empty:
                pass

    def set_volume(self, volume: int):
        """Set volume (0-200)."""
        self.volume = max(0, min(200, volume)) / 100.0

    @property
    def level(self):
        """Current audio level 0.0-1.0."""
        return self._level

    @property
    def is_playing(self):
        return self._running
