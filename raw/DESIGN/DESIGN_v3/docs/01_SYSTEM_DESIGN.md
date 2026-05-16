# 01 — System Design Document v3.0
## VISTA: Vehicle Intelligence & Safety Telematics Architecture

**Version:** 3.0 | **Status:** Final — Physics-Verified | **Date:** May 10, 2026

---

## 1. System Overview

VISTA is a **hybrid edge-cloud vehicle intelligence platform** running on a Raspberry Pi 4B with an ESP32-C3 coprocessor. It fuses 4 sensing modalities (OBD-II, IMU, Audio, Camera) using a **tiered detection architecture** — sensors are assigned roles by physical response time, not treated as equals.

### 1.1 Core Design Philosophy

> **"Every claim must survive contact with physics."** Use what Pi already has (WiFi/BLE). Use what the phone already has (GPS/Display). Use what the cloud does best (vision AI). And verify every timing assumption against real hardware.

### 1.2 Tiered Sensor Architecture

| Tier | Sensor | Sample Rate | Latency | Role |
|------|--------|------------|---------|------|
| **T1: Instant** | IMU (MPU6050) | 100 Hz | <10ms | PRIMARY crash/motion detector |
| **T2: Fast** | Audio CNN | 25 Hz (1s windows) | ~50ms | SECONDARY crash corroboration |
| **T3: Async** | OBD-II (ELM327) | 2-3 Hz actual | 300-1000ms | POST-EVENT confirmation |
| **T4: Enrichment** | Camera + Cloud API | On-demand | 2-5s | Scene understanding |

> **Why tiered?** ELM327 USB adapters achieve 7-12 individual PIDs/sec. With 4 PIDs needed, effective rate is 2-3 complete reads/second. Pretending OBD is "10Hz real-time" would produce a design that fails in real vehicles.

---

## 2. System States & Modes

### 2.1 State Machine

```
                    ┌──────────┐
                    │  POWER   │ (12V applied to DC-DC)
                    │  APPLIED │
                    └────┬─────┘
                         │ ESP32 boots (200ms)
                         ▼
                    ┌──────────┐
                    │  ESP32   │ (Checks battery, temp)
                    │  INIT    │
                    └────┬─────┘
                         │
              ┌──────────┴──────────┐
              │                     │
         OBD RPM>0              OBD RPM=0 or
         (Ignition ON)          No OBD signal
              │                     │
              ▼                     ▼
        ┌──────────┐          ┌──────────┐
        │ DRIVING  │          │  PARKED  │
        │  MODE    │          │  MODE    │
        │          │          │          │
        │ Pi: ON   │          │ Pi: OFF  │
        │ (MOSFET) │          │ (MOSFET) │
        └────┬─────┘          └────┬─────┘
             │                     │
    ┌────────┼────────┐     ┌──────┼──────┐
    ▼        ▼        ▼     ▼      ▼      ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│NORMAL│ │CRASH │ │ALERT │ │SLEEP │ │THEFT │
│DRIVE │ │EVENT │ │DRIVE │ │ 5μA  │ │ALERT │
└──────┘ └──┬───┘ └──────┘ └──────┘ └──┬───┘
            │                           │
            ▼                           ▼
       ┌────────────────┐    ┌────────────────┐
       │  EMERGENCY     │    │  Pi BOOTS      │
       │  RESPONSE      │    │  (35s cold     │
       │  (Enriched     │    │   boot)        │
       │   Alert)       │    │  Camera+API    │
       └────────────────┘    └────────────────┘
```

### 2.2 Mode Definitions (Physics-Verified)

| Mode | Trigger | Pi State | ESP32 State | Pi Power | Boot Time |
|------|---------|----------|-------------|----------|-----------|
| **DRIVING-NORMAL** | OBD RPM > 0 | Active | Active | 8W (MOSFET ON) | Already booted |
| **DRIVING-CRASH** | IMU jerk >5g/s | Active | Active | 8W | Already booted |
| **PARKED-SLEEP** | Ignition OFF + 5min | **OFF (MOSFET)** | Deep sleep (5μA) | **0W** | N/A |
| **PARKED-ALERT** | PIR triggered | **Booting (cold)** | Active | 8W for ~5min | **35 seconds** |
| **THEFT-MODE** | User arms via phone | **OFF (MOSFET)** | Active (PIR+BLE) | **0W** | 35s when triggered |
| **LOW-BATTERY** | VBAT < 11.8V | **OFF (MOSFET forced)** | Active (BLE only) | **0W** | Blocked |
| **THERMAL-BLOCK** | Ambient > 55°C | **OFF (MOSFET blocked)** | Active (BLE alert) | **0W** | Blocked until cool |

> **Key difference from v2.1:** Pi is truly OFF when not needed (MOSFET cuts power). No "deep sleep" fiction. Boot time is honest 35 seconds, not 10 seconds.

---

## 3. Data Architecture

### 3.1 Data Types & Storage (on USB SSD)

| Data Type | Source | Actual Rate | Storage | Retention |
|-----------|--------|-------------|---------|-----------|
| OBD-II PIDs | ELM327 | **2-3 Hz** (verified) | InfluxDB (USB SSD) | 30 days |
| IMU raw | MPU6050 | 100 Hz | InfluxDB (USB SSD) | 7 days (downsampled) |
| IMU fused velocity | EKF output | **2-3 Hz** (matches OBD) | InfluxDB | 30 days |
| Audio features | CNN preprocessing | 25 Hz | Not stored (streaming) | — |
| Audio events | CNN classification | On-event | SQLite (USB SSD) | 90 days |
| Camera images | Pi Cam v3 | On-event | USB SSD (JPEG) | 30 days or 500MB cap |
| System events | Decision engine | On-event | SQLite (USB SSD) | 90 days |
| Cloud API responses | Gemini Vision | On-event | SQLite (linked) | 90 days |

### 3.2 Data Flow — Normal Driving (Corrected Timing)

```
T=0ms      OBD-II poll sent (PID 0x0D: speed)
T=100ms    OBD response: speed=45 km/h
T=100ms    OBD poll: PID 0x0C: rpm
T=200ms    OBD response: rpm=2100
T=200ms    OBD poll: PID 0x11: throttle
T=300ms    OBD response: throttle=32%
           (3 PIDs in ~300ms = ~3Hz per-PID, ~1Hz full cycle)

T=0-10ms   IMU reads at 100Hz (independent of OBD)
           ax=0.1, ay=-0.05, az=1.02

T=0-40ms   Audio: 16000 samples filling 1-sec window
T=40ms     Audio CNN: [normal: 0.98, crash: 0.01, ...]

T=400ms    EKF update: OBD speed + integrated IMU accel → fused velocity
T=410ms    Write to InfluxDB on USB SSD

T=500ms    Next OBD cycle begins
```

### 3.3 Data Flow — Crash Detection (Physics-Verified)

```
T=0ms      IMU interrupt: |jerk| = 7.2g/s (THRESHOLD EXCEEDED)
           Note: If real crash exceeds ±16g, sensor saturates.
           Saturation itself confirms severe event.

T=10ms     Flag potential crash; capture pre/post buffer

T=50ms     Audio CNN on last window: [crash: 0.91, normal: 0.06]

T=100ms    PRELIMINARY DECISION (IMU + Audio only):
           IMU: min(7.2/5.0, 1.0) = 1.00 × 0.45 = 0.450
           Audio: 0.91 × 0.30 = 0.273
           ───────────────────────────────────────
           PRELIMINARY: 0.723 > 0.65 → CRASH CONFIRMED
           → Buzzer ON, BLE alert sent

T=200ms    Camera: burst capture (5 frames)

T=500ms    OBD next poll arrives:
           Speed: 45→12 km/h, Throttle: 32%→0%
           OBD: min(100/50, 1.0) = 1.00 × 0.15 = 0.150
           UPDATED: 0.723 + 0.150 = 0.873

T=2000ms   Cloud Vision API response (if WiFi):
           "Front-end collision with barrier."
           Vision: 1.0 × 0.10 = 0.100
           FINAL: 0.873 + 0.100 = 0.973

T=2200ms   Enriched alert via Telegram
```

---

## 4. Component Interaction Matrix

| Component | OBD-II | IMU | Audio | Camera | ESP32 | Cloud API | Phone |
|-----------|--------|-----|-------|--------|-------|-----------|-------|
| **OBD-II** | — | EKF velocity fusion | — | — | — | — | — |
| **IMU** | EKF velocity fusion | — | Both feed crash detector | — | — | — | — |
| **Audio** | — | Both feed crash detector | — | — | — | — | — |
| **Camera** | — | — | — | — | — | Image → API | — |
| **ESP32** | — | — | — | — | — | — | BLE status |
| **Cloud API** | — | — | — | Image input | — | — | Enriched alert |
| **Phone** | — | — | — | — | GPS via BLE | — | — |

---

## 5. Failure Modes & Graceful Degradation

| Failure | Detection Method | System Behavior | Max Confidence Available |
|---------|-----------------|-----------------|------------------------|
| OBD-II disconnected | Connection check fails | IMU+Audio crash detection continues | 0.75 (sufficient) |
| IMU failure | I2C read error | OBD speed-rate + Audio only | 0.45 (below threshold → warning only) |
| Audio mic failure | PyAudio error | IMU+OBD detection continues | 0.60 (marginal) |
| Camera failure | picamera2 error | Text-only alerts | All sensors functional |
| WiFi unavailable | Network check | Core safety 100%; images queued | All sensors functional |
| ESP32 failure | No heartbeat | Pi stays on (no parked power management) | All sensors functional |
| Cloud API down | HTTP error/timeout | Alerts without vision enrichment | 0.90 max (still strong) |
| USB SSD failure | Mount check | Events sent as alerts but not logged | All sensors functional |
| Ambient > 55°C | ESP32 temp sensor | Pi boot blocked; BLE-only alerts | N/A (ESP32 alert only) |

---

## 6. Team Module Ownership

| Module | Primary Owner | Skills Required |
|--------|--------------|-----------------|
| **OBD-II Pipeline + EKF** | Hardware Specialist | Python, serial protocols, Kalman filtering |
| **IMU + Crash Detector** | Hardware Specialist | Signal processing, threshold tuning |
| **Audio CNN** | AI/ML Specialist | TFLite, audio DSP, model training |
| **Camera + Cloud Vision** | AI/ML Specialist | REST APIs, prompt engineering |
| **ESP32 Firmware (MOSFET + PIR)** | Hardware Specialist | C/C++, ESP-IDF, power management |
| **Decision Engine** | Data Analytics | Python, weighted fusion, explainability |
| **Database + Dashboard** | Data Analytics | InfluxDB, SQLite, Grafana, Flask |
| **Communication (MQTT/BLE/Telegram)** | Data Analytics | MQTT, BlueZ, Telegram Bot API |

---

## 7. System Startup Sequence (Cold Boot — 35 seconds)

```
1. Car ignition ON → DC-DC converter powers up
2. ESP32-C3 boots (200ms) → checks battery voltage + ambient temp
3. If VBAT < 11.8V: BLOCK Pi boot, BLE alert "Low battery"
4. If ambient > 55°C: BLOCK Pi boot, BLE alert "Too hot — waiting for AC"
5. ESP32 switches MOSFET ON → Pi receives 5V power
6. Pi cold boots Raspberry Pi OS (~30-35s)
7. Systemd starts VISTA services (staggered):
   a. vista-obd.service → connects ELM327
   b. vista-imu.service → calibrates MPU6050
   c. vista-audio.service → starts audio capture + CNN
   d. vista-fusion.service → starts EKF + crash detector
   e. vista-db.service → mounts USB SSD, starts InfluxDB
   f. vista-mqtt.service → starts Mosquitto broker
   g. vista-api.service → starts Flask dashboard
8. Pi sends heartbeat on GPIO6 (1Hz toggle)
9. ESP32 confirms Pi alive; advertises BLE "VISTA-XXXX"
10. Phone connects via BLE → sends GPS data
11. System enters DRIVING-NORMAL mode
```

---

**Next:** See `02_HARDWARE_DESIGN.md` for complete wiring and power architecture.
