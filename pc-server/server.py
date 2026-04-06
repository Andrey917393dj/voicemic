"""
VoiceMic Audio Client
Connects to phone server and receives audio data.
Architecture: Phone = server, PC = client.
"""
import socket
import threading
import time
import struct
from typing import Callable, Optional

from protocol import (
    MAGIC, PKT_HANDSHAKE, PKT_HANDSHAKE_ACK, PKT_AUDIO, PKT_CONTROL,
    PKT_PING, PKT_PONG, PKT_DISCONNECT,
    parse_packet_header, parse_handshake, build_handshake_ack,
    build_ping, build_packet,
    CTRL_MUTE, CTRL_UNMUTE, CTRL_SET_VOLUME, CTRL_SET_NOISE_SUPPRESS,
)


class ServerInfo:
    """Stores phone server information after handshake."""
    def __init__(self, addr, device_name="", sample_rate=48000, channels=1, codec=0):
        self.addr = addr
        self.device_name = device_name
        self.sample_rate = sample_rate
        self.channels = channels
        self.codec = codec
        self.connected_at = time.time()
        self.last_ping_ms = 0
        self.muted = False


class AudioClient:
    """TCP client that connects to phone server and receives audio.

    Flow:
    1. connect(ip, port) → TCP connect to phone
    2. Receive handshake from phone (audio format info)
    3. Send handshake ACK
    4. Receive audio packets in a loop
    """

    def __init__(self, port=8125):
        self.port = port
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._server_info: Optional[ServerInfo] = None
        self._ping_thread: Optional[threading.Thread] = None

        # Callbacks
        self.on_audio: Optional[Callable[[bytes], None]] = None
        self.on_client_connected: Optional[Callable[[ServerInfo], None]] = None
        self.on_client_disconnected: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_latency_update: Optional[Callable[[int], None]] = None
        self.on_status: Optional[Callable[[str], None]] = None

    def connect(self, ip: str, port: int = None):
        """Connect to phone server."""
        if self._running:
            self.stop()
        if port is not None:
            self.port = port
        self._running = True
        self._thread = threading.Thread(
            target=self._client_loop, args=(ip,), daemon=True
        )
        self._thread.start()

    def stop(self):
        """Disconnect from phone server."""
        self._running = False
        if self._socket:
            try:
                # Send disconnect packet
                pkt = build_packet(PKT_DISCONNECT)
                self._socket.sendall(pkt)
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        if self._ping_thread:
            self._ping_thread.join(timeout=2.0)
            self._ping_thread = None

    def _emit_status(self, msg: str):
        if self.on_status:
            self.on_status(msg)

    def _emit_error(self, msg: str):
        if self.on_error:
            self.on_error(msg)

    def _disconnect(self):
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        if self._server_info:
            self._server_info = None
            if self.on_client_disconnected:
                self.on_client_disconnected()

    def _client_loop(self, ip: str):
        """Connect to phone and receive audio packets."""
        try:
            self._emit_status(f"Connecting to {ip}:{self.port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((ip, self.port))
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._socket = sock
            self._emit_status(f"Connected to {ip}")
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            self._emit_error(f"Connection failed: {e}")
            self._running = False
            if self.on_client_disconnected:
                self.on_client_disconnected()
            return

        try:
            # Read first packet — expect handshake from phone
            header = self._recv_exact(sock, 9)
            parsed = parse_packet_header(header)
            if parsed is None:
                self._emit_error("Invalid handshake from server")
                return

            pkt_type, payload_len = parsed
            payload = self._recv_exact(sock, payload_len) if payload_len > 0 else b""

            if pkt_type == PKT_HANDSHAKE:
                config = parse_handshake(payload)
                if config:
                    self._server_info = ServerInfo(
                        addr=(ip, self.port),
                        device_name=config["device_name"],
                        sample_rate=config["sample_rate"],
                        channels=config["channels"],
                        codec=config["codec"],
                    )
                    # Send ACK back
                    ack = build_handshake_ack(True, "OK")
                    sock.sendall(ack)
                    if self.on_client_connected:
                        self.on_client_connected(self._server_info)
                    # Start ping thread
                    self._ping_thread = threading.Thread(
                        target=self._ping_loop, daemon=True
                    )
                    self._ping_thread.start()
                else:
                    self._emit_error("Bad handshake data")
                    return
            else:
                self._emit_error(f"Expected handshake, got type 0x{pkt_type:02x}")
                return

            # Main receive loop
            while self._running:
                header = self._recv_exact(sock, 9)
                parsed = parse_packet_header(header)
                if parsed is None:
                    self._emit_error("Invalid packet")
                    break

                pkt_type, payload_len = parsed
                payload = b""
                if payload_len > 0:
                    if payload_len > 1024 * 1024:
                        self._emit_error("Payload too large")
                        break
                    payload = self._recv_exact(sock, payload_len)

                if pkt_type == PKT_AUDIO:
                    if self.on_audio and self._server_info and not self._server_info.muted:
                        self.on_audio(payload)

                elif pkt_type == PKT_PONG:
                    if len(payload) >= 8:
                        ts = struct.unpack("!Q", payload[:8])[0]
                        now_ms = int(time.time() * 1000)
                        latency = now_ms - ts
                        if self._server_info:
                            self._server_info.last_ping_ms = latency
                        if self.on_latency_update:
                            self.on_latency_update(latency)

                elif pkt_type == PKT_CONTROL:
                    if len(payload) >= 2 and self._server_info:
                        cmd = payload[0]
                        if cmd == CTRL_MUTE:
                            self._server_info.muted = True
                        elif cmd == CTRL_UNMUTE:
                            self._server_info.muted = False

                elif pkt_type == PKT_DISCONNECT:
                    self._emit_status("Server disconnected")
                    break

        except ConnectionError:
            self._emit_status("Disconnected")
        except Exception as e:
            self._emit_error(f"Error: {e}")
        finally:
            self._running = False
            self._disconnect()

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        """Receive exactly n bytes."""
        data = bytearray()
        while len(data) < n:
            try:
                chunk = sock.recv(n - len(data))
                if not chunk:
                    raise ConnectionError("Connection closed")
                data.extend(chunk)
            except socket.timeout:
                if not self._running:
                    raise ConnectionError("Stopped")
                continue
        return bytes(data)

    def _ping_loop(self):
        """Send periodic pings to measure latency."""
        while self._running and self._socket:
            try:
                ts = int(time.time() * 1000)
                pkt = build_ping(ts)
                self._socket.sendall(pkt)
            except Exception:
                break
            time.sleep(3.0)

    def send_control(self, command: int, value: int = 0):
        """Send a control packet to the phone server."""
        if self._socket:
            from protocol import build_control
            try:
                pkt = build_control(command, value)
                self._socket.sendall(pkt)
            except Exception:
                pass

    @property
    def is_running(self):
        return self._running

    @property
    def server_info(self):
        return self._server_info

    @property
    def is_connected(self):
        return self._server_info is not None

    def get_local_ip(self):
        """Get the local IP address for display."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


# Backward-compatible alias
AudioServer = AudioClient
