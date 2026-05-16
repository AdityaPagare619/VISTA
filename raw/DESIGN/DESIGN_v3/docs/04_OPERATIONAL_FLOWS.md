# 04 — Operational Flows Document v3.0
## VISTA: Mode Transitions, Event Sequences & Protocols

**Version:** 3.0 | **Status:** Final — Physics-Verified | **Date:** May 10, 2026

---

## 1. Mode Transition Diagram (v3.0 — MOSFET-based)

```
                         ┌──────────────────┐
                         │   SYSTEM OFF      │
                         │ (No 12V power)    │
                         └────────┬─────────┘
                                  │ 12V applied
                                  ▼
                         ┌──────────────────┐
                         │  ESP32 INIT      │
                         │  (200ms boot)    │
                         │  Check: battery, │
                         │  temp, OBD       │
                         └────────┬─────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │              │
              VBAT<11.8V    Ignition ON    Ignition OFF
                    │             │              │
                    ▼             ▼              ▼
           ┌────────────┐ ┌────────────┐ ┌────────────┐
           │ LOW-BATT   │ │ BOOT PI    │ │  PARKED    │
           │ (ESP32     │ │ (MOSFET ON │ │  SLEEP     │
           │  BLE only) │ │  35s boot) │ │ (ESP32 5μA)│
           └────────────┘ └──────┬─────┘ └──────┬─────┘
                                 │              │
                                 ▼         PIR trigger
                          ┌────────────┐        │
                          │  DRIVING   │        ▼
                          │  NORMAL    │ ┌────────────┐
                          │  (Pi ON)   │ │ THEFT WAKE │
                          └──────┬─────┘ │ (MOSFET ON │
                                 │       │  35s boot) │
                     Crash detected     └──────┬─────┘
                                 │              │
                                 ▼              ▼
                          ┌────────────┐ ┌────────────┐
                          │  CRASH     │ │  CAPTURE   │
                          │  RESPONSE  │ │  + ALERT   │
                          │  (alerts)  │ │  (5 min)   │
                          └──────┬─────┘ └──────┬─────┘
                                 │              │
                          User ack / timeout    │
                                 │              │
                                 ▼              ▼
                          ┌────────────┐ ┌────────────┐
                          │  CONTINUE  │ │  PI OFF    │
                          │  or PARK   │ │  (MOSFET)  │
                          └────────────┘ └────────────┘
```

---

## 2. Event Sequences (Physics-Verified Timing)

### 2.1 Normal Driving Cycle

```
TIME (ms)    EVENT
──────────────────────────────────────────────────────
   0         Ignition ON → ESP32 detects 12V stable
   200       ESP32 boots, checks: battery OK, temp OK
   250       ESP32 sets MOSFET GPIO7 HIGH → Pi gets 5V
   35000     Pi cold boots (30-35 seconds — honest)
   35500     Systemd starts VISTA services
   36000     OBD connects → RPM > 0 confirmed → DRIVING mode
   36500     IMU calibrated → streaming at 100Hz
   37000     Audio capture started → first CNN window filling
   37500     EKF initialized with first OBD speed reading
   38000     First audio window ready → CNN: [normal: 0.96, ...]
   38500     Write to InfluxDB on USB SSD
   
   STEADY STATE (repeating):
   T+0ms     IMU read (every 10ms, 100Hz)
   T+500ms   OBD full cycle completes (4 PIDs at ~2Hz)
   T+500ms   EKF update: fused velocity
   T+1000ms  Audio CNN: classify 1-sec window
   T+1000ms  Write batch to InfluxDB
```

### 2.2 Crash Detection & Response (Corrected Timeline)

```
TIME (ms)   EVENT
──────────────────────────────────────────────────────
   0        NORMAL: speed=45 km/h, rpm=2100, throttle=32%

   10       IMU: acceleration spike detected
            ax jumps from 0.1g to -4.5g (or saturates at -16g)
            
   20       IMU: compute jerk = 7.2 g/s
            EXCEEDS 5.0 g/s threshold → POTENTIAL CRASH
            If saturated: jerk unreliable but saturation = confirmed severe

   30       Pre-buffer captured: last 2 seconds of sensor data

   50       AUDIO CNN on last window:
            [crash: 0.91, normal: 0.06, ...]
            → Audio CORROBORATES

   100      ██ PRELIMINARY DECISION (IMU + Audio only) ██
            IMU:   min(7.2/5.0, 1.0) = 1.00 × 0.45 = 0.450
            Audio: 0.91 × 0.30                       = 0.273
            ──────────────────────────────────────────
            PRELIMINARY: 0.723 > 0.65 → CRASH CONFIRMED
            
   110      IMMEDIATE ALERTS:
            • Buzzer: ON (3 short beeps, pause, repeat)
            • BLE: text alert to phone
            • MQTT: publish crash event

   150      LOCAL STORAGE:
            • SQLite: INSERT crash event
            • InfluxDB: tag recent data with crash_event=true

   200      CAMERA: burst capture (5 frames, 100ms apart)

   500      OBD NEXT POLL ARRIVES (async, 2-3Hz):
            Speed: 45→12 km/h, Throttle: 32%→0%
            OBD: min(100/50, 1.0) = 1.00 × 0.15 = 0.150
            
            ██ UPDATED DECISION ██
            0.723 + 0.150 = 0.873
            Severity confirmed CRITICAL

  1000      WIFI CHECK:
            Available? → Upload best image to Gemini Vision API

  2500      API RESPONSE:
            "Front-end collision with barrier. Airbag deployed."
            Vision: 1.0 × 0.10 = 0.100
            
            ██ FINAL DECISION ██
            0.873 + 0.100 = 0.973

  2700      ENRICHED ALERT via Telegram:
            ┌─────────────────────────────────────────┐
            │ 🚨 CRASH DETECTED — VISTA ALERT         │
            │                                         │
            │ Confidence: 97%                         │
            │ Severity: CRITICAL                      │
            │ Time: 14:32:45 IST                      │
            │ Location: NH-48, near Lonavala          │
            │                                         │
            │ EVIDENCE:                               │
            │ • IMU: 7.2 g/s jerk (weight: 45%)      │
            │ • Audio: Crash at 91% (weight: 30%)     │
            │ • OBD: Throttle 100% drop (weight: 15%) │
            │ • Vision: Barrier collision (weight: 10%)│
            │                                         │
            │ ⚠️ VISTA is a research prototype.       │
            │ Call emergency services if needed.       │
            │                                         │
            │ [CRASH IMAGE ATTACHED]                  │
            └─────────────────────────────────────────┘

  5000      USER ACKNOWLEDGMENT:
            User taps "I'm OK" → BLE → Pi
            Buzzer: OFF
```

### 2.3 Theft Detection & Response (Honest 50-Second Timeline)

```
TIME (sec)   EVENT
──────────────────────────────────────────────────────
   0.0       User parks, arms system via phone BLE
             Pi: flushes databases, signals ready for power-off
             ESP32: cuts MOSFET → Pi power OFF (0W)
             ESP32: enters deep sleep (5μA), 1-sec PIR check cycle

   ...       (Hours pass. Battery drain: negligible)

3600.0       INTRUDER APPROACHES:
             ESP32 wakes (1-sec tick), reads PIR: HIGH
             Confirm: 3 more reads at 100ms → all HIGH

3601.0       ESP32: sets MOSFET GPIO7 HIGH → Pi gets power
             ESP32: BLE advertise "VISTA-THEFT-ALERT"
             Phone: receives BLE notification immediately

3636.0       PI BOOTS (35 seconds cold boot — honest)
             Systemd starts vista-theft.service only

3638.0       CAMERA: burst capture (10 frames, 200ms intervals)
             AUDIO: record 5 seconds

3642.0       WIFI: scan for known networks / phone hotspot

3645.0       CLOUD VISION: upload 3 best images
             
3648.0       API RESPONSE:
             "Person visible in driver seat. Unauthorized entry."

3650.0       ENRICHED ALERT via Telegram:
             "🔴 THEFT ALERT — Person detected in vehicle.
              Location: 19.0760°N, 72.8777°E
              Time: 01:32 AM
              [IMAGE ATTACHED]"

3660.0       CONTINUOUS MONITORING:
             Camera every 10 seconds for 5 minutes
             If no further motion after 5 min → Pi shutdown → MOSFET off

3960.0       AUTO POWER-DOWN:
             Pi signals ready → ESP32 cuts MOSFET → back to 5μA sleep
```

> **50 seconds vs 12 seconds:** The intruder does NOT know they're being photographed. By the time they realize (if ever), the images and alert are already sent. 50-second response is functionally equivalent to 12 seconds for evidence capture purposes.

---

## 3. Communication Protocols (v3.0)

### 3.1 ESP32 ↔ Pi Protocol (MOSFET-based)

```
POWER CONTROL (ESP32 GPIO7 → MOSFET → Pi):
  GPIO7 HIGH → NPN on → MOSFET gate LOW → Pi ON
  GPIO7 LOW  → NPN off → MOSFET gate HIGH → Pi OFF
  Default (ESP32 sleeping): Pi OFF (safe default)

HEARTBEAT (Pi GPIO6 → ESP32 GPIO6):
  Pi toggles at 1 Hz when alive
  ESP32 monitors: >30s no toggle = Pi dead
  Recovery: power-cycle (MOSFET off 5s, then on)

SHUTDOWN (orderly):
  ESP32 → MQTT → Pi: "prepare_shutdown"
  Pi: flush DBs, stop services
  Pi: hold GPIO6 HIGH for 3 seconds (shutdown signal)
  ESP32: detects steady HIGH → cuts MOSFET
```

### 3.2 BLE Protocol (unchanged from v2.1)
```
Service UUID:    0000VISTA-0000-1000-8000-00805F9B34FB
Characteristics:
  • STATUS (read):     System status
  • GPS (write):       Phone writes GPS coordinates
  • COMMAND (write):   Phone sends: arm, disarm, snapshot
  • ALERT (notify):    Pi/ESP32 pushes alerts
```

### 3.3 MQTT Topics (unchanged)
```
vista/{device_id}/alert      → Crash/theft alerts
vista/{device_id}/telemetry  → Sensor data (every 10s)
vista/{device_id}/status     → System status (every 30s)
vista/{device_id}/command    → Phone → Pi commands
```

### 3.4 Cloud API (unchanged from v2.1)
```
POST gemini-1.5-flash:generateContent
Body: { text_prompt + base64_image }
Timeout: 10 seconds
Retries: 3 with exponential backoff (1s, 2s, 4s)
```

---

## 4. Error Handling Flows (v3.0)

### 4.1 Sensor Failure Degradation

```
OBD-II FAILS:
  → Crash detection continues (IMU+Audio = 0.75 max, sufficient)
  → EKF: runs on IMU integration only (drifts without OBD correction)
  → Retry every 30 seconds

IMU FAILS:
  → Critical: IMU is primary crash detector
  → Fallback: OBD speed-rate + Audio only (reduced sensitivity)
  → BLE alert: "Primary crash sensor offline"

AUDIO FAILS:
  → Crash detection: IMU + OBD (0.60 max — marginal)
  → Siren detection: unavailable
  → Redistribute audio weight to IMU

ESP32 FAILS:
  → Cannot detect: heartbeat stops, no recovery mechanism
  → Pi stays on permanently if already booted (no power management)
  → If Pi is off: system is dead until manual power-on
  → BLE: unavailable (ESP32 handles BLE)

MOSFET FAILS (open):
  → Pi never gets power → system dead for Pi functions
  → ESP32 still operates: BLE alerts, PIR monitoring
  → Fail-SAFE: no phantom power drain

MOSFET FAILS (shorted):
  → Pi always has power → reverts to v2.1 behavior
  → Pi draws power when halted (~200mW) → acceptable degradation
  → Fail-ACCEPTABLE: system works, just uses more battery
```

---

## 5. Startup & Shutdown Sequences (v3.0)

### 5.1 Startup (ESP32-Controlled Cold Boot)

```bash
# ESP32 firmware sequence (pseudocode):
1. ESP32 boots (200ms)
2. Read battery voltage (ADC): if < 11.8V → LOW-BATT mode, skip Pi boot
3. Read ambient temp: if > 55°C → THERMAL-BLOCK, skip Pi boot
4. Set MOSFET GPIO7 = HIGH → Pi receives 5V power
5. Start heartbeat monitor timer (expect toggle within 60s)
6. Wait for Pi heartbeat on GPIO6...

# Pi boot sequence (systemd):
7. Pi cold boots (~30-35s)
8. /home/pi/vista/scripts/startup.sh runs:
   - Check hardware (I2C, USB, camera, SSD mount)
   - Start services in dependency order
   - Begin GPIO6 heartbeat toggle at 1 Hz
9. System enters appropriate mode based on OBD RPM
```

### 5.2 Shutdown (Orderly MOSFET Cut)

```bash
# ESP32 initiates (or Pi self-initiates on ignition off + 5min idle):
1. MQTT message to Pi: "prepare_shutdown"
2. Pi: stop decision engine first (prevent false alerts)
3. Pi: flush InfluxDB and SQLite
4. Pi: stop all VISTA services
5. Pi: hold GPIO6 HIGH for 3 seconds (shutdown signal)
6. Pi: sudo halt
7. ESP32: detects 3s steady HIGH on GPIO6
8. ESP32: set MOSFET GPIO7 = LOW → Pi power CUT (0W)
9. ESP32: enter deep sleep (5μA) with 1-sec PIR wake
```

---

**Next:** See `05_TECHNOLOGY_STACK.md` for updated library choices and USB SSD configuration.
