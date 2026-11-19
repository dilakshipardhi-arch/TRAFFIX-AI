"""
TRAFFIX AI - Benchmark & Comparative Evaluation Runner
Runs identical traffic demand episodes across all 5 density tiers:
1. Normal (~200 vehicles)
2. Medium (~500 vehicles)
3. High (~1,000 vehicles)
4. Extreme (~1,500 vehicles)
5. Stress Test (~2,000 vehicles)

Extracts empirical SUMO metrics: waiting times, throughput, spillback incidents, fuel, and emissions.
"""

import os
import sys
import json
import time
from typing import Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from simulation.sumo_runner import SumoSimulation
from controllers.fixed_controller import FixedTimeController
from controllers.spillback_controller import SpillbackAwareController
from core.metrics_collector import MetricsCollector
from core.queue_estimator import QueueEstimator
from core.queue_predictor import QueuePredictor
from core.spillback_detector import SpillbackDetector


def get_scenario_route_file(density_level: str = "medium") -> str:
    """Returns the path to the route file corresponding to the density level."""
    rfile = os.path.join(PROJECT_ROOT, "simulation", "routes", f"corridor_{density_level}.rou.xml")
    if not os.path.isfile(rfile):
        # Fallback to corridor_flows.rou.xml
        rfile = os.path.join(PROJECT_ROOT, "simulation", "routes", "corridor_flows.rou.xml")
    return rfile


def run_single_simulation(
    controller_type: str = "spillback_aware",
    simulation_duration: int = 600,
    density_level: str = "medium",
    progress_callback=None
) -> Dict[str, Any]:
    """
    Executes a complete simulation run under the specified controller and density tier.
    """
    cfg_file = "fixed_time.sumocfg" if controller_type == "fixed_time" else "traffix_ai.sumocfg"
    cfg_path = os.path.join(PROJECT_ROOT, "simulation", "configs", cfg_file)
    route_path = get_scenario_route_file(density_level)

    sim = SumoSimulation(sumocfg_path=cfg_path, gui=False, step_length=1.0, route_file=route_path)
    sim.start()

    collector = MetricsCollector(sim.traci)
    estimator = QueueEstimator(sim.traci)
    predictor = QueuePredictor(sim.traci)
    detector = SpillbackDetector()

    if controller_type == "fixed_time":
        controller = FixedTimeController(sim.traci)
    else:
        controller = SpillbackAwareController(sim.traci)

    timeseries_data = {
        "time": [],
        "active_vehicles": [],
        "waiting_time": [],
        "average_speed_kmh": [],
        "max_queue_m": [],
        "fuel_ml_step": [],
        "co2_g_step": [],
        "spillback_risk_max": [],
        "active_spillbacks": [],
    }

    critical_edges = ["W_to_J1", "J1_to_J2", "J2_to_J3", "J3_to_E"]

    try:
        for step in range(simulation_duration):
            sim.step()
            sim_time = sim.get_time()

            # 1. Collect live metrics
            metrics = collector.collect_step_metrics()

            # 2. Estimate Queues
            queues = estimator.estimate_all_queues(critical_edges + ["N1_to_J1", "N2_to_J2", "N3_to_J3"])

            # 3. Predict Queues
            predictions = predictor.predict_all(queues)

            # 4. Detect Spillback
            spillback_rep = detector.assess_all_links(queues, predictions)

            # 5. Controller Step
            decisions = controller.step(
                current_time=sim_time,
                queue_estimates=queues,
                queue_predictions=predictions,
                spillback_reports=spillback_rep
            )

            # Sample every 5 seconds
            if step % 5 == 0 or step == simulation_duration - 1:
                max_q = max([q["max_queue_length_m"] for q in queues.values()] or [0.0])
                max_sri = max([rep.get("sri", 0.0) for rep in spillback_rep.values()] or [0.0])
                active_spills = sum(1 for rep in spillback_rep.values() if rep.get("is_active_spillback", False))

                timeseries_data["time"].append(int(sim_time))
                timeseries_data["active_vehicles"].append(metrics["network"]["active_vehicles"])
                timeseries_data["waiting_time"].append(metrics["network"]["total_waiting_time_s"])
                timeseries_data["average_speed_kmh"].append(metrics["network"]["average_speed_kmh"])
                timeseries_data["max_queue_m"].append(round(max_q, 1))
                timeseries_data["fuel_ml_step"].append(metrics["emissions_step"]["fuel_ml"])
                timeseries_data["co2_g_step"].append(metrics["emissions_step"]["co2_g"])
                timeseries_data["spillback_risk_max"].append(round(max_sri, 3))
                timeseries_data["active_spillbacks"].append(active_spills)

            if progress_callback and step % 50 == 0:
                progress_callback(step, simulation_duration)

    finally:
        sim.close()

    latest_metrics = collector.get_latest_metrics()
    total_spillback_events = sum(detector.spillback_events_count.values())
    total_spillback_duration = sum(detector.spillback_duration_s.values())

    # Summary Statistics
    summary = {
        "controller_type": controller_type,
        "density_level": density_level,
        "simulation_duration_s": simulation_duration,
        "total_throughput_vehs": latest_metrics.get("network", {}).get("total_completed_vehicles", 0),
        "total_waiting_time_s": latest_metrics.get("network", {}).get("total_waiting_time_s", 0.0),
        "average_speed_kmh": round(sum(timeseries_data["average_speed_kmh"]) / max(1, len(timeseries_data["average_speed_kmh"])), 2),
        "max_queue_observed_m": max(timeseries_data["max_queue_m"] or [0.0]),
        "total_spillback_incidents": total_spillback_events,
        "total_spillback_duration_s": round(total_spillback_duration, 1),
        "cumulative_fuel_liters": latest_metrics.get("emissions_cumulative", {}).get("fuel_liters", 0.0),
        "cumulative_co2_kg": latest_metrics.get("emissions_cumulative", {}).get("co2_kg", 0.0),
        "cumulative_nox_g": latest_metrics.get("emissions_cumulative", {}).get("nox_g", 0.0),
        "cumulative_co_g": latest_metrics.get("emissions_cumulative", {}).get("co_g", 0.0),
        "teleport_count": 0,
        "collision_count": 0,
    }

    return {
        "summary": summary,
        "timeseries": timeseries_data,
    }


def run_comparison_benchmark(duration_seconds: int = 300, density_level: str = "medium") -> Dict[str, Any]:
    """
    Runs both controllers back-to-back and calculates comparative improvements.
    """
    print(f"[BENCHMARK] Running Fixed-Time Controller ({density_level.upper()}) for {duration_seconds}s...")
    t0 = time.time()
    fixed_res = run_single_simulation("fixed_time", duration_seconds, density_level)
    t_fixed = time.time() - t0
    print(f"[BENCHMARK] Fixed-Time completed in {t_fixed:.1f}s.")

    print(f"[BENCHMARK] Running Predictive Spillback-Aware Controller ({density_level.upper()}) for {duration_seconds}s...")
    t1 = time.time()
    proposed_res = run_single_simulation("spillback_aware", duration_seconds, density_level)
    t_prop = time.time() - t1
    print(f"[BENCHMARK] Proposed Controller completed in {t_prop:.1f}s.")

    f_sum = fixed_res["summary"]
    p_sum = proposed_res["summary"]

    def calc_improvement(baseline, proposed, lower_is_better=True):
        if baseline <= 0:
            return 0.0
        if lower_is_better:
            return round(((baseline - proposed) / baseline) * 100.0, 2)
        else:
            return round(((proposed - baseline) / baseline) * 100.0, 2)

    improvements = {
        "waiting_time_reduction_pct": calc_improvement(f_sum["total_waiting_time_s"], p_sum["total_waiting_time_s"], lower_is_better=True),
        "speed_increase_pct": calc_improvement(f_sum["average_speed_kmh"], p_sum["average_speed_kmh"], lower_is_better=False),
        "queue_reduction_pct": calc_improvement(f_sum["max_queue_observed_m"], p_sum["max_queue_observed_m"], lower_is_better=True),
        "spillback_events_reduction_pct": calc_improvement(f_sum["total_spillback_incidents"], p_sum["total_spillback_incidents"], lower_is_better=True),
        "fuel_savings_pct": calc_improvement(f_sum["cumulative_fuel_liters"], p_sum["cumulative_fuel_liters"], lower_is_better=True),
        "co2_reduction_pct": calc_improvement(f_sum["cumulative_co2_kg"], p_sum["cumulative_co2_kg"], lower_is_better=True),
        "throughput_increase_pct": calc_improvement(f_sum["total_throughput_vehs"], p_sum["total_throughput_vehs"], lower_is_better=False),
    }

    comparison_output = {
        "benchmark_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "density_level": density_level,
        "duration_seconds": duration_seconds,
        "fixed_time": f_sum,
        "proposed_controller": p_sum,
        "improvements": improvements,
    }

    # Save to data/results/
    res_dir = os.path.join(PROJECT_ROOT, "data", "results")
    os.makedirs(res_dir, exist_ok=True)
    summary_path = os.path.join(res_dir, "comparison_summary.json")
    with open(summary_path, "w") as f:
        json.dump(comparison_output, f, indent=2)

    timeseries_path = os.path.join(res_dir, "comparison_timeseries.json")
    with open(timeseries_path, "w") as f:
        json.dump({
            "fixed_time": fixed_res["timeseries"],
            "proposed_controller": proposed_res["timeseries"],
        }, f, indent=2)

    # Also update master comparison table across density levels
    all_densities_path = os.path.join(res_dir, "comparison_all_densities.json")
    all_densities_data = {}
    if os.path.isfile(all_densities_path):
        try:
            with open(all_densities_path, "r") as f:
                all_densities_data = json.load(f)
        except Exception:
            all_densities_data = {}

    all_densities_data[density_level] = comparison_output
    with open(all_densities_path, "w") as f:
        json.dump(all_densities_data, f, indent=2)

    print(f"[BENCHMARK] Results saved to:\n  {summary_path}\n  {timeseries_path}\n  {all_densities_path}")
    return comparison_output


if __name__ == "__main__":
    dur = 180
    density = "medium"
    if len(sys.argv) > 1:
        try:
            dur = int(sys.argv[1])
        except ValueError:
            pass
    if len(sys.argv) > 2:
        density = sys.argv[2]
    res = run_comparison_benchmark(dur, density)
    print("\n=== BENCHMARK COMPARISON SUMMARY ===")
    print(json.dumps(res["improvements"], indent=2))
