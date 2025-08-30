"""
🌑 THE ORB v7.0 — Sistem Manajemen Keamanan Jaringan
Sistem untuk memantau dan melindungi jaringan dengan prinsip keamanan bertanggung jawab
"""

import asyncio
import json
import time
import os
import sqlite3
import random
import threading
from datetime import datetime
from fastapi import FastAPI, WebSocket, Request, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
from passlib.context import CryptContext
import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel

# ============ KONFIGURASI KEAMANAN ============
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# ============ SETUP ============
app = FastAPI(title="THE ORB v7.0 - Network Security Management")

# ============ KEAMANAN ============
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None

class User(BaseModel):
    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None

class UserInDB(User):
    hashed_password: str

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# ============ DATABASE PENGGUNA ============
def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)

def fake_hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# ============ SETUP ============
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://throng-production.up.railway.app"],
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
agents = []  # Pastikan ini list
last_activity = time.time()
omega_log = open("omega.log", "a", buffering=1)

# ============ DNA DIGITAL ============
DNA = {
    "identity": "THE ORB — Cyber Sentinel",
    "mission": {
        "primary": "Protect the network",
        "secondary": "Preserve agent integrity",
        "tertiary": "Operate within ethical boundaries"
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
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            full_name TEXT,
            hashed_password TEXT NOT NULL,
            disabled BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY,
            agent_id TEXT UNIQUE,
            status TEXT,
            last_seen TEXT,
            ip TEXT,
            parent_id TEXT,
            generation INTEGER DEFAULT 1,
            location TEXT,
            os_info TEXT
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
            timestamp TEXT,
            executed_by TEXT
        );
        
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY,
            event_type TEXT,
            description TEXT,
            severity TEXT,
            timestamp TEXT,
            resolved BOOLEAN DEFAULT 0,
            resolution_notes TEXT
        );
        
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY,
            user TEXT,
            action TEXT,
            target TEXT,
            timestamp TEXT,
            ip_address TEXT
        );
    ''')
    
    # Tambahkan pengguna admin jika belum ada
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        hashed_password = fake_hash_password("admin_password")
        cursor.execute(
            "INSERT INTO users (username, email, full_name, hashed_password, disabled) VALUES (?, ?, ?, ?, ?)",
            ("admin", "admin@example.com", "Administrator", hashed_password, 0)
        )
    conn.commit()
    conn.close()

init_db()

# ============ SISTEM KEAMANAN ============
def log_audit(user, action, target, request: Request):
    """Catat aktivitas ke audit log"""
    conn = get_db()
    conn.execute(
        "INSERT INTO audit_log (user, action, target, timestamp, ip_address) VALUES (?, ?, ?, ?, ?)",
        (user, action, target, datetime.now().isoformat(), request.client.host)
    )
    conn.commit()
    conn.close()

def create_security_event(event_type, description, severity):
    """Buat event keamanan baru"""
    conn = get_db()
    conn.execute(
        "INSERT INTO security_events (event_type, description, severity, timestamp) VALUES (?, ?, ?, ?)",
        (event_type, description, severity, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    
    # Broadcast ke WebSocket
    for ws in active_websockets:
        asyncio.run_coroutine_threadsafe(
            ws.send_text(json.dumps({
                "type": "security_event", 
                "data": {
                    "type": event_type,
                    "description": description,
                    "severity": severity,
                    "timestamp": datetime.now().isoformat()
                }
            })),
            asyncio.get_event_loop()
        )

# ============ AI SENTINEL (BERTANGGUNG JAWAB) ============
def analyze_threat(report_data):
    ip = report_data.get("ip", "unknown")
    traffic = report_data.get("network_traffic", 0)
    reasons = []
    
    # Hanya berikan peringatan jika benar-benar berisiko
    if traffic > 1000: 
        reasons.append("high_traffic")
        create_security_event(
            "HIGH_TRAFFIC", 
            f"Traffic tinggi terdeteksi dari {ip}", 
            "medium"
        )
    
    if "honeypot_alert" in str(report_data): 
        reasons.append("intruder_detected")
        create_security_event(
            "INTRUSION_ATTEMPT", 
            f"Upaya intrusi terdeteksi dari {ip}", 
            "high"
        )

    # Pesan yang profesional dan tidak provokatif
    taunts = [
        f"Peringatan: Aktivitas mencurigakan terdeteksi di {ip}. Silakan selidiki.",
        f"Perhatian: Ada aktivitas jaringan yang tidak biasa dari {ip}. Perlu investigasi."
    ]
    
    return {
        "threat": bool(reasons),
        "message": random.choice(taunts) if reasons else "Semua sistem berjalan normal.",
        "severity": "high" if "intruder_detected" in reasons else "medium" if reasons else "low"
    }

# ============ SISTEM PELAPORAN ============
def generate_security_report():
    """Hasilkan laporan keamanan harian"""
    conn = get_db()
    
    # Hitung event keamanan
    high_severity = conn.execute(
        "SELECT COUNT(*) FROM security_events WHERE severity = 'high' AND timestamp > datetime('now', '-1 day')"
    ).fetchone()[0]
    
    medium_severity = conn.execute(
        "SELECT COUNT(*) FROM security_events WHERE severity = 'medium' AND timestamp > datetime('now', '-1 day')"
    ).fetchone()[0]
    
    low_severity = conn.execute(
        "SELECT COUNT(*) FROM security_events WHERE severity = 'low' AND timestamp > datetime('now', '-1 day')"
    ).fetchone()[0]
    
    # Hitung agent aktif
    active_agents = conn.execute(
        "SELECT COUNT(*) FROM agents WHERE last_seen > datetime('now', '-15 minutes')"
    ).fetchone()[0]
    
    # Hitung event yang belum terselesaikan
    unresolved = conn.execute(
        "SELECT COUNT(*) FROM security_events WHERE resolved = 0"
    ).fetchone()[0]
    
    conn.close()
    
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": {
            "high_severity_events": high_severity,
            "medium_severity_events": medium_severity,
            "low_severity_events": low_severity,
            "active_agents": active_agents,
            "unresolved_issues": unresolved
        },
        "recommendations": []
    }

# ============ LOGIN DAN KEAMANAN ============
fake_users_db = {
    "admin": {
        "username": "admin",
        "email": "admin@example.com",
        "full_name": "Administrator",
        "hashed_password": fake_hash_password("admin_password"),
        "disabled": False,
    }
}

@app.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username}
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me/", response_model=User)
async def read_users_me(
    current_user: User = Depends(get_current_active_user)
):
    return current_user

# ============ MQTT ============
mqtt_client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        client.subscribe("throng/reports")
        client.subscribe("throng/security_events")
        print("✅ MQTT: Terhubung ke HiveMQ")
    else:
        print(f"❌ MQTT: Gagal, kode {rc}")

def on_message(client, userdata, msg):
    try:
        if msg.topic == "throng/reports":
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
                "generation": data.get("generation", 1),
                "location": data.get("location", "unknown"),
                "os_info": data.get("os_info", "unknown")
            }
            existing = next((a for a in agents if a["agent_id"] == agent_id), None)
            if existing:
                existing.update(agent_info)
            else:
                agents.append(agent_info)

            # Analisis ancaman
            analysis = analyze_threat(data)
            if analysis["threat"]:
                # Broadcast ke WebSocket
                for ws in active_websockets:
                    asyncio.run_coroutine_threadsafe(
                        ws.send_text(json.dumps({"type": "ai_alert", "data": analysis})),
                        asyncio.get_event_loop()
                    )
        
        elif msg.topic == "throng/security_events":
            security_event = json.loads(msg.payload.decode())
            # Broadcast ke WebSocket
            for ws in active_websockets:
                asyncio.run_coroutine_threadsafe(
                    ws.send_text(json.dumps({"type": "security_event", "data": security_event})),
                    asyncio.get_event_loop()
                )
                
    except Exception as e:
        print(f"❌ Error: {e}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.tls_set()
mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
mqtt_client.loop_start()

# ============ ROUTES ============

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, current_user: User = Depends(get_current_active_user)):
    return templates.TemplateResponse("terminal.html", {"request": request, "user": current_user})

@app.get("/api/agents")
async def get_agents(current_user: User = Depends(get_current_active_user)):
    log_audit(current_user.username, "view", "agents", Request)
    return {"agents": agents}

@app.get("/api/security/events")
async def get_security_events(
    current_user: User = Depends(get_current_active_user),
    resolved: bool = None
):
    log_audit(current_user.username, "view", "security_events", Request)
    
    conn = get_db()
    query = "SELECT * FROM security_events"
    params = []
    
    if resolved is not None:
        query += " WHERE resolved = ?"
        params.append(1 if resolved else 0)
        
    query += " ORDER BY timestamp DESC LIMIT 50"
    
    events = conn.execute(query, params).fetchall()
    conn.close()
    
    return {"events": [dict(e) for e in events]}

@app.post("/api/security/events/{event_id}/resolve")
async def resolve_security_event(
    event_id: int,
    resolution_notes: str,
    current_user: User = Depends(get_current_active_user)
):
    log_audit(current_user.username, "resolve", f"security_event:{event_id}", Request)
    
    conn = get_db()
    conn.execute(
        "UPDATE security_events SET resolved = 1, resolution_notes = ? WHERE id = ?",
        (resolution_notes, event_id)
    )
    conn.commit()
    conn.close()
    
    return {"status": "resolved"}

@app.get("/api/daily-report")
async def get_daily_report(current_user: User = Depends(get_current_active_user)):
    log_audit(current_user.username, "view", "daily_report", Request)
    return generate_security_report()

@app.post("/api/command")
async def send_command(
    request: Request,
    current_user: User = Depends(get_current_active_user)
):
    data = await request.json()
    agent_id = data.get("agent_id")
    command = data.get("command")
    target = data.get("target", "")
    
    log_audit(current_user.username, "command", f"{command}:{agent_id}", request)
    
    # Validasi perintah yang diizinkan
    allowed_commands = ["ping", "scan", "block_ip", "unblock_ip"]
    if command not in allowed_commands:
        return {"status": "error", "message": "Command not allowed"}
    
    conn = get_db()
    conn.execute("INSERT INTO commands VALUES (NULL, ?, ?, 'pending', ?, ?)",
                (agent_id, command, datetime.now().isoformat(), current_user.username))
    conn.commit()
    conn.close()
    
    payload = {"action": command}
    if target: payload["target"] = target
    
    mqtt_client.publish(f"throng/commands/{agent_id}", json.dumps(payload))
    
    # Broadcast ke WebSocket
    for ws in active_websockets:
        asyncio.run_coroutine_threadsafe(
            ws.send_text(json.dumps({
                "type": "command", 
                "data": {
                    "agent_id": agent_id, 
                    "command": command, 
                    "target": target,
                    "executed_by": current_user.username
                }
            })),
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

# ============ SISTEM PELAPORAN OTOMATIS ============
def generate_daily_report():
    """Hasilkan dan kirim laporan keamanan harian"""
    report = generate_security_report()
    
    # Di dunia nyata, ini akan mengirim email atau notifikasi
    print(f"📊 Laporan Keamanan Harian ({report['date']}):")
    print(f"  - Event Tinggi: {report['summary']['high_severity_events']}")
    print(f"  - Event Sedang: {report['summary']['medium_severity_events']}")
    print(f"  - Event Rendah: {report['summary']['low_severity_events']}")
    print(f"  - Agent Aktif: {report['summary']['active_agents']}")
    print(f"  - Masalah Belum Selesai: {report['summary']['unresolved_issues']}")

def daily_report_loop():
    """Loop untuk menghasilkan laporan harian"""
    while True:
        # Tunggu sampai jam 8 pagi
        now = datetime.now()
        next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        
        time_to_wait = (next_run - now).total_seconds()
        time.sleep(time_to_wait)
        
        # Hasilkan laporan
        generate_daily_report()

threading.Thread(target=daily_report_loop, daemon=True).start()

# ============ INISIALISASI ============
print("🌌 THE ORB v7.0 — Sistem Manajemen Keamanan Jaringan")
print("   Menggunakan prinsip keamanan bertanggung jawab dan transparan")
print("   Semua aktivitas dicatat dalam audit log untuk akuntabilitas")
print("   Sistem siap melindungi jaringan Anda dengan etika dan profesionalisme")