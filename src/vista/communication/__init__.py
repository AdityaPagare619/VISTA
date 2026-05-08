"""
VISTA Communication Layer
=========================
Alert routing, MQTT telemetry, BLE peripheral, and cloud messaging.

Exports:
    MQTTManager   — MQTT publisher/subscriber to local broker
    BLEManager    — BLE peripheral advertising vehicle data
    AlertManager  — Multi-channel alert router (Telegram/BLE/MQTT/buzzer)
    Decision      — Structured decision output from the intelligence engine
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from loguru import logger


# ── Decision Dataclass ────────────────────────────────────────────
# Shared across intelligence → communication → alert pipeline.

@dataclass
class Decision:
    """Structured decision output from the VISTA intelligence engine.

    Produced by the decision engine and routed through AlertManager
    to all configured channels (Telegram, MQTT, BLE, buzzer).

    Attributes:
        event_type: One of "crash", "theft", "harsh_braking",
            "rapid_accel", "sharp_turn", or generic event types.
        confidence: 0.0-1.0 probability score from the decision engine.
        severity: "critical", "warning", or "info" — drives routing logic.
        evidence: Dict of sensor name → contribution score for explainability.
        timestamp: Unix epoch float when the decision was made.
        location: Optional GPS dict {"lat", "lon", "speed", "accuracy"}.
        image_path: Optional filesystem path to a captured camera frame.
    """

    event_type: str
    confidence: float
    severity: str = "info"
    evidence: Dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: __import__("time").time())
    location: Optional[Dict[str, float]] = None
    image_path: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate Decision fields after construction."""
        valid_severities = {"critical", "warning", "info"}
        if self.severity not in valid_severities:
            logger.warning(
                f"Invalid severity '{self.severity}' — defaulting to 'info'"
            )
            self.severity = "info"

        if not (0.0 <= self.confidence <= 1.0):
            logger.warning(
                f"Confidence {self.confidence} out of range — clamping to [0, 1]"
            )
            self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def evidence_summary(self) -> str:
        """Human-readable evidence breakdown for alert messages."""
        if not self.evidence:
            return "No evidence available"
        items = [f"{k}: {v:.1%}" for k, v in sorted(
            self.evidence.items(), key=lambda x: x[1], reverse=True
        )]
        return " | ".join(items)

    @property
    def location_str(self) -> str:
        """Formatted GPS location string or 'unknown'."""
        if not self.location:
            return "Unknown"
        lat = self.location.get("lat", "?")
        lon = self.location.get("lon", "?")
        speed = self.location.get("speed")
        parts = [f"({lat}, {lon})"]
        if speed is not None:
            parts.append(f"{speed:.1f} km/h")
        return " ".join(parts)


# ── Config Loading (shared across communication modules) ─────────

_config: Optional[Dict[str, Any]] = None
_config_lock = threading.Lock()


def _load_config() -> Dict[str, Any]:
    """Load and cache the VISTA configuration from config.yaml.

    Thread-safe singleton. Path resolved relative to the vista package root.
    """
    global _config
    if _config is not None:
        return _config

    with _config_lock:
        if _config is not None:
            return _config

        package_root = Path(__file__).resolve().parent.parent
        config_path = package_root / "config.yaml"

        if not config_path.exists():
            logger.error(f"Config file not found at {config_path}")
            raise FileNotFoundError(f"config.yaml not found at {config_path}")

        logger.debug(f"Loading config from {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)

        return _config


def _is_demo_mode() -> bool:
    """Return True if the system is running in demo mode."""
    env_demo = os.environ.get("DEMO_MODE", "").lower()
    if env_demo in ("true", "1", "yes", "on"):
        return True
    if env_demo in ("false", "0", "no", "off"):
        return False
    cfg = _load_config()
    return bool(cfg.get("system", {}).get("demo_mode", False))


# ── Optional import of dotenv (best-effort) ──────────────────────
try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore

    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        _load_dotenv(_env_path)
        logger.debug(f"Loaded environment from {_env_path}")
except ImportError:
    pass  # python-dotenv is optional — env vars must be set externally


# ── Public API ────────────────────────────────────────────────────

from .mqtt_manager import MQTTManager    # noqa: E402
from .ble_manager import BLEManager      # noqa: E402
from .alert_manager import AlertManager  # noqa: E402

__all__ = [
    "Decision",
    "MQTTManager",
    "BLEManager",
    "AlertManager",
]
