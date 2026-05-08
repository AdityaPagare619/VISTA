/**
 * VISTA Dashboard — Frontend JavaScript
 * ======================================
 * Handles SocketIO connection, real-time telemetry updates,
 * Chart.js speed chart, toast notifications for alerts,
 * and the demo crash trigger button.
 */

// ── Socket.IO Connection ──────────────────────────────────────────

const socket = io({
    transports: ["websocket", "polling"],
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
});

socket.on("connect", () => {
    console.log("[VISTA] SocketIO connected");
    updateStatusBadge(true);
    fetchInitialState();
});

socket.on("disconnect", () => {
    console.log("[VISTA] SocketIO disconnected");
    updateStatusBadge(false);
});

socket.on("connect_error", (err) => {
    console.warn("[VISTA] SocketIO error:", err.message);
    updateStatusBadge(false);
});

// ── Telemetry Updates (pushed every 1s) ───────────────────────────

socket.on("telemetry", (data) => {
    updateOBDCards(data);
    updateAudioClassification(data);
    updateSpeedChart(data);
});

// ── Alert Events ──────────────────────────────────────────────────

socket.on("alert", (event) => {
    console.log("[VISTA] Alert received:", event);
    showToast(event);
    addAlertToList(event);
});

// ── Chart.js Setup ────────────────────────────────────────────────

const MAX_CHART_POINTS = 60;
const chartLabels = [];
const chartData = [];

// Pre-fill with zeros so the chart starts clean
for (let i = 0; i < MAX_CHART_POINTS; i++) {
    chartLabels.push("");
    chartData.push(null);
}

const speedCtx = document.getElementById("speedChart").getContext("2d");
const speedChart = new Chart(speedCtx, {
    type: "line",
    data: {
        labels: chartLabels,
        datasets: [{
            label: "Speed (km/h)",
            data: chartData,
            borderColor: "#3fb950",
            backgroundColor: "rgba(63, 185, 80, 0.08)",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3,
            fill: true,
        }],
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 200 },
        scales: {
            x: {
                display: true,
                grid: { color: "rgba(48, 54, 61, 0.5)" },
                ticks: {
                    color: "#8b949e",
                    font: { size: 10, family: "monospace" },
                    maxTicksLimit: 8,
                    callback: function (val, index) {
                        // Show time every ~10s
                        return index % 10 === 0 ? this.getLabelForValue(val) : "";
                    },
                },
            },
            y: {
                display: true,
                min: 0,
                max: 120,
                grid: { color: "rgba(48, 54, 61, 0.5)" },
                ticks: {
                    color: "#8b949e",
                    font: { size: 10, family: "monospace" },
                    callback: (v) => v + "",
                },
            },
        },
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: "#1c2333",
                titleColor: "#3fb950",
                bodyColor: "#e6edf3",
                borderColor: "#30363d",
                borderWidth: 1,
                titleFont: { family: "monospace" },
                bodyFont: { family: "monospace" },
            },
        },
    },
});

// ── OBD Card Updates ──────────────────────────────────────────────

function updateOBDCards(data) {
    const speed = data.speed;
    const rpm = data.rpm;
    const throttle = data.throttle;
    const coolant = data.coolant_temp;

    document.getElementById("obdSpeed").textContent =
        speed != null ? speed.toFixed(0) : "--";
    document.getElementById("obdRPM").textContent =
        rpm != null ? rpm.toFixed(0) : "--";
    document.getElementById("obdThrottle").textContent =
        throttle != null ? throttle.toFixed(1) : "--";
    document.getElementById("obdCoolant").textContent =
        coolant != null ? coolant.toFixed(1) : "--";

    // Color-code temperature
    const coolantEl = document.getElementById("obdCoolant");
    if (coolant != null) {
        if (coolant > 105) coolantEl.style.color = "var(--red)";
        else if (coolant > 95) coolantEl.style.color = "var(--orange)";
        else coolantEl.style.color = "var(--green)";
    }
}

// ── Speed Chart Update ────────────────────────────────────────────

function updateSpeedChart(data) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString("en-US", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });

    // Shift and push
    chartLabels.push(timeStr);
    chartLabels.shift();

    const speed = data.speed != null ? data.speed : null;
    chartData.push(speed);
    chartData.shift();

    speedChart.update("none"); // no animation for smoother updates
}

// ── Audio Classification ──────────────────────────────────────────

const audioLabelEl = document.getElementById("audioLabel");
const audioConfEl = document.getElementById("audioConf");

function updateAudioClassification(data) {
    const ac = data.audio_classification;
    if (!ac) return;

    const label = ac.label || "normal";
    const confidence = ac.confidence != null ? ac.confidence : 0;

    audioLabelEl.textContent = label.toUpperCase();
    audioLabelEl.className = "audio-label " + label;
    audioConfEl.textContent = "Confidence: " + (confidence * 100).toFixed(0) + "%";
}

// ── Alerts List ───────────────────────────────────────────────────

const alertsList = document.getElementById("alertsList");
const MAX_ALERTS_SHOWN = 5;
let alertCount = 0;

function addAlertToList(event) {
    if (alertCount === 0) {
        alertsList.innerHTML = ""; // clear "No alerts yet"
    }

    const type = event.type || "unknown";
    const confidence = event.confidence != null ? (event.confidence * 100).toFixed(0) + "%" : "??";
    const timestamp = formatTime(event.timestamp);

    const item = document.createElement("div");
    item.className = "alert-item " + (type || "unknown");
    item.innerHTML = `
        <div class="alert-type">${formatAlertType(type)}</div>
        <div class="alert-meta">
            ${timestamp} &middot; Confidence ${confidence}
        </div>
    `;

    alertsList.prepend(item);
    alertCount++;

    // Enforce max alerts shown
    while (alertsList.children.length > MAX_ALERTS_SHOWN) {
        alertsList.removeChild(alertsList.lastChild);
    }
}

function formatAlertType(type) {
    return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatTime(isoString) {
    try {
        const d = new Date(isoString);
        return d.toLocaleTimeString("en-US", {
            hour12: false,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    } catch {
        return "--:--:--";
    }
}

// ── Toast Notifications ───────────────────────────────────────────

function showToast(event) {
    const container = document.getElementById("toastContainer");

    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent =
        "\u26A0 " + formatAlertType(event.type) +
        " (" + (event.confidence != null ? (event.confidence * 100).toFixed(0) + "%" : "?") + ")";

    container.appendChild(toast);

    // Auto-remove after fade-out
    setTimeout(() => {
        if (toast.parentNode) {
            toast.remove();
        }
    }, 5200);
}

// ── Status Badge ──────────────────────────────────────────────────

function updateStatusBadge(online) {
    const badge = document.getElementById("statusBadge");
    const text = document.getElementById("statusText");
    if (online) {
        badge.className = "status-badge online";
        text.textContent = "ONLINE";
    } else {
        badge.className = "status-badge offline";
        text.textContent = "OFFLINE";
    }
}

// ── Footer Updates ────────────────────────────────────────────────

function updateFooter(status) {
    document.getElementById("footerUptime").textContent =
        status.uptime_formatted || "--";

    const wifiEl = document.getElementById("footerWifi");
    const wifiDot = document.getElementById("wifiDot");
    wifiEl.textContent = status.mode === "live" ? "Active" : "Demo";
    wifiDot.className = "footer-dot " + (status.mode === "live" ? "good" : "warn");

    const battery = status.battery_v;
    const batteryEl = document.getElementById("footerBattery");
    if (battery != null) {
        batteryEl.textContent = battery.toFixed(1) + "V";
    } else {
        batteryEl.textContent = "--";
    }

    document.getElementById("footerMode").textContent =
        "MODE: " + (status.mode || "--").toUpperCase();
}

// ── Clock ─────────────────────────────────────────────────────────

function updateClock() {
    const now = new Date();
    document.getElementById("clock").textContent = now.toLocaleTimeString("en-US", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
}
updateClock();
setInterval(updateClock, 1000);

// ── Demo Crash Button ─────────────────────────────────────────────

document.getElementById("demoCrashBtn").addEventListener("click", () => {
    const btn = document.getElementById("demoCrashBtn");
    btn.textContent = "Sending...";
    btn.disabled = true;

    fetch("/api/demo/crash", { method: "POST" })
        .then((res) => res.json())
        .then((data) => {
            console.log("[VISTA] Demo crash response:", data);
            btn.textContent = "\u2713 Simulated!";
            setTimeout(() => {
                btn.textContent = "\u26A0 Trigger Crash Demo";
                btn.disabled = false;
            }, 2000);
        })
        .catch((err) => {
            console.error("[VISTA] Demo crash failed:", err);
            btn.textContent = "\u2717 Failed";
            setTimeout(() => {
                btn.textContent = "\u26A0 Trigger Crash Demo";
                btn.disabled = false;
            }, 2000);
        });
});

// ── Initial State Fetch ───────────────────────────────────────────

function fetchInitialState() {
    // Fetch system status
    fetch("/api/status")
        .then((res) => res.json())
        .then((status) => {
            updateFooter(status);
            updateStatusBadge(status.sensors && Object.values(status.sensors).some(Boolean));
        })
        .catch((err) => console.warn("[VISTA] Status fetch failed:", err));

    // Fetch recent events
    fetch("/api/events/recent?limit=5")
        .then((res) => res.json())
        .then((data) => {
            if (data.events && data.events.length > 0) {
                // Reverse to show oldest-first (they prepend)
                data.events.slice().reverse().forEach(addAlertToList);
            }
        })
        .catch((err) => console.warn("[VISTA] Events fetch failed:", err));
}

// ── Periodic Full Refresh (backup for SocketIO gaps) ──────────────

setInterval(() => {
    fetch("/api/status")
        .then((res) => res.json())
        .then(updateFooter)
        .catch(() => {});
}, 10000);
