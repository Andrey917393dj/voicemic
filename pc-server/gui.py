"""
VoiceMic Client
Classic Windows-style VoiceMic PC client interface.
Menu bar: Connection, Options. Status bar. Connect/Advanced dialogs.
"""
import tkinter as tk
from tkinter import messagebox
import threading
import time
import socket
import struct
import logging
import os
import sys

from config import Config
from server import AudioClient
from audio_player import AudioPlayer
from audio_bridge import AudioBridge
from tray_icon import TrayManager

log = logging.getLogger("VoiceMic")

APP_VERSION = "1.0.0"
TRANSPORT_WIFI = "wifi"
TRANSPORT_USB = "usb"
TRANSPORT_BLUETOOTH = "bluetooth"
TRANSPORT_WIFI_DIRECT = "wifi_direct"

TRANSPORT_LABELS = {
    TRANSPORT_WIFI: "Wi-Fi",
    TRANSPORT_USB: "USB",
    TRANSPORT_BLUETOOTH: "Bluetooth",
    TRANSPORT_WIFI_DIRECT: "Wi-Fi Direct",
}


def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ═══════════════════════════════════════
# Connect Dialog
# ═══════════════════════════════════════

class ConnectDialog(tk.Toplevel):
    """Connection dialog — select transport and enter parameters."""

    def __init__(self, parent, config):
        super().__init__(parent)
        self.title("Connect")
        self.resizable(False, False)
        self.config = config
        self.result = None  # will hold dict on OK

        self.transient(parent)
        self.grab_set()

        # ── Transport type ──
        tf = tk.LabelFrame(self, text="Transport type", padx=10, pady=8)
        tf.pack(fill="x", padx=12, pady=(12, 6))

        self.transport_var = tk.StringVar(value=config["transport"])
        for val, label in TRANSPORT_LABELS.items():
            tk.Radiobutton(
                tf, text=label, variable=self.transport_var,
                value=val, command=self._on_transport_changed,
            ).pack(anchor="w")

        # ── Parameters frame ──
        pf = tk.LabelFrame(self, text="Parameters", padx=10, pady=8)
        pf.pack(fill="x", padx=12, pady=(6, 6))

        # IP Address row
        self.ip_frame = tk.Frame(pf)
        self.ip_frame.pack(fill="x", pady=2)
        tk.Label(self.ip_frame, text="Phone IP Address:").pack(side="left")
        self.ip_entry = tk.Entry(self.ip_frame, width=20)
        self.ip_entry.insert(0, config.get("last_ip", ""))
        self.ip_entry.pack(side="right")

        # Bluetooth device row
        self.bt_frame = tk.Frame(pf)
        self.bt_frame.pack(fill="x", pady=2)
        tk.Label(self.bt_frame, text="Bluetooth device:").pack(side="left")
        self.bt_var = tk.StringVar(value=config.get("last_bt_device", ""))
        self.bt_combo = tk.OptionMenu(self.bt_frame, self.bt_var, "")
        self.bt_combo.pack(side="right")

        # ── Buttons ──
        bf = tk.Frame(self)
        bf.pack(fill="x", padx=12, pady=(6, 12))
        tk.Button(bf, text="Connect", width=10, command=self._on_connect).pack(side="left", padx=(0, 6))
        tk.Button(bf, text="Cancel", width=10, command=self.destroy).pack(side="left")

        self._on_transport_changed()
        self.geometry(f"+{parent.winfo_rootx()+60}+{parent.winfo_rooty()+60}")
        self.ip_entry.focus_set()
        self.bind("<Return>", lambda e: self._on_connect())
        self.bind("<Escape>", lambda e: self.destroy())

    def _on_transport_changed(self):
        t = self.transport_var.get()
        if t in (TRANSPORT_WIFI, TRANSPORT_WIFI_DIRECT):
            self.ip_frame.pack(fill="x", pady=2)
            self.bt_frame.pack_forget()
        elif t == TRANSPORT_BLUETOOTH:
            self.ip_frame.pack_forget()
            self.bt_frame.pack(fill="x", pady=2)
        elif t == TRANSPORT_USB:
            self.ip_frame.pack_forget()
            self.bt_frame.pack_forget()

    def _on_connect(self):
        t = self.transport_var.get()
        ip = self.ip_entry.get().strip()
        if t in (TRANSPORT_WIFI, TRANSPORT_WIFI_DIRECT) and not ip:
            messagebox.showwarning("Warning", "Please enter phone IP address.", parent=self)
            return
        self.result = {
            "transport": t,
            "ip": ip if t != TRANSPORT_USB else "127.0.0.1",
            "bt_device": self.bt_var.get(),
        }
        self.destroy()


# ═══════════════════════════════════════
# Advanced Dialog
# ═══════════════════════════════════════

class AdvancedDialog(tk.Toplevel):
    """Advanced settings — ports and debug mode."""

    def __init__(self, parent, config):
        super().__init__(parent)
        self.title("Advanced")
        self.resizable(False, False)
        self.config = config
        self.result = None

        self.transient(parent)
        self.grab_set()

        f = tk.Frame(self, padx=12, pady=12)
        f.pack()

        # Control port
        row1 = tk.Frame(f)
        row1.pack(fill="x", pady=3)
        tk.Label(row1, text="Control port:", width=14, anchor="w").pack(side="left")
        self.ctrl_port = tk.Entry(row1, width=10)
        self.ctrl_port.insert(0, str(config["control_port"]))
        self.ctrl_port.pack(side="left")

        # Media port
        row2 = tk.Frame(f)
        row2.pack(fill="x", pady=3)
        tk.Label(row2, text="Media port:", width=14, anchor="w").pack(side="left")
        self.media_port = tk.Entry(row2, width=10)
        self.media_port.insert(0, str(config["media_port"]))
        self.media_port.pack(side="left")

        # Debug mode
        self.debug_var = tk.BooleanVar(value=config.get("debug_mode", False))
        tk.Checkbutton(f, text="Enable debug mode", variable=self.debug_var).pack(anchor="w", pady=(8, 4))

        # Buttons
        bf = tk.Frame(f)
        bf.pack(fill="x", pady=(8, 0))
        tk.Button(bf, text="OK", width=8, command=self._on_ok).pack(side="left", padx=(0, 6))
        tk.Button(bf, text="Cancel", width=8, command=self.destroy).pack(side="left")

        self.geometry(f"+{parent.winfo_rootx()+80}+{parent.winfo_rooty()+80}")
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())

    def _on_ok(self):
        try:
            cp = int(self.ctrl_port.get())
            mp = int(self.media_port.get())
        except ValueError:
            messagebox.showwarning("Warning", "Ports must be numbers.", parent=self)
            return
        self.result = {
            "control_port": cp,
            "media_port": mp,
            "debug_mode": self.debug_var.get(),
        }
        self.destroy()


# ═══════════════════════════════════════
# Main Application
# ═══════════════════════════════════════

class VoiceMicApp(tk.Tk):
    """Classic VoiceMic client window."""

    def __init__(self):
        super().__init__()

        self.config = Config()

        self.title("VoiceMic Client")
        self.geometry("420x200")
        self.resizable(True, True)
        self.minsize(360, 160)

        # ── Core components ──
        self.client = AudioClient(port=self.config["control_port"])
        self.player = AudioPlayer(
            sample_rate=self.config["sample_rate"],
            channels=self.config["channels"],
            volume=self.config["volume"],
        )
        self.tray = TrayManager()
        self.audio_bridge = AudioBridge()
        self._bridge_active = False
        self._connected = False
        self._client_device = ""
        self._auto_reconnect_info = None
        self._flash_timer = None

        # ── Server callbacks ──
        self.client.on_audio = self._on_audio
        self.client.on_client_connected = self._on_connected
        self.client.on_client_disconnected = self._on_disconnected
        self.client.on_error = self._on_error
        self.client.on_status = self._on_status
        self.client.on_latency_update = self._on_latency

        # ── Tray callbacks ──
        self.tray.on_show = self._show_window
        self.tray.on_quit = self._quit_app
        self.tray.start()

        # ── Build UI ──
        self._build_menu()
        self._build_main_area()
        self._build_status_bar()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Open audio bridge to virtual driver
        self._try_open_bridge()

    # ────────────────────────────────────
    # Menu Bar
    # ────────────────────────────────────

    def _build_menu(self):
        menubar = tk.Menu(self)

        # Connection menu
        self.conn_menu = tk.Menu(menubar, tearoff=0)
        self.conn_menu.add_command(label="Connect...", command=self._show_connect_dialog)
        self.conn_menu.add_command(label="Disconnect", command=self._do_disconnect, state="disabled")
        menubar.add_cascade(label="Connection", menu=self.conn_menu)

        # Options menu
        self.opt_menu = tk.Menu(menubar, tearoff=0)

        self._play_speaker_var = tk.BooleanVar(value=self.config["play_in_speaker"])
        self.opt_menu.add_checkbutton(
            label="Play in speaker", variable=self._play_speaker_var,
            command=self._on_play_speaker_toggle,
        )

        # When aborting submenu
        abort_menu = tk.Menu(self.opt_menu, tearoff=0)
        self._auto_reconnect_var = tk.BooleanVar(value=self.config["auto_reconnect"])
        abort_menu.add_checkbutton(
            label="Auto reconnect", variable=self._auto_reconnect_var,
            command=lambda: self.config.set("auto_reconnect", self._auto_reconnect_var.get()),
        )
        self._flash_window_var = tk.BooleanVar(value=self.config["flash_window"])
        abort_menu.add_checkbutton(
            label="Flash window", variable=self._flash_window_var,
            command=lambda: self.config.set("flash_window", self._flash_window_var.get()),
        )
        self.opt_menu.add_cascade(label="When aborting", menu=abort_menu)

        self.opt_menu.add_separator()
        self.opt_menu.add_command(label="Advanced...", command=self._show_advanced_dialog)

        menubar.add_cascade(label="Options", menu=self.opt_menu)

        self.configure(menu=menubar)

    # ────────────────────────────────────
    # Main Content Area
    # ────────────────────────────────────

    def _build_main_area(self):
        self.main_frame = tk.Frame(self, bg="white")
        self.main_frame.pack(fill="both", expand=True)

        # Center info label
        self.info_label = tk.Label(
            self.main_frame, text="Disconnected",
            font=("Segoe UI", 14), bg="white", fg="#333333",
        )
        self.info_label.pack(expand=True)

    # ────────────────────────────────────
    # Status Bar
    # ────────────────────────────────────

    def _build_status_bar(self):
        self.status_bar = tk.Label(
            self, text="Disconnected", bd=1, relief="sunken",
            anchor="w", padx=6, font=("Segoe UI", 9),
        )
        self.status_bar.pack(side="bottom", fill="x")

    # ────────────────────────────────────
    # Connect Dialog
    # ────────────────────────────────────

    def _show_connect_dialog(self):
        if self._connected:
            messagebox.showinfo("Info", "Already connected. Disconnect first.", parent=self)
            return
        dlg = ConnectDialog(self, self.config)
        self.wait_window(dlg)
        if dlg.result:
            self._do_connect(dlg.result)

    def _do_connect(self, params):
        transport = params["transport"]
        ip = params["ip"]

        # Save last used values
        self.config.set("transport", transport)
        if ip:
            self.config.set("last_ip", ip)

        self._set_status(f"Connecting to {ip}...")
        self.info_label.configure(text=f"Connecting to {ip}...")

        # Store for auto-reconnect
        self._auto_reconnect_info = params

        # Connect to phone server
        self.client.connect(ip, self.config["control_port"])

    def _do_disconnect(self):
        self._auto_reconnect_info = None
        self.client.stop()
        self.player.stop()
        self._connected = False
        self._client_device = ""
        self.conn_menu.entryconfigure("Connect...", state="normal")
        self.conn_menu.entryconfigure("Disconnect", state="disabled")
        self.info_label.configure(text="Disconnected")
        self._set_status("Disconnected")
        self.tray.set_connected(False)

    # ────────────────────────────────────
    # Advanced Dialog
    # ────────────────────────────────────

    def _show_advanced_dialog(self):
        dlg = AdvancedDialog(self, self.config)
        self.wait_window(dlg)
        if dlg.result:
            self.config.set("control_port", dlg.result["control_port"])
            self.config.set("media_port", dlg.result["media_port"])
            self.config.set("debug_mode", dlg.result["debug_mode"])
            if dlg.result["debug_mode"]:
                logging.basicConfig(level=logging.DEBUG)

    # ────────────────────────────────────
    # Audio Bridge
    # ────────────────────────────────────

    def _try_open_bridge(self):
        ok = self.audio_bridge.open(
            sample_rate=self.config["sample_rate"],
            channels=self.config["channels"],
        )
        self._bridge_active = ok
        if ok:
            log.info("Virtual mic driver active")

    # ────────────────────────────────────
    # Server Callbacks
    # ────────────────────────────────────

    def _on_audio(self, data: bytes):
        # Write to virtual driver
        if self._bridge_active:
            self.audio_bridge.write(data)
        # Play in speaker if enabled
        if self._play_speaker_var.get():
            self.player.feed(data)

    def _on_connected(self, client_info):
        self._connected = True
        self._client_device = client_info.device_name
        self.player.sample_rate = client_info.sample_rate
        self.player.channels = client_info.channels
        if self._bridge_active:
            self.audio_bridge.set_format(client_info.sample_rate, client_info.channels)
        if self._play_speaker_var.get():
            self.player.start()
        self.after(0, self._update_ui_connected, client_info)

    def _on_disconnected(self):
        was_connected = self._connected
        self._connected = False
        self._client_device = ""
        self.player.stop()
        self.after(0, self._update_ui_disconnected)

        # Flash window if enabled
        if was_connected and self._flash_window_var.get():
            self._flash()

        # Auto reconnect if enabled
        if was_connected and self._auto_reconnect_var.get() and self._auto_reconnect_info:
            self.after(2000, lambda: self._do_connect(self._auto_reconnect_info))

    def _on_error(self, msg: str):
        log.error(msg)
        self.after(0, lambda: self._set_status(f"Error: {msg}"))

    def _on_status(self, msg: str):
        log.info(msg)
        self.after(0, lambda: self._set_status(msg))

    def _on_latency(self, ms: int):
        if self._connected:
            self.after(0, lambda: self._set_status(f"Connected  |  Latency: {ms} ms"))

    # ────────────────────────────────────
    # UI Updates
    # ────────────────────────────────────

    def _update_ui_connected(self, client_info):
        self.conn_menu.entryconfigure("Connect...", state="disabled")
        self.conn_menu.entryconfigure("Disconnect", state="normal")
        text = f"Connected: {client_info.device_name}\n{client_info.addr[0]}"
        self.info_label.configure(text=text, fg="#006600")
        self._set_status(f"Connected to {client_info.device_name}")
        self.tray.set_connected(True, client_info.device_name)

    def _update_ui_disconnected(self):
        self.conn_menu.entryconfigure("Connect...", state="normal")
        self.conn_menu.entryconfigure("Disconnect", state="disabled")
        self.info_label.configure(text="Disconnected", fg="#333333")
        self._set_status("Disconnected")
        self.tray.set_connected(False)

    def _set_status(self, text: str):
        self.status_bar.configure(text=text)

    def _flash(self):
        """Flash the window in taskbar to alert user."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            my_hwnd = self.winfo_id()
            if hwnd != my_hwnd:
                ctypes.windll.user32.FlashWindow(my_hwnd, True)
        except Exception:
            self.bell()

    def _on_play_speaker_toggle(self):
        enabled = self._play_speaker_var.get()
        self.config.set("play_in_speaker", enabled)
        if enabled and self._connected:
            self.player.start()
        elif not enabled:
            self.player.stop()

    # ────────────────────────────────────
    # Window Management
    # ────────────────────────────────────

    def _show_window(self):
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def _on_close(self):
        self._quit_app()

    def _quit_app(self):
        self.client.stop()
        self.player.stop()
        self.audio_bridge.close()
        self.tray.stop()
        self.config.save()
        self.destroy()


def run():
    app = VoiceMicApp()
    app.mainloop()
