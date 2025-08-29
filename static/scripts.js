// scripts.js - Throng Hive Dashboard (Full Version)

let ws = null;
let token = '';

// Tampilkan notifikasi
function showNotification(message, type = 'info') {
    const notification = document.getElementById('notifications');
    const notif = document.createElement('div');
    notif.className = 'notification';
    notif.textContent = message;
    notif.style.opacity = 1;
    notif.style.transition = 'opacity 0.3s';
    
    // Warna berdasarkan tipe
    if (type === 'error') {
        notif.style.borderLeftColor = '#ff3b3b';
        notif.style.backgroundColor = '#4d2a2a';
    } else if (type === 'success') {
        notif.style.borderLeftColor = '#00ff00';
        notif.style.backgroundColor = '#2a4d2a';
    } else {
        notif.style.borderLeftColor = '#00b7eb';
    }

    notif.onclick = () => {
        notif.style.opacity = 0;
        setTimeout(() => notif.remove(), 300);
    };

    notification.appendChild(notif);

    // Hilang otomatis
    setTimeout(() => {
        if (notification.contains(notif)) {
            notif.style.opacity = 0;
            setTimeout(() => notif.remove(), 300);
        }
    }, 5000);
}

// Connect ke WebSocket
function connectWebSocket() {
    token = document.getElementById('tokenInput').value.trim();
    if (!token) {
        showNotification('Please enter a valid JWT token', 'error');
        return;
    }

    // Simpan token
    localStorage.setItem('throngToken', token);
    document.getElementById('connectionStatus').textContent = 'Connecting...';

    // Tutup koneksi lama
    if (ws) {
        ws.close();
    }

    // Buat koneksi baru
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        document.getElementById('connectionStatus').textContent = 'Connected';
        document.getElementById('connectionStatus').style.color = '#00ff00';
        showNotification('Connected to Hive WebSocket ✅');
        fetchDashboard(); // Ambil data terbaru
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            console.log('WebSocket message:', data);

            if (data.type === 'report') {
                updateReport(data.data);
            }
            if (data.type === 'update') {
                updateAgentStatus(data.data.agent_id, data.data.status);
            }
            if (data.type === 'command') {
                showNotification(`Command sent: ${data.data.action}`, 'success');
            }

            // Refresh semua data agar konsisten
            fetchDashboard();
        } catch (err) {
            console.error('Parse error:', err);
        }
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        showNotification('WebSocket error occurred', 'error');
    };

    ws.onclose = () => {
        document.getElementById('connectionStatus').textContent = 'Disconnected';
        document.getElementById('connectionStatus').style.color = '#ffeb3b';
        showNotification('Connection lost. Reconnecting...', 'error');
        // Reconnect otomatis
        setTimeout(connectWebSocket, 3000);
    };
}

// Ambil data dari /api/data
async function fetchDashboard() {
    if (!token) return;

    try {
        const res = await fetch("/api/data", {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (res.status === 401) {
            showNotification("Unauthorized: Invalid or expired token", "error");
            return;
        }

        if (!res.ok) {
            throw new Error(`Server error: ${res.status}`);
        }

        const data = await res.json();
        updateAllTables(data);
    } catch (err) {
        console.error("Fetch error:", err);
        showNotification("Failed to load data: " + err.message, "error");
    }
}

// Update semua tabel
function updateAllTables(data) {
    // Update Agents
    const agentsBody = document.querySelector("#agentsTable tbody");
    agentsBody.innerHTML = "";
    (data.agents || []).forEach(agent => {
        const row = agentsBody.insertRow();
        row.innerHTML = `
            <td>${agent.agent_id}</td>
            <td>${agent.status}</td>
            <td>${agent.last_seen}</td>
            <td>${agent.ip || '-'}</td>
            <td>${agent.host || '-'}</td>
            <td>
                <button onclick="sendCommand('${agent.agent_id}', 'scan_target', '192.168.1.1')">Scan</button>
                <button onclick="sendCommand('${agent.agent_id}', 'block_ip', '10.0.0.5')">Block IP</button>
            </td>
        `;
    });
    updateCount('agents');

    // Update Reports
    const reportsBody = document.querySelector("#reportsTable tbody");
    reportsBody.innerHTML = "";
    (data.reports || []).forEach(report => {
        const row = reportsBody.insertRow();
        const isAnomaly = report.data.is_anomaly ? '🔴 Yes' : '🟢 No';
        row.innerHTML = `
            <td>${report.agent_id}</td>
            <td>${report.timestamp}</td>
            <td>${report.data.network_traffic || 0} KB/s</td>
            <td>${isAnomaly}</td>
            <td>${report.data.ip || '-'}</td>
        `;
    });
    updateCount('reports');

    // Update Targets
    const targetsBody = document.querySelector("#targetsTable tbody");
    targetsBody.innerHTML = "";
    (data.targets || []).forEach(target => {
        const vulns = Array.isArray(target.vulnerability) ? target.vulnerability.join(', ') : '-';
        const score = target.score ? target.score.toFixed(2) : '0.00';
        const row = targetsBody.insertRow();
        row.innerHTML = `
            <td>${target.target}</td>
            <td>${vulns}</td>
            <td>${target.status}</td>
            <td>${target.timestamp}</td>
            <td>${score}</td>
        `;
    });
    updateCount('targets');

    // Update Emergency Logs
    const emergencyBody = document.querySelector("#emergencyTable tbody");
    emergencyBody.innerHTML = "";
    (data.emergency_logs || []).forEach(log => {
        const details = JSON.stringify(log.details, null, 2);
        const row = emergencyBody.insertRow();
        row.innerHTML = `
            <td>${log.agent_id}</td>
            <td>${log.action}</td>
            <td><pre>${details}</pre></td>
            <td>${log.timestamp}</td>
        `;
    });
    updateCount('emergency');
}

// Update status agent (dari WebSocket)
function updateAgentStatus(agentId, status) {
    const rows = document.querySelectorAll("#agentsTable tbody tr");
    for (let row of rows) {
        if (row.cells[0].textContent === agentId) {
            row.cells[1].textContent = status;
            row.cells[1].style.color = status === 'active' ? '#00ff00' : '#ff3b3b';
            break;
        }
    }
    updateCount('agents');
}

// Update report (dari WebSocket)
function updateReport(report) {
    const table = document.querySelector("#reportsTable tbody");
    const row = table.insertRow(0); // Tambah di atas
    const isAnomaly = report.data.is_anomaly ? '🔴 Yes' : '🟢 No';
    row.innerHTML = `
        <td>${report.agent_id}</td>
        <td>${report.timestamp || new Date().toISOString()}</td>
        <td>${report.data.network_traffic || 0} KB/s</td>
        <td>${isAnomaly}</td>
        <td>${report.data.ip || '-'}</td>
    `;
    updateCount('reports');
}

// Update jumlah data di header
function updateCount(tabName) {
    const table = document.getElementById(`${tabName}Table`);
    const count = table?.getElementsByTagName('tbody')[0]?.rows.length || 0;
    const countSpan = document.getElementById(`${tabName}Count`);
    if (countSpan) {
        countSpan.textContent = `(${count})`;
    }
}

// Filter tabel
function filterTable(tableId) {
    const input = document.getElementById(`${tableId.replace('Table', 'Filter')}`).value.toLowerCase();
    const tbody = document.querySelector(`#${tableId} tbody`);
    const rows = tbody.getElementsByTagName('tr');

    for (let i = 0; i < rows.length; i++) {
        const cells = rows[i].getElementsByTagName('td');
        let found = false;
        for (let cell of cells) {
            if (cell.textContent.toLowerCase().includes(input)) {
                found = true;
                break;
            }
        }
        rows[i].style.display = found ? '' : 'none';
    }
}

// Sort tabel
function sortTable(tableId, n) {
    const table = document.getElementById(tableId);
    let switching = true, switchCount = 0;
    let direction = 'asc';

    while (switching) {
        switching = false;
        const rows = table.rows;
        for (let i = 1; i < (rows.length - 1); i++) {
            const x = rows[i].getElementsByTagName('td')[n];
            const y = rows[i + 1].getElementsByTagName('td')[n];
            const shouldSwitch = direction === 'asc' 
                ? x.textContent.toLowerCase() > y.textContent.toLowerCase()
                : x.textContent.toLowerCase() < y.textContent.toLowerCase();

            if (shouldSwitch) {
                rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                switching = true;
                switchCount++;
                break;
            }
        }
        if (!switching && switchCount === 0 && direction === 'asc') {
            direction = 'desc';
            switching = true;
        }
    }
}

// Kirim perintah ke agent
async function sendCommand(agentId, action, target = null) {
    if (!token) {
        showNotification('Please connect with a valid JWT token first', 'error');
        return;
    }

    const payload = { agent_id: agentId, action, target, emergency: action === 'spawn_agent' };

    try {
        const res = await fetch("/command", {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const result = await res.json();
        showNotification(result.status || `Command ${action} sent`, 'success');
    } catch (err) {
        showNotification(`Network error: ${err.message}`, 'error');
    }
}

// Tab system
function openTab(tabName) {
    const tabs = document.getElementsByClassName('tab');
    const tabContents = document.getElementsByClassName('tab-content');
    
    for (let i = 0; i < tabs.length; i++) {
        tabs[i].className = tabs[i].className.replace(' active', '');
        tabContents[i].className = tabContents[i].className.replace(' active', '');
    }
    
    document.getElementById(tabName).className += ' active';
    document.querySelector(`[onclick="openTab('${tabName}')"]`).className += ' active';
}

// Auto-load saat halaman siap
document.addEventListener('DOMContentLoaded', () => {
    const savedToken = localStorage.getItem('throngToken');
    if (savedToken) {
        document.getElementById('tokenInput').value = savedToken;
        token = savedToken;
    }

    // Opsi: auto-connect saat buka halaman
    // connectWebSocket();

    // Inisialisasi jumlah
    ['agents', 'reports', 'targets', 'emergency'].forEach(updateCount);
});

// Auto-reconnect saat token ada
document.getElementById('tokenInput').addEventListener('change', (e) => {
    localStorage.setItem('throngToken', e.target.value);
});