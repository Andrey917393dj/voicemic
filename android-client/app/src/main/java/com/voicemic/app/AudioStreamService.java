package com.voicemic.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.media.audiofx.NoiseSuppressor;
import android.os.Binder;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import androidx.preference.PreferenceManager;

/**
 * Foreground service that captures microphone audio and streams it to the PC server.
 */
public class AudioStreamService extends Service {

    private static final String TAG = "AudioStreamService";
    private static final String CHANNEL_ID = "voicemic_channel";
    private static final int NOTIFICATION_ID = 1;

    public interface StatusListener {
        void onStatusChanged(String status);
        void onConnected(String serverIp);
        void onDisconnected(String reason);
        void onError(String error);
        void onLatencyUpdate(long ms);
        void onAudioLevel(float level);
    }

    private final IBinder binder = new LocalBinder();
    private NetworkClient networkClient;
    private AudioRecord audioRecord;
    private Thread recordThread;
    private volatile boolean isRecording = false;
    private volatile boolean isMuted = false;
    private StatusListener statusListener;
    private PowerManager.WakeLock wakeLock;
    private NoiseSuppressor noiseSuppressor;
    private AudioEncoder audioEncoder;

    // Audio config
    private int sampleRate = 48000;
    private int channelConfig = AudioFormat.CHANNEL_IN_MONO;
    private int audioFormat = AudioFormat.ENCODING_PCM_16BIT;
    private int bufferSize;
    private int codec = Protocol.CODEC_PCM;

    public class LocalBinder extends Binder {
        AudioStreamService getService() {
            return AudioStreamService.this;
        }
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return binder;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        networkClient = new NetworkClient();

        networkClient.setListener(new NetworkClient.Listener() {
            @Override
            public void onConnected() {
                if (statusListener != null) statusListener.onConnected(getServerHost());
                startRecording();
            }

            @Override
            public void onDisconnected(String reason) {
                stopRecording();
                if (statusListener != null) statusListener.onDisconnected(reason);
                updateNotification("Disconnected");
            }

            @Override
            public void onError(String error) {
                if (statusListener != null) statusListener.onError(error);
            }

            @Override
            public void onLatencyUpdate(long latencyMs) {
                if (statusListener != null) statusListener.onLatencyUpdate(latencyMs);
            }
        });
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(NOTIFICATION_ID, buildNotification("Starting..."));
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        disconnect();
        releaseWakeLock();
        super.onDestroy();
    }

    public void setStatusListener(StatusListener listener) {
        this.statusListener = listener;
    }

    public void connect(String host, int port) {
        loadSettings();
        acquireWakeLock();
        updateNotification("Connecting to " + host + ":" + port + "...");
        if (statusListener != null) statusListener.onStatusChanged("Connecting...");

        String deviceName = Build.MANUFACTURER + " " + Build.MODEL;
        int channels = (channelConfig == AudioFormat.CHANNEL_IN_STEREO) ? 2 : 1;
        networkClient.connect(host, port, sampleRate, channels, codec, deviceName);
    }

    public void disconnect() {
        stopRecording();
        networkClient.disconnect();
        releaseWakeLock();
        updateNotification("Disconnected");
        if (statusListener != null) statusListener.onStatusChanged("Disconnected");
    }

    public boolean isConnected() {
        return networkClient.isConnected();
    }

    public void setMuted(boolean muted) {
        isMuted = muted;
        if (networkClient.isConnected()) {
            networkClient.sendControl(
                    muted ? Protocol.CTRL_MUTE : Protocol.CTRL_UNMUTE, 0);
        }
    }

    public boolean isMuted() {
        return isMuted;
    }

    private void loadSettings() {
        SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(this);
        String rateStr = prefs.getString("sample_rate", "48000");
        sampleRate = Integer.parseInt(rateStr);

        boolean stereo = prefs.getBoolean("stereo", false);
        channelConfig = stereo ? AudioFormat.CHANNEL_IN_STEREO : AudioFormat.CHANNEL_IN_MONO;

        String codecStr = prefs.getString("codec", "0");
        codec = Integer.parseInt(codecStr);
    }

    private String getServerHost() {
        SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(this);
        return prefs.getString("server_ip", "192.168.1.1");
    }

    private void startRecording() {
        if (isRecording) return;

        bufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat);
        if (bufferSize == AudioRecord.ERROR || bufferSize == AudioRecord.ERROR_BAD_VALUE) {
            bufferSize = sampleRate * 2; // fallback: 1 sec buffer
        }
        bufferSize = Math.max(bufferSize, 4096);

        try {
            audioRecord = new AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    sampleRate,
                    channelConfig,
                    audioFormat,
                    bufferSize
            );

            if (audioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
                if (statusListener != null) statusListener.onError("AudioRecord init failed");
                return;
            }

            audioRecord.startRecording();
            isRecording = true;
            attachNoiseSuppressor();
            initEncoder();
            updateNotification("Streaming...");

            recordThread = new Thread(this::recordLoop, "VoiceMic-Record");
            recordThread.setPriority(Thread.MAX_PRIORITY);
            recordThread.start();

            if (statusListener != null) statusListener.onStatusChanged("Streaming");

        } catch (SecurityException e) {
            Log.e(TAG, "No mic permission", e);
            if (statusListener != null) statusListener.onError("Microphone permission denied");
        } catch (Exception e) {
            Log.e(TAG, "Record start failed", e);
            if (statusListener != null) statusListener.onError("Failed to start recording: " + e.getMessage());
        }
    }

    private void initEncoder() {
        if (codec == Protocol.CODEC_OPUS) {
            int channels = (channelConfig == AudioFormat.CHANNEL_IN_STEREO) ? 2 : 1;
            int bitRate = 64000; // 64 kbps
            audioEncoder = new AudioEncoder(sampleRate, channels, bitRate);
            if (!audioEncoder.init()) {
                Log.w(TAG, "Opus not available, falling back to PCM");
                audioEncoder = null;
            }
        }
    }

    private void releaseEncoder() {
        if (audioEncoder != null) {
            audioEncoder.release();
            audioEncoder = null;
        }
    }

    private void recordLoop() {
        // Use 20ms frames
        int frameSize = (sampleRate / 50) * 2; // 20ms of 16-bit mono
        if (channelConfig == AudioFormat.CHANNEL_IN_STEREO) frameSize *= 2;

        byte[] buffer = new byte[frameSize];

        while (isRecording && networkClient.isConnected()) {
            int read = audioRecord.read(buffer, 0, frameSize);
            if (read > 0) {
                // Calculate audio level for UI
                if (statusListener != null) {
                    float level = calculateLevel(buffer, read);
                    statusListener.onAudioLevel(level);
                }

                if (!isMuted) {
                    if (audioEncoder != null) {
                        byte[] encoded = audioEncoder.encode(buffer, 0, read);
                        if (encoded != null && encoded.length > 0) {
                            networkClient.sendAudio(encoded);
                        }
                    } else {
                        networkClient.sendAudio(buffer, 0, read);
                    }
                }
            } else if (read < 0) {
                Log.e(TAG, "AudioRecord read error: " + read);
                break;
            }
        }
    }

    private float calculateLevel(byte[] buffer, int length) {
        long sum = 0;
        int samples = length / 2;
        for (int i = 0; i < length - 1; i += 2) {
            short sample = (short) ((buffer[i] & 0xFF) | (buffer[i + 1] << 8));
            sum += Math.abs(sample);
        }
        float avg = (float) sum / samples;
        return Math.min(1.0f, avg / 16384.0f);
    }

    private void attachNoiseSuppressor() {
        SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(this);
        boolean nsEnabled = prefs.getBoolean("noise_suppression", false);
        if (!nsEnabled || audioRecord == null) return;

        if (NoiseSuppressor.isAvailable()) {
            try {
                noiseSuppressor = NoiseSuppressor.create(audioRecord.getAudioSessionId());
                if (noiseSuppressor != null) {
                    noiseSuppressor.setEnabled(true);
                    Log.i(TAG, "NoiseSuppressor attached");
                }
            } catch (Exception e) {
                Log.w(TAG, "NoiseSuppressor failed: " + e.getMessage());
            }
        } else {
            Log.w(TAG, "NoiseSuppressor not available on this device");
        }
    }

    private void releaseNoiseSuppressor() {
        if (noiseSuppressor != null) {
            try {
                noiseSuppressor.setEnabled(false);
                noiseSuppressor.release();
            } catch (Exception ignored) {}
            noiseSuppressor = null;
        }
    }

    private void stopRecording() {
        isRecording = false;
        if (recordThread != null) {
            try {
                recordThread.join(2000);
            } catch (InterruptedException ignored) {}
            recordThread = null;
        }
        releaseNoiseSuppressor();
        releaseEncoder();
        if (audioRecord != null) {
            try {
                audioRecord.stop();
                audioRecord.release();
            } catch (Exception ignored) {}
            audioRecord = null;
        }
    }

    private void acquireWakeLock() {
        if (wakeLock == null) {
            PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "VoiceMic::Streaming");
            wakeLock.acquire(60 * 60 * 1000L); // 1 hour max
        }
    }

    private void releaseWakeLock() {
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
            wakeLock = null;
        }
    }

    // ── Notifications ──

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID, "VoiceMic Streaming",
                    NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Shows when VoiceMic is streaming audio");
            NotificationManager nm = getSystemService(NotificationManager.class);
            nm.createNotificationChannel(channel);
        }
    }

    private Notification buildNotification(String status) {
        Intent intent = new Intent(this, MainActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pi = PendingIntent.getActivity(this, 0, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        return new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("VoiceMic")
                .setContentText(status)
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setContentIntent(pi)
                .setOngoing(true)
                .build();
    }

    private void updateNotification(String status) {
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.notify(NOTIFICATION_ID, buildNotification(status));
    }
}
