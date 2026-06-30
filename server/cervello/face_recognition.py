import os
import tensorflow as tf
tf.config.set_visible_devices([], 'GPU')
import uuid
from deepface import DeepFace

from langchain_chroma import Chroma
from datetime import datetime

# Inizializziamo il database dei volti
face_db = Chroma(
    collection_name="memoria_fotografica",
    embedding_function=None,
    persist_directory="./chroma_db_photos"
)
#img_path da aggiungere come variabile per il server
def identify(img_path): #per il server aggiungere la variabile img_path
    print("face recognition inizializzato...")
    
    try:
        models = ["VGG-Face", "Facenet", "OpenFace", "DeepFace", "Dlib", "ArcFace"]
        embedding_obj = DeepFace.represent(img_path, model_name = models[5], enforce_detection=False) #per il server

        # 1. Estrarre il vettore (Feature Extraction) senza il server
        #embedding_obj = DeepFace.represent(img_path = "HarryStyles.jpg", model_name = "ArcFace") 
        vettore_volto = embedding_obj[0]["embedding"]
        
        # 1. Ricerca NATIVA nel database 
        risultati = face_db._collection.query(
            query_embeddings=[vettore_volto],
            n_results=1
        )

        # Variabile per capire se abbiamo trovato qualcuno
        is_rec = False
        # 2. Controlliamo se il database ha restituito qualcosa
        if risultati['ids'] and risultati['ids'][0]:
            distanza = risultati['distances'][0][0]
            
            # Se la distanza è minore di 0.6, è lo stesso bambino
            if distanza < 0.6:
                #nome_bambino = risultati['metadatas'][0][0].get("name", "Sconosciuto")
                user_id = risultati['ids'][0][0]
                print(f"Riconosciuto: (ID: {user_id}) - Distanza: {distanza}")
                is_rec = True
            else:
                print(f"Non riconosciuto (Distanza: {distanza}).")
        
        # 3. Se NON è stato riconosciuto (o perché il DB era vuoto o la distanza era alta)
        if not is_rec:
            print("Registrazione in corso...")
            
            user_id = str(uuid.uuid4())
            timestamp_attuale = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            #nome_bambino = "Nuovo amico"
            
            face_db._collection.add(
                ids=[user_id],
                embeddings=[vettore_volto],
                metadatas=[{
                    "user_id": user_id,
                    #"name": nome_bambino, 
                    "data_registrazione": timestamp_attuale,
                    "tipo": "face_embedding"
                }]
            )

        
        return user_id, is_rec #nome_bambino
            
    except Exception as e:
        print(f"Errore visione: {e}")
        return "guest", False #, False

