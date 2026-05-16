# 02 — Hardware Design Document v4.0
## VISTA: Component Selection, Wiring & Power Architecture

**Version:** 4.0 | **Status:** Built & Verified | **Date:** May 16, 2026

> All pin numbers, voltages, and currents verified against `config.yaml` and `esp32/main/main.c`.

---

## 1. Bill of Materials v4.0 (₹5,770)

| # | Component | Model | ₹ | Interface | Role |
|---|---|---|---|---|---|
| 1 | Raspberry Pi 4B | 4GB RAM | 0 (owned) | — | Main compute |
| 2 | ESP32-C3 DevKit | DevKitM-1 | 400 | GPIO ↔ Pi | Always-on sentinel |
| 3 | OBD-II Adapter | ELM327 USB | 500 | /dev/ttyUSB0 | Vehicle CAN data |
| 4 | IMU Sensor | MPU6050 GY-521 | 150 | I2C bus 1, 0x68 | Crash + motion |
| 5 | Pi Camera | Camera v3 IMX708 | 1,800 | CSI-2 ribbon | Scene capture |
| 6 | USB Microphone | Mini condenser 16-bit | 200 | USB-A | YAMNet audio |
| 7 | PIR Sensor | HC-SR501 | 80 | ESP32 GPIO0 | Parked intrusion |
| 8 | Active Buzzer | 5V piezo | 40 | Pi GPIO17 | Local alarm |
| 9 | DC-DC Converter | LM2596 / Mini560 | 300 | 12V→5V/3A | Power regulation |
| 10 | P-MOSFET Switch | AO3401 SOT-23 | 50 | ESP32 GPIO7→gate | Pi power control |
| 11 | NPN Transistor | 2N2222 | 10 | Level shift 3.3→5V | MOSFET gate drive |
| 12 | **Fuel Pump Relay** | **5V relay module** | **60** | **Pi GPIO** | **Ghost Key immobilizer** |
| 13 | **USB SSD** | **Kingston A400 120GB** | **900** | **USB-A** | **Event DB + images** |
| 14 | MicroSD Card | 32GB High-Endurance | 400 | Pi microSD | OS only |
| 15 | Voltage Divider | 100kΩ + 33kΩ (1%) | 5 | ESP32 ADC GPIO3 | Battery monitoring |
| 16 | Pull-down resistors | 10kΩ × 4 | 10 | GPIO pull-downs | Signal integrity |
| 17 | Jumper wires | M-M, M-F, F-F | 150 | — | Connections |
| 18 | Breadboard | 400-point | 50 | — | Prototyping |
| 19 | 12V Cig adapter | Cig lighter → barrel jack | 100 | — | Car 12V input |
| 20 | Heat sink + fan | Aluminium for Pi 4 | 200 | — | Thermal management |
| 21 | ABS Enclosure | 3D printed (NOT PLA) | 400 | — | Housing |
| | **TOTAL** | | **₹5,770** | | |

> **V4 vs V3 BOM changes:** Added fuel pump relay (₹60) for Ghost Key TSA physical immobilization. USB SSD already in V3 but now mandatory (not optional) — InfluxDB + SQLite kill SD cards in weeks.

---

## 2. Power Architecture

```
CAR BATTERY (12–14.6V)
       │
       ├─── Cigarette lighter adapter → 5.5mm barrel jack
       │
       ▼
┌──────────────────┐
│  DC-DC LM2596    │  12–14.6V → 5.1V / 3A
│  (set to 5.1V)   │  0.1V headroom for cable drop
└────────┬─────────┘
         │ 5V Rail
         │
         ├─────────────────────────────────┐
         ▼                                 ▼
┌─────────────────┐             ┌──────────────────────┐
│  ESP32-C3 5V    │             │  P-MOSFET AO3401     │
│  (ALWAYS ON)    │             │  Source ◄── 5V Rail  │
│  Deep sleep=5μA │             │  Gate ◄── NPN 2N2222 │
└────────┬────────┘             │  Drain ──► Pi 5V Pin │
         │ GPIO7 (3.3V)         └──────────┬───────────┘
         ▼                                 │
┌─────────────────┐                        ▼
│  NPN 2N2222     │             ┌──────────────────────┐
│  Base ◄── GPIO7 │             │  Raspberry Pi 4B     │
│  Collector ─────┼─── MOSFET  │  Powered only when   │
│  Emitter ── GND │       Gate  │  ESP32 drives GPIO7  │
└─────────────────┘             │  LOW (P-chan logic)  │
                                └──────────────────────┘

Battery Monitoring:
CAR 12V ──► 100kΩ ──┬──► ESP32 ADC GPIO3
                    └──► 33kΩ ──► GND
Divider: 33/(100+33) = 0.248 → at 12V: ADC sees 2.98V (within 3.3V range)
Low battery threshold: 11.8V (config: power.low_battery_voltage)
```

---

## 3. GPIO Wiring Tables

### 3.1 Raspberry Pi 4B GPIO

| Pi Pin | GPIO | Signal | Connects To | Direction |
|---|---|---|---|---|
| 3 | GPIO2 / SDA1 | I2C Data | MPU6050 SDA | Bidirectional |
| 5 | GPIO3 / SCL1 | I2C Clock | MPU6050 SCL | Output |
| 11 | GPIO17 | Buzzer | Buzzer (+) | Output, Active HIGH |
| 31 | GPIO6 | Heartbeat | ESP32 GPIO6 | Output, 1Hz toggle |
| 2 | 5V | Power in | MOSFET Drain | Power |
| 6 | GND | Common GND | All devices | Ground |

### 3.2 ESP32-C3 GPIO

| GPIO | Signal | Connects To | Config Reference |
|---|---|---|---|
| GPIO0 | PIR Input | HC-SR501 OUT | 10kΩ pull-down to GND |
| GPIO3 | Battery ADC | Voltage divider | `power.low_battery_voltage: 11.8` |
| GPIO4 | Pi Wake Pulse | Via MOSFET gate | 500ms HIGH → Pi boots |
| GPIO5 | Pi Status | Pi GPIO5 | Pi holds HIGH 3s on shutdown |
| GPIO6 | Pi Heartbeat | Pi GPIO31 | No toggle for 30s → Pi dead |
| GPIO7 | MOSFET Gate | NPN 2N2222 base | `power.mosfet_gpio: 7` |

### 3.3 MPU6050 I2C Connection

```
MPU6050 GY-521     Raspberry Pi 4B
─────────────────────────────────
VCC (3.3V)    →    Pin 17 (3.3V)
GND           →    Pin 6  (GND)
SCL           →    Pin 5  (GPIO3/SCL1)
SDA           →    Pin 3  (GPIO2/SDA1)
AD0           →    GND    (address = 0x68)
INT           →    Not connected (polling, not interrupt)

Verify: sudo i2cdetect -y 1
Expected: 0x68 appears in grid

Config (config.yaml):
  bus: 1
  address: 0x68
  accel_range: 16   ← MAXIMUM (crashes produce 20-70g)
  gyro_range: 500
  saturation_threshold: 15.5
```

---

## 4. Fuel Pump Relay — Ghost Key Immobilizer

```
Why a relay, not a CAN signal?
  A CAN-bus injection attack operates at the software/bus layer.
  A physical relay on the fuel pump power wire is hardware-layer.
  It CANNOT be defeated by any software attack.

Circuit:
  Relay VCC  → Pi 5V (Pin 2)
  Relay GND  → Pi GND (Pin 6)
  Relay IN   → Pi GPIO (via GPIOManager)
  Relay COM  → Fuel pump (+) wire (inline splice at pump harness)
  Relay NC   → Fuel pump motor terminal (normally closed = runs)

Normal state:   NC closed → fuel pump runs → engine starts
Theft detected: Relay switches NC→NO → fuel pump open circuit
                Engine dies within 3–10 seconds (fuel in line depletes)

IMPORTANT: Use relay's NC (Normally Closed) terminal.
  This means a power failure to the Pi does NOT cut the fuel pump.
  The relay only cuts when actively commanded — fail-safe design.
```

---

## 5. USB Peripheral Allocation

| USB Port | Device | Dev Node | Baud/Rate | Purpose |
|---|---|---|---|---|
| USB-A 1 | ELM327 OBD-II | /dev/ttyUSB0 | 38400 | Vehicle CAN data (2Hz) |
| USB-A 2 | USB Microphone | hw:1,0 | 16kHz mono | YAMNet audio inference |
| USB-A 3 | Kingston SSD | /dev/sda | — | events.db, images, logs |
| USB-A 4 | Reserved | — | — | USB hub if needed |
| CSI-2 | Pi Camera v3 | libcamera | 3MP JPEG | On-demand crash capture |

> **SSD is mandatory, not optional.** SQLite in WAL mode + InfluxDB time-series writes will destroy an SD card's flash cells within weeks. The SSD handles write-heavy workloads by design.

---

## 6. Component Verification Checklist

```
Before powering the complete assembly:

□  DC-DC output: 5.1V ± 0.1V (measure with multimeter)
□  All grounds common (continuity test across GND points)
□  MPU6050:  sudo i2cdetect -y 1  →  shows 0x68
□  ELM327:   ls /dev/ttyUSB*      →  shows /dev/ttyUSB0
□  USB mic:  arecord -l            →  lists capture device
□  USB SSD:  df -h                 →  shows /mnt/vista-data
□  ESP32:    nRF Connect app       →  sees VISTA-0001 BLE
□  Heartbeat: ESP32 GPIO6 toggles 1Hz when Pi alive
□  MOSFET:   Pi powers off when ESP32 GPIO7 = HIGH
□  Relay:    Fuel pump circuit opens when GPIO triggered
□  PIR:      Delay pot set to minimum (0.5s)
□  Voltage:  ADC reading matches actual battery voltage
□  Thermal:  ABS enclosure has ventilation slots (Pi = 5W heat)
□  Demo off: DEMO_MODE=false in .env before vehicle install
```

---

**Version:** 4.0 | **Date:** May 16, 2026
