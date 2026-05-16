"""
VISTA Audio Classifier — Zero-Training YAMNet Inference
========================================================
Uses YAMNet's existing 521 classes directly, mapping them
to VISTA's 6 classes. No training required.

This is the FASTEST path to a working audio classifier.
If accuracy is insufficient (<70%), use the transfer learning
pipeline (train_audio_classifier.py) instead.

YAMNet class mappings to VISTA:
    crash:          [463] Smash/crash, [420] Explosion, [460] Bang,
                    [437] Shatter, [434] Crack
    horn:           [302] Vehicle horn, [312] Air horn/truck horn
    siren:          [317] Police siren, [318] Ambulance, [319] Fire truck,
                    [390] Siren, [391] Civil defense siren,
                    [316] Emergency vehicle
    skidding:       [306] Skidding, [307] Tire squeal, [479] Squeal
    pothole/bump:   [454] Thump/thud (partial — context needed)
    normal:         Everything else below threshold
"""

import csv
import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Class Mapping: YAMNet index → VISTA class ──────────────────

VISTA_CLASS_MAP: Dict[str, List[int]] = {
    "crash": [463, 420, 460, 437, 434],   # Smash, Explosion, Bang, Shatter, Crack
    "horn": [302, 312],                     # Vehicle horn, Air horn
    "siren": [317, 318, 319, 390, 391, 316],  # Police, Ambulance, Fire, Siren, Civil, Emergency
    "skidding": [306, 307, 479],            # Skidding, Tire squeal, Squeal
    "thump": [454],                         # Thump/thud (pothole indicator for audio)
}

# Minimum confidence to consider a YAMNet prediction
MIN_YAMNET_CONFIDENCE = 0.15  # YAMNet scores are distributed, not peaked


class YAMNetDirectClassifier:
    """Direct YAMNet inference without any training.

    Maps YAMNet's 521-class output to VISTA's classes by
    summing probabilities of related YAMNet classes.
    """

    def __init__(self, model_dir: Optional[Path] = None):
        if model_dir is None:
            model_dir = Path(__file__).resolve().parent.parent / "src" / "vista" / "models"

        self._model_path = model_dir / "yamnet.tflite"
        self._labels_path = model_dir / "yamnet_class_map.csv"

        if not self._model_path.exists():
            raise FileNotFoundError(
                f"YAMNet model not found: {self._model_path}\n"
                "Run: python scripts/setup_ml.py"
            )

        # Load class labels
        self._yamnet_labels: Dict[int, str] = {}
        if self._labels_path.exists():
            with open(self._labels_path, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    idx = int(row["index"])
                    self._yamnet_labels[idx] = row["display_name"]

        # Load TFLite model
        self._interpreter = None
        self._load_model()

    def _load_model(self):
        """Load YAMNet TFLite interpreter."""
        try:
            # Try tflite-runtime first (lighter, for Pi)
            import tflite_runtime.interpreter as tflite
            self._interpreter = tflite.Interpreter(
                model_path=str(self._model_path)
            )
        except (ImportError, ValueError):
            try:
                # Fall back to full TensorFlow
                import tensorflow as tf
                self._interpreter = tf.lite.Interpreter(
                    model_path=str(self._model_path)
                )
            except ImportError:
                raise ImportError(
                    "Need either tflite-runtime (Pi) or tensorflow (dev).\n"
                    "Pi:  pip install tflite-runtime\n"
                    "Dev: pip install tensorflow==2.13.1"
                )

        self._interpreter.allocate_tensors()
        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()

    def classify(self, audio_waveform: np.ndarray, sample_rate: int = 16000) -> Dict:
        """Classify a 1-second audio waveform.

        Args:
            audio_waveform: 1D float32 array, values in [-1, 1], 16kHz mono
            sample_rate: Must be 16000

        Returns:
            Dict with:
                label: VISTA class name or "normal"
                confidence: float [0, 1]
                yamnet_top5: list of (class_name, score) for debugging
                vista_scores: dict of VISTA class → aggregated score
        """
        assert sample_rate == 16000, "YAMNet requires 16kHz audio"

        # Ensure correct shape and type
        wav = audio_waveform.astype(np.float32).flatten()

        # Run YAMNet
        self._interpreter.resize_tensor_input(
            self._input_details[0]["index"], wav.shape
        )
        self._interpreter.allocate_tensors()
        self._interpreter.set_tensor(
            self._input_details[0]["index"], wav
        )
        self._interpreter.invoke()

        # Get scores (first output tensor)
        scores = self._interpreter.get_tensor(
            self._output_details[0]["index"]
        )

        # If multiple frames, average across time
        if scores.ndim == 2:
            scores = np.mean(scores, axis=0)

        # Map YAMNet scores to VISTA classes
        vista_scores = {}
        for vista_class, yamnet_indices in VISTA_CLASS_MAP.items():
            # Sum the probabilities of all mapped YAMNet classes
            class_score = sum(
                float(scores[idx]) for idx in yamnet_indices
                if idx < len(scores)
            )
            vista_scores[vista_class] = class_score

        # Find top YAMNet classes (for debugging)
        top5_indices = np.argsort(scores)[-5:][::-1]
        yamnet_top5 = [
            (self._yamnet_labels.get(int(i), f"class_{i}"), float(scores[i]))
            for i in top5_indices
        ]

        # Determine VISTA class
        best_class = max(vista_scores, key=vista_scores.get)
        best_score = vista_scores[best_class]

        if best_score < MIN_YAMNET_CONFIDENCE:
            label = "normal"
            confidence = 1.0 - best_score  # Confidence in normalcy
        else:
            label = best_class
            confidence = min(best_score * 2.0, 1.0)  # Scale up (YAMNet scores are low)

        return {
            "label": label,
            "confidence": round(confidence, 3),
            "vista_scores": {k: round(v, 4) for k, v in vista_scores.items()},
            "yamnet_top5": yamnet_top5,
        }


def test_with_silence():
    """Quick test: classify 1 second of silence. Should be 'normal'."""
    print("Testing with 1 second of silence...")
    wav = np.zeros(16000, dtype=np.float32)

    classifier = YAMNetDirectClassifier()
    result = classifier.classify(wav)

    print(f"  Label: {result['label']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  VISTA scores: {result['vista_scores']}")
    print(f"  YAMNet top-5: {result['yamnet_top5']}")

    assert result["label"] == "normal", f"Silence classified as {result['label']}!"
    print("  PASS: Silence correctly classified as normal")
    return True


def test_with_noise():
    """Test with white noise (should not trigger crash)."""
    print("\nTesting with white noise (1 sec)...")
    rng = np.random.RandomState(42)
    wav = rng.randn(16000).astype(np.float32) * 0.1  # Low-level noise

    classifier = YAMNetDirectClassifier()
    result = classifier.classify(wav)

    print(f"  Label: {result['label']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  VISTA scores: {result['vista_scores']}")

    # White noise should NOT be classified as crash
    assert result["label"] != "crash", "White noise falsely classified as crash!"
    print("  PASS: White noise not classified as crash")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("VISTA — YAMNet Direct Classifier Test")
    print("=" * 60)

    try:
        test_with_silence()
        test_with_noise()
        print("\nAll tests passed!")
    except ImportError as e:
        print(f"\nCannot test: {e}")
        print("Install tensorflow or tflite-runtime first.")
    except Exception as e:
        print(f"\nTest failed: {e}")
