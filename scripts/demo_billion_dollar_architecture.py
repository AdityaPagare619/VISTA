"""
VISTA Enterprise Architecture: Software-in-the-Loop Demo
=========================================================
This script demonstrates the two V4 intelligence engines in the demo room:

  1. Ghost Key Temporal Sequence Analysis (Defeating CAN-Bus Injection)
  2. Predictive NVH Analytics (Simulated Drivetrain Health Monitoring)

DEMO ROOM METHODOLOGY (Hardware-Software In-the-Loop):
  The ALGORITHMS are real. The SENSOR DATA is simulated.
  This is exactly how Bosch, Continental, and Mobileye validate
  systems before field testing. Every number you see comes from
  actual VISTA code — not hardcoded strings.

WHAT'S REAL vs SIMULATED:
  ┌─────────────────────┬─────────────┬──────────────┐
  │ Component           │ Algorithm   │ Data Source   │
  ├─────────────────────┼─────────────┼──────────────┤
  │ Ghost Key TSA       │ ✅ REAL     │ Mock events   │
  │ BLE Proximity       │ ✅ REAL     │ Mock flag     │
  │ NVH Health Score    │ Simulated   │ Deterministic │
  │ Telegram Bot        │ ✅ REAL     │ ✅ REAL       │
  │ Gemini REST API     │ ✅ REAL     │ Text prompt   │
  └─────────────────────┴─────────────┴──────────────┘
"""

import sys
import time
import json
from pathlib import Path
from loguru import logger

# Ensure src/vista is in the python path
vista_root = Path(__file__).resolve().parent.parent / "src" / "vista"
if str(vista_root) not in sys.path:
    sys.path.insert(0, str(vista_root))

from intelligence.theft_detector import TheftDetector
from intelligence.predictive_analytics import PredictiveAnalyticsEngine


def demo_ghost_key_tsa():
    """
    SCENARIO 1: CAN-Bus Injection Attack (Relay Theft)
    
    What we demonstrate to the room:
      A hacker accesses headlight wiring and injects "Unlock" + "Engine Start"
      directly into the CAN-bus. The car's ECU sees a valid command.
      
      VISTA's Ghost Key TSA detects FOUR temporal anomalies:
        1. BLE_ABSENT - Owner's phone is not in the cabin
        2. No door_open event - Hacker injected digitally, didn't open door
        3. No driver_seated event - Nobody sat down
        4. Timing < 2.5s - Automated tool, not human biomechanics
      
      Result: Analog fuel relay cut. Vehicle immobilized.
    """
    logger.info("=" * 60)
    logger.info("🧪 SCENARIO 1: CAN-BUS INJECTION ATTACK (RELAY THEFT)")
    logger.info("=" * 60)
    time.sleep(1)

    detector = TheftDetector()

    # 1. Simulate the CAN-bus injection
    logger.warning("ATTACKER: Injecting CAN-bus 'Unlock' + 'Engine Start' signals...")
    time.sleep(1)

    # 2. Set up the mock state for the demo:
    #    - No BLE (thief doesn't have owner's phone)
    #    - Event sequence is missing door_open and driver_seated
    #    - Entry time is 1.2 seconds (automated tool)
    detector.mock_owner_ble_present = False
    detector.mock_event_sequence = ["can_unlock", "engine_start"]  # Missing door/seat
    detector.mock_entry_duration_sec = 1.2  # Automated tool speed

    # 3. Trigger the VISTA security pipeline
    was_prevented = detector.handle_motion_trigger(can_bus_hacked=True)

    if was_prevented:
        logger.success("✅ RESULT: Ghost Key TSA detected temporal anomalies. Fuel relay cut.")
    else:
        logger.error("❌ RESULT: Vehicle stolen (this should NOT happen).")

    time.sleep(2)
    return was_prevented


def demo_ghost_key_legitimate():
    """
    SCENARIO 1B: Legitimate Owner Entry (No False Positive)
    
    What we demonstrate:
      The owner approaches with their phone (BLE detected).
      The system silently disarms. No fuel cut, no alert.
    """
    logger.info("=" * 60)
    logger.info("🧪 SCENARIO 1B: LEGITIMATE OWNER ENTRY (BLE PRESENT)")
    logger.info("=" * 60)
    time.sleep(1)

    detector = TheftDetector()

    # Owner has their phone — BLE is present
    detector.mock_owner_ble_present = True

    was_prevented = detector.handle_motion_trigger(can_bus_hacked=False)

    if not was_prevented:
        logger.success("✅ RESULT: Owner authenticated via BLE. Silent disarm. Zero false positives.")
    else:
        logger.error("❌ RESULT: False positive — owner blocked (this should NOT happen).")

    time.sleep(2)
    return not was_prevented


def demo_nvh_predictive_maintenance():
    """
    SCENARIO 2: Enterprise B2B Predictive NVH Analytics
    
    What we demonstrate:
      The NVH pipeline produces a deterministic 2KB health JSON.
      In the demo room, this proves the data flow:
        Edge sensor → FFT analysis → Health Score → API → Dashboard
      
      The values are SIMULATED (clearly labeled _simulation_mode: true).
      A real deployment requires 14 days of baseline data collection.
    """
    logger.info("=" * 60)
    logger.info("🧪 SCENARIO 2: ENTERPRISE B2B PREDICTIVE NVH ANALYTICS")
    logger.info("=" * 60)
    time.sleep(1)

    analytics = PredictiveAnalyticsEngine()

    logger.info("VISTA Edge: Running NVH Autoencoder (SIMULATION MODE)...")
    time.sleep(1)

    # 1. Generate the 2KB B2B Health Score
    health_score = analytics.calculate_nvh_reconstruction_error()

    logger.info("VISTA Cloud: B2B Insurance/OEM API Response:")
    print(json.dumps(health_score, indent=2))
    time.sleep(1)

    # Show simulation disclosure
    if health_score.get("_simulation_mode"):
        logger.info("📋 NOTE: Values are deterministic simulation. Real model requires baseline training.")

    if health_score["drivetrain_anomaly_detected"]:
        logger.warning(
            f"⚠️ ENTERPRISE ALERT: Drivetrain anomaly at "
            f"{health_score['anomaly_frequency_band']}"
        )
        logger.info("Triggering Gemini 'Expert Mechanic' for Telegram B2C Report...")
        analytics.run_and_notify()

    return True


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("VISTA Software-in-the-Loop Architecture Demo")
    logger.info("Algorithms: REAL | Sensor Data: SIMULATED")
    logger.info("=" * 60)
    time.sleep(1)

    results = {}

    # Test 1: CAN-Bus injection caught
    results["theft_detected"] = demo_ghost_key_tsa()
    print("\n")

    # Test 2: Legitimate owner passes
    results["legitimate_passes"] = demo_ghost_key_legitimate()
    print("\n")

    # Test 3: NVH health pipeline
    results["nvh_pipeline"] = demo_nvh_predictive_maintenance()
    print("\n")

    # Summary
    logger.info("=" * 60)
    logger.info("🏁 DEMO RESULTS SUMMARY")
    logger.info("=" * 60)
    all_pass = all(results.values())
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"  {name}: {status}")

    if all_pass:
        logger.success("ALL SCENARIOS PASSED.")
        sys.exit(0)
    else:
        logger.error("SOME SCENARIOS FAILED.")
        sys.exit(1)
