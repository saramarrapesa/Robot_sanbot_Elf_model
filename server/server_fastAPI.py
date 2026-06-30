from fastapi import FastAPI, File, UploadFile, HTTPException #, BackgroundTasks
from pydantic import BaseModel
import queue
import threading
import math
import time
from face_recognition import identify
from robot_memory_llama3 import get_session_count, start_robot_conversation_server

app = FastAPI()

#code per gestire i messaggi tra i thread
input_queue = queue.Queue()
output_queue = queue.Queue()
session_queue = queue.Queue() # Coda per avviare il cervello

#----- ENDPOINT PER IL ROBOT ---
@app.post("/input")
async def receive_input(data: dict):
    """Riceve la voce del robot e la mette nella coda per il LangGraph"""
    text = data.get("text", "")
    print(f"Sanbot dice: {text}")
    input_queue.put(text)
    return {"status": "receveid"}

@app.get("/command")
async def send_command():
    """Il robot chiama questo in pooling per sapere cosa dire"""
    try:
        #recupera il messaggio dalla coda senza bloccare
        message = output_queue.get_nowait()
        return {"command": message}
    except queue.Empty:
        return {"command": ""}

@app.post("/recognize")
async def start_Session(file: UploadFile = File()):
    """ Riceve la foto da android, riconosce e avvia il cervello """
    print("[SERVER] Ricevuta immagine per face recognition...")

    #salviamo temporaneamente l'immagine
    img_path = "face.jpg"
    with open(img_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    uid, is_rec = identify(img_path) #funzione di face recognition


    session_data = {
        "uid": uid,
        "is_rec": is_rec,
        #"session_n": session_n
        #"wait_time": wait_time
    }
    session_queue.put(session_data)
    # L'endpoint finisce qui e risponde ad Android senza bloccarsi!
    return {"status": "success", "user_id": uid, "recognized": is_rec} 

 

#---- LOGICA DEL CERVELLO ----
def brain_worker():
    while True:
        
        data = session_queue.get()
        
        uid = data["uid"]
        is_rec = data["is_rec"]
        #wait_time = data["wait_time"]
        #session_n = data["session_n"]
    
        #print(f"Sessione innescata. Aspetto iniziativa utente per {wait_time:.1f} sec...")
        
        user_initiated = False
        user_input = ""
        #user_input = input_queue.get()

        while True:
            user_input = input_queue.get() # Il thread si mette in ascolto qui a ogni turno
        
            if user_input == "[USER_SILENT]":
                user_initiated = False
                print("[SERVER] Android ha rilevato silenzio. Mando il prompt visivo e resto in attesa del prossimo tentativo.")
                tag = "[PROMPT_VISIVO]"
                prompt_visivo = "Ricordati di salutarmi quando inizia la sessione di training"
                output_queue.put(f"{tag} {prompt_visivo}")
                # NOTA: Qui NON mettiamo il "break". Il ciclo ricomincia e torna su input_queue.get() 
                # aspettando che l'utente dica qualcosa o che Android mandi [SALUTO_INIZIALE]

            elif user_input == "[SALUTO_INIZIALE]":
                user_initiated = False
                print("[SERVER] Android segnala il terzo silenzio. Il robot prende l'iniziativa e avvia l'LLM.")
                if is_rec:
                    saluto_iniziale = "Hello! I'm glad to see you again. How are you today?"
                else:
                    saluto_iniziale = "Hello! I am Robby, a social robot. How are you today?"
                    
                start_robot_conversation_server(uid, is_rec, initial_msg=saluto_iniziale, role="robot_first", input_q=input_queue, output_q=output_queue)
                break # USCIAMO DAL LOOP: la conversazione è partita, ora se ne occupa il ciclo interno dell'LLM
        
            else: 
                # L'utente ha risposto al 1°, al 2° o al 3° tentativo!
                user_initiated = True
                print(f"[SERVER] L'utente ha preso l'iniziativa e ha detto: {user_input}")
                start_robot_conversation_server(uid, is_rec, initial_msg=user_input, role="user_first", input_q=input_queue, output_q=output_queue)
                break # USCIAMO DAL LOOP: la conversazione è partita in modalità user_first
        
        print("[SERVER] Fase di inizializzazione superata con successo. Conversazione passata all'IA.")
        print("Sessione terminata. Torno in attesa")
    
threading.Thread(target=brain_worker, daemon=True).start()



#uvicorn server_fastAPI:app --host 0.0.0.0 --port 8000

