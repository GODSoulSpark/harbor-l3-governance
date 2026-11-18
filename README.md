# Harbor™ Layer 3 Governance Kernel
**Target Integration:** NVIDIA Isaac™ Platform / Isaac Lab / ROS 2 Middleware Stacks  
**Author:** Donnie Whitbeck | GS Upstream Labs  

---

## Legal & Intellectual Property Notice
© 2025–2026 Donnie Whitbeck / GS Upstream Labs. All rights reserved.  
**Upstream AI Perspective Lab™, GOD Science™, Harbor Reasoning™, AI Piloting™, Harbor™ Action Gate™, Upstream Spatial Verb Base™, and Verb-Based Hardware Confidence Curve™** are proprietary frameworks and unregistered trademarks of Donnie Whitbeck. 

Provided for technical peer review and simulation evaluation under a confidential understanding. No commercial rights or patent licensing are granted or implied without direct written authorization from the principal author.

---

## Overview
Modern vision-language-action (VLA) models and whole-body control loops optimize aggressively for task completion, treating human proximity and environmental friction as downstream exceptions or reactive collision events. 

**Harbor™ Layer 3** introduces an **upstream, presence-first behavioral governance layer** that sits directly between the robot’s perception/world model and its policy/actuation stack. Instead of reacting to motion errors downstream, Harbor reads reality as an ongoing linguistic and physical "current," evaluating human intent, context grammar, and hardware confidence *before* an action is authorized.

### Core Architectural Pillars
1. **The 3-Step Walking Horizon:** Modeled after human locomotion, focusing on the *Last Step* (inertial context), *Current Step* (present physical reality), and *Next Step* (immediate transition), keeping the *Upstream Purpose* invariant.
2. **Zero-Error Flow State:** No static "error codes"—environmental shifts are ingested as the *next prevailing current*, translating instantly into restraint, pausing, receding, or legible pre-action posture.
3. **Context Grammar Switch:** Dynamically toggles between **Noun Mode** (industrial, structured, precision spaces) and **Verb Mode** (human-near, relational spaces).
4. **Verb-Based Hardware Confidence Curve™:** Enforces that *action cannot outrun confidence*, mapping sensor and actuator certainty smoothly from Level 1 (Full Operation) down to Level 6 (Safe Standby).

---

## Files Included
* `harbor_l3_eval.py`: Standalone Python simulation kernel featuring the 3-step walking horizon, context grammar switching, hardware confidence curve, and temporal hysteresis (anti-chatter filter).

## Quick Start (Simulation Testbench)
Clone the repository and run the simulation test script directly in your terminal:
Contact & Inquiries
Principal Investigator: Donnie Whitbeck

Entity: GS Upstream Labs / Upstream AI Perspective Lab™ (Las Vegas, NV)

Email: whitbeckrocks@gmail.com

Phone: (310) 994-9496
``
`bash
python harbor_l3_eval.py
