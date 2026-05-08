### VISO Ecosystem Report: The Evolution of 5G Advanced, Edge AI, and Global V2X Integration

##### 1\. The 5G Advanced Foundation: Setting the Stage for 6G

The telecommunications landscape is currently navigating a pivotal transition from foundational 5G (Releases 15-17) to 5G Advanced, beginning with 3GPP Release 18\. As a technology strategist, it is critical to recognize that Release 18 does more than introduce features; it establishes the "scope" for the coming decade. By defining numerous Study Items (SI) that will mature into Work Items (WI) in later releases, 3GPP is effectively future-proofing the platform for the 2030s and the eventual transition to 6G.

###### *The 3GPP 5G Evolution Path*

Release Number,Primary Focus,Key Technical Features  
Release 15,5G NR Foundation,"eMBB, Sub-6 GHz Massive MIMO, mmWave, Flexible Framework."  
Release 16,Industry Expansion,"C-V2X Sidelink, eURLLC for IIoT, NR in unlicensed spectrum."  
Release 17,Continued Expansion,"NR-Light (RedCap), Non-terrestrial networks (NTN), Enhanced MIMO."  
Release 18+,5G Advanced,"AI/ML data-driven designs, 6/8 Tx Uplink, Evolution of duplexing."

###### *5G Advanced Pillars*

Release 18 drives a balanced evolution across two strategic pillars, ensuring the system can handle the high-throughput requirements of autonomous platforms:

* **Strengthening the System Foundation:**  
* Integration of AI/ML data-driven designs to optimize network performance.  
* Advanced MIMO enhancements and evolved duplexing for spectral efficiency.  
* Introduction of Smart Repeaters and "Green Networks" to prioritize energy efficiency.  
* **Proliferating to New Use Cases:**  
* Evolution of NR-Light (RedCap) for low-complexity IoT expansion.  
* Development of Boundless Extended Reality (XR) and expanded positioning capabilities.  
* Enhancement of Sidelink functionality across virtually all device categories.

##### 2\. MIMO and Uplink Performance: Strengthening the System Core

To achieve VISO’s objectives of high-velocity reliability, Release 18 introduces significant enhancements to the air interface. This is a competitive differentiator for industrial and automotive applications where uplink capacity has traditionally been a bottleneck.

###### *MIMO Efficiency*

1. **6/8 Tx Uplink Support:**  A critical technical milestone, Release 18 supports 6/8 Tx uplink to enable 4+ layers per device. This specifically targets high-performance hardware like vehicles and industrial Customer Premises Equipment (CPE).  
2. **CSI Acquisition:**  Enhanced Channel State Information (CSI) and Reference Signal (CSI-RS) handling for medium-to-high velocity environments, utilizing time-domain correlation to maintain connectivity at speed.  
3. **Joint Transmission (JT):**  Targeted at the sub-7 GHz band, enhanced CSI acquisition for coherent-JT supports up to four Transmission Reception Points (TRPs). Strategically, this ensures urban V2X reliability by allowing joint transmission across multiple network nodes.  
4. **TCI Framework:**  Extension of the unified Transmission Configuration Indicator (TCI) framework for multiple downlink and uplink states, streamlining beam management.

###### *Coverage & Capacity*

* **4-step RACH for mmWave:**  Coverage improvements for the Physical Random Access Channel (PRACH) allow for multiple transmissions across different beams, specifically optimizing 4-step RACH in the mmWave spectrum.  
* **Dynamic Waveform Switching:**  Performance is bolstered by dynamic switching between Cyclic Prefix Orthogonal Frequency Division Multiplexing (CP-OFDM) and Discrete Fourier Transform Spread OFDM (DFTS-OFDM).

##### 3\. Edge AI in Automotive: The Shift to Onboard Intelligence

Automotive OEMs are shifting from traditional rule-based systems toward End-to-End (E2E) ADAS models. This requires moving AI execution from the cloud to the edge to ensure the sub-second response times necessary for safety-critical maneuvers.

###### *AI Execution Comparison: Cloud vs. Edge vs. Hybrid*

Feature,Cloud AI,Edge AI,Hybrid AI  
Latency,1000–2200ms,300–700ms,Variable (Task-dependent)  
Privacy,Lower (Data offboarding),Higher (Local processing),Moderate  
Reliability,4G/5G dependent,High (Offline available),Reliable for basic tasks  
Data Costs,High (Network traffic),Low (Local execution),Moderate  
Energy Consumption,Low (Offloaded),High (Vehicle load),Moderate  
*Note: Energy consumption is a vital strategic factor, cited as a concern by 35% of stakeholders due to its direct impact on Battery Electric Vehicle (BEV) range.*

###### *The In-Car AI Stack*

The hardware architecture is evolving to support intensive transformer-based models via specialized building blocks:

* **CPU:**  Orchestrates system-level deterministic workloads.  
* **DSP:**  Manages dedicated data-processing for sensor inputs.  
* **GPU:**  Handles parallel computing and display rendering.  
* **NPU (Neural Processing Unit):**  Increasingly essential for executing intensive AI tasks with high compute power and energy efficiency.

###### *Model Optimization*

Strategic deployment at the edge is enabled by "lightweight" models. Using advanced  **pruning and simplification techniques** , developers can reduce model size by several orders of magnitude, allowing high-performance inference to run within the limited RAM and flash memory of standard automotive SoCs.

##### 4\. V2X Global Status: A Regional Deployment Analysis

The VISO ecosystem operates within a fragmented global regulatory and protocol landscape.

* **Europe:**  Moving into the "Urban Phase" (Phase 3, 2024+). With 1.5 million vehicles already equipped with C-ITS, the focus has shifted to integrating new stakeholders and city-level deployments.  
* **USA:**  Guided by the USDOT national plan, aiming for 20% of the National Highway System (NHS) to be V2X-equipped by 2028\. A key technical challenge is the FCC's frequency reassignment: DSRC is now restricted to channel 180, whereas C-V2X is permitted on both 180 and 183\.  
* **China:**  Leading in vertical integration through the "Vehicle Road Cloud" strategy across 20 pilot cities. China has achieved a \~55.7% C-V2X equipment rate in new L2 vehicles, focusing on Multi-access Edge Computing (MEC) at intersections.  
* **Japan:**  Utilizes the 760 MHz band for its "ITS Connect" system. While over 500,000 vehicles are equipped, RSU counts remain low (115) because government budgets have been prioritized for natural disaster recovery measures.

##### 5\. Collaborative Safety: Vulnerable Road Users (VRUs) and Special Use Cases

V2X serves as the ultimate safety net by addressing the "2-second obscurity" problem—where 25% of cyclists at junctions are hidden until two seconds before a collision.

* **VRU Protection:**  By utilizing  **Sensor Sharing Messages (SSM)**  and  **Road Side Messages (RSM)** , vehicles and infrastructure can share perception data. This allows a vehicle to "see" a cyclist through an obstruction by receiving the coordinates via the RSU or another vehicle's sensors.  
* **Specialized Verticals:**  
* **Agricultural Machinery:**  The "Slow Vehicle Warning" prevents high-speed collisions with farm equipment.  
* **Emergency Services:**  "Emergency Vehicle Approaching" and "Emergency Vehicle in Intervention" warnings provide blue-light organizations with a digital siren that penetrates sound-insulated cabins.

##### 6\. Hardware Evolution and Market Projections

Vertical integration and hardware-software co-design are now mandatory for future-proofing platforms.

* **Market Growth:**  The market for advanced automotive microcomponents (MCUs, MPUs, and SoCs at 20nm or smaller) is expanding at a  **24% annual growth rate** , projected to reach  **$18 billion by 2030** .  
* **Scalable Architectures:**  To manage evolving AI workloads, the industry is moving toward modular SoC designs.  
* **Heterogeneous Integration:**  Manufacturers are adopting  **chiplets**  to scale performance without the cost of a full chip redesign. This trend is supported by industry-wide standards like  **Universal Chiplet Interconnect Express (UCIe)** , which facilitates modular hardware ecosystems.

##### 7\. Strategic Outlook and Value Chain Collaboration

Realizing the potential of 5G Advanced requires a fundamental shift in how the value chain interacts. The era of simple component supply is over; we are now in an era of full system provision.**OEMs must prioritize the transition to centralized E/E architectures.**  This shift is the only way to enable the cross-domain functionality and sensor fusion required for advanced ADAS. By decoupling software from hardware, OEMs can utilize over-the-air (OTA) updates to continuously enhance vehicle features and safety protocols throughout the product lifecycle.**Tier 1 Suppliers are under intense pressure to strengthen their AI competencies.**  As OEMs move toward vertical integration and semiconductor players move upstream into software, Tier 1s must evolve into complex systems integrators. They must offer sophisticated software stacks that bridge the gap between silicon capabilities and the OEM’s digital experience requirements.**Semiconductor Players are transitioning into full system and software providers.**  This is evidenced by significant M\&A activity—such as Qualcomm’s acquisition of Arriver and NXP’s integration of Kinara—to build in-house ADAS/AD competence. Success for silicon providers now depends on providing comprehensive, vertically integrated platforms that include the software libraries and AI frameworks necessary for edge execution.**Final Ecosystem Vision:**  The 5G Advanced era will be defined by "Vehicle-Road-Cloud" synergy. By standardizing interfaces and emphasizing cross-domain functionality through centralized E/E architectures, the industry will finally move past rule-based silos to realize a truly intelligent, low-latency, and energy-efficient transport ecosystem.  
