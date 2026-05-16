# VISTA — Vehicle Intelligence & Safety Telematics Architecture

[![CI](https://github.com/AdityaPagare619/VISTA/actions/workflows/ci.yml/badge.svg)](https://github.com/AdityaPagare619/VISTA/actions)
[![Status](https://img.shields.io/badge/status-v4.0%20verified-brightgreen)](https://github.com/AdityaPagare619/VISTA)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%204B-red)](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/)
[![Coprocessor](https://img.shields.io/badge/coprocessor-ESP32--C3-blue)](https://www.espressif.com/en/products/socs/esp32-c3)
[![Tests](https://img.shields.io/badge/tests-20%2F20%20passing-brightgreen)](src/vista/tests)
[![BOM](https://img.shields.io/badge/BOM-%E2%82%B95%2C770-yellow)](raw/DESIGN/DESIGN_v4/docs/02_HARDWARE_DESIGN.md)

> **Hybrid edge-cloud multi-modal vehicle intelligence platform for Indian road safety.**
> Final Year Project — Electronics & Telecommunication Engineering.
> Built on ₹5,770 of hardware. Verified: 19/19 modules, 20/20 tests, 3/3 SITL scenarios.

---

## What VISTA Is

VISTA is a vehicle-mounted intelligence system that fuses four physical sensing modalities — OBD-II vehicle bus data, inertial measurement, acoustic classification, and camera — to detect safety-critical events and respond autonomously.

The system runs on a Raspberry Pi 4B as the primary compute unit and an ESP32-C3 as a 5μA always-on sentinel. Together they provide:

**Crash Detection** — A 4-tier detection pipeline that distinguishes real collisions from potholes and speed bumps using temporal pattern analysis across IMU jerk signatures, YAMNet audio classification, OBD-II speed telemetry, and Gemini cloud vision.

**Ghost Key TSA (Theft Prevention)** — A temporal sequence analysis engine that defends against the three dominant modern vehicle theft vectors: relay attacks, CAN-bus injection, and master key duplication. It analyzes the physical sequence of events (BLE presence, door opening, seat occupancy, timing) rather than reacting to any single trigger. When theft is confirmed, a physical fuel pump relay is cut — a hardware-layer response that cannot be defeated by software.

**Predictive NVH Analytics** — A drivetrain health monitoring pipeline using FFT-based vibration analysis and a Gemini-powered "expert mechanic" report, enabling B2B insurance and fleet management integrations.

**Operational Visibility** — A SystemHealthMonitor that tracks sensor liveness and system resources every 30 seconds, ensuring fleet operators know the real-time health of each unit.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    VEHICLE SENSING LAYER                          │
│  OBD-II ELM327    MPU6050 IMU     USB Microphone   Pi Camera v3 │
│  /dev/ttyUSB0     I2C 0x68        16kHz mono        CSI-2 3MP   │
│  2 Hz actual      100 Hz          YAMNet window      On-demand   │
└─────────────────────────────┬────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────┐
│                HARDWARE ABSTRACTION LAYER (HAL)                    │
│  6 drivers with graceful demo-mode fallback                       │
│  System never crashes due to missing hardware                     │
└─────────────────────────────┬────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────┐
│                   INTELLIGENCE PIPELINE                            │
│                                                                    │
│  VelocityEKF          2-state Kalman: OBD + IMU fusion            │
│  CrashDetector        4-tier: jerk → audio → OBD → vision        │
│  AudioClassifier      YAMNet TFLite 4.1MB, 521 → 6 classes       │
│  TheftDetector        Ghost Key TSA: 4-layer temporal analysis    │
│  PredictiveAnalytics  NVH FFT + Gemini mechanic report            │
│  SystemHealthMonitor  Sensor liveness + CPU/RAM/temp              │
│  DecisionEngine       Weighted confidence, explainable output     │
│  CloudVision          Gemini 1.5-flash REST, 3 retries            │
└─────────────────────────────┬────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────┐         ┌─────────────────────────┐
│   COMMUNICATIONS    │         │   DATA STORAGE          │
│  Telegram (alerts)  │         │  SQLite (events, WAL)   │
│  MQTT (telemetry)   │         │  InfluxDB (time-series) │
│  BLE (proximity)    │         │  USB SSD primary        │
│  Buzzer (local)     │         │  (not SD card)          │
└─────────────────────┘         └─────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│              ESP32-C3 COPROCESSOR (ALWAYS-ON)                    │
│  Deep sleep: 5μA · PIR intrusion · BLE auth · MOSFET Pi power   │
│  Battery monitor · Heartbeat watchdog · 4-state machine          │
└──────────────────────────────────────────────────────────────────┘
```

---

## Hardware

**Total BOM: ₹5,770 (~$69 USD)** · **Recurring cloud cost: ₹0/month**

| Component | Purpose | Cost |
|---|---|---|
| Raspberry Pi 4B (4GB) | Main compute | ₹0 (owned) |
| ESP32-C3-DevKitM-1 | Always-on 5μA sentinel | ₹400 |
| ELM327 OBD-II (USB) | Vehicle CAN data | ₹500 |
| MPU6050 GY-521 | Crash + motion detection | ₹150 |
| Pi Camera v3 (IMX708) | Scene capture for Gemini | ₹1,800 |
| USB Microphone | YAMNet audio classification | ₹200 |
| HC-SR501 PIR | Parked intrusion detection | ₹80 |
| AO3401 P-MOSFET + 2N2222 | Pi power control circuit | ₹60 |
| Fuel pump relay module | Ghost Key physical immobilizer | ₹60 |
| DC-DC LM2596 (12V→5V) | Car power regulation | ₹300 |
| Kingston A400 SSD (120GB) | Event DB + images (not SD) | ₹900 |
| Misc (wires, resistors, enclosure) | Assembly | ₹320 |

> The USB SSD is mandatory, not optional. SQLite in WAL mode and InfluxDB write-heavy workloads destroy SD card flash cells within weeks.

See → [`raw/DESIGN/DESIGN_v4/docs/02_HARDWARE_DESIGN.md`](raw/DESIGN/DESIGN_v4/docs/02_HARDWARE_DESIGN.md) for complete pin diagrams, wiring schematics, and installation guide.

---

## Key Design Decisions

**Tiered sensor architecture, not equal weighting.**
The IMU responds in <10ms. Audio responds in ~50ms. OBD responds in 300–500ms. These sensors cannot be treated as equals. VISTA assigns them roles: IMU is the primary trigger, Audio is the fast corroborator, OBD is the async post-event confirmation.

**Hardware-layer theft response.**
A physical relay on the fuel pump power wire cannot be defeated by CAN-bus injection or any software attack. This is the architectural reason for choosing an analog relay over a CAN command.

**Persist before transmit.**
Crash events are written to SQLite before any Telegram alert is attempted. If the network fails, the event survives. This reversal of the naive "alert first" pattern is critical for forensic completeness.

**The cloud does what the edge cannot.**
Gemini 1.5-flash replaces 5 separate local vision models (object detection, scene classification, damage assessment, license plate reading, natural language reporting). One API call. Zero local compute overhead. Context-aware output in the owner's language.

**Every hardware claim must survive physics.**
OBD-II achieves 2–3 Hz in practice, not 10 Hz. Pi 4 cannot suspend-to-RAM. MPU6050 saturates at ±16g — deliberately configured at maximum range because real crashes produce 20–70g. These are not assumptions; they are measured facts baked into `config.yaml`.

---

## System Verification (May 16, 2026)

```
python -m pytest src/vista/tests/test_v3_quick.py
→ 20 passed, 0 failed

python scripts/demo_billion_dollar_architecture.py
→ theft_detected:    ✅ PASS
→ legitimate_passes: ✅ PASS
→ nvh_pipeline:      ✅ PASS
→ ALL SCENARIOS PASSED. Exit code: 0

Import check:
→ 19/19 modules importable (DEMO_MODE=true)
```

---

## Quick Start

```bash
git clone https://github.com/AdityaPagare619/VISTA.git
cd VISTA

# Configure API keys
cp src/vista/.env.example src/vista/.env
# Edit .env: add GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# Run in demo mode (no hardware needed)
cd src/vista
DEMO_MODE=true python run_dashboard.py
# Open http://localhost:5000

# Run on Raspberry Pi (production)
sudo ./scripts/deploy.sh
sudo systemctl start vista vista-dashboard
```

---

## Documentation

| Document | For |
|---|---|
| [DESIGN_v4/docs/README.md](raw/DESIGN/DESIGN_v4/docs/README.md) | Start here — index + reading order by team |
| [01 System Design](raw/DESIGN/DESIGN_v4/docs/01_SYSTEM_DESIGN.md) | Architecture, state machine, boot sequence, innovation claims |
| [02 Hardware Design](raw/DESIGN/DESIGN_v4/docs/02_HARDWARE_DESIGN.md) | **BOM, wiring diagrams, GPIO tables, relay circuit** |
| [03 Software Architecture](raw/DESIGN/DESIGN_v4/docs/03_SOFTWARE_ARCHITECTURE.md) | Package structure, module APIs, data schemas |
| [04 Operational Flows](raw/DESIGN/DESIGN_v4/docs/04_OPERATIONAL_FLOWS.md) | Crash timeline, Ghost Key sequence, NVH flow, EKF dropout |
| [05 Technology Stack](raw/DESIGN/DESIGN_v4/docs/05_TECHNOLOGY_STACK.md) | Dependencies, cloud config, deployment, CI/CD |
| [06 Demo Methodology](raw/DESIGN/DESIGN_v4/docs/06_DEMO_METHODOLOGY.md) | Dashboard walkthrough, exam scripts, verifiable claims |

---

## Project Structure

```
VISO-PROJECT/
├── README.md
├── pyproject.toml              ← pytest config
├── scripts/
│   ├── deploy.sh               ← One-command Pi deployment
│   └── demo_billion_dollar_architecture.py  ← SITL demo
├── .github/workflows/ci.yml    ← 4-job CI pipeline
└── src/vista/
    ├── main.py                 ← 5-phase initialization
    ├── config.yaml             ← All configuration
    ├── hal/                    ← 6 hardware drivers
    ├── intelligence/           ← 8 AI/ML modules
    ├── communication/          ← Telegram, MQTT, BLE
    ├── data/                   ← SQLite + InfluxDB
    ├── dashboard/              ← Flask-SocketIO web UI
    ├── esp32/main/main.c       ← 1,098 LOC C firmware
    ├── models/yamnet.tflite    ← 4.1MB real ML model
    └── tests/                  ← 20-test verified suite
```

---

## Team

| Role | Domain |
|---|---|
| **Hardware Lead** | Wiring, sensors, ESP32 firmware, relay circuit, vehicle installation |
| **AI/ML Engineer** | YAMNet training, Gemini integration, NVH baseline collection |
| **Data & Integration** | Dashboard, alerts, database, system integration, CI/CD |
| **Research & Docs** | IEEE paper, documentation, presentation, evaluation |

---

## License

MIT — use, modify, and build upon freely. Credit appreciated.
