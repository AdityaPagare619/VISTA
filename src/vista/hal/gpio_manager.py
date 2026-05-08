"""
VISTA GPIO Manager
==================
Abstracts Raspberry Pi GPIO operations for the buzzer and ESP32-C3
power sentinel communication.  All hardware access is mediated through
gpiozero; in demo mode, actions are logged instead of toggling pins.

Pin assignments:
    Buzzer:    configurable (default GPIO 17)
    ESP32 WAKE:  config.esp32.wake_gpio   (Pi → ESP32, default GPIO 5)
    ESP32 STATUS: config.esp32.status_gpio (Pi ← ESP32, default GPIO 6)
"""

import time
from typing import Any, Dict, List, Optional

from loguru import logger

from . import _is_demo_mode, _load_config


class GPIOManager:
    """Manages GPIO peripherals: buzzer and ESP32 communication.

    In demo mode, all hardware operations become no-ops with
    descriptive logging, enabling classroom demonstrations without
    physical hardware connected.
    """

    _DEFAULT_BUZZER_PIN = 17
    _DEFAULT_ESP_WAKE = 5
    _DEFAULT_ESP_STATUS = 6

    def __init__(self) -> None:
        cfg = _load_config()
        esp_cfg = cfg.get("esp32", {})

        self._demo_mode = _is_demo_mode()

        # Pin assignments
        self._buzzer_pin = self._DEFAULT_BUZZER_PIN
        self._esp_wake = esp_cfg.get("wake_gpio", self._DEFAULT_ESP_WAKE)
        self._esp_status = esp_cfg.get("status_gpio", self._DEFAULT_ESP_STATUS)

        # Hardware objects (None in demo mode)
        self._buzzer: Any = None       # gpiozero.Buzzer or PWMOutputDevice
        self._wake_line: Any = None    # gpiozero.DigitalOutputDevice
        self._status_line: Any = None  # gpiozero.DigitalInputDevice

        self._initialised = False
        self._running = False

        logger.info(
            f"GPIOManager initialized | "
            f"buzzer=GPIO{self._buzzer_pin} | "
            f"wake=GPIO{self._esp_wake} | "
            f"status=GPIO{self._esp_status} | "
            f"demo={self._demo_mode}"
        )

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Initialise GPIO pins via gpiozero.

        In demo mode, this is a no-op.
        """
        if self._running:
            logger.warning("GPIOManager.start() called but already running")
            return

        if self._demo_mode:
            logger.info("GPIOManager starting in DEMO mode (GPIO logging only)")
            self._initialised = True
            self._running = True
            return

        try:
            from gpiozero import (  # type: ignore[import-untyped]
                DigitalInputDevice,
                DigitalOutputDevice,
            )

            # Configure ESP32 WAKE as output (Pi drives high to wake ESP32)
            self._wake_line = DigitalOutputDevice(
                self._esp_wake, active_high=True, initial_value=False
            )

            # Configure ESP32 STATUS as input (Pi reads ESP32 status)
            self._status_line = DigitalInputDevice(
                self._esp_status, pull_up=False
            )

            # Configure buzzer via PWM-capable pin
            from gpiozero import PWMOutputDevice

            self._buzzer = PWMOutputDevice(
                self._buzzer_pin, frequency=440, initial_value=0.0
            )

            self._initialised = True
            self._running = True
            logger.success(
                f"GPIO initialised | buzzer=GPIO{self._buzzer_pin} | "
                f"wake=GPIO{self._esp_wake} | status=GPIO{self._esp_status}"
            )

        except ImportError:
            logger.error("gpiozero not installed — falling back to demo")
            self._demo_mode = True
            self._initialised = True
            self._running = True
        except Exception as exc:
            logger.error(f"GPIO init failed: {exc} — falling back to demo")
            self._demo_mode = True
            self._initialised = True
            self._running = True

    def stop(self) -> None:
        """Release all GPIO resources."""
        if not self._running:
            return

        logger.info("GPIOManager stopping…")

        if self._buzzer is not None:
            try:
                self._buzzer.off()
                self._buzzer.close()
            except Exception as exc:
                logger.warning(f"Error closing buzzer: {exc}")
            self._buzzer = None

        if self._wake_line is not None:
            try:
                self._wake_line.off()
                self._wake_line.close()
            except Exception as exc:
                logger.warning(f"Error closing wake line: {exc}")
            self._wake_line = None

        if self._status_line is not None:
            try:
                self._status_line.close()
            except Exception as exc:
                logger.warning(f"Error closing status line: {exc}")
            self._status_line = None

        self._running = False
        self._initialised = False
        logger.info("GPIOManager stopped")

    # ── Buzzer Operations ────────────────────────────────────────

    def buzzer_on(self, frequency: int = 440, duty_cycle: float = 0.5) -> None:
        """Turn the buzzer on continuously.

        Args:
            frequency: Tone frequency in Hz (default 440 = A4).
            duty_cycle: PWM duty cycle 0.0-1.0 (default 0.5).
        """
        if self._demo_mode:
            logger.info(f"[DEMO] BUZZER ON (freq={frequency}Hz, duty={duty_cycle:.1%})")
            return

        if not self._running:
            logger.warning("buzzer_on() called but GPIOManager not started")
            return

        try:
            if self._buzzer is not None:
                self._buzzer.frequency = frequency
                self._buzzer.value = float(duty_cycle)
                logger.debug(f"Buzzer ON | {frequency}Hz @ {duty_cycle:.0%}")
        except Exception as exc:
            logger.error(f"buzzer_on() failed: {exc}")

    def buzzer_off(self) -> None:
        """Turn the buzzer off."""
        if self._demo_mode:
            logger.info("[DEMO] BUZZER OFF")
            return

        if not self._running:
            return

        try:
            if self._buzzer is not None:
                self._buzzer.off()
                logger.debug("Buzzer OFF")
        except Exception as exc:
            logger.error(f"buzzer_off() failed: {exc}")

    def buzzer_beep(
        self,
        pattern: Optional[List[float]] = None,
        frequency: int = 1000,
    ) -> None:
        """Play a beep pattern.

        Args:
            pattern: List of (on_ms, off_ms, ...) durations in seconds.
                     Defaults to a single 200ms beep.
            frequency: Tone frequency in Hz.
        """
        if pattern is None:
            pattern = [0.2]

        if self._demo_mode:
            logger.info(
                f"[DEMO] BUZZER BEEP | pattern={pattern} | freq={frequency}Hz"
            )
            return

        if not self._running:
            logger.warning("buzzer_beep() called but GPIOManager not started")
            return

        logger.debug(f"Buzzer beep pattern: {pattern} @ {frequency}Hz")
        try:
            for i, duration in enumerate(pattern):
                if i % 2 == 0:
                    self.buzzer_on(frequency=frequency, duty_cycle=0.5)
                else:
                    self.buzzer_off()
                time.sleep(duration)
            # Ensure off after pattern
            self.buzzer_off()
        except Exception as exc:
            logger.error(f"buzzer_beep() failed: {exc}")
            self.buzzer_off()

    # ── ESP32 Communication ──────────────────────────────────────

    def wake_esp32(self, pulse_duration: float = 0.1) -> None:
        """Send a wake-up pulse to the ESP32-C3 power sentinel.

        Drives the WAKE GPIO high for *pulse_duration* seconds,
        then returns it low.

        Args:
            pulse_duration: High pulse width in seconds.
        """
        if self._demo_mode:
            logger.info(
                f"[DEMO] WAKE ESP32 | pulse={pulse_duration}s | "
                f"GPIO{self._esp_wake}"
            )
            return

        if not self._running:
            logger.warning("wake_esp32() called but GPIOManager not started")
            return

        try:
            if self._wake_line is not None:
                self._wake_line.on()
                time.sleep(pulse_duration)
                self._wake_line.off()
                logger.debug(
                    f"ESP32 wake pulse sent | {pulse_duration}s | "
                    f"GPIO{self._esp_wake}"
                )
        except Exception as exc:
            logger.error(f"wake_esp32() failed: {exc}")

    def is_esp32_alive(self) -> bool:
        """Check if the ESP32 is alive by reading its STATUS line.

        Returns:
            True if the ESP32 STATUS GPIO is high, else False.
        """
        if self._demo_mode:
            # In demo mode, simulate ESP32 alive after first wake
            logger.debug("[DEMO] is_esp32_alive() → True")
            return True

        if not self._running or self._status_line is None:
            return False

        try:
            alive = bool(self._status_line.value)
            logger.debug(f"ESP32 STATUS GPIO{self._esp_status} = {'HIGH' if alive else 'LOW'}")
            return alive
        except Exception as exc:
            logger.error(f"is_esp32_alive() read failed: {exc}")
            return False

    def read_esp32_status(self) -> Optional[Dict[str, Any]]:
        """Read the ESP32 status.

        Currently polls the digital STATUS line.  In a full
        implementation this could read serial/I2C/SPI for richer
        telemetry (battery voltage, PIR state, etc.).

        Returns:
            Dict with keys: 'alive', 'gpio', or None on error.
        """
        alive = self.is_esp32_alive()

        status: Dict[str, Any] = {
            "alive": alive,
            "gpio": self._esp_status,
        }

        if self._demo_mode:
            status.update({
                "battery_v": 12.4,
                "battery_pct": 85,
                "pir_triggered": False,
                "mode": "demo",
            })

        logger.debug(f"ESP32 status: {status}")
        return status

    # ── Properties ───────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def demo_mode(self) -> bool:
        return self._demo_mode
