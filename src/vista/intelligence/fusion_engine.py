"""
VISTA Fusion Engine — Extended Kalman Filter
=============================================
Fuses OBD-II vehicle speed with IMU accelerometer data using an
Extended Kalman Filter to produce an accurate, low-latency velocity
estimate with auto-calibrating sensor bias compensation.

State Vector
    x = [velocity (m/s), accel_bias_x (m/s^2), accel_bias_y (m/s^2)]

The filter predicts forward using the IMU's x-axis acceleration
(corrected for bias), then corrects using OBD speed as a direct
measurement and IMU raw readings as pseudo-measurements of bias
(when the vehicle is near steady-state, these are good bias estimates).

References
    - Welch & Bishop, "An Introduction to the Kalman Filter"
    - Kok et al., "Using Inertial Sensors for Position and Orientation"
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import yaml
from loguru import logger

# ── Constants ───────────────────────────────────────────────────
_G = 9.80665                # Standard gravity (m/s² per g)
_KPH_TO_MPS = 1.0 / 3.6     # km/h → m/s
_MPS_TO_KPH = 3.6           # m/s → km/h


class FusionEngine:
    """Extended Kalman Filter fusing OBD-II speed + IMU acceleration.

    Thread-safe.  Runs the filter update on every call to
    ``predict()`` / ``update()`` so external callers can drive
    the loop at whatever cadence their pipeline uses.

    Usage::

        fe = FusionEngine()
        fe.predict(imu_accel=(0.02, 0.00, 1.01))   # IMU in g
        fe.update(obd_speed=62.5, imu_ax=0.22)      # OBD km/h, IMU ax in m/s²
        v = fe.get_velocity()                        # km/h
        j = fe.get_jerk()                            # g/s
    """

    # ── Initialisation ───────────────────────────────────────────

    def __init__(self) -> None:
        cfg = self._load_config()
        fusion_cfg = cfg.get("fusion", {})

        # Time step (seconds)
        self._dt: float = float(fusion_cfg.get("dt", 0.1))

        # ── State vector ─────────────────────────────────────
        # x = [velocity (m/s), accel_bias_x (m/s²), accel_bias_y (m/s²)]
        self._x: np.ndarray = np.zeros((3, 1), dtype=np.float64)

        # ── Covariance matrix P ──────────────────────────────
        # Start with moderate uncertainty
        self._P: np.ndarray = np.eye(3, dtype=np.float64) * 0.5

        # ── Process noise Q (from config) ────────────────────
        process_noise = fusion_cfg.get("process_noise", [0.1, 0.01, 0.01])
        self._Q: np.ndarray = np.diag([
            float(process_noise[0]),
            float(process_noise[1]),
            float(process_noise[2]),
        ])

        # ── Measurement noise R (from config) ────────────────
        meas_noise = fusion_cfg.get("measurement_noise", [1.0, 0.5, 0.5])
        self._R: np.ndarray = np.diag([
            float(meas_noise[0]),
            float(meas_noise[1]),
            float(meas_noise[2]),
        ])

        # ── Identity for convenience ─────────────────────────
        self._I: np.ndarray = np.eye(3, dtype=np.float64)

        # ── State transition Jacobian F ──────────────────────
        # dx/dx = [[1, -dt, 0],
        #          [0,   1, 0],
        #          [0,   0, 1]]
        self._F: np.ndarray = np.array([
            [1.0, -self._dt, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)

        # ── Measurement Jacobian H (identity — direct readings)
        # z = [v_obd, a_x_imu, a_y_imu]
        self._H: np.ndarray = np.eye(3, dtype=np.float64)

        # ── Jerk tracking ────────────────────────────────────
        self._prev_accel: float = 0.0       # previous corrected ax (g)
        self._prev_accel_time: float = 0.0  # monotonic time of last accel
        self._jerk: float = 0.0             # g/s

        # Thread safety
        self._lock = threading.RLock()

        logger.info(
            f"FusionEngine initialized | dt={self._dt:.3f}s | "
            f"Q={process_noise} | R={meas_noise}"
        )

    # ── Config loader ────────────────────────────────────────────

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        """Resolve and load config.yaml relative to the vista package root."""
        package_root = Path(__file__).resolve().parent.parent
        config_path = package_root / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(
                f"config.yaml not found at {config_path}"
            )
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)  # type: ignore[no-any-return]

    # ── EKF Predict ──────────────────────────────────────────────

    def predict(self, imu_accel: Tuple[float, float, float]) -> None:
        """Predict the next state using IMU acceleration.

        Args:
            imu_accel: (ax, ay, az) in **g** (Earth gravity units).
        """
        ax_g, _ay, _az = imu_accel

        # Convert IMU ax from g → m/s²
        ax_mps2 = float(ax_g) * _G

        with self._lock:
            bias_x = float(self._x[1, 0])

            # Corrected forward acceleration (m/s² after removing bias)
            a_corrected = ax_mps2 - bias_x

            # ── State prediction ─────────────────────────────
            # v_k+1 = v_k + (a - bias) * dt
            # bias stays constant (modelled in noise)
            self._x[0, 0] += a_corrected * self._dt

            # ── Covariance prediction ────────────────────────
            self._P = self._F @ self._P @ self._F.T + self._Q

            # ── Update jerk estimate ─────────────────────────
            now = self._monotonic_time()
            ax_corrected_g = a_corrected / _G
            if self._prev_accel_time > 0:
                dt_jerk = now - self._prev_accel_time
                # Fall back to config dt if calls are very close
                if dt_jerk < 1e-6:
                    dt_jerk = self._dt
                self._jerk = (ax_corrected_g - self._prev_accel) / dt_jerk
            self._prev_accel = ax_corrected_g
            self._prev_accel_time = now

    # ── EKF Update ───────────────────────────────────────────────

    def update(self, obd_speed: Optional[float], imu_ax: Optional[float]) -> None:
        """Correct the filter state using OBD speed and IMU readings.

        Args:
            obd_speed: Vehicle speed in **km/h** from OBD-II (may be None).
            imu_ax:   IMU x-axis raw acceleration in **m/s²** (may be None).
                      Used as a pseudo-measurement of accel_bias_x
                      (valid at near-steady-state).

        When a sensor value is ``None`` (unavailable), that row of
        the measurement update is skipped.
        """
        with self._lock:
            # Build measurement vector z (3×1) and valid flag
            z = np.zeros((3, 1), dtype=np.float64)
            valid = np.array([True, True, True], dtype=bool)

            if obd_speed is not None:
                z[0, 0] = float(obd_speed) * _KPH_TO_MPS  # km/h → m/s
            else:
                valid[0] = False

            if imu_ax is not None:
                z[1, 0] = float(imu_ax)
            else:
                valid[1] = False

            # a_y measurement (bias pseudo-measurement)
            # We use 0.0 as the expected lateral acceleration
            # (valid when the vehicle is not cornering hard).
            # Always "valid" but with high noise in R.
            z[2, 0] = 0.0

            # ── For each valid measurement row, do a sequential update ─
            for i in range(3):
                if not valid[i]:
                    continue

                h_i = self._H[i:i + 1, :]          # 1×3
                r_i = self._R[i, i]                 # scalar

                # Innovation (measurement residual)
                y_residual = z[i, 0] - float(h_i @ self._x)

                # Innovation covariance
                S = float(h_i @ self._P @ h_i.T) + r_i
                if S < 1e-12:
                    continue  # numerical guard

                # Kalman gain
                K = self._P @ h_i.T / S             # 3×1

                # State correction
                self._x += K * y_residual

                # Covariance correction (Joseph-form for stability)
                I_KH = self._I - K @ h_i
                self._P = I_KH @ self._P @ I_KH.T + K * r_i * K.T

            # Clamp velocity to sane range [0, 300] km/h
            v_mps = float(self._x[0, 0])
            v_mps = max(0.0, min(v_mps, 300.0 * _KPH_TO_MPS))
            self._x[0, 0] = v_mps

    # ── Public Accessors ─────────────────────────────────────────

    def get_velocity(self) -> float:
        """Return the fused velocity estimate in **km/h**."""
        with self._lock:
            return float(self._x[0, 0]) * _MPS_TO_KPH

    def get_jerk(self) -> float:
        """Return the latest jerk estimate in **g/s**."""
        with self._lock:
            return float(self._jerk)

    def get_state(self) -> Dict[str, float]:
        """Return the full filter state as a dictionary.

        Keys: ``velocity_kmh``, ``bias_x_mps2``, ``bias_y_mps2``.
        """
        with self._lock:
            return {
                "velocity_kmh": float(self._x[0, 0]) * _MPS_TO_KPH,
                "bias_x_mps2": float(self._x[1, 0]),
                "bias_y_mps2": float(self._x[2, 0]),
            }

    def get_covariance(self) -> np.ndarray:
        """Return a copy of the current 3×3 covariance matrix."""
        with self._lock:
            return self._P.copy()

    def reset(self) -> None:
        """Reset the filter to its initial state (e.g., on vehicle restart)."""
        with self._lock:
            self._x.fill(0.0)
            self._P = np.eye(3, dtype=np.float64) * 0.5
            self._jerk = 0.0
            self._prev_accel = 0.0
            self._prev_accel_time = 0.0
            logger.info("FusionEngine reset to initial state")

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _monotonic_time() -> float:
        """Return a high-resolution monotonic timestamp (seconds)."""
        import time
        return time.monotonic()
