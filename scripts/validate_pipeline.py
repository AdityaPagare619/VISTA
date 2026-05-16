"""
VISTA — Pipeline Validation with ESC-50
=========================================
Feed ESC-50 audio through YAMNet to verify the classification
pipeline works end-to-end before touching real crash data.

Tests:
1. Can we load WAV files and resample to 16kHz?
2. Does YAMNet produce correct scores for known sounds?
3. Does our class mapping (YAMNet → VISTA) work?
4. What's the baseline accuracy on clean data?
"""
import csv
import os
import sys
import time
from pathlib import Path

import numpy as np

# TF for YAMNet inference
import tensorflow as tf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "src" / "vista" / "models"
ESC50_DIR = PROJECT_ROOT / "data" / "esc50"

# Map ESC-50 classes to VISTA classes
ESC50_TO_VISTA = {
    "car_horn": "horn",
    "siren": "siren",
    "engine": "normal_driving",  # Engine = vehicle running = normal
    "glass_breaking": "crash",   # Glass breaking often accompanies crashes
}


def load_wav_16k(path: str) -> np.ndarray:
    """Load a WAV file and resample to 16kHz mono."""
    try:
        import soundfile as sf
        wav, sr = sf.read(path, dtype="float32")
    except ImportError:
        import wave
        with wave.open(path, "rb") as w:
            sr = w.getframerate()
            frames = w.readframes(w.getnframes())
            wav = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            if w.getnchannels() == 2:
                wav = wav[::2]  # Take left channel

    # Mono
    if wav.ndim > 1:
        wav = wav.mean(axis=1)

    # Resample to 16kHz if needed
    if sr != 16000:
        # Simple linear interpolation resampling
        duration = len(wav) / sr
        target_len = int(duration * 16000)
        indices = np.linspace(0, len(wav) - 1, target_len)
        wav = np.interp(indices, np.arange(len(wav)), wav)

    # Normalize
    max_val = np.max(np.abs(wav))
    if max_val > 0:
        wav = wav / max_val

    # Truncate/pad to YAMNet input size (15600 samples = 0.975s)
    target_len = 15600
    if len(wav) < target_len:
        wav = np.pad(wav, (0, target_len - len(wav)))
    else:
        wav = wav[:target_len]

    return wav.astype(np.float32)


def main():
    print("=" * 60)
    print("VISTA Pipeline Validation — ESC-50 + YAMNet")
    print("=" * 60)

    # Load YAMNet
    print("\n[1] Loading YAMNet...")
    interp = tf.lite.Interpreter(model_path=str(MODELS_DIR / "yamnet.tflite"))
    interp.allocate_tensors()
    inp_detail = interp.get_input_details()
    out_detail = interp.get_output_details()
    print(f"    Model loaded. Input: {inp_detail[0]['shape']}")

    # Load YAMNet labels
    yamnet_labels = {}
    with open(MODELS_DIR / "yamnet_class_map.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yamnet_labels[int(row["index"])] = row["display_name"]

    # VISTA class mapping (YAMNet index → VISTA class)
    VISTA_MAP = {
        "crash": [463, 420, 460, 437, 434],
        "horn": [302, 312],
        "siren": [317, 318, 319, 390, 391, 316],
        "skidding": [306, 307, 479],
        "thump": [454],
    }

    # Load ESC-50 metadata
    print("\n[2] Loading ESC-50 metadata...")
    meta_file = ESC50_DIR / "meta" / "esc50.csv"
    with open(meta_file, encoding="utf-8") as f:
        esc_meta = list(csv.DictReader(f))

    # Filter to relevant classes
    relevant = [r for r in esc_meta if r["category"] in ESC50_TO_VISTA]
    print(f"    Relevant clips: {len(relevant)}")
    for cat in ESC50_TO_VISTA:
        count = sum(1 for r in relevant if r["category"] == cat)
        print(f"    {cat}: {count} clips -> VISTA '{ESC50_TO_VISTA[cat]}'")

    # Process each clip
    print("\n[3] Running YAMNet inference on ESC-50 clips...")
    results = {"correct": 0, "wrong": 0, "total": 0}
    class_results = {}

    for i, meta in enumerate(relevant):
        filename = meta["filename"]
        expected_esc = meta["category"]
        expected_vista = ESC50_TO_VISTA[expected_esc]

        wav_path = ESC50_DIR / "audio" / filename
        if not wav_path.exists():
            continue

        try:
            wav = load_wav_16k(str(wav_path))

            # YAMNet inference
            interp.resize_tensor_input(inp_detail[0]["index"], wav.shape)
            interp.allocate_tensors()
            interp.set_tensor(inp_detail[0]["index"], wav)
            interp.invoke()

            scores = interp.get_tensor(out_detail[0]["index"])
            mean_scores = scores.mean(axis=0) if scores.ndim == 2 else scores

            # Map to VISTA classes
            vista_scores = {}
            for vcls, yamnet_ids in VISTA_MAP.items():
                vista_scores[vcls] = sum(
                    float(mean_scores[idx]) for idx in yamnet_ids
                    if idx < len(mean_scores)
                )

            # Add "normal" as catch-all
            vista_scores["normal"] = 1.0 - sum(vista_scores.values())

            best_vista = max(vista_scores, key=vista_scores.get)

            # Check if correct
            # Mapping: horn→horn, siren→siren, glass_breaking→crash, engine→normal
            is_correct = False
            if expected_vista == "horn" and best_vista == "horn":
                is_correct = True
            elif expected_vista == "siren" and best_vista == "siren":
                is_correct = True
            elif expected_vista == "crash" and best_vista == "crash":
                is_correct = True
            elif expected_vista == "normal_driving" and best_vista == "normal":
                is_correct = True

            results["total"] += 1
            if is_correct:
                results["correct"] += 1
            else:
                results["wrong"] += 1

            if expected_esc not in class_results:
                class_results[expected_esc] = {"correct": 0, "total": 0}
            class_results[expected_esc]["total"] += 1
            if is_correct:
                class_results[expected_esc]["correct"] += 1

            if (i + 1) % 20 == 0:
                acc = results["correct"] / results["total"] * 100
                print(f"    Processed {i+1}/{len(relevant)} clips... ({acc:.0f}% so far)")

        except Exception as exc:
            print(f"    SKIP {filename}: {exc}")
            continue

    # Report
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    total_acc = results["correct"] / max(results["total"], 1) * 100
    print(f"\nOverall accuracy: {total_acc:.1f}% ({results['correct']}/{results['total']})")

    print("\nPer-class:")
    for cls, r in sorted(class_results.items()):
        acc = r["correct"] / max(r["total"], 1) * 100
        vista_cls = ESC50_TO_VISTA.get(cls, "?")
        print(f"  {cls:20s} -> {vista_cls:15s}: {acc:5.1f}% ({r['correct']}/{r['total']})")

    print(f"\nConclusion: {'PIPELINE WORKS' if total_acc > 40 else 'NEEDS INVESTIGATION'}")
    if total_acc > 70:
        print("  Zero-training direct classification is VIABLE for demo!")
    elif total_acc > 50:
        print("  Marginal. Transfer learning recommended for production.")
    else:
        print("  Transfer learning is REQUIRED. Direct mapping insufficient.")


if __name__ == "__main__":
    main()
