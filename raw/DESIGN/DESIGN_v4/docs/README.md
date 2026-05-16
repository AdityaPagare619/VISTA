# VISTA Design Documents v4.0 — Complete Index

> **What changed from v3.0:** v4.0 reflects the **fully built, tested, and verified system** as of May 2026. Every claim in these documents is backed by running code, verified test outputs, and SITL demonstrations. This is not a design specification — it is a faithful record of what was built.

---

## 📋 V3.0 → V4.0 Key Changes

| What Changed | V3.0 Said | V4.0 Reality | Why It Matters |
|---|---|---|---|
| **Theft Detection** | PIR + camera (reactive) | Ghost Key TSA: 4-layer temporal analysis | Defeats relay attack, CAN injection, timing attack — all modern vectors |
| **V4 Intelligence Modules** | Not present | TheftDetector + PredictiveAnalyticsEngine + SystemHealthMonitor | Now wired into production main loop |
| **Data Persistence** | SQLite/InfluxDB existed | Now actively called — crash events persist before Telegram | Events survive network outages |
| **InfluxDB Client** | Re-created every 500ms | Module-level singleton — one TCP connection reused | Eliminates socket exhaustion |
| **Health Monitor** | File existed, never called | Pings sensors every tick, 30s periodic report | OPS team gets real-time sensor liveness |
| **Dashboard** | 4 cards, basic chart | 6-metric strip, sensor health rings, architecture flow animation | Demo-room ready |
| **BOM** | ₹4,700 | ₹5,770 (added USB SSD + fuel pump relay) | Honest accounting |
| **NVH Analytics** | Not present | Simulated pipeline with correct API shape | B2B insurance API demonstrated |
| **CI/CD** | None | GitHub Actions: 4 jobs (import, tests, SITL, lint) | Regression protection |
| **Deploy Script** | `install.sh` existed | `scripts/deploy.sh` — 6-phase automated Pi setup | One command from bare Pi to running system |
| **Gemini API** | Described | Active — gemini-1.5-flash, 3 retries, 10s timeout, verified live | Reports sent to Telegram from real API |

---

## 📄 Document Index

| # | Document | Read For | Hardware/Software Teams |
|---|---|---|---|
| — | [README.md](README.md) | This index — start here | Both |
| 01 | [01_SYSTEM_DESIGN.md](01_SYSTEM_DESIGN.md) | State machine, data flow, boot sequence, V4 architecture | Both |
| 02 | [02_HARDWARE_DESIGN.md](02_HARDWARE_DESIGN.md) | **BOM, wiring diagrams, pin tables, power circuit, relay cut** | Hardware |
| 03 | [03_SOFTWARE_ARCHITECTURE.md](03_SOFTWARE_ARCHITECTURE.md) | Package structure, module APIs, data contracts, config hierarchy | Software |
| 04 | [04_OPERATIONAL_FLOWS.md](04_OPERATIONAL_FLOWS.md) | Crash detection timeline, Ghost Key TSA sequence, NVH flow | Both |
| 05 | [05_TECHNOLOGY_STACK.md](05_TECHNOLOGY_STACK.md) | Libraries, versions, cloud services, deployment environment | Software |
| 06 | [06_DEMO_METHODOLOGY.md](06_DEMO_METHODOLOGY.md) | SITL demo script, dashboard walkthrough, expected outputs | Both |

---

## 🚀 Reading Order by Team

### Hardware Team (Will wire and build the physical unit)
1. **02_HARDWARE_DESIGN.md** → BOM, exact wiring, pin numbers, power circuit
2. **01_SYSTEM_DESIGN.md** → Understand what the system does to know what you're building
3. **04_OPERATIONAL_FLOWS.md** → Understand timing constraints (35s boot, 300ms relay cut)
4. **06_DEMO_METHODOLOGY.md** → Know what needs to work for demo day

### Software / Integration Team
1. **01_SYSTEM_DESIGN.md** → System states and data flows
2. **03_SOFTWARE_ARCHITECTURE.md** → Package structure, how to add modules
3. **05_TECHNOLOGY_STACK.md** → Environment setup, dependencies
4. **04_OPERATIONAL_FLOWS.md** → Event sequences and expected behavior

### Research / IEEE Paper Team
1. **01_SYSTEM_DESIGN.md** → Innovation claims, architecture novelty
2. **04_OPERATIONAL_FLOWS.md** → Algorithm descriptions for methods section
3. **02_HARDWARE_DESIGN.md** → Hardware methodology, cost analysis
4. **03_SOFTWARE_ARCHITECTURE.md** → Implementation details for paper

---

## 📊 System At-a-Glance (Verified May 16, 2026)

```
Modules:    19/19 importable (100%)
Tests:      20/20 passing    (100%)
SITL Demo:   3/3 scenarios   EXIT 0
Codebase:   45 source files  ~15,741 LOC
ML Model:   4.1MB YAMNet TFLite (real, shipped)
BOM:        ₹5,770           (~$69 USD)
Cloud cost: ₹0/month         (Gemini free tier + Telegram free)
```

---

**Version:** 4.0 | **Date:** May 16, 2026
**Previous:** v3.0 in `DESIGN_v3/` (preserved, not modified)
