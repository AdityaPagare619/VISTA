# 04 — Operational Flows Document v4.0
## VISTA: Event Sequences, Detection Timelines & Algorithm Descriptions

**Version:** 4.0 | **Status:** Built & Verified | **Date:** May 16, 2026

---

## 1. Crash Detection Timeline

Complete sequence from impact to alert delivery:

```
T = 0.000s  ── IMPACT ──────────────────────────────────────────────
                IMU records jerk = 12.0 g/s (threshold: 5.0 g/s)
                Accel vector: (8.5g, 2.1g, -1.2g)
                Saturation flag: FALSE (below 15.5g clip threshold)

T = 0.010s  ── IMU TIER COMPLETE (10ms) ─────────────────────────────
                CrashDetector.assess() called
                IMU jerk score:  0.85  (weight: 0.45)
                Running confidence: 0.85 × 0.45 = 0.383

T = 0.060s  ── AUDIO TIER COMPLETE (~50ms) ──────────────────────────
                YAMNet TFLite inference on 1s window
                Top class: "crash" @ 92% confidence
                VISTA mapped class: "crash"
                Audio score: 0.92  (weight: 0.30)
                Running confidence: 0.383 + (0.92 × 0.30) = 0.659

T = 0.060s  ── THRESHOLD CROSSED ──────────────────────────────────
                0.659 > confirm_threshold (0.65) → CRASH CONFIRMED
                Severity: CRITICAL (confidence > 0.8 → critical)

T = 0.070s  ── LOCAL PERSIST ─────────────────────────────────────────
                SQLiteManager.log_event("crash", 0.659, "critical")
                Writes to /mnt/vista-data/events.db (WAL mode)
                Event ID returned: e.g., 42
                ← Network failure here? Event is safe.

T = 0.500s  ── OBD TIER (async, 2Hz) ──────────────────────────────
                Speed: 60 → 0 km/h transition detected
                Throttle: 45% → 0% transition detected
                OBD score: 0.65  (weight: 0.15)
                Final confidence: 0.659 + (0.65 × 0.15) = 0.756

T = 1.000s  ── CAMERA CAPTURE ────────────────────────────────────────
                Pi Camera v3 captures 5 burst frames @ 100ms intervals
                Resolution: 2304×1296 JPEG quality 85
                Saved to: /mnt/vista-data/images/crash_<timestamp>.jpg

T = 1.500s  ── CLOUD VISION (Gemini) ───────────────────────────────
                CloudVision.describe_scene(image_path)
                Gemini 1.5-flash API call
                Returns: "Front-end collision visible. Airbag deployed.
                          Road surface: highway. Time: daytime."
                Vision score: 0.90  (weight: 0.10)
                Final confidence: 0.756 + (0.90 × 0.10) = 0.846

T = 2.000s  ── TELEGRAM ALERT ────────────────────────────────────────
                TelegramAlertBot.send_alert()
                Message contains:
                  - Event type: CRASH (CRITICAL)
                  - Confidence: 84.6%
                  - Evidence breakdown (per-sensor bars)
                  - Gemini scene description
                  - Timestamp and device ID
                  - Safety disclaimer
                Delivered to owner's phone via Telegram Bot API

T = 2.000s  ── MQTT PUBLISH ──────────────────────────────────────────
                AlertManager publishes to vista/events/crash
                Fleet management systems receive via MQTT

T = 2.000s  ── BUZZER ───────────────────────────────────────────────
                GPIOManager.pulse_buzzer(pattern="crash")
                3 short pulses on GPIO17
```

### 1.1 Crash Classification Logic (Signature-Aware)

```
NOT all high-jerk events are crashes. CrashDetector uses pattern matching:

Pothole:
  IMU jerk: HIGH (spike, then immediate return to 1g)
  Duration: <100ms sustained
  Audio:    Road noise, not "crash" class
  OBD:      Speed continues (no sudden drop)
  Result:   REJECTED — not classified as crash ✓

Speed Bump:
  IMU jerk: MODERATE (slower rise and fall)
  Duration: 200–500ms
  Audio:    Low rumble, not "crash" class
  OBD:      Speed may briefly drop then recover
  Result:   REJECTED — not classified as crash ✓

Real Crash:
  IMU jerk: HIGH + SUSTAINED deceleration
  Pattern:  Initial spike + prolonged deceleration signature
  Audio:    "crash" class score elevated
  OBD:      Speed drops to 0 within 2s
  Result:   DETECTED ✓

Door Slam:
  IMU:      Brief spike, single axis
  Audio:    Not "crash" class
  OBD:      Speed unchanged
  Result:   REJECTED ✓
```

---

## 2. Ghost Key TSA — Theft Prevention Sequence

The Ghost Key Temporal Sequence Analysis runs when an engine start is detected without legitimate BLE authorization.

```
SCENARIO: Relay Attack / CAN-Bus Injection
──────────────────────────────────────────────────────────────────

T = 0.000s  ATTACKER injects CAN-bus "Unlock" command
            (or amplifies key fob signal for relay attack)

T = 0.100s  ATTACKER injects CAN-bus "Engine Start" command
            Vehicle electronics respond (steering unlocked, etc.)

T = 0.100s  TheftDetector.handle_motion_trigger() fires
            (PIR or CAN event triggers security check)

T = 0.100s  LAYER 1: BLE Proximity Check
            TheftDetector.check_ble_proximity()
            Scans for authorized device MAC addresses
            Scan window: 300ms
            Result: NO AUTHORIZED DEVICES FOUND
            Anomaly logged: BLE_ABSENT

T = 0.400s  LAYER 2: Event Ordering Check (Physics)
            Was a door opened before engine start?
            Expected sequence: Door open → Sit → Engine start
            Actual sequence:   Engine start (no door event)
            Result: IMPOSSIBLE_PHYSICS — "Engine started but no door opened"
            Anomaly logged: IMPOSSIBLE_PHYSICS (door)

T = 0.400s  LAYER 3: Occupancy Check (Physics)
            Was driver seat occupied?
            Expected: Seat sensor weight change before engine start
            Actual:   No seat occupancy event
            Result: IMPOSSIBLE_PHYSICS — "Engine started but no driver seated"
            Anomaly logged: IMPOSSIBLE_PHYSICS (seat)

T = 1.200s  LAYER 4: Timing Analysis
            Time from "Unlock" to "Engine Start": 1.2 seconds
            Human minimum entry time: 2.5 seconds
              (open door + enter + close door + insert key/press start)
            Result: TIMING_ANOMALY — "Entry took 1.2s (minimum human: 2.5s)"
            Anomaly logged: TIMING_ANOMALY

T = 1.200s  DECISION: 4/4 anomalies → GHOST KEY DETECTED
            Confidence: 100% (4 independent anomalies)

T = 1.200s  PHYSICAL RESPONSE:
            GPIOManager.trigger_relay(FUEL_PUMP, CUT)
            Fuel pump relay switches NC → NO
            Engine loses fuel supply

T = 3.000s  Engine dies (fuel line depletes)

T = 3.100s  SQLiteManager.log_event("theft_attempt", 1.0, "critical")

T = 3.500s  Telegram alert to owner:
            "🚨 GHOST KEY DETECTED — 4 anomalies
             Fuel pump cut. Engine disabled.
             Location: [GPS if available]"

SCENARIO: Legitimate Owner Entry (Zero False Positive)
──────────────────────────────────────────────────────────────────

T = 0.000s  Owner approaches vehicle (phone in pocket)

T = 0.100s  LAYER 1: BLE Proximity Check
            ESP32-C3 detects owner's phone BLE MAC
            MAC matches authorized device list
            Result: AUTHORIZED DEVICE PRESENT

T = 0.100s  DECISION: Authorized → SILENT DISARM
            No alert. No relay cut. No false positive.
            Log: "Authorized entry — silent disarm"
```

---

## 3. NVH Predictive Maintenance Flow

```
DAILY OPERATION (runs in background thread):

Every 30 minutes:
  1. Collect IMU Z-axis readings during driving (1 minute buffer)
  2. Apply FFT to vibration data
     → Isolates frequency bands: drivetrain, suspension, engine
  3. PredictiveAnalyticsEngine.calculate_nvh_reconstruction_error()
     → Compares current FFT profile to baseline (14-day trained model)
     → Reconstruction error > 0.30 → anomaly flagged

On anomaly detected:
  4. B2B API response generated:
     {
       "nvh_health_score_fft": 68.5,
       "reconstruction_error": 0.32,
       "drivetrain_anomaly_detected": true,
       "anomaly_frequency_band": "3.5kHz (Acoustic) + 1.2Hz (IMU Z-axis)"
     }

  5. Gemini "Expert Mechanic" report generated:
     CloudVision.ask("You are an expert mechanic. The vehicle shows
     anomalous vibration at 3.5kHz acoustic band and 1.2Hz on the
     vertical IMU axis. What might be wrong?")

  6. B2C Telegram report:
     "🔧 Vehicle Health Update
      Drivetrain anomaly detected. Unusual vibration pattern at
      frequencies consistent with early bearing wear. Recommend
      inspection within 500km."

SIMULATION NOTE (honest disclosure):
  Current NVH model is SIMULATED (deterministic hash, not trained).
  The API shape is correct and the Gemini report is real.
  A real model requires 14 days of baseline driving data collection.
  The simulation demonstrates the full pipeline architecture.
```

---

## 4. OBD Dropout Recovery (EKF Resilience)

```
Normal operation (OBD connected):
  VelocityEKF.update(obd_speed=60.0, imu_accel=0.05)
  State: [velocity=60.0 km/h, accel_bias=0.01]

T = 0s: OBD cable disconnects (USB timeout)
  OBDReader returns None for all readings

T = 0s: EKF receives no OBD measurement
  EKF.predict() called with last known state
  State propagates using IMU accel only:
    v(t+dt) = v(t) + accel × dt − accel_bias × dt

T = 2s: Hard braking detected via IMU
  accel = -0.8g (−7.8 m/s²)
  EKF tracks: 60 → 42 → 28 → 18 → 8 km/h
  velocity NEVER goes negative (EKF constraint enforced)

T = 10s: EKF maintains reasonable estimate
  Without OBD: uncertainty grows (P matrix inflates)
  But estimate remains physically plausible

T = 30s: OBD reconnects
  EKF re-converges to OBD speed within 2–3 cycles
  State: [velocity=55.0 km/h, accel_bias=0.01]

Key EKF parameters (config.yaml):
  dt: 0.4s              (matches OBD 2Hz poll)
  process_noise: [0.5, 0.01]   (velocity drift, bias drift)
  measurement_noise: [0.08]    ((1 km/h / 3.6)² ≈ 0.08 m/s²)
```

---

## 5. ESP32-C3 Parked Mode Sequence

```
Vehicle parked (engine off, ignition off):

T = 0s:   OBD RPM = 0 detected
          ESP32 transitions DRIVING_MODE → PARKED_MODE

T = 1s:   ESP32 sends Pi shutdown signal (GPIO5 → Pi)
          Pi receives signal, graceful shutdown sequence:
          Dashboard → Comms → Intelligence → HAL
          Pi holds GPIO6 HIGH for 3s ("ready to cut power")

T = 4s:   Pi GPIO6 LOW (shutdown complete)
          ESP32 drives GPIO7 HIGH → MOSFET OFF → Pi power cut
          Pi draws 0W

T = 4s:   ESP32 enters deep sleep
          Wake source: PIR interrupt on GPIO0
          Sleep current: 5μA
          Battery drain: 12Ah car aux battery → ~100 days

PIR Trigger (potential theft):
T = 0s:   PIR detects motion → ESP32 wakes (200ms boot)
T = 0.2s: ESP32 BLE scan: authorized phone present?
  → YES: owner approach → do nothing, go back to sleep
  → NO:  potential threat → continue

T = 0.5s: ESP32 drives GPIO4 HIGH (500ms pulse)
          MOSFET gates on → Pi 5V applied

T = 35s:  Pi completes cold boot
          Phase 1–5 initialization
          TheftDetector activates

T = 36s:  Ghost Key TSA runs (if CAN signals detected)
          OR: camera captures scene, Gemini describes it
          Alert sent to owner
```

---

## 6. System Health Monitor (30s Periodic Report)

```
Every 30 seconds in driving loop:
  SystemHealthMonitor.get_health_report()

Report contents:
  sensors:
    obd:   LIVE / DEAD (last ping within 5s?)
    imu:   LIVE / DEAD
    audio: LIVE / DEAD
    camera: LIVE / DEAD

  resources:
    cpu_pct:  float (e.g., 45.2%)
    ram_pct:  float (e.g., 62.1%)
    temp_c:   float (Pi SoC temperature, e.g., 52.3°C)
    disk_pct: float (SSD usage)

  capacity: float 0.0–1.0
    (fraction of sensors currently live × weights)

  alerts:
    high_cpu: bool  (> 80% sustained)
    high_temp: bool (> 70°C)
    low_disk:  bool (< 500MB free)

Log example:
  INFO | health_monitor | Capacity=90% | CPU=45% | RAM=62% |
         Temp=52°C | Sensors=obd✓ imu✓ audio✓ cam✗
```

---

**Version:** 4.0 | **Date:** May 16, 2026
