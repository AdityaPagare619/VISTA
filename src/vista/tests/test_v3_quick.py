"""
VISTA v3.0 — Edge Case Verification Suite
==========================================
These tests prove the things that COULD go wrong in production.
Not import checks — logic validation against real-world scenarios.

Target: Raspberry Pi (Linux/ARM). Runs on dev machine too.
"""
import sys
import time
import math

sys.path.insert(0, ".")

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  ({detail})")


# ================================================================
# 1. CRASH DETECTOR: Pothole vs Crash discrimination
# ================================================================
print("\n=== CRASH DETECTOR: Pothole vs Crash ===")

from intelligence.crash_detector import CrashDetector, CrashEvidence

cd = CrashDetector()

# --- Scenario A: POTHOLE (brief symmetric spike, should NOT trigger crash) ---
# Simulate 50 normal readings, then a 10g spike for 2 samples (20ms), then normal
for _ in range(50):
    cd.check_imu(1.0, 0.01)  # Normal driving at 1g

# Pothole: sharp up, sharp down (symmetric)
cd.check_imu(8.0, 0.01)   # Spike up
cd.check_imu(10.0, 0.01)  # Peak
cd.check_imu(8.0, 0.01)   # Spike down (symmetric!)
cd.check_imu(1.5, 0.01)   # Back to normal fast

pothole_ev = CrashEvidence(
    imu_jerk=9.0,  # High jerk
    imu_saturated=False,
    audio_class="normal",  # No crash sound
    audio_confidence=0.0,
)
pothole_result = cd.assess(pothole_ev)

check(
    "Pothole NOT classified as crash",
    not pothole_result["is_crash"],
    f"conf={pothole_result['confidence']:.3f} (should be <0.65)"
)
check(
    "Pothole confidence is LOW despite high jerk",
    pothole_result["confidence"] < 0.5,
    f"conf={pothole_result['confidence']:.3f}"
)

# --- Scenario B: REAL CRASH (sustained asymmetric, SHOULD trigger) ---
cd2 = CrashDetector()

# Normal driving
for _ in range(50):
    cd2.check_imu(1.0, 0.01)

# Crash: fast onset, SUSTAINED high-g, slow decay
cd2.check_imu(3.0, 0.01)   # Rising
cd2.check_imu(8.0, 0.01)   # Rising fast
cd2.check_imu(14.0, 0.01)  # Near peak
cd2.check_imu(15.5, 0.01)  # SATURATED
cd2.check_imu(15.5, 0.01)  # Sustained
cd2.check_imu(15.5, 0.01)  # Sustained
cd2.check_imu(15.5, 0.01)  # Sustained (80ms at saturation)
cd2.check_imu(15.5, 0.01)  # Sustained
cd2.check_imu(15.5, 0.01)  # Sustained
cd2.check_imu(12.0, 0.01)  # Slow decay begins
cd2.check_imu(9.0, 0.01)   # Decaying
cd2.check_imu(6.0, 0.01)   # Still high
cd2.check_imu(4.0, 0.01)   # Decaying slowly
cd2.check_imu(2.5, 0.01)   # Decaying
cd2.check_imu(1.5, 0.01)   # Near normal

crash_ev = CrashEvidence(
    imu_jerk=12.0,
    imu_saturated=True,  # MPU6050 clipped
    audio_class="crash",
    audio_confidence=0.92,
    obd_speed_drop=45,
    obd_throttle_drop=90,
)
crash_result = cd2.assess(crash_ev)

check(
    "Real crash IS detected",
    crash_result["is_crash"],
    f"conf={crash_result['confidence']:.3f}"
)
check(
    "Crash confidence is HIGH",
    crash_result["confidence"] >= 0.65,
    f"conf={crash_result['confidence']:.3f}"
)
check(
    "Crash severity is critical",
    crash_result["severity"] == "critical",
    f"severity={crash_result['severity']}"
)

# --- Scenario C: Speed bump at 20 km/h (should NOT trigger) ---
cd3 = CrashDetector()
for _ in range(50):
    cd3.check_imu(1.0, 0.01)

# Speed bump: moderate, brief, symmetric
cd3.check_imu(2.0, 0.01)
cd3.check_imu(3.5, 0.01)
cd3.check_imu(2.0, 0.01)
cd3.check_imu(1.0, 0.01)

bump_ev = CrashEvidence(
    imu_jerk=2.5,
    imu_saturated=False,
    audio_class="normal",
    audio_confidence=0.1,
)
bump_result = cd3.assess(bump_ev)

check(
    "Speed bump NOT classified as crash",
    not bump_result["is_crash"],
    f"conf={bump_result['confidence']:.3f}"
)

# ================================================================
# 2. VELOCITY EKF: Convergence and sanity
# ================================================================
print("\n=== VELOCITY EKF: Convergence ===")

from intelligence.velocity_ekf import VelocityEKF

ekf = VelocityEKF()

# Simulate: vehicle cruising at 60 km/h, IMU reads ~0g forward (constant speed)
for i in range(20):
    ekf.predict(0.0)    # No acceleration
    ekf.update(60.0)    # OBD says 60 km/h

v = ekf.get_velocity_kmh()
check(
    "EKF converges to 60 km/h with constant OBD",
    55 < v < 65,
    f"got {v:.2f}"
)

# Now simulate hard braking: IMU shows -0.5g, OBD drops to 20 km/h
for i in range(10):
    ekf.predict(-0.5)   # Braking at -0.5g
    ekf.update(20.0)    # OBD confirms deceleration

v_brake = ekf.get_velocity_kmh()
check(
    "EKF tracks hard braking (velocity drops)",
    v_brake < 35,
    f"got {v_brake:.2f}"
)

# Edge case: what if OBD drops out? EKF should still predict from IMU alone
ekf2 = VelocityEKF()
for _ in range(10):
    ekf2.predict(0.0)
    ekf2.update(50.0)

# Now OBD disconnects, only IMU predict (no update)
for _ in range(5):
    ekf2.predict(0.0)  # Constant speed, no OBD

v_no_obd = ekf2.get_velocity_kmh()
check(
    "EKF holds velocity when OBD disconnects",
    40 < v_no_obd < 60,
    f"got {v_no_obd:.2f} (should drift slightly)"
)

# Edge case: velocity should never go negative
ekf3 = VelocityEKF()
ekf3.predict(-2.0)  # Extreme braking
ekf3.update(0.0)
v_neg = ekf3.get_velocity_kmh()
check(
    "EKF velocity never goes negative",
    v_neg >= 0.0,
    f"got {v_neg:.2f}"
)

# ================================================================
# 3. CRASH DETECTOR: Weight redistribution
# ================================================================
print("\n=== CRASH DETECTOR: Degraded mode ===")

cd4 = CrashDetector()

# Only IMU available (audio mic broken, no OBD, no WiFi)
imu_only_weights = cd4.get_weights_for_sensors({"imu"})
check(
    "IMU-only weight sums to 1.0",
    abs(sum(imu_only_weights.values()) - 1.0) < 0.01,
    f"sum={sum(imu_only_weights.values()):.3f}"
)
check(
    "IMU-only: IMU gets full weight",
    imu_only_weights.get("imu", 0) > 0.9,
    f"imu_weight={imu_only_weights.get('imu', 0):.3f}"
)

# IMU + Audio only (OBD and Vision unavailable)
imu_audio_weights = cd4.get_weights_for_sensors({"imu", "audio"})
check(
    "IMU+Audio weights sum to 1.0",
    abs(sum(imu_audio_weights.values()) - 1.0) < 0.01,
    f"sum={sum(imu_audio_weights.values()):.3f}"
)

# ================================================================
# 4. CONFIG: Critical values are physics-honest
# ================================================================
print("\n=== CONFIG: Physics constraints ===")

import yaml
with open("config.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

obd_rate = cfg["sensors"]["obd"]["poll_interval"]
check(
    "OBD rate is honest (>= 0.3s)",
    obd_rate >= 0.3,
    f"poll_interval={obd_rate}s (ELM327 can't do faster)"
)

imu_range = cfg["sensors"]["imu"]["accel_range"]
check(
    "IMU range is maximum (16g)",
    imu_range == 16,
    f"accel_range={imu_range}"
)

ekf_states = len(cfg["velocity_ekf"]["process_noise"])
check(
    "EKF is 2-state (not broken 3-state)",
    ekf_states == 2,
    f"process_noise has {ekf_states} elements"
)

imu_weight = cfg["crash_detection"]["sensor_weights"]["imu"]
check(
    "IMU has highest crash weight (primary sensor)",
    imu_weight >= 0.4,
    f"imu_weight={imu_weight}"
)

disclaimer = cfg.get("system", {}).get("safety_disclaimer", "")
check(
    "Safety disclaimer exists",
    len(disclaimer) > 10,
    "missing or too short"
)

ssd_mount = cfg.get("storage", {}).get("data_mount", "")
check(
    "Storage targets USB SSD, not SD card",
    "mnt" in ssd_mount or "ssd" in ssd_mount.lower() or "usb" in ssd_mount.lower(),
    f"data_mount={ssd_mount}"
)

# ================================================================
# 5. POWER MANAGER: Safe defaults
# ================================================================
print("\n=== POWER MANAGER: Safety ===")

from hal.power_manager import PowerManager
pm = PowerManager()
status = pm.get_status()

check(
    "PowerManager defaults to NOT running",
    not status["running"],
    "should not auto-start"
)

# ================================================================
# SUMMARY
# ================================================================
print(f"\n{'=' * 50}")
print(f"RESULTS: {PASS} passed, {FAIL} failed out of {PASS + FAIL}")
if FAIL == 0:
    print("ALL EDGE CASES HANDLED CORRECTLY")
else:
    print(f"WARNING: {FAIL} edge case(s) need attention!")
print(f"{'=' * 50}")

sys.exit(1 if FAIL > 0 else 0)
