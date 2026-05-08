package com.example.face_detect;

import android.graphics.Bitmap;
import android.os.Bundle;
import android.util.Log;

import com.sanbot.opensdk.base.TopBaseActivity;
import com.sanbot.opensdk.beans.FuncConstant;
import com.sanbot.opensdk.beans.OperationResult;
import com.sanbot.opensdk.function.beans.FaceRecognizeBean;
import com.sanbot.opensdk.function.beans.StreamOption;
import com.sanbot.opensdk.function.unit.HDCameraManager;
import com.sanbot.opensdk.function.unit.interfaces.media.FaceRecognizeListener;

import java.io.ByteArrayInputStream;
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


public class Face_Detection extends TopBaseActivity {
    private final String SERVER_URL = "" ;
    private final String TAG = "SanbotFaceDetection";
    private final long UPLOAD_COOLDOWN_MS = 3000;
    private HDCameraManager hdCameraManager;
    private int streamHandle = -1; // ID dello stream video
    private long lastUploadTime = 0;
    private OkHttpClient httpClient;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // 2. Registra l'activity per i servizi Sanbot
        register(MainActivity.class);
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        //vedere come creare la connessione client-server , come ho fatto per le altre classi

        // 3. Inizializza il manager della telecamera tramite l'UnitManager
        hdCameraManager = (HDCameraManager) getUnitManager(FuncConstant.HDCAMERA_MANAGER);
    }

    @Override
    protected void onMainServiceConnected() {
        Log.i("Sanbot","Servizi connessi correttamente");

        StreamOption streamOption = new StreamOption();
        streamOption.setChannel(StreamOption.MAIN_STREAM);
        streamOption.setDecodType(StreamOption.HARDWARE_DECODE);
        streamOption.setJustIframe(false);

        OperationResult result = hdCameraManager.openStream(streamOption);
        streamHandle = Integer.parseInt(result.getResult());

        setupFaceDetectionListener();


    }

    private void setupFaceDetectionListener(){
        hdCameraManager.setMediaListener(new FaceRecognizeListener() {
            @Override
            public void recognizeResult(List<FaceRecognizeBean> list) {
                if(list != null && !list.isEmpty()){
                    long currentTime = System.currentTimeMillis();

                    //controlla se sono passati almeno 3 secondi dall'ultimo invio
                    if(currentTime - lastUploadTime > UPLOAD_COOLDOWN_MS){
                        lastUploadTime = currentTime;
                        Log.i(TAG, "Volto rilevato! Cattura del frame...");

                        Bitmap currentFrame = hdCameraManager.getVideoImage();
                        uploadFaceToServer(currentFrame);
                    }
                }
            }
        });
    }

    private void uploadFaceToServer(Bitmap currentFrame) {
        ByteArrayOutputStream stream = new ByteArrayOutputStream();
        currentFrame.compress(Bitmap.CompressFormat.JPEG, 90, stream);
        byte[] byteArray = stream.toByteArray();

        RequestBody requestBody = new MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("file", "sanbot_face_" + System.currentTimeMillis() + ".jpg",
                        RequestBody.create(MediaType.parse("image/jpeg"), byteArray))
                .build();

        Request request = new Request.Builder()
                .url(SERVER_URL)
                .post(requestBody)
                .build();
        httpClient.newCall(request).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                Log.e(TAG, "Errore connessione al server: "+ e.getMessage());
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                if(response.isSuccessful()){
                    Log.i(TAG, "Foto inviata al server con successo !");

                }
                else{
                    Log.e(TAG, "Il server ha risposto con errore: "+ response.code());
                }
            }
        });
    }
    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (hdCameraManager !=null && streamHandle !=-1){
            hdCameraManager.closeStream(streamHandle);
        }
    }


}
