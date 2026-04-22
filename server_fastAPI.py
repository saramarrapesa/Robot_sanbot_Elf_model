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

#uvicorn server_fastAPI:app --host 0.0.0.0 --port 8000
#nel terminale apro python e faccio 
# import requests
#requests.post("http://127.0.0.1:8000/command", json={"text":"funziona yeeee"})