"""
VISTA v3.0 Master Stroke Verification Script
=============================================
Runs the Predictive Maintenance Analytics pipeline and the Anti-Theft Verification pipeline
to test the Gemini API and Telegram bot integration.
"""

import sys
from pathlib import Path
from loguru import logger

# Add src/vista to path so imports work
vista_root = Path(__file__).resolve().parent.parent / "src" / "vista"
sys.path.insert(0, str(vista_root))

from intelligence.predictive_analytics import PredictiveAnalyticsEngine
from intelligence.theft_detector import TheftDetector


def run_tests():
    logger.info("==================================================")
    logger.info("   VISTA CLOUD INTELLIGENCE MASTER STROKE TEST    ")
    logger.info("==================================================")

    logger.info("\n--- TEST 1: PREDICTIVE MAINTENANCE ANALYTICS ---")
    analytics = PredictiveAnalyticsEngine()
    success_maintenance = analytics.run_and_notify()
    
    if success_maintenance:
        logger.success("Test 1 Passed: Predictive Maintenance report sent to Telegram.")
    else:
        logger.error("Test 1 Failed.")

    logger.info("\n--- TEST 2: DUAL-VALIDATION ANTI-THEFT ---")
    detector = TheftDetector()
    success_theft = detector.handle_motion_trigger()
    
    if success_theft:
        logger.success("Test 2 Passed: Unauthorized entry detected and sent to Telegram.")
    else:
        logger.error("Test 2 Failed or resulted in silent disarm.")


if __name__ == "__main__":
    run_tests()
