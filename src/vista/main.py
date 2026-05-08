#!/usr/bin/env python3
"""
VISTA — Vehicle Intelligence & Safety Telematics Architecture
=============================================================
System entry point. Initializes and orchestrates all VISTA modules
in the correct dependency order, then runs the main telemetry loop.

Modes (--mode):
    driving  — Active vehicle monitoring (OBD+IMU+audio+camera+vision)
    parked   — Low-power sleep; ESP32 handles PIR wake (requires GPIO)
    demo     — Classroom demo with simulated data

Demo scenarios (--demo-scenario):
    normal   — Simulated normal driving
    crash    — Orchestrated crash sequence
    theft    — PIR-based theft walk-through

Usage:
    python main.py --mode driving
    python main.py --mode demo --demo-scenario crash

Environment:
    DEMO_MODE=true               Override demo mode (highest priority)
    GEMINI_API_KEY=...           Cloud Vision API key
    TELEGRAM_BOT_TOKEN=...       Telegram alert bot token
    INFLUXDB_TOKEN=...           InfluxDB write token
    OBD_SIM_PORT=/tmp/obd_sim    OBD simulator port (demo mode)
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# ── Add vista package root to sys.path ─────────────────────────────
_VISTA_ROOT = Path(__file__).resolve().parent
if str(_VISTA_ROOT) not in sys.path:
    sys.path.insert(0, str(_VISTA_ROOT))

# ── Environment loading (best-effort, before any config access) ─────
try:
    from dotenv import load_dotenv

    _env_path = _VISTA_ROOT / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

# ── Logging ─────────────────────────────────────────────────────────
from loguru import logger

# ── Config loading (matches hal's singleton pattern) ────────────────
import threading

import yaml

_config: Dict[str, Any] | None = None
_config_lock = threading.Lock()


def load_config() -> Dict[str, Any]:
    """Load and cache VISTA configuration from config.yaml."""
    global _config
    if _config is not None:
        return _config
    with _config_lock:
        if _config is not None:
            return _config
        config_path = _VISTA_ROOT / "config.yaml"
        if not config_path.exists():
            logger.error(f"config.yaml not found at {config_path}")
            raise FileNotFoundError(f"config.yaml not found at {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)
        logger.info(
            f"Config loaded | device={_config.get('device', {}).get('id', '?')} | "
            f"demo_mode={_config.get('system', {}).get('demo_mode', False)}"
        )
        return _config


def is_demo_mode() -> bool:
    """Return True if running in demo mode (env override takes priority)."""
    env_demo = os.environ.get("DEMO_MODE", "").lower()
    if env_demo in ("true", "1", "yes", "on"):
        return True
    if env_demo in ("false", "0", "no", "off"):
        return False
    cfg = load_config()
    return bool(cfg.get("system", {}).get("demo_mode", False))


# ── Console log sink for clean startup output ──────────────────────
logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    colorize=True,
)

# ── File log sink ───────────────────────────────────────────────────
_log_cfg = load_config()
_log_path = _VISTA_ROOT / _log_cfg.get("system", {}).get("log_path", "logs/vista.log")
_log_path.parent.mkdir(parents=True, exist_ok=True)
_log_level = _log_cfg.get("system", {}).get("log_level", "INFO")
logger.add(
    _log_path,
    level=_log_level,
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
)


# ══════════════════════════════════════════════════════════════════════
# Module Imports (graceful degradation for modules not yet built)
# ══════════════════════════════════════════════════════════════════════

# ── HAL (fully implemented) ─────────────────────────────────────────
try:
    from hal import OBDReader, IMUReader, AudioCapture, CameraCapture, GPIOManager

    HAL_AVAILABLE = True
except ImportError as exc:
    logger.error(f"HAL import failed: {exc}")
    HAL_AVAILABLE = False
    OBDReader, IMUReader, AudioCapture, CameraCapture, GPIOManager = (
        None,
        None,
        None,
        None,
        None,
    )

# ── Intelligence (stub — modules may not exist yet) ─────────────────
try:
    from intelligence import (
        FusionEngine,
        AudioClassifier,
        DecisionEngine,
        CloudVision,
        Evidence,
    )

    INTEL_AVAILABLE = True
except (ImportError, SyntaxError) as exc:
    logger.warning(f"Intelligence layer not available: {exc} — running without")
    INTEL_AVAILABLE = False
    FusionEngine, AudioClassifier, DecisionEngine, CloudVision, Evidence = (
        None,
        None,
        None,
        None,
        None,
    )

# ── Communication (stub — Decision dataclass exists, rest may not) ──
try:
    from communication import Decision, MQTTManager, BLEManager, AlertManager

    COMM_AVAILABLE = True
except ImportError as exc:
    # Fallback: only the Decision dataclass may be importable from __init__
    try:
        from communication import Decision

        COMM_AVAILABLE = True
    except ImportError:
        logger.warning(f"Communication layer not available: {exc} — running without")
        COMM_AVAILABLE = False
        Decision, MQTTManager, BLEManager, AlertManager = None, None, None, None

# ── Dashboard (stub — import may fail) ──────────────────────────────
try:
    from dashboard import create_app, start as dash_start, stop as dash_stop

    DASH_AVAILABLE = True
except ImportError as exc:
    logger.warning(f"Dashboard not available: {exc} — running without")
    DASH_AVAILABLE = False
    create_app, dash_start, dash_stop = None, None, None


# ══════════════════════════════════════════════════════════════════════
# System State
# ══════════════════════════════════════════════════════════════════════

class SystemState:
    """Global system state container — thread-safe flags for shutdown."""

    def __init__(self) -> None:
        self.running = True
        self.mode: str = "driving"
        self.demo_scenario: str = "normal"
        self.modules: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def shutdown(self) -> None:
        with self._lock:
            self.running = False

    def is_running(self) -> bool:
        with self._lock:
            return self.running


state = SystemState()


# ══════════════════════════════════════════════════════════════════════
# Signal Handlers
# ══════════════════════════════════════════════════════════════════════

def handle_shutdown(signum: int, frame: Any) -> None:
    """Handle SIGINT (Ctrl+C) and SIGTERM gracefully."""
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name} — initiating graceful shutdown")
    state.shutdown()


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


# ══════════════════════════════════════════════════════════════════════
# Module Initialization
# ══════════════════════════════════════════════════════════════════════

def init_hal(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Initialize Hardware Abstraction Layer modules."""
    modules: Dict[str, Any] = {}
    if not HAL_AVAILABLE:
        logger.warning("HAL not available — skipping hardware init")
        return modules

    sensors = cfg.get("sensors", {})

    # OBD Reader
    try:
        obd = OBDReader()
        obd.start()
        modules["obd"] = obd
        logger.info("OBDReader started")
    except Exception as exc:
        logger.error(f"OBDReader failed: {exc}")

    # IMU Reader
    try:
        if sensors.get("imu", {}).get("enabled", True):
            imu = IMUReader()
            imu.start()
            modules["imu"] = imu
            logger.info("IMUReader started")
    except Exception as exc:
        logger.error(f"IMUReader failed: {exc}")

    # Audio Capture
    try:
        if sensors.get("audio", {}).get("enabled", True):
            audio = AudioCapture()
            audio.start()
            modules["audio"] = audio
            logger.info("AudioCapture started")
    except Exception as exc:
        logger.error(f"AudioCapture failed: {exc}")

    # Camera Capture
    try:
        if sensors.get("camera", {}).get("enabled", True):
            camera = CameraCapture()
            camera.start()
            modules["camera"] = camera
            logger.info("CameraCapture started")
    except Exception as exc:
        logger.error(f"CameraCapture failed: {exc}")

    # GPIO Manager
    try:
        gpio = GPIOManager()
        gpio.start()
        modules["gpio"] = gpio
        logger.info("GPIOManager started")
    except Exception as exc:
        logger.error(f"GPIOManager failed: {exc}")

    return modules


def init_intelligence(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Initialize Intelligence modules (best-effort)."""
    modules: Dict[str, Any] = {}
    if not INTEL_AVAILABLE:
        logger.warning("Intelligence layer not available — skipping")
        return modules

    try:
        fusion = FusionEngine()
        modules["fusion"] = fusion
        logger.info("FusionEngine started")
    except Exception as exc:
        logger.error(f"FusionEngine failed: {exc}")

    try:
        classifier = AudioClassifier()
        modules["audio_classifier"] = classifier
        logger.info("AudioClassifier started")
    except Exception as exc:
        logger.error(f"AudioClassifier failed: {exc}")

    try:
        decision = DecisionEngine()
        modules["decision_engine"] = decision
        logger.info("DecisionEngine started")
    except Exception as exc:
        logger.error(f"DecisionEngine failed: {exc}")

    try:
        vision = CloudVision()
        modules["cloud_vision"] = vision
        logger.info("CloudVision started")
    except Exception as exc:
        logger.error(f"CloudVision failed: {exc}")

    return modules


def init_communication(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Initialize Communication modules (best-effort)."""
    modules: Dict[str, Any] = {}
    if not COMM_AVAILABLE:
        logger.warning("Communication layer not available — skipping")
        return modules

    try:
        if cfg.get("communication", {}).get("mqtt", {}).get("broker_host"):
            mqtt = MQTTManager()
            modules["mqtt"] = mqtt
            logger.info("MQTTManager started")
    except Exception as exc:
        logger.error(f"MQTTManager failed: {exc}")

    try:
        if cfg.get("communication", {}).get("ble", {}).get("device_name"):
            ble = BLEManager()
            modules["ble"] = ble
            logger.info("BLEManager started")
    except Exception as exc:
        logger.error(f"BLEManager failed: {exc}")

    try:
        alert = AlertManager()
        modules["alert"] = alert
        logger.info("AlertManager started")
    except Exception as exc:
        logger.error(f"AlertManager failed: {exc}")

    return modules


def init_dashboard(cfg: Dict[str, Any]) -> Optional[Any]:
    """Initialize dashboard web app (best-effort)."""
    if not DASH_AVAILABLE:
        logger.warning("Dashboard not available — skipping")
        return None
    try:
        app = create_app()
        dash_start()
        logger.info("Dashboard started")
        return app
    except Exception as exc:
        logger.error(f"Dashboard failed: {exc}")
        return None


# ══════════════════════════════════════════════════════════════════════
# Telemetry Helpers
# ══════════════════════════════════════════════════════════════════════

def write_telemetry_point(
    obd: Any, imu: Any, modules: Dict[str, Any], timestamp: float
) -> None:
    """Write a single telemetry point. Best-effort — never crashes main loop."""
    try:
        data = {
            "timestamp": timestamp,
            "speed": 0.0,
            "rpm": 0.0,
            "throttle": 0.0,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": 0.0,
            "gyro_x": 0.0,
            "gyro_y": 0.0,
            "gyro_z": 0.0,
        }

        if obd and hasattr(obd, "get_speed"):
            try:
                data["speed"] = obd.get_speed() or 0.0
            except Exception:
                data["speed"] = 0.0
            try:
                data["rpm"] = obd.get_rpm() or 0.0
            except Exception:
                data["rpm"] = 0.0
            try:
                data["throttle"] = obd.get_throttle_position() or 0.0
            except Exception:
                data["throttle"] = 0.0

        imu_reader = modules.get("imu")
        if imu_reader and hasattr(imu_reader, "get_all"):
            try:
                imu_data = imu_reader.get_all()
                accel = imu_data.get("accel", (0, 0, 0))
                gyro = imu_data.get("gyro", (0, 0, 0))
                data["accel_x"] = accel[0] if accel else 0.0
                data["accel_y"] = accel[1] if accel and len(accel) > 1 else 0.0
                data["accel_z"] = accel[2] if accel and len(accel) > 2 else 0.0
                data["gyro_x"] = gyro[0] if gyro else 0.0
                data["gyro_y"] = gyro[1] if gyro and len(gyro) > 1 else 0.0
                data["gyro_z"] = gyro[2] if gyro and len(gyro) > 2 else 0.0
            except Exception:
                pass

        # Log to console (every cycle would be noisy — log at debug)
        logger.debug(
            f"Telemetry | speed={data['speed']:.1f} km/h | "
            f"rpm={data['rpm']:.0f} | throttle={data['throttle']:.0f}%"
        )

        # Write to InfluxDB (best-effort)
        try:
            import influxdb_client
            from influxdb_client.client.write_api import SYNCHRONOUS

            cfg = load_config()
            influx_cfg = cfg.get("storage", {}).get("influxdb", {})
            token = os.environ.get(influx_cfg.get("token_env", "INFLUXDB_TOKEN"), "")
            if token:
                client = influxdb_client.InfluxDBClient(
                    url=f"http://{influx_cfg.get('host', 'localhost')}:{influx_cfg.get('port', 8086)}",
                    token=token,
                    org=influx_cfg.get("org", "vista"),
                )
                write_api = client.write_api(write_options=SYNCHRONOUS)
                point = (
                    influxdb_client.Point("telemetry")
                    .tag("device", cfg.get("device", {}).get("id", "VISTA-0001"))
                    .field("speed_kmh", float(data["speed"]))
                    .field("rpm", float(data["rpm"]))
                    .field("throttle_pct", float(data["throttle"]))
                    .field("accel_x_g", float(data["accel_x"]))
                    .field("accel_y_g", float(data["accel_y"]))
                    .field("accel_z_g", float(data["accel_z"]))
                    .field("gyro_x_dps", float(data["gyro_x"]))
                    .field("gyro_y_dps", float(data["gyro_y"]))
                    .field("gyro_z_dps", float(data["gyro_z"]))
                    .time(timestamp)
                )
                write_api.write(
                    bucket=influx_cfg.get("bucket", "vista_telemetry"),
                    record=point,
                )
                client.close()
        except ImportError:
            pass  # influxdb-client not installed — skip silently
        except Exception as exc:
            logger.debug(f"InfluxDB write skipped: {exc}")

    except Exception as exc:
        logger.warning(f"Telemetry write failed (non-fatal): {exc}")


def run_audio_classification(
    modules: Dict[str, Any], timestamp: float
) -> Optional[str]:
    """Run audio classification and return label if detection made."""
    try:
        audio = modules.get("audio")
        classifier = modules.get("audio_classifier")
        if not audio or not classifier:
            return None
        window = audio.get_window()
        if window is None:
            return None
        result = classifier.classify(window)
        label = result.get("label", "normal") if isinstance(result, dict) else "normal"
        if label and label != "normal":
            logger.info(f"Audio classification: {label} (conf={result.get('confidence', 0):.2f})")
        return label
    except Exception as exc:
        logger.debug(f"Audio classification skipped: {exc}")
        return None


def check_crash_conditions(
    modules: Dict[str, Any], obd: Any, audio_label: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Check for crash conditions via decision engine. Returns decision dict or None."""
    try:
        decision_engine = modules.get("decision_engine")
        if not decision_engine:
            if is_demo_mode():
                # Simulated crash detection: check audio label
                if audio_label == "crash":
                    return {"event_type": "crash", "confidence": 0.85, "severity": "critical"}
            return None

        # Gather sensor evidence
        evidence: Dict[str, float] = {}

        # IMU jerk
        imu = modules.get("imu")
        if imu and hasattr(imu, "get_all"):
            try:
                imu_data = imu.get_all()
                accel = imu_data.get("accel", (0, 0, 0))
                evidence["imu_jerk"] = abs(accel[0]) if accel else 0.0
            except Exception:
                evidence["imu_jerk"] = 0.0

        # OBD throttle drop
        if obd and hasattr(obd, "get_throttle_position"):
            try:
                evidence["obd_throttle"] = obd.get_throttle_position() or 0.0
            except Exception:
                evidence["obd_throttle"] = 0.0

        # Audio evidence
        if audio_label:
            evidence["audio"] = 1.0 if audio_label in ("crash", "collision") else 0.0

        decision = decision_engine.evaluate(evidence)
        if decision and getattr(decision, "severity", "info") in ("critical", "warning"):
            return {
                "event_type": getattr(decision, "event_type", "unknown"),
                "confidence": getattr(decision, "confidence", 0.0),
                "severity": getattr(decision, "severity", "info"),
            }
        return None
    except Exception as exc:
        logger.debug(f"Crash check skipped: {exc}")
        return None


def handle_crash_alert(
    decision: Dict[str, Any],
    modules: Dict[str, Any],
    camera: Any,
    timestamp: float,
) -> None:
    """Handle crash alert: capture image, run cloud vision, send alerts."""
    event_type = decision.get("event_type", "crash")
    confidence = decision.get("confidence", 0.0)
    severity = decision.get("severity", "critical")

    logger.info(
        f"🚨 {event_type.upper()} DETECTED | "
        f"confidence={confidence:.2f} | severity={severity}"
    )

    # 1. Buzzer alert
    gpio = modules.get("gpio")
    if gpio and hasattr(gpio, "buzzer_beep"):
        try:
            gpio.buzzer_beep(pattern=[0.2, 0.1, 0.2, 0.1, 0.2], frequency=1000)
        except Exception as exc:
            logger.debug(f"Buzzer failed: {exc}")

    # 2. Camera burst capture
    image_path: Optional[str] = None
    if camera and hasattr(camera, "capture_burst"):
        try:
            images_dir = _VISTA_ROOT / "data" / "images"
            images_dir.mkdir(parents=True, exist_ok=True)
            burst = camera.capture_burst(count=5, interval_ms=100)
            for i, img in enumerate(burst):
                path = images_dir / f"crash_{int(timestamp)}_{i:02d}.jpg"
                path.write_bytes(img)
            image_path = str(images_dir / f"crash_{int(timestamp)}_00.jpg")
            logger.info(f"Burst captured: {len(burst)} frames")
        except Exception as exc:
            logger.error(f"Burst capture failed: {exc}")

    # 3. Cloud Vision analysis
    cloud_vision = modules.get("cloud_vision")
    if cloud_vision and image_path:
        try:
            analysis = cloud_vision.analyze(image_path)
            logger.info(f"Cloud Vision: {analysis}")
        except Exception as exc:
            logger.error(f"Cloud Vision failed: {exc}")

    # 4. Alert routing
    alert = modules.get("alert")
    if alert and hasattr(alert, "send_alert"):
        try:
            location: Optional[Dict[str, float]] = None
            alert.send_alert(
                event_type=event_type,
                confidence=confidence,
                severity=severity,
                location=location,
                image_path=image_path,
            )
        except Exception as exc:
            logger.error(f"Alert send failed: {exc}")


# ══════════════════════════════════════════════════════════════════════
# Mode: Driving
# ══════════════════════════════════════════════════════════════════════

def run_driving_mode(cfg: Dict[str, Any], modules: Dict[str, Any]) -> None:
    """Main driving loop: poll sensors, classify audio, check crash, write telemetry."""
    logger.info("=" * 60)
    logger.info("VISTA — DRIVING MODE ACTIVE")
    logger.info(f"Device: {cfg.get('device', {}).get('name', 'Unknown')}")
    logger.info("=" * 60)

    obd = modules.get("obd")
    poll_interval = cfg.get("sensors", {}).get("obd", {}).get("poll_interval", 0.1)

    last_audio_time = 0.0
    audio_interval = 1.0  # Classify audio every 1 second
    last_vision_time = 0.0
    vision_interval = 300.0  # Camera + vision every 5 minutes

    iteration = 0

    while state.is_running():
        tick_start = time.monotonic()
        now = time.time()

        # ── Poll OBD + IMU ──────────────────────────────────────────
        write_telemetry_point(obd, modules.get("imu"), modules, now)

        # ── Audio classification every 1s ───────────────────────────
        audio_label: Optional[str] = None
        if now - last_audio_time >= audio_interval:
            audio_label = run_audio_classification(modules, now)
            last_audio_time = now

        # ── EKF fusion (if available) ───────────────────────────────
        fusion = modules.get("fusion")
        if fusion and hasattr(fusion, "update"):
            try:
                imu = modules.get("imu")
                accel = None
                if imu and hasattr(imu, "get_all"):
                    imu_data = imu.get_all()
                    accel = imu_data.get("accel")
                if accel:
                    fusion.update(accel, now)
            except Exception as exc:
                logger.debug(f"Fusion update skipped: {exc}")

        # ── Crash check ─────────────────────────────────────────────
        crash = check_crash_conditions(modules, obd, audio_label)
        if crash:
            camera = modules.get("camera")
            handle_crash_alert(crash, modules, camera, now)

        # ── Periodic camera + vision ────────────────────────────────
        if now - last_vision_time >= vision_interval:
            camera = modules.get("camera")
            cloud_vision = modules.get("cloud_vision")
            if camera and hasattr(camera, "capture_jpeg"):
                try:
                    frame = camera.capture_jpeg()
                    if cloud_vision and hasattr(cloud_vision, "analyze"):
                        try:
                            analysis = cloud_vision.analyze(frame)
                            logger.debug(f"Periodic vision: {analysis}")
                        except Exception as exc:
                            logger.debug(f"Vision analysis skipped: {exc}")
                except Exception as exc:
                    logger.debug(f"Periodic capture skipped: {exc}")
            last_vision_time = now

        iteration += 1
        if iteration % 100 == 0:
            logger.debug(f"Main loop iteration {iteration} | running OK")

        # ── Sleep to maintain poll rate ─────────────────────────────
        elapsed = time.monotonic() - tick_start
        sleep_time = max(0.0, poll_interval - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

    logger.info("Driving loop exited")


# ══════════════════════════════════════════════════════════════════════
# Mode: Parked
# ══════════════════════════════════════════════════════════════════════

def run_parked_mode(cfg: Dict[str, Any], modules: Dict[str, Any]) -> None:
    """Parked mode: hand off monitoring to ESP32, sleep the Raspberry Pi."""
    logger.info("=" * 60)
    logger.info("VISTA — PARKED MODE")
    logger.info("Handing off to ESP32 for PIR-based monitoring")
    logger.info("=" * 60)

    # Wake ESP32 to begin monitoring
    gpio = modules.get("gpio")
    if gpio and hasattr(gpio, "wake_esp32"):
        try:
            gpio.wake_esp32(pulse_duration=0.1)
            logger.info("ESP32 woken — PIR monitoring active")
        except Exception as exc:
            logger.error(f"Failed to wake ESP32: {exc}")

    # ESP32 will handle PIR monitoring. Pi goes to sleep.
    logger.info("Raspberry Pi entering low-power state...")
    logger.info("ESP32 will WAKE Pi via GPIO when motion detected")

    # In demo mode, just loop waiting for shutdown
    if is_demo_mode():
        logger.info("Demo parked mode — press Ctrl+C to exit")
        while state.is_running():
            time.sleep(1.0)
    else:
        # Real parked mode: systemd should stop the service
        # The ESP32 will pull WAKE GPIO high to restart Pi
        logger.info("Shutting down for park...")
        state.shutdown()


# ══════════════════════════════════════════════════════════════════════
# Mode: Demo
# ══════════════════════════════════════════════════════════════════════

def run_demo_mode(cfg: Dict[str, Any], modules: Dict[str, Any]) -> None:
    """Demo mode: run with simulated data for classroom demonstrations."""
    scenario = state.demo_scenario
    logger.info("=" * 60)
    logger.info(f"VISTA — DEMO MODE ({scenario})")
    logger.info("Using simulated sensor data — no hardware required")
    logger.info("=" * 60)

    # Run the demo orchestrator if available
    try:
        from demo.demo_orchestrator import run_demo

        run_demo(scenario, modules)
        return
    except ImportError:
        logger.warning("Demo orchestrator not found — running basic demo loop")

    # Fallback: basic demo loop
    logger.info("Demo loop running — press Ctrl+C to exit")
    iteration = 0

    while state.is_running():
        now = time.time()

        # Simulated telemetry
        import math

        sim_speed = 45 + 10 * math.sin(now * 0.5)
        sim_rpm = 1800 + 400 * math.sin(now * 0.5)

        logger.debug(
            f"[DEMO] speed={sim_speed:.1f} km/h | "
            f"rpm={sim_rpm:.0f} | mode={scenario}"
        )

        # Every 10 seconds show demo status
        iteration += 1
        if iteration % 100 == 0:
            logger.info(
                f"[DEMO] System Normal | speed={sim_speed:.1f} km/h | "
                f"rpm={sim_rpm:.0f}"
            )

        time.sleep(0.1)

    logger.info("Demo loop exited")


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="VISTA — Vehicle Intelligence & Safety Telematics Architecture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --mode driving
  python main.py --mode demo --demo-scenario crash
  python main.py --mode parked
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["driving", "parked", "demo"],
        default="driving",
        help="Operating mode (default: driving)",
    )
    parser.add_argument(
        "--demo-scenario",
        choices=["normal", "crash", "theft"],
        default="normal",
        help="Demo scenario when mode=demo (default: normal)",
    )
    return parser.parse_args()


def main() -> None:
    """Initialize system and run the selected mode."""
    args = parse_args()

    logger.info("╔══════════════════════════════════════════════════════════╗")
    logger.info("║   VISTA — Vehicle Intelligence & Safety Telematics      ║")
    logger.info("╚══════════════════════════════════════════════════════════╝")

    cfg = load_config()
    state.mode = args.mode
    state.demo_scenario = args.demo_scenario

    # If mode is "demo", force demo mode
    if args.mode == "demo":
        os.environ["DEMO_MODE"] = "true"
        logger.info("Demo mode forced via --mode demo")

    # ── Phase 1: Initialize HAL ────────────────────────────────────
    logger.info("Phase 1/5: Initializing Hardware Abstraction Layer...")
    modules = init_hal(cfg)

    # ── Phase 2: Initialize Intelligence ───────────────────────────
    logger.info("Phase 2/5: Initializing Intelligence Engine...")
    intel_modules = init_intelligence(cfg)
    modules.update(intel_modules)

    # ── Phase 3: Initialize Data Layer ─────────────────────────────
    logger.info("Phase 3/5: Initializing Data Storage...")
    # Ensure data directories exist
    data_dir = _VISTA_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    images_dir = data_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = _VISTA_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Data directories ready")

    # ── Phase 4: Initialize Communication ──────────────────────────
    logger.info("Phase 4/5: Initializing Communication Layer...")
    comm_modules = init_communication(cfg)
    modules.update(comm_modules)

    # ── Phase 5: Initialize Dashboard ──────────────────────────────
    logger.info("Phase 5/5: Initializing Dashboard...")
    dash = init_dashboard(cfg)
    if dash:
        modules["dashboard"] = dash

    logger.info(
        f"System initialized | mode={state.mode} | "
        f"modules_loaded={len(modules)}"
    )

    # ── Run selected mode ──────────────────────────────────────────
    try:
        if state.mode == "driving":
            run_driving_mode(cfg, modules)
        elif state.mode == "parked":
            run_parked_mode(cfg, modules)
        elif state.mode == "demo":
            run_demo_mode(cfg, modules)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        shutdown_all(modules)


def shutdown_all(modules: Dict[str, Any]) -> None:
    """Gracefully stop all modules in reverse dependency order."""
    logger.info("Initiating graceful shutdown of all modules...")

    # 1. Dashboard
    if DASH_AVAILABLE and dash_stop:
        try:
            dash_stop()
            logger.info("Dashboard stopped")
        except Exception as exc:
            logger.warning(f"Dashboard stop failed: {exc}")

    # 2. Communication
    for name in ("alert", "ble", "mqtt"):
        mod = modules.get(name)
        if mod and hasattr(mod, "stop"):
            try:
                mod.stop()
                logger.info(f"{name} stopped")
            except Exception as exc:
                logger.warning(f"{name} stop failed: {exc}")

    # 3. Intelligence
    for name in ("cloud_vision", "decision_engine", "audio_classifier", "fusion"):
        mod = modules.get(name)
        if mod and hasattr(mod, "stop"):
            try:
                mod.stop()
                logger.info(f"{name} stopped")
            except Exception as exc:
                logger.warning(f"{name} stop failed: {exc}")

    # 4. HAL
    for name in ("gpio", "camera", "audio", "imu", "obd"):
        mod = modules.get(name)
        if mod and hasattr(mod, "stop"):
            try:
                mod.stop()
                logger.info(f"{name} stopped")
            except Exception as exc:
                logger.warning(f"{name} stop failed: {exc}")

    # 5. Flush any remaining data
    logger.info("All modules stopped. Data flushed.")
    logger.info("VISTA shutdown complete.")


if __name__ == "__main__":
    main()
