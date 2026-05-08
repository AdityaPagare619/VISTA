#!/usr/bin/env python3
"""
VISTA OBD-II Simulator — ELM327-compatible Virtual OBD Port
============================================================
Creates a virtual serial port that mimics an ELM327 OBD-II adapter,
responding to AT commands and PID requests with realistic data.

Designed for classroom demonstrations when no real vehicle is available.

Connection:
    Use socat to create virtual serial pair:
        socat -d -d pty,raw,echo=0,link=/tmp/obd_sim pty,raw,echo=0,link=/tmp/obd_pi

    The simulator listens on /tmp/obd_sim
    The OBDReader connects to /tmp/obd_pi

Scenarios (controlled via serial commands or --scenario flag):
    normal       — Steady driving at ~45 km/h, 2100 RPM
    idle         — Engine idling: 0 km/h, 850 RPM
    accelerating — Gradually increasing speed and RPM
    crash        — Crash sequence: throttle→0, speed→12→0 km/h over 2 seconds

Usage:
    # Start the simulator
    python demo/obd_simulator.py --port /tmp/obd_sim --scenario normal

    # In another terminal, send commands:
    echo "crash" > /tmp/obd_sim
    echo "normal" > /tmp/obd_sim
    echo "idle" > /tmp/obd_sim
"""

from __future__ import annotations

import argparse
import math
import os
import random
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# ── Logging ─────────────────────────────────────────────────────────────
try:
    from loguru import logger

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<cyan>{time:HH:mm:ss}</cyan> | <level>{level: <8}</level> | {message}",
        colorize=True,
    )
except ImportError:
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("obd_sim")  # type: ignore


# ════════════════════════════════════════════════════════════════════════════
# ELM327 AT Commands
# ════════════════════════════════════════════════════════════════════════════

# Standard ELM327 responses
AT_RESPONSES: Dict[str, str] = {
    "ATZ": "ELM327 v1.5",          # Reset
    "ATI": "ELM327 v1.5",          # Device ID
    "ATE0": "OK",                  # Echo off
    "ATE1": "OK",                  # Echo on
    "ATL0": "OK",                  # Linefeed off
    "ATL1": "OK",                  # Linefeed on
    "ATH0": "OK",                  # Headers off
    "ATH1": "OK",                  # Headers on
    "ATS0": "OK",                  # Printing spaces off
    "ATS1": "OK",                  # Printing spaces on
    "ATSP0": "OK",                 # Protocol auto
    "ATSP3": "OK",                 # Protocol ISO 9141-2
    "ATSP6": "OK",                 # Protocol CAN 11-bit 500kbps
    "ATDP": "AUTO, ISO 15765-4 (CAN 11/500)",  # Describe protocol
    "ATDPN": "6",                  # Protocol number
    "ATRV": "14.2V",               # Voltage reading
    "ATIGN": "ON",                 # Ignition status
    "AT@1": "VISTA OBD SIMULATOR v1.0",  # Device description
    "ATST": "62",                  # Max response time
    "ATH": "OK",                   # Headers off
}

# OBD-II Mode 01 PID data
# Each PID returns a formula component that gets computed at query time
# PID: (bytes_expected, description, formula returning str)


class OBDDataStore:
    """Thread-safe OBD-II data store for simulated PID values."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: Dict[str, float] = {
            "speed": 45.0,         # km/h
            "rpm": 2100.0,         # RPM
            "throttle": 25.0,      # % (0-100)
            "engine_load": 35.0,   # %
            "coolant_temp": 87.0,  # °C
            "fuel_level": 65.0,    # %
            "intake_temp": 32.0,   # °C
            "maf": 15.5,           # g/s
            "timing": 12.0,        # degrees advance
            "o2_voltage": 0.65,    # V (sensor 1)
            "o2_voltage_s2": 0.55, # V (sensor 2)
            "fuel_pressure": 380.0, # kPa
            "runtime": 3600.0,     # seconds since start
        }

    def get(self, key: str) -> float:
        with self._lock:
            return self._data.get(key, 0.0)

    def set(self, key: str, value: float) -> None:
        with self._lock:
            self._data[key] = value

    def get_all(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._data)


# ── PID Response Formatters ──────────────────────────────────────────────

def _format_pid_response(data: OBDDataStore, _pid: str) -> Optional[str]:
    """Map PID request to response byte string.

    Returns hex bytes for the requested PID, or None if unknown.
    The bytes follow SAE J1979 encoding.

    PID hex → (A, B, C, D formula) where value = (A * 256 + B) / scale + offset
    """
    pid = _pid.upper().strip()

    responses: Dict[str, str] = {
        "010C": lambda: _rpm_hex(data.get("rpm")),        # Engine RPM
        "010D": lambda: _speed_hex(data.get("speed")),    # Vehicle Speed
        "0111": lambda: _throttle_hex(data.get("throttle")),  # Throttle Position
        "0104": lambda: _load_hex(data.get("engine_load")),    # Engine Load
        "0105": lambda: _temp_hex(data.get("coolant_temp")),   # Coolant Temp
        "010F": lambda: _temp_hex(data.get("intake_temp")),    # Intake Air Temp
        "0110": lambda: _maf_hex(data.get("maf")),              # MAF Air Flow
        "010A": lambda: _fuel_pressure_hex(data.get("fuel_pressure")),  # Fuel Pressure
        "010E": lambda: _timing_hex(data.get("timing")),        # Timing Advance
        "0114": lambda: _o2_hex(data.get("o2_voltage")),        # O2 Sensor 1
        "0115": lambda: _o2_hex(data.get("o2_voltage_s2")),     # O2 Sensor 2
        "011F": lambda: _runtime_hex(data.get("runtime")),      # Run Time
        "012F": lambda: _fuel_hex(data.get("fuel_level")),      # Fuel Level
        "0100": lambda: "BE 3F B8 10",     # Supported PIDs 01-20
        "0120": lambda: "80 11 00 01",     # Supported PIDs 21-40
    }

    if pid in responses:
        try:
            result = responses[pid]()
            if callable(result) and not isinstance(result, str):
                result = result()
            return str(result)
        except Exception as exc:
            logger.debug(f"PID {pid} formatter error: {exc}")
            return "NO DATA"
    return None


def _rpm_hex(rpm: float) -> str:
    """RPM = (A * 256 + B) / 4"""
    val = int(rpm * 4)
    a = (val >> 8) & 0xFF
    b = val & 0xFF
    return f"{a:02X} {b:02X}"


def _speed_hex(speed: float) -> str:
    """Speed in km/h = A (single byte)"""
    return f"{int(speed):02X}"


def _throttle_hex(throttle: float) -> str:
    """Throttle % = A * 100 / 255"""
    val = int(throttle * 255 / 100)
    return f"{val:02X}"


def _load_hex(load: float) -> str:
    """Engine load % = A * 100 / 255"""
    val = int(load * 255 / 100)
    return f"{val:02X}"


def _temp_hex(temp_c: float) -> str:
    """Temperature °C = A - 40"""
    val = int(temp_c + 40)
    return f"{val:02X}"


def _maf_hex(maf: float) -> str:
    """MAF g/s = (A * 256 + B) / 100"""
    val = int(maf * 100)
    a = (val >> 8) & 0xFF
    b = val & 0xFF
    return f"{a:02X} {b:02X}"


def _fuel_pressure_hex(pressure_kpa: float) -> str:
    """Fuel pressure kPa = A * 3"""
    val = int(pressure_kpa / 3)
    return f"{val:02X}"


def _timing_hex(timing_deg: float) -> str:
    """Timing advance ° = A / 2 - 64"""
    val = int((timing_deg + 64) * 2)
    return f"{val:02X}"


def _o2_hex(voltage: float) -> str:
    """O2 voltage V = A * 0.005 (first byte), B * 100 / 128 (short term fuel trim)"""
    o2_val = int(voltage / 0.005)
    stft = 128  # 0% trim
    return f"{o2_val:02X} {stft:02X}"


def _runtime_hex(seconds: float) -> str:
    """Runtime seconds = (A * 256 + B)"""
    val = int(seconds)
    a = (val >> 8) & 0xFF
    b = val & 0xFF
    return f"{a:02X} {b:02X}"


def _fuel_hex(level_pct: float) -> str:
    """Fuel level % = A * 100 / 255"""
    val = int(level_pct * 255 / 100)
    return f"{val:02X}"


# ════════════════════════════════════════════════════════════════════════════
# DTC Simulation
# ════════════════════════════════════════════════════════════════════════════

DTC_DATABASE: Dict[str, str] = {
    "P0300": "Random/Multiple Cylinder Misfire Detected",
    "P0301": "Cylinder 1 Misfire Detected",
    "P0420": "Catalyst System Efficiency Below Threshold",
    "P0171": "System Too Lean (Bank 1)",
    "P0172": "System Too Rich (Bank 1)",
    "P0455": "Evaporative Emission System Leak Detected (Large)",
    "P0135": "O2 Sensor Heater Circuit (Bank 1 Sensor 1)",
    "P0700": "Transmission Control System Malfunction",
    "P0500": "Vehicle Speed Sensor Malfunction",
    "U0100": "Lost Communication With ECM/PCM",
}

# Active DTCs during different scenarios
CRASH_DTCS = ["P0300", "P0135"]
NORMAL_DTCS: list = []


# ════════════════════════════════════════════════════════════════════════════
# Simulator Core
# ════════════════════════════════════════════════════════════════════════════

class OBD2Simulator:
    """Virtual ELM327 OBD-II adapter over a serial port.

    Responds to AT commands, OBD-II PID requests, and scenario commands.
    Accepts text commands on the serial port line for scenario changes.
    """

    def __init__(self, port: str, scenario: str = "normal") -> None:
        self.port = port
        self.scenario = scenario
        self.data = OBDDataStore()
        self.running = True
        self._reader_thread: Optional[threading.Thread] = None
        self._command_thread: Optional[threading.Thread] = None

        # Scenario state
        self._crash_phase = -1  # -1 = inactive, 0..= active
        self._crash_start_time = 0.0
        self._start_time = time.time()

        # Protocol state
        self._echo = True
        self._headers = False
        self._protocol = "6"  # CAN 11/500

        # Serial file descriptor
        self._fd: Any = None

        logger.info(
            f"OBD2Simulator initialized | port={port} | scenario={scenario}"
        )

    # ── Scenario Commands ────────────────────────────────────────────────

    def set_scenario(self, scenario: str) -> None:
        """Change the current simulation scenario."""
        valid = ("normal", "idle", "accelerating", "crash")
        if scenario not in valid:
            logger.warning(f"Unknown scenario '{scenario}' — ignoring")
            return
        self.scenario = scenario
        self._crash_phase = -1
        logger.info(f"Scenario changed to: {scenario}")
        if scenario == "crash":
            self._crash_phase = 0
            self._crash_start_time = time.time()
            logger.warning("🚨 CRASH SEQUENCE STARTED")

    def _update_scenario_data(self) -> None:
        """Update simulated OBD data based on current scenario."""
        elapsed = time.time() - self._start_time
        wave = math.sin(elapsed * 0.3)  # Gentle sine wave for realism

        if self.scenario == "normal":
            self.data.set("speed", 45.0 + wave * 5.0)
            self.data.set("rpm", 2100.0 + wave * 200.0)
            self.data.set("throttle", 25.0 + wave * 5.0)
            self.data.set("engine_load", 35.0 + wave * 8.0)
            self.data.set("coolant_temp", 87.0 + wave * 2.0)

        elif self.scenario == "idle":
            self.data.set("speed", max(0.0, wave * 1.0))
            self.data.set("rpm", 850.0 + random.uniform(-30, 30))
            self.data.set("throttle", 12.0 + wave * 2.0)
            self.data.set("engine_load", 18.0 + wave * 3.0)
            self.data.set("coolant_temp", 82.0 + wave * 1.0)

        elif self.scenario == "accelerating":
            t = elapsed % 20.0  # 20-second cycle
            if t < 5.0:
                # Ramp up
                frac = t / 5.0
                self.data.set("speed", frac * 80.0)
                self.data.set("rpm", 1000.0 + frac * 3000.0)
                self.data.set("throttle", 30.0 + frac * 50.0)
            elif t < 10.0:
                # Hold at max
                self.data.set("speed", 80.0 + wave * 3.0)
                self.data.set("rpm", 4000.0 + wave * 200.0)
                self.data.set("throttle", 80.0 + wave * 10.0)
            elif t < 15.0:
                # Decelerate
                frac = (t - 10.0) / 5.0
                self.data.set("speed", 80.0 * (1.0 - frac))
                self.data.set("rpm", 4000.0 * (1.0 - frac) + 800.0)
                self.data.set("throttle", 15.0)
            else:
                # Idle
                self.data.set("speed", 0.0)
                self.data.set("rpm", 850.0)
                self.data.set("throttle", 12.0)

        elif self.scenario == "crash":
            self._update_crash_data()

        # Update runtime
        self.data.set("runtime", elapsed)

    def _update_crash_data(self) -> None:
        """Execute crash simulation sequence over ~2 seconds."""
        if self._crash_phase < 0:
            # Before crash: normal driving
            self.data.set("speed", 45.0)
            self.data.set("rpm", 2100.0)
            self.data.set("throttle", 25.0)
            return

        crash_elapsed = time.time() - self._crash_start_time

        if crash_elapsed < 0.5:
            # Phase 0: Normal → throttle snap closed
            self._crash_phase = 0
            self.data.set("throttle", max(0.0, 25.0 * (1.0 - crash_elapsed / 0.5)))
            self.data.set("speed", 45.0)
            self.data.set("rpm", 2100.0)

        elif crash_elapsed < 1.0:
            # Phase 1: Speed dropping rapidly
            self._crash_phase = 1
            frac = (crash_elapsed - 0.5) / 0.5
            self.data.set("throttle", 0.0)
            self.data.set("speed", 45.0 - frac * 33.0)  # 45 → 12 km/h
            self.data.set("rpm", 2100.0 - frac * 1200.0)  # 2100 → 900

        elif crash_elapsed < 2.0:
            # Phase 2: Impact → 0
            self._crash_phase = 2
            frac = (crash_elapsed - 1.0) / 1.0
            self.data.set("throttle", 0.0)
            self.data.set("speed", max(0.0, 12.0 * (1.0 - frac)))
            self.data.set("rpm", max(0.0, 900.0 - frac * 900.0))

        else:
            # Phase 3: Post-crash — vehicle stopped
            self._crash_phase = 3
            self.data.set("throttle", 0.0)
            self.data.set("speed", 0.0)
            self.data.set("rpm", 0.0)
            self.data.set("engine_load", 0.0)
            logger.info("Crash sequence complete — vehicle at rest")

    # ── AT Command Handler ───────────────────────────────────────────────

    def _handle_at_command(self, cmd: str) -> str:
        """Handle ELM327 AT command. Returns response string."""
        cmd_upper = cmd.strip().upper()

        # Exact match
        if cmd_upper in AT_RESPONSES:
            return AT_RESPONSES[cmd_upper]

        # Prefix match (e.g., ATSP6, ATSPA6)
        for at_cmd, response in AT_RESPONSES.items():
            if cmd_upper.startswith(at_cmd):
                return response

        # Common variants
        if cmd_upper.startswith("ATSP"):
            return "OK"
        if cmd_upper.startswith("ATSW"):
            return "OK"
        if cmd_upper.startswith("ATPP"):
            return "OK"
        if cmd_upper in ("AT", ""):
            return "OK"

        logger.debug(f"Unknown AT command: {cmd_upper}")
        return "OK"  # Most ELM327s respond OK to unknown commands

    # ── OBD-II Request Handler ───────────────────────────────────────────

    def _handle_obd_request(self, cmd: str) -> str:
        """Handle OBD-II PID request. Returns hex data or 'NO DATA'."""
        cmd_clean = cmd.strip().upper().replace(" ", "")

        # Standard Mode 01 (Show current data) format: 01 PID
        if len(cmd_clean) >= 4:
            # Construct PID: mode + PID bytes
            pid_key = cmd_clean[:4]  # e.g., "010C" for RPM

            response = _format_pid_response(self.data, pid_key)
            if response:
                # Format with header if enabled
                if self._headers:
                    return f"7E8 06 41 {cmd_clean[2:4]} {response}"
                return f"41 {cmd_clean[2:4]} {response}"

        # Mode 03 (Show DTCs)
        if cmd_clean == "03":
            active_dtcs = CRASH_DTCS if self.scenario == "crash" else NORMAL_DTCS
            if not active_dtcs:
                return "43 00"  # No DTCs
            dtc_bytes = " ".join(
                f"{int(dtc[1:3], 16):02X} {int(dtc[3:5], 16):02X}"
                for dtc in active_dtcs[:2]  # Max 2 DTCs per response
            )
            return f"43 {len(active_dtcs):02X} {dtc_bytes}"

        # Mode 09 (Vehicle info) — VIN request
        if cmd_clean == "0902":
            # Return a fake VIN
            return "49 02 01 56 49 53 54 41 30 30 30 31 32 33 34 35 36"  # VISTA000123456

        logger.debug(f"Unknown OBD request: {cmd_clean}")
        return "NO DATA"

    # ── Line Processing ──────────────────────────────────────────────────

    def _process_line(self, line: str) -> Optional[str]:
        """Process a single line from the serial port.

        Returns response string, or None if no response needed.
        Supports:
            - AT commands (start with "AT")
            - OBD-II requests (hex digits)
            - Text scenario commands: "crash", "normal", "idle", "accelerating"
        """
        line = line.strip()
        if not line:
            return None

        # Check for text scenario commands
        lower = line.lower().strip()
        if lower in ("crash", "normal", "idle", "accelerating"):
            self.set_scenario(lower)
            return f"SCENARIO: {lower.upper()}"

        if lower == "status":
            d = self.data.get_all()
            return (
                f"speed={d['speed']:.1f}km/h rpm={d['rpm']:.0f} "
                f"throttle={d['throttle']:.0f}% scenario={self.scenario}"
            )

        if lower == "dtc":
            active = CRASH_DTCS if self.scenario == "crash" else NORMAL_DTCS
            if not active:
                return "No DTCs"
            return "\n".join(f"{dtc}: {DTC_DATABASE.get(dtc, 'Unknown')}" for dtc in active)

        if lower in ("help", "?"):
            return (
                "VISTA OBD Simulator Commands:\n"
                "  normal, idle, accelerating, crash  — Change scenario\n"
                "  status                               — Show current data\n"
                "  dtc                                  — Show active DTCs\n"
                "  AT commands                          — Standard ELM327\n"
                "  01 PID                               — OBD-II Mode 01\n"
            )

        # AT command
        if line.upper().startswith("AT"):
            return self._handle_at_command(line)

        # OBD-II request (hex)
        # Accept formats: "010C", "01 0C", "010C\r"
        if all(c in "0123456789ABCDEFabcdef " for c in line):
            return self._handle_obd_request(line)

        return "?"  # Unknown command

    # ── Serial Communication ─────────────────────────────────────────────

    def _open_port(self) -> bool:
        """Open the virtual serial port for reading and writing."""
        try:
            import serial
        except ImportError:
            logger.error("pyserial not installed — cannot open port")
            return False

        try:
            self._fd = serial.Serial(
                port=self.port,
                baudrate=38400,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,  # Non-blocking read
                write_timeout=1.0,
            )
            logger.info(f"Port opened: {self.port} @ 38400 8N1")
            return True
        except serial.SerialException as exc:
            logger.error(f"Failed to open port {self.port}: {exc}")
            return False

    def _read_loop(self) -> None:
        """Main read loop — processes incoming serial data."""
        if not self._fd:
            return

        buffer = ""

        while self.running:
            try:
                if self._fd.in_waiting > 0:
                    data = self._fd.read(self._fd.in_waiting)
                    try:
                        text = data.decode("ascii", errors="replace")
                    except Exception:
                        text = data.decode("latin-1", errors="replace")

                    buffer += text

                    # Process complete lines (terminated by \r or \n)
                    while "\r" in buffer or "\n" in buffer:
                        # Split on first terminator
                        split_pos = -1
                        for term in ("\r\n", "\r", "\n"):
                            pos = buffer.find(term)
                            if pos >= 0 and (split_pos < 0 or pos < split_pos):
                                split_pos = pos
                                term_len = len(term)

                        if split_pos < 0:
                            break

                        line = buffer[:split_pos].strip()
                        buffer = buffer[split_pos + 1:]  # len might vary

                        if line:
                            response = self._process_line(line)
                            if response is not None:
                                # ELM327 style: \r-terminated response with prompt
                                self._write_line(response)

                # Small sleep to prevent busy-waiting
                time.sleep(0.001)

            except serial.SerialException as exc:
                logger.error(f"Serial read error: {exc}")
                time.sleep(0.5)
            except Exception as exc:
                logger.error(f"Read loop error: {exc}")
                time.sleep(0.1)

    def _write_line(self, text: str) -> None:
        """Write a response line to the serial port, terminated with \r."""
        if not self._fd:
            return
        try:
            self._fd.write(f"{text}\r".encode("ascii", errors="replace"))
        except Exception as exc:
            logger.debug(f"Write error: {exc}")

    def _update_loop(self) -> None:
        """Background loop that updates scenario data at regular intervals."""
        while self.running:
            self._update_scenario_data()
            time.sleep(0.05)  # 20 Hz update

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the OBD simulator."""
        if not self._open_port():
            logger.warning(
                f"Port {self.port} not available — check socat is running:\n"
                f"  socat -d -d pty,raw,echo=0,link={self.port} pty,raw,echo=0,link=/tmp/obd_pi"
            )
            return

        logger.info(f"VISTA OBD Simulator running on {self.port}")
        logger.info(f"Scenario: {self.scenario}")
        logger.info("Waiting for connections...")

        self._reader_thread = threading.Thread(
            target=self._read_loop, daemon=True, name="obd-reader"
        )
        self._reader_thread.start()

        self._update_thread = threading.Thread(
            target=self._update_loop, daemon=True, name="obd-update"
        )
        self._update_thread.start()

    def stop(self) -> None:
        """Stop the simulator and close the port."""
        self.running = False
        if self._fd:
            try:
                self._fd.close()
            except Exception:
                pass
        logger.info("OBD Simulator stopped")

    def run_forever(self) -> None:
        """Start and block until interrupted."""
        self.start()
        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt")
        finally:
            self.stop()


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="VISTA OBD-II Simulator — Virtual ELM327 adapter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Setup:
    # Create virtual serial pair (in another terminal):
    socat -d -d pty,raw,echo=0,link=/tmp/obd_sim pty,raw,echo=0,link=/tmp/obd_pi

    # Run the simulator:
    python demo/obd_simulator.py --port /tmp/obd_sim --scenario normal

    # Control from another terminal:
    echo "crash" > /tmp/obd_sim
    echo "status" > /tmp/obd_sim
        """,
    )
    parser.add_argument(
        "--port",
        default="/tmp/obd_sim",
        help="Virtual serial port path (default: /tmp/obd_sim)",
    )
    parser.add_argument(
        "--scenario",
        choices=["normal", "idle", "accelerating", "crash"],
        default="normal",
        help="Initial scenario (default: normal)",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()

    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║   VISTA OBD-II Simulator                     ║")
    logger.info("╚══════════════════════════════════════════════╝")

    sim = OBD2Simulator(port=args.port, scenario=args.scenario)
    sim.run_forever()


if __name__ == "__main__":
    main()
