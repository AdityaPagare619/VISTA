# 05 — Technology Stack & Choices
## VISTA: Libraries, Frameworks, APIs & Infrastructure

**Version:** 2.1 | **Status:** Final | **Date:** May 8, 2026

---

## 1. Operating System & Base

| Component | Choice | Version | Why |
|-----------|--------|---------|-----|
| **Pi OS** | Raspberry Pi OS (Debian 12 Bookworm) | 64-bit | Official; stable; full apt package support; Python 3.11 |
| **ESP32 OS** | ESP-IDF (FreeRTOS) | v5.2+ | Native Espressif SDK; best power management; Arduino as fallback |
| **Python** | CPython | 3.11 | Pre-installed; all libraries available; stable |
| **Shell** | Bash | 5.2 | Default on Debian |

---

## 2. Core Libraries

### 2.1 Hardware Abstraction

| Library | Purpose | Install | Why Not Alternative |
|---------|---------|---------|---------------------|
| **python-OBD** | OBD-II data reading | `pip install obd` | Only well-maintained OBD library for Python; handles ELM327 + all protocols |
| **mpu6050-raspberrypi** | IMU sensor driver | `pip install mpu6050-raspberrypi` | Simple I2C interface; widely used; well-documented |
| **picamera2** | Camera control | Pre-installed on Bookworm | Official Pi camera library; better than legacy picamera |
| **PyAudio** | Audio capture | `apt install python3-pyaudio` | Standard; supports 16kHz/16-bit; callback API for streaming |
| **gpiozero** | GPIO control | Pre-installed | Official Pi GPIO library; simpler than RPi.GPIO |
| **pyserial** | Serial communication | `pip install pyserial` | Standard; needed for OBD-II serial fallback |
| **smbus2** | I2C communication | `pip install smbus2` | Pure Python; cleaner API than smbus-cffi |

### 2.2 Machine Learning

| Library | Purpose | Install | Why Not Alternative |
|---------|---------|---------|---------------------|
| **TensorFlow Lite Runtime** | Audio CNN inference | `pip install tflite-runtime` | Only 2MB install size; XNNPACK ARM delegate; INT8 quantization |
| **NumPy** | Numerical computation | Pre-installed | Standard; needed for EKF matrices, signal processing |
| **SciPy** | Signal processing | `pip install scipy` | FFT, filtering for audio preprocessing |
| **librosa** | Audio feature extraction | `pip install librosa` | Mel-spectrogram conversion; standard in audio ML |
| **scikit-learn** | Random Forest (driver behavior) | `pip install scikit-learn` | Lightweight; doesn't need GPU; easy model export |

### 2.3 Data Storage

| Library | Purpose | Install | Why Not Alternative |
|---------|---------|---------|---------------------|
| **influxdb-client** | Time-series data writes | `pip install influxdb-client` | Official InfluxDB Python client; batch writes; 10x faster than generic HTTP |
| **InfluxDB OSS** | Time-series database | `apt install influxdb` | Purpose-built for sensor data; auto-downsampling; retention policies |
| **SQLite3** | Event/relational storage | Built-in (stdlib) | Zero setup; file-based; perfect for event logs; ACID compliant |

### 2.4 Communication

| Library | Purpose | Install | Why Not Alternative |
|---------|---------|---------|---------------------|
| **paho-mqtt** | MQTT client | `pip install paho-mqtt` | Most popular Python MQTT; QoS support; async |
| **Mosquitto** | MQTT broker | `apt install mosquitto` | Lightweight (120KB); runs on Pi; standard |
| **bleak** | BLE communication | `pip install bleak` | Cross-platform BLE; async API; better than BlueZ direct |
| **google-generativeai** | Gemini Vision API | `pip install google-generativeai` | Official Google SDK; automatic retry; image handling |
| **requests** | HTTP client (WhatsApp Bot API) | `pip install requests` | Standard; simple; used for alert bot APIs |

### 2.5 Dashboard & UI

| Library | Purpose | Install | Why Not Alternative |
|---------|---------|---------|---------------------|
| **Flask** | Web dashboard server | `pip install flask` | Lightweight; runs on Pi; Jinja2 templates |
| **Grafana** | Data visualization | `apt install grafana` | Beautiful dashboards; InfluxDB native connector; free |
| **Flask-SocketIO** | Real-time dashboard updates | `pip install flask-socketio` | WebSocket push; live telemetry on dashboard |

### 2.6 System Utilities

| Library | Purpose | Install | Why |
|---------|---------|---------|-----|
| **systemd** | Service management | Built-in | Standard Linux init; auto-restart; logging (journald) |
| **loguru** | Application logging | `pip install loguru` | Better than stdlib logging; colored output; rotation |
| **python-dotenv** | Environment variables | `pip install python-dotenv` | .env file for API keys; keeps secrets out of code |
| **PyYAML** | Configuration parsing | `pip install pyyaml` | config.yaml reader |
| **psutil** | System monitoring | `pip install psutil` | CPU/RAM/disk monitoring |

---

## 3. Cloud Services

### 3.1 Vision AI

| Service | Tier | Limit | Cost | Why |
|---------|------|-------|------|-----|
| **Google Gemini 1.5 Flash** | Free | 1,500 requests/day | $0 (free tier) | Fastest; cheapest; good image understanding; JSON output |
| **OpenAI GPT-4V (backup)** | Free trial | Varies | $0 (trial) | Fallback if Gemini unavailable |

### 3.2 Messaging

| Service | Purpose | API | Cost |
|---------|---------|-----|------|
| **WhatsApp Business API** | Enriched crash/theft alerts | Meta Graph API | ₹0.50/msg or free tier |
| **Telegram Bot API** | (Optional) alternative alert channel | HTTP Bot API | Free |

### 3.3 Cloud Sync (Optional)

| Service | Purpose | Cost |
|---------|---------|------|
| **InfluxDB Cloud** | Remote dashboard (optional) | Free tier: 10GB |
| **GitHub** | Code hosting + version control | Free |

---

## 4. Development Tools

| Tool | Purpose | Install |
|------|---------|---------|
| **VS Code (Remote SSH)** | Code editing on Pi | Desktop |
| **Git** | Version control | `apt install git` |
| **venv** | Python virtual environment | Built-in |
| **black** | Code formatting | `pip install black` |
| **pytest** | Unit testing | `pip install pytest` |
| **htop** | System monitoring | `apt install htop` |
| **tmux** | Terminal multiplexer | `apt install tmux` |

---

## 5. Directory Structure

```
/home/pi/vista/
├── config.yaml                  # Main configuration
├── .env                         # API keys (gitignored)
├── requirements.txt             # Python dependencies
│
├── hal/                         # Hardware Abstraction Layer
│   ├── __init__.py
│   ├── obd_reader.py
│   ├── imu_reader.py
│   ├── audio_capture.py
│   ├── camera_capture.py
│   ├── gpio_manager.py
│   └── esp32_bridge.py
│
├── intelligence/                # Intelligence Layer
│   ├── __init__.py
│   ├── fusion_engine.py         # EKF implementation
│   ├── audio_classifier.py      # TFLite CNN inference
│   ├── decision_engine.py       # Explainable decision engine
│   └── cloud_vision.py          # Gemini Vision API client
│
├── communication/               # Communication Layer
│   ├── __init__.py
│   ├── mqtt_manager.py
│   ├── ble_manager.py
│   ├── alert_manager.py         # Multi-channel alert routing
│   └── whatsapp_bot.py
│
├── data/                        # Data Layer
│   ├── __init__.py
│   ├── influx_writer.py
│   ├── sqlite_manager.py
│   └── file_manager.py
│
├── dashboard/                   # Web Dashboard
│   ├── app.py                   # Flask server
│   ├── templates/
│   │   ├── index.html
│   │   ├── live.html
│   │   └── history.html
│   └── static/
│       ├── style.css
│       └── dashboard.js
│
├── models/                      # ML Models (gitignored)
│   ├── audio_cnn.tflite
│   └── driver_behavior.pkl
│
├── data_storage/                # Local databases
│   ├── influxdb/               # Time-series data
│   ├── events.db               # SQLite event database
│   └── images/                 # Captured images
│       ├── driving/
│       ├── crash/
│       └── theft/
│
├── scripts/                     # Utility scripts
│   ├── startup.sh
│   ├── shutdown.sh
│   ├── calibrate_imu.py
│   └── test_all_sensors.py
│
├── services/                    # Systemd service files
│   ├── vista-obd.service
│   ├── vista-imu.service
│   ├── vista-audio.service
│   ├── vista-fusion.service
│   ├── vista-decision.service
│   ├── vista-mqtt.service
│   └── vista-api.service
│
├── esp32/                       # ESP32 firmware
│   ├── main/
│   │   └── main.c              # ESP-IDF main
│   ├── CMakeLists.txt
│   └── sdkconfig
│
├── tests/                       # Test suite
│   ├── test_obd_reader.py
│   ├── test_imu_reader.py
│   ├── test_fusion_engine.py
│   ├── test_decision_engine.py
│   └── test_integration.py
│
└── docs/                        # Documentation
    ├── README.md
    └── API.md
```

---

## 6. Dependency Installation

```bash
#!/bin/bash
# Complete setup script for Pi

# System dependencies
sudo apt update
sudo apt install -y python3-pip python3-venv i2c-tools \
    influxdb mosquitto grafana git tmux \
    portaudio19-dev python3-pyaudio \
    libatlas-base-dev libopenblas-dev  # For NumPy/SciPy optimization

# Enable interfaces
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_camera 0

# Python virtual environment
cd /home/pi/vista
python3 -m venv venv
source venv/bin/activate

# Core libraries
pip install obd mpu6050-raspberrypi picamera2 gpiozero pyserial smbus2

# ML stack
pip install tflite-runtime numpy scipy librosa scikit-learn

# Data
pip install influxdb-client

# Communication
pip install paho-mqtt bleak google-generativeai requests

# Web
pip install flask flask-socketio

# Utilities
pip install loguru python-dotenv pyyaml psutil

# Development
pip install black pytest

# Start services
sudo systemctl enable influxdb mosquitto grafana-server
sudo systemctl start influxdb mosquitto grafana-server

# Setup InfluxDB
influx setup --username vista --password vista123 --org vista --bucket vista_telemetry

echo "✅ VISTA environment ready"
```

---

## 7. Technology Decision Matrix

| Decision | Options Considered | Chosen | Deciding Factor |
|----------|-------------------|--------|-----------------|
| OS | Ubuntu Server, DietPi, Pi OS | **Pi OS** | Official support; all drivers pre-configured |
| ML Runtime | ONNX, PyTorch Mobile, TFLite | **TFLite** | Smallest (2MB); best ARM optimization; INT8 quant |
| Audio ML | YAMNet, VGGish, Custom CNN | **Custom CNN** | 25x smaller; vehicle-specific classes; fast |
| Vision | Local model, Cloud API | **Cloud API** | Unlimited classes; zero Pi CPU; natural language |
| DB: Time-series | TimescaleDB, MongoDB, InfluxDB | **InfluxDB** | Purpose-built; retention policies; Grafana native |
| DB: Events | PostgreSQL, MySQL, SQLite | **SQLite** | Zero setup; file-based; sufficient for event logs |
| MQTT Broker | EMQX, RabbitMQ, Mosquitto | **Mosquitto** | 120KB; simple; standard |
| BLE Stack | BlueZ direct, noble, bleak | **bleak** | Async; cross-platform; clean API |
| Web framework | FastAPI, Django, Flask | **Flask** | Lightest; runs on Pi; sufficient for dashboard |
| Logging | stdlib logging, structlog, loguru | **loguru** | Clean syntax; colored; rotation built-in |
| ESP-IDF vs Arduino | ESP-IDF, Arduino-ESP32 | **ESP-IDF** | Better power management; native FreeRTOS |

---

## 8. Version Compatibility Matrix

| Component | Required Version | Tested On |
|-----------|-----------------|-----------|
| Raspberry Pi OS | Debian 12 (Bookworm) | 2024-03-15 release |
| Linux Kernel | 6.1+ | 6.1.21-v8+ |
| Python | 3.11+ | 3.11.2 |
| TFLite Runtime | 2.14+ | 2.14.0 |
| OpenCV (optional) | 4.8+ | Not used in v2.1 (cloud API instead) |
| ESP-IDF | 5.2+ | 5.2.0 |
| InfluxDB | 2.7+ | 2.7.4 |
| Mosquitto | 2.0+ | 2.0.18 |
| Grafana | 10+ | 10.2.0 |

---

## 9. `.gitignore`

```gitignore
# Secrets
.env
*.pem
*.key

# ML Models (too large for git)
models/*.tflite
models/*.pkl
models/*.h5

# Data
data_storage/influxdb/
data_storage/images/
*.db
*.db-journal

# Python
__pycache__/
*.pyc
venv/

# ESP32
esp32/build/
esp32/sdkconfig.old

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
```

---

**Next:** See `01_SYSTEM_DESIGN.md` for overall system design overview.
