# VISTA v4.0 Architecture Supplement
### *Documenting V4 additions without modifying V3 design docs*

**Date:** May 16, 2026  
**Scope:** New modules, APIs, and data flows added in V4  
**Reference:** V3 docs (01-06) remain the definitive source for crash detection, hardware, power, and operational flows.

---

## Purpose

The V3 design docs (`DESIGN_v3/docs/01-06`) describe the system architecture as of V3 code-freeze. V4 development added several new modules and modified existing files. Rather than editing the immutable V3 documents, this supplement documents what was added and how it integrates.

---

## New Modules Added in V4

### 1. `intelligence/theft_detector.py` — Ghost Key TSA

**Replaces:** Basic PIR + Gemini vision from V3 concept  
**Architecture Tier:** Security (runs on CAN-bus trigger, not on the crash detection loop)

```
Integration Point (in app.py):
  CAN-bus trigger → TheftDetector.handle_motion_trigger(can_bus_hacked=True)
    ├── Layer 1: BLE proximity scan (0.3s, edge-only)
    ├── Layer 2: Ghost Key TSA temporal sequence check (0.1s, edge-only)  
    └── Layer 3: Gemini Vision escalation (2-5s, cloud)
```

**Dependencies:** `cloud_vision.py`, `telegram_bot.py`  
**Demo Room Usage:** Triggered via dashboard UI button "CAN-Bus Injection" → visible in Event Intelligence Log

---

### 2. `intelligence/predictive_analytics.py` — NVH Simulation

**Status:** SIMULATION MODE (no real autoencoder model)  
**Architecture Tier:** Enterprise Analytics (periodic, not real-time)

```
Integration Point (in app.py):
  /api/nvh/score (GET) → PredictiveAnalyticsEngine.calculate_nvh_reconstruction_error()
    └── Returns 2KB JSON with _simulation_mode: true flag
```

**Dependencies:** `cloud_vision.py` (for Gemini mechanic reports), `telegram_bot.py`  
**Demo Room Usage:** NVH panel in dashboard auto-refreshes every 3 seconds

---

### 3. `intelligence/cloud_vision.py` — Gemini REST API

**Replaces:** V3's planned `google-generativeai` SDK (unstable, abandoned)  
**Architecture:** Custom `requests`-based REST client with retry logic

```
API: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent
Auth: API key from .env (GEMINI_API_KEY)
Retry: 3 attempts with exponential backoff
```

**Demo Room Usage:** Called by TheftDetector (Layer 3) and PredictiveAnalyticsEngine (mechanic reports)

---

## Modified Files (V3 → V4 Delta)

### `dashboard/app.py`
- Added `TheftDetector` and `PredictiveAnalyticsEngine` imports
- Added `/api/nvh/score` endpoint (B2B)
- Added `/api/demo/scenario` handler for `can_bus_injection`
- Ghost Key TSA mock state setup for demo

### `dashboard/static/dashboard.js`
- Added `theft_attempt` and `theft_prevented` alert handlers
- Added NVH polling loop (3-second interval to `/api/nvh/score`)
- Alert label: "GHOST KEY TSA DEPLOYED"

### `dashboard/templates/index.html`
- Added "Enterprise Fleet Health (Predictive NVH)" panel
- Added "CAN-Bus Injection (Relay Attack)" scenario button
- NVH displays: health score, reconstruction error, anomaly band

### `communication/telegram_bot.py`
- Wired with `CHAT_ID` from `.env` (verified: `8407946567`)
- Supports text and photo uploads

---

## V4 Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                    VISTA V4 DATA FLOW                         │
│                                                                │
│  SENSORS (or demo_data.py)                                    │
│  ├── IMU (100Hz) ──────┐                                     │
│  ├── OBD (2-3Hz) ──────┤                                     │
│  └── Audio (16kHz) ────┤                                     │
│                         ▼                                     │
│  ┌─────────────────────────────────┐                         │
│  │  V3 CORE (untouched)            │                         │
│  │  ├── VelocityEKF                │                         │
│  │  ├── CrashDetector              │──── CRASH ──→ Telegram  │
│  │  └── AudioClassifier (YAMNet)   │              (B2C)      │
│  └─────────────────────────────────┘                         │
│                                                                │
│  CAN-BUS TRIGGER ──→ ┌─────────────────────────┐            │
│                       │  V4: TheftDetector       │            │
│                       │  ├── BLE Scan            │            │
│                       │  ├── Ghost Key TSA       │──→ Telegram│
│                       │  └── Gemini Vision       │   (B2C)    │
│                       └─────────────────────────┘            │
│                                                                │
│  PERIODIC (30s) ────→ ┌─────────────────────────┐            │
│                       │  V4: NVH Analytics       │            │
│                       │  └── Health Score JSON   │──→ Dashboard│
│                       └─────────────────────────┘   (B2B)    │
│                                                                │
│  ALL TELEMETRY ─────→ SocketIO WebSocket ──────→ Dashboard   │
│                                                    (B2B)      │
└──────────────────────────────────────────────────────────────┘
```

---

## What V3 Docs Still Govern (Do NOT Edit)

| V3 Doc | Governs | V4 Impact |
|--------|---------|-----------|
| `01_SYSTEM_DESIGN.md` | 4-tier detection, state machine | V4 adds TSA as a 5th tier (security). Core tiers unchanged. |
| `02_HARDWARE_DESIGN.md` | Wiring, BOM, MOSFET, power | Zero changes. V4 is pure software. |
| `03_SOFTWARE_ARCHITECTURE.md` | EKF, CrashDetector, AudioClassifier | V4 adds 3 new modules alongside. Core modules unchanged. |
| `04_OPERATIONAL_FLOWS.md` | Boot, shutdown, mode transitions | V4 adds CAN-bus injection flow (not in V3). |
| `05_TECHNOLOGY_STACK.md` | Libraries, storage, comms | V4 migrated Gemini SDK → REST. Telegram unchanged. |
| `06_DEMO_EVALUATION_METHODOLOGY.md` | Demo scripts, evaluation | V4 adds `demo_billion_dollar_architecture.py` as a new demo. |

---

*This document supplements but does not replace the V3 design docs. All V3 specifications remain authoritative for crash detection, hardware, and operational flows.*
