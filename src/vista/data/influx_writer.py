"""
VISTA InfluxDB Time-Series Writer
=================================
Writes real-time telemetry and event data to InfluxDB with buffered
batch writes for efficiency. Handles connection failures gracefully
by buffering points in memory and retrying.

Requires:
    - influxdb-client package
    - InfluxDB 2.x server (localhost:8086 by default)
    - Token from INFLUXDB_TOKEN environment variable
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from . import _is_demo_mode, _load_config

_INFLUX_AVAILABLE = False
try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision  # type: ignore
    from influxdb_client.client.write_api import SYNCHRONOUS  # type: ignore
    _INFLUX_AVAILABLE = True
except ImportError:
    logger.warning("influxdb-client not installed — InfluxDB features disabled")


class InfluxWriter:
    """Buffered InfluxDB writer for VISTA telemetry and events.

    Telemetry data (speed, rpm, throttle, audio_class, etc.) is
    written to the "vista_telemetry" bucket. Events (crash, theft,
    etc.) are written as separate points with event details.

    Points are buffered in memory (10 by default) and flushed as a
    batch to minimize network overhead. If the connection fails,
    points are held in the buffer until the next successful flush.

    In demo mode, writes are logged but not sent to InfluxDB.

    Usage::

        writer = InfluxWriter()
        writer.start()
        writer.write_telemetry(
            timestamp=time.time(),
            speed=65.5,
            rpm=2200.0,
            throttle=25.0,
            audio_class="normal",
            fused_velocity=18.2,
        )
        # ... more writes ...
        writer.stop()  # flushes remaining buffer
    """

    _DEFAULT_BATCH_SIZE = 10
    _FLUSH_INTERVAL_SECONDS = 1.0
    _MAX_BUFFER_SIZE = 1000     # Drop oldest if buffer exceeds this
    _RECONNECT_BACKOFF_BASE = 2.0
    _RECONNECT_BACKOFF_MAX = 60.0

    def __init__(self) -> None:
        cfg = _load_config()
        influx_cfg = cfg.get("storage", {}).get("influxdb", {})
        device_cfg = cfg.get("device", {})

        self._host: str = influx_cfg.get("host", "localhost")
        self._port: int = influx_cfg.get("port", 8086)
        self._org: str = influx_cfg.get("org", "vista")
        self._bucket: str = influx_cfg.get("bucket", "vista_telemetry")
        self._retention_days: int = influx_cfg.get("retention_days", 30)
        self._device_id: str = device_cfg.get("id", "VISTA-0001")
        self._demo_mode = _is_demo_mode()

        # Token from environment (config specifies the env var name)
        token_env = influx_cfg.get("token_env", "INFLUXDB_TOKEN")
        self._token: str = os.environ.get(token_env, "").strip()
        if not self._token and not self._demo_mode:
            logger.warning(
                f"InfluxDB token not set. Set {token_env} in .env. "
                f"Telemetry writes will be buffered only."
            )

        # URL for InfluxDB client
        self._url = f"http://{self._host}:{self._port}"

        # Client and write API (created in start())
        self._client: Any = None
        self._write_api: Any = None

        # Buffering
        self._batch_size: int = self._DEFAULT_BATCH_SIZE
        self._buffer: List[Point] = []
        self._buffer_lock = threading.Lock()
        self._flush_timer: Optional[threading.Timer] = None
        self._running = False
        self._connected = False

        # Background flush thread
        self._flush_thread: Optional[threading.Thread] = None

        logger.info(
            f"InfluxWriter initialized | url={self._url} | "
            f"org={self._org} | bucket={self._bucket} | demo={self._demo_mode}"
        )

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self) -> None:
        """Connect to InfluxDB and start background flush timer."""
        if self._running:
            logger.warning("InfluxWriter.start() called but already running")
            return

        if self._demo_mode:
            logger.info("InfluxWriter: demo mode — writes logged only")
            self._running = True
            return

        if not _INFLUX_AVAILABLE:
            logger.error("influxdb-client not available — cannot start InfluxWriter")
            self._running = True  # Mark running to allow buffered writes
            return

        self._running = True
        self._connect()
        self._start_flush_thread()
        logger.info("InfluxWriter started")

    def stop(self) -> None:
        """Flush remaining buffer and disconnect from InfluxDB."""
        if not self._running:
            return

        logger.info("InfluxWriter stopping…")
        self._running = False

        # Cancel pending flush timer
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None

        # Wait for flush thread
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=5.0)

        # Final flush
        self._flush(force=True)

        # Close client
        if self._client is not None:
            try:
                self._client.close()
            except Exception as exc:
                logger.warning(f"Error closing InfluxDB client: {exc}")
            self._client = None
            self._write_api = None

        self._connected = False
        logger.info("InfluxWriter stopped")

    # ── Connection ─────────────────────────────────────────────────

    def _connect(self) -> bool:
        """Establish connection to InfluxDB."""
        if not self._token:
            logger.warning("InfluxDB token not set — writes will be buffered only")
            self._connected = True  # Pretend connected so buffering works
            return True

        try:
            self._client = InfluxDBClient(
                url=self._url,
                token=self._token,
                org=self._org,
                timeout=10_000,  # 10s
            )

            # Verify connection with a ping
            health = self._client.health()
            if health.status == "pass":
                self._write_api = self._client.write_api(
                    write_options=SYNCHRONOUS
                )
                self._connected = True
                logger.success(f"InfluxDB connected | {self._url}")
                return True
            else:
                logger.warning(f"InfluxDB health check: {health.status}")
                self._connected = False
                return False

        except Exception as exc:
            logger.error(f"InfluxDB connection failed: {exc}")
            self._connected = False
            return False

    # ── Flush Thread ───────────────────────────────────────────────

    def _start_flush_thread(self) -> None:
        """Start a background thread that periodically flushes the buffer."""
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="influx-flush",
            daemon=True,
        )
        self._flush_thread.start()

    def _flush_loop(self) -> None:
        """Periodically flush buffered points to InfluxDB."""
        while self._running:
            time.sleep(self._FLUSH_INTERVAL_SECONDS)
            if not self._running:
                break
            self._flush(force=False)

    def _flush(self, force: bool = False) -> bool:
        """Write all buffered points to InfluxDB.

        Args:
            force: If True, flush regardless of batch size.

        Returns:
            True if flush succeeded (or no points to flush).
        """
        with self._buffer_lock:
            if not self._buffer:
                return True

            if not force and len(self._buffer) < self._batch_size:
                return True

            points = list(self._buffer)
            self._buffer.clear()

        if self._demo_mode or not _INFLUX_AVAILABLE:
            logger.debug(
                f"[DEMO] InfluxDB flush | {len(points)} points"
            )
            return True

        if not self._connected:
            # Put points back in buffer (but limit size)
            self._requeue_points(points)
            # Try reconnecting
            if self._running:
                self._connect()
            return False

        try:
            if self._write_api is not None:
                self._write_api.write(
                    bucket=self._bucket,
                    org=self._org,
                    record=points,
                )
                logger.debug(f"InfluxDB flush | {len(points)} points written")
                return True
            else:
                self._requeue_points(points)
                return False

        except Exception as exc:
            logger.error(f"InfluxDB write failed: {exc}")
            self._connected = False
            self._requeue_points(points)
            return False

    def _requeue_points(self, points: List[Point]) -> None:
        """Put points back into the buffer, dropping oldest if too large."""
        with self._buffer_lock:
            combined = points + self._buffer
            if len(combined) > self._MAX_BUFFER_SIZE:
                dropped = len(combined) - self._MAX_BUFFER_SIZE
                logger.warning(
                    f"InfluxDB buffer overflow — dropping {dropped} oldest points"
                )
                self._buffer = combined[-self._MAX_BUFFER_SIZE:]
            else:
                self._buffer = combined

    # ── Telemetry Writing ──────────────────────────────────────────

    def write_telemetry(
        self,
        timestamp: float,
        speed: Optional[float] = None,
        rpm: Optional[float] = None,
        throttle: Optional[float] = None,
        engine_load: Optional[float] = None,
        coolant_temp: Optional[float] = None,
        audio_class: Optional[str] = None,
        audio_confidence: Optional[float] = None,
        fused_velocity: Optional[float] = None,
        imu_accel_x: Optional[float] = None,
        imu_accel_y: Optional[float] = None,
        imu_accel_z: Optional[float] = None,
        imu_gyro_x: Optional[float] = None,
        imu_gyro_y: Optional[float] = None,
        imu_gyro_z: Optional[float] = None,
        gps_lat: Optional[float] = None,
        gps_lon: Optional[float] = None,
        gps_speed: Optional[float] = None,
        extras: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Write a telemetry data point to InfluxDB.

        Args:
            timestamp: Unix epoch timestamp (float, seconds).
            speed: Vehicle speed in km/h.
            rpm: Engine RPM.
            throttle: Throttle position (0-100%).
            engine_load: Engine load (0-100%).
            coolant_temp: Coolant temperature in °C.
            audio_class: Audio classification label (e.g., "crash", "siren").
            audio_confidence: Audio classification confidence (0-1).
            fused_velocity: Fused velocity from sensor fusion.
            imu_accel_x/y/z: IMU accelerometer readings (m/s²).
            imu_gyro_x/y/z: IMU gyroscope readings (rad/s).
            gps_lat: GPS latitude.
            gps_lon: GPS longitude.
            gps_speed: GPS speed in m/s.
            extras: Additional key-value pairs as fields.

        Returns:
            True if the point was buffered for writing.
        """
        if not self._running:
            logger.warning("InfluxWriter: write_telemetry called but not running")
            return False

        # In demo mode or without InfluxDB, just log and return success
        if self._demo_mode or not _INFLUX_AVAILABLE:
            fields = {k: v for k, v in locals().items()
                      if v is not None and k not in ('self', 'timestamp', 'extras')}
            logger.debug(
                f"[DEMO] InfluxDB telemetry | t={timestamp:.1f} | "
                f"speed={speed} rpm={rpm} throttle={throttle} "
                f"audio={audio_class} extras={extras}"
            )
            return True

        try:
            point = Point("telemetry") \
                .tag("device_id", self._device_id) \
                .time(
                    int(timestamp * 1_000_000_000),
                    WritePrecision.NS
                )

            # Add all non-None fields
            if speed is not None:
                point = point.field("speed_kmh", float(speed))
            if rpm is not None:
                point = point.field("rpm", float(rpm))
            if throttle is not None:
                point = point.field("throttle_pct", float(throttle))
            if engine_load is not None:
                point = point.field("engine_load_pct", float(engine_load))
            if coolant_temp is not None:
                point = point.field("coolant_temp_c", float(coolant_temp))
            if audio_class is not None:
                point = point.field("audio_class", str(audio_class))
            if audio_confidence is not None:
                point = point.field("audio_confidence", float(audio_confidence))
            if fused_velocity is not None:
                point = point.field("fused_velocity_ms", float(fused_velocity))
            if imu_accel_x is not None:
                point = point.field("imu_accel_x", float(imu_accel_x))
            if imu_accel_y is not None:
                point = point.field("imu_accel_y", float(imu_accel_y))
            if imu_accel_z is not None:
                point = point.field("imu_accel_z", float(imu_accel_z))
            if imu_gyro_x is not None:
                point = point.field("imu_gyro_x", float(imu_gyro_x))
            if imu_gyro_y is not None:
                point = point.field("imu_gyro_y", float(imu_gyro_y))
            if imu_gyro_z is not None:
                point = point.field("imu_gyro_z", float(imu_gyro_z))
            if gps_lat is not None:
                point = point.field("gps_lat", float(gps_lat))
            if gps_lon is not None:
                point = point.field("gps_lon", float(gps_lon))
            if gps_speed is not None:
                point = point.field("gps_speed_ms", float(gps_speed))

            # Extras
            if extras:
                for key, value in extras.items():
                    if isinstance(value, (int, float)):
                        point = point.field(key, float(value))
                    elif isinstance(value, str):
                        point = point.field(key, value)
                    elif isinstance(value, bool):
                        point = point.field(key, value)

            with self._buffer_lock:
                self._buffer.append(point)

            # Auto-flush if buffer is full
            if len(self._buffer) >= self._batch_size:
                self._flush(force=True)

            return True

        except Exception as exc:
            logger.error(f"InfluxWriter: telemetry write error: {exc}")
            return False

    # ── Event Writing ──────────────────────────────────────────────

    def write_event(
        self,
        timestamp: float,
        event_type: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Write an event point to InfluxDB.

        Args:
            timestamp: Unix epoch timestamp.
            event_type: Type of event (e.g., "crash", "theft", "harsh_braking").
            details: Additional event details (confidence, severity, etc.).

        Returns:
            True if the point was buffered for writing.
        """
        if not self._running:
            logger.warning("InfluxWriter: write_event called but not running")
            return False

        if self._demo_mode or not _INFLUX_AVAILABLE:
            logger.debug(
                f"[DEMO] InfluxDB event | t={timestamp:.1f} | "
                f"type={event_type} | details={details}"
            )
            return True

        try:
            point = Point("events") \
                .tag("device_id", self._device_id) \
                .tag("event_type", event_type) \
                .time(
                    int(timestamp * 1_000_000_000),
                    WritePrecision.NS
                ) \
                .field("event_type_str", event_type)

            if details:
                for key, value in details.items():
                    if isinstance(value, (int, float)):
                        point = point.field(key, float(value))
                    elif isinstance(value, str):
                        point = point.field(key, value)
                    elif isinstance(value, bool):
                        point = point.field(key, value)

            with self._buffer_lock:
                self._buffer.append(point)

            return True

        except Exception as exc:
            logger.error(f"InfluxWriter: event write error: {exc}")
            return False

    # ── Status ─────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """Return True if connected to InfluxDB."""
        if self._demo_mode:
            return True
        return self._connected

    @property
    def buffer_size(self) -> int:
        """Return the number of points currently buffered."""
        with self._buffer_lock:
            return len(self._buffer)
