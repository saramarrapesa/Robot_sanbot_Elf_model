package com.example.robot_application_old;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Shader;
import android.os.Handler;
import android.os.Looper;
import android.util.AttributeSet;
import android.view.View;

import java.util.Random;

public class RealNeonWaveView extends View {
    private Paint paint = new Paint();
    private boolean isRobotSpeaking = false;

    private Handler handler = new Handler(Looper.getMainLooper());
    private Random random = new Random();

    // --- CONFIGURAZIONE STILE WHATSAPP ---
    private static final int NUM_BARS = 45; // Numero di barrette verticali
    private float[] currentHeights = new float[NUM_BARS];
    private float[] targetHeights = new float[NUM_BARS];

    // Animazione fluida a ~60 FPS
    private Runnable animator = new Runnable() {
        @Override
        public void run() {
            if (isRobotSpeaking) {
                // Ogni tanto (circa 1 volta su 4) genera nuovi bersagli per le barrette
                if (random.nextInt(4) == 0) {
                    for (int i = 0; i < NUM_BARS; i++) {
                        // Genera un'altezza casuale (tra 0.1 e 1.0)
                        targetHeights[i] = 0.1f + random.nextFloat() * 0.9f;
                    }
                }

                // Interpolazione matematica: sposta gradualmente l'altezza corrente verso il target
                // Questo crea l'effetto morbidissimo e fluido del movimento
                for (int i = 0; i < NUM_BARS; i++) {
                    currentHeights[i] += (targetHeights[i] - currentHeights[i]) * 0.3f;
                }

                invalidate(); // Ridisegna lo schermo
                handler.postDelayed(this, 16); // 16ms = ~60 frame al secondo
            }
        }
    };

    public RealNeonWaveView(Context context, AttributeSet attrs) {
        super(context, attrs);
        paint.setStyle(Paint.Style.FILL);
        // IL SEGRETO: Arrotonda le punte delle linee trasformandole in "capsule"
        paint.setStrokeCap(Paint.Cap.ROUND);
        paint.setAntiAlias(true);
    }

    public void setRobotSpeaking(boolean speaking) {
        this.isRobotSpeaking = speaking;
        if (speaking) {
            handler.post(animator);
        } else {
            handler.removeCallbacks(animator);
            // Quando si ferma, resetta le altezze a zero
            for (int i = 0; i < NUM_BARS; i++) {
                currentHeights[i] = 0f;
                targetHeights[i] = 0f;
            }
            invalidate(); // Ridisegna la linea piatta
        }
    }

    // Metodo mantenuto per compatibilità con il tuo codice precedente
    public void updateWaveform(byte[] bytes) { }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);

        canvas.drawColor(Color.parseColor("#12131A")); // Sfondo scuro

        int width = getWidth();
        int height = getHeight();
        float midY = height / 2f;

        // Manteniamo i tuoi colori Neon, ma se vuoi il colore classico di WhatsApp
        // puoi sostituire l'array di colori con {Color.parseColor("#25D366"), Color.parseColor("#128C7E")}
        LinearGradient gradient = new LinearGradient(0, 0, width, 0,
                new int[]{Color.parseColor("#00BFFF"), Color.parseColor("#9370DB"), Color.parseColor("#FF69B4")},
                null, Shader.TileMode.CLAMP);
        paint.setShader(gradient);

        // --- CALCOLO DEGLI SPAZI ---
        // Decidiamo che il 30% della larghezza totale è lo spazio vuoto tra le barre
        float totalGapSpace = width * 0.35f;
        float gapWidth = totalGapSpace / (NUM_BARS + 1);
        float barWidth = (width - totalGapSpace) / NUM_BARS;

        paint.setStrokeWidth(barWidth); // Imposta lo spessore della linea

        float maxBarHeight = height * 0.75f; // L'altezza massima è il 75% della View

        // Disegna ogni singola barretta
        for (int i = 0; i < NUM_BARS; i++) {
            // Posizione X della barretta
            float x = gapWidth + (i * (barWidth + gapWidth)) + (barWidth / 2f);

            // Calcola l'altezza: il minimo assoluto è uguale alla larghezza (crea un puntino perfetto)
            float barHeight = Math.max(maxBarHeight * currentHeights[i], barWidth);

            if (!isRobotSpeaking) {
                barHeight = barWidth; // Se non parla, forza tutti a essere dei puntini tondi
            }

            // Calcola da dove a dove deve andare la linea verticale
            float top = midY - (barHeight / 2f);
            float bottom = midY + (barHeight / 2f);

            // Disegna la capsula verticale
            canvas.drawLine(x, top, x, bottom, paint);
        }
    }
}