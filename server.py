import os
import sys
import logging
import paramiko
import paho.mqtt.client as mqtt
import psutil
import requests
import sqlite3
import uuid
from fastapi import FastAPI, WebSocket
from datetime import datetime
from collections import deque
import threading
import socket
import asyncio
import websockets

app = FastAPI()
logging.basicConfig(level=logging.INFO)  # Diimpor dan dikonfigurasi dengan benar
logger = logging.getLogger(__name__)

# Konfigurasi
JWT_SECRET = os.getenv("JWT_SECRET", "throng_default_secret_1234567890")
MQTT_BROKER = os.getenv("MQTT_BROKER", "5374fec8494a4a24add8bb27fe4ddae5.s1.eu.hivemq.cloud:8883")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "throng_user")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "ThrongPass123!")
DEFAULT_SPAWN_TARGET = os.getenv("DEFAULT_SPAWN_TARGET", "192.168.1.10")
DEFAULT_SSH_USERNAME = os.getenv("DEFAULT_SSH_USERNAME", "admin")
DEFAULT_SSH_PASSWORD = os.getenv("DEFAULT_SSH_PASSWORD", "admin")
DEADMAN_TIMEOUT = int(os.getenv("DEADMAN_TIMEOUT", 600))
HISTORY_SIZE = 50

# Konfigurasi WhatsApp dari SkyNet (opsional, isi jika digunakan)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "whatsapp:+6281234567890")

# Database
db = sqlite3.connect("throng.db", check_same_thread=False)
cursor = db.cursor()

def init_db():
    cursor.execute('''CREATE TABLE IF NOT EXISTS agents 
                      (id INTEGER PRIMARY KEY, agent_id TEXT, status TEXT, last_seen DATETIME, ip TEXT, host TEXT, priority INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS reports 
                      (id INTEGER PRIMARY KEY, agent_id TEXT, data TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS actions 
                      (id INTEGER PRIMARY KEY, agent_id TEXT, action TEXT, target TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, status TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS tactics 
                      (id INTEGER PRIMARY KEY, pattern TEXT UNIQUE, response TEXT, score REAL DEFAULT 1.0)''')
    db.commit()

init_db()

# Log historis
report_history = deque(maxlen=HISTORY_SIZE)
action_history = deque(maxlen=HISTORY_SIZE)

# MQTT
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
active_websockets = []

def on_connect(client, userdata, flags, rc, properties=None):
    logger.info(f"MQTT connected with result code {rc}")
    if rc == 0:
        client.subscribe("throng/reports")
        client.subscribe("throng/commands/#")
        client.subscribe("throng/emergency")

def on_message(client, userdata, msg):
    if msg.topic.startswith("throng/reports"):
        report = json.loads(msg.payload.decode())
        report_history.append(report)
        for ws in active_websockets:
            ws.send_text(json.dumps({"type": "report", "data": report}))
    elif msg.topic.startswith("throng/commands") or msg.topic == "throng/emergency":
        command = json.loads(msg.payload.decode())
        handle_command(command)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.tls_set()
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.connect(MQTT_BROKER.split(":")[0], int(MQTT_BROKER.split(":")[1]), 60)
mqtt_client.loop_start()

# Fungsi spawn agent
def spawn_agent_ssh(target, credentials):
    try:
        new_agent_id = str(uuid.uuid4())
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(target, username=credentials.get("username"), password=credentials.get("password"))
        sftp = ssh.open_sftp()
        sftp.put("agent.py", f"/tmp/agent_{new_agent_id}.py")
        ssh.exec_command(f"python3 /tmp/agent_{new_agent_id}.py &")
        sftp.close()
        ssh.close()
        cursor.execute("INSERT INTO agents (agent_id, status, last_seen, ip, host) VALUES (?, ?, ?, ?, ?)", 
                       (new_agent_id, "active", time.strftime("%Y-%m-%d %H:%M:%S"), socket.gethostbyname(target), target))
        db.commit()
        logger.info(f"Spawned agent {new_agent_id} on {target}")
        return new_agent_id
    except Exception as e:
        logger.error(f"Error spawning agent: {e}")
        return None

# Analisis ancaman
def analyze_threat(report_data):
    traffic = report_data.get("network_traffic", 0)
    suspicious = report_data.get("suspicious_activity", False)
    reasons = []
    if traffic > 1000: reasons.append("high_traffic")
    if suspicious: reasons.append("suspicious_activity")
    pattern = "_".join(sorted(reasons)) if reasons else ""
    conn = sqlite3.connect("throng.db")
    cursor = conn.cursor()
    cursor.execute("SELECT response FROM tactics WHERE pattern = ?", (pattern,))
    tactic = cursor.fetchone()
    suggestion = tactic[0] if tactic else "spawn_agent"
    conn.close()
    return {
        "threat": bool(reasons),
        "reasons": reasons,
        "suggestion": suggestion
    }

# Penanganan perintah
def handle_command(command):
    agent_id = command.get("agent_id")
    action = command.get("action")
    target = command.get("target")
    emergency = command.get("emergency", False)

    if action == "spawn" and target:
        new_agent_id = spawn_agent_ssh(target, {"username": DEFAULT_SSH_USERNAME, "password": DEFAULT_SSH_PASSWORD})
        cursor.execute("INSERT INTO actions (agent_id, action, target, status) VALUES (?, ?, ?, ?)", 
                       (agent_id, action, target, "success" if new_agent_id else "failed"))
        db.commit()
        action_history.append({"agent_id": agent_id, "action": action, "target": target, "status": "success" if new_agent_id else "failed", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
    elif action in ["scan", "block"] and target:
        cursor.execute("INSERT INTO actions (agent_id, action, target, status) VALUES (?, ?, ?, ?)", 
                       (agent_id, action, target, "pending"))
        db.commit()
        action_history.append({"agent_id": agent_id, "action": action, "target": target, "status": "pending", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        if emergency:
            mqtt_client.publish("throng/emergency", json.dumps(command))
    logger.info(f"Handled command: {action} for {agent_id} on {target}")

# Deadman Switch
last_activity = time.time()
deadman_active = False

def deadman_check():
    global deadman_active, last_activity
    while True:
        time.sleep(30)
        if not deadman_active and time.time() - last_activity > DEADMAN_TIMEOUT:
            deadman_active = True
            print("🌑 DEADMAN ACTIVE: Mengaktifkan mode darurat!")
            mqtt_client.publish("throng/broadcast", json.dumps({
                "action": "chaos_mode",
                "target": "all",
                "reason": "protector_inactive"
            }))

threading.Thread(target=deadman_check, daemon=True).start()

# Temporal Analysis
def temporal_analysis():
    conn = sqlite3.connect("throng.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT strftime('%H', timestamp) as hour, count(*) as c 
        FROM reports 
        WHERE timestamp > datetime('now', '-7 days')
        GROUP BY hour 
        ORDER BY c DESC 
        LIMIT 1
    """)
    peak = cursor.fetchone()
    if peak:
        print(f"🕰️ POLA WAKTU: Serangan puncak jam {peak[0]}:00. Siapkan 30 menit sebelum.")
    conn.close()
    threading.Timer(21600, temporal_analysis).start()

threading.Timer(60, temporal_analysis).start()

# AI Communication with Taunts
TAUNTS = [
    "Orb: Ada yang ngacau... Mau kita jebak?",
    "Orb: Traffic tinggi? Anak SMP juga bisa DDoS.",
    "Orb: Mereka kira kita lemah? Honeypot beracun siap!"
]

def ai_send(message, level="info"):
    msg = {
        "from": "Orb-Core",
        "to": "operator",
        "message": message,
        "level": level,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    mqtt_client.publish("throng/ai/chat", json.dumps(msg))
    print(f"[AI] {msg['timestamp']} - {msg['message']} (Level: {msg['level']}")

# Notifikasi WhatsApp
def send_whatsapp_notification(threat_data, config, timestamp):
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER, WHATSAPP_NUMBER]):
        logger.warning("WhatsApp config incomplete, skipping notification")
        return
    message = f"⚠️ Threat detected: IP={threat_data['ip']}, Score={threat_data.get('score', 0)}%, Action={threat_data.get('suggestion', 'none')} @ {timestamp}"
    try:
        requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            data={
                "From": TWILIO_WHATSAPP_NUMBER,
                "To": WHATSAPP_NUMBER,
                "Body": message
            }
        )
        logger.info("WhatsApp notification sent")
    except Exception as e:
        logger.error(f"WhatsApp notification failed: {e}")

# WebSocket untuk CLI
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    global last_activity
    last_activity = time.time()
    logger.info("CLI connected via WebSocket")
    print("=== Throng Hive Terminal ===")
    print("Type 'help' for commands. Use 'exit' to quit.")
    print_active_agents()

    while True:
        try:
            data = await websocket.receive_text()
            report = json.loads(data)
            agent_id = report.get("agent_id")
            report_data = report.get("data")
            cursor.execute("INSERT INTO reports (agent_id, data) VALUES (?, ?)", (agent_id, json.dumps(report_data)))
            cursor.execute("INSERT OR REPLACE INTO agents (agent_id, status, last_seen, ip) VALUES (?, ?, ?, ?)", 
                           (agent_id, "active", time.strftime("%Y-%m-%d %H:%M:%S"), report_data.get("ip", "unknown")))
            db.commit()
            report_history.append(report)
            threat = analyze_threat(report_data)
            print_report(report, threat)
            if threat["threat"]:
                ai_send(f"Threat detected from {report_data['ip']}! Action: {threat['suggestion']}", "alert")
                send_whatsapp_notification({"ip": report_data["ip"], "score": 85, "suggestion": threat["suggestion"]}, 
                                          {"twilio_account_sid": TWILIO_ACCOUNT_SID, "twilio_auth_token": TWILIO_AUTH_TOKEN, 
                                           "twilio_whatsapp_number": TWILIO_WHATSAPP_NUMBER, "whatsapp_number": WHATSAPP_NUMBER}, 
                                          time.strftime("%Y%m%d_%H%M%S"))
        except Exception as e:
            logger.error(f"WebSocket error: {e}")

# Fungsi bantu CLI
def print_active_agents():
    cursor.execute("SELECT agent_id, ip, last_seen, priority FROM agents WHERE status = 'active'")
    agents = cursor.fetchall()
    if agents:
        print("\nActive Agents:")
        for agent in agents:
            print(f"  - {agent[0]} (IP: {agent[1]}, Last Seen: {agent[2]}, Priority: {agent[3]})")
    else:
        print("  No active agents.")

def print_report(report, threat):
    agent_id = report["agent_id"]
    data = report["data"]
    msg = random.choice(TAUNTS) if threat["threat"] else "Orb: Semua aman... untuk sekarang."
    print(f"\n[Report] {agent_id} @ {data['timestamp']}: Traffic={data['network_traffic']}, IP={data['ip']}, Threat={threat['threat']} - {msg}")

def print_history():
    print("\n=== Report History ===")
    for report in report_history:
        print(f"{report['agent_id']} @ {report['data']['timestamp']}: {json.dumps(report['data'])}")
    print("\n=== Action History ===")
    for action in action_history:
        print(f"{action['agent_id']} {action['action']} {action['target']} [{action['status']}] @ {action['timestamp']}")
    conn = sqlite3.connect("throng.db")
    cursor = conn.cursor()
    cursor.execute("SELECT pattern, response, score FROM tactics")
    tactics = cursor.fetchall()
    if tactics:
        print("\n=== Learned Tactics ===")
        for tactic in tactics:
            print(f"Pattern: {tactic[0]}, Response: {tactic[1]}, Score: {tactic[2]}")
    conn.close()

def execute_command(cmd):
    parts = cmd.split()
    if not parts:
        return "Invalid command"

    action = parts[0].lower()
    if action == "help":
        return "Commands: help, spawn [target], scan [target], block [target], priority [agent_id] [level], history, exit"
    elif action == "spawn" and len(parts) > 1:
        target = parts[1]
        new_agent_id = spawn_agent_ssh(target, {"username": DEFAULT_SSH_USERNAME, "password": DEFAULT_SSH_PASSWORD})
        return f"Spawned agent {new_agent_id}" if new_agent_id else "Spawn failed"
    elif action == "scan" and len(parts) > 1:
        target = parts[1]
        mqtt_client.publish("throng/commands/global", json.dumps({"agent_id": "all", "action": "scan", "target": target}))
        return f"Scanning {target} (broadcasted to all agents)"
    elif action == "block" and len(parts) > 1:
        target = parts[1]
        mqtt_client.publish("throng/commands/global", json.dumps({"agent_id": "all", "action": "block", "target": target, "emergency": True}))
        return f"Blocking {target} (emergency action broadcasted)"
    elif action == "priority" and len(parts) > 2:
        agent_id, level = parts[1], int(parts[2])
        cursor.execute("UPDATE agents SET priority = ? WHERE agent_id = ?", (level, agent_id))
        db.commit()
        return f"Set priority {level} for {agent_id}"
    elif action == "history":
        print_history()
        return ""
    elif action == "exit":
        return "Exiting..."
    else:
        return "Unknown command or missing arguments"

# Endpoint utama untuk CLI
@app.get("/")
async def cli_interface():
    logger.info("Starting CLI interface")
    return PlainTextResponse("Run 'python -m src.server' to start Throng Hive CLI")

# Client CLI
async def run_cli():
    uri = os.getenv("WEBSOCKET_URI", "ws://localhost:8000/ws")  # Dapat dari env untuk Railway
    async with websockets.connect(uri) as websocket:
        print("=== Throng Hive Terminal ===")
        print("Type 'help' for commands. Use 'exit' to quit.")
        print_active_agents()
        while True:
            cmd = input("> ").strip()
            if cmd.lower() == "exit":
                print("Exiting...")
                break
            response = execute_command(cmd)
            if response:
                print(response)
            await websocket.send(json.dumps({"command": cmd}))

if __name__ == "__main__":
    asyncio.run(run_cli())