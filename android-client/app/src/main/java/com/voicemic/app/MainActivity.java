package com.voicemic.app;

import android.Manifest;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.preference.PreferenceManager;

import com.google.android.material.button.MaterialButton;
import com.google.android.material.card.MaterialCardView;

/**
 * Main activity — connection screen with status, audio level, and controls.
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
    private EditText ipInput;
    private EditText portInput;
    private MaterialButton connectBtn;
    private MaterialButton muteBtn;
    private TextView statusText;
    private TextView latencyText;
    private TextView deviceInfoText;
    private ProgressBar audioLevelBar;
    private View connectedCard;

    // Service
    private AudioStreamService streamService;
    private boolean serviceBound = false;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private final ServiceConnection serviceConnection = new ServiceConnection() {
        @Override
        public void onServiceConnected(ComponentName name, IBinder binder) {
            AudioStreamService.LocalBinder localBinder = (AudioStreamService.LocalBinder) binder;
            streamService = localBinder.getService();
            serviceBound = true;
            streamService.setStatusListener(statusListener);
            updateUIState();
            tryAutoConnect();
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
            mainHandler.post(() -> {
                statusText.setText(status);
                updateUIState();
            });
        }

        @Override
        public void onConnected(String serverIp) {
            mainHandler.post(() -> {
                statusText.setText("Connected to " + serverIp);
                connectBtn.setText("Disconnect");
                connectBtn.setIconResource(android.R.drawable.ic_menu_close_clear_cancel);
                connectedCard.setVisibility(View.VISIBLE);
                applyKeepScreenOn(true);
                updateUIState();
            });
        }

        @Override
        public void onDisconnected(String reason) {
            mainHandler.post(() -> {
                statusText.setText("Disconnected: " + reason);
                connectBtn.setText("Connect");
                connectBtn.setIconResource(android.R.drawable.ic_menu_send);
                connectedCard.setVisibility(View.GONE);
                audioLevelBar.setProgress(0);
                latencyText.setText("— ms");
                applyKeepScreenOn(false);
                updateUIState();
            });
        }

        @Override
        public void onError(String error) {
            mainHandler.post(() -> {
                statusText.setText("Error: " + error);
                Toast.makeText(MainActivity.this, error, Toast.LENGTH_LONG).show();
                updateUIState();
            });
        }

        @Override
        public void onLatencyUpdate(long ms) {
            mainHandler.post(() -> latencyText.setText(ms + " ms"));
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

        // Find views
        ipInput = findViewById(R.id.ip_input);
        portInput = findViewById(R.id.port_input);
        connectBtn = findViewById(R.id.connect_btn);
        muteBtn = findViewById(R.id.mute_btn);
        statusText = findViewById(R.id.status_text);
        latencyText = findViewById(R.id.latency_text);
        deviceInfoText = findViewById(R.id.device_info_text);
        audioLevelBar = findViewById(R.id.audio_level_bar);
        connectedCard = findViewById(R.id.connected_card);

        // Load saved IP/port
        SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(this);
        ipInput.setText(prefs.getString("server_ip", "192.168.1.1"));
        portInput.setText(prefs.getString("server_port", "8125"));

        // Device info
        deviceInfoText.setText(Build.MANUFACTURER + " " + Build.MODEL);

        // Connect button
        connectBtn.setOnClickListener(v -> onConnectClicked());

        // Mute button
        muteBtn.setOnClickListener(v -> onMuteClicked());

        // Initially hide connected card
        connectedCard.setVisibility(View.GONE);

        // Request permissions
        requestPermissions();
    }

    @Override
    protected void onStart() {
        super.onStart();
        // Start and bind to service
        Intent intent = new Intent(this, AudioStreamService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
        bindService(intent, serviceConnection, Context.BIND_AUTO_CREATE);
    }

    @Override
    protected void onStop() {
        super.onStop();
        if (serviceBound) {
            unbindService(serviceConnection);
            serviceBound = false;
        }
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        getMenuInflater().inflate(R.menu.main_menu, menu);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(@NonNull MenuItem item) {
        if (item.getItemId() == R.id.action_settings) {
            startActivity(new Intent(this, SettingsActivity.class));
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    private void onConnectClicked() {
        if (!serviceBound) return;

        if (streamService.isConnected()) {
            streamService.disconnect();
        } else {
            String ip = ipInput.getText().toString().trim();
            String portStr = portInput.getText().toString().trim();

            if (ip.isEmpty()) {
                ipInput.setError("Enter server IP");
                return;
            }

            int port;
            try {
                port = Integer.parseInt(portStr);
            } catch (NumberFormatException e) {
                portInput.setError("Invalid port");
                return;
            }

            // Save for next time
            SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(this);
            prefs.edit()
                    .putString("server_ip", ip)
                    .putString("server_port", portStr)
                    .apply();

            statusText.setText("Connecting...");
            connectBtn.setEnabled(false);
            streamService.connect(ip, port);
        }
    }

    private void onMuteClicked() {
        if (!serviceBound) return;
        boolean newMuted = !streamService.isMuted();
        streamService.setMuted(newMuted);
        muteBtn.setText(newMuted ? "Unmute" : "Mute");
        muteBtn.setIconResource(newMuted ?
                android.R.drawable.ic_lock_silent_mode :
                android.R.drawable.ic_lock_silent_mode_off);
    }

    private void updateUIState() {
        if (!serviceBound) return;
        boolean connected = streamService.isConnected();
        connectBtn.setEnabled(true);
        connectBtn.setText(connected ? "Disconnect" : "Connect");
        ipInput.setEnabled(!connected);
        portInput.setEnabled(!connected);
        muteBtn.setEnabled(connected);
    }

    private void tryAutoConnect() {
        if (!serviceBound || streamService.isConnected()) return;
        SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(this);
        boolean autoConnect = prefs.getBoolean("auto_connect", false);
        if (!autoConnect) return;

        String ip = prefs.getString("server_ip", "");
        String portStr = prefs.getString("server_port", "8125");
        if (ip.isEmpty()) return;

        // Check permissions first
        boolean hasAudioPerm = ContextCompat.checkSelfPermission(this,
                Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
        if (!hasAudioPerm) return;

        int port;
        try {
            port = Integer.parseInt(portStr);
        } catch (NumberFormatException e) {
            return;
        }

        statusText.setText("Auto-connecting...");
        connectBtn.setEnabled(false);
        mainHandler.postDelayed(() -> streamService.connect(ip, port), 500);
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
