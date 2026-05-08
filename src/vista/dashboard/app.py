"""
VISTA Flask Dashboard Application
==================================
Serves the live telemetry dashboard on port 5000.
Provides REST API endpoints and real-time SocketIO push.

Routes:
    /                       Dashboard homepage
    /api/status             System status JSON
    /api/telemetry/latest   Latest sensor readings
    /api/events/recent      Recent events from SQLite
    /api/history            Time-series from InfluxDB
    /api/demo/crash         POST — simulate crash event
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import eventlet

eventlet.monkey_patch()  # noqa: E402 — must precede socketio/flask imports

from flask import Flask, jsonify, render_template, request  # noqa: E402
from flask_socketio import SocketIO, emit  # noqa: E402
from loguru import logger  # noqa: E402

# ── Lazy HAL imports (may not be available at import time) ─────────

_hal_available = False
try:
    import sys as _sys

    _vista_root = Path(__file__).resolve().parent.parent
    if str(_vista_root) not in _sys.path:
        _sys.path.insert(0, str(_vista_root))

    from hal import OBDReader, IMUReader, AudioCapture, CameraCapture, GPIOManager

    _hal_available = True
    logger.info("HAL modules loaded for dashboard")
except Exception as exc:
    logger.warning(f"HAL modules not available: {exc} — dashboard runs in standalone mode")
    OBDReader = None  # type: ignore
    IMUReader = None  # type: ignore
    AudioCapture = None  # type: ignore
    CameraCapture = None  # type: ignore
    GPIOManager = None  # type: ignore

# ── Lazy sister-module imports ────────────────────────────────────

_sqlite_available = False
try:
    from data.sqlite_manager import SQLiteManager

    _sqlite_available = True
except Exception:
    logger.info("SQLiteManager not available — /api/events will return demo data")

_influx_available = False
try:
    from data.influx_writer import InfluxWriter

    _influx_available = True
except Exception:
    logger.info("InfluxWriter not available — /api/history will return demo data")

_fusion_available = False
try:
    from intelligence.fusion_engine import FusionEngine

    _fusion_available = True
except Exception:
    logger.info("FusionEngine not available")

_decision_available = False
try:
    from intelligence.decision_engine import DecisionEngine

    _decision_available = True
except Exception:
    logger.info("DecisionEngine not available")

_alert_available = False
try:
    from communication.alert_manager import AlertManager

    _alert_available = True
except Exception:
    logger.info("AlertManager not available")

# ── Globals ───────────────────────────────────────────────────────

_flask_app: Optional[Flask] = None
_socketio: Optional[SocketIO] = None
_start_time: Optional[datetime] = None
_sensors: Dict[str, Any] = {}
_mode: str = "standalone"

# In-memory event buffer (fallback when SQLite unavailable)
_demo_events: List[Dict[str, Any]] = []

# Background task control
_bg_running = False
_bg_thread: Optional[threading.Thread] = None


# ── Flask App Factory ─────────────────────────────────────────────


def create_app() -> Flask:
    """Create and configure the Flask application.

    Returns a Flask app instance with SocketIO attached.
    Call ``start()`` after this to initialise sensors and begin serving.
    """
    global _flask_app, _socketio, _start_time

    _flask_app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    _flask_app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "vista-dashboard-secret")

    _socketio = SocketIO(
        _flask_app,
        async_mode="eventlet",
        cors_allowed_origins="*",
        logger=False,
        engineio_logger=False,
    )

    _start_time = datetime.now(timezone.utc)

    # ── Register routes ───────────────────────────────────────────

    @_flask_app.route("/")
    def index():
        """Serve the dashboard homepage."""
        return render_template("index.html")

    @_flask_app.route("/api/status")
    def api_status():
        """Return system status as JSON."""
        global _mode

        uptime_seconds = (datetime.now(timezone.utc) - _start_time).total_seconds() if _start_time else 0

        sensor_status = {
            "obd": _sensor_available("obd"),
            "imu": _sensor_available("imu"),
            "audio": _sensor_available("audio"),
            "camera": _sensor_available("camera"),
            "esp32": _sensor_available("esp32"),
        }

        battery_v = _get_battery_voltage()
        alerts_today = _count_alerts_today()

        return jsonify({
            "mode": _mode,
            "uptime_seconds": round(uptime_seconds, 1),
            "uptime_formatted": _format_uptime(uptime_seconds),
            "sensors": sensor_status,
            "battery_v": battery_v,
            "alerts_today": alerts_today,
        })

    @_flask_app.route("/api/telemetry/latest")
    def api_telemetry_latest():
        """Return latest sensor readings as JSON."""
        data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        obd = _sensors.get("obd")
        if obd and hasattr(obd, "get_all_pids"):
            data["obd"] = obd.get_all_pids()
        else:
            data["obd"] = _demo_obd_data()

        imu = _sensors.get("imu")
        if imu and hasattr(imu, "get_all"):
            data["imu"] = imu.get_all()
        else:
            data["imu"] = _demo_imu_data()

        audio = _sensors.get("audio")
        if audio and hasattr(audio, "get_window"):
            window = audio.get_window()
            data["audio"] = {
                "sample_rate": getattr(audio, "sample_rate", 16000),
                "rms": float(abs(window).mean()) if hasattr(window, "__abs__") else 0.001,
            }
        else:
            data["audio"] = {"sample_rate": 16000, "rms": 0.001}

        # Audio classification stub (filled by decision_engine or demo)
        data["audio_classification"] = _get_audio_classification()

        return jsonify(data)

    @_flask_app.route("/api/events/recent")
    def api_events_recent():
        """Return recent events (limit parameter, default 10)."""
        limit = request.args.get("limit", 10, type=int)
        limit = max(1, min(limit, 100))

        if _sqlite_available:
            try:
                events = _query_sqlite_events(limit)
                if events is not None:
                    return jsonify({"events": events})
            except Exception as exc:
                logger.warning(f"SQLite events query failed: {exc}")

        # Fallback: demo events
        if not _demo_events:
            _seed_demo_events()

        return jsonify({"events": _demo_events[-limit:]})

    @_flask_app.route("/api/history")
    def api_history():
        """Return time-series data for the last N hours (default 24)."""
        hours = request.args.get("hours", 24, type=int)
        hours = max(1, min(hours, 168))  # 1h – 1 week

        if _influx_available:
            try:
                data = _query_influx_history(hours)
                if data is not None:
                    return jsonify(data)
            except Exception as exc:
                logger.warning(f"InfluxDB history query failed: {exc}")

        # Fallback: generate demo time-series
        return jsonify(_demo_history(hours))

    @_flask_app.route("/api/demo/crash", methods=["POST"])
    def api_demo_crash():
        """Simulate a crash event for demonstration purposes."""
        global _demo_events

        crash_event = {
            "id": f"DEMO-{int(time.time())}",
            "type": "crash",
            "confidence": round(0.75 + 0.2 * (hash(str(time.time())) % 100) / 100, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": {
                "speed_kmh": round(45 + 30 * (hash(str(time.time() + 1)) % 100) / 100, 1),
                "impact_g": round(2.5 + 1.5 * (hash(str(time.time() + 2)) % 100) / 100, 1),
                "location": "simulated",
            },
        }
        _demo_events.append(crash_event)

        # Keep last 100 events
        if len(_demo_events) > 100:
            _demo_events[:] = _demo_events[-100:]

        # Push alert via SocketIO
        if _socketio:
            _socketio.emit("alert", crash_event)

        # Activate buzzer if available
        gpio = _sensors.get("gpio")
        if gpio and hasattr(gpio, "buzzer_beep"):
            try:
                gpio.buzzer_beep(pattern=[0.3, 0.1, 0.3, 0.1, 0.3], frequency=800)
            except Exception as exc:
                logger.warning(f"Buzzer beep failed: {exc}")

        logger.info(f"[DEMO] Crash event simulated: {crash_event['id']}")
        return jsonify({"status": "ok", "event": crash_event})

    logger.success("Flask dashboard application created")
    return _flask_app


# ── Lifecycle ─────────────────────────────────────────────────────


def start(host: str = "0.0.0.0", port: int = 5000) -> None:
    """Initialise sensors and start serving the dashboard.

    Args:
        host: Bind address (default 0.0.0.0 for LAN access).
        port: TCP port (default 5000).
    """
    global _mode, _bg_running, _bg_thread

    if _flask_app is None:
        raise RuntimeError("Call create_app() before start()")

    _initialise_sensors()
    _mode = "demo" if _using_demo() else "live"

    # Start background telemetry push
    _bg_running = True
    _bg_thread = threading.Thread(
        target=_telemetry_push_loop,
        name="dashboard-telemetry",
        daemon=True,
    )
    _bg_thread.start()

    logger.info(f"VISTA Dashboard starting on {host}:{port} (mode={_mode})")
    _socketio.run(_flask_app, host=host, port=port, debug=False, use_reloader=False)


def stop() -> None:
    """Gracefully stop the dashboard and release sensor resources."""
    global _bg_running

    logger.info("Dashboard stopping…")
    _bg_running = False

    if _bg_thread and _bg_thread.is_alive():
        _bg_thread.join(timeout=3.0)

    for name, sensor in _sensors.items():
        if sensor and hasattr(sensor, "stop"):
            try:
                sensor.stop()
                logger.debug(f"Stopped sensor: {name}")
            except Exception as exc:
                logger.warning(f"Error stopping sensor '{name}': {exc}")

    _sensors.clear()
    logger.info("Dashboard stopped")


# ── Sensor Management ─────────────────────────────────────────────


def _initialise_sensors() -> None:
    """Initialise all available HAL sensors."""
    global _sensors

    if not _hal_available:
        logger.info("HAL not available — dashboard running fully in demo mode")
        return

    sensor_classes = {
        "obd": OBDReader,
        "imu": IMUReader,
        "audio": AudioCapture,
        "camera": CameraCapture,
        "gpio": GPIOManager,
    }

    for name, cls in sensor_classes.items():
        if cls is None:
            continue
        try:
            instance = cls()
            instance.start()
            _sensors[name] = instance
            logger.success(f"Sensor initialised: {name}")
        except Exception as exc:
            logger.error(f"Failed to initialise sensor '{name}': {exc}")


def _sensor_available(name: str) -> bool:
    """Check if a sensor is initialised and running."""
    sensor = _sensors.get(name)
    if sensor is None:
        return False
    if hasattr(sensor, "is_running"):
        return sensor.is_running if callable(sensor.is_running) else bool(sensor.is_running)
    if hasattr(sensor, "is_connected"):
        return sensor.is_connected() if callable(sensor.is_connected) else bool(sensor.is_connected)
    return sensor is not None


def _using_demo() -> bool:
    """Return True if running in demo/standalone mode."""
    for sensor in _sensors.values():
        if hasattr(sensor, "_demo_mode") and getattr(sensor, "_demo_mode"):
            return True
    return not _hal_available


# ── Background Telemetry Push ─────────────────────────────────────


def _telemetry_push_loop() -> None:
    """Background thread: push telemetry and alerts via SocketIO every second."""
    while _bg_running:
        try:
            if _socketio:
                # Push latest telemetry
                telemetry = _build_telemetry_payload()
                _socketio.emit("telemetry", telemetry)

                # Check for new alerts (from decision engine)
                _push_alerts()
        except Exception as exc:
            logger.warning(f"Telemetry push error: {exc}")

        time.sleep(1.0)


def _build_telemetry_payload() -> Dict[str, Any]:
    """Build the telemetry payload for SocketIO push."""
    obd = _sensors.get("obd")
    obd_data = obd.get_all_pids() if obd and hasattr(obd, "get_all_pids") else {}
    if not obd_data:
        obd_data = _demo_obd_data()

    imu = _sensors.get("imu")
    imu_data = imu.get_all() if imu and hasattr(imu, "get_all") else _demo_imu_data()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "speed": obd_data.get("SPEED"),
        "rpm": obd_data.get("RPM"),
        "throttle": obd_data.get("THROTTLE_POS"),
        "engine_load": obd_data.get("ENGINE_LOAD"),
        "coolant_temp": obd_data.get("COOLANT_TEMP"),
        "audio_classification": _get_audio_classification(),
        "battery_v": _get_battery_voltage(),
    }


def _push_alerts() -> None:
    """Push any pending alerts from the decision engine via SocketIO."""
    if not _decision_available or not _alert_available:
        return

    try:
        # Check decision engine for recent alerts
        from intelligence.decision_engine import DecisionEngine
        de = _sensors.get("decision_engine")
        if de and hasattr(de, "get_recent_alerts"):
            alerts = de.get_recent_alerts(since_seconds=1)
            for alert in alerts:
                _socketio.emit("alert", alert)
    except Exception as exc:
        logger.debug(f"Alert push skipped: {exc}")


# ── Demo Data Generators ──────────────────────────────────────────

_DEMO_SPEED = 60.0
_DEMO_RPM = 2200.0


def _demo_obd_data() -> Dict[str, Any]:
    """Generate realistic demo OBD data."""
    global _DEMO_SPEED, _DEMO_RPM
    import random

    t = time.time()
    _DEMO_SPEED = 60.0 + 20.0 * (0.5 * (1 + __import__("math").sin(t * 0.3)))
    _DEMO_SPEED = max(0, min(120, _DEMO_SPEED))
    _DEMO_RPM = 2200.0 + _DEMO_SPEED * 25 + random.uniform(-100, 100)
    _DEMO_RPM = max(700, min(5500, _DEMO_RPM))

    return {
        "SPEED": round(_DEMO_SPEED, 1),
        "RPM": round(_DEMO_RPM, 0),
        "THROTTLE_POS": round(25 + 15 * __import__("math").sin(t * 0.25), 1),
        "ENGINE_LOAD": round(35 + random.uniform(-5, 5), 1),
        "COOLANT_TEMP": round(90 + random.uniform(-2, 2), 1),
    }


def _demo_imu_data() -> Dict[str, Any]:
    """Generate realistic demo IMU data."""
    import random
    import numpy as np

    t = time.time()
    noise = 0.02
    return {
        "accel": (
            round(noise * np.sin(t * 50) * random.uniform(0.5, 1.5), 4),
            round(noise * np.sin(t * 47) * random.uniform(0.5, 1.5), 4),
            round(1.0 + noise * np.sin(t * 53) * random.uniform(0.5, 1.5), 4),
        ),
        "gyro": (
            round(np.sin(t * 20) * random.uniform(0.5, 1.5), 2),
            round(np.sin(t * 22) * random.uniform(0.5, 1.5), 2),
            round(np.sin(t * 18) * random.uniform(0.5, 1.5), 2),
        ),
        "temperature": round(28.0 + 2.0 * np.sin(t * 0.1), 1),
    }


def _get_audio_classification() -> Dict[str, Any]:
    """Return simulated audio classification (or real if available)."""
    import random

    return {
        "label": random.choices(
            ["normal", "normal", "normal", "horn", "siren", "crash"],
            weights=[0.85, 0.05, 0.03, 0.03, 0.02, 0.02],
        )[0],
        "confidence": round(0.6 + random.uniform(0, 0.35), 2),
    }


def _get_battery_voltage() -> float:
    """Return battery voltage (from ESP32 or demo)."""
    gpio = _sensors.get("gpio")
    if gpio and hasattr(gpio, "read_esp32_status"):
        status = gpio.read_esp32_status()
        if status and "battery_v" in status:
            return float(status["battery_v"])
    return round(12.4, 1)


def _count_alerts_today() -> int:
    """Count alerts generated today."""
    if _sqlite_available:
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            db = SQLiteManager()
            result = db.query(
                "SELECT COUNT(*) as cnt FROM events WHERE date(timestamp) = ?",
                (today,),
            )
            if result:
                return result[0].get("cnt", 0)
        except Exception:
            pass
    # Demo: count from in-memory events
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return sum(
        1 for e in _demo_events
        if e.get("timestamp", "").startswith(today)
    )


def _seed_demo_events() -> None:
    """Populate demo event buffer."""
    global _demo_events
    now = datetime.now(timezone.utc)
    _demo_events = [
        {
            "id": "EVT-001",
            "type": "harsh_braking",
            "confidence": 0.72,
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "details": {"jerk_gs": 3.5, "speed_before": 82.0},
        },
        {
            "id": "EVT-002",
            "type": "horn_detected",
            "confidence": 0.88,
            "timestamp": (now - timedelta(minutes=12)).isoformat(),
            "details": {"duration_s": 1.2},
        },
        {
            "id": "EVT-003",
            "type": "rapid_acceleration",
            "confidence": 0.65,
            "timestamp": (now - timedelta(minutes=20)).isoformat(),
            "details": {"accel_g": 0.55},
        },
        {
            "id": "EVT-004",
            "type": "siren_detected",
            "confidence": 0.91,
            "timestamp": (now - timedelta(minutes=35)).isoformat(),
            "details": {"duration_s": 3.5},
        },
        {
            "id": "EVT-005",
            "type": "crash_warning",
            "confidence": 0.48,
            "timestamp": (now - timedelta(hours=1, minutes=10)).isoformat(),
            "details": {"speed_kmh": 55.0, "impact_g": 1.8},
        },
    ]


def _demo_history(hours: int) -> Dict[str, Any]:
    """Generate demo time-series data for the given time window."""
    import math
    import random

    now = time.time()
    points = []
    interval = max(1, (hours * 3600) // 300)  # aim for ~300 points

    for i in range(300):
        t = now - (300 - i) * interval
        ts = datetime.fromtimestamp(t, tz=timezone.utc).isoformat()

        speed = 60.0 + 20.0 * math.sin(t * 0.05) + random.uniform(-3, 3)
        rpm = 2200.0 + speed * 25 + random.uniform(-50, 50)
        coolant = 90.0 + random.uniform(-2, 2)

        points.append({
            "time": ts,
            "speed": round(max(0, speed), 1),
            "rpm": round(max(500, rpm), 0),
            "coolant_temp": round(coolant, 1),
            "throttle": round(25 + 10 * math.sin(t * 0.04), 1),
        })

    return {"points": points, "hours": hours}


# ── SQLite / InfluxDB Helpers ─────────────────────────────────────


def _query_sqlite_events(limit: int) -> Optional[List[Dict[str, Any]]]:
    """Query recent events from SQLite. Returns None on failure."""
    if not _sqlite_available:
        return None
    try:
        db = SQLiteManager()
        rows = db.query(
            "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in (rows or [])]
    except Exception:
        return None


def _query_influx_history(hours: int) -> Optional[Dict[str, Any]]:
    """Query time-series from InfluxDB. Returns None on failure."""
    if not _influx_available:
        return None
    try:
        writer = InfluxWriter()
        # Use the writer's query method if available
        if hasattr(writer, "query_range"):
            data = writer.query_range(
                bucket="vista_telemetry",
                measurement="sensors",
                start=f"-{hours}h",
                fields=["speed", "rpm", "coolant_temp", "throttle"],
            )
            return {"points": data, "hours": hours}
        return None
    except Exception:
        return None


# ── Utilities ─────────────────────────────────────────────────────


def _format_uptime(seconds: float) -> str:
    """Format uptime seconds into a human-readable string."""
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{secs}s")
    elif secs and len(parts) < 3:
        parts.append(f"{secs}s")
    return " ".join(parts)
