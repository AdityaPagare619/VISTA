"""
VISTA Crash Detector — Signature-Aware Event Detection (v3.0)
===============================================================
Separate from EKF because crashes are discontinuities that violate
Kalman filter smoothness assumptions.

FOUNDATIONAL DESIGN PRINCIPLE:
    Sensors just give numbers. The intelligence is asking the RIGHT
    question about those numbers. The wrong question: "is acceleration
    high?" The right question: "does this temporal PATTERN match the
    physics signature of a crash?"

    - Crash: asymmetric spike → sustained clip (100-300ms) → slow decay
    - Pothole: symmetric spike, brief (<30ms), no sustained phase
    - Speed bump: gradual rise, predictable, lower magnitude
    - Same peak g-force, completely different meaning.

Detection tiers (by latency):
    T1 (0ms):   IMU signature detection (primary — fastest)
    T2 (50ms):  Audio CNN corroboration
    T3 (500ms): OBD speed-rate corroboration (async)
    T4 (2-3s):  Cloud Vision enrichment (optional)

Key v3.0 design decisions:
    - IMU is primary detector (0.45 weight) — fastest at 100Hz
    - Audio is secondary (0.30 weight) — near real-time CNN
    - OBD is async corroborator (0.15 weight) — too slow to be primary
    - Vision is enrichment only (0.10 weight) — requires internet
    - MPU6050 saturates at ±16g. Saturation IS the signal.
    - Can produce a decision with IMU+Audio alone (0.75 max)

Usage::

    detector = CrashDetector()
    evidence = CrashEvidence(
        imu_jerk=7.2, imu_saturated=False,
        audio_class="crash", audio_confidence=0.91,
    )
    result = detector.assess(evidence)
    if result["is_crash"]:
        send_alert(result)
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from loguru import logger


@dataclass
class CrashEvidence:
    """Container for multi-modal crash evidence.

    Can be populated incrementally as sensors report in
    at different speeds (IMU first, OBD later, Vision last).
    """
    # Tier 1: IMU (arrives at ~10ms)
    imu_jerk: float = 0.0           # g/s — rate of acceleration change
    imu_saturated: bool = False     # True if any axis ≥ saturation threshold
    imu_accel_magnitude: float = 0.0  # g — total acceleration magnitude

    # Tier 2: Audio (arrives at ~50ms)
    audio_class: str = "normal"     # CNN classification label
    audio_confidence: float = 0.0   # CNN confidence [0, 1]

    # Tier 3: OBD (arrives at ~500ms — async)
    obd_speed_drop: float = 0.0     # km/h — how much speed dropped
    obd_throttle_drop: float = 0.0  # % — how much throttle dropped

    # Tier 4: Vision (arrives at ~2-3s — optional)
    vision_description: str = ""    # Cloud Vision scene description
    vision_confidence: float = 0.0  # Vision crash confidence [0, 1]

    # Metadata
    timestamp: float = 0.0


class CrashDetector:
    """Multi-tier crash detection with async corroboration.

    Thread-safe. Can be called with partial evidence (e.g., IMU+Audio
    first, then OBD later) and will update the decision accordingly.

    All thresholds and weights are loaded from config.yaml.
    """

    def __init__(self) -> None:
        cfg = self._load_config()
        crash_cfg = cfg.get("crash_detection", {})

        # Thresholds
        self._jerk_threshold: float = float(
            crash_cfg.get("jerk_threshold", 5.0)
        )
        self._confirm_threshold: float = float(
            crash_cfg.get("confirm_threshold", 0.65)
        )
        self._warning_threshold: float = float(
            crash_cfg.get("warning_threshold", 0.40)
        )

        # Sensor weights (v3.0 values)
        self._weights: Dict[str, float] = {
            k: float(v)
            for k, v in crash_cfg.get("sensor_weights", {
                "imu": 0.45,
                "audio": 0.30,
                "obd": 0.15,
                "vision": 0.10,
            }).items()
        }

        # IMU saturation threshold from sensor config
        imu_cfg = cfg.get("sensors", {}).get("imu", {})
        self._saturation_threshold: float = float(
            imu_cfg.get("saturation_threshold", 15.5)
        )

        # Timestamped acceleration history for PATTERN analysis
        # Each entry: (monotonic_time, accel_magnitude_g)
        self._accel_history: deque[Tuple[float, float]] = deque(maxlen=500)  # ~5s at 100Hz

        # Crash signature parameters (physics-derived)
        self._crash_sustain_min_ms: float = 50.0   # Crash sustains high-g for >50ms
        self._pothole_max_duration_ms: float = 30.0  # Pothole spike lasts <30ms
        self._crash_asymmetry_ratio: float = 2.0   # Rise is faster than decay in crash

        # State
        self._state: str = "monitoring"  # monitoring | potential | confirmed
        self._lock = threading.RLock()

        logger.info(
            f"CrashDetector initialized | jerk_threshold={self._jerk_threshold} g/s | "
            f"confirm={self._confirm_threshold} | "
            f"signature_aware=True | "
            f"weights={self._weights}"
        )

    # ── Config loader ────────────────────────────────────────────

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        package_root = Path(__file__).resolve().parent.parent
        config_path = package_root / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"config.yaml not found at {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # ── Tier 1: IMU Check (Signature-Aware) ───────────────────────

    def check_imu(self, accel_magnitude: float, dt: float) -> float:
        """Tier 1: Record IMU reading and compute jerk.

        Stores timestamped readings for temporal pattern analysis.
        The jerk alone does NOT determine crash — the pattern does.

        Args:
            accel_magnitude: Total acceleration magnitude in g.
            dt: Time since last IMU reading in seconds.

        Returns:
            Jerk value in g/s. If > jerk_threshold, further
            signature analysis is warranted.
        """
        now = time.monotonic()
        with self._lock:
            self._accel_history.append((now, accel_magnitude))

            if len(self._accel_history) < 2:
                return 0.0

            prev_mag = self._accel_history[-2][1]
            jerk = abs(accel_magnitude - prev_mag) / max(dt, 1e-6)
            return jerk

    def is_saturated(self, ax: float, ay: float, az: float) -> bool:
        """Check if any IMU axis is near saturation (clipping).

        MPU6050 at ±16g range clips at ~15.5g. If we see values
        this high, the real force exceeds sensor range — which is
        itself strong evidence of a severe event.
        """
        return any(abs(a) >= self._saturation_threshold for a in (ax, ay, az))

    def _validate_crash_signature(self) -> float:
        """Analyze the TEMPORAL SHAPE of recent IMU data.

        This is the core intelligence: instead of asking "is this number
        big?", we ask "does this pattern look like a crash?"

        Physics of a crash:
            1. Sharp onset: acceleration rises from normal (~1g) to
               extreme (5-16g+) in <20ms
            2. Sustained phase: high acceleration persists for 50-300ms
               as the vehicle deforms and decelerates
            3. Asymmetric decay: slower return to normal as energy
               dissipates (100-500ms)

        Physics of a pothole:
            1. Sharp spike: similar rise time to crash
            2. NO sustained phase: returns to normal in <30ms
            3. Symmetric: rise and fall times are nearly equal
            4. Often followed by a second symmetric spike (exit bump)

        Returns:
            Signature confidence [0.0, 1.0].
            1.0 = strong crash signature. 0.0 = noise/pothole.
        """
        with self._lock:
            if len(self._accel_history) < 10:
                return 0.0

            # Find the peak in recent history
            recent = list(self._accel_history)
            peak_idx = -1
            peak_val = 0.0
            for i, (t, mag) in enumerate(recent):
                if mag > peak_val:
                    peak_val = mag
                    peak_idx = i

            # No significant event
            if peak_val < 2.0:  # Below 2g is normal driving
                return 0.0

            peak_time = recent[peak_idx][0]

            # ── Analyze sustain duration ─────────────────────
            # How long does accel stay above 50% of peak?
            half_peak = peak_val * 0.5
            sustain_start = peak_time
            sustain_end = peak_time

            for i in range(peak_idx, len(recent)):
                if recent[i][1] >= half_peak:
                    sustain_end = recent[i][0]
                else:
                    break

            sustain_ms = (sustain_end - sustain_start) * 1000.0

            # ── Analyze asymmetry (rise time vs decay time) ──
            # Rise: time from 25% of peak to peak
            quarter_peak = peak_val * 0.25
            rise_start = peak_time
            for i in range(peak_idx, -1, -1):
                if recent[i][1] < quarter_peak:
                    rise_start = recent[i][0]
                    break
            rise_ms = (peak_time - rise_start) * 1000.0

            # Decay: time from peak to 25% of peak
            decay_end = peak_time
            for i in range(peak_idx, len(recent)):
                if recent[i][1] < quarter_peak:
                    decay_end = recent[i][0]
                    break
            decay_ms = (decay_end - peak_time) * 1000.0

            # ── Score the signature ──────────────────────────
            signature_score = 0.0

            # Sustain check: crash sustains >50ms, pothole <30ms
            if sustain_ms >= self._crash_sustain_min_ms:
                signature_score += 0.5  # Strong crash indicator
            elif sustain_ms >= 30:
                signature_score += 0.25  # Possible crash
            else:
                # Very brief spike — likely pothole or bump
                signature_score -= 0.3

            # Asymmetry check: crash has fast rise, slow decay
            if rise_ms > 0 and decay_ms > 0:
                asymmetry = decay_ms / max(rise_ms, 1.0)
                if asymmetry >= self._crash_asymmetry_ratio:
                    signature_score += 0.3  # Asymmetric = crash-like
                elif asymmetry >= 1.3:
                    signature_score += 0.1
                else:
                    # Symmetric spike = pothole
                    signature_score -= 0.2

            # Peak magnitude bonus
            if peak_val >= self._saturation_threshold:
                signature_score += 0.2  # Sensor saturated
            elif peak_val >= 8.0:
                signature_score += 0.1

            return max(0.0, min(1.0, signature_score))

    # ── Assessment ───────────────────────────────────────────────

    def assess(self, evidence: CrashEvidence) -> Dict[str, Any]:
        """Compute crash confidence from available evidence.

        Can be called with partial evidence (async OBD arrives later).
        Each call produces a complete decision with whatever data
        is available at that moment.

        Args:
            evidence: CrashEvidence with whatever fields are populated.

        Returns:
            Dict with keys: is_crash, confidence, severity, evidence, explanation
        """
        with self._lock:
            # Get effective weights (may redistribute if sensors offline)
            active_weights = self._get_active_weights(evidence)

            # ── IMU confidence (signature-aware) ────────────
            # v3.0: Don't just check "is jerk big?" — check if the
            # temporal PATTERN matches crash physics.
            raw_jerk_score = min(evidence.imu_jerk / self._jerk_threshold, 1.0)
            signature_score = self._validate_crash_signature()

            # Combine: raw jerk gives the trigger, signature confirms it.
            # Without a crash signature, even high jerk is penalized
            # (likely pothole/bump on Indian roads).
            if signature_score >= 0.5:
                imu_conf = raw_jerk_score  # Signature confirmed → trust the jerk
            elif signature_score >= 0.2:
                imu_conf = raw_jerk_score * 0.7  # Weak signature → discount
            else:
                imu_conf = raw_jerk_score * 0.3  # No signature → likely false positive

            if evidence.imu_saturated:
                imu_conf = max(imu_conf, 0.95)  # Saturation overrides — real event

            # ── Audio confidence ─────────────────────────────
            audio_conf = 0.0
            if evidence.audio_class in ("crash", "crash_impact", "collision"):
                audio_conf = evidence.audio_confidence
            elif evidence.audio_class in ("tire_skid", "harsh_braking"):
                audio_conf = evidence.audio_confidence * 0.5  # Partial signal

            # ── OBD confidence (may be 0 if not yet received) ─
            obd_conf = 0.0
            if evidence.obd_throttle_drop > 0:
                obd_conf = min(evidence.obd_throttle_drop / 50.0, 1.0)
            if evidence.obd_speed_drop > 20:
                obd_conf = max(obd_conf, min(evidence.obd_speed_drop / 40.0, 1.0))

            # ── Vision confidence (may be 0 if not yet received)
            vision_conf = evidence.vision_confidence

            # ── Weighted fusion ──────────────────────────────
            confidence = 0.0
            if "imu" in active_weights:
                confidence += active_weights["imu"] * imu_conf
            if "audio" in active_weights:
                confidence += active_weights["audio"] * audio_conf
            if "obd" in active_weights:
                confidence += active_weights["obd"] * obd_conf
            if "vision" in active_weights:
                confidence += active_weights["vision"] * vision_conf

            confidence = min(1.0, max(0.0, confidence))

            # ── Severity classification ──────────────────────
            if confidence >= self._confirm_threshold:
                severity = "critical"
                is_crash = True
                self._state = "confirmed"
            elif confidence >= self._warning_threshold:
                severity = "warning"
                is_crash = False
                self._state = "potential"
            else:
                severity = "info"
                is_crash = False
                self._state = "monitoring"

            # ── Build result ─────────────────────────────────
            result = {
                "is_crash": is_crash,
                "confidence": round(confidence, 3),
                "severity": severity,
                "state": self._state,
                "evidence": {
                    "imu": {
                        "jerk": round(evidence.imu_jerk, 2),
                        "saturated": evidence.imu_saturated,
                        "weight": active_weights.get("imu", 0),
                        "contrib": round(active_weights.get("imu", 0) * imu_conf, 3),
                    },
                    "audio": {
                        "class": evidence.audio_class,
                        "raw_conf": round(evidence.audio_confidence, 3),
                        "weight": active_weights.get("audio", 0),
                        "contrib": round(active_weights.get("audio", 0) * audio_conf, 3),
                    },
                    "obd": {
                        "speed_drop": round(evidence.obd_speed_drop, 1),
                        "throttle_drop": round(evidence.obd_throttle_drop, 1),
                        "weight": active_weights.get("obd", 0),
                        "contrib": round(active_weights.get("obd", 0) * obd_conf, 3),
                    },
                    "vision": {
                        "description": evidence.vision_description,
                        "weight": active_weights.get("vision", 0),
                        "contrib": round(active_weights.get("vision", 0) * vision_conf, 3),
                    },
                },
                "explanation": self._explain(
                    evidence, imu_conf, audio_conf, obd_conf,
                    vision_conf, confidence, active_weights,
                ),
            }

            if is_crash:
                logger.warning(
                    f"🚨 CRASH DETECTED | confidence={confidence:.1%} | "
                    f"jerk={evidence.imu_jerk:.1f} g/s | "
                    f"audio={evidence.audio_class}@{evidence.audio_confidence:.0%}"
                )

            return result

    # ── Weight Management ────────────────────────────────────────

    def _get_active_weights(self, evidence: CrashEvidence) -> Dict[str, float]:
        """Get effective weights, redistributing for unavailable sensors.

        If a sensor has no data, its weight is redistributed proportionally
        to the remaining sensors.
        """
        weights = dict(self._weights)
        available: Set[str] = set()

        # Check which sensors have contributed data
        if evidence.imu_jerk > 0 or evidence.imu_saturated:
            available.add("imu")
        if evidence.audio_class != "normal" or evidence.audio_confidence > 0:
            available.add("audio")
        if evidence.obd_throttle_drop > 0 or evidence.obd_speed_drop > 0:
            available.add("obd")
        if evidence.vision_confidence > 0:
            available.add("vision")

        # IMU is always "available" — it's the primary sensor
        available.add("imu")

        # Redistribute weights from unavailable sensors
        unavailable = set(weights.keys()) - available
        if unavailable and available:
            total_dropped = sum(weights[s] for s in unavailable)
            total_remaining = sum(weights[s] for s in available)
            if total_remaining > 0:
                scale = (total_remaining + total_dropped) / total_remaining
                for s in available:
                    weights[s] *= scale
            for s in unavailable:
                del weights[s]

        return weights

    def get_weights_for_sensors(self, sensors_available: Set[str]) -> Dict[str, float]:
        """Get crash weights for a specific set of available sensors.

        Useful for external modules to understand the system's
        detection capability given current sensor availability.
        """
        weights = dict(self._weights)
        unavailable = set(weights.keys()) - sensors_available
        if unavailable and sensors_available:
            total_dropped = sum(weights.get(s, 0) for s in unavailable)
            total_remaining = sum(weights.get(s, 0) for s in sensors_available)
            if total_remaining > 0:
                scale = (total_remaining + total_dropped) / total_remaining
                for s in sensors_available:
                    if s in weights:
                        weights[s] *= scale
            for s in unavailable:
                weights.pop(s, None)
        return weights

    # ── Explanation ───────────────────────────────────────────────

    def _explain(
        self, ev: CrashEvidence,
        imu_c: float, audio_c: float, obd_c: float, vision_c: float,
        total: float, weights: Dict[str, float],
    ) -> str:
        """Generate human-readable explanation of crash assessment."""
        lines = [f"Crash confidence: {total:.0%}"]

        # IMU
        imu_note = ""
        if ev.imu_saturated:
            imu_note = " [SATURATED — exceeded ±16g sensor range]"
        lines.append(
            f"• IMU: {ev.imu_jerk:.1f} g/s jerk{imu_note} "
            f"(threshold: {self._jerk_threshold})"
        )

        # Audio
        lines.append(
            f"• Audio: '{ev.audio_class}' at {ev.audio_confidence:.0%}"
        )

        # OBD
        if ev.obd_throttle_drop > 0 or ev.obd_speed_drop > 0:
            lines.append(
                f"• OBD: Speed -{ev.obd_speed_drop:.0f} km/h, "
                f"Throttle -{ev.obd_throttle_drop:.0f}% (async corroboration)"
            )
        else:
            lines.append("• OBD: Awaiting async corroboration...")

        # Vision
        if ev.vision_description:
            lines.append(f"• Vision: {ev.vision_description}")

        return "\n".join(lines)

    # ── Reset ────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset detector state (e.g., after user acknowledgment)."""
        with self._lock:
            self._state = "monitoring"
            self._accel_history.clear()
            logger.info("CrashDetector reset to monitoring state")
