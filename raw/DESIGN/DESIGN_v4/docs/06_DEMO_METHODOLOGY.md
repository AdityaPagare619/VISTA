# 06 — Demo & Evaluation Methodology v4.0
## VISTA: SITL Demo Script, Dashboard Walkthrough & Expected Outputs

**Version:** 4.0 | **Status:** Verified SITL EXIT 0 | **Date:** May 16, 2026

---

## 1. Demo Philosophy

VISTA demos in two modes:

| Mode | When | Hardware Needed | What Works |
|---|---|---|---|
| **SITL (Software-in-the-Loop)** | Demo room, examiners | Laptop only | All algorithms, real Gemini, real Telegram |
| **HITL (Hardware-in-the-Loop)** | Vehicle, field demo | Pi + full BOM | Everything + real sensor data |

**Key principle:** In SITL mode, algorithms are REAL. Only sensor data is simulated. The Gemini API calls are live. The Telegram alerts land on a real phone. The Ghost Key TSA actually analyzes temporal sequences.

---

## 2. Pre-Demo Checklist

```
□  Internet connection available (Gemini API + Telegram)
□  .env configured: GEMINI_API_KEY + TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
□  Telegram app open on phone (alerts arrive here)
□  Dashboard running: python run_dashboard.py
□  Browser open at http://localhost:5000
□  DEMO_MODE=true in .env (or set env var)

Quick start:
  cd src/vista
  DEMO_MODE=true python run_dashboard.py
  # Open http://localhost:5000 in browser
```

---

## 3. Dashboard Walkthrough

### 3.1 What the Examiner Sees

```
┌─────────────────────────────────────────────────────────────────┐
│  VISTA  Vehicle Intelligence & Safety Telematics v4.0    ●ONLINE│
│                                              Clock: 13:45:37.952 │
├──────────┬──────────┬───────────┬──────────┬────────┬──────────┤
│EKF VELOC │ IMU KINEM│YAMNET ACOU│ DETECT   │NVH HLTH│ SECURITY │
│ 70.0km/h │  1.02 G  │  NORMAL  │  90%     │ 81.6%  │  ARMED   │
│OBD+IMU   │MPU6050   │521-class  │All Live  │Drivetrain│GhostKey │
├─────────────────────────────────┬───────────────────────────────┤
│  VELOCITY CHART (EKF vs OBD)    │   PHYSICS ENGINE SCENARIOS   │
│                                 │  📡 OBD-II Sensor Dropout →  │
│  [Rolling 60s velocity graph]   │  🕳️  Indian Road Chaos     →  │
│  Green = EKF fused              │  💥 Severe Collision       →  │
│  White = Raw OBD                │  🔓 CAN-Bus Injection     →  │
│                                 │                              │
│                                 │  SENSOR LIVENESS             │
│                                 │  ○ OBD-II  ELM327 · 2Hz   │
│                                 │  ○ IMU     MPU6050 · 100Hz │
│                                 │  ○ Audio   YAMNet · 1Hz    │
│                                 │  ◐ Camera  Pi Cam · 5min   │
├─────────────────────────────────┴───────────────────────────────┤
│  ARCHITECTURE FLOW                                               │
│  [Sensors] →→ [HAL] →→ [Intelligence] →→ [Decision] →→ [Comms] │
│    (nodes pulse green as data flows through each stage)          │
├─────────────────────────────────────────────────────────────────┤
│  NVH ENTERPRISE HEALTH           │  EVENT INTELLIGENCE LOG      │
│  Health: 81.6%  Error: 0.234     │  [Real-time alert feed]      │
│  [████████░░] bar chart          │  color-coded by severity     │
└─────────────────────────────────┴───────────────────────────────┘
```

---

## 4. Demo Scenarios — Exact Script

### Scenario 1: Severe Collision Detection

**What to say:** *"I'm going to simulate a severe frontal impact. Watch the confidence scoring across 4 independent sensor tiers."*

**Action:** Click **💥 Severe Collision** button

**What happens (exactly):**
1. Dashboard clears velocity chart (fresh run)
2. Architecture nodes pulse green left-to-right (Sensors → HAL → Intel → Decision → Comms)
3. IMU injects: 12g jerk spike (threshold = 5 g/s)
4. CrashDetector fires: confidence 85% from IMU alone
5. YAMNet classifies audio buffer: "crash" @ 92%
6. Confidence crosses 0.65 threshold → **CRASH CONFIRMED**
7. Alert feed shows:
   ```
   💥 COLLISION DETECTED         13:45:37.234
   Confidence: 84.6% · Impact: 12.0G
   ```
8. Screen flashes red (double flash)
9. **Telegram alert arrives on phone** (owner notification)
10. OBD tier confirms: speed → 0, throttle → 0

**Expected output:**
```
CRASH DETECTED | confidence=84.8% | jerk=12.0 g/s | audio=crash@92%
```

**What to highlight:**
- "Four independent sensors agree — this isn't a single threshold trigger"
- "The Telegram arrived on my phone in real time"
- "SQLite logged this event before the Telegram was even sent"

---

### Scenario 2: Pothole Rejection (Indian Road Chaos)

**What to say:** *"Indian roads have constant high-jerk events — potholes, speed bumps, cattle crossings. Watch how the system distinguishes these from real crashes."*

**Action:** Click **🕳️ Indian Road Chaos** button

**What happens:**
1. IMU injects: 8g spike (HIGH — above crash threshold)
2. CrashDetector fires
3. Audio: road noise (not "crash" class)
4. OBD: speed continues at 40 km/h (no speed drop)
5. Temporal pattern: single brief spike (not sustained)
6. Result: **REJECTED** — not a crash

Alert feed shows:
```
🛡️ FILTERED: POTHOLE          13:45:38.001
Peak: 8.0G · Rejected by signature analysis
```

**What to highlight:**
- "Same physical force as a crash — but the temporal signature is different"
- "This is why we use 4 tiers, not a single jerk threshold"
- "Zero false positives means the owner isn't spammed with fake alerts"

---

### Scenario 3: Ghost Key TSA — CAN-Bus Injection Attack

**What to say:** *"Modern car theft doesn't use crowbars. It uses relay attacks and CAN-bus injection. I'm going to simulate exactly that."*

**Action:** Click **🔓 CAN-Bus Injection Attack** button

**What happens:**
1. System injects: CAN-bus "Unlock" + "Engine Start" commands
2. TheftDetector.handle_motion_trigger() fires
3. **Layer 1:** BLE scan → NO authorized phone → ANOMALY
4. **Layer 2:** Door never opened → IMPOSSIBLE_PHYSICS
5. **Layer 3:** Seat not occupied → IMPOSSIBLE_PHYSICS
6. **Layer 4:** Entry took 1.2s (minimum human = 2.5s) → TIMING_ANOMALY
7. 4/4 anomalies → GHOST KEY DETECTED @ 100% confidence
8. **Fuel pump relay cut** (GPIO command)
9. Security card turns RED: "THREAT"

Alert feed shows:
```
🔓 CAN-BUS INJECTION          13:45:39.494
Ghost Key TSA: 4 anomalies detected
🛡️ GHOST KEY TSA              13:45:39.500
Fuel relay cut. Engine immobilized. Alert sent.
```

Phone receives Telegram:
```
🚨 GHOST KEY DETECTED
4 temporal anomalies. Fuel pump disabled.
BLE_ABSENT | IMPOSSIBLE_PHYSICS × 2 | TIMING_ANOMALY
```

**What to highlight:**
- "This defends against relay attacks, CAN-injection, and master key theft simultaneously"
- "The fuel relay is a physical circuit — it cannot be defeated by software"
- "The legitimate owner scenario: if my phone was in BLE range, none of this would fire"

---

### Scenario 4: OBD-II Sensor Dropout

**What to say:** *"What happens when a sensor fails mid-drive? Watch the Kalman filter maintain velocity estimation from IMU alone."*

**Action:** Click **📡 OBD-II Sensor Dropout** button

**What happens:**
1. OBD feed cuts to None
2. VelocityEKF receives no OBD measurement
3. EKF propagates using IMU accelerometer only
4. Chart shows: EKF (green) continues smoothly; OBD (white) goes flat
5. Hard braking simulated: EKF tracks 60→0 km/h correctly
6. Velocity NEVER goes negative

**What to highlight:**
- "The system degrades gracefully — it doesn't crash, it adapts"
- "This is how real aerospace systems work: sensor fusion with dropout handling"

---

## 5. Verifiable Claims for Examiners

| Claim | How to Verify Live |
|---|---|
| "Gemini API is live" | Trigger crash → read Telegram message → it has scene description |
| "YAMNet is real" | Check models/: `ls -la yamnet.tflite` → 4,126,810 bytes |
| "20/20 tests pass" | `python tests/test_v3_quick.py` → runs in 30 seconds |
| "All modules load" | `DEMO_MODE=true python -c "from intelligence.theft_detector import TheftDetector; print('OK')"` |
| "SQLite persists events" | Trigger crash → `sqlite3 data/events.db "SELECT * FROM events;"` |
| "InfluxDB singleton" | Check logs: "InfluxDB client initialized (singleton)" — appears once |

---

## 6. What's Simulated (Be Honest With Examiners)

| Feature | Reality | What's Simulated |
|---|---|---|
| IMU readings | Real MPU6050 | Demo noise: 0.02g Gaussian + 1g gravity |
| OBD data | Real ELM327 | Sinusoidal speed/RPM curves |
| Audio | Real USB mic | White noise at -40dBFS |
| YAMNet inference | REAL — 4.1MB model runs | Input audio is simulated |
| Gemini API | REAL — live API calls | Crash image not from real camera |
| Telegram alerts | REAL — lands on phone | Triggered by SITL, not real crash |
| NVH autoencoder | API shape correct | Values deterministic (needs 14-day baseline) |
| BLE auth | Code complete | MAC list hardcoded for demo |
| Fuel relay | GPIO code complete | No physical relay in demo room |

**Suggested framing:** *"The algorithms, cloud integrations, and data pipelines are real and running. The sensor inputs are simulated because we don't have a car crash happening in this room."*

---

## 7. SITL Demo Script (Command Line)

For examiners who want to see full output without the browser:

```bash
cd src/vista
python ../../scripts/demo_billion_dollar_architecture.py
```

Expected output (runs ~25 seconds):
```
VISTA Software-in-the-Loop Architecture Demo
Algorithms: REAL | Sensor Data: SIMULATED

SCENARIO 1: CAN-BUS INJECTION ATTACK (RELAY THEFT)
  GHOST KEY DETECTED: 4 anomalies, confidence 100%
  → BLE_ABSENT: Owner's phone not detected
  → IMPOSSIBLE_PHYSICS: Engine started, no door opened
  → IMPOSSIBLE_PHYSICS: Engine started, no driver seated
  → TIMING_ANOMALY: Entry took 1.2s (minimum human: 2.5s)
  EXECUTING ANALOG FUEL PUMP RELAY CUT.
  ✅ RESULT: Ghost Key TSA detected. Fuel relay cut.

SCENARIO 1B: LEGITIMATE OWNER ENTRY (BLE PRESENT)
  BLE Check: Authorized owner detected. Silently disarming.
  ✅ RESULT: Owner authenticated. Silent disarm. Zero false positives.

SCENARIO 2: ENTERPRISE B2B PREDICTIVE NVH ANALYTICS
  NVH Autoencoder: Health 73.5% | Anomaly: True
  Triggering Gemini 'Expert Mechanic' report...
  Maintenance Report sent to Telegram.
  ✅ RESULT: NVH pipeline complete.

DEMO RESULTS SUMMARY
  theft_detected:   ✅ PASS
  legitimate_passes: ✅ PASS
  nvh_pipeline:     ✅ PASS
ALL SCENARIOS PASSED.
Exit code: 0
```

---

**Version:** 4.0 | **Date:** May 16, 2026
