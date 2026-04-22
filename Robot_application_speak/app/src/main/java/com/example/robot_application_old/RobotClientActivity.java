package com.example.robot_application_old;

import com.sanbot.opensdk.base.TopBaseActivity;
import android.os.Bundle;
import android.os.Handler;
import android.util.Log;
import android.widget.TextView;

import com.sanbot.opensdk.beans.FuncConstant;
import com.sanbot.opensdk.function.unit.SpeechManager;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import org.json.JSONObject;


public class RobotClientActivity extends TopBaseActivity {
    private SpeechManager speechManager;
    private Handler handler = new Handler();
    private String serverUrl = "http://10.202.155.212:8000/command";
    private boolean isPolling = false;
    private boolean isActive = false;
    //private TextView tvOutput;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        //tvOutput = findViewById(R.id.tv_output);
        // 1. Prima registriamo l'attività
        register(RobotClientActivity.class);
        super.onCreate(savedInstanceState);
    }

    /**
     * Questo metodo viene chiamato AUTOMATICAMENTE quando il robot è pronto
     */
    @Override
    protected void onMainServiceConnected() {
        Log.i("ROBOT", "Servizio Main connesso! Inizializzo hardware...");

        // 2. Inizializziamo lo speechManager qui (quando siamo sicuri che il robot risponda)
        speechManager = (SpeechManager) getUnitManager(FuncConstant.SPEECH_MANAGER);

        // 3. Facciamo partire il polling solo ora
        startPolling();
    }
    @Override
    protected void onResume() {
        super.onResume();
        isActive = true;
        Log.i("ROBOT", "onResume");

        if (speechManager != null && !isPolling) {
            startPolling();
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        isActive = false;
        Log.i("ROBOT", "onPause - fermo polling");

        stopPolling();
    }

    private Runnable pollRunnable = new Runnable() {
        @Override
        public void run() {
            if (!isPolling) return;

            getCommandFromServer();

            handler.postDelayed(this, 5000);
        }
    };

    private void stopPolling() {
        isPolling = false;
        handler.removeCallbacks(pollRunnable);
    }


    private void startPolling() {
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                getCommandFromServer();
                handler.postDelayed(this, 5000);
            }
        }, 2000);
    }


    private void getCommandFromServer() {
        new Thread(() -> {
            try {
                URL url = new URL(serverUrl);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(5000);

                if (conn.getResponseCode() == 200) {

                    BufferedReader reader = new BufferedReader(
                            new InputStreamReader(conn.getInputStream())
                    );

                    String result = reader.readLine();
                    reader.close();

                    Log.i("ROBOT", "Ricevuto RAW: " + result);

                    if (result == null || result.isEmpty()) return;

                    JSONObject json = new JSONObject(result);

                    String command = json.optString("command", "");

                    Log.i("ROBOT", "Comando parsato: " + command);

                    if (!command.isEmpty()
                            && !command.equals("null")
                            && speechManager != null
                            && isActive) {

                        runOnUiThread(() -> {
                            try {
                                speechManager.startSpeak(command);
                            } catch (Exception e) {
                                Log.e("ROBOT", "Errore speak: " + e.getMessage());
                            }
                        });
                    }
                }

                conn.disconnect();

            } catch (Exception e) {
                Log.e("ROBOT", "Errore connessione server: " + e.getMessage());
            }
        }).start();
    }
}
