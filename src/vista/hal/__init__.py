"""
VISTA Hardware Abstraction Layer (HAL)
=======================================
Provides unified interfaces for all vehicle sensors and actuators.

Exports:
    OBDReader    — ELM327 OBD-II data reader
    IMUReader    — MPU6050 6-axis inertial sensor
    AudioCapture — USB microphone audio pipeline
    CameraCapture— Pi Camera v3 image capture
    GPIOManager  — GPIO abstraction (buzzer, ESP32 comms)
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict

import yaml
from loguru import logger

# ── Config Loading ────────────────────────────────────────────────
# All HAL modules share this cached config loader to avoid
# re-reading and re-parsing config.yaml from every module.

_config: Dict[str, Any] | None = None
_config_lock = threading.Lock()


def _load_config() -> Dict[str, Any]:
    """Load and cache the VISTA configuration from config.yaml.

    Returns the cached config dict. Thread-safe. Config path is
    resolved relative to the vista package root.
    """
    global _config
    if _config is not None:
        return _config

    with _config_lock:
        if _config is not None:  # Double-check under lock
            return _config

        # Resolve config path: hal/__init__.py → ../config.yaml
        package_root = Path(__file__).resolve().parent.parent
        config_path = package_root / "config.yaml"

        if not config_path.exists():
            logger.error(f"Config file not found at {config_path}")
            raise FileNotFoundError(f"config.yaml not found at {config_path}")

        logger.debug(f"Loading configuration from {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)

        logger.info(
            f"Configuration loaded | "
            f"demo_mode={_config.get('system', {}).get('demo_mode', False)} | "
            f"device_id={_config.get('device', {}).get('id', 'unknown')}"
        )
        return _config


def _is_demo_mode() -> bool:
    """Return True if the system is running in classroom demo mode.

    Checks, in order:
    1. DEMO_MODE environment variable (overrides config)
    2. system.demo_mode in config.yaml
    """
    env_demo = os.environ.get("DEMO_MODE", "").lower()
    if env_demo in ("true", "1", "yes", "on"):
        return True
    if env_demo in ("false", "0", "no", "off"):
        return False

    cfg = _load_config()
    return bool(cfg.get("system", {}).get("demo_mode", False))


# ── Public API ───────────────────────────────────────────────────

from .obd_reader import OBDReader          # noqa: E402
from .imu_reader import IMUReader          # noqa: E402
from .audio_capture import AudioCapture    # noqa: E402
from .camera_capture import CameraCapture  # noqa: E402
from .gpio_manager import GPIOManager      # noqa: E402

__all__ = [
    "OBDReader",
    "IMUReader",
    "AudioCapture",
    "CameraCapture",
    "GPIOManager",
]
