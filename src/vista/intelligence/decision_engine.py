"""
VISTA Decision Engine — Explainable Multi-Factor Confidence Scoring
====================================================================
The core intelligence layer that fuses signals from all sensors into
high-confidence, human-readable event decisions.

Key features:
    - Multi-factor weighted scoring with automatic weight redistribution
      when a sensor is unavailable (e.g., camera offline).
    - Configurable alert/warning thresholds.
    - Human-readable explanation generation for every decision.
    - Driver behaviour analytics over configurable time windows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml
from loguru import logger


# ══════════════════════════════════════════════════════════════════
# Data Structures
# ══════════════════════════════════════════════════════════════════

@dataclass
class Evidence:
    """A single piece of sensor evidence contributing to a decision.

    Attributes:
        sensor: Canonical sensor name (e.g. "imu_jerk", "audio", "obd_throttle").
        value: The numeric reading that triggered this evidence.
        threshold: The threshold against which ``value`` was compared.
        confidence: How confident this evidence indicates an event [0, 1].
        explanation: Human-readable one-liner about what was observed.
    """
    sensor: str
    value: float
    threshold: float
    confidence: float
    explanation: str


@dataclass
class Decision:
    """The output of the decision engine for a single assessment.

    Attributes:
        is_alert: ``True`` when confidence exceeds the alert threshold.
        event_type: Canonical event name (e.g. "crash", "theft", "harsh_braking").
        confidence: Aggregate confidence score [0.0, 1.0].
        severity: "alert", "warning", or "normal".
        evidence: List of ``Evidence`` records that contributed.
        explanation: Human-readable narrative of the decision.
    """
    is_alert: bool
    event_type: str
    confidence: float
    severity: str  # "alert" | "warning" | "normal"
    evidence: List[Evidence] = field(default_factory=list)
    explanation: str = ""


# ══════════════════════════════════════════════════════════════════
# Decision Engine
# ══════════════════════════════════════════════════════════════════

class DecisionEngine:
    """Explainable multi-factor weighted confidence scorer.

    Reads fusion/decision thresholds from ``config.yaml``.
    Designed to work gracefully when the vision (camera) pipeline
    is unavailable — redistributes its weight proportionally to
    the remaining sensors.

    Usage::

        de = DecisionEngine()
        decision = de.assess_crash(
            imu_data={"jerk": 4.5, "accel_x": -2.1},
            obd_data={"throttle_delta": -80, "speed": 0},
            audio_result=("crash", 0.88),
        )
        if decision.is_alert:
            print(decision.explanation)
    """

    def __init__(self) -> None:
        cfg = self._load_config()
        dc = cfg.get("decision", {})

        # ── Crash thresholds & weights ───────────────────────────
        crash_cfg = dc.get("crash", {})
        self._crash_alert_threshold: float = float(
            crash_cfg.get("alert_threshold", 0.65)
        )
        self._crash_warning_threshold: float = float(
            crash_cfg.get("warning_threshold", 0.40)
        )
        self._crash_weights: Dict[str, float] = {
            k: float(v)
            for k, v in crash_cfg.get("sensor_weights", {
                "imu_jerk": 0.35,
                "obd_throttle": 0.25,
                "audio": 0.25,
                "vision": 0.15,
            }).items()
        }

        # ── Theft thresholds & weights ───────────────────────────
        theft_cfg = dc.get("theft", {})
        self._theft_alert_threshold: float = float(
            theft_cfg.get("alert_threshold", 0.70)
        )
        self._theft_weights: Dict[str, float] = {
            k: float(v)
            for k, v in theft_cfg.get("sensor_weights", {
                "pir": 0.40,
                "camera": 0.35,
                "ignition": 0.25,
            }).items()
        }

        # ── Driver behavior thresholds ───────────────────────────
        beh_cfg = dc.get("driver_behavior", {})
        self._harsh_braking_jerk: float = float(
            beh_cfg.get("harsh_braking_jerk_threshold", 3.0)
        )  # g/s
        self._rapid_accel_threshold: float = float(
            beh_cfg.get("rapid_accel_threshold", 0.5)
        )  # g
        self._analysis_interval_hours: float = float(
            beh_cfg.get("analysis_interval_hours", 24)
        )

        logger.info(
            f"DecisionEngine initialized | crash_alert={self._crash_alert_threshold:.2f} "
            f"crash_warn={self._crash_warning_threshold:.2f} | "
            f"theft_alert={self._theft_alert_threshold:.2f}"
        )

    # ── Config loader ────────────────────────────────────────────

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        package_root = Path(__file__).resolve().parent.parent
        config_path = package_root / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)  # type: ignore[no-any-return]

    # ── Crash Assessment ─────────────────────────────────────────

    def assess_crash(
        self,
        imu_data: Optional[Dict[str, float]] = None,
        obd_data: Optional[Dict[str, float]] = None,
        audio_result: Optional[Tuple[str, float]] = None,
        vision_result: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        """Assess whether a crash has occurred based on fused sensor data.

        Args:
            imu_data: Dict with keys ``jerk`` (g/s), ``accel_x`` (g), etc.
            obd_data: Dict with keys ``throttle_delta`` (%), ``speed`` (km/h).
            audio_result: ``(class_label, confidence)`` from AudioClassifier.
            vision_result: Optional dict from CloudVision ``analyze_scene()``.

        Returns:
            A ``Decision`` with severity and explanation.
        """
        imu_data = imu_data or {}
        obd_data = obd_data or {}

        evidence_list: List[Evidence] = []
        active_weights = dict(self._crash_weights)

        # ── 1. IMU Jerk ──────────────────────────────────────
        jerk = imu_data.get("jerk", 0.0)
        # Thresholds for jerk: > 3 g/s = abnormal, > 6 = severe
        jerk_threshold = 3.0
        jerk_conf = self._sigmoid_score(abs(jerk), jerk_threshold, 8.0)
        if jerk_conf > 0.1:
            evidence_list.append(Evidence(
                sensor="imu_jerk",
                value=jerk,
                threshold=jerk_threshold,
                confidence=jerk_conf,
                explanation=f"IMU jerk {jerk:.1f} g/s {'exceeds' if abs(jerk) > jerk_threshold else 'within'} threshold of {jerk_threshold} g/s",
            ))

        # ── 2. IMU Acceleration Spike ────────────────────────
        accel_x = imu_data.get("accel_x", 0.0)
        accel_threshold = 2.5  # g — rapid deceleration
        accel_conf = self._sigmoid_score(abs(accel_x), accel_threshold, 6.0)
        if accel_conf > 0.1:
            evidence_list.append(Evidence(
                sensor="imu_accel",
                value=accel_x,
                threshold=accel_threshold,
                confidence=accel_conf,
                explanation=f"IMU acceleration {accel_x:.1f} g (crash signature: sudden deceleration)",
            ))

        # ── 3. OBD Throttle Drop ─────────────────────────────
        throttle_delta = obd_data.get("throttle_delta", 0.0)
        speed = obd_data.get("speed", -1.0)
        throttle_conf = 0.0
        if throttle_delta < -30:  # throttle dropped >30% quickly
            throttle_conf = min(1.0, abs(throttle_delta) / 100.0)
        if speed is not None and speed <= 2.0:
            # Vehicle stopped — strong crash indicator
            throttle_conf = max(throttle_conf, 0.8)
        if throttle_conf > 0.1:
            evidence_list.append(Evidence(
                sensor="obd_throttle",
                value=throttle_delta,
                threshold=-30.0,
                confidence=throttle_conf,
                explanation=f"Throttle dropped {abs(throttle_delta):.0f}% {'and vehicle stopped' if speed is not None and speed <= 2.0 else ''}",
            ))

        # ── 4. Audio Classification ──────────────────────────
        audio_label = ""
        audio_conf = 0.0
        if audio_result is not None:
            audio_label, audio_conf = audio_result
            if audio_label == "crash" and audio_conf > 0.3:
                evidence_list.append(Evidence(
                    sensor="audio",
                    value=audio_conf,
                    threshold=0.5,
                    confidence=audio_conf,
                    explanation=f"Audio classified as '{audio_label}' with {audio_conf:.1%} confidence",
                ))

        # ── 5. Vision (optional) ─────────────────────────────
        vision_conf = 0.0
        if vision_result is not None:
            hazard = vision_result.get("hazard_score", 0.0)
            scene = vision_result.get("scene_type", "unknown")
            vision_conf = hazard / 100.0 if isinstance(hazard, (int, float)) else 0.0
            if vision_conf > 0.1:
                evidence_list.append(Evidence(
                    sensor="vision",
                    value=hazard if isinstance(hazard, (int, float)) else 0,
                    threshold=50.0,
                    confidence=vision_conf,
                    explanation=f"Vision analysis: scene='{scene}', hazard_score={hazard}",
                ))

        # ── Weight redistribution (if vision is missing) ─────
        if vision_result is None and "vision" in active_weights:
            dropped = active_weights.pop("vision")
            self._redistribute_weight(active_weights, dropped)

        # ── Compute weighted confidence ──────────────────────
        weighted_conf = self._compute_weighted_confidence(evidence_list, active_weights)

        # ── Determine severity ───────────────────────────────
        if weighted_conf >= self._crash_alert_threshold:
            severity = "alert"
            is_alert = True
        elif weighted_conf >= self._crash_warning_threshold:
            severity = "warning"
            is_alert = False
        else:
            severity = "normal"
            is_alert = False

        # ── Generate explanation ─────────────────────────────
        explanation = self._generate_explanation(evidence_list, weighted_conf)

        return Decision(
            is_alert=is_alert,
            event_type="crash",
            confidence=weighted_conf,
            severity=severity,
            evidence=evidence_list,
            explanation=explanation,
        )

    # ── Theft Assessment ─────────────────────────────────────────

    def assess_theft(
        self,
        pir_triggered: bool = False,
        ignition_off: bool = True,
        camera_analysis: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        """Assess whether a vehicle theft is in progress.

        Args:
            pir_triggered: ``True`` if the PIR motion sensor detected movement.
            ignition_off: ``True`` if the ignition is confirmed OFF.
            camera_analysis: Optional dict with ``scene_type`` and ``hazard_score``.

        Returns:
            A ``Decision`` with severity and explanation.
        """
        evidence_list: List[Evidence] = []
        active_weights = dict(self._theft_weights)

        # ── 1. PIR Motion ────────────────────────────────────
        pir_conf = 0.0
        if pir_triggered:
            pir_conf = 0.85  # High confidence when PIR is triggered
        evidence_list.append(Evidence(
            sensor="pir",
            value=float(pir_triggered),
            threshold=0.5,
            confidence=pir_conf,
            explanation=f"PIR motion sensor {'DETECTED movement' if pir_triggered else 'no movement'}",
        ))

        # ── 2. Ignition Status ───────────────────────────────
        ign_conf = 0.0
        if ignition_off:
            ign_conf = 0.6  # Ignition off + PIR = suspicious
        evidence_list.append(Evidence(
            sensor="ignition",
            value=float(ignition_off),
            threshold=0.5,
            confidence=ign_conf,
            explanation=f"Ignition is {'OFF' if ignition_off else 'ON'}",
        ))

        # ── 3. Camera (optional) ─────────────────────────────
        cam_conf = 0.0
        if camera_analysis is not None:
            scene = camera_analysis.get("scene_type", "unknown")
            hazard = camera_analysis.get("hazard_score", 0)
            if isinstance(hazard, (int, float)):
                cam_conf = hazard / 100.0
            if cam_conf > 0.1:
                evidence_list.append(Evidence(
                    sensor="camera",
                    value=hazard if isinstance(hazard, (int, float)) else 0,
                    threshold=50.0,
                    confidence=cam_conf,
                    explanation=f"Camera analysis: scene='{scene}'",
                ))

        # ── Weight redistribution ────────────────────────────
        if camera_analysis is None and "camera" in active_weights:
            dropped = active_weights.pop("camera")
            self._redistribute_weight(active_weights, dropped)

        # ── Compute weighted confidence ──────────────────────
        weighted_conf = self._compute_weighted_confidence(evidence_list, active_weights)

        # ── Determine severity ───────────────────────────────
        if weighted_conf >= self._theft_alert_threshold:
            severity = "alert"
            is_alert = True
        else:
            severity = "normal"
            is_alert = False

        explanation = self._generate_explanation(evidence_list, weighted_conf)

        return Decision(
            is_alert=is_alert,
            event_type="theft",
            confidence=weighted_conf,
            severity=severity,
            evidence=evidence_list,
            explanation=explanation,
        )

    # ── Driver Behavior Analysis ─────────────────────────────────

    def analyze_behavior(
        self,
        obd_history: Optional[List[Dict[str, float]]] = None,
        imu_history: Optional[List[Dict[str, float]]] = None,
    ) -> Dict[str, Any]:
        """Analyse recent driving history for behaviour patterns.

        Args:
            obd_history: List of dicts, each with keys like ``speed``, ``throttle``, ``rpm``.
            imu_history: List of dicts, each with keys like ``jerk``, ``accel_x``.

        Returns:
            Dict with keys: ``harsh_braking_count``, ``rapid_accel_count``,
            ``average_speed``, ``max_speed``, ``total_distance_km`` (estimated),
            ``risk_score``, ``summary``.
        """
        obd_history = obd_history or []
        imu_history = imu_history or []

        n_harsh_braking = 0
        n_rapid_accel = 0
        speeds: List[float] = []

        # Analyse IMU history for jerk events
        for entry in imu_history:
            jerk_val = abs(float(entry.get("jerk", 0.0)))
            accel_x = float(entry.get("accel_x", 0.0))

            if jerk_val >= self._harsh_braking_jerk:
                n_harsh_braking += 1
            if accel_x >= self._rapid_accel_threshold:
                n_rapid_accel += 1

        # Analyse OBD history for speed
        for entry in obd_history:
            spd = entry.get("speed", None)
            if spd is not None:
                speeds.append(float(spd))

        avg_speed = float(np.mean(speeds)) if speeds else 0.0
        max_speed = float(np.max(speeds)) if speeds else 0.0

        # Rough distance estimate: avg_speed (km/h) * hours
        hours = self._analysis_interval_hours
        est_distance = avg_speed * hours

        # Risk score (0-100)
        risk = 0.0
        risk += min(50.0, n_harsh_braking * 10.0)
        risk += min(30.0, n_rapid_accel * 5.0)
        risk += min(20.0, (max_speed - 100.0) / 5.0 if max_speed > 100 else 0.0)
        risk = min(100.0, risk)

        # Summary
        if risk < 20:
            summary = "Safe driving patterns observed. No concerning events."
        elif risk < 50:
            summary = (
                f"Moderate risk: {n_harsh_braking} harsh braking event(s), "
                f"{n_rapid_accel} rapid acceleration(s). Consider reviewing driving habits."
            )
        else:
            summary = (
                f"High risk: {n_harsh_braking} harsh braking event(s), "
                f"{n_rapid_accel} rapid acceleration(s). Immediate driver coaching recommended."
            )

        return {
            "harsh_braking_count": n_harsh_braking,
            "rapid_accel_count": n_rapid_accel,
            "average_speed_kmh": round(avg_speed, 1),
            "max_speed_kmh": round(max_speed, 1),
            "estimated_distance_km": round(est_distance, 1),
            "analysis_period_hours": hours,
            "risk_score": round(risk, 1),
            "summary": summary,
        }

    # ══════════════════════════════════════════════════════════════
    # Internal Helpers
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _sigmoid_score(value: float, threshold: float, saturation: float) -> float:
        """Map a value to a confidence [0, 1] via a shifted sigmoid.

        Args:
            value: The magnitude to evaluate (always non-negative internally).
            threshold: Value at which confidence ≈ 0.5.
            saturation: Value at which confidence ≈ 0.99.

        Returns:
            Confidence in [0.0, 1.0].
        """
        if value <= 0:
            return 0.0
        # Logistic function: 1 / (1 + exp(-k * (x - x0)))
        k = 5.0 / (saturation - threshold + 1e-6)
        x0 = threshold
        return float(1.0 / (1.0 + np.exp(-k * (value - x0))))

    @staticmethod
    def _redistribute_weight(weights: Dict[str, float], dropped: float) -> None:
        """Redistribute a dropped sensor's weight proportionally to remaining.

        Modifies ``weights`` in place.
        """
        if not weights or dropped <= 0:
            return
        total = sum(weights.values())
        if total <= 0:
            # Assign evenly
            n = len(weights)
            for k in weights:
                weights[k] = 1.0 / n
            return
        scale = (total + dropped) / total
        for k in weights:
            weights[k] *= scale

    @staticmethod
    def _compute_weighted_confidence(
        evidence_list: List[Evidence],
        weights: Dict[str, float],
    ) -> float:
        """Compute the aggregate confidence from weighted evidence.

        For each sensor type with weight w, its contribution =
        w * max(confidence of evidence entries matching that sensor).

        The final score is the sum of weighted contributions,
        capped at 1.0.
        """
        if not evidence_list or not weights:
            return 0.0

        # Group evidence by sensor, take max confidence per sensor
        sensor_conf: Dict[str, float] = {}
        for ev in evidence_list:
            key = ev.sensor
            if key not in sensor_conf or ev.confidence > sensor_conf[key]:
                sensor_conf[key] = ev.confidence

        score = 0.0
        for sensor, weight in weights.items():
            if sensor in sensor_conf:
                score += weight * sensor_conf[sensor]

        return min(1.0, max(0.0, score))

    @staticmethod
    def _generate_explanation(
        evidence_list: List[Evidence],
        confidence: float,
    ) -> str:
        """Produce a human-readable narrative from evidence and confidence.

        Args:
            evidence_list: Collected evidence items.
            confidence: Aggregate confidence score.

        Returns:
            A single string summarising the decision rationale.
        """
        if not evidence_list:
            return (
                f"Decision confidence: {confidence:.1%}. "
                f"No significant evidence from any sensor."
            )

        lines = [f"Decision confidence: {confidence:.1%}."]

        # Show top contributing evidence first
        sorted_ev = sorted(evidence_list, key=lambda e: e.confidence, reverse=True)
        for ev in sorted_ev[:5]:  # max 5 lines
            lines.append(f"  • [{ev.sensor}] {ev.explanation} "
                         f"(conf={ev.confidence:.1%})")

        return "\n".join(lines)
