# VISTA — Team Instructions & Task Breakdown
## CEO Directive: Who Does What & When

**Version:** 2.1 | **Date:** May 8, 2026 | **Status:** Code Complete — Hardware Integration Phase

---

## 📋 Team Structure

| Member | Role | Codename | Primary Domain |
|--------|------|----------|----------------|
| **Member 1** | Hardware Lead | `hw-lead` | Wiring, power, ESP32, enclosure, sensor testing |
| **Member 2** | AI/ML Engineer | `ml-engineer` | Audio CNN training, cloud vision integration, model tuning |
| **Member 3** | Data & Integration | `data-integrator` | Database setup, dashboard, alerts, system integration |
| **Member 4** | Research & Docs | `research-lead` | Paper writing, documentation, presentation, viva prep |

**Everyone also:** tests the system, practices the demo, reviews each other's work.

---

## 🔧 MEMBER 1 — Hardware Lead (`hw-lead`)

### Your Responsibility
You own everything that has wires. If it plugs in, it's yours.

### Files You Own
```
vista/hal/obd_reader.py       ← You test this with real OBD-II
vista/hal/imu_reader.py       ← You calibrate and verify
vista/hal/camera_capture.py   ← You mount and test
vista/hal/audio_capture.py    ← You position the mic
vista/hal/gpio_manager.py     ← You wire the buzzer + ESP32
vista/esp32/main/main.c       ← You flash this to ESP32
vista/esp32/CMakeLists.txt    ← Build config
vista/esp32/sdkconfig.defaults ← ESP32 settings
```

### Reference Docs
```
DESIGN/docs/02_HARDWARE_DESIGN.md    ← BOM, pinouts, wiring diagrams
DESIGN/docs/01_SYSTEM_DESIGN.md      ← System overview
```

### Step-by-Step Instructions

#### Phase 1: Procurement (Week 1)
```
[ ] Order all components from BOM (02_HARDWARE_DESIGN.md Section 2)
    Critical: ELM327 USB (not Bluetooth!), MPU6050, Pi Camera v3, USB Mic
[ ] Verify Raspberry Pi 4B boots and connects to WiFi
[ ] Flash Raspberry Pi OS (Bookworm 64-bit) to 32GB microSD
[ ] Enable SSH, I2C, Camera via raspi-config
```

#### Phase 2: Sensor Bench Testing (Week 1-2)
```
[ ] TEST 1: MPU6050 IMU
    - Wire: VCC→3.3V, GND→GND, SDA→GPIO2, SCL→GPIO3
    - Run: sudo i2cdetect -y 1 (should see 0x68)
    - Run: python hal/imu_reader.py (test script)
    - Verify: acceleration values change when you move the sensor
    - Calibrate: hold still, run calibrate(), verify gyro near zero

[ ] TEST 2: OBD-II ELM327
    - Plug ELM327 into car's OBD-II port (under dashboard)
    - Connect USB to Pi
    - Run: ls /dev/ttyUSB* (should see /dev/ttyUSB0)
    - Run: python hal/obd_reader.py (test script)
    - Verify: speed, rpm, throttle values update when car is running
    - Note: some cars need ignition ON for OBD data

[ ] TEST 3: Pi Camera v3
    - Connect ribbon cable to CSI port (blue side facing Ethernet)
    - Run: libcamera-hello --list-cameras
    - Run: libcamera-jpeg -o test.jpg
    - Run: python hal/camera_capture.py (test script)
    - Verify: image is clear, autofocus works

[ ] TEST 4: USB Microphone
    - Plug into any USB port
    - Run: arecord -l (should list the device)
    - Run: arecord -d 3 test.wav && aplay test.wav
    - Run: python hal/audio_capture.py (test script)
    - Verify: audio captured, no distortion

[ ] TEST 5: PIR Sensor (with ESP32)
    - Wire PIR: VCC→5V, GND→GND, OUT→ESP32 GPIO0
    - Flash ESP32 with vista/esp32 firmware
    - Walk past PIR → ESP32 LED should change
    - Verify: ESP32 wakes Pi via GPIO
```

#### Phase 3: ESP32 Flashing (Week 2)
```bash
# 1. Install ESP-IDF v5.2+ (one-time setup)
# Follow: https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32c3/get-started/

# 2. Build and flash
cd vista/esp32
idf.py set-target esp32c3
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor

# 3. Verify
# ESP32 should:
# - Enter deep sleep, wake every 1 second
# - BLE advertise: "VISTA-0001" visible on phone
# - PIR triggers → "VISTA-THEFT-ALERT" BLE name appears
# - Wake Pi via GPIO4 when PIR triggered
```

#### Phase 4: Power & Enclosure (Week 3)
```
[ ] Wire DC-DC converter: Car 12V → 5V/3A output
    - Input: car battery + and -
    - Output: 5V to Pi GPIO pins 2 (5V) and 6 (GND)
    - IMPORTANT: test output voltage = 5.0V ±0.1V BEFORE connecting Pi

[ ] Wire buzzer: + to GPIO17, - to GND

[ ] ESP32 to Pi wiring:
    ESP32 GPIO4 → Pi GPIO5   (ESP32 wakes Pi)
    ESP32 GPIO6 → Pi GPIO6   (Pi heartbeat to ESP32)
    ESP32 5V → Pi 5V pin     (ESP32 powered from Pi)
    ESP32 GND → Pi GND

[ ] Test full power chain:
    - Car battery → DC-DC → Pi boots → ESP32 boots → all sensors alive

[ ] 3D print enclosure (ABS filament — NOT PLA)
    - File: DESIGN/docs/02_HARDWARE_DESIGN.md Section 5
    - Ventilation slots on top and sides
    - Camera ribbon cable slot
    - USB port access
```

#### Phase 5: Vehicle Installation (Week 4)
```
[ ] Mount enclosure under dashboard or under seat
[ ] Route OBD-II cable (keep away from pedals!)
[ ] Position camera: windshield, behind rear-view mirror
[ ] Position microphone: near dashboard center
[ ] Secure all cables with zip ties
[ ] Verify: all sensors work when car is running
[ ] Record 30-minute test drive → check InfluxDB has data
```

---

## 🤖 MEMBER 2 — AI/ML Engineer (`ml-engineer`)

### Your Responsibility
You own the intelligence. Audio CNN training, cloud vision prompts, model accuracy, decision thresholds.

### Files You Own
```
vista/intelligence/audio_classifier.py    ← Your CNN inference code
vista/intelligence/cloud_vision.py        ← Your Gemini API client
vista/intelligence/decision_engine.py     ← Your explainable AI (tune thresholds)
vista/models/                             ← Your trained models go here
```

### Reference Docs
```
DESIGN/docs/03_SOFTWARE_ARCHITECTURE.md   ← Module specs, class APIs
DESIGN/docs/04_OPERATIONAL_FLOWS.md       ← Crash detection sequence
```

### Step-by-Step Instructions

#### Phase 1: Audio Data Collection (Week 1-2)
```
[ ] Collect crash sounds:
    - Search: "NHTSA crash test audio", "IIHS crash sound", "car crash sound effect"
    - Target: 20-30 distinct crash recordings (different angles, severities)

[ ] Collect siren sounds:
    - Record or download: Indian ambulance, police, fire brigade sirens
    - Target: 15-20 recordings per siren type
    - IMPORTANT: Indian sirens differ from Western ones!

[ ] Collect horn sounds:
    - Record: different car horn patterns (short, long, rhythmic)
    - Record: two-wheeler horns (different frequency)

[ ] Collect normal driving sounds:
    - Record: engine, wind, music, conversation, road noise
    - Target: 50+ minutes of varied normal audio

[ ] Organize data:
    data/audio_dataset/
    ├── crash/        (25 files)
    ├── horn/         (20 files)
    ├── siren_ambulance/  (15 files)
    ├── siren_police/     (15 files)
    ├── siren_fire/       (10 files)
    └── normal/       (50 files)
```

#### Phase 2: Train Audio CNN (Week 2-3)
```python
# Training script (create: scripts/train_audio_cnn.py)

# 1. Load all audio files, convert to mel-spectrograms
# 2. Split: 80% train, 10% validation, 10% test
# 3. Architecture: 3 Conv2D layers + GlobalAvgPool + Dense(6)
#    Conv1: 32 filters, 3x3 kernel, ReLU
#    Conv2: 64 filters, 3x3 kernel, ReLU, MaxPool
#    Conv3: 128 filters, 3x3 kernel, ReLU, MaxPool
#    Dense: 128 units, Dropout(0.3)
#    Output: 6 classes, softmax
# 4. Train for 50 epochs, batch_size=32
# 5. Target accuracy: >85% on test set
# 6. Convert to TFLite with INT8 quantization
# 7. Save to: models/audio_cnn.tflite

# Verify:
python intelligence/audio_classifier.py --test
# Should show: accuracy >85%, model size <3MB
```

#### Phase 3: Cloud Vision Tuning (Week 3)
```
[ ] Test Gemini Vision API with sample images:
    - Take photos of: empty road, traffic, parked cars, accident scenes (from internet)
    - Run: python intelligence/cloud_vision.py --test
    - Verify: API returns structured JSON with scene_type, vehicles, hazards

[ ] Tune the prompt engineering:
    - Edit: intelligence/cloud_vision.py → PROMPT_TEMPLATE
    - Ensure Indian-specific terms work (auto-rickshaw, cow, pothole, speed breaker)
    - Test: "Show a picture of a cow on the road → API should identify it"

[ ] Measure API latency:
    - Average: should be 1-3 seconds
    - Max acceptable: 5 seconds
```

#### Phase 4: Threshold Tuning (Week 4)
```
[ ] Tune crash detection thresholds:
    - Edit: config.yaml → decision.crash
    - Test with controlled IMU shakes (hard shake = crash, gentle shake = pothole)
    - Goal: <1 false alarm per day, >90% true crash detection

[ ] Test explainable decision engine:
    - Generate test scenarios (normal, crash, harsh braking)
    - Verify: evidence chain makes logical sense
    - Verify: confidence scores are reasonable (not always 100% or always 50%)

[ ] Document model performance:
    - Audio CNN: confusion matrix, accuracy, F1 score per class
    - Crash detection: precision, recall, false positive rate
    - Cloud vision: response time distribution, accuracy on Indian scenes
```

---

## 📊 MEMBER 3 — Data & Integration Lead (`data-integrator`)

### Your Responsibility
You own the data pipeline, dashboard, alerts, and system integration. You're the one who makes everything work together.

### Files You Own
```
vista/main.py                          ← System entry point (you will run this)
vista/data/influx_writer.py            ← Time-series storage
vista/data/sqlite_manager.py           ← Event database
vista/communication/mqtt_manager.py    ← Message broker
vista/communication/alert_manager.py   ← Alert routing (Telegram!)
vista/dashboard/app.py                 ← Web dashboard
vista/dashboard/templates/index.html   ← Dashboard UI
vista/dashboard/static/dashboard.js    ← Real-time updates
vista/config.yaml                      ← System configuration
vista/.env                             ← API keys
vista/scripts/install.sh               ← Pi setup script
vista/services/*.service               ← systemd services
vista/demo/demo_orchestrator.py        ← Classroom demo script
```

### Reference Docs
```
DESIGN/docs/05_TECHNOLOGY_STACK.md     ← Install commands, dependencies
DESIGN/docs/06_DEMO_EVALUATION_METHODOLOGY.md ← Demo strategy
DESIGN/docs/04_OPERATIONAL_FLOWS.md    ← Event sequences
```

### Step-by-Step Instructions

#### Phase 1: Environment Setup (Week 1)
```bash
# 1. Run the install script on the Pi
cd /home/pi/vista
chmod +x scripts/install.sh
sudo ./scripts/install.sh

# 2. Verify everything installed
python -c "import obd; import cv2; import tflite_runtime; print('OK')"

# 3. Start systemd services
sudo systemctl start vista
sudo systemctl start vista-dashboard

# 4. Check logs
journalctl -u vista -f        # Main system logs
journalctl -u vista-dashboard -f  # Dashboard logs
```

#### Phase 2: Database Verification (Week 1-2)
```
[ ] Verify InfluxDB:
    - Open: http://pi-ip:8086
    - Login: vista / vista123 (from install script)
    - Check: vista_telemetry bucket exists
    - Query: SELECT * FROM telemetry LIMIT 10 (after test drive)

[ ] Verify SQLite:
    - Run: python -c "from data.sqlite_manager import SQLiteManager; 
              db = SQLiteManager(); print(db.get_stats())"
    - Check: events, daily_reports, audit_log tables exist

[ ] Verify Grafana:
    - Open: http://pi-ip:3000
    - Login: admin / admin
    - Add InfluxDB data source → vista_telemetry bucket
    - Create dashboard with: speed graph, rpm gauge, audio class indicator
```

#### Phase 3: Alert System Testing (Week 2)
```
[ ] Register Telegram bot:
    1. Open Telegram on your phone
    2. Search for your bot: @VISTA_Alert_Bot (or whatever name you set)
    3. Send /start to the bot
    4. Check: data/telegram_chat_id.txt was created
    5. Run: python communication/alert_manager.py --test
    6. Verify: test alert arrives on your Telegram

[ ] Test MQTT:
    - Install MQTT client on phone: "MQTT Dashboard" app
    - Connect to: pi-ip:1883
    - Subscribe: vista/VISTA-0001/#
    - Run system → verify messages appear

[ ] Test BLE:
    - Open phone Bluetooth settings
    - Should see: "VISTA-0001" in device list
    - Connect with nRF Connect app
    - Read STATUS characteristic → verify data
```

#### Phase 4: Full System Integration (Week 3-4)
```bash
# 1. Start the system in driving mode
cd /home/pi/vista
python main.py --mode driving

# 2. Verify all subsystems:
#    - Terminal shows sensor data streaming
#    - Dashboard at http://pi-ip:5000 shows live data
#    - InfluxDB receiving telemetry points
#    - SQLite logging events
#    - MQTT messages flowing

# 3. Simulate crash (for testing):
python main.py --mode demo --demo-scenario crash
#    - Verify: buzzer sounds, camera captures, Telegram alert received

# 4. Run 1-hour real drive test:
#    - Start: python main.py --mode driving
#    - Drive normally for 1 hour on Indian roads
#    - After: check InfluxDB has 36,000+ data points
#    - Check: Grafana shows speed graphs, events
```

#### Phase 5: Demo Practice (Ongoing)
```
[ ] Practice the crash demo (06_DEMO_EVALUATION_METHODOLOGY.md):
    - Run: python demo/demo_orchestrator.py --demo crash
    - Time yourself: should complete in under 4 minutes
    - Practice 5+ times until smooth

[ ] Practice the theft demo:
    - ESP32 armed, Pi sleeping
    - Walk past PIR → system wakes → alert sent
    - Time: should be under 15 seconds from PIR to alert

[ ] Prepare backup plan:
    - Record screen + camera video of full demo
    - Save to USB drive (backup if live fails)
```

---

## 📝 MEMBER 4 — Research & Documentation Lead (`research-lead`)

### Your Responsibility
You own the story. Research paper, project report, presentation, viva defense. You make us look good on paper.

### What You Write
```
1. IEEE-format research paper (6-8 pages)
2. Final project report (from DESIGN/VISTA_PR_REPORT.md — already drafted!)
3. Viva presentation (PowerPoint/Google Slides, 15-20 slides)
4. Project poster (A0 size, for display)
5. Demo video script
```

### Reference Docs (Read ALL of these first)
```
DESIGN/VISTA_PR_REPORT.md              ← Master document — everything is here
DESIGN/docs/01-06 (all design docs)    ← Technical details
RESEARCH/VISO_DEEP_RESEARCH_SYNTHESIS.md ← Background research
```

### Step-by-Step Instructions

#### Phase 1: Research Paper (Weeks 1-4)

**Target Venue:** IEEE Sensors Conference / MDPI Sensors / INTERSPEECH / ACM DEV

**Paper Structure (IEEE format, 6-8 pages):**

```
Title: VISTA: Hybrid Edge-Cloud Multi-Modal Vehicle Intelligence 
       Platform for Indian Road Safety

Abstract (150-200 words):
- Problem: Indian roads see 150K deaths/year, no affordable vehicle safety
- Solution: Hybrid edge-cloud platform fusing OBD-II, IMU, audio, camera on Pi 4
- Innovation: Multi-modal fusion + audio CNN + cloud vision API + explainable AI
- Results: Crash detection accuracy >90%, BOM cost ₹3,500, 45-day parked battery
- Impact: Democratizing vehicle safety for Indian conditions

Section 1: Introduction (1 page)
- Indian road safety statistics (cite MoRTH, NCRB data)
- Why existing solutions fail (too expensive, too simple, wrong assumptions)
- Our approach: smart engineering — use what exists, cloud for intelligence

Section 2: Related Work (1 page)
- Vehicle safety systems (Mobileye, Bosch — expensive, Western-focused)
- Edge AI for automotive (cite arXiv papers found in research)
- Audio-based event detection (cite IEEE ICASSP papers)
- Gap: No multi-modal Pi-based system for Indian conditions

Section 3: System Architecture (2 pages)
- Hardware: Pi 4 + ESP32-C3 + 5 sensors (BOM ₹3,500)
- Software: Hybrid edge-cloud (local safety + cloud intelligence)
- Sensor fusion: Extended Kalman Filter (OBD + IMU)
- Audio CNN: 6-class classifier (crash, siren×3, horn, normal)
- Cloud: Gemini Vision API for unlimited scene understanding
- Power: ESP32 sleepy-edge (5μA deep sleep → 45-day parked battery)

Section 4: Explainable Decision Engine (1 page)
- Multi-factor weighted confidence scoring
- Evidence chain: per-sensor confidence + justification
- Graceful degradation: redistribute weights when sensors fail
- Example: "Crash 92%: IMU 7.2g/s + OBD throttle 100% drop + Audio 91%"

Section 5: Experimental Results (1 page)
- Audio CNN: accuracy, confusion matrix (from ml-engineer's testing)
- Crash detection: controlled tests with known G-forces
- Cloud API: latency distribution, scene analysis accuracy
- Power: measured consumption in all modes
- Demo: classroom testing methodology

Section 6: Discussion & Future Work (0.5 page)
- Limitations: OBD data simulated in demo, audio dataset size
- Future: vehicle-to-vehicle mesh, federated learning, production hardening
- Indian deployment: cost analysis, scalability

References (0.5 page)
- 15-20 citations from IEEE, ACM, arXiv, Indian government sources
```

**Writing Schedule:**
```
Week 1: Sections 1-2 (Introduction + Related Work) — send to supervisor for feedback
Week 2: Sections 3-4 (Architecture + Explainable AI)
Week 3: Section 5 (Results) — NEED DATA from ml-engineer + data-integrator!
Week 4: Polish, citations, formatting, submit to conference
```

#### Phase 2: Final Project Report (Weeks 3-6)

**Starting point:** `DESIGN/VISTA_PR_REPORT.md` is already 80% complete.

**What you need to add:**
```
[ ] Actual results from testing (replace "Expected" with measured values)
[ ] Photos of: hardware setup, vehicle installation, dashboard screenshots
[ ] Team member contributions section
[ ] Acknowledgements (supervisor, department, funding if any)
[ ] Appendices: full BOM with purchase links, wiring diagram, test logs
```

#### Phase 3: Viva Presentation (Weeks 5-6)

**Slide Deck (15-20 slides):**

```
Slide 1:  Title — VISTA: Vehicle Intelligence Platform
Slide 2:  The Problem — Indian road deaths, no affordable safety
Slide 3:  Why Existing Solutions Fail — cost, simplicity, Western bias
Slide 4:  Our Solution — 4-sentence overview
Slide 5:  Innovation Map — 7 innovation claims
Slide 6:  System Architecture — big diagram
Slide 7:  Hardware — BOM, cost comparison, smart engineering
Slide 8:  Sensor Fusion — EKF diagram, explain with simple math
Slide 9:  Audio CNN — how it works, accuracy results
Slide 10: Cloud Vision — Gemini API, one API replaces 5 models
Slide 11: Explainable AI — evidence chain example
Slide 12: Power Architecture — ESP32 sleepy-edge, 45-day battery
Slide 13: Results — accuracy, latency, power numbers
Slide 14: LIVE DEMO (transition to physical demo)
Slide 15: Demo: Normal Operation
Slide 16: Demo: Crash Detection
Slide 17: Demo: Theft Detection
Slide 18: Comparison — VISTA vs commercial vs student projects
Slide 19: Future Work & Publications
Slide 20: Thank You + Q&A
```

#### Phase 4: Supporting Materials

```
[ ] Project Poster (A0):
    - Title, team, department
    - System diagram (big, visual)
    - Key innovations (icons + 1-liners)
    - Results highlights (big numbers)
    - QR code → GitHub repo + demo video

[ ] Demo Video Script (3-5 minutes):
    - Part 1: Problem intro (30 sec)
    - Part 2: Hardware walkthrough (1 min)
    - Part 3: System in action (car installation footage) (1 min)
    - Part 4: Dashboard + alerts (30 sec)
    - Part 5: Crash detection demo (1 min)
    - Part 6: Innovation summary (30 sec)

[ ] 2-Page Project Brief:
    - 1-page summary for non-technical audience
    - 1-page technical details for faculty
```

---

## 🔄 Cross-Team Dependencies

```
MEMBER 1 (hw-lead)
    │
    │ Provides: working sensors, ESP32, vehicle installation
    │
    ├──────────────────────────────────────────────┐
    │                                              │
    ▼                                              ▼
MEMBER 2 (ml-engineer)                    MEMBER 3 (data-integrator)
    │                                          │
    │ Needs: audio/camera/IMU data             │ Needs: working sensors
    │ from real sensors                        │ to test pipeline
    │                                          │
    │ Provides: trained models,                │ Provides: working system,
    │ accuracy results, tuned thresholds       │ demo flow, dashboard
    │                                          │
    └──────────────┬───────────────────────────┘
                   │
                   ▼
            MEMBER 4 (research-lead)
                │
                │ Needs: results from ALL members
                │ to write paper + presentation
                │
                └── Everyone must provide their results by Week 3!
```

---

## 📅 Timeline (8 Weeks to Viva)

| Week | hw-lead | ml-engineer | data-integrator | research-lead |
|------|---------|-------------|-----------------|---------------|
| **1** | Order components, bench test IMU+OBD | Collect audio dataset | Run install.sh, verify DBs | Read all design docs, outline paper |
| **2** | Flash ESP32, test PIR | Train audio CNN v1 | Set up alerts (Telegram, MQTT) | Write paper Sections 1-2 |
| **3** | Power chain + enclosure | Tune cloud vision, test CNN | Full system integration test | Write paper Sections 3-4 |
| **4** | Vehicle installation, test drive | Provide accuracy results | 1-hour real drive data collection | Get results from team, write Section 5 |
| **5** | Fix any hardware issues | Tune decision thresholds | Demo practice (crash + theft) | Finish paper draft, start slides |
| **6** | Final hardware polish | Final model tuning | Record demo video | Finalize presentation, poster |
| **7** | ALL: Full dress rehearsal (3x) | ALL: Fix issues found | ALL: Backup plans ready | ALL: Practice Q&A |
| **8** | **VIVA DAY** 🎯 | | | |

---

## ⚡ Quick Reference — Key Commands

```bash
# Run the system
python main.py --mode driving           # Real driving mode
python main.py --mode demo --demo-scenario crash   # Classroom crash demo
python main.py --mode parked            # Parked monitoring

# Dashboard
python run_dashboard.py                 # Start web dashboard
# Open: http://pi-ip:5000

# Test individual sensors
python hal/obd_reader.py --test
python hal/imu_reader.py --test
python hal/camera_capture.py --test
python hal/audio_capture.py --test

# Demo tools
python demo/obd_simulator.py --port /tmp/obd_sim    # Start OBD simulator
python demo/demo_orchestrator.py --demo crash        # Run crash demo

# ESP32
cd esp32 && idf.py build flash monitor

# Check system status
sudo systemctl status vista vista-dashboard
journalctl -u vista -n 50 --no-pager

# Database queries
influx -execute 'SELECT * FROM telemetry LIMIT 10' -database=vista_telemetry
python -c "from data.sqlite_manager import SQLiteManager; db=SQLiteManager(); print(db.get_stats())"
```

---

## 🆘 Getting Help

| Problem | Ask | Where |
|---------|------|-------|
| Hardware doesn't work | hw-lead | Check `02_HARDWARE_DESIGN.md` |
| Code doesn't run | data-integrator | Check logs: `journalctl -u vista` |
| Model not accurate | ml-engineer | Check `03_SOFTWARE_ARCHITECTURE.md` |
| Don't understand architecture | research-lead (they read everything) | Check `VISTA_PR_REPORT.md` |
| Need to change design | All — discuss together | Check design docs first |

---

**CEO Sign-off:** Code complete. Hardware integration in progress. Research paper in draft. Demo strategy defined. Viva-ready in 8 weeks.

**Go build.** 🚀
