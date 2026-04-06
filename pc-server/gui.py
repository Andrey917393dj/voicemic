"""
VoiceMic PC Server GUI
Modern dark-themed interface using customtkinter with i18n,
virtual audio driver bridge, and noise suppression.
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import threading
import time
import sys

import i18n
from config import Config
from server import AudioServer
from audio_player import AudioPlayer
from audio_bridge import AudioBridge
from tray_icon import TrayManager
from noise_filter import NoiseFilter
from opus_decoder import OpusDecoder
from protocol import CODEC_PCM, CODEC_OPUS, SAMPLE_RATES, DEFAULT_PORT

APP_VERSION = "1.0.0"

# ── Color Palette ──
C_ACCENT       = "#6C5CE7"
C_ACCENT_HOVER = "#5A4BD1"
C_GREEN        = "#00B894"
C_GREEN_HOVER  = "#00A381"
C_RED          = "#FF6B6B"
C_RED_HOVER    = "#EE5A5A"
C_ORANGE       = "#FDCB6E"
C_TEXT_MUTED   = "#A0A0A0"
C_CARD_DARK    = "#1E1E2E"
C_CARD_LIGHT   = "#F0F0F5"


class VoiceMicApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.config = Config()

        # ── i18n ──
        i18n.init(self.config.get("language"))

        # ── Theme ──
        ctk.set_appearance_mode("dark" if self.config["dark_theme"] else "light")
        ctk.set_default_color_theme("blue")

        self.title(i18n.t("app_title"))
        self.geometry("560x760")
        self.minsize(500, 680)
        self.resizable(True, True)

        # ── Server and audio ──
        self.server = AudioServer(port=self.config["port"])
        self.player = AudioPlayer(
            sample_rate=self.config["sample_rate"],
            channels=self.config["channels"],
            volume=self.config["volume"],
            device_name=self.config["output_device"],
        )
        self.tray = TrayManager()
        self.noise_filter = NoiseFilter(
            sample_rate=self.config["sample_rate"],
            channels=self.config["channels"],
        )
        self.noise_filter.enable(self.config["noise_suppression"])
        self.opus_decoder = None

        # ── Audio bridge (virtual mic driver) ──
        self.audio_bridge = AudioBridge()
        self._bridge_active = False
        if self.config.get("virtual_mic", True):
            self._try_open_bridge()

        # ── State ──
        self._latency = 0
        self._connected = False
        self._level_after_id = None

        # ── Callbacks ──
        self.server.on_audio = self._on_audio
        self.server.on_client_connected = self._on_connected
        self.server.on_client_disconnected = self._on_disconnected
        self.server.on_error = self._on_error
        self.server.on_status = self._on_status
        self.server.on_latency_update = self._on_latency

        self.tray.on_show = self._show_window
        self.tray.on_quit = self._quit_app

        # Build UI
        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if self.config["minimize_to_tray"] and self.tray.available:
            self.tray.start()

        self._start_server()

    # ══════════════════════════════════════════
    # UI Construction
    # ══════════════════════════════════════════

    def _build_ui(self):
        # Scrollable main frame for smaller screens
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=0, pady=0)

        main = ctk.CTkFrame(self._scroll, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=18, pady=14)

        self._build_header(main)
        self._build_status_card(main)
        self._build_audio_card(main)
        self._build_volume_card(main)
        self._build_settings_card(main)
        self._build_buttons(main)
        self._build_log_card(main)

    def _build_header(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header, text="  VoiceMic",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(side="left")

        # Theme toggle
        self.theme_btn = ctk.CTkButton(
            header, text="☀" if self.config["dark_theme"] else "☾",
            width=34, height=34, corner_radius=17,
            command=self._toggle_theme,
            fg_color="transparent", hover_color=("gray80", "gray30"),
            font=ctk.CTkFont(size=16),
        )
        self.theme_btn.pack(side="right", padx=(4, 0))

        # Language selector
        langs = i18n.available_languages()
        lang_names = list(langs.values())
        lang_codes = list(langs.keys())
        current_idx = lang_codes.index(i18n.current_language()) if i18n.current_language() in lang_codes else 0

        self._lang_codes = lang_codes
        self.lang_combo = ctk.CTkComboBox(
            header, values=lang_names, width=110,
            command=self._on_language_change,
            font=ctk.CTkFont(size=12),
        )
        self.lang_combo.set(lang_names[current_idx])
        self.lang_combo.pack(side="right", padx=(4, 4))

    def _build_status_card(self, parent):
        card = self._card(parent)

        # Status row with colored indicator
        status_row = ctk.CTkFrame(card, fg_color="transparent")
        status_row.pack(fill="x", padx=16, pady=(14, 2))

        self.status_dot = ctk.CTkLabel(
            status_row, text="●",
            font=ctk.CTkFont(size=22), text_color=C_RED,
        )
        self.status_dot.pack(side="left")

        self.status_label = ctk.CTkLabel(
            status_row, text=i18n.t("status_disconnected"),
            font=ctk.CTkFont(size=17, weight="bold"),
        )
        self.status_label.pack(side="left", padx=(6, 0))

        self.info_label = ctk.CTkLabel(
            card, text=i18n.t("status_waiting"),
            font=ctk.CTkFont(size=12), text_color=C_TEXT_MUTED,
        )
        self.info_label.pack(padx=16, anchor="w")

        ip = self.server.get_local_ip()
        self.ip_label = ctk.CTkLabel(
            card,
            text=f"IP: {ip}   |   {i18n.t('label_port')}: {self.config['port']}",
            font=ctk.CTkFont(size=13, family="Consolas"),
        )
        self.ip_label.pack(padx=16, pady=(4, 2), anchor="w")

        self.latency_label = ctk.CTkLabel(
            card, text=f"{i18n.t('label_latency')}: — ms",
            font=ctk.CTkFont(size=12), text_color=C_TEXT_MUTED,
        )
        self.latency_label.pack(padx=16, pady=(0, 12), anchor="w")

    def _build_audio_card(self, parent):
        card = self._card(parent)

        ctk.CTkLabel(
            card, text=i18n.t("label_audio_level"),
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(10, 4), padx=16, anchor="w")

        bar_frame = ctk.CTkFrame(card, fg_color="transparent")
        bar_frame.pack(fill="x", padx=16, pady=(0, 10))

        self.level_bar = ctk.CTkProgressBar(
            bar_frame, height=14, corner_radius=7,
            progress_color=C_ACCENT,
        )
        self.level_bar.pack(fill="x")
        self.level_bar.set(0)

    def _build_volume_card(self, parent):
        card = self._card(parent)

        vol_header = ctk.CTkFrame(card, fg_color="transparent")
        vol_header.pack(fill="x", padx=16, pady=(10, 0))

        ctk.CTkLabel(
            vol_header, text=i18n.t("label_volume"),
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        self.vol_value_label = ctk.CTkLabel(
            vol_header, text=f"{self.config['volume']}%",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C_ACCENT,
        )
        self.vol_value_label.pack(side="right")

        self.vol_slider = ctk.CTkSlider(
            card, from_=0, to=200, number_of_steps=200,
            command=self._on_volume_change,
            progress_color=C_ACCENT, button_color=C_ACCENT,
            button_hover_color=C_ACCENT_HOVER,
        )
        self.vol_slider.set(self.config["volume"])
        self.vol_slider.pack(fill="x", padx=16, pady=(6, 12))

    def _build_settings_card(self, parent):
        card = self._card(parent)

        ctk.CTkLabel(
            card, text=i18n.t("label_settings"),
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(10, 8), padx=16, anchor="w")

        # Connection mode
        self._setting_row(card, i18n.t("label_connection_mode"), self._make_mode_widget)
        # Port
        self._setting_row(card, i18n.t("label_port"), self._make_port_widget)
        # Output device
        self._setting_row(card, i18n.t("label_output_device"), self._make_device_widget)
        # Virtual microphone
        self._setting_row(card, i18n.t("settings_virtual_mic"), self._make_vmic_widget)
        # Noise suppression
        self._setting_row(card, i18n.t("settings_noise_suppression"), self._make_ns_widget)
        # Minimize to tray
        self._setting_row(card, i18n.t("settings_minimize_tray"), self._make_tray_widget)
        # Always on top
        self._setting_row(card, i18n.t("settings_keep_on_top"), self._make_ontop_widget, last=True)

    def _build_buttons(self, parent):
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(2, 4))

        self.start_btn = ctk.CTkButton(
            btn_frame, text=i18n.t("btn_start"), height=42,
            command=self._restart_server,
            fg_color=C_GREEN, hover_color=C_GREEN_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=10,
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.disconnect_btn = ctk.CTkButton(
            btn_frame, text=i18n.t("btn_disconnect"), height=42,
            command=self._disconnect_client,
            fg_color=C_RED, hover_color=C_RED_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=10,
            state="disabled",
        )
        self.disconnect_btn.pack(side="right", expand=True, fill="x", padx=(5, 0))

    def _build_log_card(self, parent):
        card = self._card(parent, expand=True)

        ctk.CTkLabel(
            card, text=i18n.t("label_log"),
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=(8, 4), padx=16, anchor="w")

        self.log_text = ctk.CTkTextbox(
            card, height=90,
            font=ctk.CTkFont(size=11, family="Consolas"),
            state="disabled", corner_radius=8,
        )
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    # ── Setting widget factories ──

    def _make_mode_widget(self, parent):
        self.mode_var = ctk.StringVar(value=self.config["connection_mode"])
        ctk.CTkSegmentedButton(
            parent, values=["wifi", "usb"],
            variable=self.mode_var, command=self._on_mode_change,
        ).pack(side="right")

    def _make_port_widget(self, parent):
        self.port_entry = ctk.CTkEntry(parent, width=90, justify="center")
        self.port_entry.insert(0, str(self.config["port"]))
        self.port_entry.pack(side="right")

    def _make_device_widget(self, parent):
        devices = self.player.get_output_devices()
        dev_names = ["Default"] + [d["name"] for d in devices]
        current_dev = self.config["output_device"] if self.config["output_device"] else "Default"
        self.device_var = ctk.StringVar(value=current_dev)
        self.device_combo = ctk.CTkComboBox(
            parent, values=dev_names, variable=self.device_var,
            command=self._on_device_change, width=220,
        )
        self.device_combo.pack(side="right")

    def _make_vmic_widget(self, parent):
        self.vmic_var = ctk.BooleanVar(value=self.config.get("virtual_mic", True))
        ctk.CTkSwitch(
            parent, text="", variable=self.vmic_var,
            command=self._on_vmic_change,
            progress_color=C_ACCENT,
        ).pack(side="right")

    def _make_ns_widget(self, parent):
        self.ns_var = ctk.BooleanVar(value=self.config["noise_suppression"])
        ctk.CTkSwitch(
            parent, text="", variable=self.ns_var,
            command=self._on_ns_change,
            progress_color=C_ACCENT,
        ).pack(side="right")

    def _make_tray_widget(self, parent):
        self.tray_var = ctk.BooleanVar(value=self.config["minimize_to_tray"])
        ctk.CTkSwitch(
            parent, text="", variable=self.tray_var,
            command=self._on_tray_change,
            progress_color=C_ACCENT,
        ).pack(side="right")

    def _make_ontop_widget(self, parent):
        self.ontop_var = ctk.BooleanVar(value=self.config.get("always_on_top", False))
        ctk.CTkSwitch(
            parent, text="", variable=self.ontop_var,
            command=self._on_ontop_change,
            progress_color=C_ACCENT,
        ).pack(side="right")

    # ── Helpers ──

    def _card(self, parent, expand=False):
        card = ctk.CTkFrame(parent, corner_radius=14)
        card.pack(fill="both" if expand else "x", expand=expand, pady=(0, 10))
        return card

    def _setting_row(self, parent, label_text, widget_factory, last=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 10 if last else 3))
        ctk.CTkLabel(row, text=label_text, anchor="w").pack(side="left")
        widget_factory(row)

    # ══════════════════════════════════════════
    # Audio Bridge
    # ══════════════════════════════════════════

    def _try_open_bridge(self):
        ok = self.audio_bridge.open(
            sample_rate=self.config["sample_rate"],
            channels=self.config["channels"],
        )
        self._bridge_active = ok

    # ══════════════════════════════════════════
    # Server Callbacks
    # ══════════════════════════════════════════

    def _on_audio(self, data: bytes):
        if self.opus_decoder is not None:
            data = self.opus_decoder.decode(data)
        if self.noise_filter.enabled:
            data = self.noise_filter.process(data)
        # Route to virtual mic driver if available
        if self._bridge_active:
            self.audio_bridge.write(data)
        # Also play through speakers/headphones
        self.player.feed(data)

    def _on_connected(self, client_info):
        self._connected = True
        self.player.sample_rate = client_info.sample_rate
        self.player.channels = client_info.channels
        if client_info.codec == CODEC_OPUS:
            self.opus_decoder = OpusDecoder(client_info.sample_rate, client_info.channels)
            if not self.opus_decoder.available:
                self._log("WARNING: Opus decoder not available")
        else:
            self.opus_decoder = None
        self.noise_filter.sample_rate = client_info.sample_rate
        self.noise_filter.channels = client_info.channels
        # Update bridge format
        if self._bridge_active:
            self.audio_bridge.set_format(client_info.sample_rate, client_info.channels)
        self.player.start()
        self.after(0, self._update_ui_connected, client_info)
        self.tray.set_connected(True, client_info.device_name)
        self._start_level_update()

    def _on_disconnected(self):
        self._connected = False
        self.player.stop()
        self.after(0, self._update_ui_disconnected)
        self.tray.set_connected(False)

    def _on_error(self, msg: str):
        self._log(f"ERROR: {msg}")

    def _on_status(self, msg: str):
        self._log(msg)

    def _on_latency(self, ms: int):
        self._latency = ms
        self.after(0, lambda: self.latency_label.configure(
            text=f"{i18n.t('label_latency')}: {ms} ms"))

    def _update_ui_connected(self, client_info):
        self.status_dot.configure(text_color=C_GREEN)
        self.status_label.configure(text=i18n.t("status_connected", device=client_info.device_name))
        codec_name = "Opus" if client_info.codec == CODEC_OPUS else "PCM"
        self.info_label.configure(
            text=f"{client_info.sample_rate}Hz  ·  {codec_name}  ·  {client_info.addr[0]}"
        )
        self.disconnect_btn.configure(state="normal")
        self._log(i18n.t("log_client_connected",
                         device=client_info.device_name,
                         ip=client_info.addr[0]))
        if self._bridge_active:
            self._log(i18n.t("log_driver_active"))

    def _update_ui_disconnected(self):
        self.status_dot.configure(text_color=C_RED)
        self.status_label.configure(text=i18n.t("status_disconnected"))
        self.info_label.configure(text=i18n.t("status_waiting"))
        self.latency_label.configure(text=f"{i18n.t('label_latency')}: — ms")
        self.disconnect_btn.configure(state="disabled")
        self.level_bar.set(0)
        self._log(i18n.t("log_client_disconnected"))

    def _start_level_update(self):
        if self._connected:
            self.level_bar.set(self.player.level)
            self._level_after_id = self.after(50, self._start_level_update)

    # ══════════════════════════════════════════
    # Actions
    # ══════════════════════════════════════════

    def _start_server(self):
        self.server.port = int(self.port_entry.get() or DEFAULT_PORT)
        self.server.start()
        ip = self.server.get_local_ip()
        self.ip_label.configure(
            text=f"IP: {ip}   |   {i18n.t('label_port')}: {self.server.port}")
        self._log(i18n.t("log_server_started", port=self.server.port))
        if self._bridge_active:
            self._log(i18n.t("log_driver_active"))
        elif self.config.get("virtual_mic", True):
            self._log(i18n.t("log_driver_not_found"))

    def _restart_server(self):
        self.server.stop()
        self.player.stop()
        self._update_ui_disconnected()
        try:
            port = int(self.port_entry.get())
        except ValueError:
            port = DEFAULT_PORT
            self.port_entry.delete(0, "end")
            self.port_entry.insert(0, str(port))
        self.config["port"] = port
        self._start_server()

    def _disconnect_client(self):
        self.server.stop()
        self.player.stop()
        self._update_ui_disconnected()
        self._start_server()

    def _on_volume_change(self, value):
        vol = int(value)
        self.vol_value_label.configure(text=f"{vol}%")
        self.player.set_volume(vol)
        self.config["volume"] = vol

    def _on_mode_change(self, value):
        self.config["connection_mode"] = value
        self._log(f"{i18n.t('label_connection_mode')}: {value}")

    def _on_device_change(self, value):
        dev = "" if value == "Default" else value
        self.config["output_device"] = dev
        self.player.device_name = dev
        self._log(f"{i18n.t('label_output_device')}: {value}")

    def _on_vmic_change(self):
        enabled = self.vmic_var.get()
        self.config["virtual_mic"] = enabled
        if enabled and not self._bridge_active:
            self._try_open_bridge()
            if self._bridge_active:
                self._log(i18n.t("log_driver_active"))
            else:
                self._log(i18n.t("log_driver_not_found"))
        elif not enabled and self._bridge_active:
            self.audio_bridge.close()
            self._bridge_active = False

    def _on_ns_change(self):
        enabled = self.ns_var.get()
        self.config["noise_suppression"] = enabled
        self.noise_filter.enable(enabled)
        self._log(i18n.t("log_ns_on") if enabled else i18n.t("log_ns_off"))

    def _on_tray_change(self):
        self.config["minimize_to_tray"] = self.tray_var.get()

    def _on_ontop_change(self):
        on_top = self.ontop_var.get()
        self.config["always_on_top"] = on_top
        self.attributes("-topmost", on_top)

    def _on_language_change(self, lang_name):
        for code, name in i18n.available_languages().items():
            if name == lang_name:
                i18n.load_language(code)
                self.config["language"] = code
                self._log(f"{i18n.t('label_language')}: {lang_name}")
                self._refresh_ui_texts()
                break

    def _toggle_theme(self):
        dark = not self.config["dark_theme"]
        self.config["dark_theme"] = dark
        ctk.set_appearance_mode("dark" if dark else "light")
        self.theme_btn.configure(text="☀" if dark else "☾")

    def _refresh_ui_texts(self):
        """Refresh all translatable UI labels after language change."""
        self.title(i18n.t("app_title"))
        if not self._connected:
            self.status_label.configure(text=i18n.t("status_disconnected"))
            self.info_label.configure(text=i18n.t("status_waiting"))
        self.latency_label.configure(
            text=f"{i18n.t('label_latency')}: {self._latency if self._latency else '—'} ms")
        self.start_btn.configure(text=i18n.t("btn_start"))
        self.disconnect_btn.configure(text=i18n.t("btn_disconnect"))

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _show_window(self):
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def _on_close(self):
        if self.config["minimize_to_tray"] and self.tray.available:
            self.withdraw()
        else:
            self._quit_app()

    def _quit_app(self):
        self.server.stop()
        self.player.stop()
        self.audio_bridge.close()
        self.tray.stop()
        if self._level_after_id:
            self.after_cancel(self._level_after_id)
        self.config.save()
        self.destroy()


def run():
    app = VoiceMicApp()
    app.mainloop()
