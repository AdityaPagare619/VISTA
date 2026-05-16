"""
VISTA v3.0 — Comprehensive Engineering Verification Suite
=========================================================
Expands upon quick tests to include Audio, EKF Edge Cases,
Weight Redistribution, Health Monitoring, and System Latency.
"""

import sys
import time
import math
import numpy as np

sys.path.insert(0, ".")

PASS = 0
FAIL = 0
TEST_LOGS = []

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        msg = f"  PASS  {name}"
        print(msg)
        TEST_LOGS.append(msg)
    else:
        FAIL += 1
        msg = f"  FAIL  {name}  ({detail})"
        print(msg)
        TEST_LOGS.append(msg)


print("=" * 60)
print("VISTA v3.0 REAL-WORLD ENGINEERING SUITE")
print("=" * 60)

# ================================================================
# 1. AUDIO INTELLIGENCE (YAMNet)
# ================================================================
print("\n=== 1. AUDIO INTELLIGENCE (YAMNet) ===")

from intelligence.audio_classifier import AudioClassifier
ac = AudioClassifier()

check("AudioClassifier loads successfully", ac.model_loaded, "Model not found")

if ac.model_loaded:
    # Silence
    silence = np.zeros(15600, dtype=np.float32)
    label, conf = ac.classify(silence)
    check("Silence is classified as 'normal'", label == "normal", f"Got {label}")
    check("Silence confidence is 0.0", conf < 0.01, f"Got {conf}")

    # Crash audio
    t = np.arange(15600) / 16000
    crash_audio = np.random.randn(15600).astype(np.float32) * 0.8
    crash_audio *= np.exp(-t * 8) * (1 - np.exp(-t * 200))
    metal = np.sin(2 * np.pi * 1200 * t) * 0.3 + np.sin(2 * np.pi * 2400 * t) * 0.2
    crash_audio += metal.astype(np.float32) * np.exp(-t * 10).astype(np.float32)
    
    label, conf = ac.classify(crash_audio)
    check("Synthetic crash classified as 'crash'", label == "crash", f"Got {label}")
    check("Crash confidence is high", conf > 0.8, f"Got {conf}")

    # Verify fallback on bad data
    label, conf = ac.classify(np.array([1, 2, 3], dtype=np.float32))
    check("Classifier handles malformed input gracefully", label == "normal", "Should return normal fallback")


# ================================================================
# 2. EKF STRESS TESTS
# ================================================================
print("\n=== 2. EKF STRESS TESTS ===")

from intelligence.velocity_ekf import VelocityEKF
ekf = VelocityEKF()

# Test NaN inputs
try:
    ekf.predict(float('nan'))
    ekf.update(float('nan'))
    v = ekf.get_velocity_kmh()
    check("EKF survives NaN input without crashing", not math.isnan(v), "Returned NaN")
except Exception as e:
    check("EKF survives NaN input without crashing", False, str(e))

# Test extreme acceleration
ekf2 = VelocityEKF()
ekf2.predict(100.0)  # 100g forward (impossible)
ekf2.update(500.0)   # 500 km/h
v = ekf2.get_velocity_kmh()
check("EKF bounds extreme inputs safely", 0 <= v <= 350, f"Got {v}")

# Test negative speeds (should clamp to 0)
ekf3 = VelocityEKF()
ekf3.predict(-2.0)
ekf3.update(-50.0)
v = ekf3.get_velocity_kmh()
check("EKF clamps negative speeds to zero", v == 0.0, f"Got {v}")


# ================================================================
# 3. CRASH DETECTOR: WEIGHT REDISTRIBUTION
# ================================================================
print("\n=== 3. WEIGHT REDISTRIBUTION MATH ===")

from intelligence.crash_detector import CrashDetector
cd = CrashDetector()

# All available
w_all = cd.get_weights_for_sensors({"imu", "audio", "obd", "vision"})
check("All sensors available sum to 1.0", abs(sum(w_all.values()) - 1.0) < 0.001)

# IMU + Audio
w_imu_aud = cd.get_weights_for_sensors({"imu", "audio"})
check("IMU+Audio sum to 1.0", abs(sum(w_imu_aud.values()) - 1.0) < 0.001)
check("IMU weight increases when OBD/Vision drop", w_imu_aud["imu"] > w_all["imu"])

# IMU only
w_imu_only = cd.get_weights_for_sensors({"imu"})
check("IMU-only sum to 1.0", abs(sum(w_imu_only.values()) - 1.0) < 0.001)
check("IMU-only weight is 1.0", w_imu_only["imu"] == 1.0)

# ================================================================
# 4. SYSTEM HEALTH MONITOR
# ================================================================
print("\n=== 4. SYSTEM HEALTH MONITOR ===")

from intelligence.health_monitor import SystemHealthMonitor
hm = SystemHealthMonitor()

# Initial state
check("Health Monitor initializes with no live sensors", len(hm.get_live_sensors()) == 0)
check("Capacity is 0% without IMU", hm.get_detection_capacity() == 0.0)

# Ping IMU
hm.ping_sensor("imu")
check("IMU registered as live", "imu" in hm.get_live_sensors())
check("Capacity > 0% with IMU live", hm.get_detection_capacity() > 0.4)

# Ping all
hm.ping_sensor("obd")
hm.ping_sensor("audio")
check("Capacity near max with all core sensors", hm.get_detection_capacity() >= 0.8)

# Test timeout
time.sleep(0.6)  # IMU timeout is 0.5s
check("IMU times out correctly", "imu" not in hm.get_live_sensors())

report = hm.get_full_health_report({"velocity_kmh": 50, "accel_bias_mps2": 0.0})
check("Full health report generates without error", isinstance(report, dict) and "overall_status" in report)


# ================================================================
# 5. LATENCY CHECKS
# ================================================================
print("\n=== 5. LATENCY & TIMING ===")

from intelligence.crash_detector import CrashEvidence
cd2 = CrashDetector()

# Measure inference latency for standard loop
start_time = time.perf_counter()
for _ in range(100):
    cd2.check_imu(1.5, 0.01)
    ev = CrashEvidence(
        imu_jerk=2.0, imu_saturated=False, imu_accel_magnitude=1.5,
        audio_class="normal", audio_confidence=0.0,
        obd_speed_drop=0, obd_throttle_drop=0, timestamp=time.time()
    )
    cd2.assess(ev)
end_time = time.perf_counter()
avg_ms = ((end_time - start_time) / 100) * 1000

check(f"CrashDetector pipeline < 5ms per frame (avg: {avg_ms:.2f}ms)", avg_ms < 5.0, f"Got {avg_ms:.2f}ms")


# ================================================================
# SUMMARY
# ================================================================
print(f"\n{'=' * 50}")
print(f"RESULTS: {PASS} passed, {FAIL} failed out of {PASS + FAIL}")
if FAIL == 0:
    print("ALL TESTS PASSED. SYSTEM IS HARDENED.")
else:
    print(f"WARNING: {FAIL} tests failed!")
print(f"{'=' * 50}")

sys.exit(1 if FAIL > 0 else 0)
