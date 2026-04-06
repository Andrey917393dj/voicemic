# VoiceMic — Technical Specification

## Architecture Overview

### VoiceMic System (3 components)
1. **Phone App** — captures mic audio, transmits to PC
2. **PC Client** — receives audio, passes to virtual device
3. **Virtual Device Driver** — kernel-mode, simulates real microphone for apps

### Audio Format
- 48000 Hz sample rate
- 16-bit signed PCM
- Mono (1 channel)

---

## PC Client (Classic Win32-style)

### Window
- Classic Windows application with traditional menu bar
- Title: "VoiceMic Client"
- Small fixed-size window (~400x200)
- White/system background, minimal content area
- Status bar at bottom showing: "Disconnected" / "Connected"

### Menu Bar
```
Connection
  ├── Connect...        (opens Connect dialog)
  └── Disconnect

Options
  ├── ☐ Play in speaker
  ├── When aborting ►
  │     ├── ☐ Auto reconnect
  │     └── ☐ Flash window
  └── Advanced...       (opens Advanced dialog)
```

### Connect Dialog
- Modal dialog window
- **Transport type** radio buttons: WiFi, USB, Bluetooth, WiFi Direct
- **Phone IP Address** text field (shown for WiFi / WiFi Direct)
- **Bluetooth device** dropdown (shown for Bluetooth)
- **Connect** and **Cancel** buttons

### Advanced Dialog
- **Control port** input (default: 8125)
- **Media port** input (default: 8126)  
- **☐ Enable debug mode** checkbox
- **OK** / **Cancel** buttons

### Behavior
- On connect: status bar → "Connected"
- On disconnect: status bar → "Disconnected"
- Audio data received → written to virtual device driver via shared memory
- "Play in speaker" → also plays audio through speakers
- "Auto reconnect" → reconnects if connection drops
- "Flash window" → flashes taskbar when connection drops

---

## Android App

### Main Screen (Material Design)
- **Action Bar / Toolbar**:
  - App title "VoiceMic"
  - Settings gear icon (top-right)
  - Play ▶ / Stop ■ button (top-right action)
- **Main content area**:
  - Large status text: "Disconnected" / "Connected" / IP address display
  - Volume slider bar
  - Mute/Unmute toggle button

### Settings Screen
- **Transport**: WiFi / USB / Bluetooth / WiFi Direct (radio list)
- **Audio Source**: Default / Mic mode 1 / Mic mode 2 / Mic mode 3 / Rear mic
- **Control Port**: editable number (default: 8125)
- **Media Port**: editable number (default: 8126)

### Behavior
- Start server → shows IP address on main screen
- Captures mic audio at 48kHz/16bit/mono
- Sends audio to connected PC client
- Volume bar adjusts capture gain
- Mute button silences without disconnecting

---

## Virtual Audio Driver

### Identity
- Device name: "VoiceMic Device" 
- Shows in Device Manager under "Sound, video and game controllers"
- Acts as audio capture (recording) device
- sys file: voicemic.sys

### Technical
- WDM audio miniport driver
- Shared memory ring buffer for IPC with PC client
- Shared memory name: "VoiceMicAudioBuffer"
- Event name: "VoiceMicAudioEvent"
- Format: 48000 Hz, 16-bit, mono
- Ring buffer: 48000 * 2 * 1 = 96000 bytes (1 second mono)

---

## Installer (Inno Setup)

### What it installs
1. VoiceMic Client (exe + dependencies)
2. VoiceMic Virtual Device driver

### Behavior
- Standard Windows installer wizard
- License agreement page
- Install directory selection
- Desktop shortcut option
- Driver installation during setup
- Uninstaller removes driver too

---

## Protocol

### Transport Layer
- **WiFi**: TCP connection, phone→PC
- **USB**: TCP over ADB port forwarding  
- **Bluetooth**: RFCOMM serial
- **WiFi Direct**: TCP (phone is AP)

### Control Channel (TCP, port 8125)
- Used for handshake, commands, keepalive
- Phone connects to PC's control port

### Media Channel (UDP, port 8126)
- Used for audio data streaming
- Lower latency than TCP for audio

### Packet Format
```
[TYPE (1 byte)] [LENGTH (2 bytes big-endian)] [PAYLOAD]
```

| Type | Name | Direction | Payload |
|------|------|-----------|---------|
| 0x01 | CONNECT | Phone→PC | sample_rate(4) + bits(2) + channels(2) |
| 0x02 | CONNECT_ACK | PC→Phone | status(1) |
| 0x10 | AUDIO | Phone→PC | raw PCM data |
| 0x20 | MUTE | Phone→PC | muted(1) |
| 0x30 | PING | PC→Phone | timestamp(8) |
| 0x31 | PONG | Phone→PC | timestamp(8) |
| 0xFF | DISCONNECT | Either | (empty) |
