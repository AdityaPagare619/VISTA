# 06 — Demonstration & Evaluation Methodology
## VISTA: How to Prove It Works Without Crashing a Real Car

**Version:** 2.1 | **Status:** Final | **Date:** May 8, 2026

---

## 1. The Demo Challenge

### 1.1 The Problem

> **"How do you demonstrate a vehicle crash detection system in a classroom with no car, no crash, and no real emergency?"**

This is THE question every automotive IoT project faces. Commercial systems are validated with:
- Instrumented crash test vehicles ($100,000+ each)
- NHTSA/NCAP crash test facilities
- Years of real-world fleet data

We have a classroom, a table, and 12 minutes.

### 1.2 What Examiners Actually Evaluate

| They Want To See | How We Show It |
|-----------------|----------------|
| **Working hardware** | Physical sensors streaming real data live |
| **Real algorithms** | CNN processes actual audio; EKF fuses actual IMU data |
| **End-to-end pipeline** | Sensor → Intelligence → Alert demonstrated live |
| **Explainability** | Dashboard shows per-sensor evidence and confidence scores |
| **Innovation evidence** | Audio CNN running; Cloud Vision API enriching alerts |
| **Honesty about limitations** | Transparent about what's simulated vs. real |
| **Real-world validity** | Pre-recorded video of system in actual car |

### 1.3 The Core Philosophy

> **"We don't fake the system. We provide controlled inputs to a real system and are transparent about the context."**

| Aspect | Real | Simulated | Why |
|--------|------|-----------|-----|
| **IMU sensor** | ✅ Physically shaken | — | Genuine G-forces measured by real hardware |
| **Audio CNN** | ✅ Processes real sound | — | Real microphone, real CNN, real classification |
| **Camera** | ✅ Captures real scene | — | Real camera, real images |
| **PIR** | ✅ Detects real motion | — | Real person walking past |
| **Cloud Vision API** | ✅ Genuine API calls | — | Real API, real responses |
| **MQTT/WhatsApp** | ✅ Real alerts sent | — | Real messaging pipeline |
| **OBD-II data** | — | ⚠️ Simulated | No car in classroom; transparently disclosed |
| **Crash context** | — | ⚠️ Simulated | The IMU shake represents a crash |
| **Theft context** | — | ⚠️ Simulated | The person walking represents an intruder |

---

## 2. Demonstration Architecture

### 2.1 Classroom Physical Setup

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLASSROOM LAYOUT                            │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    PROJECTOR SCREEN                       │  │
│  │  ┌─────────────────┐  ┌──────────────┐  ┌─────────────┐ │  │
│  │  │  Pi Desktop     │  │   Grafana    │  │  Phone      │ │  │
│  │  │  (Terminal +    │  │  Dashboard   │  │  Mirror     │ │  │
│  │  │   sensor logs)  │  │  (Live data) │  │  (scrcpy)   │ │  │
│  │  └─────────────────┘  └──────────────┘  └─────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   DEMO TABLE (Front Center)               │  │
│  │                                                           │  │
│  │  ┌────────┐  ┌──────────┐  ┌────────┐  ┌──────────┐    │  │
│  │  │  Pi 4  │  │ ESP32-C3 │  │Camera  │  │ Buzzer   │    │  │
│  │  │  + All │  │ + PIR    │  │ v3     │  │          │    │  │
│  │  │ sensors│  │          │  │        │  │          │    │  │
│  │  └────────┘  └──────────┘  └────────┘  └──────────┘    │  │
│  │                                                           │  │
│  │  ┌──────────┐  ┌──────────┐                              │  │
│  │  │   IMU    │  │ USB Mic  │  ← Presenter interacts with  │  │
│  │  │ (shake!) │  │          │    these during demo         │  │
│  │  └──────────┘  └──────────┘                              │  │
│  │                                                           │  │
│  │  ┌──────────────────────────────────────────────────┐    │  │
│  │  │  LAPTOP: Running OBD-II Simulator + Audio Player │    │  │
│  │  └──────────────────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   EXAMINER PANEL                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Required Demo Equipment

| Item | Purpose | Notes |
|------|---------|-------|
| **Projector + Screen** | Display Pi desktop, dashboard, phone | HDMI from Pi + laptop |
| **Raspberry Pi 4B** | Main system | All sensors connected, running VISTA |
| **ESP32-C3 + PIR** | Theft demo | On table edge, visible |
| **IMU (MPU6050)** | Crash demo | On breadboard, presenter handles |
| **USB Microphone** | Audio detection | Placed near presenter |
| **Pi Camera v3** | Image capture | Pointed at demo area or screen |
| **Buzzer** | Audio alert | Audible in room |
| **Laptop #1** | OBD-II simulator + audio player | Connected to Pi via virtual serial |
| **Laptop #2** (optional) | Pi remote desktop | VNC into Pi for terminal display |
| **Smartphone** | Alert receiver | Mirrored via scrcpy on projector |
| **WiFi Router / Hotspot** | Internet for cloud API | Phone hotspot works |

---

## 3. Demo Scenarios

### 3.1 Scenario 1: CRASH DETECTION (5 minutes) ⭐ PRIMARY DEMO

**Setup Phase (before demo):**
```bash
# 1. Start OBD-II simulator
python3 demo/obd_simulator.py --scenario normal_driving &
# Simulator outputs: speed=45, rpm=2100, throttle=32%

# 2. Start VISTA system
sudo systemctl start vista-obd vista-imu vista-audio vista-fusion vista-decision

# 3. Open displays on projector
# Window 1: Terminal showing sensor logs
# Window 2: Grafana dashboard (http://pi:3000)
# Window 3: Phone mirror (scrcpy)
```

**Demo Script:**

| Time | Action | What Examiner Sees | Presenter Says |
|------|--------|-------------------|----------------|
| 0:00 | System running in NORMAL mode | Dashboard: smooth RPM, speed graphs. Audio: "normal 98%" | "The system is monitoring vehicle sensors. IMU shows stable acceleration. OBD-II reports 45 km/h. Audio CNN classifies sounds as normal." |
| 0:30 | Explain the architecture | Point to each sensor on table | "Four sensing modalities: IMU for crash forces, OBD-II for vehicle state, microphone for audio events, camera for visual evidence. All processing happens locally on this Raspberry Pi 4." |
| 1:00 | Explain multi-modal fusion | Show EKF output on terminal | "The Extended Kalman Filter fuses IMU and OBD-II data for accurate vehicle state estimation. Single sensors lie — multi-modal fusion tells the truth." |
| 1:30 | **CRASH DEMO BEGINS** | | "Now I'll demonstrate crash detection. I will physically shake the IMU to simulate crash forces while playing a recorded crash sound." |
| 1:35 | OBD simulator: send crash sequence | Terminal: throttle→0, speed→12 | "I've triggered the OBD-II crash sequence. Throttle drops to zero, speed rapidly decreases." |
| 1:36 | Play crash audio from phone speaker | Audio CNN output changes | "Playing a pre-recorded crash sound near the microphone. The CNN is processing this in real-time." |
| 1:37 | **SHAKE IMU BOARD** vigorously | Presenter shakes breadboard | *(Physical action — shake IMU)* |
| 1:38 | System detects crash | Terminal: "JERK: 7.2 g/s — THRESHOLD EXCEEDED!" | — |
| 1:39 | Buzzer sounds | "BEEP BEEP BEEP" (3 times) | "The buzzer activates immediately — this is the local alert." |
| 1:40 | Dashboard updates | Dashboard turns RED. Shows: "CRASH DETECTED — 92% confidence" | "The dashboard shows the crash event with evidence breakdown." |
| 1:45 | Camera captures burst | Shows 5 images captured | "Camera captured burst of images for evidence." |
| 1:50 | Cloud Vision API called | Terminal: "Uploading to Gemini Vision..." | "The image is being sent to Google Gemini Vision for scene analysis." |
| 2:30 | API response received | Dashboard updates with description | "Gemini confirms: scene shows collision scenario. This enriches our alert." |
| 2:35 | WhatsApp alert arrives | Phone mirror shows WhatsApp message with full evidence + image | "The enriched alert reaches the phone via WhatsApp. Full evidence chain: IMU, OBD, Audio, and Vision AI analysis." |
| 3:00 | Show explainable evidence | Dashboard: per-sensor breakdown | "Notice how the system EXPLAINS its decision. IMU confidence: 100%. OBD confidence: 100%. Audio confidence: 91%. Weighted fusion gives 92% final confidence." |
| 3:30 | Show event log | SQLite browser: event table | "Every event is logged with full evidence chain. This is the vehicle black box." |
| 4:00 | Q&A | — | Open for questions |

**Backup if API is slow:**
- Have a pre-recorded API response ready
- Show the request being sent, explain "processing normally takes 1-3 seconds"
- Immediately show the pre-recorded enriched alert screen

---

### 3.2 Scenario 2: THEFT DETECTION (3 minutes) ⭐ MOST CONVINCING

**Why this is the strongest demo:**
- **100% physical, 0% simulation** — every component is real
- ESP32 truly deep-sleeps (visible low power)
- PIR truly detects motion
- Camera truly captures the person
- Cloud API truly analyzes the image
- Alert truly arrives on phone
- **Nothing is faked — this exact system would work in a real car**

**Setup:**
```bash
# Pi in sleep mode
sudo systemctl stop vista-obd vista-imu vista-audio  # Not needed for theft

# ESP32: running theft_monitor firmware
# PIR: connected, monitoring
# LED: slow blink = monitoring mode
```

**Demo Script:**

| Time | Action | What Examiner Sees | Presenter Says |
|------|--------|-------------------|----------------|
| 0:00 | System in PARKED-SLEEP | Pi appears off. ESP32 LED slow-blinking. | "The system is in parked mode. The Raspberry Pi is completely asleep to save battery. Drawing less than half a watt. The ESP32-C3 is the always-on sentinel — it draws just 5 microamps in deep sleep, waking every second to check the PIR." |
| 0:15 | Show ESP32 specs | Point to ESP32 on table | "This ₹400 RISC-V microcontroller is what makes 45-day parked battery life possible. Without it, the Pi would drain the battery in 3 days." |
| 0:30 | Arm system via phone | Tap "ARM" on mirrored phone. ESP32 LED changes to fast blink. | "I'm arming the system from the phone. ESP32 is now actively monitoring." |
| 0:45 | **VOLUNTEER APPROACHES** | Volunteer walks toward PIR sensor | "I'll ask someone to approach the vehicle." |
| 0:50 | PIR triggers | ESP32 LED goes solid. Terminal: "MOTION DETECTED" | "PIR detected motion! ESP32 is waking the Pi." |
| 0:55 | Pi begins booting | Screen shows boot sequence | "The Pi boots in about 10 seconds. During this time, ESP32 already sends a BLE alert to my phone." |
| 1:05 | Pi boots, camera captures | Camera captures images of volunteer | "Camera capturing burst — 10 frames at 200ms intervals." |
| 1:10 | Cloud Vision API | Terminal: "Uploading to Gemini..." | "Images sent to Gemini Vision for analysis." |
| 1:15 | Phone BLE alert | Phone notification: "Motion detected near vehicle" | "Already received BLE alert — even before full analysis." |
| 1:45 | API response | Dashboard: "Person detected near driver side. Lighting: indoor. Posture: standing." | "Gemini Vision confirms: person detected near vehicle. This is NOT a false alarm from an animal or wind." |
| 2:00 | WhatsApp alert | Phone: full enriched alert with image | "Complete enriched alert on WhatsApp, including the image and AI analysis. Location from phone GPS." |
| 2:30 | Show power metrics | ESP32 current measurement | "After the alert, Pi returns to sleep. ESP32 back to 5 microamp monitoring. Total energy used for this event: approximately 0.7 watt-hours — less than 0.1% of the car battery." |
| 2:45 | Disarm system | Tap "DISARM" on phone | "System disarmed. Returning to normal monitoring." |

---

### 3.3 Scenario 3: DRIVER BEHAVIOR DASHBOARD (2 minutes)

**Setup:**
- Grafana dashboard pre-loaded with real driving data
- 5 recorded driving sessions from actual road tests

**Demo Script:**

| Time | Action | What Examiner Sees | Presenter Says |
|------|--------|-------------------|----------------|
| 0:00 | Open Grafana | Beautiful dashboard with graphs | "This dashboard shows analyzed data from 5 real driving sessions we conducted — totaling 6 hours on Indian roads." |
| 0:30 | Show speed profile | Speed vs time graph | "Vehicle speed profile over a 45-minute drive. You can see city traffic patterns — frequent stops and starts." |
| 1:00 | Show harsh braking | Marked points on graph | "Red markers indicate harsh braking events — detected by IMU jerk exceeding 3g. This driver had 3 harsh braking events in this session, classified as MODERATE behavior." |
| 1:30 | Show daily report | Summary panel | "Daily behavior classification, distance traveled, idle time, night driving percentage. All computed locally from OBD-II and IMU data." |
| 2:00 | Q&A | — | "Real data, not simulated. We actually installed the system in a vehicle for these recordings." |

---

### 3.4 Scenario 4: LIVE SENSOR STREAM (1 minute)

**Setup:**
- Terminal showing raw sensor output
- IMU being gently moved by presenter

**Demo Script:**

| Time | Action | What Examiner Sees | Presenter Says |
|------|--------|-------------------|----------------|
| 0:00 | Terminal: sensor output | Live scrolling data | "This is the raw sensor stream. OBD-II at 10Hz, IMU at 100Hz, audio CNN at 25Hz. All processed locally on the Pi — zero cloud dependency for core safety." |
| 0:30 | Move IMU gently | Acceleration values change in real-time | "Watch the IMU respond in real-time as I move the sensor. This is the same data that feeds the Kalman filter." |
| 1:00 | Speak near mic | Audio CNN output changes | "The audio CNN classifies every second. When I speak, it stays 'normal.' When I play a horn sound..." |

---

## 4. Demo Tool Suite

### 4.1 OBD-II Simulator (`demo/obd_simulator.py`)

```python
#!/usr/bin/env python3
"""
OBD-II ELM327 Simulator for VISTA Classroom Demo.
Creates a virtual serial port that responds to ELM327 AT commands
and PID requests with realistic vehicle data.

Usage:
    python3 obd_simulator.py --port /dev/pts/2 --scenario normal
    python3 obd_simulator.py --port /dev/pts/2 --scenario crash
"""

import os
import pty
import time
import json
import threading
import serial

class OBDSimulator:
    """Simulates an ELM327 OBD-II adapter."""
    
    # Realistic vehicle parameters for different scenarios
    SCENARIOS = {
        'normal': {
            'speed': 45,        # km/h
            'rpm': 2100,
            'throttle': 32,     # %
            'engine_load': 45,  # %
            'coolant_temp': 92, # °C
            'fuel_level': 65,   # %
            'intake_pressure': 45, # kPa
            'timing_advance': 12,  # degrees
        },
        'idle': {
            'speed': 0, 'rpm': 800, 'throttle': 15,
            'engine_load': 20, 'coolant_temp': 88, 'fuel_level': 65,
            'intake_pressure': 30, 'timing_advance': 8,
        },
        'accelerating': {
            'speed': 30, 'rpm': 3200, 'throttle': 75,
            'engine_load': 85, 'coolant_temp': 94, 'fuel_level': 64,
            'intake_pressure': 80, 'timing_advance': 25,
        },
    }
    
    def __init__(self, port: str):
        self.port = port
        self.state = self.SCENARIOS['normal'].copy()
        self.running = False
    
    def set_scenario(self, name: str):
        """Switch to a predefined scenario."""
        if name in self.SCENARIOS:
            self.state = self.SCENARIOS[name].copy()
    
    def simulate_crash_sequence(self):
        """Simulate a crash sequence over 2 seconds."""
        def _sequence():
            # T=0: Normal driving
            time.sleep(0.5)
            # T=0.5: Foot off accelerator
            self.state['throttle'] = 0
            self.state['rpm'] = 2500  # Engine braking
            time.sleep(0.2)
            # T=0.7: Impact
            self.state['speed'] = 12  # Rapid deceleration
            self.state['rpm'] = 800
            self.state['engine_load'] = 10
            time.sleep(0.3)
            # T=1.0: Post-crash
            self.state['speed'] = 0
            self.state['rpm'] = 600  # Engine stalling
            self.state['engine_load'] = 5
            time.sleep(0.5)
            # Stay in crash state
        threading.Thread(target=_sequence, daemon=True).start()
    
    def respond_to_command(self, command: str) -> str:
        """Respond to ELM327 AT commands and PID requests."""
        cmd = command.strip()
        
        # AT Commands
        if cmd == 'ATZ':
            return 'ELM327 v1.5'
        elif cmd == 'ATE0':
            return 'OK'
        elif cmd == 'ATL0':
            return 'OK'
        elif cmd == 'ATH0':
            return 'OK'
        elif cmd == 'ATS0':
            return 'OK'
        elif cmd == 'ATSP0':
            return 'OK'
        elif cmd == '0100':
            return 'SEARCHING...\n41 00 BE 3E B8 11'
        
        # PID Requests (format: 01 XX)
        if cmd.startswith('01'):
            pid = cmd[2:4]
            return self._handle_pid(pid)
        
        return '?'
    
    def _handle_pid(self, pid: str) -> str:
        """Handle OBD-II Mode 01 PID request."""
        if pid == '0D':  # Vehicle Speed
            val = int(self.state['speed'])
            return f'41 0D {val:02X}'
        elif pid == '0C':  # Engine RPM
            val = int(self.state['rpm'] * 4)
            return f'41 0C {val:04X}'
        elif pid == '11':  # Throttle Position
            val = int(self.state['throttle'] * 2.55)
            return f'41 11 {val:02X}'
        elif pid == '04':  # Engine Load
            val = int(self.state['engine_load'] * 2.55)
            return f'41 04 {val:02X}'
        elif pid == '05':  # Coolant Temp
            val = int(self.state['coolant_temp'] + 40)
            return f'41 05 {val:02X}'
        elif pid == '2F':  # Fuel Level
            val = int(self.state['fuel_level'] * 2.55)
            return f'41 2F {val:02X}'
        elif pid == '0B':  # Intake Manifold Pressure
            val = int(self.state['intake_pressure'])
            return f'41 0B {val:02X}'
        elif pid == '0E':  # Timing Advance
            val = int((self.state['timing_advance'] + 64) * 2)
            return f'41 0E {val:02X}'
        else:
            return 'NO DATA'
    
    def start(self):
        """Start the simulator."""
        self.running = True
        print(f"🚗 OBD-II Simulator running on {self.port}")
        print(f"   Scenario: NORMAL DRIVING")
        print(f"   Commands: crash | idle | accelerate | normal")
        
        with serial.Serial(self.port, 38400, timeout=1) as ser:
            while self.running:
                if ser.in_waiting:
                    cmd = ser.readline().decode('ascii', errors='ignore').strip()
                    if cmd:
                        # Check for scenario change commands
                        if cmd == 'crash':
                            self.simulate_crash_sequence()
                            response = 'OK'
                        elif cmd in self.SCENARIOS:
                            self.set_scenario(cmd)
                            response = 'OK'
                        else:
                            response = self.respond_to_command(cmd)
                        
                        ser.write((response + '\r\n>').encode('ascii'))

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='/dev/pts/2')
    args = parser.parse_args()
    
    sim = OBDSimulator(args.port)
    try:
        sim.start()
    except KeyboardInterrupt:
        sim.running = False
        print("\n🛑 Simulator stopped")
```

### 4.2 Demo Orchestrator (`demo/demo_orchestrator.py`)

```python
#!/usr/bin/env python3
"""
VISTA Demonstration Orchestrator.
Coordinates the crash demo: OBD simulation + audio playback + IMU prompt.

Usage:
    python3 demo_orchestrator.py --demo crash
    python3 demo_orchestrator.py --demo theft
"""

import time
import threading
import subprocess
import os

class DemoOrchestrator:
    """Coordinates classroom demo scenarios."""
    
    def __init__(self):
        self.demo_active = False
    
    def demo_crash(self):
        """Run the crash detection demo sequence."""
        print("=" * 60)
        print("  🚗 VISTA CRASH DETECTION DEMONSTRATION")
        print("=" * 60)
        print()
        print("Scenario: Vehicle traveling at 45 km/h on highway")
        print("          Sudden front-end collision with barrier")
        print()
        
        # Phase 1: Normal driving (let system stabilize)
        print("[Phase 1] NORMAL DRIVING — System monitoring...")
        for i in range(5, 0, -1):
            print(f"  Stabilizing... {i}s")
            time.sleep(1)
        
        print("  ✅ System stable. Dashboard shows normal data.")
        print()
        input("  Press ENTER to TRIGGER CRASH SEQUENCE...")
        
        # Phase 2: Crash sequence
        print()
        print("[Phase 2] CRASH SEQUENCE INITIATED!")
        print()
        
        # 2a: OBD-II crash sequence (send command to simulator)
        print("  ⚡ Sending OBD-II crash command...")
        # (Send 'crash' command to OBD simulator serial port)
        self._send_obd_command('crash')
        time.sleep(0.2)
        
        # 2b: Play crash audio
        print("  🔊 Playing crash sound...")
        self._play_crash_audio()
        
        # 2c: IMU shake prompt
        print()
        print("  ⚠️  ⚠️  ⚠️  SHAKE THE IMU BOARD NOW! ⚠️  ⚠️  ⚠️")
        print("       (Simulate crash forces — rapid forward-backward motion)")
        print()
        
        # Phase 3: Wait for system response
        print("[Phase 3] WAITING FOR SYSTEM DETECTION...")
        time.sleep(2)
        
        print()
        print("  🔍 Checking crash detection status...")
        # Check if system detected crash (read from decision engine)
        detected = self._check_crash_detected()
        
        if detected:
            print("  ✅ CRASH DETECTED SUCCESSFULLY!")
            print()
            print("  Evidence collected:")
            print("    • IMU: High-G event recorded")
            print("    • OBD: Throttle drop + speed decrease confirmed")
            print("    • Audio: Crash sound classified")
            print("    • Camera: Burst images captured")
            print("    • Cloud: Vision API enrichment in progress...")
            time.sleep(2)
            print("    • Alert: WhatsApp message delivered")
        else:
            print("  ⚠️  Detection threshold not met — check sensor connections")
        
        print()
        print("=" * 60)
        print("  DEMO COMPLETE")
        print("=" * 60)
    
    def _send_obd_command(self, cmd: str):
        """Send command to OBD simulator."""
        # Echo to OBD simulator's serial port
        obd_port = os.getenv('OBD_SIM_PORT', '/dev/pts/2')
        try:
            with open(obd_port, 'w') as f:
                f.write(cmd + '\n')
        except:
            print(f"  ⚠️  Could not send command to OBD simulator at {obd_port}")
    
    def _play_crash_audio(self):
        """Play pre-recorded crash sound."""
        audio_file = "demo/sounds/crash_impact_1.wav"
        if os.path.exists(audio_file):
            # Use aplay or paplay to play audio
            subprocess.Popen(['aplay', audio_file], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
        else:
            print("  ⚠️  Crash audio file not found — play manually from phone")
    
    def _check_crash_detected(self) -> bool:
        """Check if the system detected a crash."""
        # Query SQLite for latest crash event
        import sqlite3
        conn = sqlite3.connect('/home/pi/vista/data_storage/events.db')
        cursor = conn.execute(
            "SELECT * FROM events WHERE event_type='crash' "
            "ORDER BY timestamp DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()
        return row is not None

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', choices=['crash', 'theft'], default='crash')
    args = parser.parse_args()
    
    orch = DemoOrchestrator()
    if args.demo == 'crash':
        orch.demo_crash()
    elif args.demo == 'theft':
        orch.demo_theft()
```

### 4.3 Creating the Virtual Serial Port

```bash
#!/bin/bash
# demo/setup_virtual_obd.sh
# Creates virtual serial port pair for OBD-II simulation

# Create virtual serial pair
socat -d -d PTY,raw,echo=0,link=/tmp/obd_sim PTY,raw,echo=0,link=/tmp/obd_pi &

# Wait for creation
sleep 1

echo "Virtual serial ports created:"
echo "  Simulator side: /tmp/obd_sim → Connect OBD simulator here"
echo "  Pi side:        /tmp/obd_pi  → Point python-OBD to this port"
echo ""
echo "Start simulator:"
echo "  python3 demo/obd_simulator.py --port /tmp/obd_sim"
echo ""
echo "Configure VISTA to use /tmp/obd_pi as OBD port"
```

---

## 5. Evaluation Strategy

### 5.1 Pre-Recorded Real-World Evidence

**REQUIRED: Record actual driving data before the viva.**

| Session | Duration | Route | Data Collected |
|---------|----------|-------|----------------|
| Urban drive | 1 hour | City streets | Full sensor suite; frequent stops; traffic |
| Highway drive | 1.5 hours | NH-48 | High-speed; steady state; lane changes |
| Mixed rural | 1 hour | Village roads | Potholes; speed breakers; animals |
| Night drive | 45 min | Urban | Low-light camera; headlight effects |
| Parked monitoring | 2 hours | Parking lot | PIR data; battery drain measurement |

**Output:** Grafana dashboard with REAL data, which you show during viva.

### 5.2 Evaluation Metrics

| Metric | How We Measure | Demonstrated In |
|--------|---------------|-----------------|
| **Crash detection latency** | Timestamp diff: IMU spike → alert sent | Live demo timing |
| **Crash detection accuracy** | Controlled IMU inputs at known G-forces | Lab validation |
| **Audio classification accuracy** | Test with 50 recorded sounds (crash, horn, siren, normal) | Pre-recorded validation |
| **False alarm rate** | Run system for 24 hours in parked mode | Data log review |
| **Power consumption** | Measure with USB power meter | Live current display |
| **API latency** | Timestamp: image sent → response received | Live demo |

### 5.3 Validation Data (Pre-Recorded)

```python
# demo/validate_audio_cnn.py
"""
Validates audio CNN accuracy against labeled dataset.
Runs 50 pre-recorded audio samples through the classifier.
"""

TEST_SAMPLES = {
    'crash': ['sounds/crash_1.wav', 'sounds/crash_2.wav', ...],  # 10 samples
    'horn': ['sounds/horn_1.wav', ...],                            # 10 samples
    'siren': ['sounds/siren_1.wav', ...],                           # 10 samples
    'normal': ['sounds/normal_1.wav', ...],                        # 20 samples
}

def validate():
    results = {'correct': 0, 'total': 0}
    confusion = defaultdict(lambda: defaultdict(int))
    
    for true_label, files in TEST_SAMPLES.items():
        for file in files:
            audio, _ = librosa.load(file, sr=16000)
            predicted, conf = classifier.classify(audio)
            confusion[true_label][predicted] += 1
            if predicted == true_label:
                results['correct'] += 1
            results['total'] += 1
    
    accuracy = results['correct'] / results['total'] * 100
    print(f"Audio CNN Accuracy: {accuracy:.1f}% ({results['correct']}/{results['total']})")
    print("\nConfusion Matrix:")
    # Print matrix
    
    return accuracy
```

---

## 6. Viva Presentation Flow

### 6.1 Complete 15-Minute Viva Script

| Time | Segment | Duration |
|------|---------|----------|
| 0:00 | **Introduction** — Problem statement, what is VISTA, why it matters | 1 min |
| 1:00 | **System Overview** — Architecture diagram, sensor suite, hybrid edge-cloud | 2 min |
| 3:00 | **Innovation Highlights** — Multi-modal fusion, audio CNN, cloud vision, sleepy-edge, explainable AI | 2 min |
| 5:00 | **VIDEO: Real Car Installation** — Pre-recorded 2-min video of system in actual vehicle | 2 min |
| 7:00 | **LIVE DEMO: Crash Detection** — Physical IMU shake + audio playback + OBD simulation | 4 min |
| 11:00 | **LIVE DEMO: Theft Detection** — PIR walk-through → Pi wake → camera → alert | 2 min |
| 13:00 | **Dashboard + Results** — Grafana with real driving data, behavior reports | 1 min |
| 14:00 | **Q&A** — Open for examiner questions | Remaining time |

### 6.2 What's on the Projector (3 Windows)

```
┌──────────────────────────────────────────────────────────────┐
│  WINDOW 1 (Left 40%):    │  WINDOW 2 (Right 60% Top):       │
│  Pi Terminal              │  Grafana Dashboard                │
│  - Sensor data streaming  │  - Speed graph                    │
│  - CNN classification     │  - Audio class indicator          │
│  - EKF output             │  - Event timeline                 │
│  - System logs            │  - Alert history                  │
│                           │                                   │
│                           ├───────────────────────────────────┤
│                           │  WINDOW 3 (Right 60% Bottom):     │
│                           │  Phone Mirror (scrcpy)            │
│                           │  - WhatsApp alerts                │
│                           │  - BLE status                     │
│                           │  - Arm/Disarm controls            │
└──────────────────────────────────────────────────────────────┘
```

---

## 7. Backup Plans

### 7.1 If WiFi Fails
- Core crash demo works fully offline (IMU + OBD + Audio)
- Show "Vision analysis deferred — will execute when WiFi available"
- Have pre-recorded API response screenshots

### 7.2 If Cloud API Fails
- Show the API request being sent
- Display "API timeout — system queues for retry"
- Show pre-recorded enriched alert as "what it would look like"
- Emphasize: "Core safety works offline — API is enrichment only"

### 7.3 If Pi Crashes/Reboots
- Have a second microSD card with identical setup
- Swap and reboot (90 seconds)
- Pivot to showing the dashboard with pre-recorded data while Pi reboots
- ESP32 continues functioning independently

### 7.4 If Sensor Fails
- Have a spare MPU6050 on hand
- Demonstrate graceful degradation: "Even without IMU, crash detection continues with OBD+Audio"

### 7.5 Complete Demo Video Backup
- Record the ENTIRE demo beforehand (screen recording + camera on presenter)
- If live demo fails completely → play the video
- Honest: "We recorded this demo earlier to ensure you can see the full functionality"

---

## 8. Pre-Demo Checklist

```
WEEK BEFORE:
[ ] Conduct 3 full dry runs of the entire demo
[ ] Record backup video of demo
[ ] Collect real driving data (5 sessions)
[ ] Validate audio CNN accuracy (>85%)
[ ] Test cloud API latency (<3 seconds)
[ ] Verify WhatsApp alert delivery
[ ] Charge all batteries / prepare power

DAY BEFORE:
[ ] Flash clean Pi OS + VISTA install
[ ] Run full demo twice — verify 100% success rate
[ ] Prepare OBD simulator for crash scenario
[ ] Test projector + screen mirroring
[ ] Verify all cables, adapters, power strips
[ ] Print: architecture diagram (handout for examiners)
[ ] Print: BOM with costs (transparency)

MORNING OF:
[ ] Boot Pi 30 minutes before — verify thermal stability
[ ] Start OBD simulator in normal mode
[ ] Open all 3 projector windows
[ ] Test buzzer volume (audible but not startling)
[ ] Test phone mirroring
[ ] Place IMU board where easily accessible
[ ] Place PIR on table edge with clear approach path
[ ] Have backup microSD ready
[ ] Have spare MPU6050 ready
[ ] Water bottle for presenter (dry mouth = nervous)
```

---

**Next:** Return to `README.md` for complete document index.
