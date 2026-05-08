# 01 — System Design Document
## VISTA: Vehicle Intelligence & Safety Telematics Architecture

**Version:** 2.1 | **Status:** Final | **Date:** May 8, 2026

---

## 1. System Overview

VISTA is a **hybrid edge-cloud vehicle intelligence platform** running on a Raspberry Pi 4B with an ESP32-C3 coprocessor. It fuses 4 sensing modalities (OBD-II, IMU, Audio, Camera) to detect crashes, theft, and driving behavior — while using Cloud Vision AI for enriched scene understanding.

### 1.1 Core Design Philosophy

> **"The best part is no part."** — Only add hardware that's essential. Use what Pi already has (WiFi/BLE). Use what the phone already has (GPS/Display). Use what the cloud does best (vision AI).

### 1.2 System Boundaries

```
┌──────────────────────────────────────────────────────────────┐
│                     VISTA SYSTEM BOUNDARY                     │
│                                                               │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────────┐ │
│  │ OBD-II  │   │  IMU    │   │  Audio  │   │   Camera    │ │
│  │ (Input) │   │ (Input) │   │ (Input) │   │   (Input)   │ │
│  └────┬────┘   └────┬────┘   └────┬────┘   └──────┬──────┘ │
│       └──────────────┼─────────────┼───────────────┘        │
│                      ▼             ▼                         │
│              ┌──────────────────────────────┐                │
│              │      RASPBERRY PI 4B         │                │
│              │  ┌────────────────────────┐  │                │
│              │  │  SENSOR FUSION (EKF)   │  │                │
│              │  │  AUDIO CNN (TFLite)    │  │                │
│              │  │  DECISION ENGINE       │  │                │
│              │  │  LOCAL DB (Influx)     │  │                │
│              │  └────────────────────────┘  │                │
│              │  ┌────────────────────────┐  │                │
│              │  │  WiFi (built-in) ──────┼──┼──▶ Cloud API  │
│              │  │  BLE (built-in) ───────┼──┼──▶ Smartphone │
│              │  │  MQTT Broker           │  │                │
│              │  └────────────────────────┘  │                │
│              └──────────────┬───────────────┘                │
│                             │ GPIO                            │
│              ┌──────────────┴───────────────┐                │
│              │     ESP32-C3 (Sentinel)      │                │
│              │  ┌────────────────────────┐  │                │
│              │  │  PIR → GPIO Wake       │  │                │
│              │  │  Battery Monitor (ADC) │  │                │
│              │  │  BLE Peripheral        │  │                │
│              │  └────────────────────────┘  │                │
│              └──────────────────────────────┘                │
│                                                               │
│  EXTERNAL SYSTEMS (Outside boundary):                         │
│  • Gemini Vision API (Google Cloud)                           │
│  • WhatsApp/Telegram Bot API                                  │
│  • Smartphone (display, GPS, cellular)                        │
│  • Vehicle OBD-II port + 12V battery                          │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. System States & Modes

### 2.1 State Machine

```
                    ┌──────────┐
                    │  BOOT    │ (Pi power-on, 10s)
                    └────┬─────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        ┌──────────┐          ┌──────────┐
        │ DRIVING  │          │  PARKED  │
        │  MODE    │          │  MODE    │
        └────┬─────┘          └────┬─────┘
             │                     │
    ┌────────┼────────┐    ┌───────┼───────┐
    ▼        ▼        ▼    ▼       ▼       ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│NORMAL│ │CRASH │ │THEFT │ │SLEEP │ │ALERT │
│      │ │EVENT │ │EVENT │ │      │ │ONLY  │
└──────┘ └──┬───┘ └──┬───┘ └──────┘ └──────┘
            │        │
            ▼        ▼
       ┌────────────────┐
       │  EMERGENCY     │
       │  RESPONSE      │
       │  (Enriched     │
       │   Alert + DB)  │
       └────────────────┘
```

### 2.2 Mode Definitions

| Mode | Trigger | Pi State | ESP32 State | Key Actions |
|------|---------|----------|-------------|-------------|
| **BOOT** | Power applied / ESP32 wake | Booting (10s) | Active | Load drivers, connect sensors, start services |
| **DRIVING-NORMAL** | OBD-II RPM > 0 | Active (8W) | Active | Continuous OBD+IMU+Audio monitoring; periodic camera+API |
| **DRIVING-CRASH** | IMU jerk >5g + OBD confirm | Active | Active | Capture all sensors; API analysis; enriched alert; log event |
| **PARKED-SLEEP** | Ignition OFF + 5 min idle | Deep sleep | Deep sleep (5μA) | PIR monitoring only |
| **PARKED-ALERT** | PIR triggered | Wake from sleep | Active | Camera burst → API → alert → return to sleep |
| **THEFT-MODE** | User arms via phone | Sleep (ESP32 only) | Active | PIR + vibration monitor; location tracking (GPS optional) |
| **LOW-BATTERY** | VBAT < 11.8V | Forced sleep | Active (BLE only) | Alert phone; stop waking Pi; protect battery |

---

## 3. Data Architecture

### 3.1 Data Types & Storage

| Data Type | Source | Rate | Storage | Retention |
|-----------|--------|------|---------|-----------|
| OBD-II PIDs | ELM327 | 10 Hz | InfluxDB (time-series) | 30 days |
| IMU raw | MPU6050 | 100 Hz | InfluxDB | 7 days (downsampled) |
| IMU fused | EKF output | 10 Hz | InfluxDB | 30 days |
| Audio features | CNN pre-processing | 25 Hz | Not stored (streaming) | — |
| Audio events | CNN classification | On-event | SQLite (event log) | 90 days |
| Camera images | Pi Cam v3 | On-event | File system (JPEG) | 30 days or 500MB cap |
| System events | Decision engine | On-event | SQLite (event log) | 90 days |
| Cloud API responses | Gemini Vision | On-event | SQLite (linked to event) | 90 days |

### 3.2 Data Flow — Normal Driving

```
T=0ms    OBD-II poll → (speed=45, rpm=2100, throttle=32%, brake=0)
T=10ms   IMU read → (ax=0.1, ay=-0.05, az=1.02, gx=0, gy=0, gz=0.01)
T=20ms   Audio buffer: 16000 samples (1 sec window)
T=30ms   Audio CNN: → [normal: 0.98, horn: 0.01, crash: 0.00, siren: 0.01]
T=50ms   EKF update: predicted state vs measured → fused velocity=44.8 km/h
T=60ms   Write to InfluxDB: {time, speed, rpm, throttle, fused_vel, audio_class}
T=100ms  Next cycle begins
```

### 3.3 Data Flow — Crash Detection

```
T=0ms    IMU interrupt: |jerk| = 7.2g (THRESHOLD EXCEEDED!)
T=10ms   Flag potential crash; capture pre/post buffer
T=20ms   OBD-II confirm: throttle 32%→0% in 200ms, speed 45→12 km/h
T=30ms   Audio CNN on last 2 sec: [crash: 0.91, normal: 0.09]
T=40ms   Camera: capture burst (5 frames, 100ms apart)
T=50ms   Decision engine: crash confidence = 0.35*1.0 + 0.25*1.0 + 0.25*0.91 + 0.15*0 = 0.89
T=60ms   CONFIDENCE > 0.65 → CRASH CONFIRMED
T=70ms   Store event in SQLite; store sensor snapshot
T=80ms   Alert via BLE (immediate text)
T=90ms   If WiFi available: upload image to Gemini Vision API
T=2000ms API response: "Front-end collision with barrier. Airbag deployed. One vehicle."
T=2100ms Enriched alert sent via WhatsApp: full event description + image
```

---

## 4. Component Interaction Matrix

| Component | OBD-II | IMU | Audio | Camera | ESP32 | Cloud API | Phone |
|-----------|--------|-----|-------|--------|-------|-----------|-------|
| **OBD-II** | — | Fused in EKF | — | — | — | — | — |
| **IMU** | Fused in EKF | — | — | — | — | — | — |
| **Audio** | Corroborates crash | Corroborates crash | — | — | — | — | — |
| **Camera** | — | — | — | — | — | Image source | — |
| **ESP32** | — | — | — | — | — | — | BLE status |
| **Cloud API** | — | — | — | Image input | — | — | Enriched alert |
| **Phone** | — | — | — | — | GPS via BLE | — | — |

---

## 5. Failure Modes & Graceful Degradation

| Failure | System Behavior | User Impact |
|---------|-----------------|-------------|
| OBD-II disconnected | EKF runs on IMU only; crash detection continues (no OBD corroboration) | Slightly reduced crash accuracy |
| IMU failure | Crash detection falls back to OBD speed rate + audio only | Reduced crash sensitivity |
| Audio mic failure | Crash detection uses IMU+OBD only; siren detection unavailable | Core safety maintained |
| Camera failure | Vision enrichment unavailable; alerts are text-only | Lost scene context |
| WiFi unavailable | Core safety works 100%; vision analysis deferred | Enriched alerts delayed |
| ESP32 failure | Pi stays in active mode (higher power draw) | Reduced parked battery life |
| SD card full | Oldest data pruned; alerts still sent | Historical data loss |
| Cloud API down | Vision analysis unavailable; alerts are local-only | Basic alerts work |
| Car battery low | ESP32 stops waking Pi; BLE-only alerts | Theft alerts continue |

---

## 6. Team Module Ownership

| Module | Primary Owner | Secondary | Skills Required |
|--------|--------------|-----------|-----------------|
| **OBD-II Pipeline** | Hardware Specialist | AI/ML | Python, serial protocols, CAN basics |
| **IMU + EKF Fusion** | Hardware Specialist | Data Analytics | Signal processing, Kalman filtering |
| **Audio CNN** | AI/ML Specialist | — | TensorFlow Lite, audio DSP, model training |
| **Camera + Cloud API** | AI/ML Specialist | Data Analytics | REST APIs, prompt engineering, image handling |
| **ESP32 Firmware** | Hardware Specialist | — | C/C++, ESP-IDF, low-power design |
| **Decision Engine** | Data Analytics | AI/ML | Python, rule engines, confidence scoring |
| **Database + Dashboard** | Data Analytics | — | InfluxDB, SQLite, Grafana, Flask |
| **Communication (MQTT/BLE)** | Data Analytics | Hardware | MQTT, BlueZ, socket programming |
| **Enclosure + Power** | Hardware Specialist | — | 3D printing, DC-DC converters, thermal |

---

## 7. System Startup Sequence

```
1. Car ignition ON → DC-DC converter powers up
2. ESP32-C3 boots (200ms) → checks battery voltage
3. ESP32 pulls Pi WAKE pin HIGH
4. Pi boots Raspberry Pi OS (~10s)
5. Systemd starts VISTA services:
   a. vista-obd.service (OBD-II reader)
   b. vista-imu.service (IMU + Madgwick filter)
   c. vista-audio.service (Audio capture + CNN)
   d. vista-fusion.service (EKF + decision engine)
   e. vista-db.service (InfluxDB + SQLite)
   f. vista-mqtt.service (MQTT broker)
   g. vista-api.service (Flask dashboard)
6. ESP32 advertises BLE: "VISTA-XXXX"
7. Phone connects via BLE → sends GPS data
8. System enters DRIVING-NORMAL mode
```

---

**Next:** See `02_HARDWARE_DESIGN.md` for detailed hardware specifications.
