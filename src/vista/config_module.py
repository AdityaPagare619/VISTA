"""
VISTA Configuration — Central Module
======================================
Single source of truth for config loading and demo mode detection.

Replaces the 4 duplicated _load_config() / _is_demo_mode() functions
that were copy-pasted into hal/__init__, communication/__init__,
data/__init__, and main.py.

Usage:
    from vista.config import load_config, is_demo_mode
    cfg = load_config()
    if is_demo_mode():
        ...
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict

import yaml
from loguru import logger

# ── Package root (src/vista/) ────────────────────────────────────
VISTA_ROOT = Path(__file__).resolve().parent

# ── Singleton config cache ───────────────────────────────────────
_config: Dict[str, Any] | None = None
_config_lock = threading.Lock()


def load_config() -> Dict[str, Any]:
    """Load and cache the VISTA configuration from config.yaml.

    Thread-safe singleton. Returns the cached dict on subsequent calls.
    """
    global _config
    if _config is not None:
        return _config

    with _config_lock:
        if _config is not None:
            return _config

        config_path = VISTA_ROOT / "config.yaml"
        if not config_path.exists():
            logger.error(f"Config file not found at {config_path}")
            raise FileNotFoundError(f"config.yaml not found at {config_path}")

        logger.debug(f"Loading configuration from {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)

        logger.info(
            f"Configuration loaded | "
            f"device={_config.get('device', {}).get('id', 'unknown')} | "
            f"demo_mode={_config.get('system', {}).get('demo_mode', False)}"
        )
        return _config


def is_demo_mode() -> bool:
    """Return True if the system is running in demo mode.

    Checks, in order:
    1. DEMO_MODE environment variable (overrides config)
    2. system.demo_mode in config.yaml
    """
    env_demo = os.environ.get("DEMO_MODE", "").lower()
    if env_demo in ("true", "1", "yes", "on"):
        return True
    if env_demo in ("false", "0", "no", "off"):
        return False

    cfg = load_config()
    return bool(cfg.get("system", {}).get("demo_mode", False))


# ── .env loading (best-effort, on module import) ──────────────────
try:
    from dotenv import load_dotenv as _load_dotenv

    _env_path = VISTA_ROOT / ".env"
    if _env_path.exists():
        _load_dotenv(_env_path)
        logger.debug(f"Loaded environment from {_env_path}")
except ImportError:
    pass  # python-dotenv is optional
