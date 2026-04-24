package com.example.robot_application_old;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.WindowManager;

import androidx.annotation.NonNull;

import com.sanbot.opensdk.base.TopBaseActivity;
import com.sanbot.opensdk.beans.FuncConstant;
import com.sanbot.opensdk.function.beans.speech.Grammar;
import com.sanbot.opensdk.function.beans.speech.RecognizeTextBean;
import com.sanbot.opensdk.function.unit.SpeechManager;
import com.sanbot.opensdk.function.unit.interfaces.speech.RecognizeListener;
import com.sanbot.opensdk.function.beans.speech.SpeakStatus;
import com.sanbot.opensdk.function.unit.interfaces.speech.SpeakListener;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;


public class RobotClientActivity extends TopBaseActivity {

    private SpeechManager speechManager;
    private Handler handler = new Handler(Looper.getMainLooper());

    /**
     * LISTENER
     * **/
    // Variabili di stato
    private StringBuilder sentenceBuffer = new StringBuilder();
    private boolean isRetryMode = false;
    private boolean isWaitingForServer = false; //blocca l'ascolto finché il server non risponde

    // Gestione del silenzio
    private String serverPostUrl = "http://10.202.155.212:8000/input";

    /**
     * SPEAKER
     * **/
    private String serverUrl = "http://10.202.155.212:8000/command";

    // =========================
    // LIFECYCLE
    // =========================
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        register(RobotClientActivity.class);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        super.onCreate(savedInstanceState);
    }

    @Override
    protected void onMainServiceConnected() {
        Log.i("ROBOT_TEST", "Servizio connesso ...");
        speechManager = (SpeechManager) getUnitManager(FuncConstant.SPEECH_MANAGER);

        startConversation();
    }


    private void startPolling() {
        if(!isWaitingForServer) return ;
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
                            && speechManager != null) {
                        isWaitingForServer = false;
                        runOnUiThread(() -> speakAndThenWakeUp(command));
                        return;
                    }
                }

                conn.disconnect();

            } catch (Exception e) {
                Log.e("ROBOT", "Errore connessione server: " + e.getMessage());
            }
            // Se non c'è ancora risposta, riprova tra 2 secondi
            if (isWaitingForServer) {
                handler.postDelayed(this::startPolling, 2000);
            }
        }).start();
    }

    private void startConversation() {
        isRetryMode = false;
        speakAndThenWakeUp("Ciao, dimmi qualcosa!");
    }

    private void speakAndThenWakeUp(String message) {
        speechManager.setOnSpeechListener(new SpeakListener() {
            @Override
            public void onSpeakStatus(@NonNull SpeakStatus speakStatus) {
                if (speakStatus.getProgress() == 100) {
                    handler.postDelayed(() -> {
                        initSpeechListener();
                        speechManager.doWakeUp();
                    }, 500);
                }
            }
        });
        speechManager.startSpeak(message);
    }


    private void initSpeechListener() {
        speechManager.setOnSpeechListener(new RecognizeListener() {
            @Override
            public void onStartRecognize() {
                Log.i("ROBOT_TEST", "Microfono APERTO");
            }

            @Override
            public void onRecognizeText(RecognizeTextBean bean) {
                if (bean != null && bean.getText() != null && !bean.getText().isEmpty()) {
                    String text = bean.getText().toLowerCase().trim();
                    Log.i("ROBOT_TEST", "TRASCRIZIONE: " + text);

                    // Gestione comando di chiusura
                    if (text.contains("fine") || text.contains("chiudi")) {
                        speechManager.setOnSpeechListener(new SpeakListener() {
                            @Override
                            public void onSpeakStatus(@NonNull SpeakStatus speakStatus) {
                                if (speakStatus.getProgress() == 100) {
                                    handler.postDelayed(() -> speechManager.doSleep(), 500);
                                }
                            }
                        });
                        speechManager.startSpeak("Ok , ciao! ");
                    }

                    if (isRetryMode) {
                        handleRetryResponse(text);
                    } else {
                        // Caso normale: manda al server
                        sendTextToServer(text);
                        isWaitingForServer = true;
                        startPolling();
                    }
                }
            }

            @Override
            public void onStopRecognize() {
                Log.i("ROBOT_TEST", "Microfono CHIUSO");
            }

            @Override
            public void onError(int i, int i1) {
                Log.e("ROBOT_TEST", "Errore: " + i + " (" + i1 + ")");
                if (i1 == 20005 || i == 4) {
                    Log.i("ROBOT_TEST", "Silenzio rilevato, entro in Retry Mode");
                    askForHelp();
                }
            }

            @Override
            public boolean onRecognizeResult(Grammar grammar) {
                if (grammar != null) {
                    Log.i("ROBOT_TEST", "Risultato Grammar: " + grammar.getText());
                }
                return true;
            }

            @Override
            public void onRecognizeVolume(int i) {
                // Questo log ti dice se il microfono sente rumore fisico
                if (i > 10) {
                    Log.d("ROBOT_TEST", "Volume rilevato: " + i);
                }
            }
        });
    }

    private void askForHelp() {
        isRetryMode = true;
        speakAndThenWakeUp("Non ho sentito nulla. Posso esserti d'aiuto in qualche modo? ");
    }

    private void handleRetryResponse(String text) {
        if (text.contains("no")) {
            isRetryMode = false;
            // Parla e NON svegliarti (così il microfono resta spento)
            speechManager.setOnSpeechListener(new SpeakListener() {
                @Override
                public void onSpeakStatus(@NonNull SpeakStatus speakStatus) {
                    if (speakStatus.getProgress() == 100) {
                        handler.postDelayed(() -> speechManager.doSleep(), 500);
                    }
                }
            });
            speechManager.startSpeak("Ok allora mi riposo ");
        } else {
            // Se dice "Sì" o qualsiasi altra cosa, torna in modalità normale
            isRetryMode = false;
            speakAndThenWakeUp("Bene , sono qui per ascoltarti ! ");
        }
    }

    // =========================
    // COMUNICAZIONE SERVER
    // =========================
    private void sendTextToServer(String text) {
        // Le chiamate di rete su Android devono essere fatte in un thread separato
        new Thread(() -> {
            try {
                java.net.URL url = new java.net.URL(serverPostUrl);

                java.net.HttpURLConnection conn = (java.net.HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                conn.setDoOutput(true);

                // Formatta il testo in JSON (fai attenzione a eventuali virgolette nel testo)
                String safeText = text.replace("\"", "\\\"");
                String json = "{\"text\":\"" + safeText + "\"}";

                java.io.OutputStream os = conn.getOutputStream();
                os.write(json.getBytes("utf-8"));
                os.flush();
                os.close();

                int responseCode = conn.getResponseCode();
                Log.i("ROBOT", "Server Response Code: " + responseCode);

                conn.disconnect();

            } catch (Exception e) {
                Log.e("ROBOT", "Errore invio server: " + e.getMessage());
            }
        }).start();
    }
}