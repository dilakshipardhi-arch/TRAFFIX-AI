"""
TRAFFIX AI - Network & Route Verification Tests
Validates XML integrity, junction definitions, lane topologies, and vehicle classes.
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from simulation.networks.build_network import find_netconvert, build_network

class TestTrafficNetwork(unittest.TestCase):
    def setUp(self):
        self.net_dir = os.path.join(PROJECT_ROOT, "simulation", "networks")
        self.route_dir = os.path.join(PROJECT_ROOT, "simulation", "routes")
        self.config_dir = os.path.join(PROJECT_ROOT, "simulation", "configs")

    def test_01_xml_definition_files_exist(self):
        """Check all source definition XML files exist."""
        for fname in ["corridor_3j.nod.xml", "corridor_3j.edg.xml", "corridor_3j.con.xml"]:
            p = os.path.join(self.net_dir, fname)
            self.assertTrue(os.path.isfile(p), f"Missing required file: {fname}")
            # Ensure valid XML syntax
            tree = ET.parse(p)
            self.assertIsNotNone(tree.getroot())

    def test_02_junction_nodes(self):
        """Verify that the 3 signalised intersections exist with correct IDs."""
        nod_file = os.path.join(self.net_dir, "corridor_3j.nod.xml")
        tree = ET.parse(nod_file)
        root = tree.getroot()
        tls_nodes = {node.get("id"): node for node in root.findall("node") if node.get("type") == "traffic_light"}
        
        self.assertIn("J1", tls_nodes, "Missing traffic light node J1")
        self.assertIn("J2", tls_nodes, "Missing traffic light node J2")
        self.assertIn("J3", tls_nodes, "Missing traffic light node J3")
        self.assertEqual(len(tls_nodes), 3, "Expected exactly 3 signalised intersections")

    def test_03_critical_storage_edges(self):
        """Verify critical inter-intersection corridor links (J1->J2 and J2->J3)."""
        edg_file = os.path.join(self.net_dir, "corridor_3j.edg.xml")
        tree = ET.parse(edg_file)
        root = tree.getroot()
        edges = {edge.get("id"): edge for edge in root.findall("edge")}

        self.assertIn("J1_to_J2", edges, "Missing link J1_to_J2")
        self.assertIn("J2_to_J3", edges, "Missing link J2_to_J3")
        self.assertIn("W_to_J1", edges, "Missing inflow link W_to_J1")
        self.assertIn("J3_to_E", edges, "Missing outflow link J3_to_E")

        # Check lane count is 2 for main corridor
        self.assertEqual(edges["J1_to_J2"].get("numLanes"), "2")
        self.assertEqual(edges["J2_to_J3"].get("numLanes"), "2")

    def test_04_vehicle_types(self):
        """Verify heterogeneous fleet: car, motorcycle, bus, and truck."""
        rou_file = os.path.join(self.route_dir, "corridor_flows.rou.xml")
        tree = ET.parse(rou_file)
        root = tree.getroot()
        vtypes = {vt.get("id"): vt for vt in root.findall("vType")}

        required_types = ["car", "motorcycle", "bus", "truck"]
        for vt in required_types:
            self.assertIn(vt, vtypes, f"Missing vehicle type '{vt}' in corridor_flows.rou.xml")

        # Verify physical attributes differ
        car_len = float(vtypes["car"].get("length"))
        moto_len = float(vtypes["motorcycle"].get("length"))
        bus_len = float(vtypes["bus"].get("length"))
        truck_len = float(vtypes["truck"].get("length"))

        self.assertLess(moto_len, car_len, "Motorcycle length should be less than car")
        self.assertGreater(bus_len, car_len, "Bus length should be greater than car")
        self.assertGreater(truck_len, car_len, "Truck length should be greater than car")

    def test_05_configuration_files(self):
        """Verify SUMO config files exist and point to valid paths."""
        for cfg_name in ["traffix_ai.sumocfg", "fixed_time.sumocfg"]:
            p = os.path.join(self.config_dir, cfg_name)
            self.assertTrue(os.path.isfile(p), f"Missing config: {cfg_name}")
            tree = ET.parse(p)
            root = tree.getroot()
            self.assertIsNotNone(root.find(".//net-file"))
            self.assertIsNotNone(root.find(".//route-files"))

if __name__ == "__main__":
    unittest.main()
