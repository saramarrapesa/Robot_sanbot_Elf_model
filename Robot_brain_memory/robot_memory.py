import os
import uuid
import operator
import getpass
from datetime import datetime
from typing import Annotated, List, Union, TypedDict

# LangChain & Frameworks
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings 
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.graph import StateGraph, END

# DeepFace per riconoscimento (dal nostro debug precedente)
from deepface import DeepFace

# ==========================================
# 1. CONFIGURAZIONE E AMBIENTE
# ==========================================

def _set_env(var: str):
    if not os.environ.get(var):
        os.environ[var] = getpass.getpass(f"{var}:")

_set_env("TAVILY_API_KEY")

# Inizializzazione Modelli
llm = ChatOllama(model="llama3", temperature=0, base_url="http://localhost:11434")
embeddings_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# ==========================================
# 2. INIZIALIZZAZIONE DATABASE (ChromaDB)
# ==========================================

# DB Volti (Nativo)
face_db = Chroma(
    collection_name="memoria_fotografica",
    embedding_function=None,
    persist_directory="./chroma_db_photos"
)

# DB Episodico (Conversazioni)
episodic_db = Chroma(
    collection_name="memoria_episodica",
    embedding_function=embeddings_model,
    persist_directory="./chroma_db_episodic"
)

# DB Semantico (Conoscenza Web)
semantic_db = Chroma(
    collection_name="memoria_semantica",
    embedding_function=embeddings_model,
    persist_directory="./chroma_db_semantic"
)

# ==========================================
# 3. LOGICA DI MEMORIA E RIFLESSIONE
# ==========================================

reflection_prompt_template = """
Sei un sistema di analisi riflessiva per un robot sociale. 
Il tuo compito è analizzare la conversazione appena avvenuta tra il robot e un bambino per estrarre "memorie" che guideranno le interazioni future.

Analizza la conversazione e crea una riflessione seguendo queste regole:
1. Se non hai abbastanza informazioni per un campo, usa "N/A".
2. Sii estremamente conciso: ogni stringa deve essere una frase chiara e utile.
3. Focalizzati su elementi che aiutano il robot a essere più empatico e coerente in futuro.
4. I context_tags devono essere specifici per il tipo di interazione.
5. Rispondi esclusivamente in formato JSON.
6. Non includere introduzioni (es."Ecco il JSON") o conclusioni.

Genera un JSON valido esattamente in questo formato:
{{
    "context_tags": [              // 2-4 parole chiave che aiutano a identificare future conversazioni simili
        string,                    // Usa campi specifici come "emozione_positiva", "argomento_interesse", "difficoltà_comunicativa"
        ...
    ],
    "conversation_summary": string, // Una frase che riassume l'interazione e l'obiettivo raggiunto.
    "what_worked": string,         // Cosa ha stimolato una reazione positiva nel bambino (es. tono calmo, argomento specifico).
    "what_to_avoid": string        // Cosa ha causato chiusura o confusione (es. frasi troppo lunghe, termini complessi).
}}

Esempi:
- context_tags: ["interesse_astronomia", "interazione_calma"]
- conversation_summary: "Il bambino ha mostrato curiosità verso i pianeti e ha risposto positivamente alle spiegazioni semplici."
- what_worked: "L'uso di similitudini con oggetti quotidiani per spiegare la grandezza del sole."
- what_to_avoid: "Cambiare argomento troppo velocemente senza aspettare il feedback del bambino."

Ecco la conversazione precedente:
{conversation}
"""
reflection_prompt = ChatPromptTemplate.from_template(reflection_prompt_template)
reflection_llm = ChatOllama(model="llama3", temperature=0,base_url="http://localhost:11434",format="json")
reflect = reflection_prompt | reflection_llm | JsonOutputParser()

def format_conversation(messages):
    conversation = []
    for message in messages[1:]:
        conversation.append(f"{message.type.upper()}: {message.content}")
    return "\n".join(conversation)

def procedural_memory_update(what_worked, what_to_avoid):
    # Load Existing Procedural Memory Instructions
    with open("./procedural_memory.txt", "r") as content:
        current_takeaways = content.read()

    # Load Existing and Gathered Feedback into Prompt
    procedural_prompt = f"""Il tuo compito è quello di mantenere un elenco costantemente aggiornato delle istruzioni procedurali più importanti per un assistente IA. Devi affinare e migliorare questo elenco di punti chiave sulla base dei nuovi feedback ricevuti durante le conversazioni, preservando al contempo le informazioni più preziose già presenti.

    CURRENT TAKEAWAYS:
    {current_takeaways}

    NEW FEEDBACK:
    Quello che ha funzionato bene:
    {what_worked}

    Ciò che devi evitare:
    {what_to_avoid}

    Per favore genera un elenco aggiornato di massimo 10 punti chiave che combini:

    1.Gli insight più preziosi dei punti chiave attuali
    2.I nuovi apprendimenti derivati dal feedback recente
    3.Eventuali insight sintetizzati che combinano più apprendimenti

    Requisiti per ogni punto chiave:

    -Deve essere specifico e attuabile
    -Deve affrontare un aspetto distinto del comportamento
    -Deve includere una chiara motivazione
    -Deve essere scritto in forma imperativa (es. “Mantieni il contesto della conversazione...”)

    Formatta ogni punto chiave come:
    [#]. [Istruzione] - [Breve motivazione]

    L'elenco finale dovrebbe:

    -Essere ordinato per importanza/impatto
    -Coprire una gamma diversificata di aspetti dell’interazione
    -Concentrarsi su comportamenti concreti piuttosto che su principi astratti
    -Preservare i punti chiave esistenti particolarmente validi
    -Integrare nuovi insight quando apportano miglioramenti significativi

    Restituisci al massimo 10 punti chiave, sostituendo o combinando quelli esistenti se necessario per mantenere l’insieme di linee guida più efficace.
    Restituisci solo l'elenco, senza introduzioni o spiegazioni.
    """

    # Generate New Procedural Memory
    procedural_memory = llm.invoke(procedural_prompt)

    # Write to File
    with open("./procedural_memory.txt", "w") as content:
        content.write(procedural_memory.content)

    return

def add_episodic_memory(messages, episodic_db, user_id):
    #Format the conversation
    conversation = format_conversation(messages)
    #Reflect on the conversation
    reflection = reflect.invoke({"conversation": conversation})
    
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
    #return results[0].metadata

# ==========================================
# 4. DEFINIZIONE DEL GRAFO (LANGGRAPH)
# ==========================================

class RobotState(TypedDict):
    messages: Annotated[List[Union[HumanMessage, SystemMessage]], operator.add]
    query: str
    user_id: str  # Aggiunto per filtrare la memoria
    memory_context: str
    web_result: str
    needs_web: bool

def recall_node(state: RobotState):
    query = state["query"]
    uid = state["user_id"]
    
    # 1. Recall Episodico FILTRATO per user_id
    episodic_meta = episodic_recall(query,episodic_db,uid)
    
    # 2. Carica memoria procedurale
    with open("./procedural_memory.txt", "r") as f: proc = f.read()
    
    if isinstance(episodic_meta, dict):
        episodic_context = f"""
        Il bambino si chiama o ha parlato di: {episodic_meta.get('conversation_summary')}
        Cose che gli piacciono: {episodic_meta.get('context_tags')}
        Strategia vincente: {episodic_meta.get('what_worked')}

        Inoltre, ecco 10 linee guida per interagire con l'utente corrente: {proc}
        """
    else:
        episodic_context = "Nessun ricordo precedente con questo bambino."

    # 3. Logica Semantica
    semantic_context = ""
    needs_web = False
    
    keywords = ["chi è", "cos'è", "che cos'è", "spiegami", "perché", "come mai"]
    is_educational_query = any(k in query for k in keywords)  

    if is_educational_query:
        semantic_results = semantic_db.similarity_search_with_score(query, k=2)

        if semantic_results and semantic_results[0][1] < 0.5:
            semantic_context = "\n".join([doc.page_content for doc, score in semantic_results])
            needs_web = False # Sappiamo già la risposta!
            print("--- Risposta trovata nel RAG Semantico ---")
        else:
            needs_web = True # Dobbiamo chiedere a Tavily
            print("--- Conoscenza non trovata, serve Tavily ---")

    # --- 3. UNIONE DEI CONTESTI ---
    # Uniamo tutto in una stringa che passeremo al nodo Generate
    full_context = f"CONTESTO EPISODICO (IDENTITÀ):\n{episodic_context}\n\n"
    if semantic_context:
        full_context += f"CONOSCENZA SEMANTICA (FATTI):\n{semantic_context}"

    return {
        "memory_context": full_context, 
        "needs_web": needs_web,
        "query": query # Passiamo la query pulita
    }

def web_search_node(state: RobotState):
    search = TavilySearchResults(k=3)
    query = state["query"]
    print(f"--- RICERCA AVANZATA CON TAVILY: {query} ---")
    
    # 1. Esegui la ricerca
    # Tavily restituisce una lista di Documenti con già il contenuto pulito
    search_docs = search.invoke(query)
    
    # 2. Prepariamo il testo per l'LLM e per il Database
    combined_web_content = ""
    texts_to_save = []

    text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=400, 
            chunk_overlap=50
        )
    
    for doc in search_docs:
        content = doc.get('content', '')
        combined_web_content += content + "\n\n"       
        
        # Dividiamo ulteriormente se il contenuto di Tavily è lungo
        chunks = text_splitter.split_text(content)
        texts_to_save.extend(chunks)

    # 3. Salvataggio nel RAG Semantico (Memoria a lungo termine)
    if texts_to_save:
        semantic_db.add_texts(
            texts=texts_to_save,
            metadatas=[{"source": "tavily", "query": query} for _ in texts_to_save]
        )
        print(f"--- {len(texts_to_save)} frammenti salvati nel RAG Semantico ---")
    
    return {"web_result": combined_web_content}

def generate_node(state: RobotState):
    # Costruiamo il sistema prompt simile al tuo episodic_system_prompt
    prompt = f"""
    Sei un robot amichevole per bambini autistici. PARLA IN ITALIANO.
    Contesto Memoria: {state['memory_context']}
    Informazioni dal Web: {state.get('web_result', 'N/A')}
    
    Usa queste informazioni per rispondere in modo semplice e calmo.
    """
    sys_msg = SystemMessage(content=prompt)
    
    # Combiniamo i messaggi per l'LLM
    full_messages = [sys_msg] + state["messages"]
    response = llm.invoke(full_messages)
    
    return {"messages": [response]}

# BIVIO: Se serve il web, vai a web_search, altrimenti a generate
def router(state):
    if state["needs_web"]:
        return "web_search"
    return "generate"


# Costruzione Grafo
workflow = StateGraph(RobotState)

workflow.add_node("recall", recall_node)
workflow.add_node("web_search", web_search_node)
workflow.add_node("generate", generate_node)
workflow.set_entry_point("recall")
workflow.add_conditional_edges("recall", router)
workflow.add_edge("web_search", "generate")
workflow.add_edge("generate", END)

# Compiliamo il grafo
robot_app = workflow.compile()

# ==========================================
# 5. LOOP PRINCIPALE (Conversazione)
# ==========================================

def start_robot_conversation(user_id, user_name):
    """Questa è la funzione che verrà chiamata dal modulo visione"""
    print(f"\n--- Conversazione avviata con {user_name} ---")
    chat_history = []
    
    while True:
        user_input = input(f"\n{user_name}: ")
        user_message = HumanMessage(content=user_input)

        if user_input.lower() in ["exit", "arrivederci"]:
            # Salviamo la memoria prima di chiudere
            add_episodic_memory(chat_history, episodic_db, user_id)
            print("Memoria salvata. Ciao!")
            break
            
        inputs = {
            "messages": chat_history + [user_message],
            "query": user_input,
            "user_id": user_id,
            "memory_context": "",
            "needs_web": False
        }
        
        output = robot_app.invoke(inputs)
        bot_msg = output["messages"][-1]
        print(f"Robot: {bot_msg.content}")
        chat_history.extend([user_message, bot_msg])