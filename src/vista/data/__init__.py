"""
VISTA Data Layer
================
Time-series storage via InfluxDB and event logging via local SQLite.

Exports:
    InfluxWriter  — Buffered InfluxDB writer for telemetry
    SQLiteManager — Thread-safe SQLite event database
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from loguru import logger


# ── Config Loading (shared across data modules) ──────────────────

_config: Optional[Dict[str, Any]] = None
_config_lock = threading.Lock()


def _load_config() -> Dict[str, Any]:
    """Load and cache the VISTA configuration from config.yaml."""
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
    """Return True if running in demo mode."""
    env_demo = os.environ.get("DEMO_MODE", "").lower()
    if env_demo in ("true", "1", "yes", "on"):
        return True
    if env_demo in ("false", "0", "no", "off"):
        return False
    cfg = _load_config()
    return bool(cfg.get("system", {}).get("demo_mode", False))


# ── .env Loading (best-effort) ───────────────────────────────────
try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore

    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        _load_dotenv(_env_path)
        logger.debug(f"Loaded environment from {_env_path}")
except ImportError:
    pass


# ── Public API ───────────────────────────────────────────────────

from .influx_writer import InfluxWriter    # noqa: E402
from .sqlite_manager import SQLiteManager  # noqa: E402

__all__ = [
    "InfluxWriter",
    "SQLiteManager",
]
