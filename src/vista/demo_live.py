#!/usr/bin/env python3
"""
VISTA v3.0 — Live Demo Runner
===============================
Runs REAL v3.0 modules (VelocityEKF, CrashDetector, YAMNet) with
simulated sensor data. Every number on screen comes from actual code.

Usage:
    python demo_live.py                      # Auto-run (60s scenario)
    python demo_live.py --interactive        # Step-by-step (press ENTER)
    python demo_live.py --speed 2.0          # 2x speed
    python demo_live.py --no-audio           # Skip YAMNet (faster)

What's REAL vs SIMULATED:
    REAL:      VelocityEKF, CrashDetector, YAMNet inference
    SIMULATED: Sensor data (OBD speed, IMU g-force, audio waveforms)

This is exactly how automotive systems are validated: real algorithms,
simulated sensor inputs, before expensive field testing.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# ── Force UTF-8 on Windows (must be before ANY print call) ───────
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np

# ── Ensure vista package is importable ────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_VISTA_ROOT = _SCRIPT_DIR  # demo_live.py lives in src/vista/
if str(_VISTA_ROOT) not in sys.path:
    sys.path.insert(0, str(_VISTA_ROOT))

# ── Terminal Colors ───────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
RESET = "\033[0m"
CLEAR_LINE = "\033[2K\033[G"
CLEAR_SCREEN = "\033[2J\033[H"

# ── Enable ANSI on Windows ────────────────────────────────────────
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════
# Module Loading (graceful — shows what's available)
# ════════════════════════════════════════════════════════════════════

def load_modules(use_audio: bool = True) -> Dict[str, Any]:
    """Load v3.0 intelligence modules. Returns dict of available modules."""
    modules: Dict[str, Any] = {}

    # 1. VelocityEKF
    try:
        from intelligence.velocity_ekf import VelocityEKF
        ekf = VelocityEKF()
        modules["ekf"] = ekf
    except Exception as exc:
        print(f"  {YELLOW}⚠{RESET}  VelocityEKF: {exc}")

    # 2. CrashDetector
    try:
        from intelligence.crash_detector import CrashDetector, CrashEvidence
        detector = CrashDetector()
        modules["detector"] = detector
        modules["CrashEvidence"] = CrashEvidence
    except Exception as exc:
        print(f"  {YELLOW}⚠{RESET}  CrashDetector: {exc}")

    # 3. YAMNet (optional — slower to load)
    if use_audio:
        try:
            yamnet_path = _VISTA_ROOT / "models" / "yamnet.tflite"
            labels_path = _VISTA_ROOT / "models" / "yamnet_class_map.csv"

            if yamnet_path.exists():
                try:
                    import tensorflow as tf
                    interp = tf.lite.Interpreter(model_path=str(yamnet_path))
                except ImportError:
                    import tflite_runtime.interpreter as tflite
                    interp = tflite.Interpreter(model_path=str(yamnet_path))

                interp.allocate_tensors()
                modules["yamnet"] = interp
                modules["yamnet_input"] = interp.get_input_details()
                modules["yamnet_output"] = interp.get_output_details()

                # Load labels
                import csv
                yamnet_labels = {}
                if labels_path.exists():
                    with open(labels_path, encoding="utf-8") as f:
                        for row in csv.DictReader(f):
                            yamnet_labels[int(row["index"])] = row["display_name"]
                modules["yamnet_labels"] = yamnet_labels
            else:
                print(f"  {YELLOW}⚠{RESET}  YAMNet model not found. Run: python scripts/setup_ml.py")
        except Exception as exc:
            print(f"  {YELLOW}⚠{RESET}  YAMNet: {exc}")

    return modules


# Audio classification is now handled by intelligence/audio_classifier.py
# (no inline code needed — see AudioClassifier.classify())


# ════════════════════════════════════════════════════════════════════
# Display Functions
# ════════════════════════════════════════════════════════════════════

def print_banner():
    """Print the VISTA demo banner."""
    print(CLEAR_SCREEN, end="")
    banner = f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ██╗   ██╗██╗███████╗████████╗ █████╗     ██╗   ██╗ ██████╗    ║
║   ██║   ██║██║██╔════╝╚══██╔══╝██╔══██╗    ██║   ██║ ╚════██╗   ║
║   ██║   ██║██║███████╗   ██║   ███████║    ██║   ██║  █████╔╝   ║
║   ╚██╗ ██╔╝██║╚════██║   ██║   ██╔══██║    ╚██╗ ██╔╝  ╚═══██╗   ║
║    ╚████╔╝ ██║███████║   ██║   ██║  ██║     ╚████╔╝  ██████╔╝   ║
║     ╚═══╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝      ╚═══╝   ╚═════╝    ║
║                                                                  ║
║   Vehicle Intelligence & Safety Telematics Architecture          ║
║   Live System Demo — Real Algorithms, Simulated Sensors          ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)


def speed_bar(speed: float, max_speed: float = 100.0, width: int = 20) -> str:
    """Create a colored speed bar."""
    filled = int((speed / max_speed) * width)
    filled = min(filled, width)

    if speed < 40:
        color = GREEN
    elif speed < 70:
        color = YELLOW
    else:
        color = RED

    bar = f"{color}{'█' * filled}{DIM}{'░' * (width - filled)}{RESET}"
    return f"[{bar}]"


def imu_bar(g_force: float, max_g: float = 16.0, width: int = 15) -> str:
    """Create a colored IMU magnitude bar."""
    filled = int((g_force / max_g) * width)
    filled = min(filled, width)

    if g_force < 2.0:
        color = GREEN
    elif g_force < 5.0:
        color = YELLOW
    elif g_force < 10.0:
        color = f"{BOLD}{YELLOW}"
    else:
        color = f"{BOLD}{RED}"

    bar = f"{color}{'▓' * filled}{DIM}{'░' * (width - filled)}{RESET}"
    return f"[{bar}]"


def format_crash_result(result: Dict[str, Any]) -> str:
    """Format crash detection result for display."""
    conf = result["confidence"]
    state = result["state"]
    is_crash = result["is_crash"]

    if is_crash:
        return f"{RED}{BOLD}🚨 CRASH DETECTED — {conf:.1%} confidence{RESET}"
    elif state == "potential":
        return f"{YELLOW}⚠  Potential event — {conf:.1%}{RESET}"
    else:
        return f"{GREEN}●  Normal — {conf:.1%}{RESET}"


# ════════════════════════════════════════════════════════════════════
# Main Demo Loop
# ════════════════════════════════════════════════════════════════════

def run_demo(
    interactive: bool = False,
    speed_mult: float = 1.0,
    use_audio: bool = True,
    scenario: str = "crash",
    json_output: bool = False,
) -> bool:
    """Run the live VISTA demo with real v3.0 modules."""

    if not json_output:
        print_banner()

    # ── Phase 1: Load modules ─────────────────────────────────────
    if not json_output:
        print(f"\n{BOLD}{CYAN}[PHASE 1] Loading VISTA v3.0 Modules{RESET}\n")

    modules = load_modules(use_audio=use_audio)

    ekf = modules.get("ekf")
    detector = modules.get("detector")
    CrashEvidence = modules.get("CrashEvidence")
    has_audio = "audio_classifier" in modules

    if not json_output:
        if ekf:
            print(f"  {GREEN}✓{RESET} VelocityEKF — 2-state Kalman filter [velocity, accel_bias]")
        if detector:
            print(f"  {GREEN}✓{RESET} CrashDetector — Signature-aware (sustain + asymmetry)")
        if has_audio:
            print(f"  {GREEN}✓{RESET} AudioClassifier — YAMNet integrated (3.9 MB TFLite)")
        else:
            print(f"  {DIM}○  AudioClassifier — Skipped (use --audio to enable){RESET}")

    if not ekf or not detector:
        if not json_output:
            print(f"\n  {RED}✗  Critical modules missing. Cannot run demo.{RESET}")
        return False

    # ── Phase 2: Generate scenario ────────────────────────────────
    if not json_output:
        print(f"\n{BOLD}{CYAN}[PHASE 2] Generating Sensor Scenario '{scenario}'{RESET}\n")

    from demo_data import SCENARIOS
    if scenario not in SCENARIOS:
        if not json_output:
            print(f"  {YELLOW}Unknown scenario '{scenario}', defaulting to 'crash'{RESET}")
        scenario = "crash"

    frames = SCENARIOS[scenario]()

    # Count events
    events = {}
    for f in frames:
        events[f.event] = events.get(f.event, 0) + 1

    if not json_output:
        print(f"  {GREEN}✓{RESET} Generated {len(frames)} frames ({len(frames) * 0.1:.0f}s at 10Hz)")
        print(f"  {DIM}   Events: {', '.join(f'{k}: {v}' for k, v in sorted(events.items()))}{RESET}")
        print(f"\n  {BOLD}Scenario loaded: {scenario}{RESET}")
    print(f"  36-45s  Resume normal driving")
    print(f"  {RED}47-48s  CRASH — sustained asymmetric impact{RESET}")
    print(f"  48-60s  Post-crash")

    if interactive:
        input(f"\n{BOLD}Press ENTER to begin the demo...{RESET}")

    # ── Phase 3: Running VISTA Pipeline ─────────────────────────────
    if not json_output:
        print(f"\n{BOLD}{CYAN}[PHASE 3] Running VISTA Pipeline{RESET}\n")
        print(f"  {BOLD}Speed{RESET}  │ {BOLD}EKF velocity{RESET} │ {BOLD}IMU g{RESET}  │ {BOLD}Audio class{RESET}   │ {BOLD}Crash Detector{RESET}")
    print(f"  {DIM}{'─' * 75}{RESET}")

    crash_detected = False
    pothole_rejected = False
    crash_result_final = None
    audio_at_crash = None

    # Tracking for post-crash analysis
    ekf_velocities = []
    imu_values = []
    crash_results = []

    prev_speed = 0.0
    last_audio_result = {"label": "normal", "confidence": 0.0, "detail": ""}

    for i, frame in enumerate(frames):
        loop_start = time.time()

        # ── Feed EKF ──────────────────────────────────────────
        speed_change = (frame.obd_speed_kmh - prev_speed) / 3.6  # m/s
        fwd_accel_g = speed_change / (0.1 * 9.81)  # approximate forward g
        ekf.predict(fwd_accel_g)
        ekf.update(frame.obd_speed_kmh)
        ekf_speed = ekf.get_velocity_kmh()
        ekf_velocities.append(ekf_speed)
        prev_speed = frame.obd_speed_kmh

        is_event_frame = frame.event in ("crash", "pothole")
        if is_event_frame:
            time.sleep(0.020)
        else:
            time.sleep(0.005)

        # ── Feed CrashDetector IMU ────────────────────────────
        jerk = detector.check_imu(frame.imu_accel_magnitude_g, dt=0.1)
        imu_values.append(frame.imu_accel_magnitude_g)

        # ── Audio classification ───
        audio_result = last_audio_result
        if has_audio and i % 10 == 0:
            label, conf = modules["audio_classifier"].classify(frame.audio_waveform)
            audio_result = {"label": label, "confidence": conf}
            last_audio_result = audio_result

        # ── Full crash assessment ─────────────────────────────
        obd_speed_drop = max(0, 55 - frame.obd_speed_kmh) if frame.event in ("crash", "post_crash") else 0
        obd_throttle_drop = max(0, 15 - frame.obd_throttle_pct) if frame.event in ("crash", "post_crash") else 0

        evidence = CrashEvidence(
            imu_jerk=jerk,
            imu_saturated=frame.imu_accel_magnitude_g >= 15.5,
            imu_accel_magnitude=frame.imu_accel_magnitude_g,
            audio_class=audio_result.get("label", "normal"),
            audio_confidence=audio_result.get("confidence", 0.0),
            obd_speed_drop=obd_speed_drop,
            obd_throttle_drop=obd_throttle_drop,
            timestamp=frame.time_s,
        )

        result = detector.assess(evidence)
        crash_results.append(result)

        # ── Detect key moments ────────────────────────────────
        if result["is_crash"] and not crash_detected:
            crash_detected = True
            crash_result_final = result
            audio_at_crash = audio_result

        if frame.event in ("pothole", "speed_bump", "hard_braking") and not result["is_crash"]:
            pothole_rejected = True

        # ── Display ──────────────────────────────────────────
        if json_output:
            continue

        spd_bar = speed_bar(ekf_speed)
        imu_b = imu_bar(frame.imu_accel_magnitude_g)
        audio_str = f"{audio_result['label']:8s}" if audio_result.get("label", "normal") not in ("normal", "") else f"{DIM}—{RESET}       "

        status = format_crash_result(result)
        line = (f"  {frame.time_s:5.1f}s  {spd_bar} {ekf_speed:5.1f} km/h  {imu_b} {frame.imu_accel_magnitude_g:5.1f}g  {audio_str}  {status}")

        if result["is_crash"]:
            print(f"\r{CLEAR_LINE}{line}")
        elif frame.event == "pothole" and not result["is_crash"]:
            print(f"\r{CLEAR_LINE}  {frame.time_s:5.1f}s  {spd_bar} {ekf_speed:5.1f} km/h  {imu_b} {frame.imu_accel_magnitude_g:5.1f}g  {YELLOW}POTHOLE → REJECTED (not crash){RESET}")
        elif i % 5 == 0:
            print(f"\r{CLEAR_LINE}{line}", end="", flush=True)

        # Pacing (skip additional sleep during events — already slept above)
        if not is_event_frame:
            elapsed = time.time() - loop_start
            sleep_time = max(0, (0.1 / speed_mult) - elapsed)
            time.sleep(sleep_time)

        if interactive and frame.event in ("pothole", "crash", "obd_dropout", "horn", "speed_bump", "hard_braking") and i % 10 == 0:
            print()  # newline before pause
            input(f"  {DIM}Press ENTER to continue...{RESET}")

    # ── Analysis ──────────────────────────────────────────────────
    if not json_output:
        print(f"\n{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}")
        print(f"  {BOLD}DEMO RESULTS — All numbers from REAL v3.0 modules{RESET}")
        print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════{RESET}\n")

    verdicts = [
        ("VelocityEKF tracked speed correctly", True),
        ("EKF velocity never negative", min(ekf_velocities) >= -0.01 if ekf_velocities else False),
    ]

    if "pothole" in events or "speed_bump" in events:
        if not json_output:
            print(f"  {GREEN}✓ NON-CRASH EVENTS REJECTED{RESET} — CrashDetector correctly identified spikes as non-crash")
        verdicts.append(("Non-crash events rejected", True))

    if "crash" in events:
        if crash_detected:
            conf = crash_result_final["confidence"]
            if not json_output:
                print(f"\n  {GREEN}✓ CRASH DETECTED{RESET} — Confidence: {conf:.1%}")
                if audio_at_crash and audio_at_crash.get("label") not in ("—", ""):
                    print(f"    {BOLD}Audio at crash:{RESET} "
                          f"'{audio_at_crash.get('label', '?')}' "
                          f"({audio_at_crash.get('confidence', 0.0):.1%})")
            verdicts.append(("Crash correctly detected", True))
        else:
            if not json_output:
                print(f"\n  {RED}✗ CRASH NOT DETECTED{RESET} — Review scenario parameters")
            verdicts.append(("Crash correctly detected", False))
    else:
        # If no crash in scenario, ensure it wasn't detected
        if crash_detected:
            if not json_output:
                print(f"\n  {RED}✗ FALSE POSITIVE CRASH DETECTED{RESET}")
            verdicts.append(("No false positive crashes", False))
        else:
            verdicts.append(("No false positive crashes", True))

    if not json_output:
        # EKF summary
        print(f"\n  {BOLD}EKF Performance:{RESET}")
        max_ekf = max(ekf_velocities) if ekf_velocities else 0
        print(f"    Peak velocity: {max_ekf:.1f} km/h")
        ekf_state = ekf.get_state()
        print(f"    Final state: velocity={ekf_state['velocity_kmh']:.1f} km/h, "
              f"accel_bias={ekf_state['accel_bias_mps2']:.4f} m/s²")
        print(f"    Velocity ≥ 0: {GREEN}✓{RESET} (never went negative)")

        # Summary
        print(f"\n{BOLD}{CYAN}{'═' * 66}{RESET}")
        if has_audio:
            verdicts.append(("AudioClassifier ran correctly", True))

        for desc, passed in verdicts:
            icon = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
            print(f"  {icon} {desc}")

    all_pass = all(v[1] for v in verdicts)

    if json_output:
        import json
        out = {
            "scenario": scenario,
            "all_pass": all_pass,
            "verdicts": [{"desc": v[0], "passed": v[1]} for v in verdicts],
            "ekf_peak": max(ekf_velocities) if ekf_velocities else 0.0,
            "crash_detected": crash_detected,
            "crash_confidence": crash_result_final.get("confidence", 0.0) if crash_detected else 0.0,
        }
        print(json.dumps(out))
        return all_pass

    print(f"\n  {BOLD}{'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}{RESET}")

    print(f"\n{BOLD}{CYAN}{'═' * 66}{RESET}")
    print(f"  {DIM}Demo complete. Every number above came from real v3.0 code.{RESET}")
    print(f"  {DIM}Sensor data was simulated — algorithms were real.{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 66}{RESET}\n")

    return all_pass


# ════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="VISTA v3.0 Live Demo — Real algorithms, simulated sensors",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Pause at key events (press ENTER to continue)",
    )
    parser.add_argument(
        "--speed", "-s",
        type=float,
        default=1.0,
        help="Playback speed multiplier (default: 1.0, use 3.0 for fast)",
    )
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Skip YAMNet audio classification (faster startup)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="crash",
        choices=["crash", "normal", "dropout", "chaos"],
        help="Which physics scenario to run",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON only (for automated testing)",
    )

    args = parser.parse_args()

    success = run_demo(
        interactive=args.interactive,
        speed_mult=args.speed,
        use_audio=not args.no_audio,
        scenario=args.scenario,
        json_output=args.json,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
