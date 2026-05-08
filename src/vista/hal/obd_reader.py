"""
VISTA OBD-II Data Reader
========================
Interfaces with an ELM327 USB adapter via the ``obd`` (python-OBD) library.
Supports continuous polling at 10 Hz with thread-safe access and graceful
degradation via simulated data in demo mode.
"""

import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

from . import _is_demo_mode, _load_config


class OBDReader:
    """Reads real-time vehicle data from an ELM327 OBD-II adapter.

    All data-access methods are thread-safe and will return None
    (or a sensible fallback) when the adapter is disconnected.

    In demo mode, realistic simulated data is returned without
    requiring physical hardware.
    """

    # ── Simulated vehicle state (demo mode) ──────────────────────
    _DEMO_SPEED_BASE = 60.0       # km/h cruise
    _DEMO_SPEED_AMP = 20.0        # ± variation
    _DEMO_RPM_BASE = 2200.0       # RPM cruise
    _DEMO_RPM_AMP = 800.0
    _DEMO_THROTTLE_BASE = 25.0    # % open
    _DEMO_LOAD_BASE = 35.0        # %  
    _DEMO_COOLANT_BASE = 90.0     # °C

    def __init__(self) -> None:
        cfg = _load_config()
        sensor_cfg = cfg.get("sensors", {}).get("obd", {})

        self._port = sensor_cfg.get("port", "/dev/ttyUSB0")
        self._baudrate = sensor_cfg.get("baudrate", 38400)
        self._poll_interval = sensor_cfg.get("poll_interval", 0.1)
        self._enabled = sensor_cfg.get("enabled", True)
        self._demo_mode = _is_demo_mode()

        self._connection: Any = None   # obd.OBD / obd.Async
        self._lock = threading.RLock()
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._connected = False

        # Latest cached values (populated by background poll thread)
        self._cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()

        self._dtc_cache: List[Tuple[str, str]] = []
        self._demo_t = 0.0  # demo time accumulator

        logger.info(
            f"OBDReader initialized | port={self._port} | "
            f"demo={self._demo_mode} | interval={self._poll_interval}s"
        )

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Connect to the OBD-II adapter and begin background polling."""
        if self._running:
            logger.warning("OBDReader.start() called but already running")
            return

        if not self._enabled:
            logger.info("OBD sensor disabled in config — skipping start")
            return

        if self._demo_mode:
            logger.info("OBDReader starting in DEMO mode (simulated data)")
            self._running = True
            self._start_demo_loop()
            return

        self._running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="obd-poll",
            daemon=True,
        )
        self._poll_thread.start()
        logger.info("OBDReader polling thread started")

    def stop(self) -> None:
        """Disconnect and stop background polling."""
        if not self._running:
            return

        logger.info("OBDReader stopping…")
        self._running = False

        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=5.0)

        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                except Exception as exc:
                    logger.warning(f"Error closing OBD connection: {exc}")
                self._connection = None
                self._connected = False

        logger.info("OBDReader stopped")

    # ── Connection Management ────────────────────────────────────

    def _connect(self) -> bool:
        """Attempt to connect to the ELM327 adapter with retry backoff."""
        try:
            import obd  # type: ignore[import-untyped]

            logger.debug(f"Connecting to OBD-II on {self._port} @ {self._baudrate}")
            self._connection = obd.OBD(
                portstr=self._port,
                baudrate=self._baudrate,
                fast=False,
                timeout=5,
            )
            self._connected = self._connection.is_connected()

            if self._connected:
                logger.success(f"OBD-II connected on {self._port}")
            else:
                logger.warning(f"OBD-II port {self._port} opened but not responding")
            return self._connected

        except ImportError:
            logger.error("python-OBD library not installed — falling back to demo")
            self._demo_mode = True
            self._connected = False
            return False
        except Exception as exc:
            logger.error(f"Failed to connect OBD-II: {exc}")
            self._connected = False
            return False

    def _reconnect_with_backoff(self) -> None:
        """Attempt reconnection with exponential backoff (1s → 32s max)."""
        backoff = 1.0
        max_backoff = 32.0

        while self._running and not self._connected:
            logger.info(f"OBD reconnecting in {backoff:.1f}s…")
            time.sleep(backoff)
            if not self._running:
                return

            try:
                with self._lock:
                    if self._connection is not None:
                        try:
                            self._connection.close()
                        except Exception:
                            pass
                    self._connect()
            except Exception as exc:
                logger.warning(f"OBD reconnect attempt failed: {exc}")

            if not self._connected:
                backoff = min(backoff * 2, max_backoff)

    # ── Background Poll Loop ─────────────────────────────────────

    def _poll_loop(self) -> None:
        """Main polling thread: connect, then poll at configured rate."""
        try:
            import obd  # type: ignore[import-untyped]
        except ImportError:
            logger.error(
                "python-OBD library not installed — falling back to demo"
            )
            self._demo_mode = True
            self._start_demo_loop()
            return

        with self._lock:
            if not self._connect():
                logger.warning("OBD initial connection failed — will retry")

        while self._running:
            if not self._connected:
                self._reconnect_with_backoff()
                if not self._running:
                    break
                if not self._connected:
                    continue

            try:
                with self._lock:
                    conn = self._connection

                if conn is None:
                    self._connected = False
                    continue

                # Query all standard PIDs in one batch
                results: Dict[str, Any] = {}

                pids = [
                    obd.commands.SPEED,
                    obd.commands.RPM,
                    obd.commands.THROTTLE_POS,
                    obd.commands.ENGINE_LOAD,
                    obd.commands.COOLANT_TEMP,
                ]
                for pid in pids:
                    try:
                        resp = conn.query(pid)
                        if resp and not resp.is_null():
                            results[pid.name] = resp.value.magnitude
                        else:
                            results[pid.name] = None
                    except Exception as exc:
                        logger.debug(f"OBD query {pid.name} failed: {exc}")
                        results[pid.name] = None

                # DTCs less frequently
                if random.random() < 0.1:  # ~1/sec at 10 Hz
                    try:
                        dtc_resp = conn.query(obd.commands.GET_DTC)
                        if dtc_resp and not dtc_resp.is_null():
                            with self._cache_lock:
                                self._dtc_cache = list(dtc_resp.value)
                    except Exception as exc:
                        logger.debug(f"OBD DTC query failed: {exc}")

                with self._cache_lock:
                    self._cache.update(results)

            except Exception as exc:
                logger.warning(f"OBD poll error: {exc}")
                self._connected = False

            time.sleep(self._poll_interval)

    # ── Demo Loop ────────────────────────────────────────────────

    def _start_demo_loop(self) -> None:
        """Start a lightweight demo thread that simulates vehicle data."""
        self._poll_thread = threading.Thread(
            target=self._demo_loop,
            name="obd-demo",
            daemon=True,
        )
        self._poll_thread.start()

    def _demo_loop(self) -> None:
        """Generate realistic simulated OBD data in a loop."""
        while self._running:
            t = self._demo_t
            self._demo_t += self._poll_interval

            # Simulate gentle driving patterns
            # Speed: varies between 40-80 km/h with slow sine
            speed = self._DEMO_SPEED_BASE + self._DEMO_SPEED_AMP * np.sin(t * 0.3)

            # RPM: follows speed loosely
            gear_factor = 30.0
            rpm = self._DEMO_RPM_BASE + speed * gear_factor * 0.8
            rpm += self._DEMO_RPM_AMP * np.sin(t * 0.7) * 0.3
            rpm = max(700, min(5500, rpm))

            # Throttle: responds to "demand"
            throttle = self._DEMO_THROTTLE_BASE + 15 * np.sin(t * 0.25)
            throttle = max(0, min(100, throttle))

            # Engine load: roughly follows throttle
            load = self._DEMO_LOAD_BASE + throttle * 0.6
            load += random.uniform(-5, 5)
            load = max(0, min(100, load))

            # Coolant: warms up then stabilizes
            if t < 120:
                coolant = 25 + (self._DEMO_COOLANT_BASE - 25) * (t / 120)
            else:
                coolant = self._DEMO_COOLANT_BASE + random.uniform(-2, 2)

            with self._cache_lock:
                self._cache["SPEED"] = round(speed, 1)
                self._cache["RPM"] = round(rpm, 0)
                self._cache["THROTTLE_POS"] = round(throttle, 1)
                self._cache["ENGINE_LOAD"] = round(load, 1)
                self._cache["COOLANT_TEMP"] = round(coolant, 1)
                self._dtc_cache = []  # No faults in demo by default

            time.sleep(self._poll_interval)

    # ── Public Data Methods (thread-safe) ────────────────────────

    def _get_cached(self, key: str) -> Optional[float]:
        with self._cache_lock:
            return self._cache.get(key)

    def get_speed(self) -> Optional[float]:
        """Return vehicle speed in km/h, or None if unavailable."""
        return self._get_cached("SPEED")

    def get_rpm(self) -> Optional[float]:
        """Return engine RPM, or None if unavailable."""
        return self._get_cached("RPM")

    def get_throttle_position(self) -> Optional[float]:
        """Return throttle position as percentage (0-100), or None."""
        return self._get_cached("THROTTLE_POS")

    def get_engine_load(self) -> Optional[float]:
        """Return engine load as percentage (0-100), or None."""
        return self._get_cached("ENGINE_LOAD")

    def get_coolant_temp(self) -> Optional[float]:
        """Return coolant temperature in °C, or None."""
        return self._get_cached("COOLANT_TEMP")

    def get_dtc_codes(self) -> List[Tuple[str, str]]:
        """Return list of (code, description) tuples for active DTCs."""
        with self._cache_lock:
            return list(self._dtc_cache)

    def get_all_pids(self) -> Dict[str, Optional[float]]:
        """Return a dict of all cached PID values.

        Keys: SPEED, RPM, THROTTLE_POS, ENGINE_LOAD, COOLANT_TEMP
        """
        with self._cache_lock:
            return dict(self._cache)

    def is_connected(self) -> bool:
        """Return True if the OBD-II adapter is currently connected."""
        if self._demo_mode:
            return self._running
        return self._connected
