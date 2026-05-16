"""Quick test of the rewritten AudioClassifier."""
import sys
sys.path.insert(0, ".")
import numpy as np
from intelligence.audio_classifier import AudioClassifier

ac = AudioClassifier()
print(f"Model loaded: {ac.model_loaded}")

# Test 1: Silence
silence = np.zeros(15600, dtype=np.float32)
label, conf = ac.classify(silence)
print(f"Silence:  {label} ({conf:.3f})")

# Test 2: White noise
noise = np.random.randn(15600).astype(np.float32) * 0.5
label2, conf2 = ac.classify(noise)
print(f"Noise:    {label2} ({conf2:.3f})")

# Test 3: Synthetic crash (broadband burst with decay)
t = np.arange(15600) / 16000
crash_audio = np.random.randn(15600).astype(np.float32) * 0.8
crash_audio *= np.exp(-t * 8) * (1 - np.exp(-t * 200))  # impact envelope
metal = np.sin(2 * np.pi * 1200 * t) * 0.3 + np.sin(2 * np.pi * 2400 * t) * 0.2
crash_audio += metal.astype(np.float32) * np.exp(-t * 10).astype(np.float32)
label3, conf3 = ac.classify(crash_audio)
print(f"Crash:    {label3} ({conf3:.3f})")

# Test 4: Horn (dual tone)
horn = (np.sin(2*np.pi*400*t)*0.4 + np.sin(2*np.pi*500*t)*0.3).astype(np.float32)
label4, conf4 = ac.classify(horn)
print(f"Horn:     {label4} ({conf4:.3f})")

# Test 5: Detailed output
detail = ac.classify_detailed(crash_audio)
print(f"\nDetailed crash analysis:")
print(f"  VISTA class: {detail['vista_class']}")
print(f"  Confidence:  {detail['confidence']:.3f}")
print(f"  YAMNet top:  {detail['yamnet_top']} ({detail.get('yamnet_top_score', 0):.4f})")
for cls, score in sorted(detail.get("vista_scores", {}).items(), key=lambda x: -x[1]):
    bar = "#" * int(score * 100)
    print(f"  {cls:15s}: {score:.4f} {bar}")
