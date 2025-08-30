import os
import logging
import sqlite3
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from collections import deque
import paho.mqtt.client as mqtt
import threading
import socket
import uvicorn

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Konfigurasi
MQTT_BROKER = os.getenv("MQTT_BROKER", "5374fec8494a4a24add8bb27fe4ddae5.s1.eu.hivemq.cloud:8883")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "throng_user")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "ThrongPass123!")
DEFAULT_SPAWN_TARGET = os.getenv("DEFAULT_SPAWN_TARGET", "192.168.1.10")
DEFAULT_SSH_USERNAME = os.getenv("DEFAULT_SSH_USERNAME", "admin")
DEFAULT_SSH_PASSWORD = os.getenv("DEFAULT_SSH_PASSWORD", "admin")
HISTORY_SIZE = 50

# Pastikan direktori data ada
if not os.path.exists("data"):
    os.makedirs("data")
DB_PATH = os.path.join("data", "throng.db")

# Database
db = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = db.cursor()

def init_db():
    cursor.execute('''CREATE TABLE IF NOT EXISTS agents 
                      (id INTEGER PRIMARY KEY, agent_id TEXT, status TEXT, last_seen DATETIME, ip TEXT, host TEXT, priority INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS reports 
                      (id INTEGER PRIMARY KEY, agent_id TEXT, data TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS actions 
                      (id INTEGER PRIMARY KEY, agent_id TEXT, action TEXT, target TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, status TEXT)''')
    db.commit()

init_db()

# Log historis
report_history = deque(maxlen=HISTORY_SIZE)
action_history = deque(maxlen=HISTORY_SIZE)

# MQTT
mqtt_client = mqtt.Client()
active_websockets = []

def on_connect(client, userdata, flags, rc):
    logger.info(f"MQTT connected with result code {rc}")
    if rc == 0:
        client.subscribe("throng/reports")
        client.subscribe("throng/commands/#")

def on_message(client, userdata, msg):
    if msg.topic.startswith("throng/reports"):
        report = eval(msg.payload.decode())  # Sederhana, ganti dengan json.loads jika perlu
        report_history.append(report)
        for ws in active_websockets:
            ws.send_text(str({"type": "report", "data": report}))

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.connect(MQTT_BROKER.split(":")[0], int(MQTT_BROKER.split(":")[1]), 60)
mqtt_client.loop_start()

# Fungsi spawn agent (sederhana)
def spawn_agent_ssh(target, credentials):
    try:
        new_agent_id = "temp_" + str(hash(target))  # Placeholder, ganti dengan logika nyata
        cursor.execute("INSERT INTO agents (agent_id, status, last_seen, ip, host) VALUES (?, ?, ?, ?, ?)", 
                       (new_agent_id, "active", time.strftime("%Y-%m-%d %H:%M:%S"), socket.gethostbyname(target), target))
        db.commit()
        logger.info(f"Spawned agent {new_agent_id} on {target}")
        return new_agent_id
    except Exception as e:
        logger.error(f"Error spawning agent: {e}")
        return None

# Penanganan perintah
def handle_command(command):
    agent_id = command.get("agent_id", "unknown")
    action = command.get("action")
    target = command.get("target")
    if action == "spawn" and target:
        new_agent_id = spawn_agent_ssh(target, {"username": DEFAULT_SSH_USERNAME, "password": DEFAULT_SSH_PASSWORD})
        if new_agent_id:
            cursor.execute("INSERT INTO actions (agent_id, action, target, status) VALUES (?, ?, ?, ?)", 
                           (agent_id, action, target, "success"))
        else:
            cursor.execute("INSERT INTO actions (agent_id, action, target, status) VALUES (?, ?, ?, ?)", 
                           (agent_id, action, target, "failed"))
        db.commit()

# Endpoint HTTP default
@app.get("/", response_class=HTMLResponse)
async def read_root():
    html_content = """
    <html>
        <head><title>Throng Hive</title></head>
        <body>
            <h1>Welcome to Throng Hive</h1>
            <p>This is a CLI-based agent monitoring system.</p>
            <p>To use the CLI, connect to the WebSocket endpoint: <code>/ws</code> using a WebSocket client.</p>
            <p>Supported commands: <code>{"agent_id": "test", "action": "spawn", "target": "192.168.1.10"}</code></p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# WebSocket untuk CLI
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    logger.info("CLI connected via WebSocket")
    print("=== Throng Hive Terminal ===")
    print("Type 'help' for commands. Use 'exit' to quit.")

    while True:
        try:
            data = await websocket.receive_text()
            command = eval(data)  # Sederhana, ganti dengan json.loads jika perlu
            handle_command(command)
            print(f"Command executed: {command}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)