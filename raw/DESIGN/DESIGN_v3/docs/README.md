# VISTA Design Documents v3.0 — Complete Index

## 📚 What Changed from v2.1

| Change | Why | Impact |
|--------|-----|--------|
| Pi "sleep" → halt + MOSFET power-off | Pi 4 cannot suspend-to-RAM (hardware fact) | True 0W off; honest 35s boot time |
| OBD 10Hz → 2-3Hz (actual) | ELM327 real-world measurement | Tiered detection; OBD is async corroborator |
| EKF: 3-state broken → 2-state correct | Original had dimensional inconsistency | Velocity estimation only; crash detection separated |
| WhatsApp → Telegram | WhatsApp has no free tier for outbound | Zero cost; richer API; same functionality |
| SD card → USB SSD for databases | InfluxDB kills SD cards in months | Reliable storage; faster queries |
| 7 innovations → 3 primary + 4 supporting | Depth beats breadth | Stronger publication and viva story |
| Added safety disclaimer | Ethical engineering maturity | Proactive honesty strengthens defense |

## 📄 Document Index

| # | Document | Purpose | Key v3.0 Changes |
|---|----------|---------|--------------------|
| — | [VISTA_PR_REPORT.md](../VISTA_PR_REPORT.md) | Master report | Tiered detection, MOSFET, identity clarity |
| 01 | [SYSTEM_DESIGN.md](01_SYSTEM_DESIGN.md) | System states, data flow | Fixed state machine, corrected timing |
| 02 | [HARDWARE_DESIGN.md](02_HARDWARE_DESIGN.md) | BOM, wiring, power | MOSFET switch, USB SSD, direct ESP32 power |
| 03 | [SOFTWARE_ARCHITECTURE.md](03_SOFTWARE_ARCHITECTURE.md) | Module specs, code | Corrected EKF, separated crash detector |
| 04 | [OPERATIONAL_FLOWS.md](04_OPERATIONAL_FLOWS.md) | Event sequences | Honest 35s boot, 50s theft response |
| 05 | [TECHNOLOGY_STACK.md](05_TECHNOLOGY_STACK.md) | Libraries, setup | Telegram primary, SSD config |
| 06 | [DEMO_EVALUATION_METHODOLOGY.md](06_DEMO_EVALUATION_METHODOLOGY.md) | Demo scripts | MOSFET demo, safety disclaimer |

## 🚀 Quick Start (same as v2.1)

1. Read PR Report → understand vision
2. Read 01 → understand system
3. Read 02 → order components (**now includes MOSFET + SSD**)
4. Read 05 → set up environment
5. Read 03 → start coding
6. Read 04 → understand behavior
7. Read 06 → prepare for demo

---

**Version:** 3.0 | **Date:** May 10, 2026  
**Previous:** v2.1 in `../` (preserved, not overwritten)
