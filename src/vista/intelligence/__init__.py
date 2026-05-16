"""
VISTA Intelligence Layer (v3.0)
================================
Sensor fusion, crash detection, audio classification, decision logic,
and cloud vision.

v3.0 Changes:
    - FusionEngine → VelocityEKF (2-state, velocity-only)
    - NEW CrashDetector (separated from EKF, signature-aware)
    - FusionEngine kept as backward-compat alias

Exports:
    VelocityEKF     — 2-state EKF for OBD+IMU velocity estimation
    CrashDetector   — Signature-aware multi-tier crash detection
    CrashEvidence   — Dataclass for multi-modal crash evidence
    AudioClassifier — CNN-based crash/siren/horn detection (TFLite)
    DecisionEngine  — Explainable multi-factor weighted confidence scoring
    CloudVision     — Gemini Vision API scene analysis
    Evidence        — Evidence dataclass (from DecisionEngine)
    Decision        — Decision dataclass (from DecisionEngine)
    FusionEngine    — DEPRECATED alias for VelocityEKF
"""

from __future__ import annotations

# v3.0: Primary exports
from .velocity_ekf import VelocityEKF
from .crash_detector import CrashDetector, CrashEvidence
from .audio_classifier import AudioClassifier
from .decision_engine import DecisionEngine, Evidence, Decision
from .cloud_vision import CloudVision

# Backward compatibility: FusionEngine → VelocityEKF
from .velocity_ekf import FusionEngine

__all__ = [
    # v3.0 primary
    "VelocityEKF",
    "CrashDetector",
    "CrashEvidence",
    # Existing
    "AudioClassifier",
    "DecisionEngine",
    "Evidence",
    "Decision",
    "CloudVision",
    # Deprecated alias
    "FusionEngine",
]
