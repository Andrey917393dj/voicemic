package com.voicemic.app;

import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.util.Log;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;

/**
 * Encodes PCM audio to Opus using Android's MediaCodec API.
 * Falls back to raw PCM if Opus encoder is not available.
 */
public class AudioEncoder {

    private static final String TAG = "AudioEncoder";
    private static final String MIME_OPUS = "audio/opus";

    private MediaCodec codec;
    private boolean initialized = false;
    private boolean opusAvailable = false;
    private int sampleRate;
    private int channels;
    private int bitRate;

    public AudioEncoder(int sampleRate, int channels, int bitRate) {
        this.sampleRate = sampleRate;
        this.channels = channels;
        this.bitRate = bitRate;
    }

    /**
     * Initialize the Opus encoder. Returns true if Opus is available.
     */
    public boolean init() {
        try {
            MediaFormat format = MediaFormat.createAudioFormat(MIME_OPUS, sampleRate, channels);
            format.setInteger(MediaFormat.KEY_BIT_RATE, bitRate);
            format.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, sampleRate * channels * 2); // 1 sec

            codec = MediaCodec.createEncoderByType(MIME_OPUS);
            codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            codec.start();

            initialized = true;
            opusAvailable = true;
            Log.i(TAG, "Opus encoder initialized: " + sampleRate + "Hz, " + channels + "ch, " + bitRate + "bps");
            return true;

        } catch (Exception e) {
            Log.w(TAG, "Opus encoder not available: " + e.getMessage());
            initialized = false;
            opusAvailable = false;
            return false;
        }
    }

    /**
     * Encode PCM data to Opus. Returns encoded bytes or null if encoding fails.
     * If Opus is not available, returns the original PCM data.
     */
    public byte[] encode(byte[] pcmData, int offset, int length) {
        if (!initialized || !opusAvailable) {
            // Fallback: return raw PCM
            if (offset == 0 && length == pcmData.length) return pcmData;
            byte[] copy = new byte[length];
            System.arraycopy(pcmData, offset, copy, 0, length);
            return copy;
        }

        try {
            // Feed input buffer
            int inputIndex = codec.dequeueInputBuffer(10000); // 10ms timeout
            if (inputIndex >= 0) {
                ByteBuffer inputBuffer = codec.getInputBuffer(inputIndex);
                if (inputBuffer != null) {
                    inputBuffer.clear();
                    inputBuffer.put(pcmData, offset, length);
                    codec.queueInputBuffer(inputIndex, 0, length, 0, 0);
                }
            }

            // Get output
            MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();
            ByteArrayOutputStream output = new ByteArrayOutputStream();

            int outputIndex;
            while ((outputIndex = codec.dequeueOutputBuffer(bufferInfo, 1000)) >= 0) {
                ByteBuffer outputBuffer = codec.getOutputBuffer(outputIndex);
                if (outputBuffer != null) {
                    byte[] encoded = new byte[bufferInfo.size];
                    outputBuffer.get(encoded);
                    output.write(encoded);
                }
                codec.releaseOutputBuffer(outputIndex, false);
            }

            byte[] result = output.toByteArray();
            return result.length > 0 ? result : null;

        } catch (Exception e) {
            Log.e(TAG, "Encode error: " + e.getMessage());
            return null;
        }
    }

    /**
     * Release the encoder resources.
     */
    public void release() {
        if (codec != null) {
            try {
                codec.stop();
                codec.release();
            } catch (Exception ignored) {}
            codec = null;
        }
        initialized = false;
    }

    public boolean isOpusAvailable() {
        return opusAvailable;
    }

    /**
     * Check if Opus encoding is supported on this device without initializing.
     */
    public static boolean isOpusSupported() {
        try {
            MediaCodec testCodec = MediaCodec.createEncoderByType(MIME_OPUS);
            testCodec.release();
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
