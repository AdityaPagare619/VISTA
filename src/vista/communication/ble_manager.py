"""
VISTA BLE Peripheral Manager
============================
Advertises the vehicle as a BLE peripheral so phone apps can connect
and exchange data without requiring a paired connection.

Characteristics:
    STATUS  (read)   — Vehicle arm/disarm status, connection state
    GPS     (write)  — Phone sends GPS data {"lat","lon","speed","accuracy"}
    COMMAND (write)  — Phone sends commands: "arm", "disarm", "snapshot"
    ALERT   (notify) — Device notifies phone of critical events

Uses bleak (async). Wraps the asyncio event loop in a daemon thread
so the module can be used from synchronous code.

Shared state is published to a thread-safe dict for other modules to consume.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from . import _is_demo_mode, _load_config

_BLEAK_AVAILABLE = False
try:
    import bleak  # type: ignore
    _BLEAK_AVAILABLE = True
except ImportError:
    logger.warning("bleak not installed — BLE features disabled")


# ── BLE UUIDs (custom 128-bit based on VISTA service) ────────────
_SERVICE_UUID_DEFAULT = "0000VISTA-0000-1000-8000-00805F9B34FB"

# Characteristics — derived from service base
# We use the standard pattern: {base_prefix}-{char_id}-1000-8000-00805F9B34FB
def _make_char_uuid(base: str, suffix: str) -> str:
    """Derive a 128-bit characteristic UUID from the service base."""
    prefix = base[:8]  # "0000xxxx"
    return f"{prefix}-{suffix}-1000-8000-00805F9B34FB"


_CHAR_STATUS_UUID = "0000VSTA-0001-1000-8000-00805F9B34FB"   # STATUS
_CHAR_GPS_UUID = "0000VSTA-0002-1000-8000-00805F9B34FB"       # GPS
_CHAR_COMMAND_UUID = "0000VSTA-0003-1000-8000-00805F9B34FB"   # COMMAND
_CHAR_ALERT_UUID = "0000VSTA-0004-1000-8000-00805F9B34FB"     # ALERT


class BLEManager:
    """BLE peripheral advertising vehicle status and receiving commands.

    The BLE service runs its own asyncio event loop on a daemon thread,
    allowing synchronous start()/stop() from the main application.

    Usage::

        ble = BLEManager()
        ble.start()
        # ... read shared state ...
        ble.send_alert("Crash detected!")
        ble.stop()

    Shared State:
        ble.shared_state["gps"]     → latest phone GPS data
        ble.shared_state["command"] → latest received command
        ble.shared_state["status"]  → current vehicle status text

    Command Callbacks:
        Register callbacks to react to commands immediately.
        Registers a default handler that updates shared_state["command"].
    """

    def __init__(self) -> None:
        cfg = _load_config()
        ble_cfg = cfg.get("communication", {}).get("ble", {})
        device_cfg = cfg.get("device", {})

        self._device_name: str = ble_cfg.get("device_name", device_cfg.get("id", "VISTA-0001"))
        self._service_uuid: str = ble_cfg.get("service_uuid", _SERVICE_UUID_DEFAULT)
        self._ad_interval_ms: int = ble_cfg.get("advertising_interval_ms", 100)
        self._demo_mode = _is_demo_mode()

        # Thread-safe shared state for other modules to read
        self._state_lock = threading.RLock()
        self._shared_state: Dict[str, Any] = {
            "gps": None,
            "command": None,
            "status": "initializing",
            "connected": False,
        }

        # Command callbacks
        self._command_callbacks: List[Callable[[str, dict], None]] = []

        # Internal BLE state
        self._running = False
        self._advertising = False
        self._server: Any = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ble_thread: Optional[threading.Thread] = None
        self._alert_clients: List[Any] = []  # Subscribed clients for ALERT notify

        logger.info(
            f"BLEManager initialized | name={self._device_name} | demo={self._demo_mode}"
        )

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self) -> None:
        """Start BLE advertising on a background asyncio thread."""
        if self._running:
            logger.warning("BLEManager.start() called but already running")
            return

        if self._demo_mode:
            logger.info("BLEManager: demo mode — BLE operations are no-ops")
            self._running = True
            with self._state_lock:
                self._shared_state["status"] = "demo"
            return

        if not _BLEAK_AVAILABLE:
            logger.error("bleak not installed — cannot start BLE")
            self._running = True  # Mark running so stop() can clean up
            return

        self._running = True
        self._ble_thread = threading.Thread(
            target=self._run_loop,
            name="ble-loop",
            daemon=True,
        )
        self._ble_thread.start()
        logger.info("BLEManager: advertising thread started")

    def stop(self) -> None:
        """Stop BLE advertising and clean up resources."""
        if not self._running:
            return

        logger.info("BLEManager stopping…")
        self._running = False

        if self._loop is not None and self._loop.is_running():
            # Schedule stop on the event loop
            asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)

        if self._ble_thread and self._ble_thread.is_alive():
            self._ble_thread.join(timeout=5.0)

        logger.info("BLEManager stopped")

    async def _async_stop(self) -> None:
        """Coroutine to stop BLE server gracefully."""
        try:
            if self._server is not None:
                await self._server.stop()
                self._server = None
            self._advertising = False
        except Exception as exc:
            logger.warning(f"Error during BLE async stop: {exc}")

    # ── Background Event Loop ──────────────────────────────────────

    def _run_loop(self) -> None:
        """Create and run the asyncio event loop on a daemon thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._start_advertising())
        except Exception as exc:
            logger.error(f"BLE event loop error: {exc}")
        finally:
            self._loop.close()
            self._loop = None

    async def _start_advertising(self) -> None:
        """Set up BLE server and begin advertising."""
        try:
            from bleak import BleakServer, BleakService, BleakCharacteristic  # type: ignore

            # Define service
            service = BleakService(
                uuid=self._service_uuid,
                characteristics=[
                    # STATUS — Read characteristic for vehicle state
                    BleakCharacteristic(
                        uuid=_CHAR_STATUS_UUID,
                        properties=["read"],
                        value=self._build_status_value(),
                        description="Vehicle Status",
                    ),
                    # GPS — Write characteristic for phone GPS data
                    BleakCharacteristic(
                        uuid=_CHAR_GPS_UUID,
                        properties=["write"],
                        description="GPS Data",
                    ),
                    # COMMAND — Write characteristic for phone commands
                    BleakCharacteristic(
                        uuid=_CHAR_COMMAND_UUID,
                        properties=["write"],
                        description="Commands",
                    ),
                    # ALERT — Notify characteristic for device alerts
                    BleakCharacteristic(
                        uuid=_CHAR_ALERT_UUID,
                        properties=["notify"],
                        description="Alert Notifications",
                    ),
                ],
            )

            # Create and start server
            self._server = BleakServer(
                name=self._device_name,
                services=[service],
            )

            # Register write handler
            # Note: bleak uses decorators; we hook into on_write via the characteristic
            self._server.on_write = self._on_write

            await self._server.start()
            self._advertising = True

            logger.success(
                f"BLE advertising as '{self._device_name}' | "
                f"service={self._service_uuid[:12]}…"
            )

            # Keep the server alive until stopped
            while self._running:
                await asyncio.sleep(0.5)

        except ImportError as exc:
            logger.error(f"BLE import error (missing bleak): {exc}")
        except Exception as exc:
            logger.error(f"BLE advertising error: {exc}")
            self._advertising = False

    # ── BLE Event Handlers ─────────────────────────────────────────

    def _on_write(self, characteristic: Any, data: bytes) -> None:
        """Handle writes to BLE characteristics."""
        try:
            char_uuid = getattr(characteristic, "uuid", "")

            if char_uuid == _CHAR_GPS_UUID:
                self._handle_gps_write(data)
            elif char_uuid == _CHAR_COMMAND_UUID:
                self._handle_command_write(data)
            else:
                logger.debug(f"BLE write to unknown characteristic: {char_uuid}")

        except Exception as exc:
            logger.error(f"BLE write handler error: {exc}")

    def _handle_gps_write(self, data: bytes) -> None:
        """Parse and store GPS data from the phone."""
        try:
            text = data.decode("utf-8")
            gps_data = json.loads(text)

            # Validate expected fields
            required = {"lat", "lon"}
            if not required.issubset(gps_data.keys()):
                missing = required - gps_data.keys()
                logger.warning(f"GPS data missing fields: {missing}")
                return

            # Clamp and validate
            lat = float(gps_data["lat"])
            lon = float(gps_data["lon"])
            speed = float(gps_data.get("speed", 0))
            accuracy = float(gps_data.get("accuracy", 0))

            if not (-90 <= lat <= 90):
                logger.warning(f"Invalid GPS latitude: {lat}")
                return
            if not (-180 <= lon <= 180):
                logger.warning(f"Invalid GPS longitude: {lon}")
                return
            if speed < 0:
                speed = 0
            if accuracy < 0:
                accuracy = 999

            parsed = {
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "speed": round(speed, 1),
                "accuracy": round(accuracy, 1),
            }

            with self._state_lock:
                self._shared_state["gps"] = parsed

            logger.debug(
                f"BLE GPS update | ({parsed['lat']}, {parsed['lon']}) "
                f"speed={parsed['speed']} m/s ±{parsed['accuracy']}m"
            )

        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning(f"BLE GPS parse error: {exc} — data: {data[:100]!r}")

    def _handle_command_write(self, data: bytes) -> None:
        """Parse and dispatch commands from the phone."""
        try:
            text = data.decode("utf-8").strip().lower()
            logger.info(f"BLE command received: '{text}'")

            # Validate command
            valid_commands = {"arm", "disarm", "snapshot", "status"}
            if text not in valid_commands:
                logger.warning(f"Unknown BLE command: '{text}'")
                return

            payload = {"command": text, "source": "ble"}

            with self._state_lock:
                self._shared_state["command"] = text

            # Notify all registered callbacks
            for cb in self._command_callbacks:
                try:
                    cb(text, payload)
                except Exception as exc:
                    logger.error(f"BLE command callback error: {exc}")

        except Exception as exc:
            logger.error(f"BLE command parse error: {exc}")

    # ── Alert Notification ─────────────────────────────────────────

    async def _async_send_alert(self, message: str) -> bool:
        """Send alert notification to all connected BLE clients (async)."""
        if self._server is None:
            return False

        try:
            data = json.dumps({
                "message": message,
                "timestamp": time.time(),
            }).encode("utf-8")

            if hasattr(self._server, "notify"):
                await self._server.notify(_CHAR_ALERT_UUID, data)
                logger.debug(f"BLE alert sent: {message[:100]}")
                return True
            else:
                logger.warning("BLE server does not support notify")
                return False

        except Exception as exc:
            logger.error(f"BLE alert send error: {exc}")
            return False

    def send_alert(self, message: str) -> bool:
        """Send an alert notification to connected BLE clients.

        Args:
            message: Alert message text to notify.

        Returns:
            True if the alert was queued for delivery.
            In demo mode, always returns True with logging.
        """
        if self._demo_mode:
            logger.info(f"[DEMO] BLE alert: {message[:100]}")
            return True

        if not self._advertising:
            logger.warning("BLE alert: not advertising — alert not sent")
            return False

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_send_alert(message), self._loop
            )
            return True
        else:
            logger.warning("BLE alert: event loop not running")
            return False

    # ── Callback Registration ──────────────────────────────────────

    def register_command_callback(
        self, callback: Callable[[str, dict], None]
    ) -> None:
        """Register a function called when a BLE command is received.

        Callback signature: callback(command: str, payload: dict)
        """
        if not callable(callback):
            logger.error("register_command_callback: callback must be callable")
            return
        self._command_callbacks.append(callback)

    def remove_command_callback(
        self, callback: Callable[[str, dict], None]
    ) -> None:
        """Remove a previously registered command callback."""
        try:
            self._command_callbacks.remove(callback)
        except ValueError:
            logger.warning("remove_command_callback: callback not found")

    # ── Status Helpers ─────────────────────────────────────────────

    def _build_status_value(self) -> bytes:
        """Build the STATUS characteristic value."""
        with self._state_lock:
            status_json = {
                "status": self._shared_state.get("status", "unknown"),
                "connected": self._shared_state.get("connected", False),
                "timestamp": time.time(),
            }
        return json.dumps(status_json).encode("utf-8")

    def update_status(self, status: str) -> None:
        """Update the vehicle status string (e.g., 'armed', 'disarmed')."""
        with self._state_lock:
            self._shared_state["status"] = status
        logger.debug(f"BLE status updated: {status}")

    # ── Public Properties ──────────────────────────────────────────

    @property
    def shared_state(self) -> Dict[str, Any]:
        """Return a snapshot of the shared state (thread-safe copy)."""
        with self._state_lock:
            return dict(self._shared_state)

    @property
    def gps_data(self) -> Optional[Dict[str, float]]:
        """Return the latest GPS data or None."""
        with self._state_lock:
            gps = self._shared_state.get("gps")
            return dict(gps) if gps else None

    @property
    def last_command(self) -> Optional[str]:
        """Return the last received command or None."""
        with self._state_lock:
            return self._shared_state.get("command")

    @property
    def is_advertising(self) -> bool:
        """Return True if BLE is actively advertising."""
        if self._demo_mode:
            return self._running
        return self._advertising
