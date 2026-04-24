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




public class RobotClientActivity_old extends TopBaseActivity {

    private SpeechManager speechManager;
    private Handler handler = new Handler(Looper.getMainLooper());

    // Variabili di stato
    private StringBuilder sentenceBuffer = new StringBuilder();
    private boolean isRetryMode = false;
    private boolean hasSpoken = false;

    // Gestione del silenzio
    private Runnable initialSilenceRunnable;
    private static final long NO_INPUT_TIMEOUT = 6000; // 6 secondi per iniziare a parlare
    private String serverPostUrl = "http://10.202.155.212:8000/input";

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
        Log.i("ROBOT_TEST", "Service connected");
        speechManager = (SpeechManager) getUnitManager(FuncConstant.SPEECH_MANAGER);

        startConversation();
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

                    if (isRetryMode) {
                        handleRetryResponse(text);
                    } else {
                        // Caso normale: manda al server
                        sendTextToServer(text);
                        //speakAndThenWakeUp("Messaggio inviato. Vuoi dirmi altro?");
                    }
                }
            }

            @Override
            public void onStopRecognize() {
                Log.i("ROBOT_TEST", "Microfono CHIUSO");
                // Se si chiude da solo, riaccendilo per il test
                //handler.postDelayed(() -> speechManager.doWakeUp(), 500);
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