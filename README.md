# VoiceMic — Use Phone as PC Microphone

Turn your Android phone into a wireless microphone for your PC.
Includes a **virtual audio driver** — no third-party virtual cable needed.

## Features

- **Phone-as-server architecture** — phone runs server, PC connects as client
- **Built-in virtual microphone driver** — appears as a real mic in Windows
- **Windows installer** (Setup.exe) with driver auto-install
- **WiFi, USB, Bluetooth, WiFi Direct** transport support
- **PCM / Opus** codec support
- **Classic Win32-style** PC client GUI (menu bar, connect dialog, status bar)
- **Compact** Android app (play/stop in action bar, IP display)
- **Real-time audio level** monitoring
- **Latency display** (ping/pong)
- **Volume control** (0-200%)
- **Noise suppression** on Android
- **Mute/unmute** on phone
- **System tray** on PC (minimize to tray)
- **Auto-reconnect** on disconnect
- **Keep screen on** while streaming
- **Foreground service** — works with screen off
- **Headless mode** — run PC client without GUI

---

## Quick Start

### 1. Download
Go to **Releases** on GitHub and download:
- `VoiceMic-Setup-1.0.0.exe` — PC installer (includes virtual mic driver)
- `VoiceMic-debug.apk` — Android app

### 2. Install & Run
1. Run `VoiceMic-Setup-1.0.0.exe` — installs the app and virtual microphone driver
2. Install the APK on your phone
3. Open VoiceMic on phone → tap **Play** → note the IP address shown
4. Open VoiceMic on PC → **Connection → Connect...** → enter phone's IP → OK
5. Your phone microphone now streams to PC!

### 3. Use as Microphone in Apps
The VoiceMic virtual driver registers as **"VoiceMic Virtual Microphone"** in Windows:
- In **Discord** → Settings → Voice → Input Device → select **VoiceMic Virtual Microphone**
- In **Zoom** → Settings → Audio → Microphone → select **VoiceMic Virtual Microphone**
- Works in any app that accepts a microphone input

---

## Build from Source

### PC Client (.exe)

```bash
cd pc-server
pip install -r requirements.txt

# Run directly
python main.py

# Build .exe
pyinstaller voicemic.spec --clean
# Output: dist/VoiceMic/VoiceMic.exe
```

**Headless mode** (no GUI):
```bash
python main.py --headless --ip 192.168.1.100 --port 8125
```

### Android App (.apk)

Requires Android SDK & JDK 17.

```bash
cd android-client
./gradlew assembleDebug
# Output: app/build/outputs/apk/debug/app-debug.apk
```

### Virtual Audio Driver

Requires Windows Driver Kit (WDK) 10.

```bash
cd driver
msbuild voicemic_audio.vcxproj /p:Configuration=Release /p:Platform=x64
```

### Windows Installer

Requires [Inno Setup 6](https://jrsoftware.org/isdownload.php).

```bash
iscc installer/voicemic.iss
# Output: dist/VoiceMic-Setup-1.0.0.exe
```

---

## Build via GitHub Actions

GitHub builds everything in the cloud — no local SDK or WDK required.

1. Push code to GitHub
2. **Actions tab** — three workflows run automatically:
   - `Build Windows EXE + Installer` → `VoiceMic-Setup` and `VoiceMic-Windows`
   - `Build Android APK` → `VoiceMic-Android-Debug`
   - `Build Virtual Audio Driver` → `voicemic-driver-x64`
3. Download artifacts from the latest workflow run
4. For release builds:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

---

## Connection Modes

### WiFi (default)
- Phone and PC must be on the **same WiFi network**
- Start server on phone → enter phone's IP in PC client
- Default port: **8125**

### USB
1. Enable **USB Debugging** on phone
2. Connect phone via USB
3. Run: `adb forward tcp:8125 tcp:8125`
4. In PC client, connect to `127.0.0.1`

### Bluetooth
- Pair phone with PC
- Select Bluetooth transport in both apps

### WiFi Direct
- Connect devices via WiFi Direct
- Use the WiFi Direct IP address

---

## Architecture

**Phone = Server, PC = Client**

```
Phone (Server)                         PC (Client)
┌─────────────┐                    ┌──────────────────┐
│ Mic Capture  │                    │ VoiceMic Client  │
│      ↓       │   TCP/WiFi        │      ↓           │
│ TCP Server  ─┼──────────────────→│ Audio Player     │
│ (port 8125)  │  Audio packets    │      ↓           │
└─────────────┘                    │ Shared Memory    │
                                   │      ↓           │
                                   │ Virtual Driver   │
                                   │      ↓           │
                                   │ Apps (Discord..) │
                                   └──────────────────┘
```

### Protocol

Custom TCP protocol with binary packets:

```
[MAGIC "VMIC" (4B)] [TYPE (1B)] [LENGTH (4B)] [PAYLOAD (NB)]
```

| Packet | Type | Direction | Description |
|--------|------|-----------|-------------|
| Handshake | 0x01 | Phone → PC | Audio format: sample rate, channels, codec, device name |
| Handshake ACK | 0x02 | PC → Phone | Accepted/rejected |
| Audio | 0x10 | Phone → PC | Raw audio frames |
| Control | 0x20 | Bidirectional | Mute, volume, noise suppress |
| Ping | 0x30 | PC → Phone | Timestamp for latency |
| Pong | 0x31 | Phone → PC | Echo timestamp |
| Disconnect | 0xFF | Either | Graceful disconnect |

---

## Project Structure

```
├── pc-server/
│   ├── main.py            # Entry point (GUI + headless)
│   ├── gui.py             # Classic Win32-style tkinter GUI
│   ├── server.py          # TCP client (connects to phone)
│   ├── audio_player.py    # Audio output (PyAudio/sounddevice)
│   ├── audio_bridge.py    # Shared memory bridge to virtual driver
│   ├── protocol.py        # Wire protocol
│   ├── config.py          # Persistent settings
│   ├── tray_icon.py       # System tray
│   ├── requirements.txt   # Python dependencies
│   └── voicemic.spec      # PyInstaller build spec
│
├── android-client/
│   ├── app/src/main/java/com/voicemic/app/
│   │   ├── MainActivity.java       # Main UI (play/stop)
│   │   ├── AudioStreamService.java # Foreground service + mic capture
│   │   ├── AudioEncoder.java       # Opus encoding via MediaCodec
│   │   ├── NetworkClient.java      # TCP server (accepts PC connections)
│   │   ├── SettingsActivity.java   # Settings screen
│   │   └── Protocol.java           # Wire protocol (Java)
│   ├── app/src/main/res/
│   └── app/build.gradle
│
├── driver/
│   ├── adapter.cpp        # WDM adapter initialization
│   ├── minwave.cpp        # Wave cyclic miniport (capture)
│   ├── common.h           # Shared definitions
│   ├── voicemic_audio.inf # Driver INF file
│   └── voicemic_audio.vcxproj
│
├── installer/
│   ├── voicemic.iss       # Inno Setup installer script
│   └── license.txt
│
├── .github/workflows/
│   ├── build-exe.yml      # Build EXE + Installer
│   ├── build-apk.yml      # Build Android APK
│   └── build-driver.yml   # Build virtual audio driver
│
├── SPEC.md                # Detailed specification
└── README.md
```

---

## Requirements

### PC
- Windows 10/11 (64-bit)
- The installer handles everything

### For Building from Source
- Python 3.9+
- Windows Driver Kit 10 (for driver)
- Inno Setup 6 (for installer)
- Android SDK + JDK 17 (for Android app)

### Android
- Android 7.0+ (API 24)
- Microphone permission

---

## License

MIT License — free for personal and commercial use.
