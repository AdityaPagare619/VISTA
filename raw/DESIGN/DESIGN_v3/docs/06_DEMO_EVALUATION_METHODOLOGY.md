# 06 — Demonstration & Evaluation Methodology v3.0
## VISTA: How to Prove It Works Without Crashing a Real Car

**Version:** 3.0 | **Status:** Final | **Date:** May 10, 2026

> [!NOTE]
> This document is largely preserved from v2.1, which was already excellent. v3.0 changes: updated timing to match 35s boot, added safety disclaimer to demo alerts, switched WhatsApp references to Telegram, added MOSFET demo step.

---

## 1. The Demo Challenge (unchanged)

> **"How do you demonstrate a vehicle crash detection system in a classroom with no car, no crash, and no real emergency?"**

### 1.1 What's Real vs. Simulated (v3.0)

| Aspect | Real | Simulated | Why |
|--------|------|-----------|-----|
| IMU sensor | ✅ Physically shaken | — | Genuine G-forces |
| Audio CNN | ✅ Processes real sound | — | Real mic, real CNN |
| Camera | ✅ Captures real scene | — | Real camera |
| PIR | ✅ Detects real motion | — | Real person approaching |
| Cloud Vision API | ✅ Genuine API calls | — | Real responses |
| **MOSFET power switch** | **✅ Real Pi power cut/restore** | — | **NEW: Demonstrate true power control** |
| Telegram alerts | ✅ Real alerts sent | — | Real messaging |
| OBD-II data | — | ⚠️ Simulated (virtual serial) | No car in classroom |
| Crash context | — | ⚠️ IMU shake represents crash | Transparently disclosed |

---

## 2. Demo Scenarios

### 2.1 Scenario 1: CRASH DETECTION (5 minutes) ⭐ PRIMARY

**Demo Script (updated timing):**

| Time | Action | Presenter Says |
|------|--------|----------------|
| 0:00 | System running NORMAL | "System monitoring. IMU stable. OBD reports 45 km/h. Audio: normal." |
| 0:30 | Point to sensors | "Four modalities. IMU is primary — fastest at 100Hz. OBD is the async corroborator at 2-3Hz. We don't pretend OBD is real-time — we engineered around its actual speed." |
| 1:00 | Explain tiered detection | "IMU detects in 10ms. Audio confirms in 50ms. OBD corroborates 500ms later. Like real airbag systems." |
| 1:30 | **CRASH DEMO** | "I'll shake the IMU and play a crash sound. Watch the tiered response." |
| 1:35 | OBD simulator: crash | Terminal: throttle→0, speed→12 |
| 1:36 | Play crash audio | Audio CNN output changes |
| 1:37 | **SHAKE IMU** | *(Physical action)* |
| 1:38 | System detects | "JERK: 7.2 g/s — THRESHOLD EXCEEDED! Preliminary decision in 100ms." |
| 1:39 | Buzzer sounds | "Buzzer fires immediately — local alert." |
| 1:40 | Dashboard RED | "Confidence 72% from IMU+Audio. OBD arriving..." |
| 1:42 | OBD corroborates | "OBD confirms: throttle dropped 100%. Updated to 87%." |
| 2:00 | API response | "Gemini confirms collision. Final: 97%." |
| 2:05 | Telegram alert arrives | "Enriched alert on Telegram with image and full evidence chain." |
| 3:00 | Show evidence chain | "Notice: the system EXPLAINS every decision. Not a black box." |
| 3:30 | Show disclaimer | "Every alert includes: 'VISTA is a research prototype.' Engineering maturity requires honesty." |

### 2.2 Scenario 2: THEFT DETECTION (4 minutes) ⭐ MOST CONVINCING

**Why this is strongest: 100% physical, 0% simulation. NEW: includes MOSFET demo.**

| Time | Action | Presenter Says |
|------|--------|----------------|
| 0:00 | Show MOSFET circuit | "This ₹50 MOSFET is key. Pi can't sleep — that's a hardware fact. So we engineered true power control. Watch." |
| 0:10 | Arm system via phone | "Arming. Pi shutting down... ESP32 cutting MOSFET..." |
| 0:15 | Pi screen goes black | "Pi is now truly OFF. Zero watts. Not sleeping — OFF. Measure it." |
| 0:20 | Show ESP32 LED | "ESP32 drawing 5 microamps. This gives us 37+ days of parked battery life." |
| 0:30 | Volunteer approaches PIR | "Someone approaches..." |
| 0:35 | PIR triggers | "PIR detected! ESP32 switching MOSFET — Pi getting power..." |
| 0:40 | Pi boot screen appears | "Cold boot. 35 seconds. Honest." |
| 0:45 | Show BLE alert on phone | "BLE alert already received — before Pi even boots." |
| 1:10 | Pi boots, camera captures | "Camera capturing burst — 10 frames." |
| 1:20 | Cloud Vision API | "Uploading to Gemini..." |
| 1:45 | API response | "Person detected near driver seat." |
| 2:00 | Telegram alert | "Complete enriched alert with image. Location from phone GPS." |
| 2:30 | Show power metrics | "Total energy for this event: 0.7 Wh. Less than 0.1% of car battery." |
| 3:00 | Pi powers down | "Pi shutting down. MOSFET cutting power. Back to 5μA." |
| 3:15 | Disarm | "50-second total response time. Intruder never knew they were photographed." |

### 2.3 Scenario 3: DASHBOARD (2 minutes) — unchanged from v2.1
### 2.4 Scenario 4: LIVE SENSOR STREAM (1 minute) — unchanged from v2.1

---

## 3. OBD-II Simulator (Updated comments)

```python
"""
OBD-II ELM327 Simulator for classroom demo.
Creates virtual serial port with realistic vehicle data.

NOTE: Real ELM327 achieves 2-3 full PID cycles/sec.
This simulator responds faster for demo fluidity,
but we explicitly disclose this to examiners.
"""
# [Implementation identical to v2.1 — simulator code is correct]
```

---

## 4. Viva Presentation Flow (15 minutes)

| Time | Segment | Duration |
|------|---------|----------|
| 0:00 | Introduction — Problem + what is VISTA | 1 min |
| 1:00 | Architecture — Tiered detection, MOSFET power, hybrid edge-cloud | 2 min |
| 3:00 | Innovation — 3 primary contributions + honest limitations | 2 min |
| 5:00 | VIDEO — Pre-recorded 2-min of system in real vehicle | 2 min |
| 7:00 | LIVE DEMO — Crash (IMU shake + audio + OBD sim) | 4 min |
| 11:00 | LIVE DEMO — Theft (PIR → MOSFET → boot → capture → alert) | 3 min |
| 14:00 | Q&A | Remaining |

---

## 5. Backup Plans (unchanged + additions)

| If... | Then... |
|-------|---------|
| WiFi fails | Core demo works offline. Show pre-recorded API response. |
| Cloud API fails | "System queues for retry. Core safety works offline." |
| Pi crashes | Swap SD card. Show dashboard with pre-recorded data. |
| MOSFET circuit fails | Power Pi manually. Demo reverts to v2.1 behavior. |
| Sensor fails | Demonstrate graceful degradation. "Even without IMU, crash detection continues with OBD+Audio." |

---

## 6. Pre-Demo Checklist (v3.0)

```
WEEK BEFORE:
[ ] 3 full dry runs of entire demo
[ ] Record backup video
[ ] Collect real driving data (5 sessions)
[ ] Validate audio CNN accuracy (>80%, with confidence intervals)
[ ] Test MOSFET power cycle: Pi ON/OFF/ON reliably
[ ] Test Telegram bot delivery
[ ] Measure Pi cold boot time (should be 30-40s)

DAY BEFORE:
[ ] Flash clean Pi OS + VISTA install
[ ] Verify USB SSD mounted and InfluxDB running
[ ] Run full demo twice — 100% success rate
[ ] Test projector + phone mirroring
[ ] Print: architecture diagram + BOM (handouts)

MORNING OF:
[ ] Boot Pi 30 min before — verify thermal stability
[ ] Start OBD simulator
[ ] Open 3 projector windows (terminal, Grafana, phone)
[ ] Test buzzer volume
[ ] Place IMU board accessible
[ ] Place PIR on table edge
[ ] Have backup SD + spare MPU6050
[ ] Water bottle ready
```

---

**Return to:** `README.md` for complete document index.
