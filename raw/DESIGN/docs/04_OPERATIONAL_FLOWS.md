# 04 — Operational Flows Document
## VISTA: Mode Transitions, Event Sequences & Protocols

**Version:** 2.1 | **Status:** Final | **Date:** May 8, 2026

---

## 1. Mode Transition Diagram

```
                         ┌──────────────────┐
                         │   SYSTEM OFF      │
                         │ (Car battery      │
                         │  disconnected)    │
                         └────────┬─────────┘
                                  │ 12V applied
                                  ▼
                         ┌──────────────────┐
                    ┌────│    BOOT MODE     │────┐
                    │    │  (Pi booting,    │    │
                    │    │   ESP32 active)  │    │
                    │    └────────┬─────────┘    │
                    │             │              │
              OBD RPM>0       OBD RPM=0     Ignition OFF
                    │             │              │
                    ▼             ▼              ▼
            ┌───────────┐  ┌───────────┐  ┌───────────┐
            │ DRIVING   │  │  PARKED   │  │  PARKED   │
            │  MODE     │  │  MONITOR  │  │  SLEEP    │
            │           │  │           │  │           │
            │ Pi: ON    │  │ Pi: OFF   │  │ Pi: OFF   │
            │ ESP32: ON │  │ ESP32: ON │  │ ESP32: 5μA│
            └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
                  │              │ PIR trigger   │ 1-sec timer
                  │ Crash        ▼               │ tick
                  │ detected ┌───────────┐       │
                  ▼          │  ALERT    │       ▼
            ┌───────────┐   │  MODE     │  ┌───────────┐
            │CRASH MODE │   │           │  │  CHECK    │
            │           │   │ Pi: WAKE  │  │  PIR      │
            │Emergency  │   │ Camera→API│  │  (ESP32)  │
            │Response   │   │ Alert     │  └─────┬─────┘
            └───────────┘   └─────┬─────┘       │
                  │               │ 5 min idle  │ PIR HIGH
                  │ User ack      ▼              │
                  ▼          ┌───────────┐       ▼
            ┌───────────┐   │  PARKED   │  ┌───────────┐
            │  RETURN   │   │  SLEEP    │  │  ALERT    │
            │  NORMAL   │   │  (return) │  │  MODE     │
            └───────────┘   └───────────┘  └───────────┘
```

---

## 2. Detailed Event Sequences

### 2.1 Normal Driving Cycle

```
TIME (sec)  EVENT
────────────────────────────────────────────────────────────
  0.00     Ignition ON → OBD-II detects RPM > 0
  0.01     System enters DRIVING mode
  0.10     OBD poll: speed=0, rpm=800, throttle=15%, coolant=35°C
  0.10     IMU read: ax=0.02, ay=-0.01, az=1.00 (stationary)
  0.10     Audio capture started; first window filling
  0.50     EKF initialized with first OBD speed measurement
  1.00     First audio window ready → CNN inference
  1.05     CNN: [normal: 0.96, horn: 0.02, crash: 0.01, siren: 0.01]
  1.10     Write to InfluxDB: {time, speed, rpm, throttle, audio_class}
  2.00     Vehicle starts moving; OBD speed=5 km/h
  2.10     EKF update: fused_velocity=4.8 km/h
  5.00     Periodic camera capture: image → save locally
  5.10     WiFi available? Yes → upload to Gemini Vision API
  7.00     API response: "City road, moderate traffic. Two cars ahead. Road good."
  7.10     Write vision result to SQLite linked to timestamp
  ...
 60.00     Continuous loop continues at 10 Hz
 60.00     (Every 5 min: camera → API → store result)
```

### 2.2 Crash Detection & Response

```
TIME (ms)  EVENT
────────────────────────────────────────────────────────────
   0       NORMAL DRIVING: speed=45 km/h, rpm=2100, throttle=32%
           
  10       IMU detects ACCELERATION SPIKE
           ax jumps from 0.1g to -4.5g in 50ms
           gy=+45°/s (rotation detected)
           
  20       IMU INTERRUPT: compute jerk = 7.2 g/s
           EXCEEDS CRASH THRESHOLD (5.0 g/s)
           → Flag: POTENTIAL CRASH
           
  30       Capture pre-buffer: last 2 seconds of sensor data
           Store in memory ring buffer
           
  40       OBD-II CORROBORATION CHECK:
           Poll OBD: speed=45→12 km/h, throttle=32%→0%, rpm=2100→800
           Throttle drop: 100% in 200ms → CONFIRMED
           
  50       AUDIO CORROBORATION:
           CNN on last 2 audio windows:
           [normal: 0.98, crash: 0.01, ...]  (pre-crash)
           [crash: 0.91, normal: 0.06, ...]  (impact detected!)
           Audio confirms crash at 91% confidence
           
  60       CAMERA CAPTURE:
           Burst mode: 5 frames at 100ms intervals
           Store all frames to local storage
           
  70       DECISION ENGINE:
           IMU confidence:  min(7.2/5.0, 1.0) = 1.00  × 0.35 = 0.350
           OBD confidence:  min(100/50, 1.0)  = 1.00  × 0.25 = 0.250
           Audio confidence: 0.91                   × 0.25 = 0.228
           Vision: pending (0 for now)              × 0.15 = 0.000
           ─────────────────────────────────────────────────────
           FINAL CONFIDENCE: 0.828 → CRASH CONFIRMED (CRITICAL)
           
  80       IMMEDIATE LOCAL ALERT:
           Buzzer: ON (3 short beeps, pause, repeat)
           BLE: Send alert to phone (non-enriched)
           MQTT: Publish crash event
           
  90       LOCAL STORAGE:
           SQLite: INSERT crash event {timestamp, confidence:0.83, severity:critical}
           InfluxDB: Tag all recent data points with "crash_event=true"
           
  100      CHECK WIFI:
           WiFi available? Check: YES (phone hotspot connected)
           
  200      UPLOAD TO CLOUD VISION:
           HTTP POST: best crash image → Gemini Vision API
           Prompt: "This is a CRASH SCENE. Analyze collision type, severity..."
           
 2000      API RESPONSE RECEIVED:
           {
             "collision_type": "front-end impact with concrete barrier",
             "vehicles_involved": 1,
             "severity": "moderate",
             "airbag_deployed": "yes - driver side visible",
             "license_plate": "MH-12-AB-1234",
             "description": "Single vehicle front-end collision with highway barrier.
                           Driver airbag deployed. Front-end damage visible. 
                           No other vehicles involved."
           }
           
 2100      UPDATE DECISION:
           Vision confidence: 1.0 (API confirms crash) × 0.15 = 0.150
           REVISED FINAL CONFIDENCE: 0.828 + 0.150 = 0.978
           
 2200      ENRICHED ALERT SENT:
           WhatsApp message:
           ┌─────────────────────────────────────────┐
           │ 🚨 CRASH DETECTED — VISTA ALERT         │
           │                                         │
           │ Confidence: 98%                         │
           │ Severity: CRITICAL                      │
           │ Time: 14:32:45 IST                      │
           │ Location: NH-48, near Lonavala (via GPS)│
           │                                         │
           │ EVIDENCE:                               │
           │ • IMU: 7.2 g/s jerk detected            │
           │ • OBD: Throttle 100% drop in 200ms      │
           │ • Audio: Crash sound at 91% confidence  │
           │ • Vision: Front-end barrier collision   │
           │          Airbag deployed                │
           │          License: MH-12-AB-1234         │
           │                                         │
           │ [CRASH IMAGE ATTACHED]                  │
           └─────────────────────────────────────────┘
           
 5000      USER ACKNOWLEDGMENT:
           User taps "I'm OK" on phone → BLE → Pi
           System logs: "crash_acknowledged"
           Buzzer: OFF
           
10000      SYSTEM RETURNS:
           If vehicle still operational → continue monitoring
           If vehicle disabled → enter PARKED-MONITOR mode
```

### 2.3 Theft Detection & Response

```
TIME (sec)  EVENT
────────────────────────────────────────────────────────────
   0.0     User parks car, exits, arms system via phone app
           Phone → BLE → ESP32: "ARM SYSTEM"
           
   1.0     ESP32: Enable PIR interrupt on GPIO0
           ESP32: Begin 1-second wake-check cycle
           
   1.0     Pi: Save final telemetry, prepare for sleep
           Pi: echo mem > /sys/power/state  (suspend to RAM)
           Pi: Power draw drops to ~0.5W (idle suspend)
           
   5.0     System in PARKED-SLEEP mode
           ESP32: Deep sleep (5μA), wakes every 1 sec for PIR check
           
  ...      (hours pass...)
  
3600.0     INTRUDER APPROACHES:
           ESP32 wakes (1-sec tick), reads PIR: LOW (no motion)
           Back to deep sleep
           
3601.0     INTRUDER ENTERS VEHICLE:
           ESP32 wakes, reads PIR: HIGH (motion detected!)
           ESP32: Confirm — read PIR 3 more times at 100ms intervals
           PIR: HIGH, HIGH, HIGH → CONFIRMED MOTION
           
3601.5     ESP32: Pull WAKE pin (GPIO4) HIGH
           Pi: Begins waking from suspend
           
3602.0     ESP32: BLE advertise — "VISTA-THEFT-ALERT" 
           Phone receives BLE notification: "Motion detected"
           
3611.0     PI BOOTS (~9 seconds from wake signal)
           Pi: Systemd starts vista-theft.service
           
3612.0     CAMERA CAPTURE:
           Burst: 10 frames at 200ms intervals (2 seconds total)
           Audio: Record 5 seconds of audio
           
3615.0     WIFI CHECK:
           Scan for known networks or phone hotspot
           Found: Phone hotspot active → connect
           
3618.0     CLOUD VISION ANALYSIS:
           Upload 3 best images to Gemini Vision API
           
3620.0     API RESPONSE:
           "Person visible inside vehicle driver seat. 
            Hands on steering wheel. Appears to be unauthorized entry.
            Vehicle interior: dark, dashboard visible."
           
3622.0     PHONE GPS CHECK (via BLE):
           Phone reports: GPS=19.0760,72.8777
           Last known location logged
           
3625.0     ENRICHED ALERT SENT:
           WhatsApp: "🔴 THEFT ALERT — Motion detected in your vehicle.
                     Vision: Person in driver seat. 
                     Location: 19.0760°N, 72.8777°E
                     Time: 01:32 AM"
           
3630.0     CONTINUOUS MONITORING:
           Camera: Capture every 10 seconds
           Each image → API → store description
           All data saved to SQLite as theft event chain
           
3900.0     USER ARRIVES / DE-ARMS:
           Phone → BLE → ESP32: "DISARM SYSTEM"
           ESP32: Disable PIR interrupt
           Pi: Return to normal PARKED-SLEEP mode
```

### 2.4 Driver Behavior Analysis (Daily)

```
TIME      EVENT
────────────────────────────────────────────────────────────
23:59     Daily cron job triggers: vista-behavior-analyzer.py
          
00:00     LOAD DATA:
          Query InfluxDB: SELECT * FROM telemetry 
          WHERE time > now() - 24h
          
00:01     COMPUTE METRICS:
          - Harsh braking events: count(IMU jerk > 3g AND OBD throttle<10%)
          - Rapid acceleration events: count(IMU ax > 0.5g AND throttle>80%)
          - Average speed: mean(OBD speed)
          - Max speed: max(OBD speed)
          - Idle time: sum(time where rpm>0 AND speed=0)
          - Night driving: sum(time where hour between 22-05)
          
00:02     CLASSIFY BEHAVIOR:
          if harsh_braking > 5 OR rapid_accel > 10:
              behavior = "AGGRESSIVE"
          elif harsh_braking > 2:
              behavior = "MODERATE"
          else:
              behavior = "SMOOTH"
          
00:03     GENERATE REPORT:
          Write to SQLite: daily_behavior_report table
          
00:05     (OPTIONAL) CLOUD AI ANALYSIS:
          If WiFi: upload aggregated stats to LLM
          Prompt: "Analyze this driver's behavior data..."
          Get natural language feedback report
          
00:10     STORE REPORT:
          Available via Grafana dashboard
          Phone notification: "Daily driving report ready"
```

---

## 3. Communication Protocols

### 3.1 Pi ↔ ESP32 GPIO Protocol

```
WAKE SIGNAL (Pi GPIO5 ← ESP32 GPIO4):
  ESP32 sets GPIO4 HIGH for 500ms → Pi wakes
  ESP32 then sets GPIO4 LOW
  
STATUS SIGNAL (Pi GPIO6 → ESP32 GPIO6):
  Pi toggles GPIO6 at 1 Hz when alive (heartbeat)
  ESP32 monitors: if heartbeat stops for >30s, Pi is dead
  ESP32 can then power-cycle Pi (optional relay circuit)
```

### 3.2 Pi ↔ Phone BLE Protocol

```
Service UUID:    0000VISTA-0000-1000-8000-00805F9B34FB
Characteristics:
  • STATUS (read):     System status {mode, battery, alerts}
  • GPS (write):       Phone writes GPS coordinates
  • COMMAND (write):   Phone sends commands {arm, disarm, snapshot}
  • ALERT (notify):    Pi pushes alerts to phone

GPS Format:
  Phone → Pi (every 5 sec while connected):
  {"lat": 19.0760, "lon": 72.8777, "speed": 0, "accuracy": 5.0}
```

### 3.3 MQTT Topics

```
Topic Structure: vista/{device_id}/{category}

Publish:
  vista/VISTA-0001/alert        → Crash/theft alerts
  vista/VISTA-0001/telemetry    → Periodic sensor data (every 10s)
  vista/VISTA-0001/status       → System status (every 30s)

Subscribe:
  vista/VISTA-0001/command      → Phone → Pi commands
  vista/VISTA-0001/gps          → Phone GPS data
```

### 3.4 Cloud API Protocol

```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent
Headers:
  Authorization: Bearer {API_KEY}
  Content-Type: application/json

Body:
{
  "contents": [{
    "parts": [
      {"text": "Analyze this scene..."},
      {"inline_data": {"mime_type": "image/jpeg", "data": "{base64_image}"}}
    ]
  }]
}

Response (parsed):
{
  "candidates": [{
    "content": {
      "parts": [{"text": "{\"scene_type\": \"city\", ...}"}]
    }
  }]
}
```

---

## 4. Error Handling Flows

### 4.1 Sensor Failure Degradation

```
OBD-II FAILS:
  → Log warning: "OBD-II disconnected"
  → Crash detection: IMU-only (remains functional)
  → Decision engine: redistribute OBD weight (25%) to IMU+Audio
  → User notified: BLE alert "OBD sensor offline"
  → Retry connection every 30 seconds
  → When reconnected: log "OBD-II reconnected", restore weights

IMU FAILS:
  → Log warning: "IMU disconnected"
  → Crash detection: OBD speed-rate + Audio only
  → Audio becomes primary crash detector (weight 50%)
  → User notified: "Motion sensor offline"

AUDIO FAILS:
  → Log warning: "Microphone disconnected"
  → Crash detection: IMU + OBD (remains functional)
  → Siren detection: unavailable
  → Redistribute audio weight to IMU

CAMERA FAILS:
  → Log warning: "Camera error"
  → Vision enrichment: unavailable
  → Alerts: text-only (core functionality preserved)
  → Retry camera initialization every 5 minutes

ALL SENSORS FAIL:
  → System enters "degraded mode"
  → Logs: event "system_degraded"
  → ESP32: BLE alert "System failure — service required"
  → Pi: attempt reboot
```

### 4.2 Cloud API Failure

```
GEMINI VISION API FAILS:
  → Log: "Vision API error: {status_code}"
  → Retry: exponential backoff (1s, 2s, 4s, 8s, 16s)
  → After 5 retries: mark event as "vision_pending"
  → Alert sent WITHOUT vision enrichment (text-only)
  → When WiFi/API recovers: retry pending events
  → Max pending: 100 events → oldest evicted

WHATSAPP API FAILS:
  → Fallback to MQTT alert (still reaches phone)
  → If BLE connected: send via BLE
  → Log: "WhatsApp delivery failed"
```

---

## 5. Startup & Shutdown Sequences

### 5.1 Clean Startup

```bash
#!/bin/bash
# /home/pi/vista/scripts/startup.sh

# 1. Check hardware
echo "Checking hardware..."
i2cdetect -y 1 | grep 68  # MPU6050
ls /dev/ttyUSB0            # OBD-II
arecord -l                 # Microphone
libcamera-hello --list-cameras  # Camera

# 2. Start systemd services in order
sudo systemctl start vista-obd
sleep 2
sudo systemctl start vista-imu
sleep 1
sudo systemctl start vista-audio
sleep 1
sudo systemctl start vista-fusion
sleep 2
sudo systemctl start vista-decision
sudo systemctl start vista-mqtt
sudo systemctl start vista-api

# 3. Verify all services healthy
sudo systemctl status vista-* | grep "active (running)"
```

### 5.2 Clean Shutdown

```bash
#!/bin/bash
# /home/pi/vista/scripts/shutdown.sh

# 1. Stop decision engine first (prevents false alerts)
sudo systemctl stop vista-decision
sleep 1

# 2. Flush databases
python3 -c "from influx_writer import flush_all; flush_all()"

# 3. Stop remaining services
sudo systemctl stop vista-fusion vista-audio vista-imu vista-obd
sudo systemctl stop vista-mqtt vista-api

# 4. Signal ESP32: Pi shutting down
python3 -c "from gpio_manager import signal_shutdown; signal_shutdown()"

# 5. Shutdown Pi
sudo shutdown -h now
```

---

**Next:** See `05_TECHNOLOGY_STACK.md` for complete library/framework choices.
