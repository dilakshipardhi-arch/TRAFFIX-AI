"""
TRAFFIX AI - Web API & Dashboard Endpoints Test Suite
Validates Flask server routes, status polling, simulation step triggers, and benchmark data endpoints.
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from web.app import app, mgr


class TestWebAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.testing = True
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        mgr._close_existing()

    def test_01_index_and_comparison_pages(self):
        """Test HTML dashboard pages render successfully."""
        res_index = self.client.get("/")
        self.assertEqual(res_index.status_code, 200)
        self.assertIn(b"TRAFFIX AI", res_index.data)
        self.assertIn(b"Predictive Spillback-Aware Signal Control", res_index.data)

        res_comp = self.client.get("/comparison")
        self.assertEqual(res_comp.status_code, 200)
        self.assertIn(b"Comparative Performance & Emission Evaluation", res_comp.data)

    def test_02_status_endpoint(self):
        """Test /api/status telemetry structure."""
        # Initialize simulation in paused mode so tests control step execution
        mgr.init_simulation("spillback_aware")
        mgr.is_paused = True

        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertIn("simulation_time", data)
        self.assertIn("network", data)
        self.assertIn("junctions", data)
        self.assertIn("queues", data)
        self.assertIn("spillback_reports", data)
        self.assertIn("emissions_cumulative", data)

        # Check junctions
        self.assertIn("J1", data["junctions"])
        self.assertIn("J2", data["junctions"])
        self.assertIn("J3", data["junctions"])

    def test_03_single_step_endpoint(self):
        """Test /api/step advances the simulation clock."""
        mgr.is_paused = True
        res = self.client.post("/api/step")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertGreaterEqual(data["simulation_time"], 1)

    def test_04_benchmark_results_endpoint(self):
        """Test /api/benchmark/results returns saved evaluation data."""
        res = self.client.get("/api/benchmark/results")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("summary", data)
        self.assertIn("improvements", data["summary"])
        self.assertIn("waiting_time_reduction_pct", data["summary"]["improvements"])


if __name__ == "__main__":
    unittest.main()
