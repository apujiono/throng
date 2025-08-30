const ws = new WebSocket(`wss://${window.location.host}/ws`);
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "report") {
        document.getElementById("reports").innerHTML += `<p>${data.data.agent_id}: ${JSON.stringify(data.data.data)}</p>`;
    } else if (data.type === "update") {
        document.getElementById("agents").innerHTML += `<p>${data.data.agent_id} - ${data.data.status}</p>`;
    }
};