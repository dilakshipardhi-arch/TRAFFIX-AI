"""
TRAFFIX AI - Simulation Execution Test
Tests launching SUMO with TraCI, stepping for 60 seconds, and checking vehicle insertion.
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from simulation.sumo_runner import SumoSimulation

class TestSimulationRun(unittest.TestCase):
    def test_traci_simulation_step(self):
        cfg_path = os.path.join(PROJECT_ROOT, "simulation", "configs", "fixed_time.sumocfg")
        self.assertTrue(os.path.isfile(cfg_path), f"Config file not found: {cfg_path}")

        sim = SumoSimulation(sumocfg_path=cfg_path, gui=False, step_length=1.0)
        try:
            print("\n[TEST] Starting SUMO via TraCI...")
            sim.start()
            self.assertTrue(sim.is_running(), "Simulation failed to start")

            # Check that 3 traffic light programs exist
            tls_ids = sim.traci.trafficlight.getIDList()
            print(f"[TEST] Detected Traffic Light Junctions: {tls_ids}")
            self.assertIn("J1", tls_ids)
            self.assertIn("J2", tls_ids)
            self.assertIn("J3", tls_ids)

            # Step forward for 60 seconds
            vehicle_counts = []
            for t in range(60):
                sim.step()
                num_vehs = sim.traci.vehicle.getIDCount()
                vehicle_counts.append(num_vehs)

            current_time = sim.get_time()
            self.assertEqual(current_time, 60.0, f"Expected simulation time 60.0s, got {current_time}")

            # Vehicles should have been injected into the network
            final_veh_count = vehicle_counts[-1]
            print(f"[TEST] Simulation reached {current_time}s. Active vehicles on network: {final_veh_count}")
            self.assertGreater(final_veh_count, 0, "No vehicles were inserted into the simulation!")

            # Verify that different vehicle types were spawned
            active_vehs = sim.traci.vehicle.getIDList()
            vtypes_present = set(sim.traci.vehicle.getTypeID(vid) for vid in active_vehs)
            print(f"[TEST] Vehicle types currently active: {vtypes_present}")
            self.assertTrue(len(vtypes_present) >= 2, "Expected multiple heterogeneous vehicle types")

        finally:
            sim.close()
            print("[TEST] TraCI closed cleanly.")

if __name__ == "__main__":
    unittest.main()
