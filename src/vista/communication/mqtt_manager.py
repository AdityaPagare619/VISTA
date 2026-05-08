"""
VISTA MQTT Communication Manager
================================
Publishes telemetry, alerts, and status to a local Mosquitto broker.
Subscribes to command topics for remote control from the phone app.

Thread-safe. Auto-reconnects on disconnect with exponential backoff.
Supports demo mode (no-op with logging).
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Dict, Optional

from loguru import logger

from . import _is_demo_mode, _load_config

# Import is optional — gracefully degrade if paho-mqtt is not installed.
try:
    import paho.mqtt.client as mqtt  # type: ignore
    _PAHO_AVAILABLE = True
except ImportError:
    _PAHO_AVAILABLE = False
    logger.warning("paho-mqtt not installed — MQTT features disabled")


class MQTTManager:
    """Publishes vehicle data and receives commands via MQTT.

    Topics (all relative to vista/{device_id}/):
        telemetry  — real-time sensor data (published)
        alert      — decision engine alerts (published)
        status     — device health/status (published)
        command    — remote phone commands (subscribed)

    In demo mode all operations are no-ops with logging.
    """

    def __init__(self) -> None:
        cfg = _load_config()
        device_cfg = cfg.get("device", {})
        mqtt_cfg = cfg.get("communication", {}).get("mqtt", {})

        self._device_id: str = device_cfg.get("id", "VISTA-0001")
        self._broker_host: str = mqtt_cfg.get("broker_host", "localhost")
        self._broker_port: int = mqtt_cfg.get("broker_port", 1883)
        self._topic_prefix: str = mqtt_cfg.get("topic_prefix", "vista")
        self._qos: int = mqtt_cfg.get("qos", 1)
        self._demo_mode = _is_demo_mode()

        # Topic templates
        self._base = f"{self._topic_prefix}/{self._device_id}"
        self._topic_telemetry = f"{self._base}/telemetry"
        self._topic_alert = f"{self._base}/alert"
        self._topic_status = f"{self._base}/status"
        self._topic_command = f"{self._base}/command"

        # State
        self._client: Optional[mqtt.Client] = None  # type: ignore[name-defined]
        self._connected = False
        self._running = False
        self._lock = threading.RLock()
        self._command_callbacks: list[Callable[[str, dict], None]] = []
        self._reconnect_thread: Optional[threading.Thread] = None

        logger.info(
            f"MQTTManager initialized | device={self._device_id} | "
            f"broker={self._broker_host}:{self._broker_port} | "
            f"demo={self._demo_mode}"
        )

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self) -> None:
        """Connect to the MQTT broker and start background loop."""
        if self._running:
            logger.warning("MQTTManager.start() called but already running")
            return

        if self._demo_mode:
            logger.info("MQTTManager: demo mode — MQTT operations are no-ops")
            self._running = True
            return

        if not _PAHO_AVAILABLE:
            logger.error("paho-mqtt not available — cannot start MQTT")
            self._running = True  # Mark running so stop() can clean up
            return

        self._running = True
        self._connect()

    def stop(self) -> None:
        """Disconnect from the broker and stop background threads."""
        if not self._running:
            return

        logger.info("MQTTManager stopping…")
        self._running = False

        with self._lock:
            if self._client is not None:
                try:
                    self._client.disconnect()
                    self._client.loop_stop()
                except Exception as exc:
                    logger.warning(f"Error during MQTT disconnect: {exc}")
                self._client = None
                self._connected = False

        logger.info("MQTTManager stopped")

    # ── Connection Management ──────────────────────────────────────

    def _connect(self) -> bool:
        """Establish MQTT connection and subscribe to command topic."""
        try:
            self._client = mqtt.Client(
                client_id=self._device_id,
                clean_session=True,
            )
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message

            # Enable automatic reconnect in paho
            self._client.reconnect_delay_set(min_delay=2, max_delay=30)

            logger.debug(
                f"Connecting to MQTT broker {self._broker_host}:{self._broker_port}"
            )
            self._client.connect_async(self._broker_host, self._broker_port)
            self._client.loop_start()

            # Wait briefly for connection
            timeout = 5.0
            start = time.monotonic()
            while not self._connected and (time.monotonic() - start) < timeout:
                time.sleep(0.1)

            if self._connected:
                logger.success(
                    f"MQTT connected to {self._broker_host}:{self._broker_port}"
                )
            else:
                logger.warning(
                    f"MQTT connection timeout ({timeout}s) — will retry in background"
                )
                self._start_reconnect_thread()

            return self._connected

        except Exception as exc:
            logger.error(f"MQTT connection failed: {exc}")
            self._connected = False
            self._start_reconnect_thread()
            return False

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """paho callback: called when the client connects to the broker."""
        if rc == 0:
            self._connected = True
            logger.success(f"MQTT connected (rc={rc})")
            # Subscribe to command topic
            try:
                client.subscribe(self._topic_command, qos=self._qos)
                logger.info(f"Subscribed to {self._topic_command}")
            except Exception as exc:
                logger.error(f"Failed to subscribe to command topic: {exc}")
        else:
            self._connected = False
            logger.warning(f"MQTT connection refused (rc={rc})")

    def _on_disconnect(self, client, userdata, rc, properties=None) -> None:
        """paho callback: called when the client disconnects."""
        self._connected = False
        if rc != 0:
            logger.warning(f"MQTT unexpected disconnect (rc={rc}) — auto-reconnecting")
        else:
            logger.info("MQTT disconnected cleanly")

    def _on_message(self, client, userdata, msg) -> None:
        """paho callback: called when a message arrives on a subscribed topic."""
        try:
            payload_str = msg.payload.decode("utf-8")
            payload = json.loads(payload_str)
            logger.debug(
                f"MQTT command received | topic={msg.topic} | "
                f"payload={payload_str[:200]}"
            )

            # Dispatch to registered callbacks
            command = payload.get("command", "")
            for cb in self._command_callbacks:
                try:
                    cb(command, payload)
                except Exception as exc:
                    logger.error(f"Command callback error: {exc}")

        except json.JSONDecodeError:
            logger.warning(f"MQTT command not valid JSON: {msg.payload[:200]}")
        except Exception as exc:
            logger.error(f"MQTT message handling error: {exc}")

    def _start_reconnect_thread(self) -> None:
        """Start a background thread that periodically attempts reconnection."""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return

        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            name="mqtt-reconnect",
            daemon=True,
        )
        self._reconnect_thread.start()

    def _reconnect_loop(self) -> None:
        """Attempt reconnection with exponential backoff (2s → 60s max)."""
        backoff = 2.0
        max_backoff = 60.0

        while self._running and not self._connected:
            logger.info(f"MQTT reconnect attempt in {backoff:.0f}s…")
            time.sleep(backoff)

            if not self._running:
                return

            with self._lock:
                if self._client is not None:
                    try:
                        self._client.loop_stop()
                    except Exception:
                        pass
                    self._client = None

            self._connect()

            if not self._connected:
                backoff = min(backoff * 1.5, max_backoff)
            else:
                backoff = 2.0  # Reset on success

    # ── Publishing ─────────────────────────────────────────────────

    def _publish(self, topic: str, payload: dict) -> bool:
        """Publish a JSON payload to an MQTT topic.

        Returns True on success, False on failure. Thread-safe.
        """
        if self._demo_mode:
            logger.debug(f"[DEMO] MQTT publish → {topic}: {json.dumps(payload)[:200]}")
            return True

        if not _PAHO_AVAILABLE or not self._connected:
            logger.warning(f"MQTT not connected — message queued/dropped: {topic}")
            return False

        try:
            payload_bytes = json.dumps(payload).encode("utf-8")
            result = self._client.publish(  # type: ignore[union-attr]
                topic,
                payload_bytes,
                qos=self._qos,
            )
            if result.rc == mqtt.MQTT_ERR_SUCCESS:  # type: ignore[union-attr]
                logger.debug(f"MQTT published → {topic} ({len(payload_bytes)} bytes)")
                return True
            else:
                logger.warning(f"MQTT publish failed (rc={result.rc}): {topic}")
                return False

        except Exception as exc:
            logger.error(f"MQTT publish error ({topic}): {exc}")
            return False

    def publish_telemetry(self, data: Dict[str, Any]) -> bool:
        """Publish real-time telemetry data.

        Args:
            data: Dict with sensor readings (speed, rpm, throttle,
                  audio_class, fused_velocity, timestamp, etc.)

        Returns:
            True if published successfully (or demo mode).
        """
        if not isinstance(data, dict):
            logger.error("publish_telemetry: data must be a dict")
            return False

        payload = {
            "device_id": self._device_id,
            "type": "telemetry",
            "data": data,
        }
        return self._publish(self._topic_telemetry, payload)

    def publish_alert(self, decision: Dict[str, Any]) -> bool:
        """Publish a decision engine alert.

        Args:
            decision: Dict with event_type, confidence, severity,
                      evidence, timestamp, location, image_path.

        Returns:
            True if published successfully (or demo mode).
        """
        if not isinstance(decision, dict):
            logger.error("publish_alert: decision must be a dict")
            return False

        payload = {
            "device_id": self._device_id,
            "type": "alert",
            "decision": decision,
        }
        return self._publish(self._topic_alert, payload)

    def publish_status(self, status: Dict[str, Any]) -> bool:
        """Publish device health/status information.

        Args:
            status: Dict with status fields (uptime, cpu_temp,
                    storage_free, sensor_statuses, etc.)

        Returns:
            True if published successfully (or demo mode).
        """
        if not isinstance(status, dict):
            logger.error("publish_status: status must be a dict")
            return False

        payload = {
            "device_id": self._device_id,
            "type": "status",
            "status": status,
        }
        return self._publish(self._topic_status, payload)

    # ── Command Handling ───────────────────────────────────────────

    def register_command_callback(
        self, callback: Callable[[str, dict], None]
    ) -> None:
        """Register a function to be called when a command is received.

        The callback receives (command: str, payload: dict).
        Multiple callbacks can be registered.
        """
        if not callable(callback):
            logger.error("register_command_callback: callback must be callable")
            return
        self._command_callbacks.append(callback)
        logger.debug(
            f"Command callback registered (total: {len(self._command_callbacks)})"
        )

    def remove_command_callback(
        self, callback: Callable[[str, dict], None]
    ) -> None:
        """Remove a previously registered command callback."""
        try:
            self._command_callbacks.remove(callback)
        except ValueError:
            logger.warning("remove_command_callback: callback not found")

    # ── Status ─────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """Return True if connected to the MQTT broker."""
        if self._demo_mode:
            return True
        return self._connected

    @property
    def device_id(self) -> str:
        """Return the configured device ID."""
        return self._device_id
