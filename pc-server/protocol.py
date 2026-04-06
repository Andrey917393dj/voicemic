"""
VoiceMic Protocol Definition
Wire protocol for audio streaming between phone and PC.
"""
import struct

# Protocol constants
MAGIC = b"VMIC"
VERSION = 1
DEFAULT_PORT = 8125

# Packet types
PKT_HANDSHAKE = 0x01
PKT_HANDSHAKE_ACK = 0x02
PKT_AUDIO = 0x10
PKT_CONTROL = 0x20
PKT_PING = 0x30
PKT_PONG = 0x31
PKT_DISCONNECT = 0xFF

# Codec IDs
CODEC_PCM = 0
CODEC_OPUS = 1

# Control commands
CTRL_MUTE = 0x01
CTRL_UNMUTE = 0x02
CTRL_SET_VOLUME = 0x03
CTRL_SET_NOISE_SUPPRESS = 0x04

# Sample rates
SAMPLE_RATES = [8000, 16000, 22050, 44100, 48000]
DEFAULT_SAMPLE_RATE = 48000
DEFAULT_CHANNELS = 1
DEFAULT_FRAME_SIZE = 960  # 20ms at 48kHz


def build_packet(pkt_type: int, payload: bytes = b"") -> bytes:
    """Build a protocol packet: [MAGIC(4)][TYPE(1)][LENGTH(4)][PAYLOAD(N)]"""
    header = MAGIC + struct.pack("!BI", pkt_type, len(payload))
    return header + payload


def parse_packet_header(data: bytes):
    """Parse packet header, returns (pkt_type, payload_length) or None."""
    if len(data) < 9:
        return None
    magic = data[:4]
    if magic != MAGIC:
        return None
    pkt_type = data[4]
    payload_len = struct.unpack("!I", data[5:9])[0]
    return pkt_type, payload_len


def build_handshake(sample_rate: int, channels: int, codec: int, device_name: str = "Android") -> bytes:
    """Build handshake packet."""
    name_bytes = device_name.encode("utf-8")[:64]
    payload = struct.pack("!IHBB", sample_rate, channels, codec, len(name_bytes)) + name_bytes
    return build_packet(PKT_HANDSHAKE, payload)


def parse_handshake(payload: bytes):
    """Parse handshake payload. Returns dict with config."""
    if len(payload) < 8:
        return None
    sample_rate, channels, codec, name_len = struct.unpack("!IHBB", payload[:8])
    device_name = payload[8:8 + name_len].decode("utf-8", errors="replace")
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "codec": codec,
        "device_name": device_name,
    }


def build_handshake_ack(accepted: bool, message: str = "") -> bytes:
    """Build handshake acknowledgement."""
    msg_bytes = message.encode("utf-8")[:128]
    payload = struct.pack("!B", 1 if accepted else 0) + msg_bytes
    return build_packet(PKT_HANDSHAKE_ACK, payload)


def build_audio_packet(audio_data: bytes) -> bytes:
    """Build audio data packet."""
    return build_packet(PKT_AUDIO, audio_data)


def build_control(command: int, value: int = 0) -> bytes:
    """Build control packet."""
    payload = struct.pack("!BB", command, value)
    return build_packet(PKT_CONTROL, payload)


def build_ping(timestamp_ms: int) -> bytes:
    """Build ping packet."""
    payload = struct.pack("!Q", timestamp_ms)
    return build_packet(PKT_PING, payload)


def build_pong(timestamp_ms: int) -> bytes:
    """Build pong packet."""
    payload = struct.pack("!Q", timestamp_ms)
    return build_packet(PKT_PONG, payload)
