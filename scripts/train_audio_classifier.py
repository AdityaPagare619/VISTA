"""
VISTA Audio Classifier — YAMNet Transfer Learning Pipeline
============================================================
Extracts 1024-dim embeddings from YAMNet, trains a small
Dense classifier head for VISTA's 6 audio classes.

Requirements (dev machine only):
    pip install tensorflow==2.13.1 librosa soundfile

Deployment (Pi 4):
    pip install tflite-runtime  (Python 3.11+)
    Only needs: yamnet.tflite + vista_classifier.tflite

Architecture:
    Audio (16kHz, 1s) → YAMNet → 1024-dim embedding
    → Dense(128, ReLU) → Dropout(0.3) → Dense(6, Softmax)

Total deployed size: ~15MB (YAMNet) + ~50KB (classifier head)
Inference on Pi 4: ~25ms per 1-second frame
"""

import json
import os
import sys
from pathlib import Path

# Resolve paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
MODELS_DIR = PROJECT_ROOT / "src" / "vista" / "models"
DATA_DIR = PROJECT_ROOT / "data" / "audio"

# Load mel config
MEL_CONFIG_PATH = MODELS_DIR / "mel_config.json"


def check_dependencies():
    """Verify all required packages are installed."""
    missing = []

    try:
        import tensorflow as tf
        tf_version = tf.__version__
        print(f"  TensorFlow: {tf_version}")
        if not tf_version.startswith("2."):
            print(f"  WARNING: Expected TF 2.x, got {tf_version}")
    except ImportError:
        missing.append("tensorflow==2.13.1")

    try:
        import librosa
        print(f"  librosa: {librosa.__version__}")
    except ImportError:
        missing.append("librosa")

    try:
        import soundfile
        print(f"  soundfile: {soundfile.__version__}")
    except ImportError:
        missing.append("soundfile")

    try:
        import numpy as np
        print(f"  numpy: {np.__version__}")
    except ImportError:
        missing.append("numpy")

    if missing:
        print(f"\n  MISSING PACKAGES: {', '.join(missing)}")
        print(f"  Run: pip install {' '.join(missing)}")
        return False
    return True


def scan_audio_data():
    """Scan the data/audio/ directory and report what's available."""
    print("\n  Audio data inventory:")
    total_clips = 0

    if not DATA_DIR.exists():
        print(f"  WARNING: {DATA_DIR} does not exist")
        print("  Run the dataset download steps first")
        return {}

    inventory = {}
    for class_dir in sorted(DATA_DIR.iterdir()):
        if not class_dir.is_dir():
            continue
        # Count audio files
        audio_exts = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
        clips = [f for f in class_dir.iterdir()
                 if f.suffix.lower() in audio_exts]
        count = len(clips)
        total_clips += count
        inventory[class_dir.name] = count

        # Status indicator
        if count >= 200:
            status = "OK"
        elif count >= 50:
            status = "LOW"
        elif count > 0:
            status = "VERY LOW"
        else:
            status = "EMPTY"

        print(f"    {class_dir.name:20s}: {count:5d} clips  [{status}]")

    print(f"\n  Total: {total_clips} clips across {len(inventory)} classes")

    # Check minimum viability
    if total_clips < 100:
        print("\n  NOT ENOUGH DATA for training.")
        print("  Need at least 50 clips per class (300 total for 6 classes)")
        print("  Download NINA and ESC-50 first.")

    return inventory


def extract_embeddings(audio_dir: Path, yamnet_model_path: Path):
    """Extract YAMNet embeddings from all audio files.

    Returns:
        embeddings: np.ndarray of shape (N, 1024)
        labels: list of class names
        files: list of source file paths
    """
    import numpy as np
    import librosa
    import tensorflow as tf

    # Load YAMNet
    print("\n  Loading YAMNet model...")
    interpreter = tf.lite.Interpreter(model_path=str(yamnet_model_path))
    interpreter.allocate_tensors()

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    print(f"  Input shape: {input_details[0]['shape']}")
    print(f"  Output tensors: {len(output_details)}")

    # Load config
    with open(MEL_CONFIG_PATH, "r") as f:
        mel_cfg = json.load(f)
    sr = mel_cfg["sample_rate"]
    window_sec = mel_cfg["window_sec"]
    samples_per_window = int(sr * window_sec)

    all_embeddings = []
    all_labels = []
    all_files = []

    classes = sorted([d.name for d in audio_dir.iterdir() if d.is_dir()])
    print(f"  Classes found: {classes}")

    for class_name in classes:
        class_dir = audio_dir / class_name
        audio_exts = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
        files = [f for f in class_dir.iterdir()
                 if f.suffix.lower() in audio_exts]

        print(f"  Processing {class_name}: {len(files)} files...", end="", flush=True)
        count = 0

        for audio_file in files:
            try:
                # Load and resample to 16kHz mono
                wav, _ = librosa.load(str(audio_file), sr=sr, mono=True)

                # Pad or truncate to window_sec
                if len(wav) < samples_per_window:
                    wav = np.pad(wav, (0, samples_per_window - len(wav)))
                else:
                    wav = wav[:samples_per_window]

                # Normalize to [-1, 1]
                max_val = np.max(np.abs(wav))
                if max_val > 0:
                    wav = wav / max_val

                # Run YAMNet inference
                wav = wav.astype(np.float32)

                # Resize input tensor if needed
                interpreter.resize_tensor_input(
                    input_details[0]['index'], wav.shape
                )
                interpreter.allocate_tensors()
                interpreter.set_tensor(input_details[0]['index'], wav)
                interpreter.invoke()

                # Get embedding (usually the last output tensor)
                # YAMNet outputs: [scores, embeddings, spectrogram]
                if len(output_details) >= 2:
                    embedding = interpreter.get_tensor(
                        output_details[1]['index']
                    )
                else:
                    embedding = interpreter.get_tensor(
                        output_details[0]['index']
                    )

                # Average embeddings across frames
                if embedding.ndim == 2:
                    embedding = np.mean(embedding, axis=0)

                all_embeddings.append(embedding)
                all_labels.append(class_name)
                all_files.append(str(audio_file))
                count += 1

            except Exception as exc:
                print(f"\n    SKIP {audio_file.name}: {exc}")
                continue

        print(f" {count} OK")

    embeddings = np.array(all_embeddings)
    print(f"\n  Total embeddings: {embeddings.shape}")
    return embeddings, all_labels, all_files


def train_classifier(embeddings, labels, classes):
    """Train a small Dense classifier on YAMNet embeddings.

    Architecture: Dense(1024→128, ReLU) → Dropout(0.3) → Dense(N, Softmax)
    Training time: ~5 minutes on CPU.
    """
    import numpy as np
    import tensorflow as tf
    from tensorflow import keras

    # Encode labels
    label_to_idx = {c: i for i, c in enumerate(classes)}
    y = np.array([label_to_idx[l] for l in labels])

    # Shuffle and split
    indices = np.arange(len(y))
    np.random.seed(42)
    np.random.shuffle(indices)

    split = int(0.8 * len(indices))
    train_idx = indices[:split]
    val_idx = indices[split:]

    X_train, y_train = embeddings[train_idx], y[train_idx]
    X_val, y_val = embeddings[val_idx], y[val_idx]

    print(f"\n  Train: {len(X_train)} samples")
    print(f"  Val:   {len(X_val)} samples")
    print(f"  Classes: {classes}")

    # Build model
    model = keras.Sequential([
        keras.layers.Input(shape=(embeddings.shape[1],)),
        keras.layers.Dense(128, activation="relu"),
        keras.layers.Dropout(0.3),
        keras.layers.Dense(len(classes), activation="softmax"),
    ])

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    model.summary()

    # Train
    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=50,
        batch_size=32,
        verbose=1,
    )

    # Report
    val_acc = max(history.history["val_accuracy"])
    print(f"\n  Best validation accuracy: {val_acc:.1%}")

    return model, history


def export_tflite(model, classes):
    """Export the classifier head to TFLite."""
    import tensorflow as tf

    # Convert to TFLite
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]  # int8 quantize
    tflite_model = converter.convert()

    # Save
    output_path = MODELS_DIR / "vista_classifier.tflite"
    output_path.write_bytes(tflite_model)
    size_kb = len(tflite_model) / 1024
    print(f"\n  Classifier exported: {output_path.name} ({size_kb:.1f} KB)")

    # Save class labels
    labels_path = MODELS_DIR / "vista_classes.json"
    with open(labels_path, "w") as f:
        json.dump(classes, f, indent=2)
    print(f"  Labels saved: {labels_path.name}")

    return output_path


def main():
    print("=" * 60)
    print("VISTA Audio Classifier — Training Pipeline")
    print("=" * 60)

    # Step 1: Check dependencies
    print("\n[1/5] Checking dependencies...")
    if not check_dependencies():
        print("\nInstall missing packages and re-run.")
        sys.exit(1)

    # Step 2: Scan audio data
    print("\n[2/5] Scanning audio data...")
    inventory = scan_audio_data()
    if not inventory or sum(inventory.values()) < 100:
        print("\nDownload audio datasets first (see scripts/setup_ml.py)")
        sys.exit(1)

    # Step 3: Extract embeddings
    print("\n[3/5] Extracting YAMNet embeddings...")
    yamnet_path = MODELS_DIR / "yamnet.tflite"
    if not yamnet_path.exists():
        print(f"  ERROR: YAMNet model not found at {yamnet_path}")
        print("  Run: python scripts/setup_ml.py")
        sys.exit(1)

    embeddings, labels, files = extract_embeddings(DATA_DIR, yamnet_path)

    # Step 4: Train classifier
    print("\n[4/5] Training classifier head...")
    classes = sorted(set(labels))
    model, history = train_classifier(embeddings, labels, classes)

    # Step 5: Export
    print("\n[5/5] Exporting to TFLite...")
    export_tflite(model, classes)

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)
    print(f"""
Deploy to Pi:
  1. Copy these files to the Pi:
     - {MODELS_DIR / 'yamnet.tflite'}
     - {MODELS_DIR / 'vista_classifier.tflite'}
     - {MODELS_DIR / 'vista_classes.json'}
     - {MODELS_DIR / 'mel_config.json'}

  2. Install on Pi:
     pip install tflite-runtime

  3. Total deployed size: ~4MB + classifier head
""")


if __name__ == "__main__":
    main()
