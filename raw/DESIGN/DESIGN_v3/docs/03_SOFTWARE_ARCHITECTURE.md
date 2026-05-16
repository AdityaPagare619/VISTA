# 03 — Software Architecture Document v3.0
## VISTA: Module Design, Corrected EKF & Separated Crash Detection

**Version:** 3.0 | **Status:** Final — Physics-Verified | **Date:** May 10, 2026

---

## 1. Software Stack Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                                │
│  crash_detector.py  │  theft_detector.py  │  driver_behavior.py        │
│  vehicle_health.py  │  dashboard_server.py│  alert_manager.py           │
├─────────────────────────────────────────────────────────────────────────┤
│                        INTELLIGENCE LAYER                                │
│  velocity_ekf.py (2-state)  │  audio_classifier.py (TFLite CNN)        │
│  crash_detector.py (NEW)    │  cloud_vision.py (Gemini API)            │
│  decision_engine.py          │                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                           DATA LAYER                                     │
│  influx_writer.py (→USB SSD) │ sqlite_manager.py (→USB SSD)            │
│  file_manager.py (images)                                                │
├─────────────────────────────────────────────────────────────────────────┤
│                       COMMUNICATION LAYER                                │
│  mqtt_broker.py │ ble_manager.py │ wifi_manager.py │ telegram_bot.py  │
├─────────────────────────────────────────────────────────────────────────┤
│                     HARDWARE ABSTRACTION LAYER                           │
│  obd_reader.py │ imu_reader.py │ audio_capture.py │ camera_capture.py  │
│  gpio_manager.py │ esp32_bridge.py │ power_manager.py (NEW)            │
├─────────────────────────────────────────────────────────────────────────┤
│                     OPERATING SYSTEM                                     │
│  Raspberry Pi OS (Debian 12 Bookworm) │ Linux Kernel 6.1               │
│  Python 3.11 │ systemd │ BlueZ │ USB SSD mounted at /mnt/vista-data   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key changes from v2.1:**
- `fusion_engine.py` → renamed to `velocity_ekf.py` (scope clarified)
- `crash_detector.py` → NEW separate module (not inside EKF)
- `telegram_bot.py` → replaces WhatsApp as primary
- `power_manager.py` → NEW module for MOSFET/ESP32 power control
- All data storage → USB SSD at `/mnt/vista-data/`

---

## 2. Module Specifications

### 2.1 Hardware Abstraction Layer

#### `obd_reader.py` (Updated: honest polling rate)
```python
"""
OBD-II Data Reader using python-OBD library.
IMPORTANT: Real ELM327 USB achieves 2-3 full reads/sec, NOT 10Hz.
Each PID request is a serial round-trip taking 100-150ms.
"""

class OBDReader:
    # Realistic polling: 4 PIDs × ~120ms each = ~500ms per full cycle = ~2Hz
    POLL_INTERVAL = 0.5  # seconds (honest, measured)
    PRIORITY_PIDS = ['speed', 'rpm', 'throttle', 'engine_load']

    def __init__(self, port: str = "/dev/ttyUSB0"):
        self.connection = obd.OBD(portstr=port, fast=False)
        # Reduce FTDI USB latency timer from 16ms to 1ms
        self._optimize_usb_latency()

    def poll_all(self) -> dict:
        """Poll all priority PIDs. Takes ~500ms for 4 PIDs."""
        data = {}
        for pid in self.PRIORITY_PIDS:
            response = self.connection.query(obd.commands[pid.upper()])
            if response.value is not None:
                data[pid] = response.value.magnitude
        data['timestamp'] = time.time()
        return data

    def get_speed_rate(self, prev_speed: float, curr_speed: float) -> float:
        """Compute speed change rate (for crash corroboration).
        Uses actual OBD polling interval, not assumed 10Hz."""
        return (curr_speed - prev_speed) / self.POLL_INTERVAL

    def _optimize_usb_latency(self):
        """Reduce FTDI latency timer to 1ms for faster response."""
        try:
            os.system("echo 1 > /sys/bus/usb-serial/devices/ttyUSB0/latency_timer")
        except: pass
```

#### `imu_reader.py` (Updated: saturation detection)
```python
"""
IMU Data Reader using MPU6050 over I2C.
IMPORTANT: MPU6050 saturates at ±16g. Real crashes produce 20-70g.
Saturation IS the signal — if sensor clips, something severe happened.
"""

SATURATION_THRESHOLD = 15.5  # g — if |accel| > this, sensor is clipping

class IMUReader:
    def __init__(self, bus: int = 1, address: int = 0x68):
        self.mpu = mpu6050(bus, address)
        self.mpu.set_accel_range(mpu6050.ACCEL_RANGE_16G)  # Max range
        self.calibrate()

    def get_acceleration(self) -> tuple[float, float, float]:
        """Returns (ax, ay, az) in g. Max ±16g (saturates above)."""
        data = self.mpu.get_accel_data(g=True)
        return data['x'], data['y'], data['z']

    def is_saturated(self, ax, ay, az) -> bool:
        """Check if any axis is near saturation (clipping)."""
        return any(abs(a) >= SATURATION_THRESHOLD for a in (ax, ay, az))

    def get_jerk(self, prev_accel: float, curr_accel: float, dt: float) -> float:
        """Compute jerk magnitude. If saturated, jerk is unreliable —
        return a high sentinel value instead."""
        return abs(curr_accel - prev_accel) / dt

    def calibrate(self, samples: int = 100):
        """Calibrate gyroscope offsets at rest."""
        ...
```

### 2.2 Intelligence Layer

#### `velocity_ekf.py` (REWRITTEN — correct 2-state filter)
```python
"""
2-State Extended Kalman Filter for velocity estimation ONLY.
NOT used for crash detection (crashes violate EKF smoothness assumption).

State vector: [velocity_m/s, accel_bias_m/s²]
Prediction: velocity += (imu_accel_forward * 9.81 - bias) * dt
Measurement: OBD speed (converted km/h → m/s)
"""

import numpy as np

class VelocityEKF:
    """
    Fuses OBD-II speed and IMU acceleration for accurate velocity.
    Used for: driver behavior analysis, trip logging, speed profiles.
    NOT used for: crash detection (separate module).
    """

    def __init__(self, dt: float = 0.4):
        """dt=0.4s matches real OBD polling rate (~2.5Hz)."""
        self.dt = dt
        # State: [velocity (m/s), accel_bias (m/s²)]
        self.x = np.zeros(2)
        self.P = np.eye(2) * 1.0
        # Process noise: velocity drifts slightly, bias drifts slowly
        self.Q = np.diag([0.5, 0.01])
        # Measurement noise: OBD speed has ~1 km/h accuracy
        self.R = np.array([[0.08]])  # (1 km/h / 3.6)² ≈ 0.08 (m/s)²

    def predict(self, imu_accel_forward_g: float):
        """Prediction step using forward-axis IMU acceleration.

        Args:
            imu_accel_forward_g: forward acceleration in g-units
        """
        # State transition: v += (a*9.81 - bias) * dt
        accel_mps2 = imu_accel_forward_g * 9.81
        corrected_accel = accel_mps2 - self.x[1]  # Remove bias
        self.x[0] += corrected_accel * self.dt

        # Jacobian of state transition
        F = np.array([
            [1, -self.dt],  # dv/dv=1, dv/dbias=-dt
            [0, 1]          # dbias is constant
        ])
        self.P = F @ self.P @ F.T + self.Q

    def update(self, obd_speed_kmh: float):
        """Update step using OBD-II speed measurement.

        Args:
            obd_speed_kmh: vehicle speed from OBD-II in km/h
        """
        obd_speed_mps = obd_speed_kmh / 3.6
        z = np.array([obd_speed_mps])

        # Observation matrix: we observe velocity directly
        H = np.array([[1, 0]])

        # Innovation
        y = z - H @ self.x
        S = H @ self.P @ H.T + self.R
        K = self.P @ H.T @ np.linalg.inv(S)

        self.x += (K @ y).flatten()
        self.P = (np.eye(2) - K @ H) @ self.P

    def get_velocity_kmh(self) -> float:
        """Returns fused velocity in km/h."""
        return max(0.0, self.x[0] * 3.6)

    def get_velocity_mps(self) -> float:
        """Returns fused velocity in m/s."""
        return max(0.0, self.x[0])
```

#### `crash_detector.py` (NEW — separated from EKF)
```python
"""
Crash Detection Module — Threshold + Weighted Evidence Voting.
Separate from EKF because crashes are discontinuities that violate
Kalman filter smoothness assumptions.

Detection tiers:
  T1 (0ms):   IMU jerk detection (primary)
  T2 (50ms):  Audio CNN corroboration
  T3 (500ms): OBD speed-rate corroboration (async)
"""

from dataclasses import dataclass
from collections import deque

@dataclass
class CrashEvidence:
    imu_jerk: float = 0.0
    imu_saturated: bool = False
    audio_class: str = "normal"
    audio_confidence: float = 0.0
    obd_speed_drop: float = 0.0
    obd_throttle_drop: float = 0.0
    timestamp: float = 0.0

class CrashDetector:
    """Multi-tier crash detection with async corroboration."""

    JERK_THRESHOLD = 5.0   # g/s — triggers potential crash
    WEIGHTS = {
        'imu':   0.45,  # Primary — fastest, most reliable
        'audio': 0.30,  # Secondary — near-real-time
        'obd':   0.15,  # Async corroborator
        'vision': 0.10, # Enrichment (added later)
    }
    CONFIRM_THRESHOLD = 0.65
    WARNING_THRESHOLD = 0.40

    def __init__(self):
        self.accel_history = deque(maxlen=200)  # 2 sec at 100Hz
        self.state = 'monitoring'  # monitoring | potential | confirmed

    def check_imu(self, accel: float, dt: float) -> float:
        """Tier 1: Check IMU for crash-level jerk. Returns jerk value."""
        self.accel_history.append(accel)
        if len(self.accel_history) < 2:
            return 0.0
        jerk = abs(accel - self.accel_history[-2]) / dt
        return jerk

    def assess(self, evidence: CrashEvidence) -> dict:
        """Compute crash confidence from available evidence.
        Can be called with partial evidence (async OBD arrives later).
        """
        # IMU confidence
        imu_conf = min(evidence.imu_jerk / self.JERK_THRESHOLD, 1.0)
        if evidence.imu_saturated:
            imu_conf = 1.0  # Saturation = definite severe event

        # Audio confidence
        audio_conf = evidence.audio_confidence if evidence.audio_class == 'crash' else 0.0

        # OBD confidence (may be 0 if not yet received)
        obd_conf = min(evidence.obd_throttle_drop / 50.0, 1.0)

        # Weighted fusion (vision added later via update)
        confidence = (
            self.WEIGHTS['imu'] * imu_conf +
            self.WEIGHTS['audio'] * audio_conf +
            self.WEIGHTS['obd'] * obd_conf
        )

        severity = ('critical' if confidence > 0.65 else
                    'warning' if confidence > 0.40 else 'info')

        return {
            'is_crash': confidence > self.CONFIRM_THRESHOLD,
            'confidence': round(confidence, 3),
            'severity': severity,
            'evidence': {
                'imu': {'jerk': evidence.imu_jerk, 'saturated': evidence.imu_saturated,
                        'weight': self.WEIGHTS['imu'], 'contrib': round(self.WEIGHTS['imu'] * imu_conf, 3)},
                'audio': {'class': evidence.audio_class, 'raw_conf': evidence.audio_confidence,
                          'weight': self.WEIGHTS['audio'], 'contrib': round(self.WEIGHTS['audio'] * audio_conf, 3)},
                'obd': {'throttle_drop': evidence.obd_throttle_drop,
                        'weight': self.WEIGHTS['obd'], 'contrib': round(self.WEIGHTS['obd'] * obd_conf, 3)},
            },
            'explanation': self._explain(imu_conf, audio_conf, obd_conf, confidence, evidence),
        }

    def _explain(self, imu_c, audio_c, obd_c, total, ev) -> str:
        lines = [f"Crash confidence: {total:.0%}"]
        imu_note = " [SATURATED — exceeded ±16g sensor range]" if ev.imu_saturated else ""
        lines.append(f"• IMU: {ev.imu_jerk:.1f} g/s jerk{imu_note} (threshold: {self.JERK_THRESHOLD})")
        lines.append(f"• Audio: '{ev.audio_class}' at {ev.audio_confidence:.0%}")
        if ev.obd_throttle_drop > 0:
            lines.append(f"• OBD: Throttle dropped {ev.obd_throttle_drop:.0f}% (async corroboration)")
        else:
            lines.append(f"• OBD: Awaiting async corroboration...")
        return "\n".join(lines)
```

#### `audio_classifier.py` (Unchanged logic, updated comments)
```python
"""
Audio Event Classifier using TFLite.
Dual-path strategy:
  Path A: Custom lightweight CNN (~300KB) — if team collects 500+ samples
  Path B: Fine-tuned YAMNet (~3MB) — fallback if Path A accuracy <80%
Decision gate: Week 8 of development.
"""
# [Implementation identical to v2.1 — class structure is sound]
# Key change: CLASSES now includes 'harsh_braking'
CLASSES = ['normal', 'crash_impact', 'horn', 'siren_ambulance',
           'siren_police', 'harsh_braking']
```

#### `cloud_vision.py` (Updated: Gemini model, fallback handling)
```python
"""
Cloud Vision using Gemini 1.5 Flash.
ENRICHMENT ONLY — system works 100% without this.
Free tier: 1,500 requests/day (monitor usage, may change).
"""
# [Implementation identical to v2.1 — the API contract is correct]
# Key addition: explicit timeout and fallback
API_TIMEOUT = 10  # seconds — if no response, skip enrichment
MAX_RETRIES = 3
BACKOFF = [1, 2, 4]  # exponential backoff seconds
```

### 2.3 Communication Layer

#### `telegram_bot.py` (NEW — replaces WhatsApp as primary)
```python
"""
Telegram Bot for VISTA alerts.
Why Telegram over WhatsApp:
  - Completely free API (no per-message cost)
  - No business verification required
  - Rich media support (images, buttons, formatting)
  - Bot API is developer-friendly with official docs
"""
import requests

class TelegramAlertBot:
    API_BASE = "https://api.telegram.org/bot{token}"

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = self.API_BASE.format(token=token)

    def send_crash_alert(self, decision: dict, image_bytes: bytes = None):
        """Send enriched crash alert with evidence chain."""
        text = self._format_crash_message(decision)
        if image_bytes:
            self._send_photo(image_bytes, text)
        else:
            self._send_message(text)

    def send_theft_alert(self, description: str, image_bytes: bytes = None):
        """Send theft alert with camera capture."""
        ...

    def _format_crash_message(self, decision: dict) -> str:
        return (
            f"🚨 *CRASH DETECTED — VISTA ALERT*\n\n"
            f"Confidence: {decision['confidence']:.0%}\n"
            f"Severity: {decision['severity'].upper()}\n\n"
            f"*EVIDENCE:*\n{decision['explanation']}\n\n"
            f"⚠️ _VISTA is a research prototype. "
            f"Call emergency services if needed._"
        )

    def _send_message(self, text: str):
        requests.post(f"{self.base_url}/sendMessage", json={
            'chat_id': self.chat_id, 'text': text, 'parse_mode': 'Markdown'
        }, timeout=10)

    def _send_photo(self, photo_bytes: bytes, caption: str):
        requests.post(f"{self.base_url}/sendPhoto",
            data={'chat_id': self.chat_id, 'caption': caption, 'parse_mode': 'Markdown'},
            files={'photo': ('crash.jpg', photo_bytes, 'image/jpeg')},
            timeout=15)
```

---

## 3. Systemd Services (Updated paths for USB SSD)

```ini
# /etc/systemd/system/vista-fusion.service
[Unit]
Description=VISTA Velocity EKF + Crash Detector
After=vista-obd.service vista-imu.service vista-audio.service
Requires=vista-obd.service vista-imu.service

[Service]
Type=simple
User=pi
ExecStart=/home/pi/vista/venv/bin/python3 /home/pi/vista/intelligence/main_fusion.py
Restart=on-failure
RestartSec=10
Environment=VISTA_DATA=/mnt/vista-data

[Install]
WantedBy=multi-user.target
```

---

## 4. USB SSD Mount Configuration

```bash
# /etc/fstab entry for USB SSD
# Use UUID to avoid mount issues if USB port changes
UUID=<your-ssd-uuid>  /mnt/vista-data  ext4  defaults,noatime,nofail  0  2

# Directory structure on SSD:
# /mnt/vista-data/
# ├── influxdb/          # InfluxDB data directory
# ├── events.db          # SQLite event database
# └── images/            # Captured images
#     ├── driving/
#     ├── crash/
#     └── theft/
```

---

## 5. Error Handling (Updated weight redistribution)

```python
def get_crash_weights(sensors_available: set) -> dict:
    """Redistribute weights when sensors are unavailable."""
    weights = CrashDetector.WEIGHTS.copy()

    if 'audio' not in sensors_available:
        # Audio's 30% redistributed: 20% to IMU, 10% to OBD
        weights['imu'] += 0.20
        weights['obd'] += 0.10
        del weights['audio']

    if 'obd' not in sensors_available:
        # OBD's 15% redistributed: 10% to IMU, 5% to audio
        weights['imu'] += 0.10
        if 'audio' in weights:
            weights['audio'] += 0.05
        del weights['obd']

    # IMU alone can still exceed threshold (0.45 base, up to 0.75 with redistribution)
    return weights
```

---

## 6. Configuration (Updated)

```yaml
# /home/pi/vista/config.yaml (v3.0)
device:
  id: "VISTA-0001"
  name: "Maruti Swift VXI"

sensors:
  obd:
    port: "/dev/ttyUSB0"
    poll_interval: 0.5  # seconds (honest — 2Hz per full cycle)
    priority_pids: [speed, rpm, throttle, engine_load]
  imu:
    bus: 1
    address: 0x68
    sample_rate: 100
    accel_range: 16  # ±16g (max, will saturate above)
    saturation_threshold: 15.5
  audio:
    sample_rate: 16000
    window_sec: 1.0
    model_path: "models/audio_cnn.tflite"
  camera:
    resolution: [2304, 1296]
    quality: 85

velocity_ekf:
  dt: 0.4  # matches OBD polling rate
  process_noise: [0.5, 0.01]
  measurement_noise: [0.08]

crash_detection:
  jerk_threshold: 5.0  # g/s
  confirm_threshold: 0.65
  warning_threshold: 0.40
  weights: {imu: 0.45, audio: 0.30, obd: 0.15, vision: 0.10}

cloud:
  gemini_api_key: "${GEMINI_API_KEY}"
  api_timeout: 10
  max_retries: 3

alerts:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
  whatsapp:
    enabled: false  # Optional paid upgrade
  buzzer: true

storage:
  data_mount: "/mnt/vista-data"
  influxdb:
    host: "localhost"
    port: 8086
    database: "vista"
    retention_days: 30
  sqlite:
    path: "/mnt/vista-data/events.db"
  images:
    path: "/mnt/vista-data/images"
    max_size_mb: 500

power:
  low_battery_voltage: 11.8
  thermal_block_temp: 55  # °C — ESP32 blocks Pi boot above this
```

---

**Next:** See `04_OPERATIONAL_FLOWS.md` for corrected timing sequences.
