package com.voicemic.app;

import android.Manifest;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.PorterDuff;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.Toolbar;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.preference.PreferenceManager;

/**
 * Main activity — VoiceMic server interface.
 * Toolbar with Play/Stop, centered mic icon, status text, IP:port display.
 */
public class MainActivity extends AppCompatActivity {

    private static final int PERM_REQUEST_CODE = 100;
    private static final String[] REQUIRED_PERMISSIONS;

    static {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            REQUIRED_PERMISSIONS = new String[]{
                    Manifest.permission.RECORD_AUDIO,
                    Manifest.permission.POST_NOTIFICATIONS,
            };
        } else {
            REQUIRED_PERMISSIONS = new String[]{
                    Manifest.permission.RECORD_AUDIO,
            };
        }
    }

    // UI
    private ImageView micIcon;
    private TextView statusText;
    private TextView ipText;
    private ProgressBar audioLevelBar;
    private ImageView muteBtn;
    private MenuItem playMenuItem;
    private MenuItem stopMenuItem;

    private boolean serverRunning = false;
    private boolean isMuted = false;

    // Service
    private AudioStreamService streamService;
    private boolean serviceBound = false;
    private boolean pendingPlay = false;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private final ServiceConnection serviceConnection = new ServiceConnection() {
        @Override
        public void onServiceConnected(ComponentName name, IBinder binder) {
            AudioStreamService.LocalBinder localBinder = (AudioStreamService.LocalBinder) binder;
            streamService = localBinder.getService();
            serviceBound = true;
            streamService.setStatusListener(statusListener);

            if (pendingPlay) {
                pendingPlay = false;
                doStartServer();
            } else {
                updateUIState();
            }
        }

        @Override
        public void onServiceDisconnected(ComponentName name) {
            serviceBound = false;
            streamService = null;
        }
    };

    private final AudioStreamService.StatusListener statusListener = new AudioStreamService.StatusListener() {
        @Override
        public void onStatusChanged(String status) {
            mainHandler.post(() -> statusText.setText(status));
        }

        @Override
        public void onConnected(String clientInfo) {
            mainHandler.post(() -> {
                statusText.setText("Connected");
                micIcon.setColorFilter(Color.parseColor("#4CAF50"), PorterDuff.Mode.SRC_IN);
                audioLevelBar.setVisibility(View.VISIBLE);
                muteBtn.setVisibility(View.VISIBLE);
                applyKeepScreenOn(true);
            });
        }

        @Override
        public void onDisconnected(String reason) {
            mainHandler.post(() -> {
                if (serverRunning) {
                    statusText.setText("Waiting for connection...");
                    micIcon.setColorFilter(Color.parseColor("#FF9800"), PorterDuff.Mode.SRC_IN);
                } else {
                    statusText.setText("Idle");
                    micIcon.setColorFilter(Color.parseColor("#808080"), PorterDuff.Mode.SRC_IN);
                    ipText.setVisibility(View.GONE);
                }
                audioLevelBar.setVisibility(View.GONE);
                audioLevelBar.setProgress(0);
                muteBtn.setVisibility(View.GONE);
                applyKeepScreenOn(false);
            });
        }

        @Override
        public void onError(String error) {
            mainHandler.post(() -> {
                Toast.makeText(MainActivity.this, error, Toast.LENGTH_LONG).show();
                statusText.setText("Error");
                micIcon.setColorFilter(Color.parseColor("#F44336"), PorterDuff.Mode.SRC_IN);
            });
        }

        @Override
        public void onLatencyUpdate(long ms) {
            // latency info not shown on main screen in original
        }

        @Override
        public void onAudioLevel(float level) {
            mainHandler.post(() -> audioLevelBar.setProgress((int) (level * 100)));
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // Set Toolbar as ActionBar
        Toolbar toolbar = findViewById(R.id.toolbar);
        setSupportActionBar(toolbar);

        // Find views
        micIcon = findViewById(R.id.mic_icon);
        statusText = findViewById(R.id.status_text);
        ipText = findViewById(R.id.ip_text);
        audioLevelBar = findViewById(R.id.audio_level_bar);
        muteBtn = findViewById(R.id.mute_btn);

        // Mute button
        muteBtn.setOnClickListener(v -> onMuteClicked());

        // Request permissions on start
        requestPermissions();
    }

    @Override
    protected void onStop() {
        super.onStop();
        if (serviceBound) {
            unbindService(serviceConnection);
            serviceBound = false;
        }
    }

    // ── Menu ──

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        getMenuInflater().inflate(R.menu.main_menu, menu);
        playMenuItem = menu.findItem(R.id.action_play);
        stopMenuItem = menu.findItem(R.id.action_stop);
        updateMenuState();
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(@NonNull MenuItem item) {
        int id = item.getItemId();
        if (id == R.id.action_play) {
            onPlayClicked();
            return true;
        } else if (id == R.id.action_stop) {
            onStopClicked();
            return true;
        } else if (id == R.id.action_settings) {
            startActivity(new Intent(this, SettingsActivity.class));
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    // ── Actions ──

    private void onPlayClicked() {
        // Check permissions first
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions();
            return;
        }

        // Start and bind to service
        Intent intent = new Intent(this, AudioStreamService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }

        if (serviceBound) {
            doStartServer();
        } else {
            pendingPlay = true;
            bindService(intent, serviceConnection, Context.BIND_AUTO_CREATE);
        }
    }

    private void doStartServer() {
        if (!serviceBound) return;

        SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(this);
        int port = Integer.parseInt(prefs.getString("server_port", "8125"));
        String transport = prefs.getString("transport", "wifi");

        serverRunning = true;
        streamService.startServer(port);

        // Show IP:port like original
        String ip = getLocalIpAddress();
        String transportLabel = "Wi-Fi";
        switch (transport) {
            case "usb": transportLabel = "USB"; break;
            case "bluetooth": transportLabel = "Bluetooth"; break;
            case "wifi_direct": transportLabel = "Wi-Fi Direct"; break;
        }

        statusText.setText("Waiting for connection...");
        ipText.setText(transportLabel + ": " + ip + ":" + port);
        ipText.setVisibility(View.VISIBLE);
        micIcon.setColorFilter(Color.parseColor("#FF9800"), PorterDuff.Mode.SRC_IN);
        updateMenuState();
    }

    private void onStopClicked() {
        if (serviceBound) {
            streamService.stopServer();
        }

        serverRunning = false;
        statusText.setText("Idle");
        ipText.setVisibility(View.GONE);
        micIcon.setColorFilter(Color.parseColor("#808080"), PorterDuff.Mode.SRC_IN);
        audioLevelBar.setVisibility(View.GONE);
        muteBtn.setVisibility(View.GONE);
        updateMenuState();
        applyKeepScreenOn(false);
    }

    private void onMuteClicked() {
        if (!serviceBound) return;
        isMuted = !isMuted;
        streamService.setMuted(isMuted);
        if (isMuted) {
            muteBtn.setColorFilter(Color.parseColor("#F44336"), PorterDuff.Mode.SRC_IN);
        } else {
            muteBtn.setColorFilter(Color.WHITE, PorterDuff.Mode.SRC_IN);
        }
    }

    // ── UI helpers ──

    private void updateUIState() {
        if (!serviceBound) return;
        serverRunning = streamService.isServerRunning();
        boolean connected = streamService.isConnected();

        if (connected) {
            statusText.setText("Connected");
            micIcon.setColorFilter(Color.parseColor("#4CAF50"), PorterDuff.Mode.SRC_IN);
            audioLevelBar.setVisibility(View.VISIBLE);
            muteBtn.setVisibility(View.VISIBLE);
            ipText.setVisibility(View.VISIBLE);
        } else if (serverRunning) {
            statusText.setText("Waiting for connection...");
            micIcon.setColorFilter(Color.parseColor("#FF9800"), PorterDuff.Mode.SRC_IN);
            ipText.setVisibility(View.VISIBLE);
        } else {
            statusText.setText("Idle");
            micIcon.setColorFilter(Color.parseColor("#808080"), PorterDuff.Mode.SRC_IN);
            ipText.setVisibility(View.GONE);
            audioLevelBar.setVisibility(View.GONE);
            muteBtn.setVisibility(View.GONE);
        }
        updateMenuState();
    }

    private void updateMenuState() {
        if (playMenuItem == null || stopMenuItem == null) return;
        playMenuItem.setVisible(!serverRunning);
        stopMenuItem.setVisible(serverRunning);
    }

    private void applyKeepScreenOn(boolean on) {
        SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(this);
        boolean keepScreenOn = prefs.getBoolean("keep_screen_on", false);
        if (keepScreenOn && on) {
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        } else {
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        }
    }

    @SuppressWarnings("deprecation")
    private String getLocalIpAddress() {
        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(WIFI_SERVICE);
            WifiInfo wi = wm.getConnectionInfo();
            int ipInt = wi.getIpAddress();
            if (ipInt != 0) {
                return String.format("%d.%d.%d.%d",
                        (ipInt & 0xff), (ipInt >> 8 & 0xff),
                        (ipInt >> 16 & 0xff), (ipInt >> 24 & 0xff));
            }
        } catch (Exception ignored) {}

        try {
            java.util.Enumeration<java.net.NetworkInterface> nis =
                    java.net.NetworkInterface.getNetworkInterfaces();
            while (nis.hasMoreElements()) {
                java.net.NetworkInterface ni = nis.nextElement();
                java.util.Enumeration<java.net.InetAddress> addrs = ni.getInetAddresses();
                while (addrs.hasMoreElements()) {
                    java.net.InetAddress addr = addrs.nextElement();
                    if (!addr.isLoopbackAddress() && addr instanceof java.net.Inet4Address) {
                        return addr.getHostAddress();
                    }
                }
            }
        } catch (Exception ignored) {}

        return "0.0.0.0";
    }

    private void requestPermissions() {
        boolean allGranted = true;
        for (String perm : REQUIRED_PERMISSIONS) {
            if (ContextCompat.checkSelfPermission(this, perm) != PackageManager.PERMISSION_GRANTED) {
                allGranted = false;
                break;
            }
        }
        if (!allGranted) {
            ActivityCompat.requestPermissions(this, REQUIRED_PERMISSIONS, PERM_REQUEST_CODE);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == PERM_REQUEST_CODE) {
            for (int result : grantResults) {
                if (result != PackageManager.PERMISSION_GRANTED) {
                    Toast.makeText(this, "Microphone permission is required!", Toast.LENGTH_LONG).show();
                    return;
                }
            }
        }
    }
}
