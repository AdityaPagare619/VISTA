# 05 — Technology Stack v4.0
## VISTA: Libraries, Cloud Services & Deployment Environment

**Version:** 4.0 | **Status:** Built & Verified | **Date:** May 16, 2026

---

## 1. Python Runtime

```
Python:  3.9+  (tested on 3.8.1 and 3.11)
Pi OS:   Raspberry Pi OS Bookworm (Debian 12) 64-bit
         (required for 64-bit TFLite runtime)
```

---

## 2. Core Dependencies

### 2.1 Always Required

| Library | Version | Purpose | Install |
|---|---|---|---|
| `numpy` | ≥1.21 | Array math, EKF, FFT | pip |
| `pyyaml` | ≥6.0 | config.yaml parsing | pip |
| `loguru` | ≥0.7 | Structured logging with levels | pip |
| `requests` | ≥2.28 | Telegram + Gemini REST calls | pip |
| `python-dotenv` | ≥1.0 | .env file loading | pip |
| `flask` | ≥3.0 | Dashboard web server | pip |
| `flask-socketio` | ≥5.3 | Real-time telemetry push | pip |
| `eventlet` | ≥0.33 | Async SocketIO worker | pip |

### 2.2 Pi Hardware (gracefully skipped on dev machine)

| Library | Purpose | Fallback Behavior |
|---|---|---|
| `RPi.GPIO` | Pi GPIO control (buzzer, heartbeat) | Log-only simulation |
| `smbus2` | I2C bus access for MPU6050 | Demo noise generation |
| `mpu6050-raspberrypi` | MPU6050 high-level driver | 0.02g noise simulation |
| `python-obd` | ELM327 OBD-II communication | Sinusoidal speed/RPM demo |
| `pyaudio` | USB microphone capture | White noise at -40dBFS |
| `bleak` | BLE scanning (async) | MAC list simulation |
| `paho-mqtt` | MQTT client | Graceful disable, log warning |

### 2.3 ML / AI

| Library | Version | Purpose |
|---|---|---|
| `tflite-runtime` | ≥2.13 | YAMNet inference (Pi, no full TF needed) |
| `tensorflow` | ≥2.13 | Alternative if tflite-runtime unavailable |
| `scipy` | ≥1.9 | FFT for NVH analysis |

### 2.4 Data Storage

| Library | Purpose | Notes |
|---|---|---|
| `sqlite3` | Event database | stdlib — zero install |
| `influxdb-client` | Time-series telemetry | Optional — graceful skip if absent |

---

## 3. Cloud Services

### 3.1 Gemini API (Google)

```yaml
Provider:   Google AI Studio
Model:      gemini-1.5-flash
Endpoint:   https://generativelanguage.googleapis.com/v1beta/models/
API Key:    GEMINI_API_KEY env var (see .env.example)
Rate limit: 1,500 requests/day (free tier)
Cost:       ₹0/month on free tier
Use cases:
  1. Crash scene description (on-demand, per event)
  2. NVH "Expert Mechanic" maintenance report
  3. Alert enrichment with natural language

Configuration (config.yaml):
  cloud.vision.model: "gemini-1.5-flash"
  cloud.vision.max_retries: 3
  cloud.vision.timeout_seconds: 10
```

### 3.2 Telegram Bot API

```yaml
Provider:   Telegram Bot API (free, unlimited)
Endpoint:   https://api.telegram.org/bot<TOKEN>/sendMessage
Auth:       TELEGRAM_BOT_TOKEN env var
Target:     TELEGRAM_CHAT_ID env var (owner's chat)
Cost:       ₹0 — completely free

Alert routing by severity:
  CRITICAL  → Telegram + MQTT + BLE notify + Buzzer
  WARNING   → MQTT + BLE notify
  INFO      → MQTT only

Alert format delivered to owner:
  💥 VISTA Alert 💥
  🔴 Event: Crash / CRITICAL
  📊 Confidence: 84.6%
  Evidence bars:
    imu_jerk: ████████░░ 85%
    audio:    ████████░░ 78%
    obd:      ██████░░░░ 55%
  Scene: [Gemini description]
  Time: 2026-05-16 13:30:45 UTC
  ⚠️ VISTA is a research prototype. Call emergency services.
```

### 3.3 InfluxDB (Optional, local)

```yaml
Host:   localhost:8086
Auth:   INFLUXDB_TOKEN env var
Org:    vista
Bucket: vista_telemetry
Retention: 30 days
Cost:   ₹0 — local, self-hosted
Notes:  Must be on USB SSD (not SD card)
        If INFLUXDB_TOKEN not set, writes silently skipped
```

---

## 4. ESP32-C3 Firmware Stack

```
IDE:        ESP-IDF v5.x (Espressif official framework)
Language:   C (main.c, 1,098 lines)
Build:      cmake / idf.py build
Flash:      idf.py -p /dev/ttyUSB1 flash

Key libraries used:
  driver/gpio.h          GPIO control
  esp_sleep.h            Deep sleep (5μA)
  nvs_flash.h            NVS: persists state across deep sleep
  esp_bt.h / esp_gap_ble_api.h  BLE advertising + scanning
  driver/adc.h           Battery voltage ADC
  esp_log.h              UART debug logging

BLE GATT Service:
  Service UUID: 0000VISTA-0000-1000-8000-00805F9B34FB
  Characteristics:
    - battery_mv (READ)
    - mode (READ: 0=sleep, 1=alert, 2=normal)
    - pir_state (READ: 0/1)
    - pi_alive (READ: 0/1)
    - command (WRITE: "arm" / "disarm")
```

---

## 5. Development vs Production Environment

### 5.1 Development (Windows / Mac / Linux laptop)

```bash
# No Pi hardware needed
cd src/vista
DEMO_MODE=true python main.py --mode dashboard

# All hardware gracefully falls back to simulation:
#   OBD → sinusoidal speed/RPM
#   IMU → 0.02g Gaussian noise + 1g gravity
#   Audio → white noise at -40dBFS
#   GPIO → log-only

# Run demo scenarios via browser:
# http://localhost:5000
```

### 5.2 Production (Raspberry Pi 4B)

```bash
# One-command deployment from project root:
sudo ./scripts/deploy.sh

# What it does (6 phases):
# 1. apt-get: portaudio, i2c-tools, bluez, sqlite3
# 2. Create 'vista' system user with gpio/i2c/audio groups
# 3. Copy source to /opt/vista/
# 4. Python venv at /opt/vista/venv/
# 5. pip install all requirements
# 6. Install + enable systemd services

# Start services:
sudo systemctl start vista
sudo systemctl start vista-dashboard

# View logs:
journalctl -u vista -f
```

### 5.3 Environment Variables (.env)

```bash
# Copy template:
cp .env.example .env

# Required for cloud features:
GEMINI_API_KEY=AIza...             # Google AI Studio
TELEGRAM_BOT_TOKEN=123456:ABC...   # @BotFather
TELEGRAM_CHAT_ID=8407946567        # Your chat ID

# Optional:
INFLUXDB_TOKEN=...                 # Local InfluxDB
DEMO_MODE=false                    # true = no hardware needed

# Get Telegram chat ID:
# 1. Message your bot
# 2. Visit: https://api.telegram.org/bot<TOKEN>/getUpdates
# 3. Read "chat": {"id": <YOUR_ID>}
```

---

## 6. CI/CD Pipeline (.github/workflows/ci.yml)

```yaml
Trigger: push to main or develop, PR to main

Jobs (run in sequence):
  1. import-check (Python 3.9 + 3.11)
     → Imports all 19 modules with DEMO_MODE=true
     → Must complete with exit 0

  2. unit-tests (Python 3.11)
     → Runs tests/test_v3_quick.py
     → Must show 20/20 PASSED

  3. sitl-demo (Python 3.11, main branch only)
     → Runs scripts/demo_billion_dollar_architecture.py
     → Requires GEMINI_API_KEY + TELEGRAM_* secrets
     → Must show ALL SCENARIOS PASSED + EXIT 0

  4. code-quality (Ruff linter)
     → ruff check src/vista/ --select E,F,W --ignore E501,E402,F401
     → Exit code 0 required (warnings allowed, errors block)
```

---

## 7. Install Commands Reference

```bash
# Full Pi install (automated):
sudo ./scripts/deploy.sh

# Manual install (development):
pip install numpy pyyaml loguru requests python-dotenv
pip install flask flask-socketio eventlet
pip install tflite-runtime  # or tensorflow on non-Pi

# Pi hardware packages (Pi only):
pip install RPi.GPIO smbus2 mpu6050-raspberrypi
pip install python-obd pyaudio bleak paho-mqtt

# Verify model exists:
ls -la src/vista/models/yamnet.tflite
# Expected: 4,126,810 bytes

# Verify I2C:
sudo i2cdetect -y 1
# Expected: 0x68 shown

# Run quick verification:
cd src/vista
python tests/test_v3_quick.py
# Expected: 20 passed, 0 failed
```

---

**Version:** 4.0 | **Date:** May 16, 2026
