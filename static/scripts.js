let ws = null;
let token = '';

function showNotification(message, type = 'info') {
    const notification = document.getElementById('notifications');
    notification.style.display = 'block';
    notification.textContent = message;
    notification.style.backgroundColor = type === 'error' ? '#dc3545' : '#28a745';
    setTimeout(() => {
        notification.style.display = 'none';
    }, 5000);
}

function connectWebSocket() {
    token = document.getElementById('tokenInput').value;
    if (!token) {
        showNotification('Please enter a valid JWT token', 'error');
        return;
    }
    localStorage.setItem('throngToken', token);

    if (ws) ws.close();
    ws = new WebSocket(`wss://${window.location.host}/ws`);
    ws.onopen = () => {
        ws.send(JSON.stringify({ token }));
        showNotification('Connected to Hive WebSocket');
    };
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'report') updateReport(data.data);
        if (data.type === 'command') showNotification(`Command sent: ${data.data.action}`);
        if (data.type === 'update') updateAgentStatus(data.data.agent_id, data.data.status);
    };
    ws.onerror = (error) => showNotification(`WebSocket error: ${error}`, 'error');
    ws.onclose = () => showNotification('WebSocket disconnected', 'error');
}

function updateAgentStatus(agentId, status) {
    const table = document.getElementById('agentsTable');
    const rows = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');
    for (let row of rows) {
        if (row.cells[0].textContent === agentId) {
            row.cells[1].textContent = status;
            row.cells[1].style.color = status === 'active' ? '#00ff00' : '#ff0000';
            break;
        }
    }
}

function updateReport(report) {
    updateTable('reportsTable', [report], ['agent_id', 'data.timestamp', 'data.network_traffic', 'data.is_anomaly', 'data.ip'], (row, report) => {
        row.cells[3].textContent = report.data.is_anomaly ? 'Yes' : 'No';
        row.cells[3].style.color = report.data.is_anomaly ? '#ff0000' : '#00ff00';
    });
}

function updateTable(tableId, data, columns, customRender = null) {
    const table = document.getElementById(tableId);
    const tbody = table.getElementsByTagName('tbody')[0];
    let updated = false;

    data.forEach(item => {
        let row = Array.from(tbody.getElementsByTagName('tr')).find(r => r.cells[0].textContent === item.agent_id || r.cells[0].textContent === item.target);
        if (!row) {
            row = tbody.insertRow();
            updated = true;
        }
        while (row.cells.length > columns.length + (tableId === 'agentsTable' ? 1 : 0)) row.deleteCell(-1);
        columns.forEach((col, index) => {
            const cell = row.cells[index] || row.insertCell(index);
            const value = col.split('.').reduce((obj, key) => obj ? obj[key] : '', item) || 'N/A';
            cell.textContent = value;
        });
        if (customRender) customRender(row, item);
        if (tableId === 'agentsTable' && !row.cells[5]) {
            const actionsCell = row.insertCell(5);
            const spawnButton = document.createElement('button');
            spawnButton.textContent = 'Spawn';
            spawnButton.onclick = () => sendCommand(item.agent_id, 'spawn_agent', '192.168.1.10');
            actionsCell.appendChild(spawnButton);
        }
    });

    if (updated) filterTable(tableId);
}

function filterTable(tableId) {
    const input = document.getElementById(`${tableId.replace('Table', 'Filter')}`).value.toLowerCase();
    const table = document.getElementById(tableId);
    const tr = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');

    for (let i = 0; i < tr.length; i++) {
        let found = false;
        const td = tr[i].getElementsByTagName('td');
        for (let j = 0; j < td.length - (tableId === 'agentsTable' ? 1 : 0); j++) {
            if (td[j].textContent.toLowerCase().indexOf(input) > -1) {
                found = true;
                break;
            }
        }
        tr[i].style.display = found ? '' : 'none';
    }
}

function sortTable(tableId, n) {
    const table = document.getElementById(tableId);
    let rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
    switching = true;
    dir = 'asc';

    while (switching) {
        switching = false;
        rows = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');

        for (i = 0; i < (rows.length - 1); i++) {
            shouldSwitch = false;
            x = rows[i].getElementsByTagName('td')[n];
            y = rows[i + 1].getElementsByTagName('td')[n];

            if (dir === 'asc') {
                if (x.textContent.toLowerCase() > y.textContent.toLowerCase()) {
                    shouldSwitch = true;
                    break;
                }
            } else if (dir === 'desc') {
                if (x.textContent.toLowerCase() < y.textContent.toLowerCase()) {
                    shouldSwitch = true;
                    break;
                }
            }
        }

        if (shouldSwitch) {
            rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
            switching = true;
            switchcount++;
        } else if (switchcount === 0 && dir === 'asc') {
            dir = 'desc';
            switching = true;
        }
    }
}

function sendCommand(agentId, action, target) {
    if (!token) {
        showNotification('Please connect with a valid JWT token first', 'error');
        return;
    }

    fetch('/command', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ agent_id: agentId, action: action, target: target })
    })
    .then(response => response.json())
    .then(data => showNotification(data.status))
    .catch(error => showNotification(`Error sending command: ${error.message}`, 'error'));
}

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

// Initial load
document.addEventListener('DOMContentLoaded', () => {
    const savedToken = localStorage.getItem('throngToken');
    if (savedToken) {
        document.getElementById('tokenInput').value = savedToken;
    }
});

document.getElementById('tokenInput').addEventListener('change', (e) => {
    localStorage.setItem('throngToken', e.target.value);
});