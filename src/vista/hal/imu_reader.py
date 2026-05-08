"""
VISTA IMU Sensor Reader
=======================
Reads the MPU6050 6-DoF inertial measurement unit over I2C.
Provides calibrated acceleration (g) and angular velocity (°/s).
"""

import random
import threading
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np
from loguru import logger

from . import _is_demo_mode, _load_config


class IMUReader:
    """Reads MPU6050 IMU data over I2C with calibration support.

    Calibration computes gyroscope offsets from 100 samples at rest.
    All getter methods return (x, y, z) tuples in sensor-native units
    (g for acceleration, °/s for gyroscope, °C for temperature).

    In demo mode, realistic motion data is simulated.
    """

    _DEMO_AX_BASE = 0.0     # g — level ground
    _DEMO_AY_BASE = 0.0
    _DEMO_AZ_BASE = 1.0     # gravity down
    _DEMO_GX_BASE = 0.0     # °/s — no rotation at rest
    _DEMO_GY_BASE = 0.0
    _DEMO_GZ_BASE = 0.0

    def __init__(self) -> None:
        cfg = _load_config()
        sensor_cfg = cfg.get("sensors", {}).get("imu", {})

        self._enabled = sensor_cfg.get("enabled", True)
        self._bus = sensor_cfg.get("bus", 1)
        self._address = sensor_cfg.get("address", 0x68)
        self._sample_rate = sensor_cfg.get("sample_rate", 100)
        self._accel_range = sensor_cfg.get("accel_range", 8)
        self._gyro_range = sensor_cfg.get("gyro_range", 500)
        self._demo_mode = _is_demo_mode()

        self._sensor: Any = None  # mpu6050.mpu6050 instance
        self._lock = threading.RLock()

        # Calibration offsets (computed by calibrate())
        self._gyro_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._calibrated = False

        # Latest cached values
        self._cache: Dict[str, Tuple[float, float, float]] = {}
        self._temp_cache: float = 25.0
        self._cache_lock = threading.Lock()

        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._demo_t = 0.0

        logger.info(
            f"IMUReader initialized | bus={self._bus} addr=0x{self._address:02X} "
            f"rate={self._sample_rate}Hz | demo={self._demo_mode}"
        )

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Initialise the MPU6050 and begin background sampling."""
        if self._running:
            logger.warning("IMUReader.start() called but already running")
            return

        if not self._enabled:
            logger.info("IMU sensor disabled in config — skipping start")
            return

        if self._demo_mode:
            logger.info("IMUReader starting in DEMO mode (simulated data)")
            self._running = True
            self._calibrated = True
            self._start_polling()
            return

        try:
            import mpu6050  # type: ignore[import-untyped]

            self._sensor = mpu6050.mpu6050(address=self._address, bus=self._bus)
            # Verify communication
            temp = self._sensor.get_temp()
            logger.info(
                f"MPU6050 connected | bus={self._bus} "
                f"addr=0x{self._address:02X} | init_temp={temp:.1f}°C"
            )
        except ImportError:
            logger.error("mpu6050-raspberrypi not installed — falling back to demo")
            self._demo_mode = True
        except Exception as exc:
            logger.error(f"MPU6050 init failed: {exc} — falling back to demo")
            self._demo_mode = True

        self._running = True
        self._start_polling()

    def stop(self) -> None:
        """Stop background sampling."""
        if not self._running:
            return

        logger.info("IMUReader stopping…")
        self._running = False

        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)

        with self._lock:
            self._sensor = None

        logger.info("IMUReader stopped")

    def _start_polling(self) -> None:
        interval = 1.0 / max(self._sample_rate, 1)
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            args=(interval,),
            name="imu-poll",
            daemon=True,
        )
        self._poll_thread.start()

    def _poll_loop(self, interval: float) -> None:
        """Background loop that reads the IMU at the configured sample rate."""
        while self._running:
            start = time.monotonic()

            try:
                if self._demo_mode:
                    accel, gyro, temp = self._demo_sample()
                elif self._sensor is not None:
                    raw_accel = self._sensor.get_accel_data()
                    raw_gyro = self._sensor.get_gyro_data()
                    temp = self._sensor.get_temp()

                    accel = (
                        raw_accel.get("x", 0.0),
                        raw_accel.get("y", 0.0),
                        raw_accel.get("z", 0.0),
                    )
                    gyro = (
                        raw_gyro.get("x", 0.0) - self._gyro_offset[0],
                        raw_gyro.get("y", 0.0) - self._gyro_offset[1],
                        raw_gyro.get("z", 0.0) - self._gyro_offset[2],
                    )
                else:
                    time.sleep(interval)
                    continue

                with self._cache_lock:
                    self._cache["accel"] = accel
                    self._cache["gyro"] = gyro
                    self._temp_cache = temp

            except Exception as exc:
                logger.warning(f"IMU read error: {exc}")
                # Graceful: keep last known values

            elapsed = time.monotonic() - start
            sleep_for = max(0, interval - elapsed)
            if sleep_for > 0:
                time.sleep(sleep_for)

    # ── Calibration ──────────────────────────────────────────────

    def calibrate(self, samples: int = 100, delay: float = 0.01) -> bool:
        """Compute gyroscope offsets from *samples* readings at rest.

        The vehicle must be stationary during calibration.
        Returns True on success, False on failure.
        """
        if self._demo_mode:
            logger.info("IMU calibrate() — demo mode (offsets zeroed)")
            self._gyro_offset = (0.0, 0.0, 0.0)
            self._calibrated = True
            return True

        if self._sensor is None:
            logger.error("IMU calibrate() failed: sensor not initialized")
            return False

        logger.info(f"IMU calibrating from {samples} samples (keep vehicle still)…")

        gx_samples: list[float] = []
        gy_samples: list[float] = []
        gz_samples: list[float] = []

        for i in range(samples):
            try:
                gyro = self._sensor.get_gyro_data()
                gx_samples.append(gyro.get("x", 0.0))
                gy_samples.append(gyro.get("y", 0.0))
                gz_samples.append(gyro.get("z", 0.0))
            except Exception as exc:
                logger.warning(f"IMU calibration sample {i} failed: {exc}")
            time.sleep(delay)

        if len(gx_samples) < 10:
            logger.error("IMU calibrate() failed: insufficient samples")
            return False

        self._gyro_offset = (
            float(np.mean(gx_samples)),
            float(np.mean(gy_samples)),
            float(np.mean(gz_samples)),
        )
        self._calibrated = True

        logger.info(
            f"IMU calibration complete | gyro_offsets=("
            f"{self._gyro_offset[0]:.3f}, "
            f"{self._gyro_offset[1]:.3f}, "
            f"{self._gyro_offset[2]:.3f}) °/s"
        )
        return True

    # ── Demo Data Generation ─────────────────────────────────────

    def _demo_sample(self) -> Tuple[
        Tuple[float, float, float],
        Tuple[float, float, float],
        float,
    ]:
        """Generate a realistic simulated IMU sample."""
        t = self._demo_t
        self._demo_t += 1.0 / max(self._sample_rate, 1)

        # Gentle vibrations + gravity
        noise = 0.02  # g
        ax = self._DEMO_AX_BASE + noise * np.sin(t * 50) * random.uniform(0.5, 1.5)
        ay = self._DEMO_AY_BASE + noise * np.sin(t * 47) * random.uniform(0.5, 1.5)
        az = self._DEMO_AZ_BASE + noise * np.sin(t * 53) * random.uniform(0.5, 1.5)

        # Some rotational noise
        g_noise = 1.0  # °/s
        gx = self._DEMO_GX_BASE + g_noise * np.sin(t * 20) * random.uniform(0.5, 1.5)
        gy = self._DEMO_GY_BASE + g_noise * np.sin(t * 22) * random.uniform(0.5, 1.5)
        gz = self._DEMO_GZ_BASE + g_noise * np.sin(t * 18) * random.uniform(0.5, 1.5)

        temp = 28.0 + 2.0 * np.sin(t * 0.1)  # °C

        return (round(ax, 4), round(ay, 4), round(az, 4)), (
            round(gx, 2),
            round(gy, 2),
            round(gz, 2),
        ), round(temp, 1)

    # ── Public Data Methods ──────────────────────────────────────

    def _get_cached(self, key: str) -> Optional[Tuple[float, float, float]]:
        with self._cache_lock:
            return self._cache.get(key)

    def get_acceleration(self) -> Optional[Tuple[float, float, float]]:
        """Return (ax, ay, az) in g, or None if no data."""
        return self._get_cached("accel")

    def get_gyroscope(self) -> Optional[Tuple[float, float, float]]:
        """Return (gx, gy, gz) in °/s, or None if no data."""
        return self._get_cached("gyro")

    def get_temperature(self) -> Optional[float]:
        """Return IMU die temperature in °C."""
        if self._demo_mode:
            return self._temp_cache
        with self._cache_lock:
            return self._temp_cache

    def get_all(self) -> Dict[str, Any]:
        """Return dict with 'accel', 'gyro', 'temperature' keys."""
        with self._cache_lock:
            return {
                "accel": self._cache.get("accel"),
                "gyro": self._cache.get("gyro"),
                "temperature": self._temp_cache,
            }

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated
