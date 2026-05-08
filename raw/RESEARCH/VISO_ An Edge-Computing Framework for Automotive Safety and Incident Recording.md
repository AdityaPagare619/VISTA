### VISO: An Edge-Computing Framework for Automotive Safety and Incident Recording

##### 1\. Project Background and Objective

The VISO project represents a first-principles engineering response to the increasing complexity of automotive safety and data management. It establishes a robust framework for real-time incident detection and intelligent data routing, prioritising local edge computing to bypass the inherent limitations of cloud-dependent architectures. By processing data at the source, VISO ensures safety-critical responsiveness and data integrity.The primary objectives of the VISO framework include:

* **Local AI Filtering:**  Utilising on-vehicle intelligence to process high-bandwidth sensor streams, ensuring only verified safety incidents trigger external transmission.  
* **Black Box Buffering:**  Implementing a high-frequency telemetry and imagery buffer to preserve the "Perception-to-Control" state during critical high-G events.  
* **Smart Routing:**  Automating the dissemination of incident snapshots to a multi-stakeholder ecosystem via 5G Advanced network protocols.

##### 2\. Industry Context: The Shift to Automotive Edge AI

As automotive Original Equipment Manufacturers (OEMs) transition toward software-defined vehicles, the execution of AI models—known as inference—is shifting from remote data centres to the vehicle edge. According to McKinsey research, this transition is necessitated by the requirement for offline availability in 39% of ADAS and autonomous driving (AD) use cases. VISO addresses the critical trade-offs between latency, privacy, and operational expenditure that cloud-only solutions cannot resolve.**Performance Metrics: Edge vs. Cloud**| Metric | Edge Execution (VISO) | Cloud-Based Execution || \------ | \------ | \------ || **Latency** | 300–700ms | 1000–2200ms || **Operational Requirements** | Reliable offline availability; critical for safety-relevant systems. | Continuous 4G/5G connection; vulnerable to network outages. || **Privacy & Security** | Localised processing; minimises transmission of sensitive personal data. | High user concern regarding the transmission of private communications. |

##### 3\. Hardware Architecture and Sensor Fusion

The VISO hardware stack mirrors the current semiconductor trend towards Heterogeneous Integration and the use of Chiplets to scale performance. While production-grade systems will eventually utilise dedicated Neural Processing Units (NPUs) for energy efficiency—a priority for 35% of industry stakeholders—the initial VISO prototype employs a modular System-on-Chip (SoC) architecture.

1. **Raspberry Pi (Modular SoC):**  Acts as the central hub for local inference. This choice facilitates fast development cycles and the future-proofing of the platform, allowing for the eventual transition to NPUs and advanced packaging technologies.  
2. **Inertial Measurement Unit (IMU):**  Monitors vehicle dynamics to detect high-G incidents (collisions, emergency braking), serving as the primary hardware trigger for the recording system.  
3. **Passive Infrared (PIR) Sensor:**  Complements visual sensors by detecting heat signatures to confirm occupant presence or external human proximity.  
4. **Camera Module:**  Captures the raw visual inputs required for environmental perception and the subsequent generation of incident snapshots.

##### 4\. Local AI Logic: OpenCV Filtering and False Alarm Mitigation

To manage the computational constraints of edge hardware, VISO employs "Lightweight Models" optimised through advanced pruning and simplification techniques. These methods reduce the model footprint on flash memory and RAM while maintaining inference accuracy.The processing pipeline utilizes OpenCV to execute local computer vision logic without the latency overhead of a cloud round-trip. The system performs real-time frame-by-frame analysis to filter out environmental noise and non-critical events. This local filtering directly addresses the concern of high data traffic costs (cited by 6% of stakeholders) by ensuring that only relevant, high-fidelity data is prepared for routing, rather than continuous raw streams.

##### 5\. Crash Black Box: Incident Buffering and Perception-to-Control

In accordance with modern End-to-End (E2E) ADAS concepts, VISO treats the "Perception-to-Control Pipeline" as a unified deep-learning task. Rather than separating sensor modules, the system integrates Camera and IMU data to derive immediate driving actions or "incident snapshots."

* **Continuous Buffering:**  Raw sensor inputs are continuously recorded into a rolling temporary RAM buffer.  
* **Trigger and Commit:**  Upon the detection of a high-G event by the IMU, the system freezes the current buffer and commits the pre- and post-event data to non-volatile flash memory.  
* **Data Preservation:**  This "Black Box" mechanism ensures that the deterministic telemetry leading to an incident is preserved for forensic or safety analysis, even in the event of a total network failure.

##### 6\. Smart Data Routing and Multi-Stakeholder Integration

Following a confirmed incident, VISO executes an intelligent data routing protocol designed for compatibility with 5G Advanced technology (3GPP Release 18 and beyond).

1. **5G Advanced Evolution:**  Release 18 (Rel-18) introduces AI/ML data-driven designs and "Enhanced Sidelink" capabilities. VISO is architected to leverage these features for highly reliable Vehicle-to-Everything (V2X) communication.  
2. **Multi-Stakeholder Routing:**  Following a "Vehicle-Road-Cloud" strategy, VISO routes data to a centralised application accessible by road operators—such as ASFINAG in Austria or Autobahn GmbH in Germany—and "blue light organisations" (emergency services). This integration is essential for the rollout of Cooperative Intelligent Transport Systems (C-ITS).  
3. **Vulnerable Road User (VRU) Protection:**  Industry data indicates that 70% of car accidents involve bicycles or motorcycles. Notably, 72% of motorcycle accidents are attributed to a lack of awareness. VISO provides significant value to safety organisations by prioritising data routing that can alert or protect these high-risk road users.

##### 7\. Global Rollout and Technical Feasibility

The VISO framework is designed to integrate seamlessly into established and emerging global V2X infrastructures:

* **Europe:**  Integration targets the C-Roads platform, currently in "Phase 3: Urban Phase." This phase focuses on city deployments and new stakeholder integration. Currently, approximately 1.5 million vehicles in Europe are already equipped with C-ITS capabilities, primarily on motorways.  
* **USA:**  Commercialisation aligns with the US National Deployment Plan (2028–2036). The plan targets V2X deployment on 20% of the National Highway System by 2028, reaching full deployment by 2036\.  
* **China:**  The framework supports the national "Vehicle-Road-Cloud" strategy, which includes 20 pilot cities dedicated to enhancing Road Side Unit (RSU) coverage and Multi-access Edge Computing (MEC).

##### 8\. Conclusion and Future Evolution

The VISO framework successfully mitigates the decisive industry challenges of latency, privacy, and data cost. By executing inference at the edge, the system achieves sub-700ms response times while ensuring that sensitive driver data remains localised.The future of VISO will track the 3GPP Release 19 and Release 20+ timelines. Within the Rel-18 scope, VISO will integrate into "Green Networks" to optimise energy efficiency—a critical factor for the battery life of Electric Vehicles. As the 5G Advanced ecosystem matures, VISO will evolve to support more complex E2E ADAS models, further reducing the reliance on discrete rule-based processing and enhancing the safety of the global transport network.  
