Here is the smart, cost-effective hardware list that maximizes your Raspberry Pi using first-principles engineering:

* **The Brain:** Your Raspberry Pi (acting as the Edge AI and local processing node).  
* **V2X Connectivity:** A basic Cellular-V2X (C-V2X) module (such as the Qualcomm 9150 used in commercial On-Board Units 1\) or, to keep it strictly within a student budget, a standard Wi-Fi module programmed to simulate DSRC/V2V communication protocols 2\.  
* **Crash & Tilt Detection:** An MPU6050 IMU. It is incredibly cheap but can accurately provide the acceleration and gyroscope data needed to detect crashes, harsh braking, and tow-away tilting.  
* **Smart Vision:** A standard Pi Camera paired with a cheap PIR motion sensor. The PIR acts as a low-power trigger, waking up the Pi to run a lightweight AI model (like a YOLO-variant) on the camera feed to confirm if the motion is a human thief or a false alarm 3\.  
* **Cabin Safety:** A basic DHT11 or DHT22 temperature sensor to monitor for dangerous cabin heat levels.  
* **Location Tracking:** A low-cost GPS module (like the NEO-6M) for geotagging crash and theft events.  
* **Power Persistence:** A simple DIY battery backup circuit or power bank to ensure your "black box" saves critical data even if the car battery is disconnected during a crash.

This stack keeps your Bill of Materials (BOM) strictly optimized while enabling flagship-level logic.  
Should we map out how to wire these sensors to the Pi's GPIO pins, or would you prefer to start outlining the Python code for the camera's AI logic?  
