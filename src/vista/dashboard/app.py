"""
VISTA Enterprise Dashboard Application
======================================
Connects the web dashboard directly to the real VISTA Core Intelligence.
"""

from __future__ import annotations

import os
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO
from loguru import logger

# ── Import Real VISTA Core ─────────────────────────────────────────
vista_root = Path(__file__).resolve().parent.parent
if str(vista_root) not in sys.path:
    sys.path.insert(0, str(vista_root))

from intelligence.velocity_ekf import VelocityEKF
from intelligence.crash_detector import CrashDetector, CrashEvidence
from intelligence.health_monitor import SystemHealthMonitor
from intelligence.audio_classifier import AudioClassifier
from intelligence.predictive_analytics import PredictiveAnalyticsEngine
from demo_data import SCENARIOS

# ── Globals ───────────────────────────────────────────────────────
_flask_app: Optional[Flask] = None
_socketio: Optional[SocketIO] = None

# Active Intelligence Modules
_ekf = VelocityEKF()
_detector = CrashDetector()
_audio = AudioClassifier()
_health = SystemHealthMonitor()
_predictive = PredictiveAnalyticsEngine()

from intelligence.theft_detector import TheftDetector
_theft = TheftDetector()

# Background Loop State
_bg_running = False
_bg_thread = None
_active_scenario = "normal"  # normal, crash, chaos, dropout
_scenario_trigger = False

def create_app() -> Flask:
    global _flask_app, _socketio
    
    current_dir = Path(__file__).resolve().parent
    _flask_app = Flask(
        __name__,
        template_folder=str(current_dir / "templates"),
        static_folder=str(current_dir / "static"),
    )
    _flask_app.config["SECRET_KEY"] = "vista-enterprise-secret"

    _socketio = SocketIO(
        _flask_app,
        async_mode="eventlet",
        cors_allowed_origins="*",
        logger=False,
        engineio_logger=False,
    )

    @_flask_app.route("/")
    def index():
        return render_template("index.html")

    @_flask_app.route("/api/status")
    def api_status():
        ekf_state = _ekf.get_state()
        report = _health.get_full_health_report(ekf_state)
        return jsonify({
            "mode": "live_intelligence",
            "uptime_seconds": time.time() - _health.startup_time,
            "health_report": report
        })

    @_flask_app.route("/api/demo/scenario", methods=["POST"])
    def api_demo_scenario():
        global _active_scenario, _scenario_trigger, _ekf, _detector
        data = request.json or {}
        scenario = data.get("scenario", "crash")
        
        if scenario == "can_bus_injection":
            logger.warning("B2B API: Triggering CAN-Bus Injection Attack Simulation...")
            _socketio.emit("alert", {
                "id": f"HACK-{int(time.time())}",
                "type": "theft_attempt",
                "confidence": 1.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": {"action": "CAN-Bus Unlock sequence detected"}
            })
            
            # Set up Ghost Key TSA mock state (CAN-Bus injection scenario):
            # - No BLE (thief doesn't have owner's phone)
            # - Missing door_open and driver_seated events (injected directly into CAN)
            # - Ultra-fast entry timing (automated tool, not human)
            _theft.mock_owner_ble_present = False
            _theft.mock_event_sequence = ["can_unlock", "engine_start"]  # Skipped door/seat
            _theft.mock_entry_duration_sec = 1.2  # Automated tool speed
            was_prevented = _theft.handle_motion_trigger(can_bus_hacked=True)
            
            if was_prevented:
                _socketio.emit("alert", {
                    "id": f"TSA-SUCCESS-{int(time.time())}",
                    "type": "theft_prevented",
                    "confidence": 1.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "details": {"action": "Ghost Key TSA: Temporal sequence anomaly. Analog Fuel Cut Engaged."}
                })
            return jsonify({"status": "ok", "scenario": scenario})

        if scenario in SCENARIOS:
            _active_scenario = scenario
            _scenario_trigger = True
            # Reset core states for new scenario run
            _ekf = VelocityEKF()
            _detector = CrashDetector()
            logger.info(f"Triggered scenario: {scenario}")
            return jsonify({"status": "ok", "scenario": scenario})
        return jsonify({"status": "error", "message": "Unknown scenario"}), 400

    @_flask_app.route("/api/events/recent")
    def api_events_recent():
        return jsonify({"events": []})  # Handled by live SocketIO now

    @_flask_app.route("/api/nvh/score")
    def api_nvh_score():
        """B2B Enterprise API Endpoint for Predictive NVH Degradation"""
        nvh_data = _predictive.calculate_nvh_reconstruction_error()
        return jsonify(nvh_data)

    return _flask_app

def _intelligence_loop():
    """Background thread that runs the actual VISTA core on synthetic scenarios."""
    global _bg_running, _scenario_trigger, _active_scenario
    
    # Idle loop generating nominal data
    prev_speed = 60.0
    
    while _bg_running:
        if _scenario_trigger:
            _scenario_trigger = False
            _run_scenario(_active_scenario)
            prev_speed = _ekf.get_velocity_kmh()  # sync back up
        else:
            # Idle Normal driving at 60km/h
            _health.ping_sensor("imu")
            _health.ping_sensor("obd")
            if _audio.model_loaded: _health.ping_sensor("audio")
            
            fwd_accel_g = 0.0
            _ekf.predict(fwd_accel_g)
            _ekf.update(prev_speed)
            ekf_speed = _ekf.get_velocity_kmh()
            
            _push_telemetry(
                ekf_speed=ekf_speed,
                raw_speed=prev_speed,
                imu_g=1.0,
                audio_label="normal",
                audio_conf=0.99
            )
            time.sleep(0.1)

def _run_scenario(scenario_name: str):
    """Run a specific physics scenario through the real intelligence pipeline."""
    frames = SCENARIOS[scenario_name]()
    prev_speed = frames[0].obd_speed_kmh if frames else 0.0
    
    for i, frame in enumerate(frames):
        if not _bg_running or _scenario_trigger:
            break
            
        loop_start = time.time()
        
        # Ping health monitor for active sensors
        _health.ping_sensor("imu")
        if frame.obd_speed_kmh is not None:
            _health.ping_sensor("obd")
        if _audio.model_loaded:
            _health.ping_sensor("audio")
            
        # 1. EKF
        current_obd = frame.obd_speed_kmh if frame.obd_speed_kmh is not None else prev_speed
        speed_change = (current_obd - prev_speed) / 3.6
        fwd_accel_g = speed_change / (0.1 * 9.81)
        _ekf.predict(fwd_accel_g)
        
        if frame.obd_speed_kmh is not None:
            _ekf.update(frame.obd_speed_kmh)
            prev_speed = frame.obd_speed_kmh
            
        ekf_speed = _ekf.get_velocity_kmh()
        
        # 2. Audio
        audio_label = "normal"
        audio_conf = 0.0
        if _audio.model_loaded and i % 10 == 0:
            audio_label, audio_conf = _audio.classify(frame.audio_waveform)
            
        # 3. Crash Detector
        jerk = _detector.check_imu(frame.imu_accel_magnitude_g, dt=0.1)
        ev = CrashEvidence(
            imu_jerk=jerk,
            imu_saturated=frame.imu_accel_magnitude_g > 15.0,
            imu_accel_magnitude=frame.imu_accel_magnitude_g,
            audio_class=audio_label,
            audio_confidence=audio_conf,
            obd_speed_drop=0,  # simplified for demo
            obd_throttle_drop=0,
            timestamp=time.time()
        )
        result = _detector.assess(ev)
        
        # 4. Push to Dashboard
        _push_telemetry(
            ekf_speed=ekf_speed,
            raw_speed=frame.obd_speed_kmh if frame.obd_speed_kmh is not None else 0.0,
            imu_g=frame.imu_accel_magnitude_g,
            audio_label=audio_label,
            audio_conf=audio_conf
        )
        
        if result["is_crash"]:
            _socketio.emit("alert", {
                "id": f"CRASH-{int(time.time())}",
                "type": "crash",
                "confidence": result["confidence"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": {"impact_g": frame.imu_accel_magnitude_g}
            })
        elif frame.event in ("pothole", "speed_bump") and not result["is_crash"]:
            _socketio.emit("alert", {
                "id": f"REJECTED-{int(time.time())}",
                "type": f"rejected_{frame.event}",
                "confidence": 1.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": {"impact_g": frame.imu_accel_magnitude_g}
            })
            
        # Pacing
        is_event = frame.event in ("crash", "pothole", "speed_bump")
        if is_event:
            time.sleep(0.02)
        else:
            elapsed = time.time() - loop_start
            time.sleep(max(0, 0.1 - elapsed))

def _push_telemetry(ekf_speed: float, raw_speed: float, imu_g: float, audio_label: str, audio_conf: float):
    if _socketio:
        _socketio.emit("telemetry", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ekf_speed": round(ekf_speed, 1),
            "raw_speed": round(raw_speed, 1),
            "imu_g": round(imu_g, 2),
            "audio_label": audio_label,
            "audio_conf": audio_conf,
            "capacity": _health.get_detection_capacity()
        })

def start(host: str = "0.0.0.0", port: int = 5000) -> None:
    global _bg_running, _bg_thread
    if _flask_app is None:
        raise RuntimeError("Call create_app() before start()")
        
    _bg_running = True
    _bg_thread = threading.Thread(target=_intelligence_loop, daemon=True)
    _bg_thread.start()
    
    logger.info(f"VISTA Enterprise Dashboard starting on {host}:{port}")
    _socketio.run(_flask_app, host=host, port=port, debug=False, use_reloader=False)

def stop() -> None:
    global _bg_running
    _bg_running = False
    if _bg_thread:
        _bg_thread.join(timeout=2.0)
    logger.info("Dashboard stopped")

if __name__ == "__main__":
    app = create_app()
    start()
