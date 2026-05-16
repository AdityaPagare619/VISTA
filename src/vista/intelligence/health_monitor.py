"""
VISTA System Health Monitor
===========================
Continuous self-diagnostics for the VISTA real-time pipeline.
Answers the question: "Is the system healthy enough to deploy?"

Checks:
- Sensor liveness (IMU, OBD, Audio)
- Detection capability (What % of capacity is available in degraded mode?)
- EKF convergence (Is velocity reliable?)
- System resources (Memory/Disk usage)
"""

import os
import psutil
import time
from typing import Dict, Any, List

class SystemHealthMonitor:
    def __init__(self):
        self.startup_time = time.time()
        self.last_sensor_updates = {
            "imu": 0.0,
            "obd": 0.0,
            "audio": 0.0
        }
        # Timeouts in seconds before considering a sensor "dead"
        self.timeouts = {
            "imu": 0.5,
            "obd": 2.0,   # OBD is slower (ELM327)
            "audio": 1.5
        }

    def ping_sensor(self, sensor_name: str) -> None:
        """Called when a new reading is received from a sensor."""
        if sensor_name in self.last_sensor_updates:
            self.last_sensor_updates[sensor_name] = time.time()

    def get_live_sensors(self) -> List[str]:
        """Return list of currently active sensors."""
        now = time.time()
        live = []
        for name, last_update in self.last_sensor_updates.items():
            if last_update > 0 and (now - last_update) < self.timeouts[name]:
                live.append(name)
        return live

    def get_detection_capacity(self) -> float:
        """Calculate system capacity based on live sensors.
        IMU is mandatory (45%). Audio adds 30%. OBD adds 15%. Vision 10%.
        Returns percentage 0.0 to 1.0.
        """
        live = self.get_live_sensors()
        if "imu" not in live:
            return 0.0  # System is completely blind without IMU
            
        capacity = 0.45  # IMU base
        if "audio" in live:
            capacity += 0.30
        if "obd" in live:
            capacity += 0.15
            
        # Add 10% for vision if we ever integrate it, cap at 90% for now
        return min(capacity, 0.90)

    def check_ekf_health(self, ekf_state: Dict[str, Any]) -> str:
        """Check if EKF has converged to a reasonable state."""
        # Unreasonable bias
        if abs(ekf_state.get("accel_bias_mps2", 0)) > 2.0:
            return "diverging (high bias)"
            
        # Negative velocity means something broke physically
        if ekf_state.get("velocity_kmh", 0) < -0.1:
            return "error (negative velocity)"
            
        return "converged"

    def get_system_metrics(self) -> Dict[str, Any]:
        """Get OS-level health metrics."""
        try:
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            cpu = psutil.cpu_percent(interval=None)
            
            # Warn if we're swapping heavily
            swap = psutil.swap_memory()
            memory_health = "critical" if swap.percent > 80 else ("warning" if mem.percent > 85 else "ok")
            
            # Disk space for logging
            disk_health = "critical" if disk.percent > 95 else ("warning" if disk.percent > 85 else "ok")
            
            return {
                "cpu_percent": cpu,
                "memory_percent": mem.percent,
                "memory_health": memory_health,
                "disk_percent": disk.percent,
                "disk_health": disk_health,
                "uptime_sec": time.time() - self.startup_time
            }
        except Exception:
            return {"error": "psutil not available"}

    def get_full_health_report(self, ekf_state: Dict[str, Any] = None) -> Dict[str, Any]:
        """Return complete health status payload."""
        live_sensors = self.get_live_sensors()
        capacity = self.get_detection_capacity()
        
        status = "HEALTHY"
        if capacity < 0.5:
            status = "CRITICAL (IMU OFFLINE)"
        elif capacity < 0.8:
            status = "DEGRADED"
            
        ekf_status = self.check_ekf_health(ekf_state) if ekf_state else "unknown"
        if ekf_status != "converged":
            status = "DEGRADED (EKF DIVERGENCE)"

        sys_metrics = self.get_system_metrics()
        if sys_metrics.get("memory_health") == "critical" or sys_metrics.get("disk_health") == "critical":
            status = "CRITICAL (RESOURCE EXHAUSTION)"

        return {
            "overall_status": status,
            "detection_capacity": capacity,
            "live_sensors": live_sensors,
            "dead_sensors": [s for s in self.timeouts.keys() if s not in live_sensors],
            "ekf_status": ekf_status,
            "system": sys_metrics
        }
