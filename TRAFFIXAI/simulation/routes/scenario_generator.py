"""
TRAFFIX AI - Scenario Generator
Generates realistic SUMO route schedules for 5 traffic density tiers:
1. Normal (~200 vehicles)
2. Medium (~500 vehicles)
3. High (~1,000 vehicles)
4. Extreme (~1,500 vehicles)
5. Stress Test (~2,000 vehicles)

Includes support for:
- Heterogeneous fleet (cars, motorcycles, buses, trucks, emergency vehicles)
- Uneven directional demands and turn ratios
- Sudden traffic bursts and surges
"""

import os
import xml.etree.ElementTree as ET

SCENARIO_CONFIGS = {
    "normal": {
        "name": "Normal Traffic",
        "description": "Balanced urban arterial flow with minimal queuing (~200 vehicles)",
        "arterial_we_rate": 350,   # veh/hr
        "arterial_ew_rate": 200,
        "cross_street_rate": 90,
        "duration": 1200,
    },
    "medium": {
        "name": "Medium Traffic",
        "description": "Standard peak-hour commute flow with localized queues (~500 vehicles)",
        "arterial_we_rate": 800,
        "arterial_ew_rate": 450,
        "cross_street_rate": 180,
        "duration": 1200,
    },
    "high": {
        "name": "High Traffic",
        "description": "Heavy peak flow testing short-term queue progression (~1,000 vehicles)",
        "arterial_we_rate": 1500,
        "arterial_ew_rate": 800,
        "cross_street_rate": 320,
        "duration": 1200,
    },
    "extreme": {
        "name": "Extreme Congestion",
        "description": "Severe oversaturation testing predictive gating before spillback (~1,500 vehicles)",
        "arterial_we_rate": 2200,
        "arterial_ew_rate": 1100,
        "cross_street_rate": 450,
        "duration": 1200,
    },
    "stress_test": {
        "name": "Stress Test (Gridlock Prevention)",
        "description": "Massive corridor surge testing anti-starvation & gridlock recovery (~2,000 vehicles)",
        "arterial_we_rate": 2800,
        "arterial_ew_rate": 1400,
        "cross_street_rate": 600,
        "duration": 1200,
    },
}


def generate_scenario_xml(
    scenario_key: str = "medium",
    duration: int = 1200,
    include_surge: bool = False,
    output_path: str = None
) -> str:
    """
    Generates a complete SUMO .rou.xml file for the given scenario configuration.
    """
    if scenario_key not in SCENARIO_CONFIGS:
        scenario_key = "medium"

    cfg = SCENARIO_CONFIGS[scenario_key]
    dur = duration or cfg["duration"]

    routes_root = ET.Element(
        "routes",
        {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation": "http://sumo.dlr.de/xsd/routes_file.xsd"
        }
    )

    # 1. Vehicle Type Definitions
    vtypes = [
        ("car", "passenger", "4.5", "1.8", "33.33", "2.6", "4.5", "0.5", "2.5", "passenger", "HBEFA3/PC_G_EU4", "0.2,0.6,1.0", "1.0"),
        ("motorcycle", "motorcycle", "2.2", "0.9", "38.89", "3.2", "5.0", "0.5", "1.5", "motorcycle", "HBEFA3/LDV_G_EU4", "1.0,0.8,0.0", "1.0"),
        ("bus", "bus", "12.0", "2.5", "22.22", "1.2", "3.5", "0.4", "3.0", "bus", "HBEFA3/Bus", "0.2,0.85,0.3", "1.0"),
        ("truck", "truck", "10.0", "2.5", "20.0", "1.3", "3.5", "0.4", "3.5", "truck", "HBEFA3/HDV_D_EU4", "0.9,0.3,0.3", "1.0"),
        ("emergency", "emergency", "6.5", "2.2", "38.89", "3.5", "5.0", "0.2", "2.0", "emergency", "HBEFA3/PC_G_EU4", "1.0,1.0,1.0", "1.3"),
    ]

    for tid, vclass, length, width, max_s, acc, dec, sig, min_g, shape, emiss, color, sfactor in vtypes:
        ET.SubElement(
            routes_root,
            "vType",
            {
                "id": tid,
                "vClass": vclass,
                "length": length,
                "width": width,
                "maxSpeed": max_s,
                "accel": acc,
                "decel": dec,
                "sigma": sig,
                "minGap": min_g,
                "guiShape": shape,
                "emissionClass": emiss,
                "color": color,
                "speedFactor": sfactor
            }
        )

    # 2. Route Definitions
    route_defs = [
        ("r_WE", "W_to_J1 J1_to_J2 J2_to_J3 J3_to_E"),
        ("r_EW", "E_to_J3 J3_to_J2 J2_to_J1 J1_to_W"),
        ("r_NS_1", "N1_to_J1 J1_to_S1"),
        ("r_SN_1", "S1_to_J1 J1_to_N1"),
        ("r_NS_2", "N2_to_J2 J2_to_S2"),
        ("r_SN_2", "S2_to_J2 J2_to_N2"),
        ("r_NS_3", "N3_to_J3 J3_to_S3"),
        ("r_SN_3", "S3_to_J3 J3_to_N3"),
        ("r_N1_E", "N1_to_J1 J1_to_J2 J2_to_J3 J3_to_E"),
        ("r_S1_E", "S1_to_J1 J1_to_J2 J2_to_J3 J3_to_E"),
        ("r_N2_E", "N2_to_J2 J2_to_J3 J3_to_E"),
        ("r_S2_E", "S2_to_J2 J2_to_J3 J3_to_E"),
    ]

    for rid, edges in route_defs:
        ET.SubElement(routes_root, "route", {"id": rid, "edges": edges})

    # 3. Base Flows Calculation based on rates
    rate_we = cfg["arterial_we_rate"]
    rate_ew = cfg["arterial_ew_rate"]
    rate_cross = cfg["cross_street_rate"]

    # Fleet split: 65% Car, 20% Motorcycle, 10% Bus, 5% Truck
    flows = [
        # Arterial West-to-East (Primary Corridor)
        ("f_car_we", "r_WE", "car", "0", str(dur), str(int(rate_we * 0.65))),
        ("f_moto_we", "r_WE", "motorcycle", "0", str(dur), str(int(rate_we * 0.20))),
        ("f_bus_we", "r_WE", "bus", "0", str(dur), str(max(10, int(rate_we * 0.10)))),
        ("f_truck_we", "r_WE", "truck", "0", str(dur), str(max(10, int(rate_we * 0.05)))),

        # Counter Flow East-to-West
        ("f_car_ew", "r_EW", "car", "0", str(dur), str(int(rate_ew * 0.65))),
        ("f_moto_ew", "r_EW", "motorcycle", "0", str(dur), str(int(rate_ew * 0.20))),
        ("f_bus_ew", "r_EW", "bus", "0", str(dur), str(max(5, int(rate_ew * 0.10)))),
        ("f_truck_ew", "r_EW", "truck", "0", str(dur), str(max(5, int(rate_ew * 0.05)))),

        # Cross Street Approaches (N/S at J1, J2, J3)
        ("f_cross_j1_ns", "r_NS_1", "car", "0", str(dur), str(int(rate_cross * 0.75))),
        ("f_cross_j1_sn", "r_SN_1", "car", "0", str(dur), str(int(rate_cross * 0.75))),
        ("f_turn_j1", "r_N1_E", "car", "0", str(dur), str(max(15, int(rate_cross * 0.25)))),

        ("f_cross_j2_ns", "r_NS_2", "car", "0", str(dur), str(int(rate_cross * 0.85))),
        ("f_cross_j2_sn", "r_SN_2", "car", "0", str(dur), str(int(rate_cross * 0.85))),
        ("f_cross_j2_bus", "r_NS_2", "bus", "0", str(dur), str(max(10, int(rate_cross * 0.15)))),
        ("f_turn_j2", "r_N2_E", "car", "0", str(dur), str(max(15, int(rate_cross * 0.25)))),

        ("f_cross_j3_ns", "r_NS_3", "car", "0", str(dur), str(int(rate_cross * 0.75))),
        ("f_cross_j3_sn", "r_SN_3", "car", "0", str(dur), str(int(rate_cross * 0.75))),
    ]

    for fid, r_id, vtype, b_time, e_time, vph in flows:
        ET.SubElement(
            routes_root,
            "flow",
            {
                "id": fid,
                "route": r_id,
                "type": vtype,
                "begin": b_time,
                "end": e_time,
                "vehsPerHour": vph,
                "departLane": "best",
                "departSpeed": "max" if vtype != "bus" else "avg"
            }
        )

    # 4. Optional Sudden Traffic Burst / Surge (e.g. at t=80 to t=240)
    if include_surge or scenario_key in ["extreme", "stress_test"]:
        ET.SubElement(
            routes_root,
            "flow",
            {
                "id": "f_surge_we",
                "route": "r_WE",
                "type": "car",
                "begin": "90",
                "end": "300",
                "vehsPerHour": "1200",
                "departLane": "best",
                "departSpeed": "max"
            }
        )
        ET.SubElement(
            routes_root,
            "flow",
            {
                "id": "f_surge_cross",
                "route": "r_NS_2",
                "type": "car",
                "begin": "150",
                "end": "350",
                "vehsPerHour": "600",
                "departLane": "best",
                "departSpeed": "max"
            }
        )

    # 5. Periodic Scheduled Emergency Priority Vehicle (Ambulance at t=120)
    ET.SubElement(
        routes_root,
        "vehicle",
        {
            "id": "ambulance_1",
            "type": "emergency",
            "route": "r_WE",
            "depart": "120",
            "departLane": "best",
            "departSpeed": "max"
        }
    )

    if not output_path:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(current_dir, f"scenario_{scenario_key}.rou.xml")

    # Format XML nicely
    tree = ET.ElementTree(routes_root)
    ET.indent(tree, space="    ", level=0)
    tree.write(output_path, encoding="UTF-8", xml_declaration=True)
    return output_path


def generate_all_scenarios():
    """Generates all 5 scenario route files in simulation/routes/."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    generated_files = {}
    for key in SCENARIO_CONFIGS:
        out_f = os.path.join(current_dir, f"corridor_{key}.rou.xml")
        res = generate_scenario_xml(key, duration=1800, output_path=out_f)
        generated_files[key] = res
        print(f"[SCENARIO GENERATOR] Created {key.upper()}: {out_f}")
    return generated_files


if __name__ == "__main__":
    generate_all_scenarios()
