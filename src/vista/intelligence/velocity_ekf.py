"""
VISTA Velocity EKF — 2-State Extended Kalman Filter (v3.0)
===========================================================
Fuses OBD-II vehicle speed with IMU forward acceleration to produce
an accurate, low-latency velocity estimate with accel bias compensation.

**v3.0 Changes from v2.1:**
    - State vector: 3-state [v, bias_x, bias_y] → 2-state [v, bias]
    - bias_y was dimensionally broken (lateral bias observing 0 = nonsense)
    - dt: 0.1 → 0.4 (matches real ELM327 OBD polling rate of ~2.5Hz)
    - R: 1.0 → 0.08 (properly computed: (1 km/h / 3.6)² ≈ 0.08)

**NOT used for crash detection** — crashes are discontinuities that
violate EKF smoothness assumptions. See crash_detector.py instead.

State Vector:
    x = [velocity (m/s), accel_bias (m/s²)]

Prediction:
    v_{k+1} = v_k + (imu_accel_forward * 9.81 - bias) * dt
    bias_{k+1} = bias_k  (random walk)

Measurement:
    z = OBD speed (converted km/h → m/s)

References:
    - Welch & Bishop, "An Introduction to the Kalman Filter"
    - Kok et al., "Using Inertial Sensors for Position and Orientation"
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import yaml
from loguru import logger

# ── Constants ───────────────────────────────────────────────────
_G = 9.80665            # Standard gravity (m/s² per g)
_KPH_TO_MPS = 1.0 / 3.6
_MPS_TO_KPH = 3.6


class VelocityEKF:
    """2-State Extended Kalman Filter for velocity estimation ONLY.

    Fuses OBD-II speed and IMU acceleration for accurate velocity.
    Used for: driver behavior analysis, trip logging, speed profiles.
    NOT used for: crash detection (separate module).

    Thread-safe. Runs the filter update on every call to
    ``predict()`` / ``update()`` so external callers can drive
    the loop at whatever cadence their pipeline uses.

    Usage::

        ekf = VelocityEKF()
        ekf.predict(0.05)           # IMU forward accel in g
        ekf.update(62.5)            # OBD speed in km/h
        v = ekf.get_velocity_kmh()  # Fused velocity
    """

    # ── Initialisation ───────────────────────────────────────────

    def __init__(self) -> None:
        cfg = self._load_config()
        ekf_cfg = cfg.get("velocity_ekf", cfg.get("fusion", {}))

        # Time step (seconds) — matches real OBD polling rate
        self._dt: float = float(ekf_cfg.get("dt", 0.4))

        # ── State vector: [velocity (m/s), accel_bias (m/s²)] ────
        self._x: np.ndarray = np.zeros(2, dtype=np.float64)

        # ── Covariance matrix P (2×2) ────────────────────────────
        self._P: np.ndarray = np.eye(2, dtype=np.float64) * 1.0

        # ── Process noise Q (from config) ────────────────────────
        process_noise = ekf_cfg.get("process_noise", [0.5, 0.01])
        self._Q: np.ndarray = np.diag([
            float(process_noise[0]),
            float(process_noise[1]),
        ])

        # ── Measurement noise R (from config) ────────────────────
        meas_noise = ekf_cfg.get("measurement_noise", [0.08])
        self._R: np.ndarray = np.array([[float(meas_noise[0])]])

        # Thread safety
        self._lock = threading.RLock()

        logger.info(
            f"VelocityEKF initialized | dt={self._dt:.3f}s | "
            f"Q=diag({process_noise}) | R=diag({meas_noise}) | "
            f"state_dim=2 (v3.0 corrected)"
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
            return yaml.safe_load(f)

    # ── EKF Predict ──────────────────────────────────────────────

    def predict(self, imu_accel_forward_g: float) -> None:
        """Prediction step using forward-axis IMU acceleration.

        Args:
            imu_accel_forward_g: Forward acceleration in g-units.
                Positive = accelerating forward.
                Negative = braking / decelerating.
        """
        with self._lock:
            # Convert IMU reading from g → m/s²
            accel_mps2 = float(imu_accel_forward_g) * _G

            # Remove estimated bias
            corrected_accel = accel_mps2 - self._x[1]

            # State transition: v += (a - bias) * dt
            self._x[0] += corrected_accel * self._dt
            # Bias stays constant (modeled as random walk in Q)

            # Jacobian of state transition (2×2)
            F = np.array([
                [1.0, -self._dt],   # dv/dv = 1, dv/dbias = -dt
                [0.0,  1.0],        # dbias is constant
            ])

            # Covariance prediction
            self._P = F @ self._P @ F.T + self._Q

    # ── EKF Update ───────────────────────────────────────────────

    def update(self, obd_speed_kmh: float) -> None:
        """Update step using OBD-II speed measurement.

        Args:
            obd_speed_kmh: Vehicle speed from OBD-II in km/h.
        """
        with self._lock:
            # Convert measurement to m/s
            obd_speed_mps = float(obd_speed_kmh) * _KPH_TO_MPS
            z = np.array([obd_speed_mps])

            # Observation matrix: we observe velocity directly
            H = np.array([[1.0, 0.0]])

            # Innovation (measurement residual)
            y = z - H @ self._x

            # Innovation covariance
            S = H @ self._P @ H.T + self._R

            # Kalman gain
            K = self._P @ H.T @ np.linalg.inv(S)

            # State correction
            self._x += (K @ y).flatten()

            # Covariance correction (Joseph form for numerical stability)
            I_KH = np.eye(2) - K @ H
            self._P = I_KH @ self._P @ I_KH.T + K @ self._R @ K.T

            # Clamp velocity to sane range [0, 300 km/h]
            self._x[0] = max(0.0, min(self._x[0], 300.0 * _KPH_TO_MPS))

    # ── Public Accessors ─────────────────────────────────────────

    def get_velocity_kmh(self) -> float:
        """Return the fused velocity estimate in km/h."""
        with self._lock:
            return max(0.0, float(self._x[0]) * _MPS_TO_KPH)

    def get_velocity_mps(self) -> float:
        """Return the fused velocity estimate in m/s."""
        with self._lock:
            return max(0.0, float(self._x[0]))

    def get_state(self) -> Dict[str, float]:
        """Return the full 2-state filter state as a dictionary."""
        with self._lock:
            return {
                "velocity_kmh": float(self._x[0]) * _MPS_TO_KPH,
                "velocity_mps": float(self._x[0]),
                "accel_bias_mps2": float(self._x[1]),
            }

    def get_covariance(self) -> np.ndarray:
        """Return a copy of the current 2×2 covariance matrix."""
        with self._lock:
            return self._P.copy()

    def reset(self) -> None:
        """Reset the filter to its initial state (e.g., on vehicle restart)."""
        with self._lock:
            self._x.fill(0.0)
            self._P = np.eye(2, dtype=np.float64) * 1.0
            logger.info("VelocityEKF reset to initial state")


# ── Backward compatibility alias ─────────────────────────────────
# Code that imported FusionEngine can still work during transition.
FusionEngine = VelocityEKF
