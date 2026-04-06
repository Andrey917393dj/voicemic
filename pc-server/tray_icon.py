"""
VoiceMic System Tray Icon
"""
import threading
from typing import Callable, Optional

try:
    from pystray import Icon, Menu, MenuItem
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


def create_mic_icon(color="green", size=64):
    """Create a microphone icon image."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    colors = {
        "green": (76, 175, 80),
        "red": (244, 67, 54),
        "gray": (158, 158, 158),
        "blue": (33, 150, 243),
    }
    c = colors.get(color, colors["gray"])

    # Mic body
    cx, cy = size // 2, size // 2 - 4
    rw, rh = size // 6, size // 4
    draw.rounded_rectangle(
        [cx - rw, cy - rh, cx + rw, cy + rh],
        radius=rw,
        fill=c,
    )

    # Mic arc
    arc_y = cy + rh - 4
    arc_r = rw + 6
    draw.arc(
        [cx - arc_r, arc_y - arc_r, cx + arc_r, arc_y + arc_r],
        start=0, end=180,
        fill=c, width=3,
    )

    # Mic stand
    stand_top = arc_y + arc_r
    stand_bottom = stand_top + 8
    draw.line([cx, stand_top, cx, stand_bottom], fill=c, width=3)
    draw.line([cx - 8, stand_bottom, cx + 8, stand_bottom], fill=c, width=3)

    return img


class TrayManager:
    """Manages system tray icon."""

    def __init__(self):
        self._icon: Optional[Icon] = None
        self._thread: Optional[threading.Thread] = None
        self.on_show: Optional[Callable] = None
        self.on_quit: Optional[Callable] = None
        self._connected = False

    def start(self):
        if not HAS_TRAY:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        menu = Menu(
            MenuItem("Show", self._on_show, default=True),
            MenuItem("Quit", self._on_quit),
        )
        self._icon = Icon(
            "VoiceMic",
            icon=create_mic_icon("gray"),
            title="VoiceMic - Disconnected",
            menu=menu,
        )
        self._icon.run()

    def _on_show(self, icon, item):
        if self.on_show:
            self.on_show()

    def _on_quit(self, icon, item):
        if self.on_quit:
            self.on_quit()
        self.stop()

    def set_connected(self, connected: bool, device_name: str = ""):
        self._connected = connected
        if self._icon:
            if connected:
                self._icon.icon = create_mic_icon("green")
                self._icon.title = f"VoiceMic - {device_name}"
            else:
                self._icon.icon = create_mic_icon("gray")
                self._icon.title = "VoiceMic - Disconnected"

    def stop(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    @property
    def available(self):
        return HAS_TRAY
