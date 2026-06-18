package com.example.robot_application_old;

import android.graphics.Bitmap;
import android.graphics.ImageFormat;
import android.graphics.Rect;
import android.graphics.YuvImage;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.sanbot.opensdk.beans.OperationResult;
import com.sanbot.opensdk.function.beans.FaceRecognizeBean;
import com.sanbot.opensdk.function.beans.StreamOption;
import com.sanbot.opensdk.function.unit.HDCameraManager;
import com.sanbot.opensdk.function.unit.interfaces.media.FaceRecognizeListener;
import com.sanbot.opensdk.function.unit.interfaces.media.MediaListener;
import com.sanbot.opensdk.function.unit.interfaces.media.MediaStreamListener;

import android.graphics.BitmapFactory;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.List;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.MultipartBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class VisionManager {
    private final String TAG = "VisionManager";
    private final String SERVER_URL = "https://provoke-commodity-coral.ngrok-free.dev/recognize";
    private boolean isModuleFinished = false; // Ferma tutto quando il tempo scade o l'utente è riconosciuto
    private Handler timeoutHandler = new Handler(Looper.getMainLooper());
    private Runnable timeoutRunnable;

    private android.widget.ImageView ivPreview;
    private android.view.View targetIndicator;
    private android.widget.TextView tvStatus;

    private HDCameraManager hdCameraManager;
    private OkHttpClient httpClient;
    private int streamHandle = -1;
    private boolean isProcessing = false;
    private Bitmap currentFrameBitmap = null;
    private Handler previewHandler = new Handler(Looper.getMainLooper());
    private Runnable previewRunnable;

    public VisionManager(HDCameraManager cameraManager,android.widget.ImageView ivPreview, android.view.View targetIndicator, android.widget.TextView tvStatus) {
        this.hdCameraManager = cameraManager;
        this.httpClient = getUnsafeOkHttpClient();
        this.ivPreview = ivPreview;
        this.targetIndicator = targetIndicator;
        this.tvStatus = tvStatus;

    }


    public void startFaceDetection(VisionCallbacks callbacks){
        if(hdCameraManager == null) return;

        Log.i("Sanbot","Servizi connessi correttamente");
        isProcessing = false;
        isModuleFinished = false;

        StreamOption streamOption = new StreamOption();
        //streamOption.setChannel(StreamOption.MAIN_STREAM);
        // Passa a 640x480: la CPU del Sanbot ringrazierà e il video diventerà fluido
        streamOption.setChannel(StreamOption.SUB_STREAM);
        streamOption.setDecodType(StreamOption.HARDWARE_DECODE);
        streamOption.setJustIframe(false);

        OperationResult result = hdCameraManager.openStream(streamOption);
        streamHandle = Integer.parseInt(result.getResult());

        previewRunnable = new Runnable() {
            @Override
            public void run() {
                if (!isModuleFinished && hdCameraManager != null) {
                    // Catturiamo il frame direttamente dall'hardware in modo sicuro
                    Bitmap bitmap = hdCameraManager.getVideoImage();
                    if (bitmap != null) {
                        currentFrameBitmap = bitmap;
                        ivPreview.setImageBitmap(currentFrameBitmap);
                    }
                    // Ripete ogni 100ms (circa 10 FPS, fluido e leggerissimo per il Sanbot)
                    previewHandler.postDelayed(this, 60);
                }
            }
        };
        previewHandler.post(previewRunnable);

        timeoutRunnable = new Runnable() {
            @Override
            public void run() {
                if (!isModuleFinished) {
                    Log.i(TAG, "Tempo scaduto (10s)! Chiudo la fotocamera e procedo comunque.");
                    stop(); // Spegne la telecamera immediatamente
                    isModuleFinished = true;
                    callbacks.onRecognitionFailed("Timeout stabilizzazione camera");
                }
            }
        };
        timeoutHandler.postDelayed(timeoutRunnable, 60000);
        hdCameraManager.setMediaListener(new FaceRecognizeListener() {

            @Override
            public void recognizeResult(List<FaceRecognizeBean> list) {
                Log.d(TAG, "FaceRecognizeListener: vedo " + (list != null ? list.size() : 0) + " volti. Processing: " + isProcessing);

                if(isModuleFinished) return;

                if(list != null && !list.isEmpty()){
                    Log.i(TAG, "Volto rilevato, catturo frame ...");
                    FaceRecognizeBean face = list.get(0);
                    double faceCenterX = (face.getLeft()+face.getRight())/2.0;
                    boolean isCentered = faceCenterX > 0.30 && faceCenterX < 0.70;

                    new Handler(Looper.getMainLooper()).post(() -> {
                       if(isCentered){
                           targetIndicator.setBackgroundResource(R.drawable.target_green);
                           tvStatus.setText("Viso rilevato! Rimani fermo...");
                       }else{
                           targetIndicator.setBackgroundResource(R.drawable.target_red);
                           tvStatus.setText("Centra il viso nel mirino...");
                       }
                    });
                    if(isCentered && !isProcessing){
                        isProcessing = true;
                        Log.i(TAG, "Volto centrato e valido, catturo frame ...");
                        Bitmap bitmap = hdCameraManager.getVideoImage();
                        if (bitmap != null) {
                            uploadFace(bitmap, callbacks);
                        } else {
                            Log.e(TAG, "Errore: Frame catturato vuoto (null)");
                            isProcessing = false; // Riprova al prossimo frame utile
                        }
                    }
                }else{
                    new Handler(Looper.getMainLooper()).post(() -> {
                       targetIndicator.setBackgroundResource(R.drawable.target_red);
                       tvStatus.setText("Inquadra il tuo volto nel mirino");
                    });
                }
            }
        });
    }

    private void uploadFace(Bitmap bitmap, VisionCallbacks callbacks){
        Log.d(TAG, "Preparazione upload... Dimensione bitmap: " + bitmap.getByteCount());

        ByteArrayOutputStream stream = new ByteArrayOutputStream();
        bitmap.compress(Bitmap.CompressFormat.JPEG, 20, stream);
        byte[] byteArray = stream.toByteArray();

        RequestBody requestBody = new MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("file", "face.jpg",
                        RequestBody.create(MediaType.parse("image/jpeg"), byteArray))
                .build();

        Request request = new Request.Builder()
                .url(SERVER_URL)
                .addHeader("ngrok-skip-browser-warning", "69420")
                .post(requestBody)
                .build();
        Log.d(TAG, "Invio richiesta HTTP a: " + SERVER_URL);

        httpClient.newCall(request).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                isProcessing = false;
                new Handler(Looper.getMainLooper()).post(() -> {
                    targetIndicator.setBackgroundResource(R.drawable.target_red);
                    tvStatus.setText("Errore invio. Riprovo...");
                });
                if (!isModuleFinished) {
                    callbacks.onRecognitionFailed(e.getMessage());
                }
            }
            //da vedere esattamente cosa fa
            @Override
            public void onResponse(Call call, Response response) throws IOException {
                if(response.isSuccessful()){
                    try{
                        if (response.isSuccessful()) {
                            Log.i(TAG, "Foto inviata al server con successo !");
                            String responseData = response.body().string();
                            JSONObject json = new JSONObject(responseData);
                            String uid = json.getString("user_id");
                            boolean recognized = json.getBoolean("recognized");
                            //double waitTime = json.optDouble("wait_time", 5.0);

                            timeoutHandler.removeCallbacks(timeoutRunnable);
                            isModuleFinished = true;
                            stop(); // SPEGNE LA TELECAMERA SUBITO!

                            callbacks.onRecognitionSuccess(uid, recognized);
                        } else {
                            // Se il server risponde 404, 500 ecc.
                            Log.e(TAG, "Errore Server: " + response.code());
                            isProcessing = false; // <--- FONDAMENTALE
                            //callbacks.onRecognitionFailed("Errore server: " + response.code());
                        }
                    }catch (Exception e){
                        Log.e(TAG, "Errore parsing: " + e.getMessage());
                        isProcessing = false; // <--- FONDAMENTALE
                        callbacks.onRecognitionFailed("Errore parsing dati");
                    } finally {
                        response.close(); // Chiudi sempre la risposta per evitare memory leak
                    }
                }

            }
        });
    }

    public void stop(){
        if (previewHandler != null && previewRunnable != null) {
            previewHandler.removeCallbacks(previewRunnable);
        }
        // Cancella i timer residui per evitare memory leak
        if (timeoutHandler != null && timeoutRunnable != null) {
            timeoutHandler.removeCallbacks(timeoutRunnable);
        }

        // Chiude lo stream video della telecamera Sanbot
        if (hdCameraManager != null && streamHandle != -1) {
            //hdCameraManager.setMediaListener(null); // Rimuove il listener prima di chiudere
            hdCameraManager.closeStream(streamHandle);
            streamHandle = -1;
            Log.i(TAG, "Telecamera spenta con successo. Modulo terminato.");
        }
        new Handler(Looper.getMainLooper()).post(() -> {
            if (ivPreview != null) {
                ivPreview.setImageBitmap(null); // Cancella l'ultimo frame rimasto impresso
                ivPreview.setVisibility(android.view.View.GONE); // Nasconde la vista video
            }
            if (targetIndicator != null) {
                targetIndicator.setVisibility(android.view.View.GONE); // Nasconde il mirino
            }
            if (tvStatus != null) {
                tvStatus.setVisibility(android.view.View.GONE); // Nasconde il testo di stato
            }
        });

        // Svuota il bitmap per liberare la RAM del tablet
        if (currentFrameBitmap != null) {
            currentFrameBitmap.recycle();
            currentFrameBitmap = null;
        }
    }

    private OkHttpClient getUnsafeOkHttpClient() {
        try {
            // Crea un gestore che si fida di QUALSIASI certificato (Bypassa l'errore Trust Anchor)
            final javax.net.ssl.TrustManager[] trustAllCerts = new javax.net.ssl.TrustManager[]{
                    new javax.net.ssl.X509TrustManager() {
                        @Override public void checkClientTrusted(java.security.cert.X509Certificate[] chain, String authType) {}
                        @Override public void checkServerTrusted(java.security.cert.X509Certificate[] chain, String authType) {}
                        @Override public java.security.cert.X509Certificate[] getAcceptedIssuers() { return new java.security.cert.X509Certificate[]{}; }
                    }
            };

            final javax.net.ssl.SSLContext sslContext = javax.net.ssl.SSLContext.getInstance("SSL");
            sslContext.init(null, trustAllCerts, new java.security.SecureRandom());

            return new OkHttpClient.Builder()
                    .sslSocketFactory(sslContext.getSocketFactory(), (javax.net.ssl.X509TrustManager)trustAllCerts[0])
                    .hostnameVerifier((hostname, session) -> true)
                    .connectTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
                    .writeTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
                    .readTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
                    .build();
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

}
