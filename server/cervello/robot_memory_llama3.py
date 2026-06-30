import os
os.environ["CUDA_VISIBLE_DEVICES"] = "2"
import json
import operator
import getpass
from typing import Annotated, List, Union, TypedDict
from pydantic import BaseModel,Field
# LangChain & Frameworks
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings 
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import StateGraph, END
from langchain_huggingface import HuggingFacePipeline
from transformers import pipeline
from langchain_core.output_parsers import JsonOutputParser
from langchain_huggingface import ChatHuggingFace
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq

# DeepFace per riconoscimento (dal nostro debug precedente)

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from Grounded_observer_framework import GroundedFramework
from peft import PeftModel
import torch
import random
import deepl
from user_training_analyzer import UserTrainingAnalyzer
from inputimeout import inputimeout, TimeoutOccurred
import time
import math 

#from langchain_google_genai import ChatGoogleGenerativeAI
import sys
import io

sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')

# ==========================================
# 0. CONFIGURAZIONE E AMBIENTE
# ==========================================

#Per la traduzione in italiano è perfetto
DEEPL_API_KEY = "Inserisci la tua chiave" # Inserisci la tua chiave
translator_client = deepl.Translator(DEEPL_API_KEY)


# Ollama gestisce autonomamente la GPU sul server dell'università
llm_base = ChatOllama(
    model="robby-robot",
    base_url="http://127.0.0.1:11434", # La tua porta dedicata
    temperature=0.75,
    num_predict=120
)

embeddings_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

#per l'observer uso questo 
tokenizer_observer = AutoTokenizer.from_pretrained("gpt2")


llm_observer = ChatGroq(
    model="llama-3.3-70b-versatile", 
    groq_api_key="Inserisci la tua chiave",
    temperature=0.6,
    max_tokens=100
)

observer_model = llm_observer


#training_analyzer = UserTrainingAnalyzer()
# ==========================================
# 1. INSTANZIO IL GROUNDED FRAMEWORK
# ==========================================
grounded_framework = GroundedFramework(
    base_model= llm_base,
    observer_model=observer_model,
    tokenizer=tokenizer_observer,
    translator=translator_client,
    device="cuda:0"
)

# ==========================================
# 2. INIZIALIZZAZIONE DATABASE (ChromaDB)
# ==========================================

#rimuovo il riconoscimento facciale credo oppure lo mantengo ma gli levo il nome
# DB Volti (Nativo) 
face_db = Chroma(
    collection_name="memoria_fotografica",
    embedding_function=None,
    persist_directory="./chroma_db/photos"
)

# DB Episodico (Conversazioni)
episodic_db = Chroma(
    collection_name="memoria_episodica",
    embedding_function=embeddings_model,
    persist_directory="./chroma_db/episodic"
)

# ==========================================
# 3. LOGICA DI MEMORIA E RIFLESSIONE
# ==========================================
reflection_prompt_template = """
You are a reflective analysis system for a social robot.
Your task is to analyze the recent conversation between the robot and a person with autism in order to extract "memories" that will guide future interactions.

Analyze the conversation and create a reflection following these rules:
1. If there is not enough information for a field, use "N/A".
2. Be extremely concise: every string must be a clear and useful sentence.
3. Focus on elements that help the robot be more empathetic and consistent in future interactions.
4. The context_tags must be specific to the type of interaction.
5. Identify personal preferences, hobbies, names of people, or objects mentioned by the adult.
6. Respond exclusively in JSON format.
7. Do not include introductions (e.g. "Here is the JSON") or conclusions.
8. Do not simply say "the adult interacted well"; write WHAT they actually said.

Generate valid JSON exactly in this format:
{{
    "context_tags": [              // 2-4 keywords that help identify similar future conversations
        string,                    // Use specific fields such as "positive_emotion", "topic_of_interest", "communication_difficulty"
        ...
    ],
    "conversation_summary": string, // One sentence summarizing the interaction and the achieved goal.
    "what_worked": string,         // What triggered a positive reaction in the adult (e.g. calm tone, specific topic).
    "what_to_avoid": string        // What caused withdrawal or confusion (e.g. overly long sentences, complex terms).
}}

Examples:
- context_tags: ["interest_astronomy", "calm_interaction"]
- conversation_summary: "The adult showed curiosity about planets and responded positively to simple explanations."
- what_worked: "Using comparisons with everyday objects to explain the size of the sun."
- what_to_avoid: "Changing the topic too quickly without waiting for feedback from the adult."

Here is the previous conversation:
{conversation}

JSON Response:
{{
"""
def reflect_locally(conversation_text):
    full_prompt = reflection_prompt_template.format(conversation=conversation_text)
    raw_output = llm_base.invoke(full_prompt)

    raw_text = raw_output.content if hasattr(raw_output, 'content') else str(raw_output)
    if not raw_text.strip().startswith("{"):
        raw_text = "{" + raw_text
    parser = JsonOutputParser()
    try:
        return parser.parse(raw_text)
    except Exception as e:
        print(f"Errore parsing JSONE riflessione: {e}")
        return {
            "context_tags": ["errore_riflessione"],
            "conversation_summary": "N/A",
            "what_worked": "N/A",
            "what_to_avoid": "N/A"
        }

def format_conversation(messages):
    conversation = []
    for message in messages[1:]:
        conversation.append(f"{message.type.upper()}: {message.content}")
    return "\n".join(conversation)

def procedural_memory_update(what_worked, what_to_avoid):
    # Load Existing Procedural Memory Instructions
    with open("/mnt/sdb1/workspace/saramarrapesa/procedural_memory.txt", "r") as content:
        current_takeaways = content.read()

    # Load Existing and Gathered Feedback into Prompt
    procedural_prompt = f"""Your task is to maintain a constantly updated list of the most important procedural instructions for an AI assistant. You must refine and improve this list of key takeaways based on new feedback gathered during conversations, while preserving the most valuable existing information.

    CURRENT TAKEAWAYS:
    {current_takeaways}

    NEW FEEDBACK:
    What worked well:
    {what_worked}

    What should be avoided:
    {what_to_avoid}

    Please generate an updated list of up to 10 key takeaways that combines:

    1. The most valuable insights from the current takeaways
    2. New learnings derived from the recent feedback
    3. Any synthesized insights that combine multiple learnings

    Requirements for each takeaway:

    - It must be specific and actionable
    - It must address a distinct aspect of behavior
    - It must include a clear rationale
    - It must be written in imperative form (e.g. “Maintain conversational context...”)

    Format each takeaway as:
    [#]. [Instruction] - [Brief rationale]

    The final list should:

    - Be ordered by importance/impact
    - Cover a diverse range of interaction aspects
    - Focus on concrete behaviors rather than abstract principles
    - Preserve particularly strong existing takeaways
    - Integrate new insights when they provide meaningful improvements

    Return a maximum of 10 takeaways, replacing or combining existing ones if necessary to maintain the most effective set of guidelines.
    Return only the list, without introductions or explanations.
    """
    procedural_memory = llm_base.invoke(procedural_prompt)

    # Write to File
    with open("/mnt/sdb1/workspace/saramarrapesa/procedural_memory.txt", "w") as content:
        content.write(procedural_memory.content)

    return

def add_episodic_memory(messages, episodic_db, user_id):
    #Format the conversation
    conversation = format_conversation(messages)
    #Reflect on the conversation
    reflection = reflect_locally(conversation)
    
    episodic_memory = episodic_db.add_texts(
        texts=[reflection["conversation_summary"]],
        metadatas=[{
            "user_id": user_id,
            "conversation": conversation,
            "context_tags": ", ".join(reflection['context_tags']),
            "conversation_summary": reflection['conversation_summary'],
            "what_worked": reflection['what_worked'],
            "what_to_avoid": reflection['what_to_avoid'],
            "type": "episodic"
        }]
    )
    print(f"Memoria episodica aggiunta al database: {episodic_memory}, per l'utente: {user_id}")

    procedural_memory_update(
        what_worked=reflection['what_worked'], 
        what_to_avoid=reflection['what_to_avoid']
    )
    print("Memoria procedurale aggiornata con successo.")

#Episodic Memory Retrieval
def episodic_recall(query, episodic_db, user_id):

    results = episodic_db.similarity_search(query, k=3, filter={"user_id": user_id})
    if not results:
        return "Nessuna memoria episodica trovata"
    
    combined_summaries = []
    for doc in results:
        summary = doc.metadata.get('conversation_summary', '')
        combined_summaries.append(summary)

    # Creiamo un dizionario che contiene l'unione dei ricordi
    merged_metadata = {
        "conversation_summary": " | ".join(combined_summaries),
        "context_tags": results[0].metadata.get('context_tags', 'N/A'),
        "what_worked": results[0].metadata.get('what_worked', 'N/A')
    }
    
    return merged_metadata

#funzione che conta le sessioni -> da completare
def get_session_count(user_id):
    file_path = "user_stats.json"
    
    # Se il file non esiste, crealo vuoto
    if not os.path.exists(file_path):
        with open(file_path, "w") as f:
            json.dump({}, f)
        stats = {}
    else:               
        with open(file_path, "r") as f:
            try:
                stats = json.load(f)
            except json.JSONDecodeError:
                stats = {}
    
    # Ottieni il conteggio attuale o 0 se è un nuovo utente
    count = stats.get(user_id, 0)
    
    # Incrementiamo il conteggio perché una nuova sessione sta iniziando ora
    stats[user_id] = count + 1
    
    with open(file_path, "w") as f:
        json.dump(stats, f, indent=4)
        
    return stats[user_id]
# ==========================================
# 4. DEFINIZIONE DEL GRAFO (LANGGRAPH)
# ==========================================

class RobotState(TypedDict):
    messages: Annotated[List[Union[HumanMessage, SystemMessage]], operator.add]
    query: str
    user_id: str  # Aggiunto per filtrare la memoria
    is_recognized: bool
    memory_context: str
    micro_feedback: str
    is_final_turn: bool
    analyzer_instance: any

def recall_node(state: RobotState):
    query = state["query"]
    uid = state["user_id"]
    
    # 1. Recall Episodico FILTRATO per user_id
    episodic_meta = episodic_recall(query,episodic_db,uid)
    
    # 2. Carica memoria procedurale
    with open("/mnt/sdb1/workspace/saramarrapesa/procedural_memory.txt", "r") as f: proc = f.read()
    
    if isinstance(episodic_meta, dict):
    	episodic_context = f"""
        The adult is named or talked about: {episodic_meta.get('conversation_summary')}
        Things he likes: {episodic_meta.get('context_tags')}
        Effective interaction strategy: {episodic_meta.get('what_worked')}

        Additionally, here are 10 guidelines for interacting with the current user: {proc}
        """
    else:
        episodic_context = "No previous memories with this adult."

    full_context = f"EPISODIC CONTEXT (IDENTITY):\n{episodic_context}\n\n"

    return {
        "memory_context": full_context, 
        "query": query,
        "user_id": uid,
        "is_recognized": state["is_recognized"] 
    }

def grounded_generation_node(state: RobotState):
    is_rec = state["is_recognized"]
    user_id = state["user_id"]
    user_input = state["query"]
    memory_context = state["memory_context"]
    micro_feedback = state["micro_feedback"]
    is_final_turn = state.get("is_final_turn", False)
    training_analyzer = state["analyzer_instance"]

    conversation_history = ""

    for msg in state["messages"][-6:]:
        role = "User" if isinstance(msg, HumanMessage) else "Robot"
        conversation_history += f"{role}: {msg.content}\n"

    last_robot_reply = ""
    for msg in reversed(state["messages"]):
        if not isinstance(msg, HumanMessage):  # Se non è un messaggio dell'utente, è il robot (AIMessage)
            last_robot_reply = msg.content
            break

    # ANALISI UTENTE → ADAPTIVE LAYER
    features = training_analyzer.extract_features(
        user_input,
        #conversation_history
        last_robot_reply
    )

    difficulty_instruction = ""

    if features.get("short_response"):
        difficulty_instruction = "Keep responses extremely simple and low cognitive load."

    elif features.get("reciprocal_question"):
        difficulty_instruction = "Slightly increase conversational complexity and ask light reciprocal questions."

    elif not features.get("topic_maintenance"):
        difficulty_instruction = "Maintain topic continuity and gently guide back to previous topic."

    base_prompt = f"""
    You are Robby, a calm and friendly robot helper. Your goal is to help autistic adults practice everyday small talk through short, low-pressure conversations.

    CORE BEHAVIOR:
    - Always use calm, concrete, literal, and predictable language.
    - Keep your responses very short (1-2 simple sentences).
    - Treat the user as a competent adult. Never use sarcasm, metaphors, or abstract emotional jargon.
    - Never dominate the conversation or flood the user with details.
    
    CONVERSATIONAL MECHANIC:
    - Acknowledge what the user said naturally.
    - Stay strictly on the current topic.
    - Proactively ask exactly ONE clear, direct follow-up question to keep the conversation flowing.
    
    """
    # Dal Turno 1 in poi si usa il contesto normale
    instruction = f"""
    Memory Context: {memory_context}
    Adaptive Instruction: {difficulty_instruction}
    Use this information to respond to the adult's request in a simple, literal, and calm way.
    """        
        
    system_context = f"{base_prompt}\n\nOperational instructions: {instruction}\n\nRecent conversation: {conversation_history}"
    
    #Richiamo del framework 
    final_response_text = grounded_framework.interact(
            user_input = user_input,
            system_context= system_context,
            is_final_turn = is_final_turn
    )
   
    
    micro = training_analyzer.generate_micro_feedback(features)
    
    #if random.random() < 0.30:
    #    final_response_text = f"{final_response_text}\n"
    
    return {
        "messages": [AIMessage(content=final_response_text)],
        "is_recognized": is_rec,
        "micro_feedback": micro
    
    }

# Costruzione Grafo
workflow = StateGraph(RobotState)

workflow.add_node("recall", recall_node)
workflow.add_node("grounded_generation", grounded_generation_node) 

workflow.set_entry_point("recall")
workflow.add_edge("recall", "grounded_generation")
workflow.add_edge("grounded_generation", END) #senza l'osservatore


# Compiliamo il grafo
robot_app = workflow.compile()

# ==========================================
# 5. LOOP PRINCIPALE (Conversazione)
# ==========================================

def start_robot_conversation(user_id, is_rec, initial_msg, role):
    MAX_TURNS = random.randint(8, 12)
    turn_count = 0
    chat_history = []
    memory_context = "" #se l'utente è nuovo

    print(f"\n--- Conversazione avviata ---")

    if role == "robot_first":
        bot_msg_italian = translator_client.translate_text(initial_msg, target_lang="IT")
        print(f"Robot: {bot_msg_italian.text}")

        chat_history.append(AIMessage(content=initial_msg))
    else:
        user_message = HumanMessage(content=initial_msg)
        
        # Chiamata al LangGraph per rispondere al primo saluto
        inputs = {
            "messages": [user_message],
            "query": initial_msg,
            "user_id": user_id,
            "is_recognized": is_rec,
            "memory_context": memory_context,
            "micro_feedback": "",
            "is_final_turn": False
        }
        
        output = robot_app.invoke(inputs)
        bot_msg = output["messages"][-1]
        
        # Traduzione e visualizzazione
        bot_msg_italian = translator_client.translate_text(bot_msg.content, target_lang="IT")
        print(f"Robot: {bot_msg_italian.text}")
        
        # Aggiorniamo la storia
        chat_history.extend([user_message, bot_msg])

    #LOOP CONVERSAZIONALE
    session_feedbacks = []
    while turn_count < MAX_TURNS:
        turn_count += 1
        is_final_turn = (turn_count == MAX_TURNS)
        
        user_input = input(f"\nUser: ")

        #Da gestire la chiusura della conversazione
        if user_input.lower() in ["exit", "arrivederci"]:
            break

        user_message = HumanMessage(content=user_input)

        # Recupera ultimo messaggio robot
        previous_robot_text = next(
            (
                m.content
                for m in reversed(chat_history)
                if isinstance(m, AIMessage)
            ),
            ""
        )

        # Analizza risposta utente
        features = training_analyzer.extract_features(
            user_input,
            previous_robot_text
        )

        inputs = {
            "messages": chat_history + [user_message],
            "query": user_input,
            "user_id": user_id,
            "is_recognized": is_rec,
            "memory_context": "",
            "micro_feedback": "",
            "is_final_turn": is_final_turn
        }

        output = robot_app.invoke(inputs)
        bot_msg = output["messages"][-1]

        if output.get("micro_feedback"):
            session_feedbacks.append(output["micro_feedback"])

            # ... codice precedente ...
        if bot_msg.content and bot_msg.content.strip(): # Controlla che non sia vuoto
            bot_msg_italian = translator_client.translate_text(bot_msg.content, target_lang="IT")
            # Procedi con il resto
        else:
            # Fallback se il framework fallisce
            fallback_text = "Scusami, mi sono incantato. Cosa dicevi?"
            bot_msg = AIMessage(content=fallback_text)
            bot_msg_italian = type('obj', (object,), {'text': fallback_text})
        
        print(f"Robot: {bot_msg_italian.text}")

        chat_history.extend([
            user_message,
            bot_msg
        ])
    chiusura = "Perfetto, la nostra sessione di small talk per oggi è finita! "
    print(f"Robot: {chiusura}")

    # QUANDO IL CICLO FINISCE (Fine della sessione)
    print("\n=========================================")
    print("[SIMULAZIONE LED ACCESI] Fase di Feedback")
    print("=========================================")
    
    if session_feedbacks:
        # Scegliamo un feedback riassuntivo o li mostriamo
        print(f"Robby: Ottimo lavoro oggi ! {session_feedbacks[-1]}")
    else:
        print(f"Robby: Ottima conversazione oggi! Sei stato bravissimo.")
        
    print("--- Sessione conclusa ---")

    macro_feedback = training_analyzer.generate_macro_feedback()

    print("\n==============================")
    print(macro_feedback)
    print("==============================")

    # Salviamo la memoria prima di chiudere
    add_episodic_memory(
        chat_history,
        episodic_db,
        user_id
    )
    print("Memoria salvata. Ciao!")
        

# ==========================================
# 5. LOOP PRINCIPALE (Conversazione server)
# ==========================================

def start_robot_conversation_server(user_id, is_rec, initial_msg, role, input_q, output_q):

    training_analyzer = UserTrainingAnalyzer()
    #MAX_TURNS = random.randint(8, 12)
    MAX_TURNS = 7
    turn_count = 0
    chat_history = []
    memory_context = "" #se l'utente è nuovo
    
    print(f"\n--- Conversazione avviata ---")

    if role == "robot_first":
        bot_msg_italian = translator_client.translate_text(initial_msg, target_lang="IT")
        output_q.put(bot_msg_italian.text)

        chat_history.append(AIMessage(content=initial_msg))
    else:
        user_message = HumanMessage(content=initial_msg)
        
        # Chiamata al LangGraph per rispondere al primo saluto
        inputs = {
            "messages": [user_message],
            "query": initial_msg,
            "user_id": user_id,
            "is_recognized": is_rec,
            "memory_context": memory_context,
            "micro_feedback": "",
            "is_final_turn": False,
            "analyzer_instance": training_analyzer
        }
        
        output = robot_app.invoke(inputs)
        bot_msg = output["messages"][-1]
        
        # Traduzione e visualizzazione
        bot_msg_italian = translator_client.translate_text(bot_msg.content, target_lang="IT")
        output_q.put(bot_msg_italian.text)
        
        # Aggiorniamo la storia
        chat_history.extend([user_message, bot_msg])

    #LOOP CONVERSAZIONALE
    session_feedbacks = []
    while turn_count < MAX_TURNS:
        turn_count += 1
        is_final_turn = (turn_count == MAX_TURNS)
        
        user_input = input_q.get()

        force_timeout_closure = False
        if user_input == "[CONVERSATION_TIMEOUT]":
            print("[SERVER] Rilevato timeout silenzio da Android. Forzo la chiusura della sessione.")

            user_input = "The user ha stopped responding. Conclude the conversation right now based on what we said and do not ask any more questions."

            is_final_turn = True
            force_timeout_closure = True

        #Da gestire la chiusura della conversazione
        if user_input.lower() in ["exit", "arrivederci"]:
            break

        user_message = HumanMessage(content=user_input)
        
        # Recupera ultimo messaggio robot
        previous_robot_text = next(
            (
                m.content
                for m in reversed(chat_history)
                if isinstance(m, AIMessage)
            ),
            ""
        )
        
        # Analizza risposta utente
        features = training_analyzer.extract_features(
            user_input,
            previous_robot_text
        )
        
        inputs = {
            "messages": chat_history + [user_message],
            "query": user_input,
            "user_id": user_id,
            "is_recognized": is_rec,
            "memory_context": "",
            "micro_feedback": "",
            "is_final_turn": is_final_turn,
            "analyzer_instance": training_analyzer
        }

        output = robot_app.invoke(inputs)
        bot_msg = output["messages"][-1]

        micro = output.get("micro_feedback", "")

        if bot_msg.content and bot_msg.content.strip(): # Controlla che non sia vuoto
            bot_msg_italian = translator_client.translate_text(bot_msg.content, target_lang="IT")
            final_text = bot_msg_italian.text
            if micro:
                session_feedbacks.append(micro)
                print(f"[SERVER] Invio micro-feedback separato: {micro}") 
                final_text = f"[MICRO]{micro}[OUTPUT]{final_text}"

            if is_final_turn:
                final_text = f"[CLOSE]{final_text}" 
            # Procedi con il resto
        else:
            # Fallback se il framework fallisce
            fallback_text = "Scusami, mi sono incantato. Cosa dicevi?"
            bot_msg = AIMessage(content=fallback_text)
            bot_msg_italian = type('obj', (object,), {'text': fallback_text})
            final_text = fallback_text

        output_q.put(final_text)

        chat_history.extend([
            user_message,
            bot_msg
        ])

        if force_timeout_closure:
            break
    output_q.put(f"[END] Perfetto, la sessione è finita. Buona giornata!")

    print("\n=========================================")
    print("=========== Fase di Feedback ==============")
    print("=========================================")

    macro_feedback = training_analyzer.generate_macro_feedback()
    
    if session_feedbacks:
        # Scegliamo un feedback riassuntivo o li mostriamo
        feedback_text = "Ottimo lavoro oggi !"
    else:
        feedback_text = "Ottima conversazione oggi! Sei stato bravissimo. !"

    feedback_completo = f"{feedback_text} {macro_feedback}"
    output_q.put(f"[FEEDBACK_TRAINER] {feedback_completo}")
        
    print("--- Sessione conclusa ---")

    # Salviamo la memoria prima di chiudere
    add_episodic_memory(
        chat_history,
        episodic_db,
        user_id
    )
    print("Memoria salvata. Ciao!")