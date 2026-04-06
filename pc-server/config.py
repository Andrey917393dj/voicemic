"""
VoiceMic PC Server Configuration
"""
import json
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "control_port": 8125,
    "media_port": 8126,
    "transport": "wifi",        # wifi, usb, bluetooth, wifi_direct
    "last_ip": "",              # last used phone IP
    "last_bt_device": "",       # last used bluetooth device
    "sample_rate": 48000,
    "channels": 1,
    "buffer_size": 4096,
    "play_in_speaker": False,   # Options -> Play in speaker
    "auto_reconnect": False,    # Options -> When aborting -> Auto reconnect
    "flash_window": False,      # Options -> When aborting -> Flash window
    "debug_mode": False,        # Options -> Advanced -> Enable debug mode
    "volume": 100,
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
