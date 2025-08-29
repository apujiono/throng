let token = null;

function loadData() {
    const jwtToken = document.getElementById('jwt-token').value;
    if (!jwtToken) {
        alert('Please enter a JWT Token');
        return;
    }
    token = jwtToken;
    fetchData();
}

function fetchData() {
    if (!token) return;
    fetch('https://throng-production.up.railway.app/api/data', {
        headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(response => response.json())
    .then(data => updateDashboard(data))
    .catch(error => console.error('Error fetching data:', error));
}

function updateDashboard(data) {
    // Update Activity Log
    const logList = document.getElementById('log-list');
    logList.innerHTML = '';
    data.reports.forEach(report => {
        const li = document.createElement('li');
        li.textContent = `${report.timestamp} | ${report.agent_id}: ${JSON.stringify(report.data)}`;
        logList.appendChild(li);
    });

    // Update Agents Table
    const agentsTable = document.getElementById('agents');
    agentsTable.innerHTML = '<tr><th>ID</th><th>Status</th><th>Last Seen</th><th>IP</th></tr>';
    data.agents.forEach(agent => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${agent.agent_id}</td><td>${agent.status}</td><td>${agent.last_seen}</td><td>${agent.ip}</td>`;
        agentsTable.appendChild(tr);
    });

    // Update Targets Table
    const targetsTable = document.getElementById('targets');
    targetsTable.innerHTML = '<tr><th>Target</th><th>Vulnerabilities</th><th>Status</th><th>Score</th><th>Timestamp</th></tr>';
    data.targets.forEach(target => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${target.target}</td><td>${JSON.stringify(target.vulnerability)}</td><td>${target.status}</td><td>${target.score}</td><td>${target.timestamp}</td>`;
        targetsTable.appendChild(tr);
    });

    // Update Emergency Logs
    const emergencyList = document.getElementById('emergency-list');
    emergencyList.innerHTML = '';
    data.emergency_logs.forEach(log => {
        const li = document.createElement('li');
        li.textContent = `${log.timestamp} | ${log.agent_id}: ${log.action} - ${JSON.stringify(log.details)}`;
        emergencyList.appendChild(li);
    });

    // Update Network Graph
    const network = new vis.Network(document.getElementById('network'), {
        nodes: new vis.DataSet(data.network.nodes),
        edges: new vis.DataSet(data.network.edges)
    }, {});

    // Update Threat Heatmap (Placeholder)
    const ctx = document.getElementById('heatmap').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.reports.map(r => r.agent_id),
            datasets: [{
                label: 'Network Traffic',
                data: data.reports.map(r => r.data.network_traffic || 0),
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 1
            }]
        },
        options: { scales: { y: { beginAtZero: true } } }
    });

    // Update Agent Select
    const agentSelect = document.getElementById('agent-select');
    agentSelect.innerHTML = '<option value="">Select Agent</option>';
    data.agents.forEach(agent => {
        const option = document.createElement('option');
        option.value = agent.agent_id;
        option.textContent = agent.agent_id;
        agentSelect.appendChild(option);
    });
}

function sendCommand() {
    const agentId = document.getElementById('agent-select').value;
    const action = document.getElementById('action-select').value;
    const target = document.getElementById('target-input').value;
    const emergency = document.getElementById('emergency').checked;

    if (!agentId || !action) {
        alert('Please select an agent and action');
        return;
    }

    fetch('https://throng-production.up.railway.app/command', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ agent_id: agentId, action, target, emergency })
    })
    .then(response => response.json())
    .then(data => alert(data.status))
    .catch(error => console.error('Error sending command:', error));
}

// Load data on page load if token is set
if (token) fetchData();