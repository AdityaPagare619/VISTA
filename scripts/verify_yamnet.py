"""Verify YAMNet TFLite model loads and produces inference."""
import numpy as np
import csv

# Use full TF (has newer tf.lite.Interpreter)
import tensorflow as tf
print(f"TensorFlow: {tf.__version__}")

# Load model
interp = tf.lite.Interpreter(model_path="src/vista/models/yamnet.tflite")
interp.allocate_tensors()

inp = interp.get_input_details()
out = interp.get_output_details()
print(f"Input:  shape={inp[0]['shape']} dtype={inp[0]['dtype']}")
for i, o in enumerate(out):
    print(f"Out[{i}]: shape={o['shape']} dtype={o['dtype']}")

# Load labels
labels = {}
with open("src/vista/models/yamnet_class_map.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        labels[int(row["index"])] = row["display_name"]

# Test 1: Silence
print("\n--- Test: 1 second silence ---")
wav = np.zeros(16000, dtype=np.float32)
interp.resize_tensor_input(inp[0]["index"], wav.shape)
interp.allocate_tensors()
interp.set_tensor(inp[0]["index"], wav)
interp.invoke()

scores = interp.get_tensor(out[0]["index"])
print(f"Scores shape: {scores.shape}")
mean_scores = scores.mean(axis=0) if scores.ndim == 2 else scores
top5 = np.argsort(mean_scores)[-5:][::-1]
print("Top-5:")
for idx in top5:
    print(f"  [{idx:3d}] {labels.get(idx, '?'):30s} = {mean_scores[idx]:.4f}")

# Check crash-related scores
crash_ids = [463, 420, 460, 437, 434]  # Smash, Explosion, Bang, Shatter, Crack
crash_score = sum(mean_scores[i] for i in crash_ids if i < len(mean_scores))
print(f"\nCrash aggregate score on silence: {crash_score:.6f} (should be ~0)")

# Test 2: White noise (should not be crash)
print("\n--- Test: 1 second white noise ---")
rng = np.random.RandomState(42)
noise = (rng.randn(16000) * 0.3).astype(np.float32)
interp.resize_tensor_input(inp[0]["index"], noise.shape)
interp.allocate_tensors()
interp.set_tensor(inp[0]["index"], noise)
interp.invoke()

scores2 = interp.get_tensor(out[0]["index"])
mean2 = scores2.mean(axis=0) if scores2.ndim == 2 else scores2
top5_noise = np.argsort(mean2)[-5:][::-1]
print("Top-5:")
for idx in top5_noise:
    print(f"  [{idx:3d}] {labels.get(idx, '?'):30s} = {mean2[idx]:.4f}")

crash_noise = sum(mean2[i] for i in crash_ids if i < len(mean2))
print(f"\nCrash aggregate score on noise: {crash_noise:.6f}")

# Test 3: Simulated impact (sharp spike)
print("\n--- Test: Simulated impact (sharp spike at 0.5s) ---")
impact = np.zeros(16000, dtype=np.float32)
# Create a sharp transient at 0.5s
t = np.arange(0, 0.05, 1/16000)
impact[8000:8000+len(t)] = np.sin(2 * np.pi * 200 * t) * np.exp(-t * 50) * 0.9
interp.resize_tensor_input(inp[0]["index"], impact.shape)
interp.allocate_tensors()
interp.set_tensor(inp[0]["index"], impact)
interp.invoke()

scores3 = interp.get_tensor(out[0]["index"])
mean3 = scores3.mean(axis=0) if scores3.ndim == 2 else scores3
top5_impact = np.argsort(mean3)[-5:][::-1]
print("Top-5:")
for idx in top5_impact:
    print(f"  [{idx:3d}] {labels.get(idx, '?'):30s} = {mean3[idx]:.4f}")

crash_impact = sum(mean3[i] for i in crash_ids if i < len(mean3))
print(f"\nCrash aggregate score on impact: {crash_impact:.6f}")

print("\n=== YAMNet INFERENCE VERIFIED ===")
