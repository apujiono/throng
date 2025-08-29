// scripts.js - No JWT Version

let ws = null;

function showNotification(message, type = 'info') {
    const notification = document.getElementById('notifications');
    const notif = document.createElement('div');
    notif.className = 'notification';
    notif.textContent = message;
    notif.style.opacity = 1;

    if (type === 'error') notif.style.borderLeftColor = '#ff3b3b';
    else if (type === 'success') notif.style.borderLeftColor = '#00ff00';
    else notif.style.borderLeftColor = '#00b7eb';

    notif.onclick = () => {
        notif.style.opacity = 0;
        setTimeout(() => notif.remove(), 300);
    };

    notification.appendChild(notif);

    setTimeout(() => {
        if (notification.contains(notif)) {
            notif.style.opacity = 0;
            setTimeout(() => notif.remove(), 300);
        }
    }, 5000);
}

function connectWebSocket() {
    document.getElementById('connectionStatus').textContent = 'Connecting...';

    if (ws) ws.close();

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        document.getElementById('connectionStatus').textContent = 'Connected';
        document.getElementById('connectionStatus').style.color = '#00ff00';
        showNotification('Connected to Hive ✅');
        fetchDashboard();
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('WS:', data);
        if (data.type === 'report') updateReport(data.data);
        if (data.type === 'command') showNotification(`Command: ${data.data.action}`);
        fetchDashboard(); // Refresh data
    };

    ws.onerror = (err) => {
        console.error('WS error:', err);
        showNotification('WebSocket error', 'error');
    };

    ws.onclose = () => {
        document.getElementById('connectionStatus').textContent = 'Disconnected';
        document.getElementById('connectionStatus').style.color = '#ffeb3b';
        showNotification('Disconnected. Reconnecting...', 'error');
        setTimeout(connectWebSocket, 3000);
    };
}

async function fetchDashboard() {
    try {
        const res = await fetch("/api/data");
        if (!res.ok) throw new Error("Failed to load data");
        const data = await res.json();
        updateAllTables(data);
    } catch (err) {
        showNotification("Load failed: " + err.message, "error");
    }
}

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
            <td><button onclick="sendCommand('${agent.agent_id}', 'scan_target')">Scan</button></td>
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
            <td>${report.data.network_traffic || 0}</td>
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

function updateCount(tabName) {
    const table = document.getElementById(`${tabName}Table`);
    const count = table?.getElementsByTagName('tbody')[0]?.rows.length || 0;
    const span = document.getElementById(`${tabName}Count`);
    if (span) span.textContent = `(${count})`;
}

function updateReport(report) {
    const tbody = document.querySelector("#reportsTable tbody");
    const row = tbody.insertRow(0);
    row.innerHTML = `
        <td>${report.agent_id}</td>
        <td>${report.timestamp}</td>
        <td>${report.data.network_traffic || 0}</td>
        <td>${report.data.is_anomaly ? '🔴 Yes' : '🟢 No'}</td>
        <td>${report.data.ip || '-'}</td>
    `;
    updateCount('reports');
}

async function sendCommand(agentId, action, target = null) {
    try {
        const res = await fetch("/command", {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent_id: agentId, action, target })
        });
        const result = await res.json();
        showNotification(result.status || action, 'success');
    } catch (err) {
        showNotification('Network error', 'error');
    }
}

function openTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');
    document.querySelector(`[onclick="openTab('${tabName}')"]`).classList.add('active');
}

function filterTable(tableId) {
    const input = document.getElementById(`${tableId.replace('Table', 'Filter')}`).value.toLowerCase();
    const rows = document.querySelector(`#${tableId} tbody`).rows;
    for (let row of rows) {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(input) ? '' : 'none';
    }
}

function sortTable(tableId, n) {
    const table = document.getElementById(tableId);
    let switching = true, direction = 'asc';
    while (switching) {
        switching = false;
        const rows = table.rows;
        for (let i = 1; i < rows.length - 1; i++) {
            const x = rows[i].cells[n], y = rows[i + 1].cells[n];
            const shouldSwitch = direction === 'asc' ? x.textContent > y.textContent : x.textContent < y.textContent;
            if (shouldSwitch) {
                rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                switching = true;
                break;
            }
        }
        if (!switching && direction === 'asc') direction = 'desc';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket(); // Auto-connect
    updateCount('agents');
    updateCount('reports');
    updateCount('targets');
    updateCount('emergency');
});