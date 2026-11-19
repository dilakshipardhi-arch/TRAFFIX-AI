"""
TRAFFIX AI - Upgraded Features Test Suite
Tests:
1. Scenario generator across all 5 density tiers (Normal, Medium, High, Extreme, Stress Test)
2. Emergency vehicle preemption logic
3. OpenCV camera vehicle detection & tripwire counting
4. HTML5 canvas vehicle coordinate streaming in /api/status
"""

import os
import sys
import unittest
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from simulation.routes.scenario_generator import SCENARIO_CONFIGS, generate_scenario_xml
from controllers.spillback_controller import SpillbackAwareController
from core.camera_detector import CameraVehicleDetector, VideoStreamHandler
from web.app import app, mgr


class TestUpgradedFeatures(unittest.TestCase):

    def test_01_all_five_scenario_densities(self):
        """Verify scenario generation for all 5 density tiers."""
        for key in ["normal", "medium", "high", "extreme", "stress_test"]:
            self.assertIn(key, SCENARIO_CONFIGS)
            out_file = os.path.join(PROJECT_ROOT, "simulation", "routes", f"test_{key}.rou.xml")
            try:
                res_path = generate_scenario_xml(key, duration=600, output_path=out_file)
                self.assertTrue(os.path.isfile(res_path))
                self.assertGreater(os.path.getsize(res_path), 500)
            finally:
                if os.path.isfile(out_file):
                    os.remove(out_file)

    def test_02_emergency_vehicle_detection_logic(self):
        """Test emergency vehicle preemption detection."""
        class MockEmergencyTraCI:
            class edge:
                @staticmethod
                def getLastStepVehicleIDs(edge_id):
                    return ["ambulance_99"] if edge_id == "W_to_J1" else []

            class vehicle:
                @staticmethod
                def getTypeID(vid):
                    return "emergency"

                @staticmethod
                def getLanePosition(vid):
                    return 200.0 # 250 - 200 = 50m to stopline

            class lane:
                @staticmethod
                def getLength(lane_id):
                    return 250.0

            class trafficlight:
                @staticmethod
                def setPhase(jid, p):
                    pass

        ctrl = SpillbackAwareController(traci_instance=MockEmergencyTraCI(), junction_ids=["J1"])
        em_info = ctrl._check_emergency_vehicles("J1")
        self.assertTrue(em_info["detected"])
        self.assertEqual(em_info["target_phase"], 0) # Corridor green
        self.assertEqual(em_info["dist_m"], 50.0)

    def test_03_camera_detector_processing(self):
        """Test OpenCV vehicle detection on synthetic frame."""
        detector = CameraVehicleDetector()
        dummy_frame = np.zeros((360, 640, 3), dtype=np.uint8)

        # Draw a simulated vehicle rectangle crossing detection line
        dummy_frame[180:240, 200:260] = (255, 255, 255)

        annotated, metrics = detector.process_frame(dummy_frame)
        self.assertEqual(annotated.shape, (360, 640, 3))
        self.assertIn("mode", metrics)
        self.assertIn("active_vehicles", metrics)
        self.assertIn("fps", metrics)

    def test_04_vehicle_coordinates_in_status_api(self):
        """Test that /api/status contains vehicle coordinate list for 2D canvas."""
        client = app.test_client()
        mgr.init_simulation("spillback_aware", "normal")
        mgr.is_paused = True

        for _ in range(10):
            mgr.single_step()

        res = client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertIn("vehicles", data)
        self.assertIsInstance(data["vehicles"], list)
        if len(data["vehicles"]) > 0:
            first_v = data["vehicles"][0]
            self.assertIn("x", first_v)
            self.assertIn("y", first_v)
            self.assertIn("speed_kmh", first_v)
            self.assertIn("angle", first_v)
            self.assertIn("type", first_v)

        mgr._close_existing()


if __name__ == "__main__":
    unittest.main()
