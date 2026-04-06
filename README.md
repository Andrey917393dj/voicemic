# 🎤 VoiceMic — Use Phone as PC Microphone

Open-source analog of WO Mic. Stream your phone's microphone to your PC over WiFi or USB.
Includes a **virtual audio driver** — no third-party virtual cable needed.

## Features

- **Built-in virtual microphone driver** — appears as a real mic in Windows
- **Windows installer** (Setup.exe) with driver auto-install
- **WiFi & USB** connection modes
- **PCM / Opus** codec support
- **Multi-language UI** (English, Русский, Deutsch, Français, Español, 中文, 日本語)
- **Real-time audio level** monitoring
- **Latency display** (ping/pong)
- **Volume control** (0-200%)
- **Noise suppression** on both PC and Android
- **Mute/unmute** on phone
- **System tray** on PC (minimize to tray)
- **Dark/Light theme** on both platforms
- **Auto-connect** on app start
- **Keep screen on** while streaming
- **Always on top** window option
- **Foreground service** — works with screen off
- **Headless mode** — run PC server without GUI

---

## Quick Start

### 1. Download Installer
Go to **Releases** on GitHub and download:
- `VoiceMic-Setup-1.0.0.exe` — PC installer (includes virtual mic driver)
- `VoiceMic-debug.apk` — Android app

### 2. Install & Run
1. Run `VoiceMic-Setup-1.0.0.exe` — installs the app and virtual microphone driver
2. Install the APK on your phone
3. Launch VoiceMic on PC — note the **IP address** displayed
4. Enter that IP in the phone app and press **Connect**
5. Your phone microphone now streams to PC!

### 3. Use as Microphone in Apps
The VoiceMic virtual driver registers as **"VoiceMic Virtual Microphone"** in Windows:
- In **Discord** → Settings → Voice → Input Device → select **VoiceMic Virtual Microphone**
- In **Zoom** → Settings → Audio → Microphone → select **VoiceMic Virtual Microphone**
- Works in any app that accepts a microphone input

> **Fallback:** If you prefer, you can also route audio through [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) using the Output Device setting.

---

## Build from Source

### PC Server (.exe)

```bash
cd pc-server
pip install -r requirements.txt

# Run directly
python main.py

# Build .exe
pyinstaller voicemic.spec --clean
# Output: dist/VoiceMic/VoiceMic.exe
```

**Headless mode** (no GUI, for servers):
```bash
python main.py --headless --port 8125
```

### Android App (.apk)

Requires Android SDK & JDK 17.

```bash
cd android-client
gradle wrapper --gradle-version 8.2
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

## Build via GitHub Actions (No Local Tools Needed)

GitHub builds everything in the cloud — no local SDK or WDK required.

### Step-by-step:

1. **Create a GitHub repo** and push this code:
   ```bash
   git init
   git add .
   git commit -m "VoiceMic v1.0"
   git remote add origin https://github.com/YOUR_USERNAME/voicemic.git
   git push -u origin main
   ```

2. **Go to Actions tab** — three workflows run automatically:
   - `Build Windows EXE + Installer` → produces `VoiceMic-Setup` and `VoiceMic-Windows`
   - `Build Android APK` → produces `VoiceMic-Android-Debug`
   - `Build Virtual Audio Driver` → produces `voicemic-driver-x64`

3. **Download artifacts** from the latest workflow run

4. **For release builds** (attached to GitHub Releases):
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

---

## Connection Modes

### WiFi
- Phone and PC must be on the **same WiFi network**
- Enter PC's IP address in the phone app
- Default port: **8125**

### USB (ADB)
1. Enable **USB Debugging** on phone
2. Connect phone via USB
3. Run: `adb forward tcp:8125 tcp:8125`  (or use `usb_connect.bat`)
4. In phone app, connect to `127.0.0.1:8125`

---

## Multi-Language Support

The PC app auto-detects your system language. Supported:

| Code | Language |
|------|----------|
| en | English |
| ru | Русский |
| de | Deutsch |
| fr | Français |
| es | Español |
| zh | 中文 |
| ja | 日本語 |

Switch language any time from the dropdown in the app header.

---

## Architecture

### Virtual Audio Driver

The VoiceMic driver is a WDM audio miniport driver that:
1. Registers as a **capture device** (microphone) in Windows
2. Reads audio from a **shared memory ring buffer**
3. The PC server app writes received audio into that buffer
4. Any application can select "VoiceMic Virtual Microphone" as input

Communication flow:
```
Phone Mic → [TCP/WiFi] → PC Server → Shared Memory → Virtual Driver → Apps
```

### Protocol

Custom TCP protocol with binary packets:

```
[MAGIC "VMIC" (4B)] [TYPE (1B)] [LENGTH (4B)] [PAYLOAD (NB)]
```

| Packet | Type | Description |
|--------|------|-------------|
| Handshake | 0x01 | Client → Server: sample rate, channels, codec, device name |
| Handshake ACK | 0x02 | Server → Client: accepted/rejected |
| Audio | 0x10 | Client → Server: raw audio frames |
| Control | 0x20 | Bidirectional: mute, volume, noise suppress |
| Ping | 0x30 | Client → Server: timestamp |
| Pong | 0x31 | Server → Client: echo timestamp |
| Disconnect | 0xFF | Graceful disconnect |

---

## Project Structure

```
├── pc-server/
│   ├── main.py            # Entry point (GUI + headless)
│   ├── gui.py             # CustomTkinter UI with i18n
│   ├── server.py          # TCP server
│   ├── audio_player.py    # Audio output (PyAudio/sounddevice)
│   ├── audio_bridge.py    # Shared memory bridge to virtual driver
│   ├── protocol.py        # Wire protocol
│   ├── config.py          # Persistent settings
│   ├── noise_filter.py    # Software noise suppression
│   ├── opus_decoder.py    # Opus codec decoder
│   ├── i18n.py            # Internationalization system
│   ├── tray_icon.py       # System tray
│   ├── lang/              # Language files (en, ru, de, fr, es, zh, ja)
│   ├── requirements.txt   # Python dependencies
│   └── voicemic.spec      # PyInstaller build spec
│
├── android-client/
│   ├── app/src/main/java/com/voicemic/app/
│   │   ├── MainActivity.java
│   │   ├── AudioStreamService.java
│   │   ├── AudioEncoder.java       # Opus encoding via MediaCodec
│   │   ├── NetworkClient.java
│   │   ├── SettingsActivity.java
│   │   └── Protocol.java
│   ├── app/src/main/res/
│   └── app/build.gradle
│
├── driver/
│   ├── adapter.cpp        # WDM adapter initialization
│   ├── minwave.cpp        # Wave cyclic miniport (capture)
│   ├── common.h           # Shared definitions
│   ├── voicemic_audio.inf # Driver INF file
│   └── voicemic_audio.vcxproj  # Visual Studio/WDK project
│
├── installer/
│   ├── voicemic.iss       # Inno Setup installer script
│   └── license.txt
│
├── .github/workflows/
│   ├── build-exe.yml      # Build EXE + Installer
│   ├── build-apk.yml      # Build Android APK
│   └── build-driver.yml   # Build virtual audio driver (WDK)
│
└── README.md
```

---

## Requirements

### PC
- Windows 10/11 (64-bit)
- The installer handles everything — no additional software needed

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
