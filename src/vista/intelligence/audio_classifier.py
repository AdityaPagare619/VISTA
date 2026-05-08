"""
VISTA Audio Classifier
======================
CNN-based crash, siren, and horn detection using TensorFlow Lite.

Runs a pre-trained TFLite model on 1-second audio windows converted
to mel-spectrograms.  If the model file is missing (or inference fails
for any reason), the classifier returns a safe ``("normal", 0.99)``
fallback so the rest of the pipeline can continue operating.

Classes (6-way)
    'normal', 'crash', 'horn',
    'siren_ambulance', 'siren_police', 'siren_fire'
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import yaml
from loguru import logger

# ── Class labels (must match model output order) ────────────────
_CLASS_LABELS: Tuple[str, ...] = (
    "normal",
    "crash",
    "horn",
    "siren_ambulance",
    "siren_police",
    "siren_fire",
)

# ── Mel-spectrogram parameters ──────────────────────────────────
_N_MELS: int = 64
_N_FFT: int = 512
_HOP_LENGTH: int = 256
_TARGET_FRAMES: int = 63  # 1s @ 16 kHz → ~63 mel frames


class AudioClassifier:
    """TFLite CNN inference for environmental audio classification.

    Usage::

        ac = AudioClassifier()
        label, conf = ac.classify(audio_window)
        # → ("crash", 0.92)
    """

    def __init__(self) -> None:
        cfg = self._load_config()
        sensor_cfg = cfg.get("sensors", {}).get("audio", {})
        self._sample_rate: int = int(sensor_cfg.get("sample_rate", 16000))
        self._model_path: str = str(sensor_cfg.get("model_path", "models/audio_cnn.tflite"))

        # Resolve the absolute model path
        package_root = Path(__file__).resolve().parent.parent
        self._model_abs_path: Path = package_root / self._model_path

        self._interpreter: Any = None
        self._input_details: Any = None
        self._output_details: Any = None
        self._model_loaded: bool = False

        self._init_model()
        logger.info(
            f"AudioClassifier initialized | model={self._model_abs_path} | "
            f"loaded={self._model_loaded}"
        )

    # ── Config loading ───────────────────────────────────────────

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        package_root = Path(__file__).resolve().parent.parent
        config_path = package_root / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)  # type: ignore[no-any-return]

    # ── Model initialisation ─────────────────────────────────────

    def _init_model(self) -> None:
        """Load the TFLite model; set ``_model_loaded`` accordingly."""
        if not self._model_abs_path.exists():
            logger.warning(
                f"Audio model not found at {self._model_abs_path} — "
                f"classifier will always return ('normal', 0.99)"
            )
            self._model_loaded = False
            return

        try:
            import tflite_runtime.interpreter as tflite  # type: ignore[import-untyped]

            self._interpreter = tflite.Interpreter(
                model_path=str(self._model_abs_path)
            )
            self._interpreter.allocate_tensors()
            self._input_details = self._interpreter.get_input_details()
            self._output_details = self._interpreter.get_output_details()
            self._model_loaded = True

            # Log expected input shape
            in_shape = self._input_details[0]["shape"] if self._input_details else "?"
            logger.success(
                f"TFLite model loaded | path={self._model_abs_path.name} | "
                f"input_shape={in_shape}"
            )

        except ImportError:
            logger.error("tflite_runtime not installed — classifier will use fallback")
            self._model_loaded = False
        except Exception as exc:
            logger.error(f"Failed to load TFLite model: {exc} — using fallback")
            self._model_loaded = False

    # ── Public API ───────────────────────────────────────────────

    def classify(self, audio_window: np.ndarray) -> Tuple[str, float]:
        """Classify a 1-second audio window.

        Args:
            audio_window: 1D numpy array of ``float32`` samples
                at the configured sample rate (16 kHz by default).
                Values should be in [-1.0, 1.0].

        Returns:
            ``(class_label, confidence)`` tuple.
            Confidence is in [0.0, 1.0].

            If the model is not loaded or inference fails, returns
            ``("normal", 0.99)`` as a safe fallback.
        """
        if not self._model_loaded:
            return ("normal", 0.99)

        try:
            # ── Preprocessing: audio → mel-spectrogram ───────
            mel_spec = self._audio_to_mel(audio_window)

            # ── Reshape for TFLite: (1, height, width, 1) ────
            # Most CNNs expect [batch, freq_bins, time_frames, channels]
            mel_spec = mel_spec.astype(np.float32)
            expected_shape = self._input_details[0]["shape"]
            if len(expected_shape) == 4:
                # NHWC: [1, freq_bins, time_frames, 1]
                mel_spec = np.expand_dims(mel_spec, axis=(0, -1))
            elif len(expected_shape) == 3:
                mel_spec = np.expand_dims(mel_spec, axis=0)
            # else: try as-is

            # ── Inference ────────────────────────────────────
            self._interpreter.set_tensor(
                self._input_details[0]["index"], mel_spec
            )
            self._interpreter.invoke()
            output = self._interpreter.get_tensor(
                self._output_details[0]["index"]
            )
            # output shape: (1, 6) → probabilities per class
            probs = output[0] if output.ndim == 2 else output

            best_idx = int(np.argmax(probs))
            label = _CLASS_LABELS[best_idx]
            confidence = float(probs[best_idx])

            return (label, confidence)

        except Exception as exc:
            logger.warning(f"Audio classification failed: {exc} — returning fallback")
            return ("normal", 0.99)

    # ── Preprocessing ────────────────────────────────────────────

    def _audio_to_mel(self, audio: np.ndarray) -> np.ndarray:
        """Convert raw audio to a normalised mel-spectrogram.

        Args:
            audio: 1D float32 array of sample values in [-1, 1].

        Returns:
            2D array of shape ``(n_mels, n_frames)``, Z-score normalised.
        """
        try:
            import librosa  # type: ignore[import-untyped]

            # Compute mel spectrogram
            mel = librosa.feature.melspectrogram(
                y=audio.astype(np.float64),
                sr=self._sample_rate,
                n_mels=_N_MELS,
                n_fft=_N_FFT,
                hop_length=_HOP_LENGTH,
                power=2.0,
            )

            # Convert to log scale (dB)
            mel_db = librosa.power_to_db(mel, ref=np.max, top_db=80.0)

            # Normalise: Z-score
            mean = np.mean(mel_db)
            std = np.std(mel_db) + 1e-8
            mel_norm = (mel_db - mean) / std

            # Ensure consistent time dimension
            # (pad or truncate to _TARGET_FRAMES)
            if mel_norm.shape[1] < _TARGET_FRAMES:
                pad_width = _TARGET_FRAMES - mel_norm.shape[1]
                mel_norm = np.pad(
                    mel_norm, ((0, 0), (0, pad_width)),
                    mode="constant", constant_values=0.0,
                )
            elif mel_norm.shape[1] > _TARGET_FRAMES:
                mel_norm = mel_norm[:, :_TARGET_FRAMES]

            return mel_norm

        except ImportError:
            logger.warning(
                "librosa not available — falling back to dummy mel spectrogram"
            )
            return np.zeros((_N_MELS, _TARGET_FRAMES), dtype=np.float32)

    # ── Properties ───────────────────────────────────────────────

    @property
    def model_loaded(self) -> bool:
        """``True`` if the TFLite model was loaded successfully."""
        return self._model_loaded

    @property
    def class_labels(self) -> Tuple[str, ...]:
        """Tuple of 6 class label strings recognised by the model."""
        return _CLASS_LABELS
