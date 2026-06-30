import torch
import nltk
import random
import deepl
from typing import Tuple, List, Dict
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from nltk.tokenize import sent_tokenize
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# Per valutare la coerenza tra la frase dell'utente e quella del modello
model = SentenceTransformer("all-MiniLM-L6-v2")

DEEPL_API_KEY = "Inserisci la tua chiave" # Inserisci la tua chiave
translator_client = deepl.Translator(DEEPL_API_KEY)
# =========================
# FEATURE EXTRACTOR
# =========================
class SocialFeatureExtractor:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.vader = SentimentIntensityAnalyzer()

    def compute_tone(self, text: str) -> float:
        overall = self.vader.polarity_scores(text)["compound"]

        sentences = sent_tokenize(text)
        if not sentences:
            return overall

        sentence_scores = [
            self.vader.polarity_scores(s)["compound"]
            for s in sentences
        ]
        avg_sentence_score = sum(sentence_scores) / len(sentence_scores)

        wH = 0.5
        wS = 0.5
        return (overall * wH) + (avg_sentence_score * wS)

    def compute_specificity(self, text: str) -> float:
        words = nltk.word_tokenize(text)
        pos_tags = nltk.pos_tag(words)

        entities = nltk.ne_chunk(pos_tags)
        entity_count = sum(
            1 for chunk in entities if hasattr(chunk, "label")
        )
        descriptive_count = sum(
            1 for _, tag in pos_tags
            if tag.startswith("JJ") or tag.startswith("RB")
        )

        raw_specificity = entity_count + descriptive_count
        MAX_EXPECTED = 10
        return min(raw_specificity / MAX_EXPECTED, 1.0)
   
    def extract(self, current_text: str) -> Dict[str, float]:
        tokens = self.tokenizer.encode(current_text)
        brevity = len(tokens)
        tone = self.compute_tone(current_text)
        specificity = self.compute_specificity(current_text)
        #coherence = self.compute_coherence(previous_text, current_text)

        has_question = "?" in current_text

        return {
            "brevity": brevity,
            "tone": tone,
            "specificity": specificity,
            "has_question": has_question
        }


# =========================
# RULE ENGINE
# =========================
class OverlayRules:
    def __init__(
        self,
        max_tokens: int = 40,
        min_tone: float = 0.0,
        max_specificity: float = 0.7,
        #min_coherence: float = 0.45
    ):
        self.max_tokens = max_tokens
        self.min_tone = min_tone
        self.max_specificity = max_specificity
        #self.min_coherence = min_coherence

    def evaluate(self, features: Dict[str, float], is_coherent_llm: bool, is_final_turn = False) -> Tuple[List[str], bool, int]:
        directives = []
        is_critical = False
        severity = 0

        # Deviazioni minori
        if features["brevity"] > self.max_tokens:
            directives.append(
                f"Keep the reply shorter and more conversational ({features['brevity']} tokens)."
            )
            severity += 1

        if features["specificity"] > self.max_specificity:
            directives.append(
                "Avoid being overly specific or mentioning niche details."
            )
            severity += 1

        # Deviazioni significative → critico
        if features["tone"] < self.min_tone:
            directives.append("Use a warmer and more natural social tone.")
            is_critical = True
            severity += 2
            
        if not is_coherent_llm:
            directives.append("Make the reply logically connected and relevant as a direct response to the user.")
            is_critical = True
            severity += 2
        """
        if not features.get("has_question", True):
            directives.append("Proactively include exactly one natural follow-up question to keep the conversation flowing.")
            severity += 1
        """
        has_q = features.get("has_question", False)
        if is_final_turn:
            if has_q:
                directives.append("This is the last turn, please remove the question and provide a closing sentence.")
                severity +=1
        else:
            if not has_q:
                directives.append("Proactively include a follow-up question.")
                severity +=1
            
        return directives, is_critical, severity


# =========================
# GROUNDED FRAMEWORK
# =========================
class GroundedFramework:
    def __init__(self, base_model, observer_model, tokenizer, translator,  device="cuda"):
        self.base_model = base_model
        self.observer_model = observer_model
        self.tokenizer = tokenizer
        self.device = device
        self.translator = translator

        self.extractor = SocialFeatureExtractor(tokenizer)
        # FIX soglie: coherence abbassata perché in small talk
        # robot e utente parlano di cose diverse per definizione.
        # min_tone abbassato leggermente per tollerare tono neutro.
        self.rules = OverlayRules(
            max_tokens=40,
            min_tone=-0.05,       # tolera tono neutro (0.0 era troppo strict)
            max_specificity=0.7
            #min_coherence=0.10    # FIX: era 0.45, impossibile da rispettare in small talk
        )
        self.max_attempts = 3

    # -------------------------------------------------------
    # GENERAZIONE TESTO
    # -------------------------------------------------------
    def _generate_text(self, model, messages: List[Dict], max_tokens: int = 100) -> str:
        langchain_messages = []
        for m in messages:
            if m["role"] == "system":
                langchain_messages.append(SystemMessage(content=m["content"]))
            elif m["role"] == "user":
                langchain_messages.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                langchain_messages.append(AIMessage(content=m["content"]))

        model_type = str(type(model)).lower()
        """
        params = (
            {"max_output_tokens": max_tokens}
            if "google" in model_type
            else {"max_tokens": max_tokens}
        )
        """
        if "google" in model_type:
            params = {"max_output_tokens": max_tokens}
        elif "ollama" in model_type:
            # Per ChatOllama i token si passano dentro il sotto-dizionario 'options'
            params = {"options": {"num_predict": max_tokens}}
        else:
            params = {"max_tokens": max_tokens}

        configured_model = model.bind(**params) if hasattr(model, "bind") else model
        response = configured_model.invoke(langchain_messages)

        content = response.content
        decoded = str(content).strip().replace('"', '')

        # --- PULIZIA OUTPUT ---
        # FIX: prefissi più mirati per non filtrare "here" generico
        FILTER_PREFIXES = (
            "here is", "here's the", "here are",
            "translation:", "note:", "reasoning:",
            "analysis:", "robot:", "user:", "response:"
        )

        lines = decoded.split('\n')
        for line in lines:
            cleaned_line = line.strip()
            if cleaned_line and not any(
                cleaned_line.lower().startswith(p) for p in FILTER_PREFIXES
            ):
                return cleaned_line

        return decoded

    def _evaluate_coherence_with_observer(self, proposal: str, user_input_en: str) -> bool:
        """Usa l'Observer per un check binario (YES/NO) sulla pertinenza della risposta."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a conversational judge. "
                    "Determine if the Assistant's reply makes logical sense as a direct response to the User. "
                    "In small talk, answering a question, acknowledging a statement, or continuing the topic naturally is COHERENT. "
                    "Replying ONLY with 'YES' if coherent. Reply ONLY with 'NO' if off-topic or nonsensical."
                )
            },
            {
                "role": "user",
                "content": f"User: {user_input_en}\nAssistant: {proposal}\nIs it coherent?"
            }
        ]
        # Max tokens bassissimo per massima velocità (Groq ci metterà millisecondi)
        response = self._generate_text(self.observer_model, messages, max_tokens=10)
        return "yes" in response.lower()


    # -------------------------------------------------------
    # FEEDBACK OBSERVER
    # FIX: ora riceve user_input e conversation_context
    # per evitare allucinazioni di contesto futuro
    # -------------------------------------------------------
    def _get_observer_feedback(
        self,
        directives: List[str],
        proposal: str,
        user_input: str,
        conversation_context: str = "",
        is_final_turn = False
    ) -> str:

        ending_instruction = (
            "- THIS IS THE LAST TURN: Do NOT ask a question. "
            "- Provide a warm, polite closing statement to end the conversation naturally."
        ) if is_final_turn else "- PROACTIVELY include a natural follow-up question."
        messages = [
            {
                "role": "system",
                "content": f"You are an observer model that improves social small talk.\n\n"
                           f"Rewrite the assistant reply so that it:\n"
                           f"- is warm, friendly, and easy to understand\n"
                           f"- uses clear and literal language\n"
                           f"- is short (1-2 sentences)\n"
                           f"- avoids repeating or paraphrasing the user's words unnecessarily\n"
                           f"- responds directly to the user's last message\n"
                           f"- ONLY uses information already present in the conversation\n"
                           f"- does NOT invent names, facts, or details not yet mentioned\n"
                           f"{ending_instruction}\n" 
                           f"- maintains topic coherence\n"
                           f"- never asks multiple questions\n\n"
                           f"Return only the corrected reply. Do not explain, analyze or justify."
            },
            {
                "role": "user",
                "content": (
                    f"Conversation context:\n{conversation_context}\n\n"
                    f"User's last message: '{user_input}'\n"
                    f"Proposed reply: '{proposal}'\n"
                    f"Violations: {', '.join(directives)}\n\n"
                    f"Rewrite the reply fixing the violations. "
                    f"Do NOT invent details not present in the conversation above."
                )
            }
        ]
        return self._generate_text(self.observer_model, messages, max_tokens=50)

    # -------------------------------------------------------
    # CONTROLLO: la risposta non deve copiare l'input utente
    # -------------------------------------------------------
    def _is_repetition_of_input(self, proposal: str, user_input: str) -> bool:
        """Restituisce True se la proposta è troppo simile all'input utente."""
        prop_clean = proposal.strip().lower()
        user_clean = user_input.strip().lower()

        # Match esatto
        if prop_clean == user_clean:
            return True

        # Similarità semantica alta (> 0.92) → copia quasi identica
        emb1 = model.encode(proposal)
        emb2 = model.encode(user_input)
        similarity = cosine_similarity([emb1], [emb2])[0][0]
        return float(similarity) > 0.92

    # -------------------------------------------------------
    # LOOP PRINCIPALE
    # last_robot_turn: ultimo messaggio del robot nella storia
    # (usato per misurare la coherence nel turno corretto)
    # -------------------------------------------------------
    def interact(self, user_input: str, system_context: str, last_robot_turn: str = "", is_final_turn: bool = False) -> str:
        user_input_en = self.translator.translate_text(user_input, target_lang="EN-US").text
        attempt = 0
        best_proposal = ""
        best_severity = float("inf")
        best_tone = float("-inf")   # FIX: tiebreaker quando severity è uguale
        accumulated_feedback = ""

        base_messages = [
            {
                "role": "system",
                "content": system_context + "\nRespond in ENGLISH for internal logic."
            },
            {
                "role": "user",
                "content": user_input_en
            }
        ]

        while attempt < self.max_attempts:

            messages = [m.copy() for m in base_messages]

            if attempt > 0 and accumulated_feedback:
                correction_instruction = (
                    f"\n\nPREVIOUS ATTEMPT WAS REJECTED."
                    f"\nReason: {accumulated_feedback}"
                    f"\nDo NOT repeat this rejected reply: '{best_proposal}'"
                    f"\nRespond ONLY to the user message."
                    f"\nOne short sentence. Stay on topic."
                    f"\nDo NOT invent details not present in the conversation."
                )
                messages[0]["content"] = (
                    system_context
                    + "\nRespond in ENGLISH for internal logic."
                    + correction_instruction
                )

            proposal = self._generate_text(self.base_model, messages)

            is_coherent_llm = self._evaluate_coherence_with_observer(proposal, user_input_en)

            features = self.extractor.extract(
                current_text=proposal
            )
            directives, is_critical, severity = self.rules.evaluate(features, is_coherent_llm, is_final_turn=is_final_turn)

            print(
                f"[DEBUG] Attempt {attempt + 1} | "
                f"brevity={features['brevity']} | "
                f"tone={features['tone']:.2f} | "
                f"specificity={features['specificity']:.2f} | "
                f"coherence_llm={is_coherent_llm} | "
                f"severity={severity} | is_critical={is_critical}"
            )

            # FIX: tiebreaker su tone quando severity è uguale
            # → scegliamo la proposta con tono più positivo
            is_better = (
                severity < best_severity
                or (severity == best_severity and features["tone"] > best_tone)
            )
            if is_better:
                best_severity = severity
                best_tone = features["tone"]
                best_proposal = proposal

            if not directives:
                print(f"[OK] Accepted at attempt {attempt + 1}: {proposal}")
                if self._is_repetition_of_input(proposal, user_input_en):
                    print("[WARN] Accepted reply too similar to user input, forcing regen.")
                    break
                return proposal

            apply_strict = (
                is_critical
                or severity >= 2
                or random.random() < 0.5
            )

            if apply_strict:
                observer_feedback = self._get_observer_feedback(
                    directives,
                    proposal,
                    user_input=user_input_en,
                    conversation_context=system_context[-400:],
                    is_final_turn=is_final_turn
                )
                
                print(f"[STRICT MODE] Attempt {attempt + 1}: Observer corrected -> {observer_feedback}")
                
                if self._is_repetition_of_input(observer_feedback, user_input_en):
                    print("[WARN] L'Observer ha generato una ripetizione. Forzo il fallback di emergenza.")
                    # Esegui il tuo blocco di fallback usando la best_proposal originale o una frase neutra
                    fallback_messages = [
                        {
                            "role": "system",
                            "content": system_context + "\nGive a short, original response. Do not repeat the user."
                        },
                        {
                            "role": "user",
                            "content": user_input_en
                        }
                    ]
                    return self._generate_text(self.base_model, fallback_messages)

                return observer_feedback
                
            else:
                accumulated_feedback = f"[SOFT] {' '.join(directives)}"
                print(f"[SOFT MODE] Attempt {attempt + 1}: {accumulated_feedback}")

            attempt += 1

        # -------------------------------------------------------
        # POST-LOOP: controllo anti-ripetizione sulla best_proposal
        # -------------------------------------------------------
        if self._is_repetition_of_input(best_proposal, user_input_en):
            print("[WARN] best_proposal is a repetition of user input. Forcing fallback regen.")
            fallback_messages = [
                {
                    "role": "system",
                    "content": (
                        system_context
                        + "\nRespond in ENGLISH for internal logic."
                        + "\nIMPORTANT: Do NOT repeat the user's words."
                        + "\nGive a short, original, on-topic response."
                        + "\nDo NOT invent names or details not present in the conversation."
                    )
                },
                {
                    "role": "user",
                    "content": user_input_en
                }
            ]
            best_proposal = self._generate_text(self.base_model, fallback_messages)
            print(f"[FALLBACK] Generated: {best_proposal}")

        print(f"[LOG] Final English reasoning: {best_proposal}")
        return best_proposal