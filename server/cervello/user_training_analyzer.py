# ==========================================
# USER TRAINING ANALYZER
# ==========================================

import numpy as np
from typing import Dict, List
from sentence_transformers import SentenceTransformer, util
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import nltk
import re
import random
#from langchain_ollama import ChatOllama
#from langchain_core.messages import SystemMessage, HumanMessage

class UserTrainingAnalyzer:
    def __init__(self):
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')

        # Inizializzazione del modello piccolo e fulmineo per il micro-feedback
        """
        self.fast_llm = ChatOllama(
            model="qwen2:1.5b",            # Modello ultra-leggero (<1.5GB VRAM)
            base_url="http://127.0.0.1:11434",  # Porta di default di Ollama
            temperature=0.2,               # Deterministico e preciso
            num_predict=45                 # Taglia la generazione se si dilunga troppo
        )
        """

        #self.previous_user_message = None
        self.vader = SentimentIntensityAnalyzer()

        self.session_metrics = {
            "reciprocal_questions": 0,
            "short_responses": 0,
            "overexplaining": 0,
            "topic_maintenance": 0,
            "total_turns": 0,
            "conversation_initiations": 0,
            "negative_tone": 0,
            "too_specific": 0
        }

        self.turns_without_question = 0

    # ==========================================
    # FEATURE EXTRACTION
    # ==========================================

    def extract_features(self, user_text: str, previous_robot_text: str = "") -> Dict:

        words = user_text.split()
        word_count = len(words)

        # --- Reciprocal question ---
        #Dato che sarà uno speech to text forse non dovrebbe essere scritto così
        QUESTION_FRAGMENTS = [
            "e tu", "a te", "tu che dici", "tu cosa", 
            "tu?", "te?", "invece tu", "tu ne pensi", "e lei"
        ]
        lower = user_text.lower()
        
        reciprocal_question = any(q in lower for q in QUESTION_FRAGMENTS)
        trigger_missing_question = False
        if reciprocal_question:
            self.turns_without_question = 0
        else:
            self.turns_without_question += 1
            if self.turns_without_question >= 3: # Modifica qui per 2 o 3 turni
                trigger_missing_question = True
                self.turns_without_question = 0
        
        # --- Brevity ---
        short_response = word_count < 4

        # --- Overexplaining ---
        overexplaining = False
        
        if previous_robot_text:
            robot_len = len(previous_robot_text.split())
            overexplaining = word_count > robot_len * 2.5

        # --- Tone ---
        tone = self.vader.polarity_scores(user_text)["compound"]
        negative_tone = tone < -0.3

        # --- Topic coherence ---
        coherence_score = 0.0

        if previous_robot_text:
            emb1 = self.embedder.encode(user_text, convert_to_tensor=True)
            emb2 = self.embedder.encode(previous_robot_text, convert_to_tensor=True)

            coherence_score = float(util.cos_sim(emb1, emb2)[0][0])

        topic_maintenance = coherence_score > 0.40

         # --- Specificity ---
        tokens = nltk.word_tokenize(user_text)
        pos_tags = nltk.pos_tag(tokens)
        entities = nltk.ne_chunk(pos_tags)

        specificity = sum( 1 for chunk in entities if hasattr(chunk, "label") )

        descriptive_words = sum(
            1 for _, tag in pos_tags
            if tag.startswith("JJ") or tag.startswith("RB")
        )
        
        raw_specificity = specificity + descriptive_words
        
        normalized_specificity = min(raw_specificity / 10, 1.0)
        
        too_specific = normalized_specificity > 0.6

        # --- Social detail level ---
        moderate_detail = 8 <= word_count <= 35

        # --- Update session metrics ---
        self.session_metrics["total_turns"] += 1

        if reciprocal_question:
            self.session_metrics["reciprocal_questions"] += 1

        if short_response:
            self.session_metrics["short_responses"] += 1

        if overexplaining:
            self.session_metrics["overexplaining"] += 1

        if topic_maintenance:
            self.session_metrics["topic_maintenance"] += 1
            
        if negative_tone:
            self.session_metrics["negative_tone"] += 1

        if too_specific:
            self.session_metrics["too_specific"] += 1

        return {
            "word_count": word_count,
            "reciprocal_question": reciprocal_question,
            "trigger_missing_question": trigger_missing_question,
            "short_response": short_response,
            "overexplaining": overexplaining,
            "topic_maintenance": topic_maintenance,
            "moderate_detail": moderate_detail,
            "coherence_score": coherence_score,
            "negative_tone": negative_tone,
            "too_specific": too_specific
        }

    # ==========================================
    # MICRO FEEDBACK
    # ==========================================
    def generate_micro_feedback(self, features: dict) -> str:
        positives = {
            "default": [
                "Hai risposto in modo molto chiaro.",
                "La tua risposta è molto chiara.",
                "Ottima risposta."
            ],
            "reciprocal_question": [
                "Bravissimo, hai fatto una domanda di ritorno.",
                "Hai fatto una domanda. È un ottimo modo per continuare a parlare.",
                "Fare una domanda è l'azione giusta, ben fatto!"
            ],
            "topic_maintenance": [
                "Hai parlato dell'argomento giusto.",
                "Hai continuato a parlare dello stesso argomento, molto bene.",
                "Stai mantenendo l'argomento della conversazione."
            ],
            "moderate_detail": [
                "Hai detto il numero giusto di informazioni.",
                "I dettagli che hai fornito erano perfetti, né troppi né pochi.",
                "La lunghezza della tua risposta era perfetta."
            ]
        }
            
        improvements = {
            "short_response": [
                "La tua risposta era molto breve. Prova ad aggiungere un dettaglio.",
                "Puoi aggiungere qualche parola in più per spiegare meglio.",
                "Prova a dire qualcosa in più nella tua risposta."
            ],
            "overexplaining": [
                "La tua risposta era molto lunga.",
                "Hai detto molte cose tutte insieme.",
                "Cerca di dire meno cose in una sola volta."
            ],
            "missing_question": [
                "Ricorda di fare una domanda alla fine.",
                "È importante fare una domanda alla persona con cui parli.",
                "Aggiungi una domanda per far continuare la conversazione."
            ],
            "negative_tone": [
                "Prova a usare parole più gentili.",
                "Usa un tono di voce più tranquillo e positivo.",
                "Scegli parole più positive quando rispondi."
            ],
            "too_specific": [
                "Aggiungi una spiegazione. L'altra persona potrebbe non conoscere questo argomento.",
                "Spiega chi è la persona o cos'è il luogo di cui parli.",
                "Cerca di dare una spiegazione generale, così è più facile capire."
            ]
        }

        examples = {
            "short_response": [
                "Ad esempio: 'Sì, mi è piaciuto molto. E a te?'",
                "Se rispondi 'Sì' o 'No', aggiungi il motivo. Per esempio: 'No, perché non avevo tempo'.",
                "Ad esempio: 'È andata bene, ho riposato. Tu cosa mi racconti?'"
            ],
            "overexplaining": [
                "Dai solo un'informazione principale e poi fai una domanda.",
                "Prova a dire solo una o due frasi alla volta.",
                "Rispondi in modo breve e poi chiedi all'altra persona cosa ne pensa."
            ],
            "missing_question": [
                "Basta aggiungere: 'E tu?'",
                "Per esempio puoi chiedere: 'Cosa ne pensi?'",
                "Ad esempio: 'E a te piace?'"
            ]
        }
    
        # 2. Inizializziamo le variabili di default
        positive = random.choice(positives["default"])
        improvement = ""
        example = ""

        # Positive reinforcement
        if features.get("reciprocal_question"):
            positive = random.choice(positives["reciprocal_question"])
        elif features.get("topic_maintenance"):
            positive = random.choice(positives["topic_maintenance"])
        elif features.get("moderate_detail"):
            positive = random.choice(positives["moderate_detail"])

        # Improvement
        if features.get("short_response"):
            improvement = random.choice(improvements["short_response"])
            example = random.choice(examples["short_response"])
        elif features.get("overexplaining"):
            improvement = random.choice(improvements["overexplaining"])
            example = random.choice(examples["overexplaining"])
        elif features.get("trigger_missing_question"):
            improvement = random.choice(improvements["missing_question"])
            example = random.choice(examples["missing_question"])
        elif features.get("negative_tone"):
            improvement = random.choice(improvements["negative_tone"])
        elif features.get("too_specific"):
            improvement = random.choice(improvements["too_specific"])

        # Ritorno del feedback completo
        parts = [p for p in (positive, improvement, example) if p]
        feedback = " ".join(parts).strip()
        return feedback 
    # ==========================================
    # MACRO FEEDBACK
    # ==========================================

    def generate_macro_feedback(self) -> str:

        total = max(self.session_metrics["total_turns"], 1)

        reciprocal_ratio = self.session_metrics["reciprocal_questions"] / total
        overexplaining_ratio = self.session_metrics["overexplaining"] / total
        topic_ratio = self.session_metrics["topic_maintenance"] / total
        negative_ratio = self.session_metrics["negative_tone"] / total
        specificity_ratio = self.session_metrics["too_specific"] / total

        strengths = []
        improvements = []

        phrases_strengths = {
            "reciprocal": [
                "Hai fatto delle domande all'altra persona.",
                "Hai chiesto all'altra persona cosa ne pensa. Questo è molto utile.",
                "Sei stato bravo a fare domande per continuare a parlare."
            ],
            "topic": [
                "Hai parlato sempre dell'argomento giusto.",
                "Hai continuato a parlare della stessa cosa senza cambiare discorso.",
                "Sei rimasto concentrato sull'argomento della conversazione."
            ],
            "default": [
                "Hai risposto alle mie domande fino alla fine.",
                "Hai partecipato a tutta la conversazione.",
                "Hai fatto un buon allenamento oggi."
            ]
        }

        phrases_improvements = {
            "overexplaining": [
                "La prossima volta, prova a dare risposte più brevi.",
                "La prossima volta, cerca di dire meno frasi in una sola volta.",
                "Ricorda di fare pause e dare risposte meno lunghe."
            ],
            "reciprocal_low": [
                "La prossima volta, ricorda di fare una domanda alla persona con cui parli.",
                "Ricorda di chiedere 'E tu?' o 'Cosa ne pensi?' per far continuare la conversazione.",
                "Prova a fare più domande per far parlare anche l'altra persona."
            ],
            "negative": [
                "La prossima volta, usa parole più positive e tranquille.",
                "Cerca di usare un tono di voce più calmo quando rispondi."
            ],
            "specificity": [
                "Quando parli di una persona o di un posto, ricorda di spiegare cos'è.",
                "Cerca di spiegare meglio i dettagli difficili, così è più facile capire."
            ],
            "default": [
                "Continua a parlare così per allenarti.",
                "Stai andando bene, continua a fare pratica ogni giorno.",
                "Oggi hai fatto pratica, continuiamo così la prossima volta."
            ]
        }

        # --- LOGICA STRENGTHS (Cose fatte bene) ---
        if reciprocal_ratio >= 0.3:
            strengths.append(random.choice(phrases_strengths["reciprocal"]))

        if topic_ratio >= 0.6:
            strengths.append(random.choice(phrases_strengths["topic"]))

        if not strengths:
            strengths.append(random.choice(phrases_strengths["default"]))

        # --- LOGICA IMPROVEMENTS (Cose da migliorare) ---
        if overexplaining_ratio >= 0.3:
            improvements.append(random.choice(phrases_improvements["overexplaining"]))

        if reciprocal_ratio < 0.2:
            improvements.append(random.choice(phrases_improvements["reciprocal_low"]))

        if negative_ratio >= 0.3:
            improvements.append(random.choice(phrases_improvements["negative"]))
        
        if specificity_ratio >= 0.3:
            improvements.append(random.choice(phrases_improvements["specificity"]))

        if not improvements:
            improvements.append(random.choice(phrases_improvements["default"]))
            
        feedback = "Feedback finale della sessione:\n\n"

        feedback += "Punti positivi:\n"
        for s in strengths:
            feedback += f"- {s}\n"

        feedback += "\nPer la prossima conversazione:\n"
        for i in improvements:
            feedback += f"- {i}\n"

        return feedback