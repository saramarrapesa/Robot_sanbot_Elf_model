package com.example.robot_application_old;

import com.sanbot.opensdk.base.TopBaseActivity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.widget.TextView;

import com.sanbot.opensdk.beans.FuncConstant;
import com.sanbot.opensdk.function.beans.speech.Grammar;
import com.sanbot.opensdk.function.beans.speech.RecognizeTextBean;
import com.sanbot.opensdk.function.unit.SpeechManager;
import com.sanbot.opensdk.function.unit.interfaces.speech.RecognizeListener;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import org.json.JSONObject;


public class RobotClientActivity extends TopBaseActivity {
    private SpeechManager speechManager;

    private Handler handler = new Handler(Looper.getMainLooper());

    private String serverGetUrl = "http://10.202.155.212:8000/command";
    private String serverPostUrl = "http://10.202.155.212:8000/input";

    private boolean isPolling = false;
    private boolean isActive = false;

    private String lastCommand = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
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
        initSpeechListener();
        // Avvia ascolto
        speechManager.doSleep();
        speechManager.doWakeUp();
        startPolling();
    }

    @Override
    protected void onResume() {
        super.onResume();
        isActive = true;

        Log.i("ROBOT", "onResume");

        if (speechManager != null) {
            speechManager.doWakeUp();
        }

        if (!isPolling) {
            startPolling();
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        isActive = false;
        Log.i("ROBOT", "onPause");

        stopPolling();
    }

    private void startPolling() {
        if (isPolling) return;

        isPolling = true;
        handler.postDelayed(pollRunnable, 2000);
    }

    private void stopPolling() {
        isPolling = false;
        handler.removeCallbacks(pollRunnable);
    }

    private Runnable pollRunnable = new Runnable() {
        @Override
        public void run() {
            if (!isPolling) return;

            getCommandFromServer();

            handler.postDelayed(this, 5000);
        }
    };

    //listener vocale
    private void initSpeechListener() {
        speechManager.setOnSpeechListener(new RecognizeListener() {

            @Override
            public boolean onRecognizeResult(Grammar grammar) {
                return false;
            }

            @Override
            public void onRecognizeText(RecognizeTextBean recognizeTextBean) {
                String text = recognizeTextBean.getText();

                Log.i("ROBOT", "Hai detto: " + text);

                sendTextToServer(text);
            }

            @Override
            public void onRecognizeVolume(int i) {
                Log.i("ROBOT", "Volume: " + i);
            }

            @Override
            public void onStartRecognize() {
                Log.i("ROBOT", "In ascolto...");
            }

            @Override
            public void onStopRecognize() {
                Log.i("ROBOT", "Fine ascolto");

                // Riattiva ascolto continuo
                if (speechManager != null && isActive) {
                    speechManager.doWakeUp();
                }
            }

            @Override
            public void onError(int i, int i1) {
                Log.e("ROBOT", "Errore riconoscimento: " + i + " - " + i1);

                if (speechManager != null && isActive) {
                    speechManager.doSleep();

                    handler.postDelayed(() -> {
                        speechManager.doWakeUp();
                    }, 1000);
                }
            }
        });
    }


    private void sendTextToServer(String text) {
        new Thread(() -> {
            try {
                URL url = new URL(serverPostUrl);

                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);

                String jsonInput = "{\"text\":\"" + text + "\"}";

                OutputStream os = conn.getOutputStream();
                os.write(jsonInput.getBytes());
                os.flush();
                os.close();

                int responseCode = conn.getResponseCode();
                Log.i("ROBOT", "POST response: " + responseCode);

                conn.disconnect();

            } catch (Exception e) {
                Log.e("ROBOT", "Errore invio testo: " + e.getMessage());
            }
        }).start();
    }

    private void getCommandFromServer() {
        new Thread(() -> {
            try {
                URL url = new URL(serverGetUrl);

                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(5000);

                if (conn.getResponseCode() == 200) {

                    BufferedReader reader = new BufferedReader(
                            new InputStreamReader(conn.getInputStream())
                    );

                    String result = reader.readLine();
                    reader.close();

                    Log.i("ROBOT", "Ricevuto: " + result);

                    if (result == null || result.isEmpty()) return;

                    JSONObject json = new JSONObject(result);
                    String command = json.optString("command", "");

                    if (!command.isEmpty()
                            && !command.equals("null")
                            && !command.equals(lastCommand)
                            && speechManager != null
                            && isActive) {

                        lastCommand = command;

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
                Log.e("ROBOT", "Errore GET: " + e.getMessage());
            }
        }).start();
    }
}
