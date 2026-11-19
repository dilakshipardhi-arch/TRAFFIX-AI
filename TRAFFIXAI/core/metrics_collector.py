"""
TRAFFIX AI - Metrics Collector Module
Collects real-time vehicle counts, average speeds, waiting times,
and environmental emissions (CO2, fuel, NOx, CO, PMx) from SUMO via TraCI.
"""

from typing import Dict, List, Any


class MetricsCollector:
    """Aggregates step-by-step traffic and environmental telemetry from TraCI."""

    # Approximate fuel density for standard gasoline/diesel blend: 740 mg/ml (0.74 g/ml)
    FUEL_DENSITY_MG_PER_ML = 740.0

    def __init__(self, traci_instance, monitored_edges: List[str] = None):
        """
        Args:
            traci_instance: Active TraCI module or connection object.
            monitored_edges: List of SUMO edge IDs to monitor.
        """
        self.traci = traci_instance
        self.monitored_edges = monitored_edges or [
            "W_to_J1", "J1_to_J2", "J2_to_J3", "J3_to_E",
            "E_to_J3", "J3_to_J2", "J2_to_J1", "J1_to_W",
            "N1_to_J1", "S1_to_J1", "N2_to_J2", "S2_to_J2", "N3_to_J3", "S3_to_J3"
        ]

        # Cumulative totals (SUMO native emission units are mg/s per step)
        self.cumulative_co2_mg = 0.0          # in milligrams
        self.cumulative_fuel_mg = 0.0         # in milligrams (SUMO returns mg/s)
        self.cumulative_nox_mg = 0.0
        self.cumulative_co_mg = 0.0
        self.cumulative_pmx_mg = 0.0
        self.total_completed_vehicles = 0

        # Step history buffer
        self.step_history: List[Dict[str, Any]] = []

    def collect_step_metrics(self) -> Dict[str, Any]:
        """
        Reads edge-level and network-level metrics at the current simulation step.
        Returns a dictionary of structured metrics.
        """
        current_time = self.traci.simulation.getTime()
        
        step_co2_mg = 0.0
        step_fuel_mg = 0.0
        step_nox_mg = 0.0
        step_co_mg = 0.0
        step_pmx_mg = 0.0

        edge_stats: Dict[str, Dict[str, float]] = {}
        total_active_vehs = 0
        total_halting_vehs = 0
        total_waiting_time = 0.0
        speeds_list = []

        for edge_id in self.monitored_edges:
            try:
                veh_count = self.traci.edge.getLastStepVehicleNumber(edge_id)
                halting_count = self.traci.edge.getLastStepHaltingNumber(edge_id)
                mean_speed = self.traci.edge.getLastStepMeanSpeed(edge_id)
                waiting_time = self.traci.edge.getWaitingTime(edge_id)
                occupancy = self.traci.edge.getLastStepOccupancy(edge_id)

                # Emissions (SUMO returns mg/s for all gases and fuel)
                co2 = self.traci.edge.getCO2Emission(edge_id)
                fuel_mg = self.traci.edge.getFuelConsumption(edge_id)
                nox = self.traci.edge.getNOxEmission(edge_id)
                co = self.traci.edge.getCOEmission(edge_id)
                pmx = self.traci.edge.getPMxEmission(edge_id)

                step_co2_mg += co2
                step_fuel_mg += fuel_mg
                step_nox_mg += nox
                step_co_mg += co
                step_pmx_mg += pmx

                total_active_vehs += veh_count
                total_halting_vehs += halting_count
                total_waiting_time += waiting_time
                if veh_count > 0:
                    speeds_list.append(mean_speed)

                edge_fuel_ml = fuel_mg / self.FUEL_DENSITY_MG_PER_ML

                edge_stats[edge_id] = {
                    "vehicle_count": veh_count,
                    "halting_count": halting_count,
                    "mean_speed_mps": round(mean_speed, 2),
                    "mean_speed_kmh": round(mean_speed * 3.6, 2),
                    "waiting_time_s": round(waiting_time, 1),
                    "occupancy_pct": round(occupancy * 100.0, 1),
                    "co2_mg_s": round(co2, 2),
                    "fuel_ml_s": round(edge_fuel_ml, 2),
                }
            except Exception:
                continue

        # Completed (arrived) vehicles in this step
        arrived_this_step = self.traci.simulation.getArrivedNumber()
        self.total_completed_vehicles += arrived_this_step

        # Accumulate environmental metrics (mg)
        self.cumulative_co2_mg += step_co2_mg
        self.cumulative_fuel_mg += step_fuel_mg
        self.cumulative_nox_mg += step_nox_mg
        self.cumulative_co_mg += step_co_mg
        self.cumulative_pmx_mg += step_pmx_mg

        network_avg_speed = (sum(speeds_list) / len(speeds_list)) if speeds_list else 0.0

        # Conversions:
        # 1 g = 1,000 mg
        # 1 kg = 1,000,000 mg
        # 1 ml fuel = 740 mg
        # 1 Liter fuel = 740,000 mg
        step_fuel_ml = step_fuel_mg / self.FUEL_DENSITY_MG_PER_ML
        cum_fuel_liters = self.cumulative_fuel_mg / (self.FUEL_DENSITY_MG_PER_ML * 1000.0)

        step_data = {
            "time_seconds": current_time,
            "network": {
                "active_vehicles": total_active_vehs,
                "halting_vehicles": total_halting_vehs,
                "total_completed_vehicles": self.total_completed_vehicles,
                "average_speed_kmh": round(network_avg_speed * 3.6, 2),
                "total_waiting_time_s": round(total_waiting_time, 1),
            },
            "emissions_step": {
                "co2_g": round(step_co2_mg / 1000.0, 3),      # converted to grams
                "fuel_ml": round(step_fuel_ml, 2),            # in milliliters
                "nox_mg": round(step_nox_mg, 2),
                "co_mg": round(step_co_mg, 2),
                "pmx_mg": round(step_pmx_mg, 2),
            },
            "emissions_cumulative": {
                "co2_kg": round(self.cumulative_co2_mg / 1e6, 4), # converted to kilograms
                "fuel_liters": round(cum_fuel_liters, 3),         # converted to Liters
                "nox_g": round(self.cumulative_nox_mg / 1000.0, 3),
                "co_g": round(self.cumulative_co_mg / 1000.0, 3),
                "pmx_g": round(self.cumulative_pmx_mg / 1000.0, 3),
            },
            "edges": edge_stats,
        }

        # Keep last 300 steps in memory
        self.step_history.append(step_data)
        if len(self.step_history) > 300:
            self.step_history.pop(0)

        return step_data

    def get_latest_metrics(self) -> Dict[str, Any]:
        """Returns the most recent collected metrics snapshot."""
        return self.step_history[-1] if self.step_history else {}
