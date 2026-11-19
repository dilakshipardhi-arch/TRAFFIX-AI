"""
TRAFFIX AI - Traffic Signal Controllers Test Suite
Tests Fixed-Time baseline and Predictive Spillback-Aware Controller safeguards, gating, and TraCI execution.
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from controllers.fixed_controller import FixedTimeController
from controllers.spillback_controller import SpillbackAwareController
from simulation.sumo_runner import SumoSimulation
from core.queue_estimator import QueueEstimator
from core.queue_predictor import QueuePredictor
from core.spillback_detector import SpillbackDetector


class MockTraCI:
    class trafficlight:
        @staticmethod
        def setPhase(jid, phase):
            pass


class TestControllers(unittest.TestCase):
    def test_fixed_controller_cycle(self):
        """Verify fixed-time 90-second cycle progression."""
        ctrl = FixedTimeController(traci_instance=MockTraCI(), junction_ids=["J1"])

        # Phase 0 for 42 seconds
        for s in range(41):
            dec = ctrl.step(float(s))
            self.assertEqual(dec["J1"]["current_phase"], 0)

        # At second 42, should transition to Phase 1 (Yellow)
        dec_42 = ctrl.step(42.0)
        self.assertEqual(dec_42["J1"]["current_phase"], 1)

        # 3 seconds of yellow (Phase 1)
        ctrl.step(43.0)
        ctrl.step(44.0)
        dec_45 = ctrl.step(45.0)
        self.assertEqual(dec_45["J1"]["current_phase"], 2)  # Cross green

    def test_spillback_controller_safeguards(self):
        """Verify min green, max green, and yellow safeguards in proposed controller."""
        ctrl = SpillbackAwareController(traci_instance=MockTraCI(), junction_ids=["J1"])

        # High SRI on J1_to_J2 at step 5 (< MIN_GREEN = 10s)
        # Gating MUST NOT override min green safeguard!
        spillback_high = {
            "J1_to_J2": {"sri": 0.95, "alert_level": "CRITICAL"}
        }

        for s in range(9):
            dec = ctrl.step(float(s), spillback_reports=spillback_high)
            self.assertEqual(dec["J1"]["current_phase"], 0, "Min green safeguard violated!")
            self.assertEqual(dec["J1"]["action"], "HOLD_MIN_GREEN_SAFEGUARD")

        # At step 10 (t_phase = 10 >= MIN_GREEN), predictive gating triggers!
        dec_10 = ctrl.step(10.0, spillback_reports=spillback_high)
        self.assertEqual(dec_10["J1"]["current_phase"], 1)  # Switched to Yellow!
        self.assertIn("PREDICTIVE_GATING_TRIGGERED", dec_10["J1"]["action"])

    def test_max_green_safeguard(self):
        """Verify that maximum green (55s) is strictly enforced under continuous demand."""
        ctrl = SpillbackAwareController(traci_instance=MockTraCI(), junction_ids=["J1"])

        # Demand keeps requesting green extension, but downstream storage is safe
        queues = {"W_to_J1": {"max_queue_length_m": 50.0}}
        spillback_normal = {"J1_to_J2": {"sri": 0.2, "alert_level": "NORMAL"}}

        # Steps 0 to 53: should stay in corridor green (Phase 0)
        for s in range(54):
            dec = ctrl.step(float(s), queue_estimates=queues, spillback_reports=spillback_normal)
            self.assertEqual(dec["J1"]["current_phase"], 0)

        # At 55s (step index 54, t_phase=55), MAX_GREEN safeguard MUST force transition to Yellow
        dec_55 = ctrl.step(55.0, queue_estimates=queues, spillback_reports=spillback_normal)
        self.assertEqual(dec_55["J1"]["current_phase"], 1, "Expected transition to Yellow at max green")
        self.assertEqual(dec_55["J1"]["action"], "MAX_GREEN_SAFEGUARD_ENFORCED")

    def test_live_traci_controller_run(self):
        """Integration test: Run SpillbackAwareController with live TraCI for 30 steps."""
        cfg_path = os.path.join(PROJECT_ROOT, "simulation", "configs", "traffix_ai.sumocfg")
        sim = SumoSimulation(sumocfg_path=cfg_path, gui=False, step_length=1.0)

        try:
            sim.start()
            estimator = QueueEstimator(sim.traci)
            predictor = QueuePredictor(sim.traci)
            detector = SpillbackDetector()
            ctrl = SpillbackAwareController(sim.traci)

            for step in range(30):
                sim.step()
                t = sim.get_time()

                queues = estimator.estimate_all_queues(["W_to_J1", "J1_to_J2", "J2_to_J3"])
                predictions = predictor.predict_all(queues)
                spillback_reports = detector.assess_all_links(queues, predictions)

                decisions = ctrl.step(
                    current_time=t,
                    queue_estimates=queues,
                    queue_predictions=predictions,
                    spillback_reports=spillback_reports
                )

                self.assertIn("J1", decisions)
                self.assertIn("J2", decisions)
                self.assertIn("J3", decisions)

            print("\n[TEST] Live TraCI Controller Run: 30 steps completed.")
            print(f"[TEST] J1 State: {ctrl.get_junction_state('J1')['phase_name']}")
            print(f"[TEST] J2 State: {ctrl.get_junction_state('J2')['phase_name']}")
            print(f"[TEST] J3 State: {ctrl.get_junction_state('J3')['phase_name']}")

        finally:
            sim.close()


if __name__ == "__main__":
    unittest.main()
