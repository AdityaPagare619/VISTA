# VISTA Design Documents — Complete Index

## 📚 Domain Design Documents

| # | Document | Purpose | Read When |
|---|----------|---------|-----------|
| **01** | [SYSTEM_DESIGN.md](01_SYSTEM_DESIGN.md) | Overall system design, states, data flow, failure modes, team ownership | Understanding the entire system |
| **02** | [HARDWARE_DESIGN.md](02_HARDWARE_DESIGN.md) | Component BOM, wiring pinouts, power architecture, enclosure, sourcing | Buying components & wiring |
| **03** | [SOFTWARE_ARCHITECTURE.md](03_SOFTWARE_ARCHITECTURE.md) | Module specs, class APIs, EKF code, CNN code, cloud integration, config | Writing code |
| **04** | [OPERATIONAL_FLOWS.md](04_OPERATIONAL_FLOWS.md) | Mode transitions, crash/theft sequences, communication protocols, error handling | Understanding behavior |
| **05** | [TECHNOLOGY_STACK.md](05_TECHNOLOGY_STACK.md) | All libraries, versions, install commands, directory structure, decisions | Setting up environment |
| **06** | [DEMO_EVALUATION_METHODOLOGY.md](06_DEMO_EVALUATION_METHODOLOGY.md) | How to demo without a real car: scenarios, scripts, simulators, backup plans | Preparing for viva |

## 📄 Master Documents

| Document | Location | Purpose |
|----------|----------|---------|
| **PR Report** | [../VISTA_PR_REPORT.md](../VISTA_PR_REPORT.md) | Complete project proposal: problem, solution, architecture, innovation, roadmap, viva defense |
| **Research Synthesis** | [../../RESEARCH/VISO_DEEP_RESEARCH_SYNTHESIS.md](../../RESEARCH/VISO_DEEP_RESEARCH_SYNTHESIS.md) | Background research: what was fantasy, what's real, domain analysis |

## 🚀 Quick Start Order

1. Read `VISTA_PR_REPORT.md` — understand the vision
2. Read `01_SYSTEM_DESIGN.md` — understand the system
3. Read `02_HARDWARE_DESIGN.md` — order components
4. Read `05_TECHNOLOGY_STACK.md` — set up Pi environment
5. Read `03_SOFTWARE_ARCHITECTURE.md` — start coding
6. Read `04_OPERATIONAL_FLOWS.md` — understand behavior
7. Read `06_DEMO_EVALUATION_METHODOLOGY.md` — prepare for viva demo

## 🛠️ For Specific Team Members

| Member | Primary Docs | Secondary Docs |
|--------|-------------|----------------|
| **Hardware Specialist** | 02, 05 | 01, 04 |
| **AI/ML Specialist** | 03 (audio_classifier, cloud_vision), 05 | 01, 04 |
| **Data Analytics** | 03 (fusion_engine, decision_engine, data layer, dashboard), 05 | 01 |
| **Integration/All** | 01, 04 | All |

---

**Version:** 2.1 | **Date:** May 8, 2026
