package com.example.robot_application_old;

import android.media.AudioRecord;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.sanbot.opensdk.function.beans.LED;
import com.sanbot.opensdk.function.beans.handmotion.CombinationHandMotion;
import com.sanbot.opensdk.function.beans.speech.Grammar;
import com.sanbot.opensdk.function.beans.speech.RecognizeTextBean;
import com.sanbot.opensdk.function.beans.speech.SpeakStatus;
import com.sanbot.opensdk.function.beans.wing.AbsoluteAngleWingMotion;
import com.sanbot.opensdk.function.beans.wing.NoAngleWingMotion;
import com.sanbot.opensdk.function.beans.wing.RelativeAngleWingMotion;
import com.sanbot.opensdk.function.unit.HandMotionManager;
import com.sanbot.opensdk.function.unit.HardWareManager;
import com.sanbot.opensdk.function.unit.HeadMotionManager;
import com.sanbot.opensdk.function.unit.SpeechManager;
import com.sanbot.opensdk.function.unit.WingMotionManager;
import com.sanbot.opensdk.function.unit.interfaces.speech.RecognizeListener;
import com.sanbot.opensdk.function.unit.interfaces.speech.SpeakListener;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.cert.CertificateException;

import javax.net.ssl.HostnameVerifier;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

import okhttp3.OkHttpClient;

public class ConversationManager {
    private SpeechManager speechManager;
    private Handler handler = new Handler(Looper.getMainLooper());

    private WingMotionManager wingMotionManager;
    private HardWareManager hardWareManager;

    private boolean isFirstTurn = false;

    private final String SERVER_INPUT_URL = "https://provoke-commodity-coral.ngrok-free.dev/input";
    private final String SERVER_COMMAND_URL = "https://provoke-commodity-coral.ngrok-free.dev/command";

    private boolean isWaitingForServer = false; //blocca l'ascolto finché il server non risponde
    private boolean isPollingActive = false;
    private boolean isRetryMode = false;

    private int timeoutCount = 0;
    private int silenceCount = 0;
    private boolean isWaitingForInitialGreeting = false;


    public ConversationManager (SpeechManager speechManager, WingMotionManager wingMotionManager, HardWareManager hardWareManager){
        this.speechManager = speechManager;
        this.wingMotionManager = wingMotionManager;
        this.hardWareManager = hardWareManager;

        setupUnsafeDefaultSSL();

    }

    private void setupUnsafeDefaultSSL() {
        try {
            final TrustManager[] trustAllCerts = new TrustManager[] {
                    new X509TrustManager() {
                        @Override
                        public void checkClientTrusted(java.security.cert.X509Certificate[] chain, String authType) throws CertificateException {}

                        @Override
                        public void checkServerTrusted(java.security.cert.X509Certificate[] chain, String authType) throws CertificateException {}

                        @Override
                        public java.security.cert.X509Certificate[] getAcceptedIssuers() {
                            return new java.security.cert.X509Certificate[]{};
                        }
                    }
            };

            final SSLContext sslContext = SSLContext.getInstance("SSL");
            sslContext.init(null, trustAllCerts, new java.security.SecureRandom());

            // Questo forza TUTTE le HttpURLConnection verso HTTPS ad accettare il bypass
            javax.net.ssl.HttpsURLConnection.setDefaultSSLSocketFactory(sslContext.getSocketFactory());
            javax.net.ssl.HttpsURLConnection.setDefaultHostnameVerifier(new HostnameVerifier() {
                @Override
                public boolean verify(String hostname, SSLSession session) {
                    return true; // Accetta ngrok e qualsiasi altro dominio di test
                }
            });
        } catch (Exception e) {
            Log.e("CONV_MANAGER", "Errore configurazione SSL globale: " + e.getMessage());
        }
    }

    //metodo chiamato dalla MainActivity quando la visione ha finito
    public void start(){
        isWaitingForInitialGreeting = false;
        isWaitingForServer = true;
        isRetryMode = false;
        isFirstTurn = true;

        //all'utente di parlare per primo , perciò si mette in ascolto
        initSpeechListener();
        speechManager.doWakeUp();
        startPolling();

        Log.i("CONV_MANAGER", "Conversazione avviata, in attesa di input o prompt fading...");
    }

    private void startPolling() {
        if (!isWaitingForServer || isPollingActive) return;
        //isFirstTurn = true;
        isPollingActive = true;

        handler.postDelayed(() ->{
            isPollingActive = false;
            getCommandFromServer();
        },2000);
    }

    /*devo rimuovere la gestione dell'iniziativa da parte dell'utente perché non può funzionare*/

    private void getCommandFromServer() {
        //if (!isWaitingForServer) return;
        new Thread(() -> {
            try {
                URL url = new URL(SERVER_COMMAND_URL);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setRequestProperty("ngrok-skip-browser-warning", "69420");

                if (conn.getResponseCode() == 200){
                    BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                    String result = reader.readLine();
                    reader.close();

                    if (result != null && !result.isEmpty()){
                        JSONObject json = new JSONObject(result);
                        String command = json.optString("command", "");

                        if(!command.isEmpty() && !command.equals("null")){
                            isWaitingForServer = false;
                            if(command.startsWith("[FEEDBACK_TRAINER]")){
                                String feedbackText = command.replace("[FEEDBACK_TRAINER]", "").trim();
                                speakAndThenSleep(feedbackText);
                            }else if(command.startsWith("[CLOSE]")){
                                String speechText = command.replace("[CLOSE]", "").trim();
                                speakAndKeepPolling(speechText);
                            }else if(command.startsWith("[END]")){
                                String speechText = command.replace("[END]", "").trim();
                                speakAndKeepPolling(speechText);
                            }else if(command.startsWith("[PROMPT_VISIVO]")){
                                String speechText = command.replace("[PROMPT_VISIVO]", "").trim();
                                speechManager.doSleep();
                                testHandMotion();
                                //saluteRightHand();
                                silenceCount = 0;
                                isWaitingForInitialGreeting = true;
                                speakAndThenWakeUp(speechText);
                                isWaitingForServer = false;

                            }else{
                                handler.post(() -> speakAndThenWakeUp(command));
                            }

                            return;
                        }
                    }
                }
            } catch (Exception e){
                Log.e("CONV_MANAGER", "Errore polling: "+ e.getMessage());
            }
            //se stiamo ancora aspettando continua il polling
            if(isWaitingForServer){
                startPolling();
            }
        }).start();
    }

    public void testHandMotion() {
        try {
            // 2. MUOVIAMO LE BRACCIA (Saluto)
            if (wingMotionManager != null) {
                Log.i("ROBOT_HARDWARE_TEST", "Utilizzo il nuovo WingMotionManager...");

                // Definizione variabili per chiarezza
                byte part = RelativeAngleWingMotion.PART_RIGHT;
                byte speed = 5;
                byte actionUp = RelativeAngleWingMotion.ACTION_UP;
                byte actionDown = RelativeAngleWingMotion.ACTION_DOWN;

                wingMotionManager.doRelativeAngleMotion(new RelativeAngleWingMotion(part, speed, actionUp, 300));

                new Handler(Looper.getMainLooper()).postDelayed(() -> {
                    wingMotionManager.doRelativeAngleMotion(new RelativeAngleWingMotion(part, speed, actionDown, 20));
                }, 1000);

                new Handler(Looper.getMainLooper()).postDelayed(() -> {
                    wingMotionManager.doRelativeAngleMotion(new RelativeAngleWingMotion(part, speed, actionUp, 100));
                }, 2000);

                new Handler(Looper.getMainLooper()).postDelayed(() -> {
                    wingMotionManager.doRelativeAngleMotion(new RelativeAngleWingMotion(part, speed, actionDown, 45));
                }, 3000);
            }

        } catch (Exception e) {
            Log.e("ROBOT_HARDWARE_TEST", "Errore durante il movimento combinato: " + e.getMessage());
        }

    }

    public void saluteRightHand() {

        try {

            byte part = AbsoluteAngleWingMotion.PART_RIGHT;
            byte speed = 8;

            // POSIZIONE INIZIALE
            int start = 30;

            // BRACCIO MOLTO ALTO
            int up = 160;

            // PICCOLO ABBASSAMENTO
            int mid = 120;

            // sicurezza: reset iniziale
            wingMotionManager.doAbsoluteAngleMotion(
                    new AbsoluteAngleWingMotion(
                            part,
                            speed,
                            start
                    )
            );

            // alza
            new Handler(Looper.getMainLooper()).postDelayed(() -> {

                wingMotionManager.doAbsoluteAngleMotion(
                        new AbsoluteAngleWingMotion(
                                part,
                                speed,
                                up
                        )
                );

            }, 500);

            // abbassa poco
            new Handler(Looper.getMainLooper()).postDelayed(() -> {

                wingMotionManager.doAbsoluteAngleMotion(
                        new AbsoluteAngleWingMotion(
                                part,
                                speed,
                                mid
                        )
                );

            }, 1300);

            // rialza
            new Handler(Looper.getMainLooper()).postDelayed(() -> {

                wingMotionManager.doAbsoluteAngleMotion(
                        new AbsoluteAngleWingMotion(
                                part,
                                speed,
                                up
                        )
                );

            }, 1900);

            // torna giù
            new Handler(Looper.getMainLooper()).postDelayed(() -> {

                wingMotionManager.doAbsoluteAngleMotion(
                        new AbsoluteAngleWingMotion(
                                part,
                                speed,
                                start
                        )
                );

            }, 2800);

        } catch (Exception e) {

            Log.e("SANBOT", e.getMessage());
        }
    }

    private void speakAndKeepPolling(String text) {
        handler.post(() -> {
            speechManager.setOnSpeechListener(new SpeakListener() {
                @Override
                public void onSpeakStatus(SpeakStatus speakStatus) {
                    if (speakStatus.getProgress() == 100) {
                        Log.i("CONV_MANAGER", "Frase detta. Continuo il polling...");
                        isWaitingForServer = true;
                        startPolling(); // Richiediamo subito il prossimo comando (il feedback)
                    }
                }
            });
            speechManager.startSpeak(text);
        });
    }

    private void speakAndThenWakeUp(String command) {
        speechManager.setOnSpeechListener(new SpeakListener() {
            @Override
            public void onSpeakStatus(SpeakStatus speakStatus) {
                if (speakStatus.getProgress() == 100){
                    handler.postDelayed(() -> {
                        initSpeechListener();
                        speechManager.doWakeUp();
                    }, 500);
                }
            }
        });
        speechManager.startSpeak(command);
    }

    private void speakAndThenSleep(String text) {
        handler.post(() -> {
            // 1. ACCENDIAMO I LED DI BLU ALL'INIZIO DEL FEEDBACK
            if (hardWareManager != null) {
                Log.i("ROBOT_HARDWARE_TEST", "Fase Feedback: accendo i LED blu...");
                hardWareManager.setLED(new LED(LED.PART_RIGHT_HEAD, LED.MODE_BLUE, (byte) 0, (byte) 0));
                hardWareManager.setLED(new LED(LED.PART_LEFT_HEAD, LED.MODE_BLUE, (byte) 0, (byte) 0));
            }
            speechManager.setOnSpeechListener(new SpeakListener() {
                @Override
                public void onSpeakStatus(SpeakStatus speakStatus) {
                    if (speakStatus.getProgress() == 100) {
                        Log.i("CONV_MANAGER", "Sessione totalmente conclusa. Spengo tutto.");
                        // 2. SPEGNIAMO TUTTI I LED QUI (Alla fine della frase)
                        if (hardWareManager != null) {
                            hardWareManager.setLED(new LED(LED.PART_ALL, LED.MODE_CLOSE, (byte) 0, (byte) 0));
                        }
                        speechManager.doSleep(); // Il robot va a dormire ORA, alla fine di tutto
                        isWaitingForServer = false; // STOP definitivo al polling
                    }
                }
            });
            speechManager.startSpeak(text);
        });
    }

    private void initSpeechListener() {
        speechManager.setOnSpeechListener(new RecognizeListener() {
            @Override
            public boolean onRecognizeResult(Grammar grammar) {
                return true;
            }

            @Override
            public void onRecognizeText(RecognizeTextBean bean) {
                if(bean != null && bean.getText() != null && !bean.getText().isEmpty()){
                    String text = bean.getText().toLowerCase().trim();
                    Log.i("CONV_MANAGER", "Utente: "+ text);
                    timeoutCount = 0;
                    isFirstTurn = false;
                    isWaitingForInitialGreeting = false;

                    if(isRetryMode){
                        handleRetryResponse(text);
                    } else{
                        //isFirstTurn = false;
                        sendTextToServer(text);
                        isWaitingForServer = true;
                        startPolling();
                    }
                }
            }

            @Override
            public void onRecognizeVolume(int i) { }

            @Override
            public void onStartRecognize() { }

            @Override
            public void onStopRecognize() { }

            @Override
            public void onError(int i, int i1) {
                if(i1 == 20005 || i == 4){
                    Log.w("CONV_MANAGER", "Timeout microfono: l'utente non ha preso l'iniziativa.");
                    if(isFirstTurn){
                        isFirstTurn = false;
                        Log.i("CONV_MANAGER", "Silenzio iniziale da parte dell'utente. Invio il tag [USER_SILENT] al server");
                        sendTextToServer("[USER_SILENT]");
                        isWaitingForServer = true;
                        startPolling();
                    }
                    else if(isWaitingForInitialGreeting){
                        silenceCount ++;
                        Log.i("CONV_MANAGER", "Silenzio al primo turno. Tentativo numero: "+ silenceCount);
                        if (silenceCount<3){
                            handler.post(() ->speakAndThenWakeUp("Non ho sentito nulla, volevi dirmi qualcosa?"));
                        }else{
                            Log.i("CONV_MANAGER", "Terzo tentativo fallito. Arresto il sistema.");
                            isWaitingForInitialGreeting = false;
                            isWaitingForServer = false;
                            sendTextToServer("[SALUTO_INIZIALE]");
                            isWaitingForServer = true;
                            startPolling();
                        }
                    }else{

                        timeoutCount ++;
                        Log.i("CONV_MANAGER", "Silenzio in conversazione. Conteggio: " + timeoutCount);
                        if(timeoutCount <=2 ){
                            askForHelp();
                        }else{
                            Log.w("CONV_MANAGER", "L'utente non risponde dopo 2 inviti. Chiudo la conversazione e chiedo il feedback");
                            timeoutCount = 0;
                            sendTextToServer("[CONVERSATION_TIMEOUT]");
                            isWaitingForServer = true;
                            startPolling();
                        }
                    }
                }
            }
        });
    }

    private void askForHelp() {
        isRetryMode = true;
        speakAndThenWakeUp("Ripeti per favore");
    }

    private void sendTextToServer(String text) {
        new Thread(() -> {
            try{
                URL url = new URL(SERVER_INPUT_URL);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("ngrok-skip-browser-warning", "69420");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);

                String json = "{\"text\":\"" + text.replace("\"","\\\"") + "\"}";
                OutputStream os = conn.getOutputStream();
                os.write(json.getBytes("UTF-8"));
                os.flush();
                os.close();

                conn.getResponseCode();
                conn.disconnect();
            }catch (Exception e){
                Log.e("CONV_MAMAGER", "Errore invio: " + e.getMessage());
            }
        }).start();
    }

    private void handleRetryResponse(String text) {
        if(text.contains("no")){
            isRetryMode = false;
            speechManager.startSpeak("Ok, mi riposo");
            speechManager.doSleep();
        }else {
            isRetryMode = false;
            Log.i("CONV_MANAGER", "Frase recuperata con successo nel retry: "+ text);
            //isFirstTurn = false;
            sendTextToServer(text);
            isWaitingForServer = true;
            startPolling();

            //speakAndThenWakeUp("Bene ti ascolto");
        }
    }


}
