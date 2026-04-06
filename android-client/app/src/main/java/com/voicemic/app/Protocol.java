package com.voicemic.app;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

/**
 * VoiceMic wire protocol — matches the Python server implementation.
 */
public class Protocol {

    public static final byte[] MAGIC = new byte[]{'V', 'M', 'I', 'C'};
    public static final int VERSION = 1;
    public static final int DEFAULT_PORT = 8125;
    public static final int HEADER_SIZE = 9; // MAGIC(4) + TYPE(1) + LENGTH(4)

    // Packet types
    public static final int PKT_HANDSHAKE = 0x01;
    public static final int PKT_HANDSHAKE_ACK = 0x02;
    public static final int PKT_AUDIO = 0x10;
    public static final int PKT_CONTROL = 0x20;
    public static final int PKT_PING = 0x30;
    public static final int PKT_PONG = 0x31;
    public static final int PKT_DISCONNECT = 0xFF;

    // Codec IDs
    public static final int CODEC_PCM = 0;
    public static final int CODEC_OPUS = 1;

    // Control commands
    public static final int CTRL_MUTE = 0x01;
    public static final int CTRL_UNMUTE = 0x02;
    public static final int CTRL_SET_VOLUME = 0x03;
    public static final int CTRL_SET_NOISE_SUPPRESS = 0x04;

    /**
     * Build a protocol packet: [MAGIC(4)][TYPE(1)][LENGTH(4)][PAYLOAD(N)]
     */
    public static byte[] buildPacket(int pktType, byte[] payload) {
        ByteBuffer buf = ByteBuffer.allocate(HEADER_SIZE + payload.length);
        buf.order(ByteOrder.BIG_ENDIAN);
        buf.put(MAGIC);
        buf.put((byte) pktType);
        buf.putInt(payload.length);
        buf.put(payload);
        return buf.array();
    }

    /**
     * Build handshake packet.
     */
    public static byte[] buildHandshake(int sampleRate, int channels, int codec, String deviceName) {
        byte[] nameBytes = deviceName.getBytes(StandardCharsets.UTF_8);
        int nameLen = Math.min(nameBytes.length, 64);

        ByteBuffer payload = ByteBuffer.allocate(8 + nameLen);
        payload.order(ByteOrder.BIG_ENDIAN);
        payload.putInt(sampleRate);
        payload.putShort((short) channels);
        payload.put((byte) codec);
        payload.put((byte) nameLen);
        payload.put(nameBytes, 0, nameLen);

        return buildPacket(PKT_HANDSHAKE, payload.array());
    }

    /**
     * Parse handshake ACK. Returns true if accepted.
     */
    public static boolean parseHandshakeAck(byte[] payload) {
        if (payload == null || payload.length < 1) return false;
        return payload[0] == 1;
    }

    /**
     * Build audio data packet.
     */
    public static byte[] buildAudioPacket(byte[] audioData) {
        return buildPacket(PKT_AUDIO, audioData);
    }

    /**
     * Build audio data packet from buffer segment.
     */
    public static byte[] buildAudioPacket(byte[] audioData, int offset, int length) {
        byte[] segment = new byte[length];
        System.arraycopy(audioData, offset, segment, 0, length);
        return buildPacket(PKT_AUDIO, segment);
    }

    /**
     * Build ping packet with current timestamp.
     */
    public static byte[] buildPing(long timestampMs) {
        ByteBuffer payload = ByteBuffer.allocate(8);
        payload.order(ByteOrder.BIG_ENDIAN);
        payload.putLong(timestampMs);
        return buildPacket(PKT_PING, payload.array());
    }

    /**
     * Parse pong packet, returns original timestamp.
     */
    public static long parsePong(byte[] payload) {
        if (payload == null || payload.length < 8) return 0;
        ByteBuffer buf = ByteBuffer.wrap(payload);
        buf.order(ByteOrder.BIG_ENDIAN);
        return buf.getLong();
    }

    /**
     * Build control packet.
     */
    public static byte[] buildControl(int command, int value) {
        byte[] payload = new byte[]{(byte) command, (byte) value};
        return buildPacket(PKT_CONTROL, payload);
    }

    /**
     * Build disconnect packet.
     */
    public static byte[] buildDisconnect() {
        return buildPacket(PKT_DISCONNECT, new byte[0]);
    }

    /**
     * Parse header from bytes. Returns [pktType, payloadLength] or null.
     */
    public static int[] parseHeader(byte[] header) {
        if (header.length < HEADER_SIZE) return null;

        // Validate magic
        for (int i = 0; i < 4; i++) {
            if (header[i] != MAGIC[i]) return null;
        }

        int pktType = header[4] & 0xFF;
        ByteBuffer buf = ByteBuffer.wrap(header, 5, 4);
        buf.order(ByteOrder.BIG_ENDIAN);
        int payloadLen = buf.getInt();

        return new int[]{pktType, payloadLen};
    }
}
