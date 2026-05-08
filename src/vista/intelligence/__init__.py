"""
VISTA Intelligence Layer
========================
Sensor fusion, audio classification, decision logic, and cloud vision.

Exports:
    FusionEngine    — Extended Kalman Filter for OBD+IMU velocity fusion
    AudioClassifier — CNN-based crash/siren/horn detection (TFLite)
    DecisionEngine  — Explainable multi-factor weighted confidence scoring
    CloudVision     — Gemini Vision API scene analysis

Also exports the Evidence and Decision dataclasses used by the
decision engine for external consumption (e.g., by alert/telemetry
modules).
"""

from __future__ import annotations

from .fusion_engine import FusionEngine
from .audio_classifier import AudioClassifier
from .decision_engine import DecisionEngine, Evidence, Decision
from .cloud_vision import CloudVision

__all__ = [
    "FusionEngine",
    "AudioClassifier",
    "DecisionEngine",
    "Evidence",
    "Decision",
    "CloudVision",
]
