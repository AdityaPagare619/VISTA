"""
VISTA Audio Capture Pipeline
============================
Captures 16 kHz mono audio from a USB microphone via PyAudio.
Maintains a 1-second sliding window in a ``collections.deque``
for downstream classification (e.g., crash sound CNN).

Runs capture in a daemon thread; ``get_window()`` returns the
latest window as a numpy float32 array.
"""

import collections
import threading
import time
from typing import Optional

import numpy as np
from loguru import logger

from . import _is_demo_mode, _load_config


class AudioCapture:
    """Captures mono 16 kHz audio in a background thread.

    Maintains a rolling 1-second buffer accessible via ``get_window()``.
    Handles USB microphone disconnection gracefully.
    """

    _CHUNK = 512  # samples per read call

    def __init__(self) -> None:
        cfg = _load_config()
        sensor_cfg = cfg.get("sensors", {}).get("audio", {})

        self._enabled = sensor_cfg.get("enabled", True)
        self._device_index = sensor_cfg.get("device_index", 0)
        self._sample_rate = sensor_cfg.get("sample_rate", 16000)
        self._window_seconds = sensor_cfg.get("window_seconds", 1.0)
        self._channels = sensor_cfg.get("channels", 1)
        self._demo_mode = _is_demo_mode()

        # Sliding window state
        self._window_size = int(self._sample_rate * self._window_seconds)
        self._buffer: collections.deque = collections.deque(
            maxlen=self._window_size + self._CHUNK
        )

        self._running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._pyaudio: Any = None  # pyaudio.PyAudio
        self._stream: Any = None   # pyaudio.Stream
        self._lock = threading.Lock()

        logger.info(
            f"AudioCapture initialized | rate={self._sample_rate}Hz "
            f"channels={self._channels} | window={self._window_seconds}s "
            f"| demo={self._demo_mode}"
        )

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Open the microphone and start the capture thread."""
        if self._running:
            logger.warning("AudioCapture.start() called but already running")
            return

        if not self._enabled:
            logger.info("Audio sensor disabled in config — skipping start")
            return

        if self._demo_mode:
            logger.info("AudioCapture starting in DEMO mode")
            self._running = True
            self._start_demo_thread()
            return

        try:
            import pyaudio  # type: ignore[import-untyped]

            self._pyaudio = pyaudio.PyAudio()
            self._stream = self._pyaudio.open(
                format=pyaudio.paInt16,
                channels=self._channels,
                rate=self._sample_rate,
                input=True,
                input_device_index=self._device_index,
                frames_per_buffer=self._CHUNK,
                stream_callback=None,  # blocking reads from thread
            )
            logger.success(
                f"Audio capture opened | device={self._device_index} "
                f"rate={self._sample_rate}Hz"
            )
        except ImportError:
            logger.error("PyAudio not installed — falling back to demo")
            self._demo_mode = True
        except Exception as exc:
            logger.error(f"Failed to open audio device: {exc} — falling back to demo")
            self._demo_mode = True

        self._running = True
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name="audio-capture",
            daemon=True,
        )
        self._capture_thread.start()

    def stop(self) -> None:
        """Stop capture and release audio resources."""
        if not self._running:
            return

        logger.info("AudioCapture stopping…")
        self._running = False

        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)

        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception as exc:
                    logger.warning(f"Error closing audio stream: {exc}")
                self._stream = None

            if self._pyaudio is not None:
                try:
                    self._pyaudio.terminate()
                except Exception as exc:
                    logger.warning(f"Error terminating PyAudio: {exc}")
                self._pyaudio = None

        self._buffer.clear()
        logger.info("AudioCapture stopped")

    # ── Capture Loop ─────────────────────────────────────────────

    def _capture_loop(self) -> None:
        """Continuously read audio chunks and feed the sliding window."""
        consecutive_errors = 0
        max_errors = 10  # before giving up

        while self._running:
            try:
                with self._lock:
                    if self._stream is None:
                        time.sleep(0.1)
                        continue

                    # Read raw int16 samples
                    raw_data = self._stream.read(
                        self._CHUNK, exception_on_overflow=False
                    )

                # Convert to numpy float32
                samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
                samples /= 32768.0  # Normalise to [-1.0, 1.0]

                self._buffer.extend(samples.tolist())
                consecutive_errors = 0  # Reset on success

            except OSError as exc:
                consecutive_errors += 1
                logger.warning(
                    f"Audio read error (attempt {consecutive_errors}/{max_errors}): {exc}"
                )
                if consecutive_errors >= max_errors:
                    logger.error("Too many audio errors — stopping capture")
                    self._running = False
                    break
                time.sleep(0.5)

            except Exception as exc:
                logger.error(f"Unexpected audio capture error: {exc}")
                time.sleep(0.1)

    # ── Demo Capture ─────────────────────────────────────────────

    def _start_demo_thread(self) -> None:
        self._capture_thread = threading.Thread(
            target=self._demo_loop,
            name="audio-demo",
            daemon=True,
        )
        self._capture_thread.start()

    def _demo_loop(self) -> None:
        """Generate low-level noise to simulate ambient audio."""
        while self._running:
            # White noise at ~-40 dBFS (very quiet ambient)
            noise = np.random.randn(self._CHUNK).astype(np.float32) * 0.01
            self._buffer.extend(noise.tolist())
            time.sleep(self._CHUNK / self._sample_rate)

    # ── Public API ───────────────────────────────────────────────

    def get_window(self) -> np.ndarray:
        """Return the latest 1-second audio window as a numpy float32 array.

        If the buffer is not yet full, returns whatever is available
        (zero-padded on the left to maintain fixed size).
        """
        with self._lock:
            # Snapshot current buffer
            buf_list = list(self._buffer)

        if len(buf_list) == 0:
            return np.zeros(self._window_size, dtype=np.float32)

        if len(buf_list) >= self._window_size:
            # Most recent window_size samples
            return np.array(buf_list[-self._window_size:], dtype=np.float32)

        # Pad with leading zeros to reach window_size
        padded = np.zeros(self._window_size, dtype=np.float32)
        padded[-len(buf_list):] = np.array(buf_list, dtype=np.float32)
        return padded

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def window_duration(self) -> float:
        return self._window_seconds

    @property
    def is_running(self) -> bool:
        return self._running
