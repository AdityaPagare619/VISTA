# 02 — Hardware Design Document v3.0
## VISTA: Component Selection, Wiring & Power Architecture

**Version:** 3.0 | **Status:** Final — Physics-Verified | **Date:** May 10, 2026

---

## 1. Hardware Philosophy

> **"The best part is no part — and every remaining part must justify its physics."** If the Pi already has it, don't add it. If the phone already has it, use the phone. And if Pi can't do something (like sleep), don't pretend — engineer around it.

---

## 2. Complete Bill of Materials

### 2.1 Core Components (All Essential)

| # | Component | Model/Spec | ₹/unit | ₹ Total | Interface | Power |
|---|-----------|-----------|--------|---------|-----------|-------|
| 1 | Raspberry Pi 4B | 4GB RAM | 0 (owned) | 0 | — | 5V/3A via MOSFET |
| 2 | ESP32-C3 Dev Board | ESP32-C3-DevKitM-1 | 400 | 400 | GPIO to Pi | 5V direct from DC-DC |
| 3 | OBD-II Adapter | ELM327 USB | 500 | 500 | USB-A | Bus-powered |
| 4 | IMU Sensor | MPU6050 GY-521 | 150 | 150 | I2C (GPIO 2,3) | 3.3V/4mA |
| 5 | Pi Camera Module | Camera v3 (IMX708) | 1,800 | 1,800 | CSI ribbon | 3.3V/300mA |
| 6 | USB Microphone | Mini condenser, 16-bit | 200 | 200 | USB-A | Bus-powered |
| 7 | PIR Sensor | HC-SR501 | 60 | 60 | ESP32 GPIO0 | 5V/0.06mA |
| 8 | Active Buzzer | 5V piezo | 40 | 40 | GPIO 17 | 5V/30mA |
| 9 | DC-DC Converter | LM2596 / Mini560 | 300 | 300 | — | 12V→5V/3A |
| 10 | **P-MOSFET Switch** | **AO3401 (SOT-23) or IRF9540** | **50** | **50** | **ESP32 GPIO7→Gate** | **Controls Pi power** |
| 11 | **NPN transistor** | **2N2222 (level shifter)** | **10** | **10** | **ESP32→MOSFET gate** | — |
| 12 | MicroSD Card | 32GB High-Endurance | 400 | 400 | Pi microSD slot | — |
| 13 | **USB SSD** | **120GB (Kingston A400 or similar)** | **900** | **900** | **Pi USB-A** | **Bus-powered** |
| 14 | Voltage Divider | 100kΩ + 33kΩ (1%) | 5 | 5 | ESP32 ADC | — |
| 15 | Jumper Wires | M-M, M-F, F-F set | 150 | 150 | — | — |
| 16 | Breadboard | 400-point | 50 | 50 | — | — |
| 17 | 12V Cig Adapter | Cig lighter → barrel jack | 100 | 100 | — | — |
| 18 | Heat Sink + Fan Kit | Aluminum for Pi 4 | 200 | 200 | — | — |
| 19 | 3D Printed Enclosure | ABS (not PLA — warps at 60°C) | 400 | 400 | — | — |
| 20 | Pull-down resistors | 10kΩ × 2 | 5 | 5 | GPIO pull-downs | — |
| | **TOTAL (excl. Pi)** | | | **₹5,770** | | |

### 2.2 What We DON'T Buy (₹1,480 saved)

| Skipped | Why Not Needed | Saved |
|---------|---------------|-------|
| External WiFi dongle | Pi 4 has 802.11ac built-in | ₹300 |
| External BLE dongle | Pi 4 + ESP32 both have BLE 5.0 | ₹200 |
| LoRa SX1278 | WiFi + phone cellular sufficient | ₹400 |
| OLED display | Phone browser = superior display | ₹150 |
| DS18B20 temp sensor | OBD-II provides engine coolant temp | ₹80 |
| GPS module (default) | Phone GPS via BLE is more accurate | ₹350 |

---

## 3. Wiring & Pinout

### 3.1 Master Connection Diagram (v3.0 — with MOSFET switch)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     COMPLETE WIRING DIAGRAM v3.0                         │
│                                                                          │
│  ╔══════════════════════════════════════════════════════════════════╗   │
│  ║              POWER SOURCE                                        ║   │
│  ║                                                                  ║   │
│  ║   CAR BATTERY (12-14.6V)                                        ║   │
│  ║        │                                                         ║   │
│  ║        ├────► DC-DC LM2596 ────► 5V Rail ──┬──► ESP32 5V       ║   │
│  ║        │     (12V→5V/3A)                    │     (DIRECT)       ║   │
│  ║        │                                    │                    ║   │
│  ║        │                              ┌─────┴──────┐            ║   │
│  ║        │                              │ P-MOSFET   │            ║   │
│  ║        │                              │ (AO3401)   │            ║   │
│  ║        │                              │            │            ║   │
│  ║        │                              │ Gate ◄─┐   │            ║   │
│  ║        │                              │ Source ◄┤   │            ║   │
│  ║        │                              │ Drain ──┼──►Pi 5V Pin  ║   │
│  ║        │                              └────────┘│               ║   │
│  ║        │                                        │               ║   │
│  ║        │                              ┌─────────┘               ║   │
│  ║        │                              │ NPN 2N2222              ║   │
│  ║        │                              │ Base ◄── ESP32 GPIO7   ║   │
│  ║        │                              │ (10kΩ pull-down)        ║   │
│  ║        │                                                         ║   │
│  ║        └────► Batt Divider (100k+33k) ──► ESP32 GPIO8 (ADC)    ║   │
│  ╚══════════════════════════════════════════════════════════════════╝   │
│                                                                          │
│  KEY CHANGE FROM v2.1:                                                  │
│  • ESP32 powered DIRECTLY from DC-DC (not through Pi)                   │
│  • Pi powered THROUGH MOSFET controlled by ESP32                        │
│  • ESP32 can truly power-off Pi (0W) when not needed                    │
│                                                                          │
│  ╔══════════════════════════════════════════════════════════════════╗   │
│  ║              RASPBERRY PI 4B GPIO HEADER                        ║   │
│  ║                                                                  ║   │
│  ║   5V (from MOSFET) ═══ Pin 2,4                                  ║   │
│  ║   3.3V ═══ Pin 1 ──────► MPU6050 VCC                           ║   │
│  ║   GPIO2 (SDA) ═══ Pin 3 ──── MPU6050 SDA                      ║   │
│  ║   GPIO3 (SCL) ═══ Pin 5 ──── MPU6050 SCL                      ║   │
│  ║   GND ═══ Pin 6 ──── MPU6050 GND + shared ground              ║   │
│  ║   GPIO17 ═══ Pin 11 ──── Buzzer (+)                            ║   │
│  ║   GND ═══ Pin 9 ──── Buzzer (-)                                ║   │
│  ║   GPIO6 ═══ Pin 31 ──── ESP32 GPIO6 (heartbeat OUT)           ║   │
│  ║   CSI ═══ Pi Camera v3                                          ║   │
│  ║   USB-A ═══ ELM327 OBD-II                                      ║   │
│  ║   USB-A ═══ USB Microphone                                      ║   │
│  ║   USB-A ═══ USB SSD (database storage)                          ║   │
│  ╚══════════════════════════════════════════════════════════════════╝   │
│                                                                          │
│  ╔══════════════════════════════════════════════════════════════════╗   │
│  ║              ESP32-C3-DevKitM-1                                 ║   │
│  ║                                                                  ║   │
│  ║   5V ◄════ DC-DC 5V Rail (DIRECT — not through Pi)              ║   │
│  ║   GND ═════ Shared ground with Pi + DC-DC                      ║   │
│  ║   GPIO0 ◄════ PIR HC-SR501 OUT                                  ║   │
│  ║   GPIO6 ◄════ Pi GPIO6 (heartbeat — Pi toggles, ESP32 reads)  ║   │
│  ║   GPIO7 ═════► NPN Base → MOSFET Gate (Pi power control)      ║   │
│  ║   GPIO8 ◄════ Battery Voltage Divider (ADC1_CH0)              ║   │
│  ╚══════════════════════════════════════════════════════════════════╝   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 MOSFET Pi Power Switch Circuit (NEW in v3.0)

```
DC-DC 5V Rail ────────┬─── ESP32 5V (always powered)
                      │
                      │  ┌──── P-MOSFET (AO3401) ────┐
                      │  │  Source ◄── DC-DC 5V       │
                      │  │  Drain  ──► Pi 5V (Pin 2)  │
                      │  │  Gate   ◄── NPN Collector   │
                      │  └────────────────────────────┘
                      │
                      │  ┌──── NPN (2N2222) ──────────┐
                      │  │  Collector ──► MOSFET Gate  │
                      │  │  Emitter  ──► GND           │
                      │  │  Base     ◄── ESP32 GPIO7   │
                      │  │              (via 1kΩ)      │
                      │  └────────────────────────────┘
                      │
                      │  10kΩ pull-down: MOSFET Gate → DC-DC 5V
                      │  (ensures Pi OFF when ESP32 not driving)

Logic:
  ESP32 GPIO7 = LOW  → NPN off → MOSFET gate pulled HIGH → Pi OFF
  ESP32 GPIO7 = HIGH → NPN on  → MOSFET gate pulled LOW  → Pi ON

Default state (ESP32 in deep sleep): Pi is OFF (safe default)
```

**Why P-channel MOSFET?** It switches the high side (5V rail). When ESP32 is in deep sleep (all GPIOs float), the pull-down resistor keeps the MOSFET gate HIGH (off state) → Pi stays powered off. This is fail-safe.

### 3.3 Quick Connection Tables

**RASPBERRY PI CONNECTIONS:**

| Pi Pin | Physical Pin# | Connects To | Direction |
|--------|---------------|-------------|-----------|
| 5V (switched) | 2, 4 | MOSFET Drain (from DC-DC via switch) | INPUT |
| 3.3V | 1 | MPU6050 VCC | OUTPUT |
| GPIO2 (SDA) | 3 | MPU6050 SDA | Bidirectional |
| GPIO3 (SCL) | 5 | MPU6050 SCL | Bidirectional |
| GND | 6 | MPU6050 GND + shared | Common |
| GND | 9 | Buzzer (-) | Common |
| GPIO17 | 11 | Buzzer (+) | OUTPUT |
| GPIO6 | 31 | ESP32 GPIO6 (heartbeat) | OUTPUT |
| CSI | — | Pi Camera v3 | Bidirectional |
| USB-A #1 | — | ELM327 OBD-II | Bidirectional |
| USB-A #2 | — | USB Microphone | Input |
| USB-A #3 | — | USB SSD (120GB) | Bidirectional |

**ESP32-C3 CONNECTIONS:**

| ESP32 Pin | Connects To | Direction | Purpose |
|-----------|-------------|-----------|---------|
| 5V | DC-DC 5V Rail (DIRECT) | INPUT | Always-on power |
| GND | Shared ground | Common | Ground |
| GPIO0 | PIR OUT pin | INPUT | Motion detection |
| GPIO6 | Pi GPIO6 (Pin 31) | INPUT | Pi heartbeat monitor |
| GPIO7 | NPN Base (via 1kΩ) | OUTPUT | **Pi power control (MOSFET)** |
| GPIO8 | Battery divider junction | INPUT (ADC) | Battery voltage monitor |

### 3.4 Battery Voltage Divider (unchanged from v2.1)

```
V_ADC = V_BAT × (33 / 133) = V_BAT × 0.248
At 12.6V: V_ADC = 3.12V (safe for ESP32 3.3V max)
At 11.8V: V_ADC = 2.93V (low battery threshold)

⚠️ Use 1% tolerance resistors.
⚠️ NEVER connect car battery directly to ESP32 ADC.
```

### 3.5 ESP32 ↔ Pi Protocol (v3.0)

```
POWER CONTROL (ESP32 GPIO7 → MOSFET → Pi power):
  ESP32 sets GPIO7 HIGH → Pi receives 5V → cold boots (35s)
  ESP32 sets GPIO7 LOW  → Pi power cut → 0W draw

HEARTBEAT (Pi GPIO6 → ESP32 GPIO6):
  Pi toggles GPIO6 at 1 Hz when alive
  ESP32 monitors: if no toggle for >30s:
    → Pi is dead/hung
    → ESP32 power-cycles Pi (GPIO7 LOW, wait 5s, GPIO7 HIGH)
    → Log: "Pi watchdog reset"
    → BLE: "VISTA-PI-RESET"

SHUTDOWN SEQUENCE:
  Pi receives "prepare shutdown" via MQTT from ESP32
  Pi flushes databases, stops services
  Pi signals "ready for power-off" via GPIO6 (held HIGH for 3s)
  ESP32 detects steady HIGH → cuts MOSFET → Pi off
```

---

## 4. Power Architecture (v3.0 — True Power Control)

### 4.1 Power Tree

```
CAR BATTERY (12-14.6V)
        │
        ▼
┌───────────────────┐
│ DC-DC Converter   │  LM2596 / Mini560
│ 12V → 5V / 3A    │  Efficiency: ~85%
└────────┬──────────┘
         │ 5V rail
         │
    ┌────┴──────────────────────────────┐
    │                                    │
    ▼                                    ▼
┌──────────────┐              ┌──────────────┐
│   ESP32-C3   │              │  P-MOSFET    │
│ (ALWAYS ON)  │              │  Switch      │
│              │              │              │
│ GPIO7 ───────┼──────────────┤ Gate         │
│ GPIO0 ◄──────┼── PIR        │              │
│ GPIO6 ◄──────┼── Pi HB      │ Drain ───────┼──▶ Pi 5V
│ GPIO8 ◄──────┼── BATT DIV   │              │
│              │              │ Source ◄──────┼── DC-DC 5V
└──────────────┘              └──────────────┘
                                     │
                              ┌──────┴──────┐
                              │  RPi 4B     │
                              │ (SWITCHED)  │
                              │             │
                              │ 3.3V → IMU  │
                              │ CSI → Cam   │
                              │ USB → OBD   │
                              │ USB → Mic   │
                              │ USB → SSD   │
                              │ GPIO17→Buzz │
                              └─────────────┘
```

### 4.2 Power States (Physics-Verified)

| State | Pi Power | Pi Draw | ESP32 Draw | Total System | Battery Life (45Ah) |
|-------|----------|---------|------------|-------------|-------------------|
| **DRIVING** | MOSFET ON | 8W | 0.3W | 8.3W | N/A (engine running) |
| **PARKED-ACTIVE** | MOSFET ON | 8W | 0.3W | 8.3W | ~32 hours continuous |
| **PARKED-MONITOR** | **MOSFET OFF** | **0W** | 0.3W | **0.3W** | **37.5 days** |
| **PARKED-SLEEP** | **MOSFET OFF** | **0W** | 5μA | **~0W** | **>1 year** |
| **LOW-BATT** | **MOSFET OFF (forced)** | **0W** | 0.3W | 0.3W | Protected |

### 4.3 Battery Life Calculator (Honest)

```
Standard car battery: 45Ah @ 12V = 540 Wh
Safe discharge limit: 50% (270 Wh usable)

PARKED-MONITOR (ESP32 active, Pi OFF via MOSFET):
  Draw: 0.3W
  Time to 50%: 270 / 0.3 = 900 hours = 37.5 days ✅

PARKED-SLEEP (ESP32 deep sleep, Pi OFF):
  Draw: ~25μW (ESP32 deep sleep)
  Time to 50%: 270 / 0.000025 = 10,800,000 hours ≈ forever ✅

Per theft/alert event (Pi boots for 5 min):
  Energy: 8.3W × (5/60)h = 0.69 Wh per event
  Events before 10% battery impact: 270 × 0.10 / 0.69 ≈ 39 events ✅

Verdict: True power control via MOSFET eliminates battery drain concern.
v3.0 is genuinely BETTER than v2.1's impossible "Pi sleep" claim.
```

---

## 5. Thermal Considerations

| Condition | Cabin Temp | Pi | ESP32 | Action |
|-----------|-----------|----|----|--------|
| Driving (AC on) | 25-35°C | Normal operation | Normal | None needed |
| Driving (no AC) | 40-50°C | Throttled; heatsink+fan critical | Normal | Monitor SoC temp |
| Parked (shade) | 35-50°C | OFF (MOSFET) | Deep sleep | No concern |
| Parked (sun, summer) | 60-70°C | OFF (MOSFET) | Deep sleep (rated 125°C) | No concern |
| Wake event in hot cabin | >55°C | **BLOCKED by ESP32** | Active | BLE alert "Too hot" |

> Pi's rated ambient range is 0-50°C. The MOSFET switch ensures Pi is never powered on in unsafe thermal conditions.

---

## 6. Enclosure Design

- **Material:** ABS (not PLA — PLA warps at 60°C, Indian cabin exceeds this)
- **Wall thickness:** 3mm
- **Ventilation:** Slots on top and sides (for driving mode when AC runs)
- **Pi mount:** M2.5 standoffs
- **Camera mount:** External via ribbon cable slot
- **SSD mount:** Velcro-mounted inside enclosure or external via USB cable
- **Dimensions:** ~140 × 90 × 55mm (slightly larger than v2.1 to accommodate SSD)

---

## 7. Component Sourcing (India)

| Component | Vendor | Note |
|-----------|--------|------|
| ESP32-C3-DevKitM-1 | Robu.in / Amazon | ~₹400 |
| ELM327 USB | Amazon / local auto shop | Get USB (not Bluetooth) |
| MPU6050 GY-521 | Robu.in / ElectronicsComp | ~₹150 |
| Pi Camera v3 | Official Pi reseller | ~₹1,800 |
| AO3401 P-MOSFET | Robu.in / ElectronicsComp | SOT-23 package, ~₹30-50 |
| 2N2222 NPN | Any electronics shop | ~₹10 |
| 120GB USB SSD | Amazon / Flipkart | Kingston A400 or WD Green |
| 32GB High-Endurance SD | Amazon | Samsung PRO Endurance |

---

## 8. Pre-Build Checklist

```
[ ] Raspberry Pi 4B tested and booting from SD card
[ ] Pi OS (Bookworm 64-bit) installed; SSH + WiFi configured
[ ] I2C enabled via raspi-config
[ ] Camera enabled via raspi-config
[ ] USB SSD formatted (ext4) and auto-mounted in /etc/fstab
[ ] ESP32-C3 tested with Blink sketch
[ ] MOSFET circuit tested: ESP32 GPIO7 HIGH → Pi gets power
[ ] MOSFET circuit tested: ESP32 GPIO7 LOW → Pi power CUT (verify 0V)
[ ] MPU6050 tested with I2C scan (address 0x68)
[ ] ELM327 tested with python-OBD on bench (measure ACTUAL polling rate!)
[ ] USB mic tested with arecord
[ ] PIR tested with ESP32 GPIO read
[ ] DC-DC output verified at 5.0V ±0.1V
[ ] Battery voltage divider verified (12V input → ~3.0V at ESP32 ADC)
[ ] Heartbeat protocol tested: Pi toggles GPIO6, ESP32 reads
[ ] All jumper wires continuity tested
```

---

**Next:** See `03_SOFTWARE_ARCHITECTURE.md` for corrected EKF, separated crash detector, and updated module design.
