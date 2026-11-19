"""
TRAFFIX AI - Core Engine Unit & Integration Tests
Validates queue estimation, prediction equations, storage monitoring, and TraCI metrics collection.
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.queue_estimator import QueueEstimator
from core.queue_predictor import QueuePredictor
from core.spillback_detector import SpillbackDetector
from core.metrics_collector import MetricsCollector
from simulation.sumo_runner import SumoSimulation


class TestCoreEngine(unittest.TestCase):
    def test_queue_predictor_calculations(self):
        """Test mathematical behavior and bounds of QueuePredictor."""
        # Use dummy TraCI instance for unit test
        class MockTraCI:
            class edge:
                @staticmethod
                def getLastStepVehicleIDs(edge_id):
                    return []

        predictor = QueuePredictor(traci_instance=MockTraCI(), avg_effective_veh_length=7.0, sat_flow_rate_per_lane=0.5)

        current_data = {
            "max_queue_length_m": 50.0,
            "edge_length_m": 250.0,
            "num_lanes": 2
        }

        # Case 1: Red phase, no arrivals -> queue stays at 50m
        res_red = predictor.predict_edge_queue(
            edge_id="test_edge",
            current_queue_data=current_data,
            is_green_phase=False,
            remaining_green_time=0.0
        )
        self.assertEqual(res_red["predictions"]["10s"]["predicted_queue_m"], 50.0)
        self.assertEqual(res_red["predictions"]["20s"]["predicted_queue_m"], 50.0)
        self.assertEqual(res_red["predictions"]["30s"]["predicted_queue_m"], 50.0)

        # Case 2: Green phase discharging for 20 seconds
        res_green = predictor.predict_edge_queue(
            edge_id="test_edge",
            current_queue_data=current_data,
            is_green_phase=True,
            remaining_green_time=25.0
        )
        # 10s green -> 10s * 0.5 veh/s/lane * 2 lanes = 10 vehs discharged
        # 10 vehs * (7.0m / 2 lanes) = 35.0m queue dissipated
        # predicted = 50.0 - 35.0 = 15.0m
        self.assertAlmostEqual(res_green["predictions"]["10s"]["predicted_queue_m"], 15.0, places=1)
        # 20s green -> queue fully dissipates to 0m (cannot be negative)
        self.assertEqual(res_green["predictions"]["20s"]["predicted_queue_m"], 0.0)

    def test_spillback_detector_thresholds(self):
        """Test Spillback Risk Index (SRI) and alert escalation."""
        detector = SpillbackDetector(critical_links=["J1_to_J2"], safety_buffer_m=25.0)

        link_len = 250.0 # usable = 225.0m

        # Test Normal Condition (Queue = 40m)
        pred_normal = {
            "10s": {"predicted_queue_m": 45.0},
            "20s": {"predicted_queue_m": 50.0},
            "30s": {"predicted_queue_m": 55.0},
        }
        rep_normal = detector.assess_link_storage("J1_to_J2", 40.0, link_len, pred_normal)
        self.assertIn(rep_normal["alert_level"], ["LOW", "NORMAL"])
        self.assertLess(rep_normal["sri"], 0.5)

        # Test High Risk Condition (Queue = 160m)
        pred_high = {
            "10s": {"predicted_queue_m": 165.0},
            "20s": {"predicted_queue_m": 175.0},
            "30s": {"predicted_queue_m": 185.0},
        }
        rep_high = detector.assess_link_storage("J1_to_J2", 160.0, link_len, pred_high)
        self.assertIn(rep_high["alert_level"], ["HIGH_RISK", "CRITICAL"])
        self.assertGreaterEqual(rep_high["sri"], 0.70)

        # Test Critical Condition (Queue = 215m near 225m usable limit)
        pred_crit = {
            "10s": {"predicted_queue_m": 220.0},
            "20s": {"predicted_queue_m": 230.0},
            "30s": {"predicted_queue_m": 240.0},
        }
        rep_crit = detector.assess_link_storage("J1_to_J2", 215.0, link_len, pred_crit)
        self.assertEqual(rep_crit["alert_level"], "CRITICAL")
        self.assertEqual(rep_crit["action_recommendation"], "GATE_UPSTREAM_AND_FLUSH_DOWNSTREAM")

    def test_live_traci_core_integration(self):
        """Test all 4 core modules running in a live TraCI simulation for 25 steps."""
        cfg_path = os.path.join(PROJECT_ROOT, "simulation", "configs", "fixed_time.sumocfg")
        sim = SumoSimulation(sumocfg_path=cfg_path, gui=False, step_length=1.0)
        
        try:
            sim.start()
            collector = MetricsCollector(sim.traci)
            estimator = QueueEstimator(sim.traci)
            predictor = QueuePredictor(sim.traci)
            detector = SpillbackDetector()

            for step in range(25):
                sim.step()
                # 1. Collect Metrics
                metrics = collector.collect_step_metrics()
                self.assertIn("network", metrics)
                self.assertIn("emissions_step", metrics)

                # 2. Estimate Queues
                queues = estimator.estimate_all_queues(["W_to_J1", "J1_to_J2", "J2_to_J3"])
                self.assertIn("J1_to_J2", queues)
                self.assertGreaterEqual(queues["J1_to_J2"]["max_queue_length_m"], 0.0)

                # 3. Predict Queues
                predictions = predictor.predict_all(queues)
                self.assertIn("J1_to_J2", predictions)
                self.assertIn("10s", predictions["J1_to_J2"]["predictions"])

                # 4. Detect Spillback
                spillback_reports = detector.assess_all_links(queues, predictions)
                self.assertIn("J1_to_J2", spillback_reports)
                self.assertIn("sri", spillback_reports["J1_to_J2"])
                self.assertIn("remaining_storage_pct", spillback_reports["J1_to_J2"])

            print("\n[TEST] Core Engine Integration: 25 simulation steps completed successfully.")
            latest = collector.get_latest_metrics()
            print(f"[TEST] Live Active Vehicles: {latest['network']['active_vehicles']}")
            print(f"[TEST] Total CO2 Generated: {latest['emissions_cumulative']['co2_kg']} kg")
            print(f"[TEST] Total Fuel Consumed: {latest['emissions_cumulative']['fuel_liters']} L")

        finally:
            sim.close()


if __name__ == "__main__":
    unittest.main()
