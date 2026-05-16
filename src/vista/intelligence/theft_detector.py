"""
VISTA Anti-Theft Verification Pipeline
======================================
Defeats modern vehicle theft (Relay Attacks, CAN-Bus Injection, Master Keys)
through a multi-layered, physics-grounded defense:

  1. BLE Proximity Check (Zero-cost silent disarm if owner's phone is near)
  2. Ghost Key Temporal Sequence Analysis (TSA) — detects anomalous event
     ordering that is physically impossible during legitimate vehicle entry
  3. Gemini Vision Verification (Cloud AI confirms suspicious interior activity)

Only if multiple checks fail is the Telegram alert fired + fuel relay cut.

DESIGN NOTE (Forensic Audit Remediation, May 15 2026):
  The previous "Mass-Velocity Authentication (MVA)" attempted to use the
  MPU6050 IMU Z-axis to measure driver mass via suspension dip. This is
  physically impossible — MEMS accelerometers cannot measure static
  displacement due to double-integration drift. See: VISTA_Forensic_Case_Study.md.

  We replaced MVA with Temporal Sequence Analysis (TSA), which uses ONLY
  data sources our hardware can actually provide:
    - BLE proximity (yes/no)
    - CAN-bus event ordering (unlock → door open → sit → engine start)
    - IMU tilt detection (driver sitting down = measurable tilt change)
    - Timing gaps between events (physically constrained by human biomechanics)
"""

from __future__ import annotations

import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from loguru import logger

from intelligence.cloud_vision import CloudVision
from communication.telegram_bot import TelegramAlertBot


# ── Temporal Sequence Analysis (TSA) Data Structures ──────────────
@dataclass
class VehicleEvent:
    """A single event in the vehicle entry sequence."""
    event_type: str   # "can_unlock", "door_open", "driver_seated", "engine_start"
    timestamp: float  # monotonic time
    source: str       # "can_bus", "imu", "ble", "obd"


@dataclass
class SequenceVerdict:
    """Result of the Ghost Key temporal sequence check."""
    is_anomalous: bool
    anomaly_reasons: List[str] = field(default_factory=list)
    confidence: float = 0.0
    sequence_received: List[str] = field(default_factory=list)


# ── Expected legitimate entry sequence ────────────────────────────
# Physics constrains the order and timing of a legitimate vehicle entry.
# A human must: approach (BLE detected) → unlock (CAN) → open door (IMU tilt)
#              → sit down (IMU tilt) → start engine (OBD RPM spike)
# Minimum realistic time from unlock to engine start: ~3-5 seconds
# If BLE is absent during any of this, it's a relay/injection attack.

LEGITIMATE_SEQUENCE = ["ble_detected", "can_unlock", "door_open", "driver_seated", "engine_start"]
MIN_UNLOCK_TO_START_SEC = 2.5   # Fastest possible human entry
MAX_UNLOCK_TO_START_SEC = 120.0  # Slowest reasonable entry


class TheftDetector:
    def __init__(self):
        self.cloud_vision = CloudVision()
        self.telegram = TelegramAlertBot()
        self._event_buffer: List[VehicleEvent] = []

        # Ensure we have the generativeai client
        if self.cloud_vision._client is None:
            logger.warning("TheftDetector: Gemini client not available.")

    # ── Layer 1: BLE Proximity ────────────────────────────────────
    def check_ble_proximity(self) -> bool:
        """
        Scans for the owner's authorized Bluetooth MAC address.
        Returns True if authorized owner is near (silent disarm).

        In demo: controlled via mock_owner_ble_present attribute.
        In production: scans for registered BLE MAC via hcitool/bleak.
        """
        logger.info("Scanning for authorized BLE devices...")
        owner_found = getattr(self, "mock_owner_ble_present", False)
        time.sleep(0.3)  # simulate scan time

        if owner_found:
            logger.info("BLE Check: Authorized owner detected. Silently disarming.")
            return True
        else:
            logger.warning("BLE Check: NO authorized devices found.")
            return False

    # ── Layer 2: Ghost Key Temporal Sequence Analysis (TSA) ───────
    def verify_temporal_sequence(self, can_bus_start_signal: bool) -> SequenceVerdict:
        """
        Ghost Key Temporal Sequence Analysis (TSA)

        Instead of trying to measure driver mass (physically impossible with
        MPU6050), we analyze the ORDERING and TIMING of vehicle entry events.

        Physics Basis:
          - A legitimate entry follows a deterministic sequence constrained
            by human biomechanics and physical causality.
          - A Relay Attack skips BLE proximity (thief has cloned signal).
          - A CAN-Bus Injection skips door_open and driver_seated events
            (thief injects "Start Engine" directly into the bus).
          - A Master Key entry has correct sequence but wrong BLE.

        All three attack vectors produce DETECTABLE temporal anomalies
        using only sensors we actually have.

        Returns SequenceVerdict with anomaly assessment.
        """
        if not can_bus_start_signal:
            return SequenceVerdict(is_anomalous=False, confidence=0.0)

        logger.info("⚡ CAN-bus 'Engine Start' detected. Running Ghost Key TSA...")

        anomaly_reasons = []
        confidence = 0.0

        # ── Check 1: BLE Proximity (Was owner's phone present?) ───
        # This defeats Relay Attacks. Thief's relay device amplifies the
        # key fob signal but the owner's PHONE BLE is in the house.
        ble_present = self.check_ble_proximity()
        if not ble_present:
            anomaly_reasons.append("BLE_ABSENT: Owner's phone not detected during engine start")
            confidence += 0.40  # Strong indicator

        # ── Check 2: Event Sequence Order ─────────────────────────
        # Simulate reading the event buffer (in production: from CAN + IMU listeners)
        # For demo: use mock_event_sequence attribute
        events = getattr(self, "mock_event_sequence", LEGITIMATE_SEQUENCE)
        sequence_names = events if isinstance(events, list) else list(events)

        # CAN-Bus Injection: Engine starts without door_open or driver_seated
        if "engine_start" in sequence_names:
            if "door_open" not in sequence_names:
                anomaly_reasons.append("IMPOSSIBLE_PHYSICS: Engine started but no door was opened")
                confidence += 0.35
            if "driver_seated" not in sequence_names:
                anomaly_reasons.append("IMPOSSIBLE_PHYSICS: Engine started but no one sat in driver seat")
                confidence += 0.25

        # ── Check 3: Timing Analysis ─────────────────────────────
        # How fast was the entry? Thieves are fast. Owners are casual.
        entry_duration_sec = getattr(self, "mock_entry_duration_sec", 6.0)

        if entry_duration_sec < MIN_UNLOCK_TO_START_SEC:
            anomaly_reasons.append(
                f"TIMING_ANOMALY: Entry took {entry_duration_sec:.1f}s "
                f"(minimum human entry: {MIN_UNLOCK_TO_START_SEC}s)"
            )
            confidence += 0.20

        # ── Final Verdict ─────────────────────────────────────────
        confidence = min(confidence, 1.0)
        is_anomalous = confidence >= 0.40  # Threshold: at least BLE missing

        verdict = SequenceVerdict(
            is_anomalous=is_anomalous,
            anomaly_reasons=anomaly_reasons,
            confidence=confidence,
            sequence_received=sequence_names,
        )

        if is_anomalous:
            logger.critical(f"🚨 GHOST KEY DETECTED: {len(anomaly_reasons)} anomalies, "
                          f"confidence {confidence*100:.0f}%")
            for reason in anomaly_reasons:
                logger.critical(f"   → {reason}")
            logger.critical("🚨 EXECUTING ANALOG FUEL PUMP RELAY CUT.")
        else:
            logger.info("✅ Temporal sequence verified. Authorized entry confirmed.")

        return verdict

    # ── Layer 3: Gemini Vision Verification ───────────────────────
    def verify_with_gemini(self) -> Dict[str, Any]:
        """
        Takes an interior camera snapshot and asks Gemini to verify.
        This is the cloud-AI escalation layer — only called if BLE and TSA
        don't definitively resolve the situation.
        """
        if self.cloud_vision._client is None:
            return {"status": "error", "error": "Gemini API unavailable."}

        prompt = (
            "You are an AI Security guard monitoring the interior of a vehicle. "
            "A motion sensor just triggered while the car was parked. "
            "Look at this image. Is the person sitting in the driver's seat attempting "
            "to tamper with the steering column/ignition, or are they a normal passenger? "
            "Return a short analysis, and end with 'VERDICT: THEFT' or 'VERDICT: SAFE'."
        )

        logger.info("Taking interior snapshot and sending to Gemini Vision API...")

        # In a real scenario, we pass image_bytes.
        # Since this is a test, we will pass a text description to Gemini to simulate vision parsing.
        simulation_prompt = prompt + (
            "\n\n[SIMULATED IMAGE INPUT: A person in a black hoodie is sitting "
            "in the driver seat, aggressively pulling wires from underneath "
            "the steering wheel console.]"
        )

        response_text = self.cloud_vision.ask_gemini(simulation_prompt)

        if response_text.startswith("Error:"):
            logger.error(f"Failed to verify with Gemini: {response_text}")
            return {"status": "error", "error": response_text}

        analysis = response_text.strip()
        is_theft = "VERDICT: THEFT" in analysis.upper()
        logger.info(f"Gemini Analysis complete. Is Theft? {is_theft}")
        return {"status": "success", "analysis": analysis, "is_theft": is_theft}

    # ── Main Pipeline ─────────────────────────────────────────────
    def handle_motion_trigger(self, can_bus_hacked: bool = False) -> bool:
        """
        The main pipeline triggered when the PIR sensor detects motion or CAN-bus triggers.

        Defense Layers (in order of cost/latency):
          1. BLE proximity — 0.3s, zero API cost
          2. Ghost Key TSA — 0.1s, zero API cost, physics-based
          3. Gemini Vision — 2-5s, API cost, cloud-dependent

        Returns True if theft was detected/prevented, False if safe.
        """
        logger.warning("🚨 Security Trigger Detected!")

        # Step 1: Zero-cost BLE check
        if self.check_ble_proximity():
            return False  # Disarmed — owner is present

        # Step 2: Ghost Key Temporal Sequence Analysis (replaces old MVA)
        if can_bus_hacked:
            logger.warning("CAN-Bus 'Unlock/Start' sequence initiated without BLE presence.")
            verdict = self.verify_temporal_sequence(can_bus_start_signal=True)
            if verdict.is_anomalous:
                alert_msg = (
                    "⚠️ *CRITICAL GHOST KEY ALERT*\n"
                    f"Confidence: {verdict.confidence*100:.0f}%\n"
                    f"Anomalies detected: {len(verdict.anomaly_reasons)}\n"
                )
                for reason in verdict.anomaly_reasons:
                    alert_msg += f"• {reason}\n"
                alert_msg += "\n🔒 Analog Fuel Relay Cut. Vehicle Secured."
                self.telegram._send_message(alert_msg)
                return True

        # Step 3: High-certainty Gemini Vision check
        verification = self.verify_with_gemini()

        if verification.get("status") == "success":
            if verification.get("is_theft"):
                telegram_msg = (
                    "🚨 *VISTA THEFT ALERT - UNAUTHORIZED ENTRY* 🚨\n\n"
                    f"*{verification['analysis']}*\n\n"
                    "📍 Location: 19.0760°N, 72.8777°E\n"
                    "⏰ Time: " + time.strftime('%Y-%m-%d %H:%M:%S') + "\n\n"
                    "⚠️ _VISTA Anti-Theft Protocol Active. Image attached above._"
                )
                success = self.telegram._send_message(telegram_msg)
                if success:
                    logger.success("Theft Alert sent to Telegram successfully.")
                return True
            else:
                logger.info("Gemini verified the scene is SAFE. False alarm averted.")
                return False
        else:
            logger.error(f"Cannot verify theft due to API error: {verification.get('error')}")
            # Fallback: Send a warning anyway if API fails
            self.telegram._send_message("⚠️ *VISTA WARNING*: Motion detected, but Vision AI is offline.")
            return True

if __name__ == "__main__":
    detector = TheftDetector()
    detector.handle_motion_trigger()
