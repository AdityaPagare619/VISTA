### VISO: Integrating 5G-Advanced C-V2X and ML-Based Misbehavior Detection in Software-Defined Vehicle Architectures

##### 1\. Abstract

The VISO project defines a high-performance architectural framework for the next generation of connected mobility, facilitating the industry’s pivot from discrete, rule-based ADAS to holistic Software-Defined Vehicle (SDV) architectures. By integrating 3GPP Release 18 (5G-Advanced), VISO leverages the inaugural wave of "5G-Advanced" innovations to support the stringent throughput and reliability requirements of Cooperative Perception. This implementation utilizes Sidelink communication for real-time sensor sharing, extending the vehicle’s perception horizon beyond line-of-sight. Crucially, the architecture incorporates an ML-based Misbehavior Detection System (MDS) optimized for Neural Processing Units (NPUs). This system performs real-time anomaly detection and malicious data filtering within the critical 300–700ms edge-inference window. By bridging advanced communication protocols with centralized E/E (Electrical/Electronic) compute, VISO addresses the imperative for functional safety, data privacy, and cybersecurity in a multi-agent autonomous ecosystem.

##### 2\. Introduction: The Evolution of Connected Mobility

**The 5G-Advanced Vision**  We are currently navigating a decade-long 5G evolution. While 3GPP Release 15 established the New Radio (NR) foundation, Release 18 (5G-Advanced) represents a second wave of innovation. It strengthens the end-to-end system foundation and facilitates vertical expansion into the automotive domain. This transition is characterized by a shift from purely mobile broadband to a unified, future-proof platform supporting mission-critical V2X (Vehicle-to-Everything) applications.**Industry Drivers**  The shift toward SDV is an architectural response to the consumer-driven requirement for perpetual feature parity. McKinsey data indicates that 38% of premium car owners are willing to switch brands for improved digital experiences—a figure that has more than doubled since 2015\. To meet these demands, the automotive value chain must decouple hardware from software, enabling continuous Over-the-Air (OTA) enhancements.**Core Directive**  This report defines the VISO architecture, a comprehensive project blueprint that bridges the gap between advanced microcomponents (SoCs/NPUs) and high-reliability 5G-Advanced communication protocols.

##### 3\. Software-Defined Vehicle (SDV) Architecture and Edge AI

**Architectural Transition**  Traditional ADAS employs a stochastic-to-deterministic pipeline across discrete ECUs. VISO moves toward "End-to-End (E2E) ADAS," where the perception-to-control pipeline is subsumed by a single deep-learning model. This transition requires centralized E/E architectures that facilitate Hardware-Software decoupling and high-bandwidth cross-domain communication.**The Rise of Edge AI**  For safety-critical ADAS, deterministic performance and minimal latency are non-negotiable. VISO prioritizes Edge AI to ensure operational continuity even in zero-connectivity environments.| Parameter | Cloud-based AI | Edge AI || \------ | \------ | \------ || **Latency (ms)** | 1,000 – 2,200 ms | 300 – 700 ms || **Connectivity Requirements** | Constant 4G/5G connection | Functional offline || **Privacy/Security** | Remote data transfer risks | On-vehicle local processing || **Data Traffic Cost** | High (OEM-covered contracts) | Minimal to Zero |  
**Hardware Foundations**  Modern automotive SoCs must balance massive compute-to-data ratios.

* **CPUs:**  Orchestrate system-level tasks and deterministic control logic.  
* **DSPs:**  Historically used for sensor data processing; their role is being subsumed by NPUs as sensor fusion moves toward E2E models.  
* **GPUs:**  Optimized for parallel display rendering but increasingly secondary to NPUs for transformer-based AI inference.  
* **Neural Processing Units (NPUs):**  The cornerstone of the VISO architecture. NPUs provide the energy efficiency required for transformer-based models, driving the 24% annual growth for advanced microcomponents (\<20nm).

##### 4\. 5G-Advanced and C-V2X Integration (3GPP Release 18\)

**Release 18 Technical Foundation**  5G-Advanced introduces significant enhancements to the C-V2X air interface:

* **Advanced MIMO:**  Support for 6/8 Tx uplink to enable 4+ layers per device, providing the necessary throughput for high-resolution sensor sharing in vehicles.  
* **Expanded Sidelink:**  Evolution of direct V2V/V2I communication for improved reliability and IoT relay capabilities.  
* **AI/ML Data-Driven Design:**  Release 18 integrates AI/ML directly into the air interface to optimize network performance and facilitate sophisticated data management.**Enhanced Mobility Management**  To maintain stable connectivity at high velocities, Release 18 introduces Layer 1/2 based inter-cell mobility. This allows for dynamic switching between candidate cells with significantly reduced handover delays compared to traditional Layer 3 procedures.

##### 5\. Cooperative Perception via Sidelink Communication

**Communication Framework**  The VISO project implements a "Vehicle-Road-Cloud" strategy, integrating Vehicle Onboard Units (OBUs) with Road-Side Units (RSUs) and urban service platforms.**Sensor Sharing Mechanisms**  Cooperative perception extends the sensing range by sharing metadata and raw data through standardized messages:

* **Sense Sharing Message (SSM):**  Broadcasts a vehicle’s perception capabilities and available sensor data.  
* **Road Side Message (RSM):**  Infrastructure-to-Vehicle (I2V) transmission providing environmental perception from roadside sensors.**Use Case Implementation**  VISO utilizes V2V direct communication for critical hazard warnings:  
* **BVW / AAW:**  Blind/Abnormal Vehicle Warnings.  
* **EBW / EVW:**  Emergency Brake/Emergency Vehicle Warnings. Cooperative perception is vital for Vulnerable Road User (VRU) safety; currently, 25% of cyclists at junctions are obscured until two seconds before a potential collision.

##### 6\. Machine Learning Misbehavior Detection Systems (MDS)

**The Security Imperative**  Within the Connectivity and Gateway domain, the transition to open V2X ecosystems necessitates advanced intrusion detection to prevent the injection of malicious or spoofed data into the ADAS pipeline.**MDS Functionality and Synergies**  VISO utilizes a specialized MDS that exploits the "AI/ML data-driven design" of Release 18\. By feeding physical and MAC layer signal data directly into NPU-resident transformer models, the system identifies anomalies (e.g., node impersonation or sensor data manipulation) in real-time. The NPU’s efficiency allows the MDS to perform deep packet inspection and behavior analysis within the 300–700ms window without starving primary ADAS tasks of compute resources.**System Constraints**

* **Resource Management:**  Limited automotive RAM and Flash memory necessitate aggressive model pruning.  
* **Energy Consumption:**  Intensive AI compute impacts the range of Battery Electric Vehicles (BEVs).  
* **Deterministic Latency:**  The MDS must neutralizing threats before they propagate to the vehicle's motion planning layer.

##### 7\. Global Rollout Status and Deployment Challenges

Region,Current Infrastructure / Equipped Vehicles,Key Focus  
Europe,1.5M vehicles (VW/Cupra); C-Roads in 21+ countries,"""Urban Phase"": VRU safety (cyclists/motorcycles) and motorway operations."  
USA,"9,300 RSUs (mostly DSRC/ITS-G5); 3,500 planned",USDOT National Deployment Plan; TSP (Transit Signal Priority) and signal preemption.  
China,20 Pilot Cities; L2 vehicles \~55.7%,"""Vehicle Road Cloud Strategy""; C-NCAP 2024 V2X scenarios (SCPO, TSR)."  
Japan,\>500k vehicles; 115 RSUs (760 MHz band),ITS Connect System; Lexus/Toyota standard fitment; emergency disaster measures.  
**Operational Challenges**  In the USA, technical planning is complicated by the FCC's "2nd Report and Order," which reassigns frequency channels. V2X is now restricted to Channel 180 (5.895–5.905 GHz) and Channel 183 (5.905–5.925 GHz). Meanwhile, China faces questions regarding the long-term sustainability of network and electricity fees for massive RSU deployments.

##### 8\. Conclusion and Future Outlook

**Strategic Pivot**  The automotive value chain is consolidating as chipmakers transition into full system providers. Significant M\&A activity, such as Qualcomm’s acquisition of Arriver and Renesas’ acquisition of Reality AI, underscores the move toward vertically integrated, AI-ready platforms.**Final Synthesis**  The VISO project demonstrates that the realization of safe autonomous mobility is predicated on the convergence of SDV frameworks and 5G-Advanced protocols. By offloading AI inference to the edge and securing the V2X data stream via NPU-optimized misbehavior detection, the industry can meet consumer expectations for digital innovation while adhering to the highest standards of functional safety.

##### 9\. References

* Qualcomm, "Setting off the 5G Advanced evolution \- 3GPP Release 18," January 2022\.  
* McKinsey & Company, "The rise of edge AI in automotive," August 2025\.  
* Vector Informatik GmbH, "V2X Worldwide – Status and Outlook 2025," October 2024\.

