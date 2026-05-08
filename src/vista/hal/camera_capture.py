"""
VISTA Camera Capture
====================
Captures JPEG images from a Pi Camera v3 (or compatible) via ``picamera2``.
Supports single-shot JPEG capture and burst mode for crash event recording.

In demo mode, returns a synthetically-generated solid-color test JPEG.
"""

import io
import struct
import threading
import time
from typing import List, Optional

from loguru import logger

from . import _is_demo_mode, _load_config


# ── Demo JPEG Generator ─────────────────────────────────────────
# Constructs a minimal valid baseline grayscale JPEG at 320x240.
# This is used when running without a physical camera (demo_mode).
# See ITU-T T.81 for the JPEG specification used here.

def _build_demo_jpeg(width: int = 320, height: int = 240) -> bytes:
    """Build a valid minimal grayscale JPEG for demo mode.

    Creates a constant mid-gray image using standard JPEG Huffman
    tables (from ITU-T T.81 Annex K).  No external libraries required.
    """

    def _w16(buf: bytearray, val: int) -> None:
        buf.extend(struct.pack(">H", val))

    buf = bytearray()

    # SOI
    buf.extend(b"\xff\xd8")

    # APP0 — JFIF header
    buf.extend(b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")

    # DQT — Quantisation table (all 1 → no compression loss for constant image)
    buf.append(0xFF)
    buf.append(0xDB)
    buf.extend(b"\x00\x43")     # length = 67
    buf.append(0x00)            # table ID 0, precision 8
    for _ in range(64):
        buf.append(0x01)

    # SOF0 — Baseline DCT, 8-bit, grayscale, dimensions
    buf.append(0xFF)
    buf.append(0xC0)
    buf.extend(b"\x00\x0b")     # length = 11
    buf.append(0x08)            # precision = 8
    _w16(buf, height)
    _w16(buf, width)
    buf.append(0x01)            # 1 component
    # Component 1: ID=1, sampling 1×1, quant table 0
    buf.extend(b"\x01\x11\x00")

    # DHT — DC Huffman table (class=0, ID=0)  – ITU-T T.81 K.3.1
    dc_bits = bytes([0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01,
                     0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    dc_vals = bytes([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                     0x08, 0x09, 0x0A, 0x0B])

    buf.append(0xFF)
    buf.append(0xC4)
    buf.extend(b"\x00\x1f")     # length = 31
    buf.append(0x00)            # class=0 (DC), ID=0
    buf.extend(dc_bits)
    buf.extend(dc_vals)

    # DHT — AC Huffman table (class=1, ID=0)  – ITU-T T.81 K.3.2
    ac_bits = bytes([0x00, 0x02, 0x01, 0x03, 0x03, 0x02, 0x04, 0x03,
                     0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D])
    ac_vals = bytes([
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12,
        0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07,
        0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0,
        0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16,
        0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39,
        0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
        0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
        0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
        0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98,
        0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7,
        0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5,
        0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4,
        0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA,
        0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8,
        0xF9, 0xFA,
    ])

    buf.append(0xFF)
    buf.append(0xC4)
    buf.extend(b"\x00\xb5")     # length = 181
    buf.append(0x10)            # class=1 (AC), ID=0
    buf.extend(ac_bits)
    buf.extend(ac_vals)

    # SOS — Start of Scan
    buf.append(0xFF)
    buf.append(0xDA)
    buf.extend(b"\x00\x08")     # length = 8
    buf.append(0x01)            # 1 component
    buf.extend(b"\x01\x00")     # component 1, DC table 0, AC table 0
    buf.extend(b"\x00\x3F\x00") # Ss=0, Se=63, Ah=0, Al=0

    # ── Scan data ────────────────────────────────────────────────
    # For a constant mid-gray (128) image:
    #   DC coefficient = 0 (after level shift -128),
    #   all AC coefficients = 0.
    #
    # Each 8×8 MCU encodes as:
    #   DC Huffman → category 0 → code '00'   (2 bits)
    #   EOB        → code '1010'              (4 bits)
    #   -------------------------------------------------
    #   Total      6 bits per MCU
    #
    # 4 MCUs → 24 bits → 3 bytes:  0x28, 0xA2, 0x8A
    # (verified: 00101000 10100010 10001010 in MSB-first ordering)
    #
    # For width×height:  num_mcus = (ceil(w/8)) * (ceil(h/8))
    # Repeating 3-byte pattern: 0x28, 0xA2, 0x8A

    mcu_w = (width + 7) // 8
    mcu_h = (height + 7) // 8
    num_mcus = mcu_w * mcu_h

    # Four MCUs pack neatly into 3 bytes
    pattern = bytes([0x28, 0xA2, 0x8A])
    full_blocks = num_mcus // 4
    remainder = num_mcus % 4

    for _ in range(full_blocks):
        buf.extend(pattern)

    # Handle remainder MCUs (0-3)
    rem_patterns = {
        0: b"",
        1: bytes([0x2F]),           # 00101111 (2-bit DC + 4-bit EOB + 2-bit pad=11)
        2: bytes([0x28, 0xBF]),     # 00101000 10111111
        3: bytes([0x28, 0xA2, 0xFF]),  # 00101000 10100010 11111111
    }
    buf.extend(rem_patterns[remainder])

    # EOI
    buf.extend(b"\xff\xd9")

    return bytes(buf)


class CameraCapture:
    """Captures JPEG images from a Pi Camera v3 via picamera2.

    Supports single-frame capture and burst mode (multiple frames
    with configurable interval).  Autofocus is enabled automatically.

    In demo mode, returns a synthetically-generated solid-gray test JPEG.
    """

    def __init__(self) -> None:
        cfg = _load_config()
        sensor_cfg = cfg.get("sensors", {}).get("camera", {})

        self._enabled = sensor_cfg.get("enabled", True)
        self._resolution = tuple(sensor_cfg.get("resolution", [2304, 1296]))
        self._quality = sensor_cfg.get("quality", 85)
        self._burst_count = sensor_cfg.get("burst_count", 5)
        self._burst_interval_ms = sensor_cfg.get("burst_interval_ms", 100)
        self._demo_mode = _is_demo_mode()

        self._camera: Any = None  # picamera2.Picamera2
        self._lock = threading.Lock()
        self._running = False

        logger.info(
            f"CameraCapture initialized | res={self._resolution[0]}×"
            f"{self._resolution[1]} | quality={self._quality} | "
            f"burst={self._burst_count}×{self._burst_interval_ms}ms | "
            f"demo={self._demo_mode}"
        )

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Initialise the camera and enable autofocus."""
        if self._running:
            logger.warning("CameraCapture.start() called but already running")
            return

        if not self._enabled:
            logger.info("Camera sensor disabled in config — skipping start")
            return

        if self._demo_mode:
            logger.info("CameraCapture starting in DEMO mode (synthetic images)")
            self._running = True
            return

        try:
            from picamera2 import Picamera2  # type: ignore[import-untyped]
            from libcamera import Transform  # type: ignore[import-untyped]

            self._camera = Picamera2()

            # Build a stills configuration at the target resolution
            config = self._camera.create_still_configuration(
                main={"size": self._resolution},
                transform=Transform(),
            )
            self._camera.configure(config)

            # Enable autofocus if supported
            try:
                self._camera.set_controls({"AfMode": 2})  # Auto / Continuous
                logger.info("Camera autofocus enabled (Continuous AF)")
            except Exception:
                logger.info("Autofocus not available on this camera")

            self._camera.start()
            self._running = True
            logger.success(
                f"Camera started | res={self._resolution[0]}×{self._resolution[1]}"
            )

        except ImportError:
            logger.error("picamera2 not installed — falling back to demo")
            self._demo_mode = True
            self._running = True
        except Exception as exc:
            logger.error(f"Camera init failed: {exc} — falling back to demo")
            self._demo_mode = True
            self._running = True

    def stop(self) -> None:
        """Stop the camera and release resources."""
        if not self._running:
            return

        logger.info("CameraCapture stopping…")
        self._running = False

        with self._lock:
            if self._camera is not None:
                try:
                    self._camera.stop()
                    self._camera.close()
                except Exception as exc:
                    logger.warning(f"Error closing camera: {exc}")
                self._camera = None

        logger.info("CameraCapture stopped")

    # ── Capture Methods ──────────────────────────────────────────

    def capture_jpeg(self, quality: Optional[int] = None) -> bytes:
        """Capture a single JPEG frame.

        Args:
            quality: JPEG quality 1-100 (default from config).

        Returns:
            JPEG-encoded image bytes.
        """
        if quality is None:
            quality = self._quality

        quality = max(1, min(100, quality))

        if self._demo_mode or self._camera is None:
            return _build_demo_jpeg(
                width=self._resolution[0],
                height=self._resolution[1],
            )

        with self._lock:
            try:
                # picamera2: capture to a BytesIO buffer
                import io as _io

                buf = _io.BytesIO()
                self._camera.capture_file(buf, format="jpeg", quality=quality)
                return buf.getvalue()

            except Exception as exc:
                logger.error(f"Camera JPEG capture failed: {exc}")
                # Graceful degradation — return demo image
                self._demo_mode = True
                return _build_demo_jpeg(
                    width=self._resolution[0],
                    height=self._resolution[1],
                )

    def capture_burst(
        self, count: Optional[int] = None, interval_ms: Optional[int] = None
    ) -> List[bytes]:
        """Capture a burst of JPEG frames (e.g., for crash event recording).

        Args:
            count: Number of frames (default from config).
            interval_ms: Delay between frames in ms (default from config).

        Returns:
            List of JPEG-encoded image bytes.
        """
        if count is None:
            count = self._burst_count
        if interval_ms is None:
            interval_ms = self._burst_interval_ms

        frames: List[bytes] = []

        for _ in range(count):
            frame = self.capture_jpeg()
            frames.append(frame)
            if count > 1:
                time.sleep(interval_ms / 1000.0)

        logger.debug(f"Burst captured: {len(frames)} frames")
        return frames

    # ── Properties ───────────────────────────────────────────────

    @property
    def resolution(self) -> tuple:
        return self._resolution

    @property
    def is_running(self) -> bool:
        return self._running
