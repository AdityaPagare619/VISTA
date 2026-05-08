# 02 — Hardware Design Document
## VISTA: Component Selection, Wiring & Power Architecture

**Version:** 2.1 | **Status:** Final | **Date:** May 8, 2026

---

## 1. Hardware Philosophy

> **"The best part is no part."** Every component must justify its existence. If the Pi already has it (WiFi, BLE), don't add an external module. If the phone already has it (GPS, display), use the phone instead.

---

## 2. Complete Bill of Materials

### 2.1 Core Components (All Essential)

| # | Component | Model/Spec | Qty | ₹/unit | ₹ Total | Interface | Power |
|---|-----------|-----------|-----|--------|---------|-----------|-------|
| 1 | Raspberry Pi 4B | 4GB RAM | 1 | 0 (owned) | 0 | — | 5V/3A via GPIO |
| 2 | ESP32-C3 Dev Board | ESP32-C3-DevKitM-1 | 1 | 400 | 400 | GPIO to Pi | 5V/0.5A via Pi |
| 3 | OBD-II Adapter | ELM327 USB | 1 | 500 | 500 | USB-A | Bus-powered |
| 4 | IMU Sensor | MPU6050 GY-521 | 1 | 150 | 150 | I2C (GPIO 2,3) | 3.3V/4mA |
| 5 | Pi Camera Module | Camera v3 (IMX708) | 1 | 1,800 | 1,800 | CSI ribbon | 3.3V/300mA |
| 6 | USB Microphone | Mini condenser, 16-bit | 1 | 200 | 200 | USB-A | Bus-powered |
| 7 | PIR Sensor | HC-SR501 | 1 | 60 | 60 | ESP32 GPIO | 5V/0.06mA |
| 8 | Active Buzzer | 5V piezo | 1 | 40 | 40 | GPIO 17 | 5V/30mA |
| 9 | DC-DC Converter | LM2596 / Mini560 | 1 | 300 | 300 | — | 12V→5V/3A |
| 10 | MicroSD Card | 32GB Class 10 A1 | 1 | 350 | 350 | Pi microSD slot | — |
| 11 | Voltage Divider Resistors | 100kΩ + 33kΩ (1% tolerance) | 1 set | 5 | 5 | Battery monitoring | — |
| 12 | Jumper Wires | M-M, M-F, F-F set | 1 pk | 150 | 150 | — | — |
| 13 | Breadboard | 400-point | 1 | 50 | 50 | — | — |
| 14 | 12V Cig Adapter | Cig lighter → barrel jack | 1 | 100 | 100 | — | — |
| 15 | Heat Sink Kit | Aluminum + fan for Pi 4 | 1 | 200 | 200 | Critical for Indian summer | — |
| 16 | Enclosure | 3D printed ABS | 1 | 400 | 400 | — | — |
| **CORE TOTAL** | | | | | **₹4,705** | | |

### 2.2 Optional Components

| # | Component | Model/Spec | Qty | ₹/unit | ₹ Total | When to Buy |
|---|-----------|-----------|-----|--------|---------|-------------|
| 15 | USB GPS Dongle | U-Blox 7 (VK-172) | 1 | 350 | 350 | If theft tracking needed |
| 16 | Heat Sink Kit | Aluminum + fan for Pi 4 | 1 | 200 | 200 | Recommended for summer |
| **FULL TOTAL** | | | | | **₹5,050** | |

### 2.3 What We DON'T Buy (Smart Engineering)

| Skipped Item | Why Not Needed | Saved ₹ |
|-------------|----------------|---------|
| External WiFi dongle | Pi 4 has 802.11ac built-in | 300 |
| External BLE dongle | Pi 4 + ESP32 both have BLE 5.0 | 200 |
| LoRa SX1278 module | WiFi + phone cellular covers all scenarios | 400 |
| OLED display | Phone browser = better display | 150 |
| DS18B20 temp sensor | OBD-II provides engine coolant temp | 80 |
| GPS module (default) | Phone GPS via BLE is more accurate | 350 |
| **GRAND TOTAL SAVED** | | **₹1,480** |

---

## 3. Wiring & Pinout

### 3.1 Master Connection Diagram (Pi ↔ ESP32 ↔ All Sensors)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     COMPLETE WIRING DIAGRAM                              │
│                                                                          │
│  ╔══════════════════════════════════════════════════════════════════╗   │
│  ║              RASPBERRY PI 4B GPIO HEADER (40-pin)               ║   │
│  ║                                                                  ║   │
│  ║        3.3V ═══ 1 ●  ●  2 ═══ 5V ──────────────┐               ║   │
│  ║   MPU SDA ═══ 3 ●  ●  4 ═══ 5V                │               ║   │
│  ║   MPU SCL ═══ 5 ●  ●  6 ═══ GND ───┬── MPU GND│               ║   │
│  ║             7 ●  ●  8 ═══ GPIO14    │          │               ║   │
│  ║            ╔══════════════════╗      │          │               ║   │
│  ║  BUZZER ═══╣ 11 (GPIO17)  12 ║      │   ╔══════╩══════════╗    ║   │
│  ║            ║ 13 (GPIO27)  14 ║ GND  │   ║   MPU6050      ║    ║   │
│  ║            ║ 15 (GPIO22)  16 ║      │   ║ ┌────────────┐ ║    ║   │
│  ║      3.3V ═╣ 17           18 ║      │   ║ │VCC → Pi 3.3V│ ║    ║   │
│  ║            ║ 19 (GPIO10)  20 ║ GND  │   ║ │GND → Pi GND │ ║    ║   │
│  ║            ║ 21 (GPIO9)   22 ║      │   ║ │SDA → Pin 3  │ ║    ║   │
│  ║            ║ 23 (GPIO11)  24 ║      │   ║ │SCL → Pin 5  │ ║    ║   │
│  ║            ╠══════════════════╣      │   ║ └────────────┘ ║    ║   │
│  ║   ←WAKE IN ╣ 29 (GPIO5)   30 ║ GND  │   ╚═════════════════╝    ║   │
│  ║ HEARTBEAT→ ╣ 31 (GPIO6)   32 ║      │                          ║   │
│  ║            ║ 33 (GPIO13)  34 ║ GND  │   ╔══════════════════╗   ║   │
│  ║            ║ 35 (GPIO19)  36 ║      │   ║  BUZZER (5V)    ║   ║   │
│  ║            ║ 37 (GPIO26)  38 ║      │   ║ + → GPIO17      ║   ║   │
│  ║            ╠══════════════════╣      │   ║ - → GND (Pin 9) ║   ║   │
│  ║       GND ═╣ 39           40 ║      │   ╚══════════════════╝   ║   │
│  ║            ╚══════════════════╝      │                          ║   │
│  ║                                      │                          ║   │
│  ║  CSI Port ═══════ Pi Camera v3      │                          ║   │
│  ║  USB-A   ═══════ ELM327 OBD-II      │                          ║   │
│  ║  USB-A   ═══════ USB Microphone     │                          ║   │
│  ║  microSD ═══════ 32GB Card          │                          ║   │
│  ║  HDMI    ═══════ (monitor/debug)    │                          ║   │
│  ╚══════════════════════════════════════╩══════════════════════════╝   │
│                                                                          │
│  ╔══════════════════════════════════════════════════════════════════╗   │
│  ║              ESP32-C3-DevKitM-1                                 ║   │
│  ║                                                                  ║   │
│  ║   USB-C ═════ (flash + power during programming)                ║   │
│  ║                                                                  ║   │
│  ║   GPIO0 ◄════ PIR HC-SR501 OUT pin                              ║   │
│  ║   GPIO4 ═════► Pi GPIO5 (WAKE signal — ESP32 wakes Pi)         ║   │
│  ║   GPIO6 ◄════  Pi GPIO6 (HEARTBEAT — Pi toggles, ESP32 reads)  ║   │
│  ║   GPIO8 ◄════  Battery Voltage Divider (ADC1_CH0)              ║   │
│  ║                                                                  ║   │
│  ║   5V    ◄════  Pi Pin 2/4 (5V rail — powered FROM Pi)           ║   │
│  ║   GND   ═════  Pi GND (Pin 6/9/14/20/25/30/34/39 — any)       ║   │
│  ╚══════════════════════════════════════════════════════════════════╝   │
│                                                                          │
│  ╔══════════════════════════════════════════════════════════════════╗   │
│  ║              POWER SOURCE                                        ║   │
│  ║                                                                  ║   │
│  ║   CAR BATTERY (12-14.6V)                                        ║   │
│  ║        │                                                         ║   │
│  ║        ├────► DC-DC LM2596 ────► 5V ────► Pi Pin 2 & 4         ║   │
│  ║        │     (12V→5V/3A)           │                             ║   │
│  ║        │                           └────► ESP32 5V pin           ║   │
│  ║        │                                                         ║   │
│  ║        └────► Batt Divider (100k+33k) ──► ESP32 GPIO8 (ADC)    ║   │
│  ║                                                                  ║   │
│  ╚══════════════════════════════════════════════════════════════════╝   │
│                                                                          │
│   LEGEND:                                                                │
│   ═══►  OUTPUT (this device drives the line)                            │
│   ◄═══  INPUT (this device reads the line)                              │
│   ═════ BIDIRECTIONAL (I2C, USB data)                                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Quick Connection Table (Print This!)

**RASPBERRY PI CONNECTIONS:**

| Pi Pin | Physical Pin# | Connects To | Direction | Wire Color (suggested) |
|--------|---------------|-------------|-----------|----------------------|
| 3.3V | 1 | MPU6050 VCC | Pi OUTPUT | Red |
| 5V | 2 or 4 | ESP32 5V pin | Pi OUTPUT | Red |
| GPIO2 (SDA) | 3 | MPU6050 SDA | Bidirectional | Yellow |
| GPIO3 (SCL) | 5 | MPU6050 SCL | Bidirectional | Green |
| GND | 6 | MPU6050 GND + ESP32 GND | Common | Black |
| GND | 9 | Buzzer - | Common | Black |
| GPIO17 | 11 | Buzzer + | Pi OUTPUT | Orange |
| GND | 14,20,25,30,34,39 | (spare ground pins) | Common | — |
| GPIO5 | 29 | ESP32 GPIO4 | Pi INPUT (ESP32 wakes Pi) | Blue |
| GPIO6 | 31 | ESP32 GPIO6 | Pi OUTPUT (heartbeat to ESP32) | Purple |
| CSI (ribbon) | — | Pi Camera v3 | Bidirectional | Ribbon cable |
| USB-A | — | ELM327 OBD-II | Bidirectional | USB cable |
| USB-A | — | USB Microphone | Bidirectional | USB cable |

**ESP32-C3 CONNECTIONS:**

| ESP32 Pin | Connects To | Direction | Purpose |
|-----------|-------------|-----------|---------|
| 5V | Pi 5V (Pin 2 or 4) | ESP32 INPUT | Power from Pi |
| GND | Pi GND (any) | Common | Ground |
| GPIO0 | PIR OUT pin | ESP32 INPUT | Motion detection |
| GPIO4 | Pi GPIO5 (Pin 29) | ESP32 OUTPUT | Wake Pi signal (HIGH=500ms wakes Pi) |
| GPIO6 | Pi GPIO6 (Pin 31) | ESP32 INPUT | Pi heartbeat monitor (>30s no toggle = Pi dead) |
| GPIO8 | Battery divider junction | ESP32 INPUT (ADC) | Battery voltage monitor |

**SENSOR CONNECTIONS:**

| Sensor | Pin | Connects To |
|--------|-----|-------------|
| **MPU6050** | VCC | Pi 3.3V (Pin 1) |
| | GND | Pi GND (Pin 6) |
| | SDA | Pi GPIO2 (Pin 3) |
| | SCL | Pi GPIO3 (Pin 5) |
| **PIR HC-SR501** | VCC | ESP32 5V or Pi 5V |
| | GND | ESP32 GND or Pi GND |
| | OUT | ESP32 GPIO0 |
| **Buzzer** | + | Pi GPIO17 (Pin 11) |
| | - | Pi GND (Pin 9) |
| **ELM327** | USB | Pi USB-A port |
| **USB Mic** | USB | Pi USB-A port |
| **Pi Cam v3** | CSI ribbon | Pi CSI port |
| **DC-DC LM2596** | IN+ | Car 12V+ |
| | IN- | Car 12V- (GND) |
| | OUT+ | Pi 5V (Pin 2 or 4) |
| | OUT- | Pi GND (any) |

### 3.3 Battery Voltage Divider (ESP32 ADC)

```
Car Battery (+) 12-14V
       │
       ├──── R1 (100kΩ) ────┬──── ESP32 GPIO8 (ADC1_CH0)
       │                     │
       │                    R2 (33kΩ)
       │                     │
       └─────────────────────┴──── GND (connect to car chassis or Pi GND)

V_ADC = V_BAT × (R2 / (R1 + R2))
V_ADC = V_BAT × (33 / 133) = V_BAT × 0.248

At 12.6V: V_ADC = 3.12V (safe for ESP32 3.3V max)
At 11.8V: V_ADC = 2.93V (low battery threshold → ESP32 stops waking Pi)

⚠️ WARNING: Use 1% tolerance resistors for accuracy.
⚠️ WARNING: Do NOT connect car battery directly to ESP32 ADC!
⚠️ WARNING: The divider MUST be connected. Without it, 12V destroys the ESP32.
```

### 3.4 Pi ↔ ESP32 GPIO Protocol (Critical!)

```
WAKE SIGNAL (ESP32 GPIO4 → Pi GPIO5):
  ┌─────────────────────────────────────────────────────────┐
  │ ESP32 detects PIR motion                                │
  │   → ESP32 sets GPIO4 HIGH                               │
  │   → Wait 500 milliseconds                               │
  │   → ESP32 sets GPIO4 LOW                                │
  │   → Pi GPIO5 detects rising edge → Pi wakes from sleep  │
  │   → Pi boots (10 seconds)                               │
  │   → Pi GPIO6 starts toggling (heartbeat)                │
  └─────────────────────────────────────────────────────────┘

HEARTBEAT SIGNAL (Pi GPIO6 → ESP32 GPIO6):
  ┌─────────────────────────────────────────────────────────┐
  │ After Pi boots:                                         │
  │   → Pi toggles GPIO6 at 1 Hz (HIGH 500ms, LOW 500ms)   │
  │   → ESP32 reads GPIO6 to confirm Pi is alive            │
  │   → If ESP32 sees NO toggle for >30 seconds:            │
  │       → Pi is dead/unresponsive                         │
  │       → ESP32 logs error, continues PIR monitoring      │
  │       → ESP32 advertises BLE: "VISTA-PI-DEAD"           │
  └─────────────────────────────────────────────────────────┘

IMPORTANT: Pi GPIO5 must be configured as INPUT with pull-down.
           Pi GPIO6 must be configured as OUTPUT.
           ESP32 GPIO4 must be configured as OUTPUT (open-drain or push-pull).
           ESP32 GPIO6 must be configured as INPUT.
```

---

## 4. Power Architecture

### 4.1 Power Tree

```
CAR BATTERY (12-14.6V)
        │
        ▼
┌───────────────────┐
│ DC-DC Converter   │  LM2596 / Mini560
│ 12V → 5V / 3A     │  Efficiency: ~85%
│ LVD: 11.5V cutoff │  Ripple: <50mV
└────────┬──────────┘
         │ 5V rail
         │
    ┌────┴────────────────────────┐
    │                             │
    ▼                             ▼
┌─────────┐              ┌──────────────┐
│ RPi 4B  │              │   ESP32-C3   │
│         │              │              │
│ 5V GPIO ├──────────────┤ 5V (from Pi) │
│ pin 2,4 │              │              │
│         │              │ GPIO4 ───────┼──▶ Pi WAKE (GPIO5)
│ 3.3V ──┼──▶ MPU6050   │ GPIO6 ◄──────┼── Pi STATUS (GPIO6)
│ CSI ────┼──▶ Camera   │              │
│ USB ────┼──▶ ELM327   │ GPIO0 ◄──────┼── PIR OUT
│ USB ────┼──▶ Mic      │ GPIO8 ◄──────┼── BATT DIVIDER
│ GPIO17 ─┼──▶ Buzzer   │              │
└─────────┘              └──────────────┘
```

### 4.2 Power States

| State | Pi | ESP32 | Total Draw | Trigger |
|-------|----|----|-----------|---------|
| **DRIVING** | Active (8W) | Active (0.3W) | 8.3W | Ignition ON |
| **PARKED-ACTIVE** | Active (8W) | Active (0.3W) | 8.3W | PIR triggered |
| **PARKED-SLEEP** | Off (0W) | Deep sleep (5μA) | <0.001W | Timeout 5 min |
| **PARKED-MONITOR** | Off (0W) | Active (0.3W) | 0.3W | PIR monitoring |
| **LOW-BATT** | Locked OFF | Active (0.3W) | 0.3W | VBAT < 11.8V |

### 4.3 Battery Life Calculator

```
Standard car battery: 45Ah @ 12V = 540 Wh

PARKED-MONITOR mode (ESP32 active, Pi off):
  Draw: 0.3W
  Time to 50% discharge: (540 × 0.5) / 0.3 = 900 hours = 37.5 days

PARKED-SLEEP mode (ESP32 deep sleep):
  Draw: ~0.001W
  Time to 50% discharge: Effectively infinite (>1 year)

PARKED-ACTIVE (after PIR trigger, Pi wakes for 5 min):
  Draw: 8.3W for 5 min = 0.69 Wh per event
  100 events before 10% battery impact

Verdict: ZERO risk of battery drain under normal use.
Even 2-week vacation → <15% battery used.
```

---

## 5. Enclosure Design

### 5.1 Requirements
- Heat resistant (Indian cabin can reach 70°C)
- Ventilation for Pi airflow
- Dust protection (IP54 minimum)
- Accessible ports (USB, CSI, GPIO for debugging)
- Mountable under dashboard or seat

### 5.2 3D Print Specs
- Material: ABS (not PLA — PLA warps at 60°C)
- Wall thickness: 3mm
- Ventilation slots on top and sides
- Pi mount: M2.5 standoffs
- Camera mount: external via ribbon cable slot
- Dimensions: ~120 × 80 × 50mm (compact)

---

## 6. Component Sourcing

### 6.1 Recommended Vendors (India)

| Component | Vendor | Link/Note |
|-----------|--------|-----------|
| ESP32-C3-DevKitM-1 | Robu.in / Amazon | ~₹400 |
| ELM327 USB | Amazon / local auto shop | Get USB version (not Bluetooth) |
| MPU6050 GY-521 | Robu.in / ElectronicsComp | ~₹150 |
| Pi Camera v3 | Robu.in / Official Pi reseller | ~₹1,800 |
| USB Microphone | Amazon Basics / local | Any 16-bit USB mic |
| PIR HC-SR501 | Any electronics shop | ~₹60 |
| LM2596 DC-DC | Robu.in / Amazon | Get version with display |
| 32GB microSD | Amazon / Flipkart | Samsung EVO or SanDisk Ultra |
| Jumper wires + breadboard | Local electronics | Standard |
| Enclosure | 3D print yourself | ABS filament |

### 6.2 Pre-Build Checklist

```
[ ] Raspberry Pi 4B tested and booting
[ ] Pi OS (Bookworm 64-bit) installed on microSD
[ ] SSH enabled; WiFi configured
[ ] I2C enabled via raspi-config
[ ] Camera enabled via raspi-config
[ ] ESP32-C3 tested with Blink sketch
[ ] MPU6050 tested with I2C scan
[ ] ELM327 tested with python-OBD on bench
[ ] USB mic tested with arecord
[ ] PIR tested with ESP32 GPIO read
[ ] DC-DC output verified at 5.0V ±0.1V
[ ] All jumper wires continuity tested
```

---

**Next:** See `03_SOFTWARE_ARCHITECTURE.md` for the software design.
