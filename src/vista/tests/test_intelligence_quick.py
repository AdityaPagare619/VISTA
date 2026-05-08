"""Quick validation of all intelligence modules."""
from intelligence import FusionEngine, AudioClassifier, DecisionEngine, CloudVision
import numpy as np

results = []

# 1. FusionEngine: EKF convergence
fe = FusionEngine()
for _ in range(20):
    fe.predict((0.03, 0.0, 1.01))
    fe.update(obd_speed=65.0, imu_ax=0.3)
v = fe.get_velocity()
ok = 58 < v < 72
results.append(("EKF convergence (65 km/h)", ok))
print(f"EKF velocity after 20 iterations: {v:.1f} km/h -> {'OK' if ok else 'OFF'}")

# 2. FusionEngine: jerk sign
fe.reset()
fe.predict((0.01, 0.0, 1.0))
fe.predict((0.20, 0.0, 1.0))
j1 = fe.get_jerk()
ok = j1 > 0
results.append(("Jerk positive", ok))
print(f"Positive jerk: {j1:.2f} g/s -> {'OK' if ok else 'FAIL'}")

fe.predict((0.01, 0.0, 1.0))
j2 = fe.get_jerk()
ok = j2 < 0
results.append(("Jerk negative", ok))
print(f"Negative jerk: {j2:.2f} g/s -> {'OK' if ok else 'FAIL'}")

# 3. AudioClassifier: fallback
ac = AudioClassifier()
label, conf = ac.classify(np.ones(16000, dtype=np.float32) * 0.01)
ok = label == "normal" and conf == 0.99
results.append(("Audio fallback", ok))
print(f"Audio fallback: ({label}, {conf}) -> {'OK' if ok else 'FAIL'}")

# 4. Decision: crash detection
de = DecisionEngine()
crash = de.assess_crash(
    imu_data={"jerk": 5.5, "accel_x": -4.0},
    obd_data={"throttle_delta": -90, "speed": 0.0},
    audio_result=("crash", 0.92),
)
ok = crash.is_alert and crash.severity == "alert"
results.append(("Crash alert", ok))
print(f"Crash: alert={crash.is_alert}, sev={crash.severity}, conf={crash.confidence:.2%}")

# 5. Decision: normal driving
normal = de.assess_crash(
    imu_data={"jerk": 0.2, "accel_x": 0.05},
    obd_data={"throttle_delta": 3, "speed": 55},
    audio_result=("normal", 0.98),
)
ok = not normal.is_alert and normal.severity == "normal"
results.append(("Normal driving", ok))
print(f"Normal: alert={normal.is_alert}, sev={normal.severity}")

# 6. Decision: theft
theft = de.assess_theft(pir_triggered=True, ignition_off=True)
ok = theft.is_alert
results.append(("Theft alert", ok))
print(f"Theft: alert={theft.is_alert}, conf={theft.confidence:.2%}")

# 7. Decision: weight redistribution (no vision)
crash2 = de.assess_crash(
    imu_data={"jerk": 5.5, "accel_x": -4.0},
    obd_data={"throttle_delta": -90, "speed": 0.0},
    audio_result=("crash", 0.92),
    vision_result=None,
)
ok = crash2.is_alert
results.append(("Vision redistribution", ok))
print(f"Crash (no vision): conf={crash2.confidence:.2%}")

# 8. Behavior analysis
beh = de.analyze_behavior(
    obd_history=[{"speed": 60}, {"speed": 65}, {"speed": 120}],
    imu_history=[{"jerk": 4.5, "accel_x": 0.2}, {"jerk": 6.0, "accel_x": 0.7}],
)
required_keys = ["harsh_braking_count", "risk_score", "summary"]
ok = all(k in beh for k in required_keys)
results.append(("Behavior keys", ok))
print(f"Behavior: harsh={beh['harsh_braking_count']}, risk={beh['risk_score']}")

# 9. CloudVision error handling
cv = CloudVision()
r = cv.analyze_scene(b"")
ok = "error" in r
results.append(("CloudVision error resilience", ok))
print(f"CloudVision error: {'error' in r}")

# 10. Evidence dataclass
from intelligence import Evidence, Decision
e = Evidence(sensor="test", value=1.0, threshold=0.5, confidence=0.8, explanation="test")
ok = e.sensor == "test" and e.confidence == 0.8
results.append(("Evidence dataclass", ok))

# 11. FusionEngine get_covariance
fe2 = FusionEngine()
cov = fe2.get_covariance()
ok = cov.shape == (3, 3) and np.all(np.diag(cov) > 0)
results.append(("Covariance shape", ok))

# Summary
print()
print("=" * 60)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"RESULTS: {passed}/{total} tests passed")
for name, ok in results:
    print(f"  {'PASS' if ok else 'FAIL'}: {name}")
print("=" * 60)
if passed == total:
    print("ALL TESTS PASSED!")
else:
    print(f"FAILURES: {total - passed}")
    exit(1)
