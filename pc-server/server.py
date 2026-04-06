"""
VoiceMic TCP Server
Accepts connections from phone clients and receives audio data.
"""
import socket
import threading
import time
import struct
from typing import Callable, Optional

from protocol import (
    MAGIC, PKT_HANDSHAKE, PKT_AUDIO, PKT_CONTROL, PKT_PING, PKT_DISCONNECT,
    parse_packet_header, parse_handshake, build_handshake_ack, build_pong,
    CTRL_MUTE, CTRL_UNMUTE, CTRL_SET_VOLUME, CTRL_SET_NOISE_SUPPRESS,
)


class ClientInfo:
    """Stores connected client information."""
    def __init__(self, addr, device_name="", sample_rate=48000, channels=1, codec=0):
        self.addr = addr
        self.device_name = device_name
        self.sample_rate = sample_rate
        self.channels = channels
        self.codec = codec
        self.connected_at = time.time()
        self.last_ping_ms = 0
        self.muted = False


class AudioServer:
    """TCP server that receives audio from phone clients."""

    def __init__(self, port=8125):
        self.port = port
        self._server_socket: Optional[socket.socket] = None
        self._client_socket: Optional[socket.socket] = None
        self._running = False
        self._listening = False
        self._thread: Optional[threading.Thread] = None
        self._client_info: Optional[ClientInfo] = None

        # Callbacks
        self.on_audio: Optional[Callable[[bytes], None]] = None
        self.on_client_connected: Optional[Callable[[ClientInfo], None]] = None
        self.on_client_disconnected: Optional[Callable[[], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_latency_update: Optional[Callable[[int], None]] = None
        self.on_status: Optional[Callable[[str], None]] = None

    def start(self):
        """Start listening for connections."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._server_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the server and disconnect any client."""
        self._running = False
        self._listening = False
        self._disconnect_client()
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

    def _emit_status(self, msg: str):
        if self.on_status:
            self.on_status(msg)

    def _emit_error(self, msg: str):
        if self.on_error:
            self.on_error(msg)

    def _disconnect_client(self):
        if self._client_socket:
            try:
                self._client_socket.close()
            except Exception:
                pass
            self._client_socket = None
        if self._client_info:
            self._client_info = None
            if self.on_client_disconnected:
                self.on_client_disconnected()

    def _server_loop(self):
        """Main server loop."""
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.settimeout(1.0)
            self._server_socket.bind(("0.0.0.0", self.port))
            self._server_socket.listen(1)
            self._listening = True
            self._emit_status(f"Listening on port {self.port}...")
        except OSError as e:
            self._emit_error(f"Cannot bind to port {self.port}: {e}")
            self._running = False
            return

        while self._running:
            try:
                client_sock, addr = self._server_socket.accept()
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                client_sock.settimeout(5.0)
                self._emit_status(f"Connection from {addr[0]}:{addr[1]}")
                self._handle_client(client_sock, addr)
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    self._emit_error("Server socket error")
                break

        self._listening = False
        self._emit_status("Server stopped")

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
                    raise ConnectionError("Server stopped")
                continue
        return bytes(data)

    def _handle_client(self, sock: socket.socket, addr):
        """Handle a single client connection."""
        self._disconnect_client()  # Disconnect any existing client
        self._client_socket = sock

        try:
            # Read and process packets
            while self._running:
                # Read header (9 bytes: MAGIC(4) + TYPE(1) + LENGTH(4))
                header = self._recv_exact(sock, 9)
                parsed = parse_packet_header(header)
                if parsed is None:
                    self._emit_error("Invalid packet received")
                    break

                pkt_type, payload_len = parsed

                # Read payload
                payload = b""
                if payload_len > 0:
                    if payload_len > 1024 * 1024:  # 1MB max
                        self._emit_error("Payload too large")
                        break
                    payload = self._recv_exact(sock, payload_len)

                # Process packet
                if pkt_type == PKT_HANDSHAKE:
                    config = parse_handshake(payload)
                    if config:
                        self._client_info = ClientInfo(
                            addr=addr,
                            device_name=config["device_name"],
                            sample_rate=config["sample_rate"],
                            channels=config["channels"],
                            codec=config["codec"],
                        )
                        # Send ACK
                        ack = build_handshake_ack(True, "Connected")
                        sock.sendall(ack)
                        if self.on_client_connected:
                            self.on_client_connected(self._client_info)
                    else:
                        ack = build_handshake_ack(False, "Invalid handshake")
                        sock.sendall(ack)
                        break

                elif pkt_type == PKT_AUDIO:
                    if self.on_audio and self._client_info and not self._client_info.muted:
                        self.on_audio(payload)

                elif pkt_type == PKT_PING:
                    if len(payload) >= 8:
                        ts = struct.unpack("!Q", payload[:8])[0]
                        pong = build_pong(ts)
                        sock.sendall(pong)
                        now_ms = int(time.time() * 1000)
                        latency = now_ms - ts
                        if self._client_info:
                            self._client_info.last_ping_ms = latency
                        if self.on_latency_update:
                            self.on_latency_update(latency)

                elif pkt_type == PKT_CONTROL:
                    if len(payload) >= 2 and self._client_info:
                        cmd, val = payload[0], payload[1]
                        if cmd == CTRL_MUTE:
                            self._client_info.muted = True
                        elif cmd == CTRL_UNMUTE:
                            self._client_info.muted = False

                elif pkt_type == PKT_DISCONNECT:
                    self._emit_status("Client disconnected gracefully")
                    break

        except ConnectionError:
            self._emit_status("Client disconnected")
        except Exception as e:
            self._emit_error(f"Client error: {e}")
        finally:
            self._disconnect_client()

    def send_control(self, command: int, value: int = 0):
        """Send a control packet to the connected client."""
        if self._client_socket:
            from protocol import build_control
            try:
                pkt = build_control(command, value)
                self._client_socket.sendall(pkt)
            except Exception:
                pass

    @property
    def is_running(self):
        return self._running

    @property
    def is_listening(self):
        return self._listening

    @property
    def client_info(self):
        return self._client_info

    @property
    def is_connected(self):
        return self._client_info is not None

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
