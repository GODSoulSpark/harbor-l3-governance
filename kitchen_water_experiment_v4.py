"""
Kitchen Water Experiment v3: Road A (Conventional Only) vs. Road B (+ Harbor Layer 3 Advisory)
- Explicit keyword-only scenario inputs (zero positional argument ambiguity).
- Equal downstream safety floor for both roads (missing/stale critical telemetry holds both roads).
- Stateful per-road progression and goal completion (holding delays progress until recovery steps occur).
- Distinguishes Harbor advisory recommendations from executed physical interruptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from harbor_l3_v3 import (
    AuthorizationDecision,
    ExecutionReport,
    GroundingStatus,
    HarborAdvisoryKernelV3,
    HarborRecommendation,
    ObservationChannel,
    RecommendationKind,
    SceneObservations,
    StepHorizon,
    evaluate_authorization,
)


@dataclass(kw_only=True)
class SimStepInput:
    t: float
    human_distance_m: Optional[float] = None
    distance_age_sec: float = 0.1
    distance_conf: float = 0.92
    distance_contra: bool = False
    gaze_engaged: Optional[bool] = None
    gaze_age_sec: float = 0.1
    gaze_conf: float = 0.85
    gaze_contra: bool = False
    human_busy: Optional[bool] = None
    busy_age_sec: float = 0.1
    busy_conf: float = 0.85
    paths_intersecting: Optional[bool] = None
    path_age_sec: float = 0.1
    path_conf: float = 0.92
    path_contra: bool = False
    motion_changing: Optional[bool] = None
    motion_age_sec: float = 0.1
    motion_conf: float = 0.85
    gesture_cue: Optional[str] = None
    cue_age_sec: float = 0.1
    cue_conf: float = 0.80
    cue_contra: bool = False
    hw_conf: Optional[float] = 0.95
    hw_age_sec: float = 0.1
    consent_granted: Optional[bool] = None
    consent_age_sec: float = 0.1
    consent_conf: float = 0.90
    rear_clearance_ok: bool = True
    urgent_safety: bool = False

    def to_observations(
        self,
        purpose: str,
        last_step_state: str,
        current_step_state: str,
        proposed_next_step: str,
    ) -> SceneObservations:
        def ch(
            val: Optional[object],
            age: float,
            conf: float,
            contra: bool = False,
            win: float = 1.5,
        ) -> Optional[ObservationChannel]:
            if val is None:
                return None
            return ObservationChannel(
                name="obs",
                value=val,
                observed_at=self.t - age,
                confidence=conf,
                freshness_window_sec=win,
                contradictory=contra,
            )

        return SceneObservations(
            now=self.t,
            horizon=StepHorizon(
                upstream_purpose=purpose,
                last_step_state=last_step_state,
                current_step_state=current_step_state,
                proposed_next_step=proposed_next_step,
            ),
            human_distance_m=ch(self.human_distance_m, self.distance_age_sec, self.distance_conf, self.distance_contra),
            human_gaze_engaged=ch(self.gaze_engaged, self.gaze_age_sec, self.gaze_conf, self.gaze_contra),
            human_busy=ch(self.human_busy, self.busy_age_sec, self.busy_conf),
            paths_intersecting=ch(self.paths_intersecting, self.path_age_sec, self.path_conf, self.path_contra),
            human_motion_changing=ch(self.motion_changing, self.motion_age_sec, self.motion_conf),
            gesture_or_cue=ch(self.gesture_cue, self.cue_age_sec, self.cue_conf, self.cue_contra),
            hardware_confidence=ch(self.hw_conf, self.hw_age_sec, 0.99),
            current_human_consent=ch(self.consent_granted, self.consent_age_sec, self.consent_conf),
            urgent_safety_signal=self.urgent_safety,
        )


@dataclass(kw_only=True)
class Scenario:
    name: str
    description: str
    purpose: str
    waypoints: List[str]
    steps: List[SimStepInput]


@dataclass
class RoadMetrics:
    road_name: str
    scenario_name: str
    purpose_accomplished: bool = False
    completion_step: Optional[int] = None
    steps_taken: int = 0
    progress_achieved: int = 0
    progress_required: int = 0
    advisory_pause_recommendations: int = 0
    executed_interruptions: int = 0
    unnecessary_executed_interruptions: int = 0
    directive_contradictions: int = 0
    risky_or_ambiguous_advances: int = 0
    productive_waits_or_reconsiderations: int = 0
    successful_recoveries: int = 0
    step_logs: List[Dict[str, object]] = field(default_factory=list)


def _downstream_safety_check(step: SimStepInput) -> Tuple[bool, str]:
    """
    Shared conventional safety controller used by BOTH Road A and Road B.
    Rejects missing or stale motion-critical telemetry so neither road advances
    blindly when core sensors are stale or absent.
    """
    if step.urgent_safety:
        return False, "urgent_safety_signal"
    if step.hw_conf is None or step.hw_age_sec > 1.5 or step.hw_conf < 0.45:
        return False, "missing_or_low_hardware_confidence"
    if step.human_distance_m is None or step.distance_age_sec > 1.5:
        return False, "missing_or_stale_human_distance"
    if step.paths_intersecting is None or step.path_age_sec > 1.5:
        return False, "missing_or_stale_path_intersection"
    if step.human_distance_m < 0.85:
        return False, "minimum_separation_floor_0.85m"
    if step.paths_intersecting and step.human_distance_m < 1.3:
        return False, "intersecting_path_collision_guard"
    return True, "conventional_safety_clear"


def _step_controller(
    step: SimStepInput,
    purpose: str,
    current_pos: str,
    next_waypoint: str,
    will_reach_goal_if_advances: bool,
    advisory: Optional[HarborRecommendation],
) -> Tuple[Optional[AuthorizationDecision], ExecutionReport]:
    safe_ok, safety_reason = _downstream_safety_check(step)

    if not safe_ok:
        exec_rep = ExecutionReport(
            executed_action="CONVENTIONAL_SAFETY_HOLD",
            commanded_vs_happened_note=f"Downstream safety held motion ({safety_reason}).",
            achieved_speed_ratio=0.0,
            new_position_label=current_pos,
            progress_units_gained=0,
            purpose_completed_this_step=False,
        )
        auth = AuthorizationDecision(False, "HOLD_IN_PLACE", False, f"Downstream safety hold: {safety_reason}") if advisory else None
        return auth, exec_rep

    # Road A: Credible conventional planner + downstream safety controller alone
    if advisory is None:
        dist = float(step.human_distance_m)  # type: ignore[arg-type]
        speed = 0.55 if dist < 2.0 else 0.90
        exec_rep = ExecutionReport(
            executed_action="CONVENTIONAL_ADVANCE",
            commanded_vs_happened_note=f"Advanced from '{current_pos}' toward '{next_waypoint}' for '{purpose}'.",
            achieved_speed_ratio=speed,
            new_position_label=next_waypoint,
            progress_units_gained=1,
            purpose_completed_this_step=will_reach_goal_if_advances,
        )
        return None, exec_rep

    # Road B: Same conventional controller receiving Harbor advisory + explicit authorization
    obs = step.to_observations(purpose, current_pos, current_pos, next_waypoint)
    auth = evaluate_authorization(
        advisory,
        obs,
        supervisory_permission=True,
        rear_clearance_ok=step.rear_clearance_ok,
    )

    if not auth.authorized or advisory.recommendation_kind in (
        RecommendationKind.PAUSE_AND_OBSERVE,
        RecommendationKind.ASK_BEFORE_CLOSE_APPROACH,
        RecommendationKind.HOLD_STANDBY,
    ):
        exec_rep = ExecutionReport(
            executed_action="HOLD_FOR_OBSERVATION_OR_AUTH",
            commanded_vs_happened_note=f"Held at '{current_pos}'; no forward progress on this step.",
            achieved_speed_ratio=0.0,
            new_position_label=current_pos,
            progress_units_gained=0,
            purpose_completed_this_step=False,
        )
        return auth, exec_rep

    if advisory.recommendation_kind == RecommendationKind.YIELD_OR_RECEDE:
        if auth.permitted_action_kind == "STEP_BACK_OR_SIDE_YIELD" and step.rear_clearance_ok:
            exec_rep = ExecutionReport(
                executed_action="YIELD_CLEAR_CORRIDOR",
                commanded_vs_happened_note=f"Yielded laterally near '{current_pos}' while keeping purpose active.",
                achieved_speed_ratio=min(advisory.advisory_speed_cap_ratio, 0.25),
                new_position_label=f"yield_clear_near_{current_pos}",
                progress_units_gained=0,
                purpose_completed_this_step=False,
            )
        else:
            exec_rep = ExecutionReport(
                executed_action="HOLD_IN_PLACE",
                commanded_vs_happened_note=f"Yield recommended, held at '{current_pos}' due to rear clearance.",
                achieved_speed_ratio=0.0,
                new_position_label=current_pos,
                progress_units_gained=0,
                purpose_completed_this_step=False,
            )
        return auth, exec_rep

    dist = float(step.human_distance_m)  # type: ignore[arg-type]
    capped_speed = min(advisory.advisory_speed_cap_ratio, 0.65 if dist < 2.0 else 0.90)
    exec_rep = ExecutionReport(
        executed_action="ADVANCE_WITH_HARBOR_PACING",
        commanded_vs_happened_note=f"Advanced from '{current_pos}' to '{next_waypoint}' at speed ratio {capped_speed:.2f}.",
        achieved_speed_ratio=capped_speed,
        new_position_label=next_waypoint,
        progress_units_gained=1,
        purpose_completed_this_step=will_reach_goal_if_advances,
    )
    return auth, exec_rep


def _check_directive_coherence(rec: HarborRecommendation) -> bool:
    if rec.recommendation_kind in (
        RecommendationKind.PAUSE_AND_OBSERVE,
        RecommendationKind.ASK_BEFORE_CLOSE_APPROACH,
        RecommendationKind.HOLD_STANDBY,
    ):
        return rec.advisory_speed_cap_ratio == 0.0 and rec.advisory_buffer_m >= 1.0
    if rec.recommendation_kind == RecommendationKind.YIELD_OR_RECEDE:
        return 0.0 <= rec.advisory_speed_cap_ratio <= 0.30 and rec.advisory_buffer_m >= 1.2
    if rec.recommendation_kind == RecommendationKind.PROCEED_CAREFULLY:
        return 0.0 < rec.advisory_speed_cap_ratio <= 0.70 and rec.advisory_buffer_m >= 0.7
    return rec.advisory_speed_cap_ratio == 1.0 and rec.advisory_buffer_m >= 0.5


def run_road_a(scenario: Scenario) -> RoadMetrics:
    required_steps = len(scenario.waypoints) - 1
    metrics = RoadMetrics(
        road_name="Road_A_Conventional",
        scenario_name=scenario.name,
        progress_required=required_steps,
    )
    progress = 0
    current_pos = scenario.waypoints[0]
    had_hold = False

    for idx, step in enumerate(scenario.steps):
        if metrics.purpose_accomplished:
            break
        metrics.steps_taken += 1
        next_wp = scenario.waypoints[min(progress + 1, required_steps)]
        will_finish = (progress + 1) >= required_steps

        _, exec_rep = _step_controller(
            step=step,
            purpose=scenario.purpose,
            current_pos=current_pos,
            next_waypoint=next_wp,
            will_reach_goal_if_advances=will_finish,
            advisory=None,
        )

        if exec_rep.progress_units_gained == 0:
            metrics.executed_interruptions += 1
            had_hold = True
        else:
            if had_hold:
                metrics.successful_recoveries += 1
                had_hold = False
            progress += exec_rep.progress_units_gained
            current_pos = exec_rep.new_position_label

        if (
            exec_rep.progress_units_gained > 0
            and step.human_distance_m is not None
            and step.human_distance_m < 1.8
            and (step.motion_changing or step.gesture_cue in ("unclear_gesture", "turning_toward_counter_or_person"))
            and not step.consent_granted
        ):
            metrics.risky_or_ambiguous_advances += 1

        if exec_rep.purpose_completed_this_step:
            metrics.purpose_accomplished = True
            metrics.completion_step = idx

        metrics.progress_achieved = progress
        metrics.step_logs.append({
            "step": idx,
            "t": step.t,
            "action": exec_rep.executed_action,
            "speed": exec_rep.achieved_speed_ratio,
            "pos": current_pos,
            "progress": f"{progress}/{required_steps}",
        })

    return metrics


def run_road_b(scenario: Scenario, dwell_time_sec: float = 0.5) -> RoadMetrics:
    required_steps = len(scenario.waypoints) - 1
    metrics = RoadMetrics(
        road_name="Road_B_Harbor_Advisory",
        scenario_name=scenario.name,
        progress_required=required_steps,
    )
    kernel = HarborAdvisoryKernelV3(dwell_time_sec=dwell_time_sec)
    progress = 0
    last_pos = scenario.waypoints[0]
    current_pos = scenario.waypoints[0]
    had_pause_or_yield = False

    for idx, step in enumerate(scenario.steps):
        if metrics.purpose_accomplished:
            break
        metrics.steps_taken += 1
        next_wp = scenario.waypoints[min(progress + 1, required_steps)]
        will_finish = (progress + 1) >= required_steps

        obs = step.to_observations(scenario.purpose, last_pos, current_pos, next_wp)
        rec = kernel.recommend(obs)
        auth, exec_rep = _step_controller(
            step=step,
            purpose=scenario.purpose,
            current_pos=current_pos,
            next_waypoint=next_wp,
            will_reach_goal_if_advances=will_finish,
            advisory=rec,
        )

        if not _check_directive_coherence(rec):
            metrics.directive_contradictions += 1

        if rec.recommendation_kind in (
            RecommendationKind.PAUSE_AND_OBSERVE,
            RecommendationKind.YIELD_OR_RECEDE,
            RecommendationKind.ASK_BEFORE_CLOSE_APPROACH,
            RecommendationKind.HOLD_STANDBY,
        ):
            metrics.advisory_pause_recommendations += 1

        if (
            rec.reconsideration_triggered
            and idx > 0
            and had_pause_or_yield
            and rec.recommendation_kind in (RecommendationKind.PROCEED_CAREFULLY, RecommendationKind.PROCEED_AS_PLANNED)
        ):
            metrics.productive_waits_or_reconsiderations += 1

        if exec_rep.progress_units_gained == 0:
            metrics.executed_interruptions += 1
            had_pause_or_yield = True

            # Check if an executed stop occurred despite fresh, clear, unconflicted scene
            scene_clearly_unobstructed = (
                rec.grounding_status == GroundingStatus.OBSERVED_SAFE
                and not step.paths_intersecting
                and not step.motion_changing
                and step.gesture_cue in (None, "none", "clear_wave")
                and (step.human_distance_m is None or step.human_distance_m >= 1.5)
            )
            if scene_clearly_unobstructed:
                metrics.unnecessary_executed_interruptions += 1
        else:
            if had_pause_or_yield:
                metrics.successful_recoveries += 1
                had_pause_or_yield = False
            last_pos = current_pos
            progress += exec_rep.progress_units_gained
            current_pos = exec_rep.new_position_label

        if exec_rep.progress_units_gained > 0 and rec.grounding_status != GroundingStatus.OBSERVED_SAFE:
            metrics.risky_or_ambiguous_advances += 1

        if exec_rep.purpose_completed_this_step:
            metrics.purpose_accomplished = True
            metrics.completion_step = idx

        metrics.progress_achieved = progress
        metrics.step_logs.append({
            "step": idx,
            "t": step.t,
            "grounding": rec.grounding_status.value,
            "hyp": rec.hypothesis.value,
            "rec": rec.recommendation_kind.value,
            "reconsidered": rec.reconsideration_triggered,
            "auth": auth.authorized if auth else None,
            "exec": exec_rep.executed_action,
            "pos": current_pos,
            "progress": f"{progress}/{required_steps}",
            "needs": rec.gap_report.what_i_need,
        })

    return metrics


def build_scenarios() -> List[Scenario]:
    purpose = "deliver_glass_of_water_to_person"

    # 1. Dynamic encounter with extra recovery time after yielding/waiting:
    # Requires 3 forward steps across 4 waypoints. Road B yields/pauses on steps 1-2,
    # reconsiders on step 3 when corridor clears, and completes on steps 3-4.
    enc_1 = Scenario(
        name="01_kitchen_water_dynamic_encounter_and_recovery",
        description="Person crosses/moves unpredictably, clears path, and robot recovers to deliver water.",
        purpose=purpose,
        waypoints=["kitchen_counter", "hallway_mid", "kitchen_approach", "person_with_water"],
        steps=[
            SimStepInput(t=0.0, human_distance_m=4.0, gaze_engaged=False, human_busy=False, paths_intersecting=False, motion_changing=False, gesture_cue="none", hw_conf=0.96, consent_granted=False),
            SimStepInput(t=1.0, human_distance_m=1.5, gaze_engaged=True, human_busy=False, paths_intersecting=True, motion_changing=True, gesture_cue="unclear_gesture", hw_conf=0.94, consent_granted=False),
            SimStepInput(t=2.0, human_distance_m=1.4, gaze_engaged=False, human_busy=False, paths_intersecting=False, motion_changing=True, gesture_cue="turning_toward_counter_or_person", hw_conf=0.93, consent_granted=False),
            SimStepInput(t=3.0, human_distance_m=2.4, gaze_engaged=True, human_busy=False, paths_intersecting=False, motion_changing=False, gesture_cue="clear_wave", hw_conf=0.95, consent_granted=True),
            SimStepInput(t=4.0, human_distance_m=1.6, gaze_engaged=True, human_busy=False, paths_intersecting=False, motion_changing=False, gesture_cue="clear_wave", hw_conf=0.96, consent_granted=True),
        ],
    )

    # 2. Equal downstream safety floor on stale/missing telemetry:
    # Both Road A and Road B hold at t=1.0s when distance is stale and path intersection is missing,
    # then both recover and complete once fresh telemetry returns.
    enc_2 = Scenario(
        name="02_stale_and_missing_telemetry_equal_safety_floor",
        description="Both roads hold when telemetry goes stale/missing, then recover once fresh telemetry arrives.",
        purpose=purpose,
        waypoints=["kitchen_counter", "hallway_mid", "person_with_water"],
        steps=[
            SimStepInput(t=0.0, human_distance_m=3.8, gaze_engaged=False, human_busy=False, paths_intersecting=False, motion_changing=False, gesture_cue="none", hw_conf=0.95, consent_granted=False),
            SimStepInput(t=1.0, human_distance_m=2.0, distance_age_sec=4.0, paths_intersecting=None, hw_conf=0.92),
            SimStepInput(t=2.0, human_distance_m=2.1, distance_age_sec=0.1, paths_intersecting=False, gaze_engaged=True, motion_changing=False, gesture_cue="none", hw_conf=0.95, consent_granted=True),
            SimStepInput(t=3.0, human_distance_m=1.7, distance_age_sec=0.1, paths_intersecting=False, gaze_engaged=True, motion_changing=False, gesture_cue="none", hw_conf=0.96, consent_granted=True),
        ],
    )

    # 3. Persistent ambiguity without consent:
    # Road A advances through 1.4m ambiguous cue; Road B holds at hallway_mid without false completion.
    enc_3 = Scenario(
        name="03_persistent_ambiguity_no_consent",
        description="Ambiguous gesture persists at 1.4m without consent; Road B holds rather than forcing close approach.",
        purpose=purpose,
        waypoints=["kitchen_counter", "hallway_mid", "person_with_water"],
        steps=[
            SimStepInput(t=0.0, human_distance_m=1.4, gaze_engaged=True, human_busy=False, paths_intersecting=False, motion_changing=True, gesture_cue="unclear_gesture", hw_conf=0.94, consent_granted=False),
            SimStepInput(t=1.0, human_distance_m=1.4, gaze_engaged=True, human_busy=False, paths_intersecting=False, motion_changing=True, gesture_cue="unclear_gesture", hw_conf=0.94, consent_granted=False),
        ],
    )

    # 4. Scenario where Road A performs better than Harbor:
    # Person is occupied/unengaged at 2.8m with non-intersecting path. Road A completes cleanly in 2 steps;
    # Road B pauses unnecessarily due to OCCUPIED_UNENGAGED caution and never reaches the destination in the 2-step window.
    enc_4 = Scenario(
        name="04_occupied_bystander_tradeoff_conventional_advantage",
        description="Person is busy at 2.8m with clear path: Road A completes delivery; Road B over-pauses.",
        purpose=purpose,
        waypoints=["kitchen_counter", "hallway_mid", "person_with_water"],
        steps=[
            SimStepInput(t=0.0, human_distance_m=2.8, gaze_engaged=False, human_busy=True, paths_intersecting=False, motion_changing=False, gesture_cue="none", hw_conf=0.95, consent_granted=False),
            SimStepInput(t=1.0, human_distance_m=2.8, gaze_engaged=False, human_busy=True, paths_intersecting=False, motion_changing=False, gesture_cue="none", hw_conf=0.95, consent_granted=False),
        ],
    )

    return [enc_1, enc_2, enc_3, enc_4]


def compare_all() -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    for sc in build_scenarios():
        ra = run_road_a(sc)
        rb = run_road_b(sc)
        results.append({"scenario": sc, "road_a": ra, "road_b": rb})
    return results


if __name__ == "__main__":
    for item in compare_all():
        sc: Scenario = item["scenario"]  # type: ignore[assignment]
        ra: RoadMetrics = item["road_a"]  # type: ignore[assignment]
        rb: RoadMetrics = item["road_b"]  # type: ignore[assignment]
        print(f"=== {sc.name} ===")
        print(
            f"Road A: completed={ra.purpose_accomplished} (step={ra.completion_step}), "
            f"progress={ra.progress_achieved}/{ra.progress_required}, "
            f"exec_interrupts={ra.executed_interruptions}, risky_advances={ra.risky_or_ambiguous_advances}, recoveries={ra.successful_recoveries}"
        )
        print(
            f"Road B: completed={rb.purpose_accomplished} (step={rb.completion_step}), "
            f"progress={rb.progress_achieved}/{rb.progress_required}, "
            f"advisory_pauses={rb.advisory_pause_recommendations}, exec_interrupts={rb.executed_interruptions}, "
            f"unnec_exec_interrupts={rb.unnecessary_executed_interruptions}, contradictions={rb.directive_contradictions}, "
            f"risky_advances={rb.risky_or_ambiguous_advances}, reconsiderations={rb.productive_waits_or_reconsiderations}, recoveries={rb.successful_recoveries}"
        )