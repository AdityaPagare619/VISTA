/**
 * VISTA Enterprise Dashboard v4.0
 * ================================
 * Real-time telemetry, animated architecture flow,
 * sensor health rings, NVH analytics, and demo scenarios.
 */

const socket = io({ transports: ["websocket", "polling"] });

// ── Clock ─────────────────────────────────────────────────────────
function updateClock() {
    const now = new Date();
    const t = now.toLocaleTimeString([], { hour12: false });
    const ms = now.getMilliseconds().toString().padStart(3, "0");
    document.getElementById("clock").textContent = `${t}.${ms}`;
}
setInterval(updateClock, 100);
updateClock();

// ── Chart.js ──────────────────────────────────────────────────────
const MAX_PTS = 120;
const ekfData = Array(MAX_PTS).fill(null);
const obdData = Array(MAX_PTS).fill(null);
const labels = Array(MAX_PTS).fill("");

const ctx = document.getElementById("velocityChart").getContext("2d");

// Gradient fill for EKF line
const ekfGrad = ctx.createLinearGradient(0, 0, 0, 280);
ekfGrad.addColorStop(0, "rgba(0, 230, 118, 0.15)");
ekfGrad.addColorStop(1, "rgba(0, 230, 118, 0)");

const velocityChart = new Chart(ctx, {
    type: "line",
    data: {
        labels,
        datasets: [
            {
                label: "EKF Velocity",
                data: ekfData,
                borderColor: "#00e676",
                backgroundColor: ekfGrad,
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.3,
                fill: true,
            },
            {
                label: "Raw OBD",
                data: obdData,
                borderColor: "rgba(255,255,255,0.15)",
                borderDash: [4, 4],
                borderWidth: 1.5,
                pointRadius: 0,
                tension: 0.3,
                fill: false,
            },
        ],
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 0 },
        interaction: { intersect: false, mode: "index" },
        scales: {
            x: { display: false },
            y: {
                display: true, min: 0, max: 100,
                grid: { color: "rgba(255,255,255,0.03)", drawBorder: false },
                ticks: { color: "#6b7280", font: { family: "JetBrains Mono", size: 10 } },
                border: { display: false },
            },
        },
        plugins: { legend: { display: false } },
    },
});

// ── Telemetry Stream ──────────────────────────────────────────────
let lastTelemetryTime = Date.now();

socket.on("telemetry", (d) => {
    lastTelemetryTime = Date.now();

    // Metric cards
    const ekfEl = document.getElementById("val-ekf");
    ekfEl.innerHTML = `${d.ekf_speed.toFixed(1)}<span class="metric-unit">km/h</span>`;

    const imuEl = document.getElementById("val-imu");
    imuEl.innerHTML = `${d.imu_g.toFixed(2)}<span class="metric-unit">G</span>`;

    const audioEl = document.getElementById("val-audio");
    audioEl.textContent = d.audio_label.toUpperCase();
    const audioCard = document.getElementById("card-audio");
    if (d.audio_label === "crash") {
        audioEl.className = "metric-value mono m-red";
        audioCard.className = "glass metric-card red";
    } else if (d.audio_label === "horn" || d.audio_label === "siren") {
        audioEl.className = "metric-value mono m-yellow";
        audioCard.className = "glass metric-card yellow";
    } else {
        audioEl.className = "metric-value mono m-yellow";
        audioCard.className = "glass metric-card yellow";
    }

    const healthEl = document.getElementById("val-health");
    const cap = (d.capacity * 100).toFixed(0);
    healthEl.innerHTML = `${cap}<span class="metric-unit">%</span>`;
    const healthCard = document.getElementById("card-health");
    if (cap >= 80) {
        healthEl.className = "metric-value mono m-green";
        healthCard.className = "glass metric-card green";
    } else if (cap >= 50) {
        healthEl.className = "metric-value mono m-yellow";
        healthCard.className = "glass metric-card yellow";
    } else {
        healthEl.className = "metric-value mono m-red";
        healthCard.className = "glass metric-card red";
    }

    // Chart
    ekfData.push(d.ekf_speed);
    ekfData.shift();
    obdData.push(d.raw_speed);
    obdData.shift();
    velocityChart.update();

    // Architecture flow: pulse intel node
    pulseNode("node-intel");
});

// ── Alert Stream ──────────────────────────────────────────────────
socket.on("alert", (ev) => {
    const feed = document.getElementById("alertFeed");
    const item = document.createElement("div");
    const d = new Date(ev.timestamp);
    const ts = d.toLocaleTimeString([], { hour12: false }) + "." + d.getMilliseconds().toString().padStart(3, "0");

    if (ev.type === "crash") {
        item.className = "alert-item critical";
        item.innerHTML = `
            <div class="alert-head">
                <span style="color:var(--accent-red)">💥 COLLISION DETECTED</span>
                <span class="alert-time">${ts}</span>
            </div>
            <div>Confidence: ${(ev.confidence * 100).toFixed(1)}% · Impact: ${ev.details.impact_g.toFixed(1)}G</div>
        `;
        triggerCrashFlash();
        pulseNode("node-comms");
    } else if (ev.type.startsWith("rejected")) {
        const reason = ev.type.replace("rejected_", "").toUpperCase();
        item.className = "alert-item warning";
        item.innerHTML = `
            <div class="alert-head">
                <span style="color:var(--accent-yellow)">🛡️ FILTERED: ${reason}</span>
                <span class="alert-time">${ts}</span>
            </div>
            <div>Peak: ${ev.details.impact_g.toFixed(1)}G · Rejected by signature analysis</div>
        `;
    } else if (ev.type === "theft_attempt") {
        item.className = "alert-item security";
        item.innerHTML = `
            <div class="alert-head">
                <span style="color:var(--accent-purple)">🔓 CAN-BUS INJECTION</span>
                <span class="alert-time">${ts}</span>
            </div>
            <div>${ev.details.action}</div>
        `;
        updateSecurity("THREAT", true);
    } else if (ev.type === "theft_prevented") {
        item.className = "alert-item info";
        item.innerHTML = `
            <div class="alert-head">
                <span style="color:var(--accent-blue)">🛡️ GHOST KEY TSA</span>
                <span class="alert-time">${ts}</span>
            </div>
            <div>${ev.details.action}</div>
        `;
        updateSecurity("DEFENDED", false);
        pulseNode("node-comms");
    }

    feed.prepend(item);
    while (feed.children.length > 50) feed.removeChild(feed.lastChild);
});

// ── Crash Flash ───────────────────────────────────────────────────
function triggerCrashFlash() {
    const el = document.getElementById("flashOverlay");
    el.classList.add("active");
    setTimeout(() => el.classList.remove("active"), 200);
    // Double flash
    setTimeout(() => {
        el.classList.add("active");
        setTimeout(() => el.classList.remove("active"), 150);
    }, 300);
}

// ── Security Status ───────────────────────────────────────────────
function updateSecurity(text, isThreat) {
    const el = document.getElementById("val-security");
    const card = document.getElementById("card-security");
    el.textContent = text;
    if (isThreat) {
        el.className = "metric-value mono m-red";
        card.className = "glass metric-card red";
        card.style.animation = "none";
        card.offsetHeight; // reflow
        card.style.animation = "threatPulse 0.5s ease 3";
    } else {
        el.className = "metric-value mono m-green";
        card.className = "glass metric-card green";
    }
    // Reset after 5s
    setTimeout(() => {
        el.textContent = "ARMED";
        el.className = "metric-value mono m-green";
        card.className = "glass metric-card purple";
    }, 5000);
}

// ── Architecture Node Pulse ───────────────────────────────────────
function pulseNode(nodeId) {
    const node = document.getElementById(nodeId);
    if (!node) return;
    node.style.borderColor = "var(--accent-green)";
    node.style.boxShadow = "0 0 12px rgba(0,230,118,0.2)";
    setTimeout(() => {
        node.style.borderColor = "";
        node.style.boxShadow = "";
    }, 300);
}

// ── Sensor Health Ring Updates ─────────────────────────────────────
function updateSensorRing(ringId, isAlive) {
    const ring = document.getElementById(ringId);
    if (!ring) return;
    const fill = ring.querySelector(".health-ring-fill");
    const text = ring.querySelector(".health-ring-text");
    if (isAlive) {
        fill.setAttribute("stroke", "var(--accent-green)");
        fill.setAttribute("stroke-dashoffset", "0");
        text.textContent = "●";
        text.className = "health-ring-text m-green";
    } else {
        fill.setAttribute("stroke", "var(--accent-red)");
        fill.setAttribute("stroke-dashoffset", "94.2");
        text.textContent = "✕";
        text.className = "health-ring-text m-red";
    }
}

// Check connection liveness every 3s
setInterval(() => {
    const alive = (Date.now() - lastTelemetryTime) < 5000;
    const badge = document.getElementById("systemStatus");
    const statusText = document.getElementById("statusText");
    if (alive) {
        badge.className = "status-badge online";
        statusText.textContent = "PIPELINE ONLINE";
    } else {
        badge.className = "status-badge warning";
        statusText.textContent = "AWAITING DATA";
    }
}, 3000);

// ── Scenario Trigger ──────────────────────────────────────────────
window.triggerScenario = function (name) {
    ekfData.fill(null);
    obdData.fill(null);
    velocityChart.update();

    // Pulse architecture flow
    ["node-sensors", "node-hal", "node-intel", "node-decision", "node-comms"].forEach((id, i) => {
        setTimeout(() => pulseNode(id), i * 200);
    });

    fetch("/api/demo/scenario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario: name }),
    })
        .then((r) => r.json())
        .then((data) => {
            const feed = document.getElementById("alertFeed");
            const marker = document.createElement("div");
            marker.style.cssText = "padding:6px 10px;color:var(--accent-blue);font-family:JetBrains Mono;font-size:11px;opacity:0.7";
            marker.textContent = `▶ SCENARIO: ${name.toUpperCase()}`;
            feed.prepend(marker);
        });
};

// ── NVH Polling ───────────────────────────────────────────────────
function fetchNVH() {
    fetch("/api/nvh/score")
        .then((r) => r.json())
        .then((data) => {
            const score = data.nvh_health_score_fft;
            const error = data.reconstruction_error;
            const anomaly = data.drivetrain_anomaly_detected;

            // Top card
            document.getElementById("nvh-score").innerHTML = `${score.toFixed(1)}<span class="metric-unit">%</span>`;

            // Large panel
            document.getElementById("nvh-score-lg").innerHTML = `${score.toFixed(1)}<span class="metric-unit">%</span>`;
            document.getElementById("nvh-error").textContent = error.toFixed(3);

            // Health bar
            const bar = document.getElementById("nvh-bar");
            bar.style.width = `${score}%`;

            const bandEl = document.getElementById("nvh-band");

            if (anomaly) {
                document.getElementById("nvh-score-lg").className = "metric-value mono m-red";
                document.getElementById("nvh-error").style.color = "var(--accent-red)";
                bar.style.background = "var(--accent-red)";
                bandEl.className = "mono m-red";
                bandEl.textContent = `⚠ ${data.anomaly_frequency_band}`;
                document.getElementById("card-nvh").className = "glass metric-card red";
            } else {
                document.getElementById("nvh-score-lg").className = "metric-value mono m-blue";
                document.getElementById("nvh-error").style.color = "var(--text-primary)";
                bar.style.background = "var(--accent-blue)";
                bandEl.className = "mono m-green";
                bandEl.textContent = "Nominal";
                document.getElementById("card-nvh").className = "glass metric-card blue";
            }
        })
        .catch(() => {});
}

setInterval(fetchNVH, 3000);
fetchNVH();

// ── Ambient Architecture Animation ────────────────────────────────
let archIdx = 0;
const archNodes = ["node-sensors", "node-hal", "node-intel", "node-decision", "node-comms", "node-storage"];
setInterval(() => {
    pulseNode(archNodes[archIdx % archNodes.length]);
    archIdx++;
}, 2000);
