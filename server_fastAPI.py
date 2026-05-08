from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

last_command = None

class Command(BaseModel):
    text: str

@app.post("/command")
def set_command(cmd: Command):
    global last_command
    last_command = cmd.text
    return {"status": "ok", "saved": last_command}

@app.get("/command")
def get_command():
    global last_command
    cmd = last_command
    last_command = None  # letto 
    return {"command": cmd}

last_input = ""
last_output = ""

class InputText(BaseModel):
    text: str

@app.post("/input")
def receive_input(data: InputText):
    global last_input, last_output

    last_input = data.text
    print("Ricevuto:", last_input)

    # Simulazione LLM
    last_output = "Hai detto: " + last_input

    return {"status": "ok"}

@app.get("/command")
def send_command():
    global last_output

    response = last_output
    last_output = ""

    return {"command": response}

@app.route('/recognize', methods=['POST'])
def recognize():
    if 'image' not in request.files:
        return jsonify({"error": "No image"}), 400
    
    file = request.files['image']
    img_path = "received_face.jpg"
    file.save(img_path)
    
    # Chiamiamo la tua funzione di riconoscimento passandogli il file appena ricevuto
    # Nota: dovrai modificare identify_child per accettare un path come argomento
    uid, name = identify_child_from_path(img_path)
    
    return jsonify({
        "status": "success",
        "user_id": uid,
        "name": name
    })

# Endpoint per far partire la conversazione (opzionale, se vuoi triggerarla dal server)
@app.route('/start_chat', methods=['POST'])
def start_chat():
    data = request.json
    # Qui lanciamo la conversazione sul terminale del PC 
    # o inviamo un comando al robot
    start_robot_conversation(data['user_id'], data['name'])
    return jsonify({"status": "started"})

#uvicorn server_fastAPI:app --host 0.0.0.0 --port 8000
#nel terminale apro python e faccio 
# import requests
#requests.post("http://127.0.0.1:8000/command", json={"text":"funziona yeeee"})