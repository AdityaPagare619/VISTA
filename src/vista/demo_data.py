"""
VISTA v3.0 — Realistic Sensor Data Generator
==============================================
Generates physically plausible sensor traces for demo scenarios.
Every value follows real physics — no random noise pretending to be data.

IMU Physics:
    - Normal driving on good road: 1.0-1.2g (gravity + vibration)
    - Pothole: 3-5g spike for 20-40ms, symmetric rise/fall
    - Crash:   8-16g sustained for 50-200ms, asymmetric (fast rise, slow decay)
    - Speed bump: 2-3g, 30-50ms, symmetric

OBD Physics:
    - ELM327 updates every 0.5s (honest rate from config)
    - Speed follows F=ma with realistic acceleration (0.3g max for normal car)
    - Throttle correlates with acceleration (not random)

Audio:
    - Silence: zeros
    - Normal driving: low-frequency rumble (engine + road noise)
    - Horn: 400Hz + 500Hz harmonics
    - Crash impact: broadband burst with exponential decay
"""

import math
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class SensorFrame:
    """One frame of simulated sensor data at a specific time."""
    time_s: float
    # OBD
    obd_speed_kmh: float = 0.0
    obd_rpm: float = 800.0
    obd_throttle_pct: float = 0.0
    # IMU
    imu_accel_magnitude_g: float = 1.0  # includes gravity
    imu_jerk_gs: float = 0.0
    # Audio (16kHz waveform for YAMNet, 0.975s = 15600 samples)
    audio_waveform: np.ndarray = field(default_factory=lambda: np.zeros(15600, dtype=np.float32))
    # Metadata
    event: str = "normal"  # normal, pothole, crash, post_crash
    event_detail: str = ""


def _engine_rumble(duration_samples: int, speed_kmh: float) -> np.ndarray:
    """Generate engine + road noise proportional to speed."""
    sr = 16000
    t = np.arange(duration_samples) / sr
    # Engine fundamental ~80-120Hz depending on RPM
    rpm_freq = 40 + speed_kmh * 0.8  # rough mapping
    rumble = np.sin(2 * np.pi * rpm_freq * t) * 0.05
    # Road noise (broadband, low amplitude)
    road = np.random.randn(duration_samples).astype(np.float32) * 0.02 * (speed_kmh / 60)
    # Tire whine ~800Hz
    tire = np.sin(2 * np.pi * 800 * t) * 0.01 * (speed_kmh / 60)
    return (rumble + road + tire).astype(np.float32)


def _crash_audio(duration_samples: int) -> np.ndarray:
    """Generate crash impact audio: broadband burst with exponential decay."""
    sr = 16000
    t = np.arange(duration_samples) / sr
    # Impact: broadband noise burst
    burst = np.random.randn(duration_samples).astype(np.float32)
    # Sharp attack, slow decay envelope
    envelope = np.exp(-t * 8) * (1 - np.exp(-t * 200))
    # Metal crunch: multiple resonant frequencies
    metal1 = np.sin(2 * np.pi * 1200 * t) * 0.3
    metal2 = np.sin(2 * np.pi * 2400 * t + 0.5) * 0.2
    glass = np.sin(2 * np.pi * 5000 * t) * np.exp(-t * 15) * 0.15
    signal = (burst * 0.4 + metal1 + metal2 + glass) * envelope * 0.8
    return np.clip(signal, -1.0, 1.0).astype(np.float32)


def _horn_audio(duration_samples: int) -> np.ndarray:
    """Generate car horn: dual-tone."""
    sr = 16000
    t = np.arange(duration_samples) / sr
    tone1 = np.sin(2 * np.pi * 400 * t) * 0.4
    tone2 = np.sin(2 * np.pi * 500 * t) * 0.3
    return (tone1 + tone2).astype(np.float32)


def generate_crash_scenario(
    duration_s: float = 60.0,
    dt: float = 0.1,  # 10 Hz frame rate
    cruise_speed: float = 55.0,
    pothole_time: float = 35.0,
    crash_time: float = 47.0,
) -> List[SensorFrame]:
    """Generate a complete crash scenario with realistic physics.

    Timeline:
        0-15s:  Cruise at cruise_speed
        15-22s: Accelerate to cruise_speed + 15 (overtaking)
        22-33s: Steady highway speed
        33-36s: POTHOLE — brief symmetric IMU spike, no speed change
        36-45s: Resume normal
        45-48s: CRASH — sustained asymmetric IMU, speed drops to 0
        48-60s: Post-crash silence
    """
    frames: List[SensorFrame] = []
    n_steps = int(duration_s / dt)

    # State
    speed = 0.0
    rpm = 800.0
    throttle = 0.0
    prev_imu = 1.0

    for i in range(n_steps):
        t = i * dt
        frame = SensorFrame(time_s=round(t, 2))

        # ── Speed profile (physics-based) ──────────────────────────
        if t < 5:
            # Startup: accelerate from 0 to cruise
            target_speed = cruise_speed * (t / 5.0)
            throttle = 40.0
        elif t < 15:
            target_speed = cruise_speed
            throttle = 15.0
        elif t < 22:
            # Overtaking acceleration
            progress = (t - 15) / 7.0
            target_speed = cruise_speed + 15.0 * progress
            throttle = 35.0
        elif t < 33:
            target_speed = cruise_speed + 15.0
            throttle = 18.0
        elif t < 36:
            # Pothole zone — speed unchanged
            target_speed = cruise_speed + 15.0
            throttle = 18.0
        elif t < 45:
            target_speed = cruise_speed + 10.0
            throttle = 15.0
        elif t < crash_time:
            # Pre-crash: still driving
            target_speed = cruise_speed + 10.0
            throttle = 15.0
        elif t < crash_time + 0.5:
            # Crash impact: throttle drops instantly
            target_speed = cruise_speed * 0.3
            throttle = 0.0
        elif t < crash_time + 2.0:
            # Post-crash deceleration
            target_speed = max(0, speed - 20 * dt)
            throttle = 0.0
        else:
            target_speed = 0.0
            throttle = 0.0

        # Smooth speed tracking (like real car with inertia)
        speed_diff = target_speed - speed
        max_accel = 8.0 if abs(speed_diff) > 20 else 3.0  # m/s^2 → km/h/s
        speed += np.clip(speed_diff, -max_accel * dt * 10, max_accel * dt * 10)
        speed = max(0, speed)

        # RPM tracks speed roughly
        if speed > 0:
            rpm = 800 + speed * 30  # ~2500 at 55 km/h
        else:
            rpm = 0 if t > crash_time + 3 else 800

        frame.obd_speed_kmh = round(speed, 1)
        frame.obd_rpm = round(rpm)
        frame.obd_throttle_pct = round(throttle, 1)

        # ── IMU profile ────────────────────────────────────────────
        # Base: 1g gravity + road vibration proportional to speed
        base_g = 1.0 + 0.05 * math.sin(t * 20) * (speed / 60)

        if pothole_time <= t < pothole_time + 0.15:
            # POTHOLE: symmetric spike, brief (150ms)
            progress = (t - pothole_time) / 0.15
            if progress < 0.5:
                # Rising
                imu_g = base_g + 4.0 * (progress / 0.5)
            else:
                # Falling (symmetric)
                imu_g = base_g + 4.0 * (1 - (progress - 0.5) / 0.5)
            frame.event = "pothole"
            frame.event_detail = f"symmetric spike {imu_g:.1f}g"

        elif crash_time <= t < crash_time + 0.05:
            # CRASH phase 1: fast onset (50ms)
            progress = (t - crash_time) / 0.05
            imu_g = base_g + 14.0 * progress
            frame.event = "crash"
            frame.event_detail = "onset"

        elif crash_time + 0.05 <= t < crash_time + 0.25:
            # CRASH phase 2: sustained saturation (200ms)
            imu_g = 15.5 + 0.5 * math.sin(t * 100)  # Near ±16g saturation
            frame.event = "crash"
            frame.event_detail = "sustained saturation"

        elif crash_time + 0.25 <= t < crash_time + 0.8:
            # CRASH phase 3: slow asymmetric decay (550ms)
            decay_progress = (t - crash_time - 0.25) / 0.55
            imu_g = 15.5 * (1 - decay_progress) ** 2 + base_g
            frame.event = "crash"
            frame.event_detail = "decay"

        elif t > crash_time + 0.8:
            imu_g = 1.0
            frame.event = "post_crash"
        else:
            imu_g = base_g
            frame.event = "normal"

        frame.imu_accel_magnitude_g = round(imu_g, 2)
        frame.imu_jerk_gs = round(abs(imu_g - prev_imu) / dt, 2)
        prev_imu = imu_g

        # ── Audio waveform (15600 samples = 0.975s at 16kHz) ──────
        if frame.event == "crash" and "saturation" in frame.event_detail:
            frame.audio_waveform = _crash_audio(15600)
        elif frame.event == "crash" and "onset" in frame.event_detail:
            frame.audio_waveform = _crash_audio(15600) * 0.5
        elif frame.event == "pothole":
            # Pothole: thump sound (low frequency, brief)
            thump = np.zeros(15600, dtype=np.float32)
            t_arr = np.arange(2000) / 16000
            thump[6000:8000] = np.sin(2 * np.pi * 100 * t_arr) * np.exp(-t_arr * 30) * 0.3
            thump += _engine_rumble(15600, speed) * 0.5
            frame.audio_waveform = thump
        elif speed > 5:
            frame.audio_waveform = _engine_rumble(15600, speed)
        else:
            frame.audio_waveform = np.zeros(15600, dtype=np.float32)

        frames.append(frame)

    return frames


def generate_normal_scenario(duration_s: float = 30.0, dt: float = 0.1) -> List[SensorFrame]:
    """Generate a normal driving scenario (no events). For baseline comparison."""
    frames = []
    speed = 45.0
    for i in range(int(duration_s / dt)):
        t = i * dt
        frame = SensorFrame(
            time_s=round(t, 2),
            obd_speed_kmh=round(speed + 5 * math.sin(t * 0.5), 1),
            obd_rpm=round(2000 + 300 * math.sin(t * 0.5)),
            obd_throttle_pct=round(20 + 5 * math.sin(t * 0.3), 1),
            imu_accel_magnitude_g=round(1.0 + 0.05 * math.sin(t * 15), 2),
            imu_jerk_gs=round(abs(0.05 * 15 * math.cos(t * 15) * 0.1), 2),
            event="normal",
        )
        frame.audio_waveform = _engine_rumble(15600, frame.obd_speed_kmh)
        frames.append(frame)
    return frames


def generate_dropout_scenario(duration_s: float = 40.0, dt: float = 0.1) -> List[SensorFrame]:
    """OBD sensor dropout scenario — tests EKF resilience.

    Timeline:
        0-10s:  Normal cruising at 50 km/h (OBD healthy)
        10-20s: OBD DISCONNECTS (speed reads 0, EKF must hold from IMU)
        20-25s: OBD reconnects
        25-28s: CRASH during normal operation
        28-40s: Post-crash

    This tests:
        - EKF holding velocity when OBD drops out
        - CrashDetector working in degraded mode (no OBD corroboration)
        - System recovery when OBD reconnects
    """
    frames: List[SensorFrame] = []
    speed = 0.0
    prev_imu = 1.0
    obd_connected = True

    for i in range(int(duration_s / dt)):
        t = round(i * dt, 2)
        frame = SensorFrame(time_s=t)

        # Speed profile
        if t < 5:
            speed = 50.0 * (t / 5.0)
            throttle = 35.0
        elif t < 10:
            speed = 50.0
            throttle = 15.0
        elif t < 20:
            # OBD disconnected — speed still 50 km/h physically
            obd_connected = False
            speed = 50.0
            throttle = 15.0
        elif t < 25:
            obd_connected = True
            speed = 50.0
            throttle = 15.0
        elif t < 25.5:
            speed = max(0, 50.0 - 80 * (t - 25))
            throttle = 0.0
        elif t < 27:
            speed = max(0, speed - 15 * dt)
            throttle = 0.0
        else:
            speed = 0.0
            throttle = 0.0

        # OBD output: 0 when disconnected
        frame.obd_speed_kmh = round(speed, 1) if obd_connected else 0.0
        frame.obd_rpm = round(800 + speed * 30) if obd_connected else 0.0
        frame.obd_throttle_pct = round(throttle, 1) if obd_connected else 0.0

        # IMU (always works — it's wired to Pi directly)
        base_g = 1.0 + 0.03 * math.sin(t * 20) * (speed / 50)
        crash_time = 25.0

        if crash_time <= t < crash_time + 0.05:
            imu_g = base_g + 14.0 * ((t - crash_time) / 0.05)
            frame.event = "crash"
            frame.event_detail = "onset"
        elif crash_time + 0.05 <= t < crash_time + 0.25:
            imu_g = 15.5 + 0.5 * math.sin(t * 80)
            frame.event = "crash"
            frame.event_detail = "sustained saturation"
        elif crash_time + 0.25 <= t < crash_time + 0.8:
            decay = (t - crash_time - 0.25) / 0.55
            imu_g = 15.5 * (1 - decay) ** 2 + base_g
            frame.event = "crash"
            frame.event_detail = "decay"
        elif t > crash_time + 0.8:
            imu_g = 1.0
            frame.event = "post_crash"
        elif not obd_connected:
            imu_g = base_g
            frame.event = "obd_dropout"
            frame.event_detail = "OBD disconnected"
        else:
            imu_g = base_g
            frame.event = "normal"

        frame.imu_accel_magnitude_g = round(imu_g, 2)
        frame.imu_jerk_gs = round(abs(imu_g - prev_imu) / dt, 2)
        prev_imu = imu_g

        # Audio
        if "saturation" in frame.event_detail:
            frame.audio_waveform = _crash_audio(15600)
        elif speed > 5:
            frame.audio_waveform = _engine_rumble(15600, speed)
        else:
            frame.audio_waveform = np.zeros(15600, dtype=np.float32)

        frames.append(frame)

    return frames


def generate_chaos_scenario(duration_s: float = 30.0, dt: float = 0.1) -> List[SensorFrame]:
    """Indian road chaos — tests false positive rejection.

    Timeline:
        0-5s:   Cruise at 40 km/h
        5-6s:   POTHOLE #1 (3g spike)
        7-8s:   Speed bump (2.5g)
        9-10s:  POTHOLE #2 (4g spike)
        11-12s: Horn blast (audio)
        13-14s: Hard braking (3g sustained 0.5s but NOT a crash)
        15-25s: Normal driving
        25-30s: Normal stop at traffic light

    EVERY event must be rejected as non-crash. Zero false positives
    is the requirement for Indian road deployment.
    """
    frames: List[SensorFrame] = []
    speed = 40.0
    prev_imu = 1.0

    for i in range(int(duration_s / dt)):
        t = round(i * dt, 2)
        frame = SensorFrame(time_s=t)

        # Speed
        if t < 5:
            speed = 40.0
            throttle = 15.0
        elif t < 13:
            speed = 40.0
            throttle = 15.0
        elif 13 <= t < 14:
            # Hard braking
            speed = max(15, 40 - 25 * (t - 13))
            throttle = 0.0
        elif t < 15:
            speed = 15.0
            throttle = 10.0
        elif t < 25:
            speed = 40.0
            throttle = 15.0
        else:
            # Stopping at light
            speed = max(0, 40 - 20 * (t - 25))
            throttle = 0.0

        frame.obd_speed_kmh = round(speed, 1)
        frame.obd_rpm = round(800 + speed * 30)
        frame.obd_throttle_pct = round(throttle, 1)

        # IMU with multiple events
        base_g = 1.0 + 0.03 * math.sin(t * 15)

        if 5.0 <= t < 5.15:
            # Pothole 1: symmetric
            p = (t - 5.0) / 0.15
            imu_g = base_g + 3.0 * (1 - abs(2 * p - 1))
            frame.event = "pothole"
        elif 7.0 <= t < 7.15:
            # Speed bump: gentle
            p = (t - 7.0) / 0.15
            imu_g = base_g + 2.0 * (1 - abs(2 * p - 1))
            frame.event = "speed_bump"
        elif 9.0 <= t < 9.15:
            # Pothole 2: slightly stronger
            p = (t - 9.0) / 0.15
            imu_g = base_g + 4.0 * (1 - abs(2 * p - 1))
            frame.event = "pothole"
        elif 13.0 <= t < 13.5:
            # Hard braking: sustained ~3g but symmetric and moderate
            imu_g = 3.0 + 0.3 * math.sin(t * 30)
            frame.event = "hard_braking"
        else:
            imu_g = base_g
            frame.event = "normal"

        frame.imu_accel_magnitude_g = round(imu_g, 2)
        frame.imu_jerk_gs = round(abs(imu_g - prev_imu) / dt, 2)
        prev_imu = imu_g

        # Audio
        if 11.0 <= t < 12.0:
            frame.audio_waveform = _horn_audio(15600)
            frame.event = "horn"
        elif speed > 5:
            frame.audio_waveform = _engine_rumble(15600, speed)
        else:
            frame.audio_waveform = np.zeros(15600, dtype=np.float32)

        frames.append(frame)

    return frames


# Scenario registry for demo_live.py
SCENARIOS = {
    "crash": generate_crash_scenario,
    "normal": generate_normal_scenario,
    "dropout": generate_dropout_scenario,
    "chaos": generate_chaos_scenario,
}
