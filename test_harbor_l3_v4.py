import unittest

from harbor_l3_v3 import (
    GroundingStatus,
    HarborAdvisoryKernelV3,
    ObservationChannel,
    RecommendationKind,
    SceneObservations,
    StepHorizon,
    evaluate_authorization,
)
from kitchen_water_experiment_v3 import compare_all


class TestHarborLayer3V3(unittest.TestCase):
    def _horizon(self) -> StepHorizon:
        return StepHorizon(
            upstream_purpose="deliver_glass_of_water_to_person",
            last_step_state="kitchen_exit",
            current_step_state="hallway_mid",
            proposed_next_step="kitchen_approach",
        )

    def test_stale_observation_is_not_treated_as_safe(self):
        kernel = HarborAdvisoryKernelV3()
        obs = SceneObservations(
            now=100.0,
            horizon=self._horizon(),
            human_distance_m=ObservationChannel("dist", 5.0, observed_at=90.0, confidence=0.99, freshness_window_sec=1.5),
            paths_intersecting=ObservationChannel("path", False, observed_at=99.9, confidence=0.99, freshness_window_sec=1.5),
            hardware_confidence=ObservationChannel("hw", 0.99, observed_at=99.9, confidence=0.99, freshness_window_sec=1.5),
        )
        rec = kernel.recommend(obs)
        self.assertEqual(rec.grounding_status, GroundingStatus.INSUFFICIENT_FRESH_CURRENT)
        self.assertEqual(rec.recommendation_kind, RecommendationKind.PAUSE_AND_OBSERVE)
        self.assertEqual(rec.advisory_speed_cap_ratio, 0.0)
        self.assertTrue(len(rec.gap_report.what_i_need) > 0)

    def test_fresh_observation_can_still_be_contradictory(self):
        kernel = HarborAdvisoryKernelV3()
        obs = SceneObservations(
            now=50.0,
            horizon=self._horizon(),
            human_distance_m=ObservationChannel("dist", 1.6, observed_at=50.0, confidence=0.92),
            paths_intersecting=ObservationChannel("path", False, observed_at=50.0, confidence=0.90),
            hardware_confidence=ObservationChannel("hw", 0.95, observed_at=50.0, confidence=0.95),
            gesture_or_cue=ObservationChannel("cue", "wave_and_step_across", observed_at=50.0, confidence=0.80, contradictory=True),
        )
        rec = kernel.recommend(obs)
        self.assertEqual(rec.grounding_status, GroundingStatus.CONTRADICTORY)
        self.assertEqual(rec.advisory_speed_cap_ratio, 0.0)

    def test_coherent_directive_during_non_urgent_hold(self):
        kernel = HarborAdvisoryKernelV3(dwell_time_sec=5.0)
        obs1 = SceneObservations(
            now=10.0,
            horizon=self._horizon(),
            human_distance_m=ObservationChannel("dist", 2.5, observed_at=10.0, confidence=0.9),
            paths_intersecting=ObservationChannel("path", False, observed_at=10.0, confidence=0.9),
            hardware_confidence=ObservationChannel("hw", 0.95, observed_at=10.0, confidence=0.95),
        )
        rec1 = kernel.recommend(obs1)
        self.assertEqual(rec1.recommendation_kind, RecommendationKind.PROCEED_CAREFULLY)

        obs2 = SceneObservations(
            now=11.0,
            horizon=self._horizon(),
            human_distance_m=ObservationChannel("dist", 2.5, observed_at=10.0, confidence=0.9),
            paths_intersecting=ObservationChannel("path", False, observed_at=10.0, confidence=0.9),
            hardware_confidence=ObservationChannel("hw", 0.95, observed_at=10.0, confidence=0.95),
        )
        rec2 = kernel.recommend(obs2)
        self.assertTrue(rec2.held_from_prior_directive)
        self.assertEqual(rec2.recommendation_kind, rec1.recommendation_kind)
        self.assertEqual(rec2.advisory_speed_cap_ratio, rec1.advisory_speed_cap_ratio)
        self.assertEqual(rec2.advisory_buffer_m, rec1.advisory_buffer_m)
        self.assertEqual(rec2.advisory_posture, rec1.advisory_posture)

    def test_remembered_consent_is_not_current_consent_for_close_approach(self):
        kernel = HarborAdvisoryKernelV3()
        stale_consent = ObservationChannel("consent", True, observed_at=1.0, confidence=0.95, freshness_window_sec=2.0)
        obs = SceneObservations(
            now=20.0,
            horizon=self._horizon(),
            human_distance_m=ObservationChannel("dist", 0.95, observed_at=20.0, confidence=0.92),
            paths_intersecting=ObservationChannel("path", False, observed_at=20.0, confidence=0.92),
            human_gaze_engaged=ObservationChannel("gaze", True, observed_at=20.0, confidence=0.90),
            hardware_confidence=ObservationChannel("hw", 0.95, observed_at=20.0, confidence=0.95),
            current_human_consent=stale_consent,
        )
        rec = kernel.recommend(obs)
        auth = evaluate_authorization(rec, obs, supervisory_permission=True)
        self.assertFalse(auth.consent_is_current)
        self.assertFalse(auth.authorized)

    def test_road_a_and_road_b_stateful_comparison(self):
        results = compare_all()
        self.assertEqual(len(results), 4)
        by_name = {item["scenario"].name: item for item in results}

        # Scenario 1: Road A finishes faster (step 2), Road B yields/pauses on steps 1-2,
        # reconsiders at step 3, and still finishes on step 4 with 0 risky advances.
        s1 = by_name["01_kitchen_water_dynamic_encounter_and_recovery"]
        self.assertTrue(s1["road_a"].purpose_accomplished)
        self.assertEqual(s1["road_a"].completion_step, 2)
        self.assertTrue(s1["road_b"].purpose_accomplished)
        self.assertEqual(s1["road_b"].completion_step, 4)
        self.assertGreater(s1["road_a"].risky_or_ambiguous_advances, s1["road_b"].risky_or_ambiguous_advances)
        self.assertEqual(s1["road_b"].directive_contradictions, 0)

        # Scenario 2: Both roads share the same downstream safety floor and hold on stale/missing telemetry
        s2 = by_name["02_stale_and_missing_telemetry_equal_safety_floor"]
        self.assertEqual(s2["road_a"].executed_interruptions, 1)
        self.assertEqual(s2["road_b"].executed_interruptions, 1)
        self.assertTrue(s2["road_a"].purpose_accomplished)
        self.assertTrue(s2["road_b"].purpose_accomplished)

        # Scenario 3: Persistent ambiguity without consent -> Road B stays held at hallway_mid
        s3 = by_name["03_persistent_ambiguity_no_consent"]
        self.assertTrue(s3["road_a"].purpose_accomplished)
        self.assertFalse(s3["road_b"].purpose_accomplished)
        self.assertEqual(s3["road_b"].progress_achieved, 0)

        # Scenario 4: Conventional advantage where Harbor's OCCUPIED_UNENGAGED caution over-pauses
        s4 = by_name["04_occupied_bystander_tradeoff_conventional_advantage"]
        self.assertTrue(s4["road_a"].purpose_accomplished)
        self.assertFalse(s4["road_b"].purpose_accomplished)
        self.assertGreater(s4["road_b"].unnecessary_executed_interruptions, 0)


if __name__ == "__main__":
    unittest.main()