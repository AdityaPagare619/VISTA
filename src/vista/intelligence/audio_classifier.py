"""
VISTA Audio Classifier — YAMNet-Based (v3.0)
==============================================
Uses Google's YAMNet (3.9MB TFLite) for real-time audio classification.
Maps YAMNet's 521 built-in classes to VISTA's 6 operational categories.

v3.0 DESIGN DECISION:
    YAMNet already knows 48 crash-relevant sounds (smash, skid, siren,
    tire screech, glass breaking). Instead of training a custom CNN on
    limited data, we aggregate YAMNet scores into VISTA classes.

    This gives us:
    - Zero training required for baseline operation
    - 521-class generalization (handles sounds we never trained on)
    - 3.9MB total footprint (fits on Pi 4 easily)
    - ~25ms inference per 1-second frame on Pi 4

Fallback chain:
    1. TensorFlow full → tf.lite.Interpreter (dev machine)
    2. tflite-runtime → lightweight Pi deployment
    3. No model found → returns ("normal", 0.0) safely

Classes (6-way VISTA mapping):
    'normal'         — engine, road noise, silence
    'crash'          — impact, smash, glass breaking
    'horn'           — vehicle horn
    'siren'          — ambulance, police, fire
    'harsh_braking'  — tire skid, screech
    'pothole'        — thump (low confidence — hard to distinguish)
"""

from __future__ import annotations

import csv
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml
from loguru import logger


# ── YAMNet class index → VISTA category mapping ─────────────────
# Curated from yamnet_class_map.csv. Each VISTA class maps to
# multiple YAMNet indices whose scores are summed.
_YAMNET_TO_VISTA: Dict[str, List[int]] = {
    "crash": [
        420,  # Crash
        434,  # Smash, crash
        437,  # Breaking
        460,  # Glass
        463,  # Shatter
        # Secondary (lower weight — corroborating signals)
        288,  # Bang
        289,  # Thump, thud
    ],
    "horn": [
        302,  # Vehicle horn, car horn, honking
        312,  # Bicycle bell (close enough for VISTA)
    ],
    "siren": [
        316,  # Emergency vehicle
        317,  # Siren
        318,  # Ambulance (siren)
        319,  # Police car (siren)
        390,  # Fire engine, fire truck (siren)
        391,  # Civil defense siren
    ],
    "harsh_braking": [
        306,  # Skidding
        307,  # Tire squeal
        479,  # Screech
    ],
    "pothole": [
        454,  # Thump, thud (secondary — hard to distinguish)
    ],
}

# Minimum aggregated score to report a non-normal class
_MIN_DETECTION_SCORE = 0.08


class AudioClassifier:
    """YAMNet-based audio classifier for VISTA.

    Thread-safe. Loads YAMNet TFLite model once, runs inference on
    demand. Falls back gracefully if model is missing.

    Usage::

        ac = AudioClassifier()
        label, conf = ac.classify(audio_1sec_16khz)
        # → ("crash", 0.87)
    """

    def __init__(self) -> None:
        cfg = self._load_config()
        sensor_cfg = cfg.get("sensors", {}).get("audio", {})
        self._sample_rate: int = int(sensor_cfg.get("sample_rate", 16000))

        # Resolve model paths relative to vista package root
        package_root = Path(__file__).resolve().parent.parent
        self._yamnet_path: Path = package_root / "models" / "yamnet.tflite"
        self._labels_path: Path = package_root / "models" / "yamnet_class_map.csv"

        self._interpreter: Any = None
        self._input_details: Any = None
        self._output_details: Any = None
        self._yamnet_labels: Dict[int, str] = {}
        self._model_loaded: bool = False
        self._lock = threading.Lock()

        self._init_model()

    # ── Config ───────────────────────────────────────────────────

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        package_root = Path(__file__).resolve().parent.parent
        config_path = package_root / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # ── Model init ───────────────────────────────────────────────

    def _init_model(self) -> None:
        """Load YAMNet TFLite model with fallback chain."""
        if not self._yamnet_path.exists():
            logger.warning(
                f"YAMNet model not found at {self._yamnet_path} — "
                f"audio classifier disabled. Run: python scripts/setup_ml.py"
            )
            return

        # Try TensorFlow full first, then tflite-runtime
        try:
            try:
                import tensorflow as tf
                self._interpreter = tf.lite.Interpreter(
                    model_path=str(self._yamnet_path)
                )
            except ImportError:
                import tflite_runtime.interpreter as tflite
                self._interpreter = tflite.Interpreter(
                    model_path=str(self._yamnet_path)
                )

            self._interpreter.allocate_tensors()
            self._input_details = self._interpreter.get_input_details()
            self._output_details = self._interpreter.get_output_details()
            self._model_loaded = True

            # Load human-readable labels
            if self._labels_path.exists():
                with open(self._labels_path, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        self._yamnet_labels[int(row["index"])] = row["display_name"]

            logger.info(
                f"AudioClassifier ready | model={self._yamnet_path.name} "
                f"({self._yamnet_path.stat().st_size / 1024:.0f} KB) | "
                f"labels={len(self._yamnet_labels)} | "
                f"vista_classes={list(_YAMNET_TO_VISTA.keys())}"
            )

        except Exception as exc:
            logger.error(f"Failed to load YAMNet: {exc}")
            self._model_loaded = False

    # ── Public API ───────────────────────────────────────────────

    def classify(self, audio_window: np.ndarray) -> Tuple[str, float]:
        """Classify a ~1-second audio window.

        Args:
            audio_window: 1D float32 array at 16kHz.
                Values should be in [-1.0, 1.0].
                YAMNet expects 0.975s = 15600 samples.

        Returns:
            (vista_class, confidence) tuple.
            If model not loaded, returns ("normal", 0.0).
        """
        if not self._model_loaded:
            return ("normal", 0.0)

        try:
            with self._lock:
                return self._run_inference(audio_window)
        except Exception as exc:
            logger.warning(f"Audio inference failed: {exc}")
            return ("normal", 0.0)

    def classify_detailed(self, audio_window: np.ndarray) -> Dict[str, Any]:
        """Classify with full detail (for demo/debugging).

        Returns dict with vista_class, confidence, all vista scores,
        top YAMNet class, and raw score breakdown.
        """
        if not self._model_loaded:
            return {
                "vista_class": "normal",
                "confidence": 0.0,
                "vista_scores": {},
                "yamnet_top": "n/a",
                "model_loaded": False,
            }

        try:
            with self._lock:
                return self._run_inference_detailed(audio_window)
        except Exception as exc:
            logger.warning(f"Audio inference failed: {exc}")
            return {
                "vista_class": "normal",
                "confidence": 0.0,
                "error": str(exc),
            }

    # ── Inference internals ──────────────────────────────────────

    def _run_inference(self, wav: np.ndarray) -> Tuple[str, float]:
        """Run YAMNet and map to VISTA class."""
        mean_scores = self._get_yamnet_scores(wav)

        # Aggregate into VISTA classes
        best_class = "normal"
        best_score = 0.0

        for vista_cls, yamnet_indices in _YAMNET_TO_VISTA.items():
            score = sum(
                float(mean_scores[idx])
                for idx in yamnet_indices
                if idx < len(mean_scores)
            )
            if score > best_score:
                best_score = score
                best_class = vista_cls

        if best_score < _MIN_DETECTION_SCORE:
            return ("normal", 0.0)

        # Normalize confidence to [0, 1] — raw YAMNet scores are
        # probabilities across 521 classes, so aggregated sums are small
        confidence = min(best_score * 3.0, 1.0)
        return (best_class, round(confidence, 3))

    def _run_inference_detailed(self, wav: np.ndarray) -> Dict[str, Any]:
        """Full inference with breakdown."""
        mean_scores = self._get_yamnet_scores(wav)

        # VISTA aggregation
        vista_scores = {}
        for vista_cls, yamnet_indices in _YAMNET_TO_VISTA.items():
            vista_scores[vista_cls] = round(sum(
                float(mean_scores[idx])
                for idx in yamnet_indices
                if idx < len(mean_scores)
            ), 4)

        best_class = max(vista_scores, key=vista_scores.get)
        best_score = vista_scores[best_class]

        # Top YAMNet class
        top_idx = int(np.argmax(mean_scores))
        top_label = self._yamnet_labels.get(top_idx, f"class_{top_idx}")

        if best_score < _MIN_DETECTION_SCORE:
            vista_class = "normal"
            confidence = 0.0
        else:
            vista_class = best_class
            confidence = round(min(best_score * 3.0, 1.0), 3)

        return {
            "vista_class": vista_class,
            "confidence": confidence,
            "vista_scores": vista_scores,
            "yamnet_top": top_label,
            "yamnet_top_score": round(float(mean_scores[top_idx]), 4),
            "model_loaded": True,
        }

    def _get_yamnet_scores(self, wav: np.ndarray) -> np.ndarray:
        """Run YAMNet and return mean class scores."""
        wav = wav.astype(np.float32).flatten()

        # YAMNet expects raw waveform, resizable input
        self._interpreter.resize_tensor_input(
            self._input_details[0]["index"], wav.shape
        )
        self._interpreter.allocate_tensors()
        self._interpreter.set_tensor(self._input_details[0]["index"], wav)
        self._interpreter.invoke()

        scores = self._interpreter.get_tensor(
            self._output_details[0]["index"]
        )

        # scores shape: (N_frames, 521) — average across frames
        if scores.ndim == 2:
            return scores.mean(axis=0)
        return scores

    # ── Properties ───────────────────────────────────────────────

    @property
    def model_loaded(self) -> bool:
        return self._model_loaded

    @property
    def class_labels(self) -> Tuple[str, ...]:
        return ("normal", "crash", "horn", "siren", "harsh_braking", "pothole")
