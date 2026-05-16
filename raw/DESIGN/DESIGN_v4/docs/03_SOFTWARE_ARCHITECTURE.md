# 03 — Software Architecture Document v4.0
## VISTA: Package Structure, Module APIs & Data Contracts

**Version:** 4.0 | **Status:** Built & Verified | **Date:** May 16, 2026

---

## 1. Repository Structure

```
VISO-PROJECT/
├── README.md                          ← Project overview (system-focused)
├── TEAM_INSTRUCTIONS.md               ← Team roles and timeline
├── pyproject.toml                     ← pytest config, pythonpath
├── .gitignore
│
├── .github/
│   └── workflows/
│       └── ci.yml                     ← GitHub Actions: 4 jobs
│
├── scripts/                           ← Operational scripts
│   ├── deploy.sh                      ← 6-phase Pi deployment script
│   ├── demo_billion_dollar_architecture.py  ← SITL demo runner
│   ├── validate_pipeline.py           ← Full pipeline validation
│   ├── verify_yamnet.py               ← YAMNet model verification
│   ├── train_audio_classifier.py      ← Custom model training
│   └── setup_ml.py                    ← ML environment setup
│
├── src/vista/                         ← Main codebase (13 packages)
│   ├── main.py                        ← Entry point, 5-phase init
│   ├── config.yaml                    ← All system configuration
│   ├── config_module.py               ← Centralized config loader
│   ├── requirements.txt               ← Python dependencies
│   ├── .env.example                   ← API key template
│   ├── demo_live.py                   ← Live demo with simulated data
│   ├── demo_data.py                   ← Demo data generators
│   ├── run_dashboard.py               ← Dashboard standalone launcher
│   │
│   ├── hal/                           ← Hardware Abstraction Layer
│   │   ├── __init__.py                ← Exports all 6 drivers
│   │   ├── obd_reader.py              ← ELM327, python-obd, 2Hz
│   │   ├── imu_reader.py              ← MPU6050, I2C, 100Hz
│   │   ├── audio_capture.py           ← PyAudio, 16kHz mono
│   │   ├── camera_capture.py          ← libcamera, Pi Camera v3
│   │   ├── gpio_manager.py            ← RPi.GPIO, buzzer, heartbeat
│   │   └── power_manager.py           ← MOSFET control, boot sequence
│   │
│   ├── intelligence/                  ← AI/ML Pipeline (9 modules)
│   │   ├── __init__.py                ← Exports primary modules
│   │   ├── velocity_ekf.py            ← 2-state Kalman filter
│   │   ├── crash_detector.py          ← 4-tier signature detection
│   │   ├── audio_classifier.py        ← YAMNet TFLite, 521→6 classes
│   │   ├── decision_engine.py         ← Weighted confidence, explainable
│   │   ├── cloud_vision.py            ← Gemini 1.5-flash REST client
│   │   ├── theft_detector.py          ← Ghost Key TSA, 4-layer
│   │   ├── predictive_analytics.py    ← NVH FFT + Gemini mechanic report
│   │   ├── health_monitor.py          ← CPU/RAM/temp + sensor liveness
│   │   └── fusion_engine.py           ← (Legacy — superseded by EKF)
│   │
│   ├── communication/                 ← Alert and data channels
│   │   ├── __init__.py                ← Exports AlertManager, Decision
│   │   ├── alert_manager.py           ← Severity-based routing
│   │   ├── telegram_bot.py            ← TelegramAlertBot, raw REST
│   │   ├── mqtt_manager.py            ← paho-mqtt, localhost:1883
│   │   └── ble_manager.py             ← bleak BLE, VISTA-0001 advertising
│   │
│   ├── data/                          ← Persistent storage
│   │   ├── __init__.py                ← Exports SQLiteManager, InfluxWriter
│   │   ├── sqlite_manager.py          ← Events DB, WAL mode, thread-safe
│   │   └── influx_writer.py           ← Time-series telemetry (singleton)
│   │
│   ├── dashboard/                     ← Web UI
│   │   ├── __init__.py
│   │   ├── app.py                     ← Flask-SocketIO, 5Hz push
│   │   ├── static/
│   │   │   ├── styles.css             ← Premium design system
│   │   │   └── dashboard.js           ← Chart.js, animations, socket
│   │   └── templates/
│   │       └── index.html             ← 6-metric strip, arch flow
│   │
│   ├── demo/                          ← Demo tooling
│   │   ├── demo_orchestrator.py       ← Full SITL orchestration
│   │   └── obd_simulator.py           ← Realistic OBD data simulation
│   │
│   ├── esp32/                         ← Coprocessor firmware (C)
│   │   ├── main/main.c                ← 1,098 LOC, 4-state machine
│   │   ├── CMakeLists.txt             ← ESP-IDF build config
│   │   └── sdkconfig.defaults         ← BLE + deep sleep settings
│   │
│   ├── models/                        ← ML artifacts
│   │   ├── yamnet.tflite              ← 4,126,810 bytes — real model
│   │   ├── yamnet_class_map.csv       ← 521 class labels
│   │   └── mel_config.json            ← Mel spectrogram config
│   │
│   ├── tests/                         ← Test suite
│   │   ├── test_v3_quick.py           ← 20 tests, all passing
│   │   ├── test_v3_comprehensive.py   ← Extended test suite
│   │   ├── test_intelligence_quick.py ← Intelligence module tests
│   │   └── test_audio.py              ← Audio classifier tests
│   │
│   ├── services/                      ← systemd units
│   │   ├── vista.service              ← Main intelligence loop
│   │   └── vista-dashboard.service    ← Web UI service
│   │
│   └── scripts/
│       └── install.sh                 ← Legacy install script
│
└── raw/
    ├── RESEARCH/                      ← Background research
    └── DESIGN/
        ├── DESIGN_v3/                 ← V3 docs (preserved, not modified)
        └── DESIGN_v4/                 ← V4 docs (this document)
```

---

## 2. Configuration Hierarchy

All configuration flows from one source of truth:

```
config.yaml          ← Primary: all thresholds, pins, rates
    ↓
.env                 ← Secrets: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN
    ↓
config_module.py     ← Central loader: load_config(), _is_demo_mode()
    ↓
main.py → init_*()  ← Passes cfg dict to each module
    ↓
Each module          ← Reads its own section (e.g., cfg["sensors"]["imu"])
```

**Key config sections:**

| Section | File Path | Controls |
|---|---|---|
| `sensors.obd` | config.yaml:11 | Port, baud, poll rate |
| `sensors.imu` | config.yaml:25 | Bus, address, range |
| `crash_detection` | config.yaml:62 | Thresholds, weights |
| `cloud.vision` | config.yaml:100 | Gemini model, retries |
| `cloud.alerts.telegram` | config.yaml:108 | Token env var, chat ID |
| `storage.sqlite` | config.yaml:152 | DB path, SSD vs local |
| `power` | config.yaml:175 | GPIO pins, voltage thresholds |

---

## 3. Module Interface Specifications

### 3.1 HAL — Hardware Abstraction Layer

All HAL drivers follow the **graceful degradation pattern**:
1. Try real hardware import → if `ImportError`, switch to demo mode
2. Try hardware init → if fails, switch to demo mode
3. System NEVER crashes due to missing hardware

```python
# OBDReader
obd = OBDReader()
speed = obd.get_speed()        # float km/h, or 0.0 in demo
rpm   = obd.get_rpm()          # float RPM
throttle = obd.get_throttle_position()  # float %

# IMUReader
imu = IMUReader()
data = imu.get_all()
# Returns: {"accel": (x,y,z), "gyro": (x,y,z), "temp": float}
# accel in g-force, gyro in °/s

# AudioCapture
audio = AudioCapture()
audio.start_capture_thread()
segment = audio.get_audio_segment(seconds=1.0)
# Returns: numpy array, 16000 samples/sec, float32

# CameraCapture
cam = CameraCapture()
path = cam.capture_image()     # Returns: str file path or None
```

### 3.2 Intelligence Pipeline

```python
# VelocityEKF — 2-state Kalman
ekf = VelocityEKF()
ekf.update(obd_speed_kmh, imu_accel_x_g)
velocity = ekf.get_velocity()   # float km/h

# CrashDetector — 4-tier signature detection
detector = CrashDetector()
result = detector.assess(
    imu_accel_vector,    # (ax, ay, az) in g
    audio_event,         # dict from AudioClassifier or None
    obd_snapshot,        # dict with speed, throttle, rpm
    timestamp            # float unix time
)
# result.detected    bool
# result.confidence  float 0.0–1.0
# result.severity    "critical" | "warning" | "info"
# result.explanation str  (explainable AI)

# AudioClassifier — YAMNet TFLite
classifier = AudioClassifier()
event = classifier.classify(audio_segment)
# event.label       "crash"|"horn"|"siren"|"harsh_braking"|"pothole"|"normal"
# event.confidence  float 0.0–1.0

# TheftDetector — Ghost Key TSA
td = TheftDetector()
td.handle_motion_trigger()  # Call when PIR fires
result = td.verify_temporal_sequence(engine_start_event)
# result.is_theft   bool
# result.anomalies  list[str]
# result.confidence float

# PredictiveAnalyticsEngine — NVH
nvh = PredictiveAnalyticsEngine()
score = nvh.calculate_nvh_reconstruction_error(accel_buffer)
# score.nvh_health_score_fft    float %
# score.reconstruction_error    float
# score.drivetrain_anomaly_detected  bool
report = await nvh.generate_maintenance_report(score)
# report: str (Gemini-generated natural language)

# SystemHealthMonitor
monitor = SystemHealthMonitor()
monitor.ping_sensor("obd", is_alive=True)
report = monitor.get_health_report()
# report.capacity   float 0.0–1.0
# report.sensors    dict[str, bool]
# report.cpu_pct    float
# report.ram_pct    float
```

### 3.3 Communication

```python
# AlertManager — severity-based routing
alerts = AlertManager(cfg)
alerts.send_crash_alert(confidence, evidence, location)
alerts.send_theft_alert(anomalies, action_taken)
alerts.send_health_report(report)

# TelegramAlertBot — direct REST
bot = TelegramAlertBot()
bot.send_alert("CRITICAL", "Crash detected", details_dict)
# Delivers formatted message with confidence bars to chat_id

# MQTTManager
mqtt = MQTTManager()
mqtt.publish("vista/telemetry", payload_dict)  # QoS 1
```

### 3.4 Data Storage

```python
# SQLiteManager — thread-safe, WAL mode
db = SQLiteManager()
db.init_db()  # Creates tables if not exist (idempotent)
event_id = db.log_event(
    event_type="crash",
    confidence=0.95,
    severity="critical",
    notes="Ghost Key: 4 anomalies detected"
)

# InfluxWriter — singleton client
from main import _get_influx_writer
write_api = _get_influx_writer()  # Returns None if no token
# Client created ONCE, reused for all subsequent writes
```

---

## 4. Data Flow — End-to-End

```
Sensor Data                    Processing                    Output
───────────                    ──────────                    ──────
IMU (100Hz)  ─────────────►  CrashDetector ──────────────► SQLite log
OBD (2Hz)    ─────────────►  VelocityEKF   ──────────────► InfluxDB
Audio (1Hz)  ─────────────►  AudioClassifier ────────────► Telegram
                                    │
                                    ▼
                             DecisionEngine
                             (weighted confidence)
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                    CRASH > 0.65          THEFT > 0.70
                         │                     │
                         ▼                     ▼
                    CameraCapture      TheftDetector.TSA
                    CloudVision             │
                    (Gemini scene)     Fuel relay cut
                         │
                    AlertManager
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
           Telegram    MQTT       Buzzer
           (family)  (fleet)    (physical)
```

---

## 5. InfluxDB Data Schema

```
Measurement: telemetry
Tags:
  device: "VISTA-0001"
Fields (per 500ms tick):
  speed_kmh:    float  (EKF fused velocity)
  rpm:          float  (OBD raw)
  throttle_pct: float  (OBD raw)
  accel_x_g:    float  (IMU)
  accel_y_g:    float  (IMU)
  accel_z_g:    float  (IMU)
  gyro_x_dps:   float  (IMU)
  gyro_y_dps:   float  (IMU)
  gyro_z_dps:   float  (IMU)

Measurement: events
  (Stored in SQLite, not InfluxDB — see sqlite_manager.py)
```

## 6. SQLite Event Schema

```sql
CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   REAL NOT NULL,          -- Unix epoch float
    event_type  TEXT NOT NULL,          -- "crash"|"theft"|"harsh_braking"
    confidence  REAL NOT NULL,          -- 0.0–1.0
    severity    TEXT NOT NULL,          -- "critical"|"warning"|"info"
    evidence    TEXT,                   -- JSON blob of sensor evidence
    image_path  TEXT,                   -- Path to captured image or NULL
    location    TEXT,                   -- JSON {lat, lon, speed} or NULL
    status      TEXT DEFAULT 'active',  -- "active"|"reviewed"|"false_positive"
    notes       TEXT,                   -- Human-readable explanation
    device_id   TEXT                    -- "VISTA-0001"
);
```

---

**Version:** 4.0 | **Date:** May 16, 2026
