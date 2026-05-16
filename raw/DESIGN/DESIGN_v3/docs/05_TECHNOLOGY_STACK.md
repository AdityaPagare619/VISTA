# 05 — Technology Stack v3.0
## VISTA: Libraries, Frameworks, APIs & Infrastructure

**Version:** 3.0 | **Status:** Final | **Date:** May 10, 2026

---

## 1. OS & Base (unchanged)

| Component | Choice | Version | Why |
|-----------|--------|---------|-----|
| Pi OS | Raspberry Pi OS (Bookworm) | 64-bit | Official; stable; Python 3.11 |
| ESP32 OS | ESP-IDF (FreeRTOS) | v5.2+ | Native; best power management |
| Python | CPython | 3.11 | Pre-installed; all libraries available |

---

## 2. Core Libraries (Updated)

### 2.1 Hardware Abstraction (unchanged)

| Library | Purpose | Install |
|---------|---------|---------|
| python-OBD | OBD-II reading (2-3Hz real rate) | `pip install obd` |
| mpu6050-raspberrypi | IMU driver | `pip install mpu6050-raspberrypi` |
| picamera2 | Camera control | Pre-installed |
| PyAudio | Audio capture | `apt install python3-pyaudio` |
| gpiozero | GPIO control | Pre-installed |

### 2.2 ML (unchanged)

| Library | Purpose | Install |
|---------|---------|---------|
| TFLite Runtime | Audio CNN inference (2MB) | `pip install tflite-runtime` |
| NumPy | EKF matrices, signal processing | Pre-installed |
| SciPy | FFT, filtering | `pip install scipy` |
| librosa | Mel-spectrogram extraction | `pip install librosa` |

### 2.3 Data Storage (Updated: USB SSD config)

| Library | Purpose | Install | Note |
|---------|---------|---------|------|
| InfluxDB OSS | Time-series DB | `apt install influxdb` | **Data dir → USB SSD** |
| influxdb-client | Python client | `pip install influxdb-client` | — |
| SQLite3 | Event/relational storage | Built-in | **DB file → USB SSD** |

**USB SSD Setup:**
```bash
# Format and mount SSD
sudo mkfs.ext4 /dev/sda1
sudo mkdir -p /mnt/vista-data
sudo mount /dev/sda1 /mnt/vista-data

# Add to /etc/fstab for auto-mount
UUID=$(blkid -s UUID -o value /dev/sda1)
echo "UUID=$UUID /mnt/vista-data ext4 defaults,noatime,nofail 0 2" | sudo tee -a /etc/fstab

# Move InfluxDB data directory
sudo systemctl stop influxdb
sudo mv /var/lib/influxdb /mnt/vista-data/influxdb
sudo ln -s /mnt/vista-data/influxdb /var/lib/influxdb
sudo systemctl start influxdb

# Create VISTA directories
mkdir -p /mnt/vista-data/{images/{driving,crash,theft}}
```

### 2.4 Communication (Updated: Telegram primary)

| Library | Purpose | Install | Note |
|---------|---------|---------|------|
| paho-mqtt | MQTT client | `pip install paho-mqtt` | — |
| Mosquitto | MQTT broker | `apt install mosquitto` | — |
| bleak | BLE communication | `pip install bleak` | — |
| google-generativeai | Gemini Vision API | `pip install google-generativeai` | — |
| **requests** | **Telegram Bot API** | `pip install requests` | **Primary alert channel (FREE)** |

**WhatsApp status:** Documented as optional paid upgrade. Not implemented for demo. Telegram is functionally equivalent and completely free.

### 2.5 Dashboard & Utilities (unchanged)

| Library | Purpose | Install |
|---------|---------|---------|
| Flask | Web dashboard | `pip install flask` |
| Grafana | Data visualization | `apt install grafana` |
| Flask-SocketIO | Real-time updates | `pip install flask-socketio` |
| loguru | Logging | `pip install loguru` |
| python-dotenv | Env vars for secrets | `pip install python-dotenv` |
| PyYAML | Config parsing | `pip install pyyaml` |
| psutil | System monitoring | `pip install psutil` |

---

## 3. Cloud Services (Updated)

| Service | Tier | Cost | Note |
|---------|------|------|------|
| Gemini 1.5 Flash | Free | $0 (1,500 req/day) | May change — system works without it |
| **Telegram Bot API** | **Free** | **$0 (unlimited)** | **Primary alert channel** |
| WhatsApp Business API | Paid | ~₹0.50/msg | Optional upgrade, NOT implemented |

---

## 4. Directory Structure (Updated for USB SSD)

```
/home/pi/vista/                  # Code (on SD card)
├── config.yaml
├── .env                         # API keys (gitignored)
├── requirements.txt
├── hal/
│   ├── obd_reader.py
│   ├── imu_reader.py
│   ├── audio_capture.py
│   ├── camera_capture.py
│   ├── gpio_manager.py
│   ├── esp32_bridge.py
│   └── power_manager.py        # NEW: MOSFET control
├── intelligence/
│   ├── velocity_ekf.py          # RENAMED: was fusion_engine.py
│   ├── crash_detector.py        # NEW: separated from EKF
│   ├── audio_classifier.py
│   ├── decision_engine.py
│   └── cloud_vision.py
├── communication/
│   ├── mqtt_manager.py
│   ├── ble_manager.py
│   ├── alert_manager.py
│   └── telegram_bot.py          # NEW: replaces whatsapp_bot.py
├── data/
│   ├── influx_writer.py
│   ├── sqlite_manager.py
│   └── file_manager.py
├── dashboard/
│   ├── app.py
│   ├── templates/
│   └── static/
├── models/                      # ML models (gitignored)
├── scripts/
│   ├── startup.sh
│   ├── shutdown.sh
│   ├── setup_ssd.sh             # NEW
│   └── test_all_sensors.py
├── services/                    # Systemd files
├── esp32/                       # ESP32 firmware
│   └── main/main.c             # Includes MOSFET control
├── tests/
└── docs/

/mnt/vista-data/                 # Data (on USB SSD)
├── influxdb/                    # Time-series data
├── events.db                    # SQLite events
└── images/
    ├── driving/
    ├── crash/
    └── theft/
```

---

## 5. Technology Decision Matrix (v3.0 additions)

| Decision | Chosen | Why |
|----------|--------|-----|
| Alert channel | **Telegram** | Free, unlimited, rich media, developer-friendly |
| Pi power control | **MOSFET switch** | Pi can't sleep; MOSFET = true 0W off |
| Storage medium | **USB SSD** | InfluxDB kills SD cards; SSD = reliable + fast |
| EKF scope | **Velocity only** | Crashes violate EKF assumptions; separate detector |
| OBD role | **Async corroborator** | ELM327 is 2-3Hz reality; can't be real-time |

---

## 6. Installation Script (Updated)

```bash
#!/bin/bash
# Complete v3.0 setup script

# System dependencies
sudo apt update && sudo apt install -y \
  python3-pip python3-venv i2c-tools \
  influxdb mosquitto grafana git tmux \
  portaudio19-dev python3-pyaudio \
  libatlas-base-dev libopenblas-dev

# Enable interfaces
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_camera 0

# Setup USB SSD (run setup_ssd.sh first)
bash /home/pi/vista/scripts/setup_ssd.sh

# Python venv
cd /home/pi/vista
python3 -m venv venv && source venv/bin/activate

# Install all Python deps
pip install obd mpu6050-raspberrypi gpiozero pyserial smbus2
pip install tflite-runtime numpy scipy librosa scikit-learn
pip install influxdb-client
pip install paho-mqtt bleak google-generativeai requests
pip install flask flask-socketio
pip install loguru python-dotenv pyyaml psutil
pip install black pytest

# Move InfluxDB data to SSD
sudo systemctl stop influxdb
sudo mv /var/lib/influxdb /mnt/vista-data/influxdb
sudo ln -s /mnt/vista-data/influxdb /var/lib/influxdb
sudo systemctl start influxdb

# Start services
sudo systemctl enable influxdb mosquitto grafana-server
sudo systemctl start influxdb mosquitto grafana-server

echo "✅ VISTA v3.0 environment ready"
```

---

**Next:** See `06_DEMO_EVALUATION_METHODOLOGY.md` for updated demo scripts.
