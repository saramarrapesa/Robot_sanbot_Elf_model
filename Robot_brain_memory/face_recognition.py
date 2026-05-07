import uuid
from deepface import DeepFace
from langchain_chroma import Chroma
# Importiamo la funzione dal file del cervello
from robot_memory import start_robot_conversation
from datetime import datetime


# Inizializziamo il database dei volti
face_db = Chroma(
    collection_name="memoria_fotografica",
    embedding_function=None,
    persist_directory="./chroma_db_photos"
)

def identify_child():
    print("Inquadra il bambino...")
    # Qui andrebbe il codice per scattare la foto dalla webcam
    img_path = "ariana.jpg" 
    
    try:
        models = ["VGG-Face", "Facenet", "OpenFace", "DeepFace", "Dlib", "ArcFace"]
        embedding_obj = DeepFace.represent(img_path, model_name = models[5])

        # 1. Estrarre il vettore (Feature Extraction)
        #embedding_obj = DeepFace.represent(img_path = "ritaglio_android.jpg", model_name = "ArcFace")
        vettore_volto = embedding_obj[0]["embedding"]
        
        # 1. Ricerca NATIVA nel database 
        risultati = face_db._collection.query(
            query_embeddings=[vettore_volto],
            n_results=1
        )

        # Variabile per capire se abbiamo trovato qualcuno
        bambino_riconosciuto = False
        # 2. Controlliamo se il database ha restituito qualcosa
        if risultati['ids'] and risultati['ids'][0]:
            distanza = risultati['distances'][0][0]
            
            # Se la distanza è minore di 0.6, è lo stesso bambino
            if distanza < 0.6:
                nome_bambino = risultati['metadatas'][0][0].get("name", "Sconosciuto")
                user_id = risultati['ids'][0][0]
                print(f"Riconosciuto: {nome_bambino} (ID: {user_id}) - Distanza: {distanza}")
                bambino_riconosciuto = True
            else:
                print(f"Bambino non riconosciuto (Distanza: {distanza}).")
        
        # 3. Se NON è stato riconosciuto (o perché il DB era vuoto o la distanza era alta)
        if not bambino_riconosciuto:
            print("Registrazione in corso...")
            
            user_id = str(uuid.uuid4())
            timestamp_attuale = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            nome_bambino = "Nuovo amico"
            
            face_db._collection.add(
                ids=[user_id],
                embeddings=[vettore_volto],
                metadatas=[{
                    "user_id": user_id,
                    "name": nome_bambino, 
                    "data_registrazione": timestamp_attuale,
                    "tipo": "face_embedding"
                }]
            )

        
        return user_id, nome_bambino
            
    except Exception as e:
        print(f"Errore visione: {e}")
        return "guest", "Ospite" 

if __name__ == "__main__":
    # 1. Riconoscimento
    uid, name = identify_child()
    
    # 2. Avvio Conversazione (passando ID e Nome al cervello)
    start_robot_conversation(uid, name)