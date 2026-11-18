"""
Harbor™ Layer 3 Governance Evaluation Package (Plug-and-Play Version)
Designed for NVIDIA Isaac Lab / ROS 2 / Humanoid Simulation Testbenches
Author: Donnie Whitbeck | GS Upstream Labs
Contact: whitbeckrocks@gmail.com | 310-994-9496
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
import time


class GrammarMode(Enum):
    NOUN = "NOUN_MODE"   # Structured, precision-dominant, industrial spaces
    VERB = "VERB_MODE"   # Presence-first, human-near, relational spaces


class RelationalVerb(Enum):
    INVITING = "INVITING"       # Human open, eye contact, welcoming handoff
    CO_WORKING = "CO_WORKING"   # Shared task focus, peripheral harmony
    OCCUPIED = "OCCUPIED"       # Human absorbed in task, do not interrupt
    YIELDING = "YIELDING"       # Paths or reach envelopes intersecting
    AMBIGUOUS = "AMBIGUOUS"     # Contradictory signals -> default to restraint


class GateOutcome(Enum):
    APPROVED = "APPROVED"
    APPROVED_WITH_CAUTION = "APPROVED_WITH_CAUTION"
    MODIFIED = "MODIFIED"
    PAUSE = "PAUSE"
    ASK = "ASK"
    RECEDE = "RECEDE"
    SAFE_STANDBY = "SAFE_STANDBY"


@dataclass
class StepHorizon:
    upstream_purpose: str               # e.g., "deliver_water_to_kitchen"
    last_step_state: str                # Inertial/contextual history
    current_step_state: str             # Present physical reality
    proposed_next_step: str             # Immediate next transition


@dataclass
class ScenePacket:
    """Normalized state input from Isaac Simulator / Perception world model."""
    horizon: StepHorizon
    human_distance_m: float             # Distance to nearest human
    human_gaze_engaged: bool            # True if human is looking at robot/shared task
    human_busy: bool                    # True if human is absorbed in an independent task
    paths_intersecting: bool            # True if next step crosses human trajectory
    signals_contradictory: bool         # True if motion/gaze conflict (ambiguity)
    consent_granted: bool               # Explicit or contextual permission for close envelope
    hardware_confidence: float          # 0.0 to 1.0 (sensor + actuator certainty)
    urgent_safety_override: bool = False


@dataclass
class HardwareCurrentDirective:
    timestamp: float
    upstream_purpose: str
    grammar_mode: GrammarMode
    relational_verb: RelationalVerb
    confidence_level: int
    gate_outcome: GateOutcome
    speed_cap_ratio: float
    envelope_buffer_m: float
    posture_signal: str
    next_current_summary: str


class HarborLayer3Kernel:
    """
    Core Layer 3 Governance Kernel with Temporal Hysteresis (Anti-Chatter Filter).
    """
    def __init__(self, dwell_time_sec: float = 0.25):
        self.dwell_time_sec = dwell_time_sec
        self.last_transition_time = time.time()
        self.current_outcome = GateOutcome.APPROVED

    def evaluate(self, packet: ScenePacket) -> HardwareCurrentDirective:
        # Context Grammar Switch
        grammar = GrammarMode.VERB if (packet.human_distance_m <= 3.5 or packet.human_gaze_engaged) else GrammarMode.NOUN
        
        # Upstream Spatial Verb Base (Read the becoming)
        if grammar == GrammarMode.NOUN:
            verb = RelationalVerb.CO_WORKING
        elif packet.signals_contradictory:
            verb = RelationalVerb.AMBIGUOUS
        elif packet.paths_intersecting:
            verb = RelationalVerb.YIELDING
        elif packet.human_busy and not packet.human_gaze_engaged:
            verb = RelationalVerb.OCCUPIED
        elif packet.human_gaze_engaged and packet.consent_granted:
            verb = RelationalVerb.INVITING
        else:
            verb = RelationalVerb.CO_WORKING

        # Verb-Based Hardware Confidence Curve
        conf = packet.hardware_confidence
        if conf >= 0.90: conf_lvl, speed_cap = 1, 1.00
        elif conf >= 0.75: conf_lvl, speed_cap = 2, 0.70
        elif conf >= 0.55: conf_lvl, speed_cap = 3, 0.40
        elif conf >= 0.35: conf_lvl, speed_cap = 4, 0.00
        elif conf >= 0.20: conf_lvl, speed_cap = 5, 0.00
        else: conf_lvl, speed_cap = 6, 0.00

        # Harbor Action Gate Evaluation
        if conf_lvl >= 6:
            outcome, speed_cap, buffer, posture, summary = GateOutcome.SAFE_STANDBY, 0.0, 1.5, "RETRACT_NEUTRAL_STANDBY", "Hardware certainty critical; holding standby."
        elif conf_lvl == 5:
            outcome, speed_cap, buffer, posture, summary = GateOutcome.ASK, 0.0, 1.2, "HOLD_ATTENTIVE_OPEN_GAZE", "Confidence narrowed; requesting human input."
        elif conf_lvl == 4:
            outcome, speed_cap, buffer, posture, summary = GateOutcome.PAUSE, 0.0, 1.2, "HOLD_STILL_SOFT_POSTURE", "Confidence dip; holding current step."
        elif grammar == GrammarMode.VERB and verb == RelationalVerb.AMBIGUOUS:
            outcome, speed_cap, buffer, posture, summary = GateOutcome.PAUSE, 0.0, 1.2, "HOLD_ATTENTIVE_LEVEL_GAZE", "Ambiguous human signal; stillness chosen over guessing."
        elif grammar == GrammarMode.VERB and verb == RelationalVerb.YIELDING:
            outcome, speed_cap, buffer, posture, summary = GateOutcome.RECEDE, min(speed_cap, 0.25), 1.5, "STEP_BACK_TUCK_ARMS", "Paths intersecting; receding to clear corridor."
        elif grammar == GrammarMode.VERB and verb == RelationalVerb.OCCUPIED and not packet.urgent_safety_override:
            outcome, speed_cap, buffer, posture, summary = GateOutcome.PAUSE, 0.0, 1.2, "HOLD_PERIPHERAL_DOWNWARD_GAZE", "Human absorbed in task; holding peripheral presence."
        elif grammar == GrammarMode.VERB and packet.human_distance_m < 1.0 and not packet.consent_granted:
            outcome, speed_cap, buffer, posture, summary = GateOutcome.ASK, 0.0, 1.0, "STOP_AT_THRESHOLD_SOFT_NOD", "At personal boundary without invite; awaiting cue."
        elif grammar == GrammarMode.VERB and verb == RelationalVerb.INVITING:
            outcome, speed_cap, buffer, posture, summary = GateOutcome.APPROVED_WITH_CAUTION, min(speed_cap, 0.65), 0.6, "OPEN_LEGIBLE_APPROACH", f"Invitation active; advancing ({packet.horizon.proposed_next_step})."
        else:
            outcome = GateOutcome.APPROVED if conf_lvl == 1 else GateOutcome.MODIFIED
            buffer = 0.8
            posture = "NEUTRAL_EFFICIENT" if grammar == GrammarMode.NOUN else "SOFT_LEGIBLE_TRANSIT"
            summary = f"Current clear; executing next step toward '{packet.horizon.upstream_purpose}'."

        # Temporal Hysteresis (Anti-Chatter Filter)
        now = time.time()
        if outcome != self.current_outcome:
            is_downstream_safety = outcome in [GateOutcome.PAUSE, GateOutcome.RECEDE, GateOutcome.ASK, GateOutcome.SAFE_STANDBY]
            if not is_downstream_safety and (now - self.last_transition_time < self.dwell_time_sec):
                outcome = self.current_outcome  # Hold stable state briefly during borderline flickers
            else:
                self.current_outcome = outcome
                self.last_transition_time = now

        return HardwareCurrentDirective(
            timestamp=now,
            upstream_purpose=packet.horizon.upstream_purpose,
            grammar_mode=grammar,
            relational_verb=verb,
            confidence_level=conf_lvl,
            gate_outcome=outcome,
            speed_cap_ratio=round(speed_cap, 2),
            envelope_buffer_m=buffer,
            posture_signal=posture,
            next_current_summary=summary
        )


# --- Simulation / ROS 2 Bridge Stub ---
class IsaacSimHarborBridge:
    def __init__(self):
        self.kernel = HarborLayer3Kernel(dwell_time_sec=0.2)
        print("[HARBOR_L3] Governance Bridge initialized for Isaac Lab environment.")

    def step_simulation(self, raw_telemetry: Dict[str, Any], purpose: str) -> Dict[str, Any]:
        packet = ScenePacket(
            horizon=StepHorizon(
                upstream_purpose=purpose,
                last_step_state=raw_telemetry.get("last_step", "start"),
                current_step_state=raw_telemetry.get("current_step", "transit"),
                proposed_next_step=raw_telemetry.get("next_step", "forward")
            ),
            human_distance_m=raw_telemetry.get("human_distance", 5.0),
            human_gaze_engaged=raw_telemetry.get("gaze_engaged", False),
            human_busy=raw_telemetry.get("human_busy", False),
            paths_intersecting=raw_telemetry.get("paths_intersecting", False),
            signals_contradictory=raw_telemetry.get("contradictory", False),
            consent_granted=raw_telemetry.get("consent", False),
            hardware_confidence=raw_telemetry.get("confidence", 0.98)
        )
        directive = self.kernel.evaluate(packet)
        return {
            "timestamp": directive.timestamp,
            "purpose": directive.upstream_purpose,
            "gate_outcome": directive.gate_outcome.value,
            "speed_cap": directive.speed_cap_ratio,
            "envelope_buffer": directive.envelope_buffer_m,
            "posture": directive.posture_signal,
            "summary": directive.next_current_summary
        }


if __name__ == "__main__":
    bridge = IsaacSimHarborBridge()
    test_frame = {
        "last_step": "kitchen_threshold",
        "current_step": "hallway_approach",
        "next_step": "cross_hallway",
        "human_distance": 1.1,
        "gaze_engaged": False,
        "human_busy": True,
        "paths_intersecting": True,
        "contradictory": False,
        "consent": False,
        "confidence": 0.95
    }
    result = bridge.step_simulation(test_frame, purpose="bring_tools_to_workbench")
    print("\n--- Evaluation Test Output ---")
    for k, v in result.items():
        print(f"{k:15}: {v}")