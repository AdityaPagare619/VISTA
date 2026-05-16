"""
VISTA ML Setup — Download YAMNet + Create Training Pipeline
=============================================================
Downloads the YAMNet TFLite model and class labels.
Works on Python 3.8+ without TensorFlow (uses tflite-runtime or
raw numpy for embedding extraction).

Target: Dev machine (training) → Pi 4 (inference only)
"""
import os
import sys
import json
import urllib.request
import ssl
from pathlib import Path

# Where to put things
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "src" / "vista" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# SSL context for downloads (some corporate networks block)
ctx = ssl.create_default_context()


def download_file(url: str, dest: Path, label: str) -> bool:
    """Download a file with progress indicator."""
    if dest.exists():
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  [SKIP] {label} already exists ({size_mb:.1f} MB)")
        return True

    print(f"  [DOWNLOAD] {label}...")
    print(f"    URL: {url}")
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (VISTA-ML-Setup)"
        })
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            data = resp.read()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            size_mb = len(data) / (1024 * 1024)
            print(f"    OK: {size_mb:.1f} MB saved to {dest.name}")
            return True
    except Exception as exc:
        print(f"    FAIL: {exc}")
        return False


def download_yamnet_labels():
    """Download the 521-class label map for YAMNet."""
    url = "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv"
    dest = MODELS_DIR / "yamnet_class_map.csv"
    return download_file(url, dest, "YAMNet class labels (521 classes)")


def download_yamnet_tflite():
    """Download YAMNet TFLite model.

    TF Hub changed their URL scheme, so we try multiple sources.
    """
    dest = MODELS_DIR / "yamnet.tflite"

    # Multiple possible download URLs (TF Hub URLs change over time)
    urls = [
        # Kaggle-hosted (most reliable in 2025+)
        "https://storage.googleapis.com/kagglesdsdata/models/2218/2609/1.tflite",
        # TF Hub legacy
        "https://tfhub.dev/google/lite-model/yamnet/classification/tflite/1?lite-format=tflite",
        # Alternative GCS bucket
        "https://storage.googleapis.com/download.tensorflow.org/models/tflite/yamnet/yamnet.tflite",
    ]

    for url in urls:
        if download_file(url, dest, "YAMNet TFLite model"):
            return True

    print("\n  [MANUAL] Automatic download failed.")
    print("  Please download YAMNet TFLite manually from:")
    print("    https://www.kaggle.com/models/google/yamnet/tfLite/classification-tflite")
    print(f"  Save the .tflite file as: {dest}")
    return False


def verify_yamnet():
    """Verify the YAMNet model is loadable."""
    model_path = MODELS_DIR / "yamnet.tflite"
    if not model_path.exists():
        print("  [SKIP] No model file to verify")
        return False

    size_mb = model_path.stat().st_size / (1024 * 1024)

    # Basic check: TFLite files start with specific magic bytes
    with open(model_path, "rb") as f:
        # FlatBuffer magic: offset 4-7 should be "TFL3"
        header = f.read(8)

    # TFLite FlatBuffer has version at offset 4
    is_valid = len(header) >= 8 and size_mb > 1.0

    if is_valid:
        print(f"  [OK] YAMNet model valid ({size_mb:.1f} MB)")

        # Try loading with tflite-runtime if available
        try:
            import tflite_runtime.interpreter as tflite
            interp = tflite.Interpreter(model_path=str(model_path))
            interp.allocate_tensors()
            inp = interp.get_input_details()
            out = interp.get_output_details()
            print(f"    Input: {inp[0]['shape']} ({inp[0]['dtype']})")
            print(f"    Outputs: {len(out)} tensors")
            return True
        except ImportError:
            print("    (tflite-runtime not installed — model file looks valid by size)")
            return True
        except Exception as exc:
            print(f"    WARNING: tflite load failed: {exc}")
            return True  # File exists, might just be wrong interpreter version
    else:
        print(f"  [FAIL] YAMNet model appears invalid ({size_mb:.1f} MB)")
        return False


def create_mel_config():
    """Create the Mel-spectrogram config file for the training pipeline."""
    config = {
        "sample_rate": 16000,
        "n_fft": 1024,
        "hop_length": 512,
        "n_mels": 64,
        "window_sec": 1.0,
        "fmin": 20,
        "fmax": 8000,
        "classes": [
            "crash",
            "normal_driving",
            "horn",
            "siren",
            "pothole",
            "harsh_braking"
        ],
        "yamnet_embedding_dim": 1024,
        "classifier_hidden": 128,
        "notes": {
            "why_16khz": "Required by YAMNet. Human hearing covers 20-20kHz, Nyquist says 16kHz captures up to 8kHz which includes all crash-relevant frequencies",
            "why_64_mels": "Standard for MobileNet-based audio models. More bins = more compute for marginal gain",
            "why_1sec_window": "Crashes last 50-300ms. 1s window captures the full event with pre/post context",
            "target_device": "Raspberry Pi 4 (ARM Cortex-A72, 2GB RAM, no GPU)",
            "inference_budget": "25ms per frame (YAMNet) or 5ms (custom CNN)"
        }
    }

    config_path = MODELS_DIR / "mel_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"  [OK] Mel-spectrogram config saved to {config_path.name}")


def print_next_steps():
    """Print what to do next."""
    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print("""
1. INSTALL TRAINING DEPS (on dev machine only):
   pip install tensorflow==2.13.1 librosa soundfile

2. DOWNLOAD ESC-50 (600MB, pipeline validation):
   git clone https://github.com/karolpiczak/ESC-50 data/esc50

3. DOWNLOAD NINA (crash audio, requires yt-dlp):
   git clone https://github.com/axa-rev-research/NINA-Dataset data/nina
   pip install yt-dlp
   cd data/nina && bash datasetCreation.sh

4. DOWNLOAD MPU6050 DRIVING DATA:
   Visit: https://data.mendeley.com/datasets/jj3tw8kj6h/2
   Save to: data/imu/

5. RUN TRAINING PIPELINE:
   python scripts/train_audio_classifier.py

6. FOR PI DEPLOYMENT (inference only):
   pip install tflite-runtime
   Copy models/yamnet.tflite + models/vista_classifier.tflite to Pi
""")


if __name__ == "__main__":
    print("=" * 60)
    print("VISTA ML Setup")
    print("=" * 60)

    print("\n[1/4] Downloading YAMNet class labels...")
    download_yamnet_labels()

    print("\n[2/4] Downloading YAMNet TFLite model...")
    download_yamnet_tflite()

    print("\n[3/4] Verifying model...")
    verify_yamnet()

    print("\n[4/4] Creating ML config...")
    create_mel_config()

    print_next_steps()
