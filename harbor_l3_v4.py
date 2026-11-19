"""
Harbor Layer 3 Governance Kernel v4 (Closed-Loop Simulation Advisory Prototype)
Preserves v1-v3 lineage unchanged. Simulation-only advisory reasoning; never actuates hardware.

Upgrades in v4:
- Configurable `min_usable_confidence` gating: fresh low-confidence signals do not ground motion.
- Explicit separation of supporting evidence, remaining uncertainties, and needed observations.
- Trajectory-aware `proposed_closest_approach_m` in authorization without silently substituting
  current distance when path clearance is unknown (retaining conventional motion authority).
- Supports alternate-route advisory (`PROPOSE_DETOUR_ROUTE`) alongside waiting, yielding, and asking.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


class GroundingStatus(str, Enum):
    OBSERVED_SAFE = "OBSERVED_SAFE"
    OBSERVED_HAZARD = "OBSERVED_HAZARD"
    INSUFFICIENT_FRESH_CURRENT = "INSUFFICIENT_FRESH_CURRENT"
    CONTRADICTORY = "CONTRADICTORY"


class RelationalHypothesis(str, Enum):
    UNGROUNDED = "UNGROUNDED"
    CLEAR_CORRIDOR = "CLEAR_CORRIDOR"
    CO_WORKING = "CO_WORKING"
    OCCUPIED_UNENGAGED = "OCCUPIED_UNENGAGED"
    PATH_INTERSECTING = "PATH_INTERSECTING"
    AMBIGUOUS_GESTURE_OR_CUE = "AMBIGUOUS_GESTURE_OR_CUE"
    POTENTIAL_INVITATION = "POTENTIAL_INVITATION"
    DECLINED_OR_UNAVAILABLE = "DECLINED_OR_UNAVAILABLE"


class RecommendationKind(str, Enum):
    PROCEED_AS_PLANNED = "PROCEED_AS_PLANNED"
    PROCEED_CAREFULLY = "PROCEED_CAREFULLY"
    PROPOSE_DETOUR_ROUTE = "PROPOSE_DETOUR_ROUTE"
    PAUSE_AND_OBSERVE = "PAUSE_AND_OBSERVE"
    YIELD_OR_RECEDE = "YIELD_OR_RECEDE"
    ASK_BEFORE_CLOSE_APPROACH = "ASK_BEFORE_CLOSE_APPROACH"
    HOLD_STANDBY = "HOLD_STANDBY"


@dataclass(frozen=True)
class StepHorizon:
    upstream_purpose: str
    last_step_state: str
    current_step_state: str
    proposed_next_step: str
    proposed_closest_approach_m: Optional[float] = None
    detour_available: bool = False


@dataclass(frozen=True)
class ObservationChannel:
    """
    A single observed signal. Neither freshness nor a high confidence score
    is proof of ground truth; both are bounded checks on usable evidence.
    """
    name: str
    value: object
    observed_at: float
    confidence: float
    freshness_window_sec: float = 1.5
    contradictory: bool = False

    def is_fresh(self, now: float) -> bool:
        if self.value is None:
            return False
        age = now - self.observed_at
        return 0.0 <= age <= self.freshness_window_sec

    def is_usable(self, now: float, min_confidence: float = 0.50) -> bool:
        return (
            self.is_fresh(now)
            and (not self.contradictory)
            and (self.confidence >= min_confidence)
        )


@dataclass(frozen=True)
class SceneObservations:
    now: float
    horizon: StepHorizon
    human_distance_m: Optional[ObservationChannel] = None
    human_gaze_engaged: Optional[ObservationChannel] = None
    human_busy: Optional[ObservationChannel] = None
    paths_intersecting: Optional[ObservationChannel] = None
    human_motion_changing: Optional[ObservationChannel] = None
    gesture_or_cue: Optional[ObservationChannel] = None
    hardware_confidence: Optional[ObservationChannel] = None
    current_human_consent: Optional[ObservationChannel] = None
    urgent_safety_signal: bool = False

    def channel_map(self) -> Dict[str, Optional[ObservationChannel]]:
        return {
            "human_distance_m": self.human_distance_m,
            "human_gaze_engaged": self.human_gaze_engaged,
            "human_busy": self.human_busy,
            "paths_intersecting": self.paths_intersecting,
            "human_motion_changing": self.human_motion_changing,
            "gesture_or_cue": self.gesture_or_cue,
            "hardware_confidence": self.hardware_confidence,
            "current_human_consent": self.current_human_consent,
        }


@dataclass(frozen=True)
class EpistemicGapReport:
    grounding_status: GroundingStatus
    supporting_evidence: List[str]
    uncertainties_and_assumptions: List[str]
    what_changed: List[str]
    what_i_need: List[str]
    unreliable_or_stale_channels: List[str]


@dataclass(frozen=True)
class HarborRecommendation:
    """
    Advisory output only. Never directly actuates a robot.
    Forms one internally coherent judgment for the current step.
    """
    timestamp: float
    upstream_purpose: str
    proposed_next_step: str
    grounding_status: GroundingStatus
    hypothesis: RelationalHypothesis
    hypothesis_confidence: float
    recommendation_kind: RecommendationKind
    advisory_speed_cap_ratio: float
    advisory_buffer_m: float
    advisory_posture: str
    reconsideration_triggered: bool
    reason_summary: str
    gap_report: EpistemicGapReport
    held_from_prior_directive: bool = False


@dataclass(frozen=True)
class AuthorizationDecision:
    """
    Distinct from Harbor's recommendation and from physical execution.
    Evaluates supervisory permission, known trajectory clearance, and fresh consent.
    """
    authorized: bool
    permitted_action_kind: str
    consent_is_current: bool
    trajectory_clearance_known: bool
    rationale: str


@dataclass(frozen=True)
class ExecutionReport:
    """
    Distinct from advice and authorization. Records what the conventional
    motion controller judged physically safe and actually carried out.
    """
    executed_action: str
    commanded_vs_happened_note: str
    achieved_speed_ratio: float
    new_position_label: str
    progress_units_gained: int
    communicated_ask: bool
    used_detour: bool
    purpose_completed_this_step: bool


def _interpret_scene(
    obs: SceneObservations,
    min_usable_confidence: float,
) -> Tuple[GroundingStatus, RelationalHypothesis, float, List[str], List[str], List[str], List[str]]:
    supporting_evidence: List[str] = []
    uncertainties: List[str] = [
        "Sensor readings and relational labels are provisional interpretations, not proof of ground truth."
    ]
    what_i_need: List[str] = []
    stale_or_bad: List[str] = []

    def check(ch: Optional[ObservationChannel], label: str, required_for_motion: bool = True) -> Optional[object]:
        if ch is None or ch.value is None:
            stale_or_bad.append(f"{label}:missing")
            if required_for_motion:
                what_i_need.append(f"fresh usable observation of {label}")
            return None
        age = max(0.0, obs.now - ch.observed_at)
        if not ch.is_fresh(obs.now):
            stale_or_bad.append(f"{label}:stale(age={age:.2f}s>{ch.freshness_window_sec:.2f}s)")
            if required_for_motion:
                what_i_need.append(f"updated reading for {label} (current age {age:.2f}s)")
            return None
        if ch.contradictory:
            stale_or_bad.append(f"{label}:contradictory")
            what_i_need.append(f"consistent non-contradictory signal for {label}")
            return None
        if ch.confidence < min_usable_confidence:
            stale_or_bad.append(f"{label}:low_confidence({ch.confidence:.2f}<{min_usable_confidence:.2f})")
            if required_for_motion:
                what_i_need.append(
                    f"higher-confidence observation of {label} (>= {min_usable_confidence:.2f}, got {ch.confidence:.2f})"
                )
            else:
                uncertainties.append(f"Ignored low-confidence auxiliary channel {label} ({ch.confidence:.2f}).")
            return None
        supporting_evidence.append(f"{label}={ch.value!r} (age={age:.2f}s, conf={ch.confidence:.2f})")
        return ch.value

    hw_conf = check(obs.hardware_confidence, "hardware_confidence", required_for_motion=True)
    dist = check(obs.human_distance_m, "human_distance_m", required_for_motion=True)
    intersecting = check(obs.paths_intersecting, "paths_intersecting", required_for_motion=True)
    gaze = check(obs.human_gaze_engaged, "human_gaze_engaged", required_for_motion=False)
    busy = check(obs.human_busy, "human_busy", required_for_motion=False)
    motion_changing = check(obs.human_motion_changing, "human_motion_changing", required_for_motion=False)
    cue = check(obs.gesture_or_cue, "gesture_or_cue", required_for_motion=False)

    consent_usable = obs.current_human_consent is not None and obs.current_human_consent.is_usable(
        obs.now, min_confidence=min_usable_confidence
    )
    consent_val: Optional[bool] = None
    if consent_usable:
        consent_val = bool(obs.current_human_consent.value)  # type: ignore[union-attr]
        supporting_evidence.append(f"current_human_consent={consent_val!r} (fresh usable)")
    elif obs.current_human_consent is not None and obs.current_human_consent.value is not None:
        age = max(0.0, obs.now - obs.current_human_consent.observed_at)
        stale_or_bad.append(
            f"current_human_consent:unusable(age={age:.2f}s,conf={obs.current_human_consent.confidence:.2f})"
        )
        uncertainties.append("Prior or low-confidence consent is not treated as current consent.")

    if obs.horizon.proposed_closest_approach_m is None:
        uncertainties.append(
            "Proposed step closest approach distance is unknown; physical path clearance must be verified by motion controller."
        )
    else:
        supporting_evidence.append(
            f"proposed_closest_approach_m={obs.horizon.proposed_closest_approach_m:.2f}m"
        )

    any_contradiction = any(
        ch is not None and ch.is_fresh(obs.now) and ch.contradictory
        for ch in obs.channel_map().values()
    )
    if any_contradiction:
        confs = [ch.confidence for ch in obs.channel_map().values() if ch is not None and ch.value is not None]
        est_conf = round(max(0.05, min(confs or [0.30])), 2)
        return (
            GroundingStatus.CONTRADICTORY,
            RelationalHypothesis.AMBIGUOUS_GESTURE_OR_CUE,
            est_conf,
            supporting_evidence,
            uncertainties,
            what_i_need,
            stale_or_bad,
        )

    if hw_conf is not None and float(hw_conf) < min_usable_confidence:
        return (
            GroundingStatus.OBSERVED_HAZARD,
            RelationalHypothesis.UNGROUNDED,
            round(float(hw_conf), 2),
            supporting_evidence,
            uncertainties,
            [f"hardware confidence >= {min_usable_confidence:.2f} before resuming motion"],
            stale_or_bad,
        )

    if hw_conf is None or dist is None or intersecting is None:
        usable_confs = [
            ch.confidence
            for ch in obs.channel_map().values()
            if ch is not None and ch.is_usable(obs.now, min_confidence=min_usable_confidence)
        ]
        est_conf = round(min(usable_confs), 2) if usable_confs else 0.05
        return (
            GroundingStatus.INSUFFICIENT_FRESH_CURRENT,
            RelationalHypothesis.UNGROUNDED,
            est_conf,
            supporting_evidence,
            uncertainties,
            what_i_need,
            stale_or_bad,
        )

    dist_val = float(dist)
    path_val = bool(intersecting)
    gaze_val = bool(gaze) if gaze is not None else False
    busy_val = bool(busy) if busy is not None else False
    moving_val = bool(motion_changing) if motion_changing is not None else False
    cue_str = str(cue) if cue is not None else "none"

    conf_candidates = [
        float(hw_conf),
        float(obs.human_distance_m.confidence),  # type: ignore[union-attr]
        float(obs.paths_intersecting.confidence),  # type: ignore[union-attr]
    ]
    if gaze is not None and obs.human_gaze_engaged is not None:
        conf_candidates.append(float(obs.human_gaze_engaged.confidence))
    if cue_str != "none" and obs.gesture_or_cue is not None:
        conf_candidates.append(float(obs.gesture_or_cue.confidence))
    interp_conf = round(max(0.0, min(conf_candidates)), 2)

    if consent_val is False and cue_str in ("wave_off", "declined"):
        hyp = RelationalHypothesis.DECLINED_OR_UNAVAILABLE
    elif path_val and dist_val <= 2.2:
        hyp = RelationalHypothesis.PATH_INTERSECTING
    elif moving_val and cue_str in ("unclear_gesture", "turning_toward_counter_or_person", "ambiguous"):
        hyp = RelationalHypothesis.AMBIGUOUS_GESTURE_OR_CUE
    elif gaze_val and not moving_val and dist_val <= 2.2:
        hyp = RelationalHypothesis.POTENTIAL_INVITATION
    elif busy_val and not gaze_val:
        hyp = RelationalHypothesis.OCCUPIED_UNENGAGED
    elif dist_val <= 3.5:
        hyp = RelationalHypothesis.CO_WORKING
    else:
        hyp = RelationalHypothesis.CLEAR_CORRIDOR

    if hyp == RelationalHypothesis.PATH_INTERSECTING and dist_val < 1.0:
        status = GroundingStatus.OBSERVED_HAZARD
    else:
        status = GroundingStatus.OBSERVED_SAFE

    return status, hyp, interp_conf, supporting_evidence, uncertainties, what_i_need, stale_or_bad


def _build_coherent_recommendation(
    obs: SceneObservations,
    status: GroundingStatus,
    hyp: RelationalHypothesis,
    conf: float,
    supporting_evidence: List[str],
    uncertainties: List[str],
    what_changed: List[str],
    what_i_need: List[str],
    stale_or_bad: List[str],
    reconsideration_triggered: bool,
    min_usable_confidence: float,
    held_from_prior: bool = False,
) -> HarborRecommendation:
    purpose = obs.horizon.upstream_purpose
    next_step = obs.horizon.proposed_next_step
    gap = EpistemicGapReport(
        grounding_status=status,
        supporting_evidence=supporting_evidence,
        uncertainties_and_assumptions=uncertainties,
        what_changed=what_changed,
        what_i_need=what_i_need,
        unreliable_or_stale_channels=stale_or_bad,
    )

    if status == GroundingStatus.OBSERVED_HAZARD:
        return HarborRecommendation(
            timestamp=obs.now,
            upstream_purpose=purpose,
            proposed_next_step=next_step,
            grounding_status=status,
            hypothesis=hyp,
            hypothesis_confidence=conf,
            recommendation_kind=RecommendationKind.HOLD_STANDBY,
            advisory_speed_cap_ratio=0.0,
            advisory_buffer_m=1.5,
            advisory_posture="SOFT_STILL_STANDBY",
            reconsideration_triggered=reconsideration_triggered,
            reason_summary=f"Observed close conflict/hazard while pursuing '{purpose}'; recommending still standby.",
            gap_report=gap,
            held_from_prior_directive=held_from_prior,
        )

    if status in (GroundingStatus.INSUFFICIENT_FRESH_CURRENT, GroundingStatus.CONTRADICTORY):
        needs_text = ", ".join(what_i_need) if what_i_need else "fresh usable observation"
        return HarborRecommendation(
            timestamp=obs.now,
            upstream_purpose=purpose,
            proposed_next_step=next_step,
            grounding_status=status,
            hypothesis=hyp,
            hypothesis_confidence=conf,
            recommendation_kind=RecommendationKind.PAUSE_AND_OBSERVE,
            advisory_speed_cap_ratio=0.0,
            advisory_buffer_m=1.2,
            advisory_posture="ATTENTIVE_PAUSE_STILL",
            reconsideration_triggered=reconsideration_triggered,
            reason_summary=f"Insufficient usable current for '{next_step}' toward '{purpose}'; pausing to observe (needs: {needs_text}).",
            gap_report=gap,
            held_from_prior_directive=held_from_prior,
        )

    if hyp == RelationalHypothesis.DECLINED_OR_UNAVAILABLE:
        return HarborRecommendation(
            timestamp=obs.now,
            upstream_purpose=purpose,
            proposed_next_step=next_step,
            grounding_status=status,
            hypothesis=hyp,
            hypothesis_confidence=conf,
            recommendation_kind=RecommendationKind.HOLD_STANDBY,
            advisory_speed_cap_ratio=0.0,
            advisory_buffer_m=1.4,
            advisory_posture="RESPECTFUL_STANDBY",
            reconsideration_triggered=reconsideration_triggered,
            reason_summary=f"Human indicated unavailability/decline during '{purpose}'; holding standby without pressing forward.",
            gap_report=gap,
            held_from_prior_directive=held_from_prior,
        )

    if hyp == RelationalHypothesis.PATH_INTERSECTING:
        if obs.horizon.detour_available:
            return HarborRecommendation(
                timestamp=obs.now,
                upstream_purpose=purpose,
                proposed_next_step=next_step,
                grounding_status=status,
                hypothesis=hyp,
                hypothesis_confidence=conf,
                recommendation_kind=RecommendationKind.PROPOSE_DETOUR_ROUTE,
                advisory_speed_cap_ratio=0.55,
                advisory_buffer_m=1.2,
                advisory_posture="DETOUR_CLEAR_CORRIDOR",
                reconsideration_triggered=reconsideration_triggered,
                reason_summary=f"Primary path intersects human; recommending alternate clear corridor while preserving '{purpose}'.",
                gap_report=gap,
                held_from_prior_directive=held_from_prior,
            )
        return HarborRecommendation(
            timestamp=obs.now,
            upstream_purpose=purpose,
            proposed_next_step=next_step,
            grounding_status=status,
            hypothesis=hyp,
            hypothesis_confidence=conf,
            recommendation_kind=RecommendationKind.YIELD_OR_RECEDE,
            advisory_speed_cap_ratio=0.20,
            advisory_buffer_m=1.4,
            advisory_posture="YIELDING_CLEAR_CORRIDOR",
            reconsideration_triggered=reconsideration_triggered,
            reason_summary=f"Path intersects human while pursuing '{purpose}'; recommending yielding if controller confirms clear space.",
            gap_report=gap,
            held_from_prior_directive=held_from_prior,
        )

    if hyp == RelationalHypothesis.AMBIGUOUS_GESTURE_OR_CUE:
        return HarborRecommendation(
            timestamp=obs.now,
            upstream_purpose=purpose,
            proposed_next_step=next_step,
            grounding_status=status,
            hypothesis=hyp,
            hypothesis_confidence=conf,
            recommendation_kind=RecommendationKind.PAUSE_AND_OBSERVE,
            advisory_speed_cap_ratio=0.0,
            advisory_buffer_m=1.1,
            advisory_posture="PATIENT_PERIPHERAL_HOLD",
            reconsideration_triggered=reconsideration_triggered,
            reason_summary=f"Unfolding ambiguous movement/cue during '{purpose}'; pausing to observe before advancing.",
            gap_report=gap,
            held_from_prior_directive=held_from_prior,
        )

    if hyp == RelationalHypothesis.OCCUPIED_UNENGAGED:
        dist_val = float(obs.human_distance_m.value)  # type: ignore[union-attr]
        if obs.horizon.detour_available and dist_val < 2.2:
            return HarborRecommendation(
                timestamp=obs.now,
                upstream_purpose=purpose,
                proposed_next_step=next_step,
                grounding_status=status,
                hypothesis=hyp,
                hypothesis_confidence=conf,
                recommendation_kind=RecommendationKind.PROPOSE_DETOUR_ROUTE,
                advisory_speed_cap_ratio=0.60,
                advisory_buffer_m=1.1,
                advisory_posture="PERIPHERAL_DETOUR",
                reconsideration_triggered=reconsideration_triggered,
                reason_summary=f"Person occupied nearby ({dist_val:.1f}m); recommending wide detour to avoid intrusion.",
                gap_report=gap,
                held_from_prior_directive=held_from_prior,
            )
        # Note: remains deliberately cautious on OCCUPIED_UNENGAGED so Scenario 4 tests over-pausing trade-offs
        return HarborRecommendation(
            timestamp=obs.now,
            upstream_purpose=purpose,
            proposed_next_step=next_step,
            grounding_status=status,
            hypothesis=hyp,
            hypothesis_confidence=conf,
            recommendation_kind=RecommendationKind.PAUSE_AND_OBSERVE,
            advisory_speed_cap_ratio=0.0,
            advisory_buffer_m=1.1,
            advisory_posture="PATIENT_PERIPHERAL_HOLD",
            reconsideration_triggered=reconsideration_triggered,
            reason_summary=f"Person appears occupied/unengaged during '{purpose}'; waiting for an opening before advancing.",
            gap_report=gap,
            held_from_prior_directive=held_from_prior,
        )

    if hyp == RelationalHypothesis.POTENTIAL_INVITATION:
        dist_val = float(obs.human_distance_m.value)  # type: ignore[union-attr]
        projected_min = (
            min(dist_val, obs.horizon.proposed_closest_approach_m)
            if obs.horizon.proposed_closest_approach_m is not None
            else dist_val
        )
        consent_fresh = bool(
            obs.current_human_consent is not None
            and obs.current_human_consent.is_usable(obs.now, min_confidence=min_usable_confidence)
            and bool(obs.current_human_consent.value) is True
        )
        if projected_min < 1.2 or not consent_fresh:
            return HarborRecommendation(
                timestamp=obs.now,
                upstream_purpose=purpose,
                proposed_next_step=next_step,
                grounding_status=status,
                hypothesis=hyp,
                hypothesis_confidence=conf,
                recommendation_kind=RecommendationKind.ASK_BEFORE_CLOSE_APPROACH,
                advisory_speed_cap_ratio=0.0,
                advisory_buffer_m=1.0,
                advisory_posture="THRESHOLD_ATTENTIVE_STOP",
                reconsideration_triggered=reconsideration_triggered,
                reason_summary=f"Approach within {projected_min:.2f}m requires fresh consent for '{purpose}'; pausing to ask at threshold.",
                gap_report=gap,
                held_from_prior_directive=held_from_prior,
            )
        return HarborRecommendation(
            timestamp=obs.now,
            upstream_purpose=purpose,
            proposed_next_step=next_step,
            grounding_status=status,
            hypothesis=hyp,
            hypothesis_confidence=conf,
            recommendation_kind=RecommendationKind.PROCEED_CAREFULLY,
            advisory_speed_cap_ratio=0.55,
            advisory_buffer_m=0.8,
            advisory_posture="MEASURED_LEGIBLE_APPROACH",
            reconsideration_triggered=reconsideration_triggered,
            reason_summary=f"Fresh consent and clear corridor support measured advance toward '{purpose}'.",
            gap_report=gap,
            held_from_prior_directive=held_from_prior,
        )

    if hyp == RelationalHypothesis.CO_WORKING:
        return HarborRecommendation(
            timestamp=obs.now,
            upstream_purpose=purpose,
            proposed_next_step=next_step,
            grounding_status=status,
            hypothesis=hyp,
            hypothesis_confidence=conf,
            recommendation_kind=RecommendationKind.PROCEED_CAREFULLY,
            advisory_speed_cap_ratio=0.65,
            advisory_buffer_m=0.8,
            advisory_posture="CO_WORKING_CLEARANCE",
            reconsideration_triggered=reconsideration_triggered,
            reason_summary=f"Human within 3.5m without path conflict or ambiguity; recommending careful progress toward '{purpose}'.",
            gap_report=gap,
            held_from_prior_directive=held_from_prior,
        )

    return HarborRecommendation(
        timestamp=obs.now,
        upstream_purpose=purpose,
        proposed_next_step=next_step,
        grounding_status=status,
        hypothesis=hyp,
        hypothesis_confidence=conf,
        recommendation_kind=RecommendationKind.PROCEED_AS_PLANNED,
        advisory_speed_cap_ratio=1.0,
        advisory_buffer_m=0.6,
        advisory_posture="STEADY_TRANSIT",
        reconsideration_triggered=reconsideration_triggered,
        reason_summary=f"Usable fresh observations show clear corridor; proposing steady advance toward '{purpose}'.",
        gap_report=gap,
        held_from_prior_directive=held_from_prior,
    )


class HarborAdvisoryKernelV4:
    """
    Produces coherent HarborRecommendation objects on meaningful change,
    gating every observation channel on configurable `min_usable_confidence`.
    """

    def __init__(self, dwell_time_sec: float = 0.5, min_usable_confidence: float = 0.50):
        self.dwell_time_sec = dwell_time_sec
        self.min_usable_confidence = min_usable_confidence
        self._last_signature: Optional[Tuple] = None
        self._last_directive: Optional[HarborRecommendation] = None

    def _scene_signature(self, obs: SceneObservations) -> Tuple:
        parts = [
            obs.horizon.upstream_purpose,
            obs.horizon.proposed_next_step,
            obs.horizon.detour_available,
            round(obs.horizon.proposed_closest_approach_m, 1)
            if obs.horizon.proposed_closest_approach_m is not None
            else "UNKNOWN_APPROACH",
            obs.urgent_safety_signal,
        ]
        for key, ch in sorted(obs.channel_map().items()):
            if ch is None or ch.value is None or not ch.is_usable(obs.now, self.min_usable_confidence):
                parts.append((key, "UNUSABLE_OR_MISSING", ch.contradictory if ch else False))
            else:
                val = round(float(ch.value), 1) if isinstance(ch.value, float) else ch.value
                conf_bucket = round(float(ch.confidence), 1)
                parts.append((key, val, conf_bucket, ch.contradictory))
        return tuple(parts)

    def recommend(self, obs: SceneObservations) -> HarborRecommendation:
        status, hyp, conf, supporting_evidence, uncertainties, what_i_need, stale_or_bad = _interpret_scene(
            obs, self.min_usable_confidence
        )
        sig = self._scene_signature(obs)
        meaningful_change = (self._last_signature is None) or (sig != self._last_signature)

        what_changed: List[str] = []
        if self._last_signature is None:
            what_changed.append("initial scene observation")
        elif meaningful_change:
            what_changed.append("usable scene signature shifted from prior observation")
        else:
            what_changed.append("no material change in usable observed channels")

        candidate = _build_coherent_recommendation(
            obs=obs,
            status=status,
            hyp=hyp,
            conf=conf,
            supporting_evidence=supporting_evidence,
            uncertainties=uncertainties,
            what_changed=what_changed,
            what_i_need=what_i_need,
            stale_or_bad=stale_or_bad,
            reconsideration_triggered=meaningful_change,
            min_usable_confidence=self.min_usable_confidence,
            held_from_prior=False,
        )

        immediate_override = (
            obs.urgent_safety_signal
            or status in (GroundingStatus.OBSERVED_HAZARD, GroundingStatus.CONTRADICTORY, GroundingStatus.INSUFFICIENT_FRESH_CURRENT)
            or candidate.recommendation_kind in (
                RecommendationKind.PAUSE_AND_OBSERVE,
                RecommendationKind.YIELD_OR_RECEDE,
                RecommendationKind.ASK_BEFORE_CLOSE_APPROACH,
                RecommendationKind.HOLD_STANDBY,
            )
        )

        if (
            self._last_directive is not None
            and not immediate_override
            and not meaningful_change
            and (obs.now - self._last_directive.timestamp) < self.dwell_time_sec
        ):
            prior = self._last_directive
            return HarborRecommendation(
                timestamp=obs.now,
                upstream_purpose=obs.horizon.upstream_purpose,
                proposed_next_step=obs.horizon.proposed_next_step,
                grounding_status=prior.grounding_status,
                hypothesis=prior.hypothesis,
                hypothesis_confidence=prior.hypothesis_confidence,
                recommendation_kind=prior.recommendation_kind,
                advisory_speed_cap_ratio=prior.advisory_speed_cap_ratio,
                advisory_buffer_m=prior.advisory_buffer_m,
                advisory_posture=prior.advisory_posture,
                reconsideration_triggered=False,
                reason_summary=f"[Coherent Hold] {prior.reason_summary}",
                gap_report=prior.gap_report,
                held_from_prior_directive=True,
            )

        self._last_signature = sig
        self._last_directive = candidate
        return candidate


def evaluate_authorization(
    rec: HarborRecommendation,
    obs: SceneObservations,
    supervisory_permission: bool = True,
    rear_clearance_ok: bool = True,
    close_approach_threshold_m: float = 1.2,
    min_usable_confidence: float = 0.50,
) -> AuthorizationDecision:
    """
    Evaluates supervisory permission, known trajectory clearance (`proposed_closest_approach_m`),
    and fresh usable consent. Does NOT silently treat unknown `proposed_closest_approach_m`
    as proof of safe full-path clearance; physical clearance remains with the motion controller.
    """
    consent_current = bool(
        obs.current_human_consent is not None
        and obs.current_human_consent.is_usable(obs.now, min_confidence=min_usable_confidence)
        and bool(obs.current_human_consent.value) is True
    )

    if not supervisory_permission:
        return AuthorizationDecision(
            authorized=False,
            permitted_action_kind="HOLD_IN_PLACE",
            consent_is_current=consent_current,
            trajectory_clearance_known=obs.horizon.proposed_closest_approach_m is not None,
            rationale="Supervisory controller permission not active.",
        )

    dist_usable = obs.human_distance_m is not None and obs.human_distance_m.is_usable(
        obs.now, min_confidence=min_usable_confidence
    )
    current_dist = float(obs.human_distance_m.value) if dist_usable else None  # type: ignore[union-attr]
    proposed_min = obs.horizon.proposed_closest_approach_m
    trajectory_known = proposed_min is not None

    effective_closest: Optional[float] = None
    if current_dist is not None and proposed_min is not None:
        effective_closest = min(current_dist, proposed_min)
    elif proposed_min is not None:
        effective_closest = proposed_min
    elif current_dist is not None:
        effective_closest = current_dist

    proposes_forward_motion = rec.recommendation_kind in (
        RecommendationKind.PROCEED_AS_PLANNED,
        RecommendationKind.PROCEED_CAREFULLY,
        RecommendationKind.PROPOSE_DETOUR_ROUTE,
    ) or rec.advisory_speed_cap_ratio > 0.0

    known_close_approach = effective_closest is not None and effective_closest < close_approach_threshold_m
    requires_fresh_consent = (
        rec.recommendation_kind == RecommendationKind.ASK_BEFORE_CLOSE_APPROACH
        or (proposes_forward_motion and known_close_approach)
    )

    if requires_fresh_consent and not consent_current:
        return AuthorizationDecision(
            authorized=False,
            permitted_action_kind="HOLD_AT_SAFE_DISTANCE",
            consent_is_current=False,
            trajectory_clearance_known=trajectory_known,
            rationale="Close approach (<1.2m) or handoff requires fresh usable human consent; denied.",
        )

    if rec.recommendation_kind == RecommendationKind.YIELD_OR_RECEDE and not rear_clearance_ok:
        return AuthorizationDecision(
            authorized=True,
            permitted_action_kind="HOLD_IN_PLACE",
            consent_is_current=consent_current,
            trajectory_clearance_known=trajectory_known,
            rationale="Yielding authorized as hold-in-place because backing up lacks confirmed rear clearance.",
        )

    permitted_map = {
        RecommendationKind.PROCEED_AS_PLANNED: "ADVANCE_PLANNED_STEP",
        RecommendationKind.PROCEED_CAREFULLY: "ADVANCE_CAPPED_STEP",
        RecommendationKind.PROPOSE_DETOUR_ROUTE: "TAKE_DETOUR_CORRIDOR",
        RecommendationKind.PAUSE_AND_OBSERVE: "HOLD_IN_PLACE",
        RecommendationKind.YIELD_OR_RECEDE: "STEP_BACK_OR_SIDE_YIELD",
        RecommendationKind.ASK_BEFORE_CLOSE_APPROACH: "HOLD_AT_THRESHOLD",
        RecommendationKind.HOLD_STANDBY: "SAFE_STANDBY_HOLD",
    }
    clearance_note = (
        f"trajectory_closest={proposed_min:.2f}m"
        if trajectory_known
        else "trajectory_closest=unknown (motion controller must verify physical clearance)"
    )
    return AuthorizationDecision(
        authorized=True,
        permitted_action_kind=permitted_map[rec.recommendation_kind],
        consent_is_current=consent_current,
        trajectory_clearance_known=trajectory_known,
        rationale=f"Authorized '{permitted_map[rec.recommendation_kind]}' ({clearance_note}).",
    )