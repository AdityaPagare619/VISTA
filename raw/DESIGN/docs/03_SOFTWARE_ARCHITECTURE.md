# 03 — Software Architecture Document
## VISTA: Module Design, Class Structure & API Contracts

**Version:** 2.1 | **Status:** Final | **Date:** May 8, 2026

---

## 1. Software Stack Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                                │
│  crash_detector.py  │  theft_detector.py  │  driver_behavior.py        │
│  vehicle_health.py  │  dashboard_server.py│  alert_manager.py           │
├─────────────────────────────────────────────────────────────────────────┤
│                        INTELLIGENCE LAYER                                │
│  fusion_engine.py (EKF)  │  audio_classifier.py (TFLite CNN)            │
│  decision_engine.py       │  cloud_vision.py (Gemini API)               │
├─────────────────────────────────────────────────────────────────────────┤
│                           DATA LAYER                                     │
│  influx_writer.py │  sqlite_manager.py │  file_manager.py               │
├─────────────────────────────────────────────────────────────────────────┤
│                       COMMUNICATION LAYER                                │
│  mqtt_broker.py │  ble_manager.py │  wifi_manager.py │  api_client.py  │
├─────────────────────────────────────────────────────────────────────────┤
│                     HARDWARE ABSTRACTION LAYER                           │
│  obd_reader.py │ imu_reader.py │ audio_capture.py │ camera_capture.py  │
│  gpio_manager.py │ esp32_bridge.py                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                     OPERATING SYSTEM                                     │
│  Raspberry Pi OS (Debian 12 Bookworm) │ Linux Kernel 6.1               │
│  Python 3.11 │ systemd services │ BlueZ │ NetworkManager              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Module Specifications

### 2.1 Hardware Abstraction Layer (HAL)

#### `obd_reader.py`
```python
"""
OBD-II Data Reader using python-OBD library.
Interface: USB ELM327 adapter.
"""

class OBDReader:
    """Reads vehicle data via OBD-II port."""
    
    def __init__(self, port: str = "/dev/ttyUSB0"):
        self.connection = obd.OBD(portstr=port, fast=False)
    
    def is_connected(self) -> bool:
        """Check if OBD-II adapter is connected and vehicle is on."""
        return self.connection.is_connected()
    
    def get_speed(self) -> float:
        """Returns vehicle speed in km/h. None if unavailable."""
        ...
    
    def get_rpm(self) -> float:
        """Returns engine RPM."""
        ...
    
    def get_throttle_position(self) -> float:
        """Returns throttle position (0-100%)."""
        ...
    
    def get_engine_load(self) -> float:
        """Returns engine load (0-100%)."""
        ...
    
    def get_coolant_temp(self) -> float:
        """Returns coolant temperature in °C."""
        ...
    
    def get_dtc_codes(self) -> list[str]:
        """Returns list of Diagnostic Trouble Codes."""
        ...
    
    def get_all_pids(self) -> dict:
        """Returns dict of all available PIDs with values."""
        ...
```

#### `imu_reader.py`
```python
"""
IMU Data Reader using MPU6050 over I2C.
Provides calibrated acceleration and gyroscope data.
"""

class IMUReader:
    """Reads 6-axis IMU data (accelerometer + gyroscope)."""
    
    def __init__(self, bus: int = 1, address: int = 0x68):
        self.mpu = mpu6050(bus, address)
        self.calibrate()
    
    def calibrate(self, samples: int = 100):
        """Calibrate gyroscope offsets."""
        ...
    
    def get_acceleration(self) -> tuple[float, float, float]:
        """Returns (ax, ay, az) in g (9.81 m/s²)."""
        ...
    
    def get_gyroscope(self) -> tuple[float, float, float]:
        """Returns (gx, gy, gz) in °/s."""
        ...
    
    def get_temperature(self) -> float:
        """Returns chip temperature in °C."""
        ...
    
    def get_all(self) -> dict:
        """Returns dict with all IMU readings."""
        ...
```

#### `audio_capture.py`
```python
"""
Audio Capture Pipeline using PyAudio.
16kHz mono, 1-second sliding windows for CNN input.
"""

class AudioCapture:
    """Continuously captures and buffers audio for classification."""
    
    def __init__(self, sample_rate: int = 16000, window_sec: float = 1.0):
        self.rate = sample_rate
        self.window_samples = int(sample_rate * window_sec)
        self.buffer = collections.deque(maxlen=self.window_samples * 2)
    
    def start(self):
        """Start audio capture thread."""
        ...
    
    def get_window(self) -> np.ndarray:
        """Returns latest 1-second audio window as numpy array."""
        ...
    
    def stop(self):
        """Stop capture thread."""
        ...
```

#### `camera_capture.py`
```python
"""
Camera Capture using picamera2.
On-demand image capture for cloud API analysis.
"""

class CameraCapture:
    """Captures images from Pi Camera v3 for vision analysis."""
    
    def __init__(self):
        self.cam = Picamera2()
        config = self.cam.create_still_configuration(
            main={"size": (2304, 1296)}  # ~3MP for API
        )
        self.cam.configure(config)
    
    def capture_jpeg(self, quality: int = 85) -> bytes:
        """Captures a single JPEG image. Returns bytes."""
        ...
    
    def capture_burst(self, count: int = 5, interval_ms: int = 100) -> list[bytes]:
        """Captures burst of images for crash documentation."""
        ...
```

---

### 2.2 Intelligence Layer

#### `fusion_engine.py`
```python
"""
Extended Kalman Filter for sensor fusion.
Fuses OBD-II speed + IMU acceleration for accurate vehicle state estimation.
"""

import numpy as np

class EKFFusion:
    """
    State vector: [velocity, acceleration_bias]
    Measurement: OBD speed, IMU acceleration
    """
    
    def __init__(self, dt: float = 0.1):
        self.dt = dt
        # State: [velocity, accel_bias_x, accel_bias_y]
        self.x = np.zeros(3)
        self.P = np.eye(3) * 0.1  # Initial covariance
        self.Q = np.diag([0.1, 0.01, 0.01])  # Process noise
        self.R = np.diag([1.0, 0.5, 0.5])  # Measurement noise
    
    def predict(self, imu_accel: np.ndarray):
        """Prediction step using IMU acceleration."""
        # Non-linear state transition
        F = np.array([
            [1, self.dt, 0],
            [0, 1, 0],
            [0, 0, 1]
        ])
        # Remove bias from acceleration
        accel_corrected = imu_accel - self.x[1:]
        self.x[0] += accel_corrected[0] * self.dt  # Integrate for velocity
        self.P = F @ self.P @ F.T + self.Q
    
    def update(self, obd_speed: float, imu_ax: float):
        """Update step using OBD-II speed measurement."""
        z = np.array([obd_speed, imu_ax, 0])
        H = np.eye(3)
        y = z - H @ self.x
        S = H @ self.P @ H.T + self.R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x += K @ y
        self.P = (np.eye(3) - K @ H) @ self.P
    
    def get_velocity(self) -> float:
        """Returns fused velocity estimate (km/h)."""
        return self.x[0] * 3.6  # m/s → km/h
    
    def get_jerk(self, prev_accel: float, curr_accel: float) -> float:
        """Compute jerk magnitude (rate of change of acceleration)."""
        return abs(curr_accel - prev_accel) / self.dt
```

#### `audio_classifier.py`
```python
"""
Audio Event Classifier using TFLite.
Classifies 1-second audio windows into: crash, horn, siren, normal.
"""

import tflite_runtime.interpreter as tflite
import numpy as np

class AudioClassifier:
    """Lightweight CNN for real-time audio event classification."""
    
    CLASSES = ['normal', 'crash', 'horn', 'siren_ambulance', 'siren_police', 'siren_fire']
    
    def __init__(self, model_path: str = "models/audio_cnn.tflite"):
        self.interpreter = tflite.Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
    
    def preprocess(self, audio_window: np.ndarray) -> np.ndarray:
        """Convert audio to mel-spectrogram and normalize."""
        mel_spec = librosa.feature.melspectrogram(
            y=audio_window, sr=16000, n_mels=64, 
            n_fft=1024, hop_length=256
        )
        mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)
        mel_spec_db = (mel_spec_db - mel_spec_db.mean()) / mel_spec_db.std()
        return mel_spec_db[np.newaxis, ..., np.newaxis].astype(np.float32)
    
    def classify(self, audio_window: np.ndarray) -> tuple[str, float]:
        """
        Returns (class_label, confidence).
        Example: ("crash", 0.91)
        """
        input_data = self.preprocess(audio_window)
        self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
        self.interpreter.invoke()
        output = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
        
        class_idx = np.argmax(output)
        confidence = float(output[class_idx])
        
        return self.CLASSES[class_idx], confidence
```

#### `decision_engine.py`
```python
"""
Explainable Decision Engine.
Multi-factor confidence scoring with per-sensor evidence.
"""

from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class Evidence:
    sensor: str
    value: float
    threshold: float
    confidence: float
    explanation: str

@dataclass
class Decision:
    is_alert: bool
    event_type: str  # "crash", "theft", "harsh_braking", etc.
    confidence: float
    severity: str  # "critical", "warning", "info"
    evidence: List[Evidence]
    explanation: str

class DecisionEngine:
    """Multi-factor explainable decision engine."""
    
    WEIGHTS = {
        'crash': {'imu_jerk': 0.35, 'obd_throttle': 0.25, 
                  'audio': 0.25, 'vision': 0.15},
        'theft': {'pir': 0.40, 'camera': 0.35, 'ignition': 0.25},
    }
    
    THRESHOLDS = {
        'crash': {'alert': 0.65, 'warning': 0.40},
        'theft': {'alert': 0.70},
    }
    
    def assess_crash(self, sensor_data: dict) -> Decision:
        """Assess crash probability from multi-modal sensor data."""
        evidence = []
        
        # Factor 1: IMU jerk
        jerk = self._compute_jerk(sensor_data['imu'])
        jerk_conf = min(jerk / 5.0, 1.0)  # 5g/s threshold
        evidence.append(Evidence(
            sensor='imu_jerk', value=jerk, threshold=5.0,
            confidence=jerk_conf,
            explanation=f"IMU jerk: {jerk:.1f} g/s (threshold: 5.0)"
        ))
        
        # Factor 2: OBD-II corroboration
        throttle_drop = sensor_data['obd'].get('throttle_drop', 0)
        throttle_conf = min(throttle_drop / 50, 1.0)
        evidence.append(Evidence(
            sensor='obd_throttle', value=throttle_drop, threshold=50,
            confidence=throttle_conf,
            explanation=f"Throttle dropped {throttle_drop}% in 200ms"
        ))
        
        # Factor 3: Audio classification
        audio_class, audio_conf = sensor_data['audio']
        audio_ev_conf = audio_conf if audio_class == 'crash' else 0.0
        evidence.append(Evidence(
            sensor='audio', value=audio_conf, threshold=0.7,
            confidence=audio_ev_conf,
            explanation=f"Audio: '{audio_class}' at {audio_conf:.0%}"
        ))
        
        # Factor 4: Vision API (optional, may be None)
        vision_conf = sensor_data.get('vision', {}).get('hazard_score', 0.0)
        evidence.append(Evidence(
            sensor='vision', value=vision_conf, threshold=0.5,
            confidence=vision_conf,
            explanation=sensor_data.get('vision', {}).get('description', 'No vision data')
        ))
        
        # Weighted fusion
        weights = self.WEIGHTS['crash']
        final_conf = sum(
            weights[e.sensor] * e.confidence 
            for e in evidence if e.sensor in weights
        )
        
        severity = 'critical' if final_conf > 0.65 else \
                   'warning' if final_conf > 0.40 else 'info'
        
        return Decision(
            is_alert=final_conf > self.THRESHOLDS['crash']['alert'],
            event_type='crash',
            confidence=final_conf,
            severity=severity,
            evidence=evidence,
            explanation=self._generate_explanation(evidence, final_conf)
        )
    
    def _compute_jerk(self, imu_data: dict) -> float:
        """Compute jerk magnitude from IMU acceleration history."""
        ...
    
    def _generate_explanation(self, evidence: List[Evidence], conf: float) -> str:
        """Generate human-readable explanation."""
        lines = [f"Event confidence: {conf:.0%}"]
        lines.extend([f"• {e.explanation}" for e in evidence])
        return "\n".join(lines)
```

#### `cloud_vision.py`
```python
"""
Cloud Vision Integration using Google Gemini Vision API.
One API call replaces all local vision models.
"""

import google.generativeai as genai
from PIL import Image
import io

class CloudVisionAnalyzer:
    """Analyzes vehicle camera images using Gemini Vision API."""
    
    PROMPT_TEMPLATE = """
    Analyze this image from a vehicle dashcam in Indian road conditions.
    Provide a structured response with:
    
    1. SCENE_TYPE: [highway/city/rural/parked]
    2. VEHICLES_PRESENT: List with types (car, two-wheeler, auto-rickshaw, truck, bus, etc.)
    3. HAZARDS: List any hazards (accident, barrier, pedestrian, animal, pothole, open manhole, unmarked speed breaker)
    4. ROAD_CONDITION: [good/moderate/poor] with description
    5. SAFETY_RATING: [safe/caution/dangerous] 
    6. HAZARD_SCORE: 0.0 to 1.0 (0 = perfectly safe, 1 = imminent danger)
    7. DESCRIPTION: One-sentence natural language description of the scene
    
    Format as JSON.
    """
    
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
    
    def analyze_scene(self, image_bytes: bytes) -> dict:
        """
        Analyzes scene and returns structured result.
        
        Returns:
            {
                "scene_type": "city",
                "vehicles": ["car", "two-wheeler", "auto-rickshaw"],
                "hazards": ["pothole - left lane"],
                "road_condition": "moderate",
                "safety_rating": "caution",
                "hazard_score": 0.3,
                "description": "Urban road with mixed traffic. Pothole visible in left lane. Two-wheeler 5m ahead."
            }
        """
        image = Image.open(io.BytesIO(image_bytes))
        response = self.model.generate_content([self.PROMPT_TEMPLATE, image])
        return self._parse_response(response.text)
    
    def analyze_crash_scene(self, image_bytes: bytes) -> str:
        """Specialized crash scene analysis."""
        prompt = """
        This is a CRASH SCENE from an Indian vehicle. Analyze:
        - What type of collision occurred?
        - How many vehicles involved?
        - Severity assessment
        - Extracted text from visible license plates if any
        - Any visible injuries or airbag deployment
        """
        image = Image.open(io.BytesIO(image_bytes))
        response = self.model.generate_content([prompt, image])
        return response.text
    
    def _parse_response(self, text: str) -> dict:
        """Parse API response into structured dict."""
        # Extract JSON from response
        ...
```

---

### 2.3 Communication Layer

#### `mqtt_manager.py`
```python
"""
MQTT Communication Manager.
Handles pub/sub messaging between Pi, phone, and cloud.
"""

import paho.mqtt.client as mqtt
import json

class MQTTManager:
    """Manages MQTT communication for alerts and data sync."""
    
    TOPICS = {
        'alert': 'vista/{device_id}/alert',
        'telemetry': 'vista/{device_id}/telemetry',
        'command': 'vista/{device_id}/command',
        'status': 'vista/{device_id}/status',
    }
    
    def __init__(self, device_id: str, broker_host: str = "localhost"):
        self.device_id = device_id
        self.client = mqtt.Client()
        self.client.connect(broker_host, 1883)
    
    def publish_alert(self, decision: dict):
        """Publish alert to phone and cloud."""
        topic = self.TOPICS['alert'].format(device_id=self.device_id)
        payload = json.dumps(decision)
        self.client.publish(topic, payload, qos=1)
    
    def publish_telemetry(self, data: dict):
        """Publish periodic telemetry data."""
        ...
```

#### `alert_manager.py`
```python
"""
Alert Manager.
Routes enriched alerts to multiple channels (WhatsApp, Telegram, MQTT, BLE).
"""

class AlertManager:
    """Routes alerts to appropriate channels based on severity."""
    
    def __init__(self):
        self.channels = {
            'critical': ['whatsapp', 'ble', 'mqtt', 'buzzer'],
            'warning': ['mqtt', 'ble'],
            'info': ['mqtt'],
        }
    
    def send_alert(self, decision: Decision, enriched_description: str = None):
        """Route alert to appropriate channels."""
        channels = self.channels.get(decision.severity, ['mqtt'])
        
        message = self._format_message(decision, enriched_description)
        
        for channel in channels:
            if channel == 'whatsapp':
                self._send_whatsapp(message, decision.image_bytes)
            elif channel == 'ble':
                self._send_ble(message)
            elif channel == 'mqtt':
                self._send_mqtt(message)
            elif channel == 'buzzer':
                self._trigger_buzzer()
```

---

## 3. Systemd Service Definitions

### `/etc/systemd/system/vista-obd.service`
```ini
[Unit]
Description=VISTA OBD-II Reader Service
After=multi-user.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/python3 /home/pi/vista/hal/obd_reader.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Similarly for: `vista-imu`, `vista-audio`, `vista-fusion`, `vista-decision`, `vista-mqtt`, `vista-api`.

---

## 4. Inter-Module Communication

### 4.1 Communication Methods

| From → To | Method | Rationale |
|-----------|--------|-----------|
| HAL → Intelligence | Direct function call (same process) | Low latency needed for fusion |
| Intelligence → Data | Direct function call | Synchronous writes |
| Intelligence → Communication | Event queue (asyncio) | Non-blocking alerts |
| Pi → ESP32 | GPIO signals (WAKE, STATUS) | Simple, reliable |
| Pi → Phone | BLE GATT + MQTT | BLE for low-power; MQTT for rich data |
| Pi → Cloud API | HTTPS REST | Standard, secure |

### 4.2 Inter-Process Communication (if multi-process)

```
                    ┌──────────────────┐
                    │   Shared Memory   │
                    │  (multiprocessing │
                    │   .shared_memory) │
                    └────────┬─────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────┴─────┐       ┌──────┴──────┐      ┌─────┴─────┐
   │ OBD Proc │       │  IMU Proc   │      │Audio Proc │
   │ (10 Hz)  │       │  (100 Hz)   │      │ (25 Hz)   │
   └──────────┘       └─────────────┘      └───────────┘
                             │
                    ┌────────┴─────────┐
                    │  Fusion Proc     │
                    │  (EKF + Decision)│
                    │  (10 Hz output)  │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        [Data Proc]   [Alert Proc]    [API Proc]
        (Influx+SQL)  (MQTT+Buzzer)  (Cloud+BLE)
```

---

## 5. Error Handling Strategy

```python
# Global error handling pattern

class VISTAError(Exception):
    """Base exception for VISTA system."""
    pass

class SensorError(VISTAError):
    """Sensor read failure."""
    pass

class APIError(VISTAError):
    """Cloud API failure."""
    pass

# Example: Graceful sensor degradation
def get_crash_confidence(sensors_available: set):
    weights = DEFAULT_WEIGHTS.copy()
    if 'audio' not in sensors_available:
        # Redistribute audio weight to IMU + OBD
        weights['imu_jerk'] += weights['audio'] * 0.6
        weights['obd_throttle'] += weights['audio'] * 0.4
        del weights['audio']
        logger.warning("Audio unavailable — redistributing weights")
    return weights
```

---

## 6. Configuration Management

```yaml
# /home/pi/vista/config.yaml
device:
  id: "VISTA-0001"
  name: "Maruti Swift VXI"

sensors:
  obd:
    port: "/dev/ttyUSB0"
    baudrate: 38400
  imu:
    bus: 1
    address: 0x68
    sample_rate: 100  # Hz
  audio:
    sample_rate: 16000
    window_sec: 1.0
    model_path: "models/audio_cnn.tflite"
  camera:
    resolution: [2304, 1296]
    quality: 85

fusion:
  dt: 0.1  # seconds
  process_noise: [0.1, 0.01, 0.01]
  measurement_noise: [1.0, 0.5, 0.5]

decision:
  crash_threshold: 0.65
  crash_warning: 0.40
  theft_threshold: 0.70

cloud:
  gemini_api_key: "${GEMINI_API_KEY}"  # From env var
  vision_prompt: "prompts/scene_analysis.txt"

alerts:
  whatsapp:
    enabled: true
    api_key: "${WHATSAPP_API_KEY}"
  telegram:
    enabled: false
  buzzer: true

storage:
  influxdb:
    host: "localhost"
    port: 8086
    database: "vista"
    retention_days: 30
  sqlite:
    path: "/home/pi/vista/data/events.db"
```

---

**Next:** See `04_OPERATIONAL_FLOWS.md` for mode transitions and event sequences.
