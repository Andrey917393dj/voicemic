package com.voicemic.app;

import android.util.Log;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * TCP client that connects to VoiceMic PC server and streams audio.
 */
public class NetworkClient {

    private static final String TAG = "NetworkClient";
    private static final int CONNECT_TIMEOUT_MS = 5000;
    private static final int PING_INTERVAL_MS = 2000;

    public interface Listener {
        void onConnected();
        void onDisconnected(String reason);
        void onError(String error);
        void onLatencyUpdate(long latencyMs);
    }

    private Socket socket;
    private OutputStream outputStream;
    private InputStream inputStream;
    private final AtomicBoolean connected = new AtomicBoolean(false);
    private final AtomicBoolean connecting = new AtomicBoolean(false);
    private Listener listener;
    private ExecutorService executor;
    private Thread readerThread;
    private Thread pingThread;

    public void setListener(Listener listener) {
        this.listener = listener;
    }

    public boolean isConnected() {
        return connected.get();
    }

    public void connect(String host, int port, int sampleRate, int channels, int codec, String deviceName) {
        if (connected.get() || connecting.get()) return;
        connecting.set(true);

        executor = Executors.newSingleThreadExecutor();
        executor.execute(() -> {
            try {
                socket = new Socket();
                socket.setTcpNoDelay(true);
                socket.setSoTimeout(0);
                socket.connect(new InetSocketAddress(host, port), CONNECT_TIMEOUT_MS);

                outputStream = socket.getOutputStream();
                inputStream = socket.getInputStream();

                // Send handshake
                byte[] handshake = Protocol.buildHandshake(sampleRate, channels, codec, deviceName);
                outputStream.write(handshake);
                outputStream.flush();

                // Read handshake ACK
                byte[] header = readExact(inputStream, Protocol.HEADER_SIZE);
                int[] parsed = Protocol.parseHeader(header);
                if (parsed == null || parsed[0] != Protocol.PKT_HANDSHAKE_ACK) {
                    throw new IOException("Invalid handshake response");
                }

                byte[] payload = readExact(inputStream, parsed[1]);
                if (!Protocol.parseHandshakeAck(payload)) {
                    String msg = payload.length > 1 ?
                            new String(payload, 1, payload.length - 1) : "Rejected";
                    throw new IOException("Server rejected: " + msg);
                }

                connected.set(true);
                connecting.set(false);

                if (listener != null) listener.onConnected();

                // Start reader and ping threads
                startReaderThread();
                startPingThread();

            } catch (IOException e) {
                connecting.set(false);
                Log.e(TAG, "Connection failed", e);
                if (listener != null) listener.onError("Connection failed: " + e.getMessage());
                closeSocket();
            }
        });
    }

    public void disconnect() {
        if (!connected.get() && !connecting.get()) return;
        connected.set(false);
        connecting.set(false);

        try {
            if (outputStream != null) {
                byte[] pkt = Protocol.buildDisconnect();
                outputStream.write(pkt);
                outputStream.flush();
            }
        } catch (IOException ignored) {
        }

        closeSocket();

        if (executor != null) {
            executor.shutdownNow();
            executor = null;
        }
    }

    public void sendAudio(byte[] data, int offset, int length) {
        if (!connected.get() || outputStream == null) return;
        try {
            byte[] packet = Protocol.buildAudioPacket(data, offset, length);
            outputStream.write(packet);
        } catch (IOException e) {
            Log.e(TAG, "Send audio failed", e);
            handleDisconnect("Send error");
        }
    }

    public void sendAudio(byte[] data) {
        sendAudio(data, 0, data.length);
    }

    public void sendControl(int command, int value) {
        if (!connected.get() || outputStream == null) return;
        try {
            byte[] packet = Protocol.buildControl(command, value);
            outputStream.write(packet);
            outputStream.flush();
        } catch (IOException e) {
            Log.e(TAG, "Send control failed", e);
        }
    }

    private void startReaderThread() {
        readerThread = new Thread(() -> {
            try {
                while (connected.get()) {
                    byte[] header = readExact(inputStream, Protocol.HEADER_SIZE);
                    int[] parsed = Protocol.parseHeader(header);
                    if (parsed == null) {
                        handleDisconnect("Invalid packet from server");
                        return;
                    }

                    int pktType = parsed[0];
                    int payloadLen = parsed[1];
                    byte[] payload = payloadLen > 0 ? readExact(inputStream, payloadLen) : new byte[0];

                    switch (pktType) {
                        case Protocol.PKT_PONG:
                            long sentTs = Protocol.parsePong(payload);
                            long latency = System.currentTimeMillis() - sentTs;
                            if (listener != null) listener.onLatencyUpdate(latency);
                            break;

                        case Protocol.PKT_CONTROL:
                            // Handle server controls if needed
                            break;

                        case Protocol.PKT_DISCONNECT:
                            handleDisconnect("Server disconnected");
                            return;
                    }
                }
            } catch (IOException e) {
                if (connected.get()) {
                    handleDisconnect("Read error: " + e.getMessage());
                }
            }
        }, "VoiceMic-Reader");
        readerThread.setDaemon(true);
        readerThread.start();
    }

    private void startPingThread() {
        pingThread = new Thread(() -> {
            try {
                while (connected.get()) {
                    Thread.sleep(PING_INTERVAL_MS);
                    if (!connected.get() || outputStream == null) break;
                    byte[] ping = Protocol.buildPing(System.currentTimeMillis());
                    outputStream.write(ping);
                    outputStream.flush();
                }
            } catch (InterruptedException | IOException ignored) {
            }
        }, "VoiceMic-Ping");
        pingThread.setDaemon(true);
        pingThread.start();
    }

    private void handleDisconnect(String reason) {
        if (!connected.getAndSet(false)) return;
        closeSocket();
        if (listener != null) listener.onDisconnected(reason);
    }

    private void closeSocket() {
        try {
            if (inputStream != null) inputStream.close();
        } catch (IOException ignored) {}
        try {
            if (outputStream != null) outputStream.close();
        } catch (IOException ignored) {}
        try {
            if (socket != null) socket.close();
        } catch (IOException ignored) {}
        inputStream = null;
        outputStream = null;
        socket = null;
    }

    private byte[] readExact(InputStream is, int n) throws IOException {
        byte[] buf = new byte[n];
        int read = 0;
        while (read < n) {
            int r = is.read(buf, read, n - read);
            if (r < 0) throw new IOException("Connection closed");
            read += r;
        }
        return buf;
    }
}
