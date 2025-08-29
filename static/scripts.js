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

function fetchData() {
    token = document.getElementById('tokenInput').value;
    if (!token) {
        showNotification('Please enter a valid JWT token', 'error');
        return;
    }
    updateData();
}

function updateData() {
    if (!token) return;

    fetch('/api/data', {
        headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(response => {
        if (!response.ok) throw new Error('Unauthorized');
        return response.json();
    })
    .then(data => {
        updateTable('agentsTable', data.agents, ['agent_id', 'status', 'last_seen', 'ip', 'host'], (row, agent) => {
            const actionsCell = row.insertCell(5);
            const spawnButton = document.createElement('button');
            spawnButton.textContent = 'Spawn';
            spawnButton.onclick = () => sendCommand(agent.agent_id, 'spawn_agent', '192.168.1.10');
            actionsCell.appendChild(spawnButton);
        });
        updateTable('reportsTable', data.reports, ['agent_id', 'timestamp', 'data.network_traffic', 'data.is_anomaly', 'data.ip'], (row, report) => {
            row.cells[3].textContent = report.data.is_anomaly ? 'Yes' : 'No';
        });
        updateTable('targetsTable', data.targets, ['target', 'vulnerability', 'status', 'timestamp', 'score']);
        updateTable('emergencyTable', data.emergency_logs, ['agent_id', 'action', 'details', 'timestamp'], (row, log) => {
            row.cells[2].textContent = JSON.stringify(log.details);
        });
        showNotification('Data updated successfully');
    })
    .catch(error => {
        showNotification(`Error fetching data: ${error.message}`, 'error');
        console.error('Error:', error);
    });
}

function updateTable(tableId, data, columns, customRender = null) {
    const table = document.getElementById(tableId);
    const tbody = table.getElementsByTagName('tbody')[0];
    tbody.innerHTML = '';

    data.forEach(item => {
        const row = tbody.insertRow();
        columns.forEach((col, index) => {
            const cell = row.insertCell(index);
            const value = col.split('.').reduce((obj, key) => obj ? obj[key] : '', item) || 'N/A';
            cell.textContent = value;
        });
        if (customRender) customRender(row, item);
    });
}

function filterTable(tableId) {
    const input = document.getElementById(`${tableId.replace('Table', 'Filter')}`).value.toLowerCase();
    const table = document.getElementById(tableId);
    const tr = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');

    for (let i = 0; i < tr.length; i++) {
        let found = false;
        const td = tr[i].getElementsByTagName('td');
        for (let j = 0; j < td.length; j++) {
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
        showNotification('Please enter a valid JWT token first', 'error');
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

// Auto-refresh every 30 seconds
setInterval(updateData, 30000);

// Initial load
document.addEventListener('DOMContentLoaded', () => {
    const savedToken = localStorage.getItem('throngToken');
    if (savedToken) {
        document.getElementById('tokenInput').value = savedToken;
        fetchData();
    }
});

document.getElementById('tokenInput').addEventListener('change', (e) => {
    localStorage.setItem('throngToken', e.target.value);
});