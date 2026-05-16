"""
VISTA Power Manager — MOSFET Lifecycle Control (v3.0)
======================================================
Manages the P-channel MOSFET power switch circuit that controls
Raspberry Pi power from the ESP32 / vehicle battery.

Hardware Circuit:
    ESP32 GPIO7 → NPN Transistor → MOSFET Gate
    - GPIO7 HIGH → NPN ON → Gate LOW → P-MOSFET ON → Pi powered
    - GPIO7 LOW  → NPN OFF → Gate HIGH → P-MOSFET OFF → Pi 0W

    Pi GPIO6 → Heartbeat (toggles 1Hz when alive)
    - ESP32 watches this. No toggle for 30s = Pi is dead.

This module runs on the Raspberry Pi side. It handles:
    - Signaling to ESP32 that Pi is alive (heartbeat)
    - Requesting orderly shutdown when parking
    - Monitoring thermal and battery states (via ESP32 serial)

In demo mode: all GPIO operations are logged but not executed.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from loguru import logger

# GPIO import guard (not available on non-Pi platforms)
try:
    import RPi.GPIO as GPIO  # type: ignore[import-untyped]
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False


class PowerManager:
    """Manages Pi power lifecycle via MOSFET circuit.

    On a real Pi:
        - Starts heartbeat on GPIO6 (1Hz toggle)
        - Monitors battery/thermal state from ESP32
        - Initiates orderly shutdown on park command

    In demo mode:
        - Logs all actions without touching GPIO
        - Simulates heartbeat timing
    """

    def __init__(self) -> None:
        cfg = self._load_config()
        power_cfg = cfg.get("power", {})

        self._heartbeat_gpio: int = int(power_cfg.get("heartbeat_gpio", 6))
        self._mosfet_gpio: int = int(power_cfg.get("mosfet_gpio", 7))
        self._heartbeat_timeout: float = float(
            power_cfg.get("heartbeat_timeout", 30)
        )
        self._low_battery_voltage: float = float(
            power_cfg.get("low_battery_voltage", 11.8)
        )
        self._thermal_block_temp: float = float(
            power_cfg.get("thermal_block_temp", 55)
        )

        # Detect demo mode
        system_cfg = cfg.get("system", {})
        import os
        env_demo = os.environ.get("DEMO_MODE", "").lower()
        self._demo_mode = (
            env_demo in ("true", "1", "yes", "on")
            or system_cfg.get("demo_mode", False)
        )

        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        logger.info(
            f"PowerManager initialized | "
            f"heartbeat=GPIO{self._heartbeat_gpio} | "
            f"mosfet=GPIO{self._mosfet_gpio} | "
            f"demo={self._demo_mode}"
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

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Initialize GPIO and start heartbeat signal."""
        if self._running:
            return

        self._running = True

        if not self._demo_mode and _GPIO_AVAILABLE:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self._heartbeat_gpio, GPIO.OUT, initial=GPIO.LOW)
                logger.info(
                    f"GPIO{self._heartbeat_gpio} configured as heartbeat output"
                )
            except Exception as exc:
                logger.error(f"GPIO setup failed: {exc} — running headless")
        elif not self._demo_mode:
            logger.warning(
                "RPi.GPIO not available — PowerManager running in headless mode"
            )

        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="power-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()
        logger.info("PowerManager heartbeat started (1Hz toggle)")

    def stop(self) -> None:
        """Stop heartbeat and clean up GPIO."""
        if not self._running:
            return

        logger.info("PowerManager stopping...")
        self._running = False

        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=3.0)

        if not self._demo_mode and _GPIO_AVAILABLE:
            try:
                GPIO.output(self._heartbeat_gpio, GPIO.LOW)
                GPIO.cleanup(self._heartbeat_gpio)
            except Exception as exc:
                logger.debug(f"GPIO cleanup: {exc}")

        logger.info("PowerManager stopped")

    # ── Heartbeat ────────────────────────────────────────────────

    def _heartbeat_loop(self) -> None:
        """Toggle heartbeat GPIO at 1Hz so ESP32 knows Pi is alive.

        If ESP32 doesn't see this toggle for 30 seconds, it assumes
        the Pi has crashed and will cut power via MOSFET.
        """
        toggle_state = False
        while self._running:
            toggle_state = not toggle_state

            if not self._demo_mode and _GPIO_AVAILABLE:
                try:
                    GPIO.output(
                        self._heartbeat_gpio,
                        GPIO.HIGH if toggle_state else GPIO.LOW,
                    )
                except Exception as exc:
                    logger.debug(f"Heartbeat toggle failed: {exc}")
            else:
                logger.debug(
                    f"[DEMO] Heartbeat GPIO{self._heartbeat_gpio} → "
                    f"{'HIGH' if toggle_state else 'LOW'}"
                )

            time.sleep(0.5)  # 1Hz = toggle every 0.5s

    # ── Power Control ────────────────────────────────────────────

    def request_shutdown(self) -> None:
        """Signal intent to park: stop heartbeat, allowing ESP32 to cut power.

        The shutdown sequence:
            1. Pi stops heartbeat toggle
            2. ESP32 detects no toggle for timeout period
            3. ESP32 pulls MOSFET gate HIGH → Pi power cut (0W)
        """
        logger.info(
            "PowerManager: Shutdown requested — "
            "stopping heartbeat, ESP32 will cut MOSFET power"
        )
        self._running = False

    def signal_ready(self) -> None:
        """Signal to ESP32 that Pi has booted and is ready.

        Called after all VISTA modules are initialized.
        Holds heartbeat GPIO HIGH for 3 seconds as a handshake.
        """
        if not self._demo_mode and _GPIO_AVAILABLE:
            try:
                GPIO.output(self._heartbeat_gpio, GPIO.HIGH)
                time.sleep(3.0)  # Hold for handshake
                logger.info("PowerManager: READY signal sent to ESP32")
            except Exception as exc:
                logger.error(f"Ready signal failed: {exc}")
        else:
            logger.info("[DEMO] PowerManager: READY signal sent to ESP32")

    # ── Status ───────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> Dict[str, Any]:
        """Return current power management status."""
        return {
            "running": self._running,
            "demo_mode": self._demo_mode,
            "heartbeat_gpio": self._heartbeat_gpio,
            "mosfet_gpio": self._mosfet_gpio,
            "gpio_available": _GPIO_AVAILABLE,
        }
