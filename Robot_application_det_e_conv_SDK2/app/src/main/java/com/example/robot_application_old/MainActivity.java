package com.example.robot_application_old;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.TextView;

import com.sanbot.opensdk.base.TopBaseActivity;
import com.sanbot.opensdk.beans.FuncConstant;
import com.sanbot.opensdk.function.beans.LED;
import com.sanbot.opensdk.function.beans.headmotion.LocateAbsoluteAngleHeadMotion;
import com.sanbot.opensdk.function.beans.wing.AbsoluteAngleWingMotion;
import com.sanbot.opensdk.function.beans.wing.NoAngleWingMotion;
import com.sanbot.opensdk.function.beans.wing.RelativeAngleWingMotion;
import com.sanbot.opensdk.function.unit.HDCameraManager;
import com.sanbot.opensdk.function.unit.HandMotionManager;
import com.sanbot.opensdk.function.unit.HardWareManager;
import com.sanbot.opensdk.function.unit.HeadMotionManager;
import com.sanbot.opensdk.function.unit.SpeechManager;
import com.sanbot.opensdk.function.unit.WingMotionManager;

import java.io.IOException;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;


public class MainActivity extends TopBaseActivity {
    private  VisionManager visionManager;
    private SpeechManager speechManager;
    private ConversationManager conversationManager;
    private HardWareManager hardWareManager;
    //private HandMotionManager handMotionManager;
    private WingMotionManager wingMotionManager;

    private ImageView ivCameraPreview;
    private View faceTargetIndicator;
    private TextView tvGuideStatus;




    @Override
    protected void onCreate(Bundle savedInstanceState) {
        register(MainActivity.class);

        // Impedisce allo schermo di spegnersi mentre il robot lavora
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        Thread.setDefaultUncaughtExceptionHandler(new Thread.UncaughtExceptionHandler() {
            @Override
            public void uncaughtException(Thread thread, Throwable e) {
                if (e instanceof NumberFormatException && e.getMessage() != null && e.getMessage().contains("BatteryChange")) {
                    // Ignoriamo silenziosamente l'errore di parsing della batteria dell'SDK
                    Log.w("CRASH_SHIELD", "Intercettato e bloccato il bug della batteria dell'SDK Sanbot!");
                } else {
                    // Se è un altro tipo di errore grave, lascialo passare o loggalo
                    Log.e("CRASH_SHIELD", "Errore fatale: ", e);
                }
            }
        });

        super.onCreate(savedInstanceState);
        //2. Carica il layout (FONDAMENTALE per non far crashare il bottone!)
        setContentView(R.layout.activity_main);

        ivCameraPreview = findViewById(R.id.ivCameraPreview);
        faceTargetIndicator = findViewById(R.id.faceTargetIndicator);
        tvGuideStatus = findViewById(R.id.tvGuideStatus);


    }

    @Override
    protected void onMainServiceConnected() {
        Log.i("MAIN", "Connesso ai servizi del Sanbot");
        speechManager = (SpeechManager) getUnitManager(FuncConstant.SPEECH_MANAGER);
        wingMotionManager = (WingMotionManager) getUnitManager(FuncConstant.WINGMOTION_MANAGER);
        hardWareManager = (HardWareManager) getUnitManager(FuncConstant.HARDWARE_MANAGER);
        //preheatOllamaModel();

        conversationManager = new ConversationManager(speechManager, wingMotionManager, hardWareManager);

        //inizializziamo il modulo di visione
        visionManager = new VisionManager((HDCameraManager) getUnitManager(FuncConstant.HDCAMERA_MANAGER), ivCameraPreview, faceTargetIndicator, tvGuideStatus);


        //Facciamo partire la sequenza
        startRobotWork();

    }

    private void startRobotWork() {
        speechManager.startSpeak("Avvio riconoscimento volto");

        visionManager.startFaceDetection(new VisionCallbacks() {
            @Override
            public void onRecognitionSuccess(String userId, boolean isRecognized) {
                visionManager.stop();
                Log.i("MAIN", "Utente identificato: "+ userId + ". Recognized: "+ isRecognized );
                runOnUiThread(() -> conversationManager.start());
            }

            @Override
            public void onRecognitionFailed(String error) {
                Log.e("MAIN", "Errore visione" + error);
                //magari riprovare dopo qualche secondo

            }
        });
    }
    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (visionManager != null) {
            visionManager.stop();
        }
    }
}

