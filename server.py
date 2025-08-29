# server.py - Throng Hive (Fixed & Stable)

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import json
import time
import os
from pydantic import BaseModel
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
from sklearn.ensemble import IsolationForest
import numpy as np
import paramiko
import requests
import uuid
import logging
import socket

# ============ SETUP ============
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ CONFIG ============
MQTT_BROKER = os.getenv("MQTT_BROKER", "5374fec8494a4a24add8bb27fe4ddae5.s1.eu.hivemq.cloud:8883")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "throng_user")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "ThrongPass123!")
DEFAULT_SPAWN_TARGET = os.getenv("DEFAULT_SPAWN_TARGET", "192.168.1.10")
DEFAULT_SSH_USERNAME = os.getenv("DEFAULT_SSH_USERNAME", "admin")
DEFAULT_SSH_PASSWORD = os.getenv("DEFAULT_SSH_PASSWORD", "admin")
AUTO_SPAWN_INTERVAL = int(os.getenv("AUTO_SPAWN_INTERVAL", "300"))

# ============ DB Helper ============
def get_db():
    conn = sqlite3.connect("throng.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS reports 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, data TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS counterattacks 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, target TEXT, action TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS agents 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, status TEXT, last_seen DATETIME, ip TEXT, host TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS targets 
                 (id INTEGER PRIMARY KEY, target TEXT, vulnerability TEXT, status TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, score REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS emergency_logs 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, action TEXT, details TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# ============ MODEL PERINTAH ============
class Command(BaseModel):
    agent_id: str
    action: str
    target: str = None
    params: dict = {}
    emergency: bool = False

# ============ MQTT ============
mqtt_client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
active_websockets = []

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("MQTT connected successfully")
        client.subscribe("throng/reports")
    else:
        logger.error(f"MQTT connection failed with code {rc}")

def on_message(client, userdata, msg):
    if msg.topic == "throng/reports":
        try:
            report = json.loads(msg.payload.decode())
            for ws in active_websockets:
                asyncio.create_task(ws.send_text(json.dumps({"type": "report", "data": report})))
        except Exception as e:
            logger.error(f"Error: {e}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.tls_set()
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

# Validasi MQTT_BROKER
try:
    broker_host = MQTT_BROKER.split(":")[0]
    broker_port = int(MQTT_BROKER.split(":")[1])
except Exception as e:
    logger.error(f"Invalid MQTT_BROKER format: {MQTT_BROKER}")
    broker_host = "localhost"
    broker_port = 1883

try:
    mqtt_client.connect(broker_host, broker_port, 60)
    mqtt_client.loop_start()
except Exception as e:
    logger.error(f"Failed to connect to MQTT: {e}")

# ============ MODEL ANOMALI ============
anomaly_model = IsolationForest(contamination=0.1, random_state=42)

def analyze_threats(reports):
    if len(reports) < 2:
        return [0] * len(reports)
    data = []
    for r in reports:
        traffic = r["data"].get("network_traffic", 0)
        vuln_count = len(r["data"].get("vulnerability", []))
        data.append([traffic, vuln_count])
    X = np.array(data)
    preds = anomaly_model.fit_predict(X)
    return [bool(x == -1) for x in preds]

# ============ ENDPOINTS ============

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    logger.info(f"Rendering dashboard.html with version {int(time.time())}")
    return templates.TemplateResponse("dashboard.html", {"request": request, "version": int(time.time())})

@app.get("/api/data")
async def get_dashboard_data():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT agent_id, status, last_seen, ip, host FROM agents WHERE status = 'active'")
    agents = [dict(row) for row in cur.fetchall()]

    cur.execute("SELECT target, vulnerability, status, timestamp, score FROM targets")
    targets = [dict(row) for row in cur.fetchall()]
    for t in targets:
        t["vulnerability"] = json.loads(t["vulnerability"])

    cur.execute("SELECT agent_id, data, timestamp FROM reports ORDER BY timestamp DESC LIMIT 100")
    reports = [dict(row) for row in cur.fetchall()]
    for r in reports:
        r["data"] = json.loads(r["data"])

    anomalies = analyze_threats(reports)
    for i, r in enumerate(reports):
        if i < len(anomalies):
            r["data"]["is_anomaly"] = anomalies[i]

    cur.execute("SELECT agent_id, action, details, timestamp FROM emergency_logs ORDER BY timestamp DESC LIMIT 100")
    emergency_logs = [dict(row) for row in cur.fetchall()]
    for e in emergency_logs:
        e["details"] = json.loads(e["details"])

    conn.close()

    return {
        "agents": agents,
        "targets": targets,
        "reports": reports,
        "emergency_logs": emergency_logs
    }

@app.post("/command")
async def send_command(command: Command):
    allowed = ["block_ip", "send_honeypot", "redirect_traffic", "spawn_agent", "replicate", "scan_target", "exploit_target"]
    if command.action not in allowed:
        return {"status": "invalid action"}

    conn = get_db()
    cur = conn.cursor()
    if command.target:
        cur.execute("INSERT INTO counterattacks (agent_id, target, action) VALUES (?, ?, ?)", 
                    (command.agent_id, command.target, command.action))
        if command.emergency:
            cur.execute("INSERT INTO emergency_logs (agent_id, action, details) VALUES (?, ?, ?)", 
                        (command.agent_id, command.action, json.dumps({"target": command.target, "params": command.params})))
    conn.commit()
    conn.close()

    mqtt_client.publish(f"throng/commands/{command.agent_id}", json.dumps(command.dict()))
    for ws in active_websockets:
        asyncio.create_task(ws.send_text(json.dumps({"type": "command", "data": command.dict()})))

    return {"status": f"Command {command.action} sent"}

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

            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO reports (agent_id, data) VALUES (?, ?)", (agent_id, json.dumps(report_data)))
            cur.execute("INSERT OR REPLACE INTO agents (agent_id, status, last_seen, ip) VALUES (?, ?, ?, ?)", 
                        (agent_id, "active", time.strftime("%Y-%m-%d %H:%M:%S"), report_data.get("ip", "unknown")))
            if "vulnerability" in report_data:
                score = len(report_data.get("vulnerability", [])) * 0.2
                cur.execute("INSERT INTO targets (target, vulnerability, status, score) VALUES (?, ?, ?, ?)", 
                            (report_data.get("target"), json.dumps(report_data.get("vulnerability")), "scanned", score))
            conn.commit()
            conn.close()
            logger.info(f"Saved report from {agent_id}")
    except Exception as e:
        logger.error(f"WS error: {e}")
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

@app.get("/health")
async def health():
    return {"status": "ok"}

import atexit
@atexit.register
def cleanup():
    try:
        db_conn = get_db()
        db_conn.close()
    except:
        pass
    mqtt_client.loop_stop()
    logger.info("Cleanup done.")