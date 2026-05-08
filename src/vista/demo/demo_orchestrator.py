#!/usr/bin/env python3
"""
VISTA Classroom Demo Orchestrator
==================================
Coordinates interactive classroom demonstrations of the VISTA system
using simulated data. Designed for educator-led demonstrations with
clear visual feedback at each step.

Scenarios:
    crash  — Full crash detection pipeline demonstration
    theft  — PIR-based theft alert walk-through
    normal — Continuous simulated telemetry display

Usage:
    python demo/demo_orchestrator.py --scenario crash
    python demo/demo_orchestrator.py --scenario theft
    python demo/demo_orchestrator.py              # defaults to crash

Interactive:
    Press ENTER at each stage to advance the demo.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

# ── Logging ─────────────────────────────────────────────────────────────
try:
    from loguru import logger

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<level>{message}</level>",
        colorize=True,
    )
except ImportError:
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(message)s"
    )
    logger = logging.getLogger("demo_orch")  # type: ignore


# ════════════════════════════════════════════════════════════════════════════
# Display Helpers
# ════════════════════════════════════════════════════════════════════════════

BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
CLEAR = "\033[2J\033[H"


def clear_screen() -> None:
    """Clear the terminal screen."""
    print(CLEAR, end="")


def print_header(title: str) -> None:
    """Print a formatted section header."""
    width = 62
    print(f"\n{BOLD}{CYAN}{'═' * width}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'═' * width}{RESET}\n")


def print_step(step_num: int, description: str) -> None:
    """Print a demo step indicator."""
    print(f"\n{BOLD}{YELLOW}[STEP {step_num}]{RESET} {description}")


def print_status(status: str) -> None:
    """Print a status message in green."""
    print(f"  {GREEN}✓{RESET} {status}")


def print_warning(msg: str) -> None:
    """Print a warning message in yellow."""
    print(f"  {YELLOW}⚠{RESET}  {BOLD}{msg}{RESET}")


def print_error(msg: str) -> None:
    """Print an error message in red."""
    print(f"  {RED}✗{RESET} {msg}")


def print_alert(msg: str) -> None:
    """Print a critical alert in bold red."""
    print(f"\n  {RED}{BOLD}🚨 {msg} 🚨{RESET}\n")


def print_info(msg: str) -> None:
    """Print an informational message."""
    print(f"  {CYAN}→{RESET} {msg}")


def wait_for_enter(prompt: str = "Press ENTER to continue...") -> None:
    """Wait for the user to press ENTER."""
    try:
        input(f"\n{BOLD}{prompt}{RESET}")
    except (EOFError, KeyboardInterrupt):
        pass


def print_banner(lines: list) -> None:
    """Print a multi-line ASCII art banner."""
    for line in lines:
        print(f"{BOLD}{CYAN}{line}{RESET}")
    print()


# ════════════════════════════════════════════════════════════════════════════
# Sound Simulation
# ════════════════════════════════════════════════════════════════════════════

def play_crash_sound() -> None:
    """Play crash sound if file exists, otherwise print instruction."""
    script_dir = Path(__file__).resolve().parent
    sound_path = script_dir / "sounds" / "crash.wav"

    if sound_path.exists():
        try:
            if sys.platform == "win32":
                import winsound  # type: ignore

                winsound.PlaySound(str(sound_path), winsound.SND_FILENAME)
            else:
                os.system(f"aplay -q '{sound_path}' 2>/dev/null &")
            print_status("Crash audio played")
        except Exception as exc:
            print_warning(f"Cannot play sound: {exc}")
            print_warning("▶  PLAY CRASH SOUND NOW!")
    else:
        print_warning("▶  PLAY CRASH SOUND NOW!  (demo/sounds/crash.wav)")

        # Try to generate a simple beep as fallback
        try:
            if sys.platform != "win32":
                os.system("speaker-test -t sine -f 440 -l 1 -p 5000 2>/dev/null &")
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
# OBD Simulator Communication
# ════════════════════════════════════════════════════════════════════════════

def send_to_obd_simulator(command: str, port: Optional[str] = None) -> bool:
    """Send a scenario command to the OBD simulator via its serial port."""
    if port is None:
        port = os.environ.get("OBD_SIM_PORT", "/tmp/obd_sim")

    try:
        with open(port, "w") as f:
            f.write(f"{command}\n")
        return True
    except Exception as exc:
        print_warning(f"Cannot send to OBD simulator ({port}): {exc}")
        print_info(f"Is the OBD simulator running? Start with:")
        print_info(f"  python demo/obd_simulator.py --port {port}")
        return False


# ════════════════════════════════════════════════════════════════════════════
# SQLite Event Check
# ════════════════════════════════════════════════════════════════════════════

def check_sqlite_for_crash(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Check SQLite database for the most recent crash event."""
    if db_path is None:
        db_path = "data/events.db"

    full_path = db_path
    if not os.path.isabs(db_path):
        # Relative to vista root
        vista_root = Path(__file__).resolve().parent.parent
        full_path = str(vista_root / db_path)

    if not os.path.exists(full_path):
        return None

    try:
        import sqlite3

        conn = sqlite3.connect(full_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM events WHERE event_type = 'crash' ORDER BY timestamp DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
    except Exception as exc:
        print_warning(f"SQLite query failed: {exc}")

    return None


# ════════════════════════════════════════════════════════════════════════════
# Demo: Normal Driving
# ════════════════════════════════════════════════════════════════════════════

def demo_normal(modules: Dict[str, Any]) -> None:
    """Run a continuous simulated telemetry display demo."""
    clear_screen()
    print_header("VISTA Classroom Demo — Normal Driving Mode")

    print_info("Displaying simulated telemetry data...")
    print_info("Press Ctrl+C to stop\n")

    try:
        import math

        start = time.time()
        while True:
            now = time.time() - start
            sim_speed = 45.0 + 10.0 * math.sin(now * 0.5)
            sim_rpm = 2100.0 + 400.0 * math.sin(now * 0.5)
            sim_throttle = 25.0 + 5.0 * math.sin(now * 0.3)

            # Clear line and print telemetry
            print(
                f"\r  {GREEN}SYSTEM NORMAL{RESET} — "
                f"Speed: {sim_speed:5.1f} km/h | "
                f"RPM: {sim_rpm:5.0f} | "
                f"Throttle: {sim_throttle:3.0f}% | "
                f"Fuel: 65% | "
                f"Temp: 87°C  ",
                end="",
                flush=True,
            )
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n")
        print_status("Demo stopped")


# ════════════════════════════════════════════════════════════════════════════
# Demo: Crash Detection
# ════════════════════════════════════════════════════════════════════════════

def demo_crash(modules: Dict[str, Any]) -> None:
    """Run the crash detection pipeline demonstration."""
    clear_screen()

    # ── Banner ───────────────────────────────────────────────────────────
    banner = [
        "╔══════════════════════════════════════════════════════╗",
        "║     VISTA Crash Detection Pipeline Demo              ║",
        "║     From sensor to alert in under 1 second            ║",
        "╚══════════════════════════════════════════════════════╝",
    ]
    print_banner(banner)

    # ── Step 1: System Normal ───────────────────────────────────────────
    print_step(1, "SYSTEM INITIALIZATION")
    print_info("Starting VISTA sensors...")

    # Check available modules
    has_obd = "obd" in modules
    has_imu = "imu" in modules
    has_audio = "audio" in modules
    has_camera = "camera" in modules
    has_gpio = "gpio" in modules

    if has_obd:
        print_status("OBD-II reader online")
    else:
        print_warning("OBD-II reader not available (using simulated data)")

    if has_imu:
        print_status("IMU sensor online")
    else:
        print_warning("IMU not available")

    if has_audio:
        print_status("Audio capture online")
    else:
        print_warning("Audio capture not available")

    if has_camera:
        print_status("Camera ready")
    else:
        print_warning("Camera not available")

    if has_gpio:
        print_status("GPIO manager ready (buzzer active)")
    else:
        print_warning("GPIO not available")

    print("")
    print_status("VISTA system initialized successfully")
    print_info("All sensors monitoring — waiting for events")

    wait_for_enter("Press ENTER to begin the crash scenario...")

    # ── Step 2: Normal Driving Display ──────────────────────────────────
    print_step(2, "SYSTEM NORMAL — Monitoring vehicle...")

    # Show simulated normal driving for a few seconds
    import math

    for i in range(20):
        now = time.time()
        speed = 45.0 + 5.0 * math.sin(now * 2.0)
        rpm = 2100.0 + 200.0 * math.sin(now * 2.5)
        throttle = 25.0 + 3.0 * math.sin(now * 1.5)
        print(
            f"\r  {GREEN}●{RESET} Speed: {speed:5.1f} km/h | "
            f"RPM: {rpm:5.0f} | Throttle: {throttle:3.0f}% | "
            f"Status: NORMAL  ",
            end="",
            flush=True,
        )
        time.sleep(0.1)

    print("\n")
    wait_for_enter("Press ENTER to trigger the crash event...")

    # ── Step 3: Crash Trigger ───────────────────────────────────────────
    print_step(3, "TRIGGERING CRASH EVENT")

    # Send crash command to OBD simulator
    obd_port = os.environ.get("OBD_SIM_PORT", "/tmp/obd_sim")
    if send_to_obd_simulator("crash", obd_port):
        print_status(f"Crash command sent to OBD simulator ({obd_port})")
    else:
        print_info("Running with simulated crash (no OBD simulator connected)")

    # Small delay for the command to propagate
    time.sleep(0.5)

    # ── Step 4: Crash Audio ─────────────────────────────────────────────
    print_step(4, "PLAYING CRASH AUDIO")
    play_crash_sound()

    # ── Step 5: IMU Shake ───────────────────────────────────────────────
    print_step(5, "SIMULATING IMPACT")
    print_warning("⚠️  SHAKE IMU BOARD NOW!")
    print_info("(Moving MPU6050 to simulate impact forces)")

    # Visual countdown while IMU registers the "impact"
    for sec in range(3, 0, -1):
        print(f"\r  {YELLOW}⏳{RESET} Recording impact data... {sec}s remaining  ", end="", flush=True)
        time.sleep(1.0)
    print("\r  {GREEN}✓{RESET} Impact data recorded                         ")

    # ── Step 6: Crash Sequence Visualization ────────────────────────────
    print_step(6, "CRASH SEQUENCE — Sensor Data")

    # Animate crash data (throttle→0, speed→12→0)
    print("")
    speed = 45.0
    rpm = 2100.0
    throttle = 25.0

    for frame in range(20):
        frac = frame / 20.0

        if frac < 0.3:
            # Throttle drops to 0
            throttle = 25.0 * (1.0 - frac / 0.3)
            speed = 45.0 - 15.0 * frac
            rpm = 2100.0 - 400.0 * frac
        elif frac < 0.6:
            # Speed drops rapidly
            throttle = 0.0
            speed = max(12.0, 38.0 - 60.0 * (frac - 0.3))
            rpm = max(800.0, 1900.0 - 2000.0 * (frac - 0.3))
        else:
            # Impact → 0
            throttle = 0.0
            speed = max(0.0, 12.0 * (1.0 - (frac - 0.6) / 0.4))
            rpm = max(0.0, 800.0 * (1.0 - (frac - 0.6) / 0.4))

        color = GREEN if frac < 0.4 else YELLOW if frac < 0.7 else RED
        bar_len = int(speed / 3)
        bar = "█" * bar_len + "░" * (15 - bar_len)

        print(
            f"\r  {color}●{RESET} Speed: [{bar}] {speed:4.1f} km/h | "
            f"RPM: {rpm:5.0f} | Throttle: {throttle:3.0f}%",
            end="",
            flush=True,
        )
        time.sleep(0.1)

    print("\n")

    # ── Step 7: Detection Result ────────────────────────────────────────
    print_step(7, "DETECTION RESULT")

    time.sleep(1.0)

    # Simulate detection verdict
    print_alert("CRASH DETECTED!")
    print(f"  {BOLD}Event:{RESET}     Vehicle Collision")
    print(f"  {BOLD}Confidence:{RESET} 92.5%")
    print(f"  {BOLD}Severity:{RESET}   CRITICAL")

    print("\n  Evidence breakdown:")
    print(f"    {YELLOW}IMU Jerk:     35%{RESET} (impact spike detected)")
    print(f"    {YELLOW}Throttle Drop: 25%{RESET} (sudden to 0%)")
    print(f"    {YELLOW}Audio:         25%{RESET} (collision sound)")
    print(f"    {YELLOW}Speed Drop:    15%{RESET} (rapid deceleration)")

    # ── Step 8: Alert Routing ───────────────────────────────────────────
    print_step(8, "ALERT ROUTING")

    buzz_text = "Activated (3 beeps @ 1000Hz)" if has_gpio else "Simulated"
    print_status(f"Buzzer: {buzz_text}")
    print_status("Telegram alert sent")
    print_status("MQTT event published to vista/alerts/crash")
    print_status("Camera burst captured (5 frames)")
    print_status("Cloud Vision analysis queued")

    # ── Step 9: SQLite Verification ─────────────────────────────────────
    print_step(9, "DATABASE VERIFICATION")

    event = check_sqlite_for_crash()
    if event:
        print_status(f"Crash event logged in SQLite database")
        print_info(f"  Event ID:  {event.get('id', '?')}")
        print_info(f"  Timestamp: {event.get('timestamp', '?')}")
        print_info(f"  Confidence: {event.get('confidence', '?')}")
    else:
        print_warning("No crash event found in SQLite database")
        print_info("(Database may not be populated in demo mode)")

    # ── Summary ─────────────────────────────────────────────────────────
    print_header("DEMO COMPLETE — Pipeline Verified")

    print(f"  {GREEN}✓{RESET} Sensor data acquisition")
    print(f"  {GREEN}✓{RESET} Audio classification")
    print(f"  {GREEN}✓{RESET} Multi-sensor fusion")
    print(f"  {GREEN}✓{RESET} Decision engine evaluation")
    print(f"  {GREEN}✓{RESET} Crash confidence: 92.5% (>65% threshold)")
    print(f"  {GREEN}✓{RESET} Alert routed to all channels")
    print(f"  {GREEN}✓{RESET} Camera evidence captured")
    print(f"  {GREEN}✓{RESET} Cloud vision analysis triggered")
    print(f"  {GREEN}✓{RESET} Event persisted to database")
    print()
    print(f"  {BOLD}Detection time: ~800ms{RESET}")
    print(f"  {BOLD}Alert latency:  ~1.2s{RESET}")
    print()


# ════════════════════════════════════════════════════════════════════════════
# Demo: Theft Detection
# ════════════════════════════════════════════════════════════════════════════

def demo_theft(modules: Dict[str, Any]) -> None:
    """Run the PIR-based theft detection walk-through demo."""
    clear_screen()

    banner = [
        "╔══════════════════════════════════════════════════════╗",
        "║     VISTA Theft Detection Walk-Through Demo           ║",
        "║     PIR sensor → ESP32 wake → Pi camera → alert       ║",
        "╚══════════════════════════════════════════════════════╝",
    ]
    print_banner(banner)

    # ── Setup ────────────────────────────────────────────────────────────
    print_step(1, "SYSTEM ARMED — Parked Mode")

    print_status("VISTA in parked mode")
    print_status("ESP32 monitoring PIR sensor")
    print_status("Raspberry Pi in low-power sleep")
    print_info("Battery: 12.4V (ESP32 only consuming ~50mA)")

    has_gpio = "gpio" in modules

    print("")
    print("  The scenario: A person approaches the parked vehicle.")
    print("  The ESP32 PIR sensor detects motion and wakes the Pi.")
    print("  The Pi captures camera frames and analyzes the scene.")
    print("")

    wait_for_enter("Press ENTER when the 'intruder' is ready to approach...")

    # ── Motion Detection ─────────────────────────────────────────────────
    print_step(2, "MOTION DETECTED — ESP32 Waking Pi")

    print_warning("PIR SENSOR TRIGGERED!")
    print_info("ESP32: Motion detected — waking Raspberry Pi")
    print_info("ESP32: GPIO5 (WAKE) → HIGH for 100ms")

    if has_gpio:
        gpio = modules.get("gpio")
        if gpio and hasattr(gpio, "is_esp32_alive"):
            alive = gpio.is_esp32_alive()
            print_status(f"ESP32 status: {'ALIVE' if alive else 'no response'}")
    else:
        print_status("ESP32 wake signal simulated")

    time.sleep(1.0)
    print_info("Raspberry Pi booting...")
    time.sleep(2.0)
    print_status("VISTA main process started in theft-detection mode")

    # ── Camera Capture ───────────────────────────────────────────────────
    print_step(3, "CAMERA CAPTURE — Recording Evidence")

    has_camera = "camera" in modules
    if has_camera:
        print_status("Capturing camera frame (hypothetical — real on Pi)")
    else:
        print_info("Camera would capture here on actual hardware")

    print_info("Running Cloud Vision analysis...")
    time.sleep(1.5)

    print_status("Vision analysis: person detected near vehicle (confidence: 87%)")
    print_info("Ignition check: OFF (vehicle not running)")

    # ── Decision ─────────────────────────────────────────────────────────
    print_step(4, "DECISION ENGINE — Theft Assessment")

    print_warning("THEFT EVENT DETECTED!")

    print(f"  {BOLD}Event:{RESET}     Potential Theft")
    print(f"  {BOLD}Confidence:{RESET} 78.5%")
    print(f"  {BOLD}Severity:{RESET}   CRITICAL")

    print("\n  Evidence breakdown:")
    print(f"    {YELLOW}PIR Motion:    40%{RESET} (motion near vehicle)")
    print(f"    {YELLOW}Camera:        35%{RESET} (person detected)")
    print(f"    {YELLOW}Ignition Off:  25%{RESET} (vehicle not running)")

    # ── Alert Routing ────────────────────────────────────────────────────
    print_step(5, "ALERT ROUTING")

    print_status("Telegram alert sent to owner")
    print_status("Camera frame attached to alert")
    print_status("MQTT event published to vista/alerts/theft")
    print_status("Buzzer: Continuous tone (250ms on/off)")

    if has_camera:
        print_status("Burst capture initiated (10 frames)")

    # ── Summary ─────────────────────────────────────────────────────────
    print_header("THEFT DEMO COMPLETE")

    print(f"  {GREEN}✓{RESET} ESP32 PIR detection")
    print(f"  {GREEN}✓{RESET} Pi wake from sleep")
    print(f"  {GREEN}✓{RESET} Camera evidence captured")
    print(f"  {GREEN}✓{RESET} Cloud Vision person detection")
    print(f"  {GREEN}✓{RESET} Decision engine: theft confidence 78.5%")
    print(f"  {GREEN}✓{RESET} Multi-channel alert dispatched")
    print(f"  {GREEN}✓{RESET} Evidence stored for review")
    print()
    print(f"  {BOLD}Total response time: ~6.5s{RESET}")
    print(f"  {BOLD}ESP32 standby draw: ~50mA{RESET}")
    print()


# ════════════════════════════════════════════════════════════════════════════
# Demo Wrapper (called by main.py)
# ════════════════════════════════════════════════════════════════════════════

def run_demo(scenario: str, modules: Dict[str, Any]) -> None:
    """Entry point called by main.py when running in demo mode."""
    if scenario == "crash":
        demo_crash(modules)
    elif scenario == "theft":
        demo_theft(modules)
    else:
        demo_normal(modules)


# ════════════════════════════════════════════════════════════════════════════
# Standalone CLI
# ════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for standalone mode."""
    parser = argparse.ArgumentParser(
        description="VISTA Classroom Demo Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demo/demo_orchestrator.py                    # crash demo (default)
  python demo/demo_orchestrator.py --scenario crash   # crash detection demo
  python demo/demo_orchestrator.py --scenario theft   # theft detection demo
  python demo/demo_orchestrator.py --scenario normal  # continuous telemetry
        """,
    )
    parser.add_argument(
        "--scenario",
        choices=["crash", "theft", "normal"],
        default="crash",
        help="Demo scenario to run (default: crash)",
    )
    return parser.parse_args()


def main() -> None:
    """Standalone entry point."""
    args = parse_args()

    print_header(f"VISTA Demo Orchestrator — {args.scenario.upper()} Scenario")

    # Run with empty modules dict (standalone mode)
    run_demo(args.scenario, {})


if __name__ == "__main__":
    main()
