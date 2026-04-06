"""
VoiceMic PC Server Configuration
"""
import json
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "port": 8125,
    "sample_rate": 48000,
    "channels": 1,
    "codec": 0,  # 0=PCM, 1=Opus
    "buffer_size": 4096,
    "volume": 100,
    "noise_suppression": False,
    "auto_connect": False,
    "minimize_to_tray": True,
    "dark_theme": True,
    "output_device": "",  # empty = default
    "connection_mode": "wifi",  # wifi, usb
    "adb_port": 8125,
    "language": None,  # None = auto-detect from system
    "virtual_mic": True,  # use virtual audio driver if available
    "always_on_top": False,
}

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "VoiceMic"
CONFIG_FILE = CONFIG_DIR / "config.json"


class Config:
    def __init__(self):
        self._data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self._data.update(saved)
        except Exception:
            pass

    def save(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value
        self.save()

    @property
    def data(self):
        return dict(self._data)
