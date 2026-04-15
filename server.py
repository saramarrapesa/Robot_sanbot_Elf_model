from flask import Flask, jsonify, request

app = Flask(__name__)

current_command = {"action": "idle"}

@app.route("/get_command")
def get_command():
    return jsonify(current_command)

@app.route("/send_command", methods=["POST"])
def send_command():
    global current_command
    current_command = request.json
    return {"status": "ok"}

app.run(host="0.0.0.0", port=5000)