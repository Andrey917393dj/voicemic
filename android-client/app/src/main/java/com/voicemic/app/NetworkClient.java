package com.voicemic.app;

import android.util.Log;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * TCP server that accepts connections from VoiceMic PC client.
 * Architecture: Phone = server, PC = client.
 *
 * Flow:
 * 1. startServer(port) - listen for PC connections
 * 2. PC connects
 * 3. Phone sends handshake (audio format info)
 * 4. PC sends handshake ACK
 * 5. Phone captures mic and sends audio packets
 */
public class NetworkClient {

    private static final String TAG = "NetworkServer";

    public interface Listener {
        void onConnected();
        void onDisconnected(String reason);
        void onError(String error);
        void onLatencyUpdate(long latencyMs);
    }

    private ServerSocket serverSocket;
    private Socket clientSocket;
    private OutputStream outputStream;
    private InputStream inputStream;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicBoolean connected = new AtomicBoolean(false);
    private Listener listener;
    private Thread acceptThread;
    private Thread readerThread;

    // Audio config set before starting server
    private int sampleRate = 48000;
    private int channels = 1;
    private int codec = Protocol.CODEC_PCM;
    private String deviceName = "Android";

    public void setListener(Listener listener) {
        this.listener = listener;
    }

    public boolean isConnected() {
        return connected.get();
    }

    public boolean isRunning() {
        return running.get();
    }

    public void setAudioConfig(int sampleRate, int channels, int codec, String deviceName) {
        this.sampleRate = sampleRate;
        this.channels = channels;
        this.codec = codec;
        this.deviceName = deviceName;
    }

    /**
     * Start TCP server listening for PC client connections.
     */
    public void startServer(int port) {
        if (running.get()) return;
        running.set(true);

        acceptThread = new Thread(() -> {
            try {
                serverSocket = new ServerSocket(port);
                serverSocket.setSoTimeout(1000); // check running flag every second
                Log.i(TAG, "Server listening on port " + port);

                while (running.get()) {
                    try {
                        Socket client = serverSocket.accept();
                        client.setTcpNoDelay(true);
                        handleClient(client);
                    } catch (SocketTimeoutException e) {
                        // Normal timeout, check running flag and loop
                    }
                }
            } catch (IOException e) {
                if (running.get()) {
                    Log.e(TAG, "Server error", e);
                    if (listener != null) listener.onError("Server error: " + e.getMessage());
                }
            } finally {
                closeServerSocket();
                running.set(false);
            }
        }, "VoiceMic-Accept");
        acceptThread.start();
    }

    /**
     * Handle a connected PC client.
     */
    private void handleClient(Socket client) {
        // Disconnect previous client if any
        disconnectClient();

        clientSocket = client;
        try {
            outputStream = client.getOutputStream();
            inputStream = client.getInputStream();

            // Send handshake to PC (phone tells PC its audio format)
            byte[] handshake = Protocol.buildHandshake(sampleRate, channels, codec, deviceName);
            outputStream.write(handshake);
            outputStream.flush();

            // Read handshake ACK from PC
            byte[] header = readExact(inputStream, Protocol.HEADER_SIZE);
            int[] parsed = Protocol.parseHeader(header);
            if (parsed == null || parsed[0] != Protocol.PKT_HANDSHAKE_ACK) {
                throw new IOException("Invalid handshake ACK from client");
            }
            byte[] payload = readExact(inputStream, parsed[1]);
            if (!Protocol.parseHandshakeAck(payload)) {
                throw new IOException("Client rejected connection");
            }

            connected.set(true);
            if (listener != null) listener.onConnected();

            // Start reader thread for incoming packets from PC (ping, control, disconnect)
            startReaderThread();

        } catch (IOException e) {
            Log.e(TAG, "Client handshake failed", e);
            if (listener != null) listener.onError("Handshake failed: " + e.getMessage());
            disconnectClient();
        }
    }

    /**
     * Stop the server completely.
     */
    public void stopServer() {
        running.set(false);
        disconnectClient();
        closeServerSocket();
        if (acceptThread != null) {
            try { acceptThread.join(3000); } catch (InterruptedException ignored) {}
            acceptThread = null;
        }
    }

    /**
     * Disconnect current client but keep server running.
     */
    public void disconnectClient() {
        boolean was = connected.getAndSet(false);
        try {
            if (outputStream != null) {
                byte[] pkt = Protocol.buildDisconnect();
                outputStream.write(pkt);
                outputStream.flush();
            }
        } catch (IOException ignored) {}
        closeClientSocket();
        if (was && listener != null) {
            listener.onDisconnected("Disconnected");
        }
    }

    // Keep old API name for backward compatibility with AudioStreamService
    public void disconnect() {
        stopServer();
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
                while (connected.get() && inputStream != null) {
                    byte[] header = readExact(inputStream, Protocol.HEADER_SIZE);
                    int[] parsed = Protocol.parseHeader(header);
                    if (parsed == null) {
                        handleDisconnect("Invalid packet from client");
                        return;
                    }

                    int pktType = parsed[0];
                    int payloadLen = parsed[1];
                    byte[] payload = payloadLen > 0 ? readExact(inputStream, payloadLen) : new byte[0];

                    switch (pktType) {
                        case Protocol.PKT_PING:
                            // Respond with pong
                            if (payload.length >= 8) {
                                long ts = Protocol.parsePong(payload);
                                byte[] pong = Protocol.buildPacket(Protocol.PKT_PONG,
                                        java.nio.ByteBuffer.allocate(8)
                                                .order(java.nio.ByteOrder.BIG_ENDIAN)
                                                .putLong(ts).array());
                                if (outputStream != null) {
                                    outputStream.write(pong);
                                    outputStream.flush();
                                }
                            }
                            break;

                        case Protocol.PKT_CONTROL:
                            // Handle controls from PC if needed
                            break;

                        case Protocol.PKT_DISCONNECT:
                            handleDisconnect("Client disconnected");
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

    private void handleDisconnect(String reason) {
        if (!connected.getAndSet(false)) return;
        closeClientSocket();
        if (listener != null) listener.onDisconnected(reason);
    }

    private void closeClientSocket() {
        try { if (inputStream != null) inputStream.close(); } catch (IOException ignored) {}
        try { if (outputStream != null) outputStream.close(); } catch (IOException ignored) {}
        try { if (clientSocket != null) clientSocket.close(); } catch (IOException ignored) {}
        inputStream = null;
        outputStream = null;
        clientSocket = null;
    }

    private void closeServerSocket() {
        try { if (serverSocket != null) serverSocket.close(); } catch (IOException ignored) {}
        serverSocket = null;
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
