### VISO: Software Architecture and AI Logic Report

##### 1\. Architectural Foundation: The Software-Defined Vehicle (SDV) Framework

The VISO architecture mandates a transition from fragmented, rule-based ADAS to a centralized, E/E architecture-driven SDV framework. This shift is not merely a preference but a structural necessity to support the high-compute, cross-domain functionalities required for future autonomy. Successful implementation necessitates an  **empowered E/E architecture function**  within the organization to manage the complexity of unified software layers.**Core Benefits and Requirements of the SDV Shift:**

* **Centralized E/E Architecture:**  Consolidates discrete compute nodes into high-performance controllers, reducing wiring complexity and enabling cross-domain feature orchestration.  
* **Over-the-Air (OTA) Updateability:**  Enables continuous lifecycle management, allowing the deployment of optimized AI models and security patches without hardware intervention.  
* **Middleware-Based Hardware Abstraction:**  Necessitates a robust abstraction layer to  **isolate application logic from the underlying System-on-Chip (SoC) and Board Support Package (BSP)** . This abstraction is critical for achieving "functional scaling," where software remains portable across evolving hardware generations.  
* **Functional Scaling:**  Orchestrates the deployment of increasingly complex AI workloads while maintaining stability across varied vehicle trims.

##### 2\. 5G Advanced Connectivity and V2X Logic (3GPP Release 18\)

The VISO platform utilizes 3GPP Release 18—the "5G Advanced" evolution—to ensure deterministic communication. This release strengthens the end-to-end 5G system, moving beyond basic broadband to support mission-critical vehicular safety.| Feature | Release 18 Enhancement | Architectural Impact || \------ | \------ | \------ || **Advanced DL/UL MIMO** | Supports  **6/8 Tx uplink to enable 4+ layers per device**  specifically for vehicles and industrial hardware. | Enhances the vehicle's capacity to stream high-bandwidth sensor data for collaborative perception. || **Expanded Sidelink** | Extends V2X reliability and facilitates Pedestrian-to-Vehicle (P2V) safety logic. | Critical for protecting Vulnerable Road Users (VRUs) through direct device-to-device positioning. || **Sidelink in Unlicensed Spectrum** | Evolution to address spectrum congestion in dense urban V2X environments. | Orchestrates reliable communication even when primary 5.9 GHz bands reach capacity. || **NR-Light (RedCap) Evolution** | Integration of lower-complexity IoT devices and wearables into the V2X ecosystem. | Incorporates data from simpler sensors and pedestrian wearables into the vehicle’s safety logic. || **Expanded Positioning** | Delivers centimeter-level accuracy for location-based safety services. | Enhances the reliability of intersection movement assist and lane-level navigation. |

##### 3\. Local Edge AI Logic: NPU and MCU Optimization

VISO prioritizes "at-the-edge" execution to ensure functional safety. Framing the latency requirements, we identify a  **"Safety-Critical Threshold"**  of 700ms; any response exceeding this limit is insufficient for deterministic ADAS maneuvers.**Cloud vs. Edge Execution Metrics:**| Requirement | Cloud-Based (1000–2200ms) | Edge-Based (300–700ms) || \------ | \------ | \------ || **Latency** | Exceeds Safety-Critical Threshold. | **Maintains Deterministic Response.** || **Privacy** | Off-vehicle data processing risk. | Data persists within the vehicle perimeter. || **Connectivity** | Requires persistent 5G/4G link. | Full functional availability in offline/tunnel zones. |  
**Hardware Logic and Inference Requirements:**

* **Neural Processing Units (NPUs):**  VISO integrates specialized NPUs to handle intensive AI tasks. NPUs are mandated over traditional GPUs for  **transformer-based neural network architectures**  due to their superior compute-per-watt and parallel processing efficiency.  
* **Microcontrollers (MCUs):**  While NPUs handle heavy inference, modern MCUs are utilized for executing lightweight AI models dedicated to real-time network monitoring and basic safety-critical supervision.  
* **Modular SoC Architectures:**  The design utilizes heterogeneous SoCs that combine CPUs for orchestration, DSPs for raw signal processing, and NPUs for the  **perception-to-control pipeline** .

##### 4\. Machine Learning Misbehavior Detection System (MDS) for V2X Data

By integrating McKinsey’s "Connectivity and Gateway" domain requirements with Vector-specified data streams, the VISO MDS monitors network health and detects data intrusions. This represents a logic shift from rule-based filters to  **End-to-End (E2E) Deep Learning**  models.**MDS Implementation Logic:**

* **Sensor Fusion Inputs:**  The MDS ingests raw data from multiple sources, including  **Road Side Messages (RSM)** ,  **Sense Sharing Messages (SSM)** , and  **Traffic Signal Recognition (TSR)** .  
* **E2E Deep Learning:**  By processing these disparate streams through a single E2E model, the architecture reduces "handover" latency between discrete perception and control components.  
* **Anomaly Detection:**  The system identifies "misbehavior"—such as spoofed RSM messages or inconsistent SSM data—by checking V2X inputs against the local perception-to-control pipeline to identify physical impossibilities or malicious data injections.

##### 5\. Global V2X Rollout and Multi-Regional Compatibility

The architecture is designed to remain standard-compliant across the following global landscapes:

1. **Europe:**  Adheres to the C-Roads "Urban Phase" (since 2024), prioritizing motorway operations and the integration of diverse stakeholders, including emergency and maintenance vehicles.  
2. **USA:**  Targets the USDOT national deployment plan, necessitating V2X on 20% of the National Highway System (NHS) by 2028, with a mandate for full NHS coverage and 5.9 GHz deployment in all 50 states by 2036\.  
3. **China:**  Follows the "Vehicle-Road-Cloud" strategy. VISO must satisfy C-NCAP 2024 scenarios (e.g., Car-to-Car Straight Crossing Path) and prepare for the  **C-NCAP 2027 forecast** , which specifically mandates V2X communication between  **passenger cars and two-wheelers** .  
4. **Japan:**  Integrates with the "ITS Connect" system. The hardware transceiver must support the current  **760 MHz band**  while providing a migration path for the  **planned 5.9 GHz band**  (5.895–5.925 MHz) expansion.

##### 6\. Hardware/Software Stack Integration

The VISO platform requires a multi-layered, future-proofed technology stack:

* **Software Layer**  
* **Real-time Operating System (RTOS):**  For safety-critical ADAS and motion control.  
* **Non-real-time OS:**  Manages infotainment and driver-experience functions.  
* **AI Frameworks & Lifecycle Management:**  Orchestrates model pruning, evaluation, and deployment.  
* **Hardware Layer**  
* **Heterogeneous SoC:**  CPU, DSP, and NPU integration.  
* **Advanced Packaging & Chiplets:**  Facilitates performance scaling by adding specific processing units without a full silicon redesign.  
* **Memory Architecture:**  
* Flash and DRAM for standard operations.  
* **High-Bandwidth Memory (HBM):**  Mandated for the active compute tasks of large-scale AI models to prevent data bottlenecks.

##### 7\. Performance Constraints and Deployment Risks

The following constraints, based on stakeholder concerns, are prioritized in the VISO risk mitigation plan:

* **Resource Constraints (46% of Stakeholders):**  Limited compute power and RAM on-vehicle necessitates aggressive model pruning and lightweight model research to fit within automotive SoC limits.  
* **Energy Consumption (35% of Stakeholders):**  High AI compute loads directly  **impact Battery Electric Vehicle (BEV) range** . Optimization of NPU efficiency is critical to maintain vehicle performance benchmarks.  
* **Data Privacy (20% of Stakeholders):**  As a strategic differentiator for premium buyers, edge execution is mandated to keep personal communications and behavioral data out of the cloud.  
* **OTA Challenges (15% of Stakeholders):**  Managing large AI model updates over-the-air requires advanced delta-update logic to handle software fragmentation and binary size constraints.

