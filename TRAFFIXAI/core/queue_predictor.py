"""
TRAFFIX AI - Queue Predictor Module
Implements short-term (10-30 seconds) queue growth and dissipation prediction
using traffic flow shockwave dynamics, vehicle approach velocities, and signal states.
"""

from typing import Dict, List, Any


class QueuePredictor:
    """Predicts spatial queue length and queued vehicle counts for 10s, 20s, and 30s horizons."""

    def __init__(self, traci_instance, avg_effective_veh_length: float = 7.0, sat_flow_rate_per_lane: float = 0.5):
        """
        Args:
            traci_instance: Active TraCI connection.
            avg_effective_veh_length: Average space occupied by a queued vehicle (length + gap) in meters.
                                      For mixed traffic (cars, bikes, buses, trucks), 7.0m is standard.
            sat_flow_rate_per_lane: Saturation departure flow rate in vehicles per second per lane (~1800 veh/hr/lane = 0.5 veh/s/lane).
        """
        self.traci = traci_instance
        self.avg_veh_len = avg_effective_veh_length
        self.sat_flow = sat_flow_rate_per_lane

    def predict_edge_queue(
        self,
        edge_id: str,
        current_queue_data: Dict[str, Any],
        is_green_phase: bool = False,
        remaining_green_time: float = 0.0
    ) -> Dict[str, Any]:
        """
        Predicts queue growth over 10s, 20s, and 30s lookahead windows.

        Args:
            edge_id: Approach edge ID (e.g. 'J1_to_J2')
            current_queue_data: Dictionary from QueueEstimator.estimate_edge_queue()
            is_green_phase: Whether this approach currently has green signal
            remaining_green_time: Remaining seconds of green phase (if green)
        """
        current_queue_m = current_queue_data["max_queue_length_m"]
        edge_len = current_queue_data["edge_length_m"]
        num_lanes = max(1, current_queue_data["num_lanes"])

        # Scan active cruising vehicles on this edge approaching the queue tail
        try:
            veh_ids = self.traci.edge.getLastStepVehicleIDs(edge_id)
        except Exception:
            veh_ids = []

        # Find cruising vehicles and calculate their time-to-queue arrival
        # Queue tail position is at (edge_len - current_queue_m) from edge start
        queue_tail_pos = max(0.0, edge_len - current_queue_m)

        arrivals_within = {10: 0, 20: 0, 30: 0}

        for vid in veh_ids:
            try:
                speed = self.traci.vehicle.getSpeed(vid)
                pos = self.traci.vehicle.getLanePosition(vid)
                # Only vehicles behind the queue tail that are moving forward
                if pos < queue_tail_pos and speed > 1.0:
                    dist_to_queue = queue_tail_pos - pos
                    eta = dist_to_queue / speed
                    for horizon in [10, 20, 30]:
                        if eta <= horizon:
                            arrivals_within[horizon] += 1
            except Exception:
                continue

        # Inflow rate smoothing: if link has upstream feed, account for upstream inflow
        # Compute predicted queue for each horizon: 10s, 20s, 30s
        predictions = {}

        for horizon in [10, 20, 30]:
            # Departures during this horizon:
            if is_green_phase:
                green_sec = min(float(horizon), max(0.0, remaining_green_time))
            else:
                green_sec = 0.0

            # Discharging capacity over horizon
            departures = green_sec * self.sat_flow * num_lanes

            # Arrivals over horizon
            arrivals = arrivals_within[horizon]

            # Net queue length change in meters:
            # delta_Q = (arrivals - departures) * (avg_veh_len / num_lanes)
            net_veh_change = arrivals - departures
            delta_q_m = (net_veh_change * self.avg_veh_len) / num_lanes

            predicted_queue_m = max(0.0, min(edge_len, current_queue_m + delta_q_m))
            predicted_queue_vehs = max(0, int(round((predicted_queue_m / self.avg_veh_len) * num_lanes)))

            # Growth rate (meters per second)
            growth_rate_mps = (predicted_queue_m - current_queue_m) / horizon

            predictions[f"{horizon}s"] = {
                "horizon_s": horizon,
                "predicted_queue_m": round(predicted_queue_m, 2),
                "predicted_queue_vehs": predicted_queue_vehs,
                "growth_rate_mps": round(growth_rate_mps, 2),
                "arrivals_count": arrivals,
                "departures_count": round(departures, 1),
            }

        return {
            "edge_id": edge_id,
            "current_queue_m": current_queue_m,
            "edge_length_m": edge_len,
            "predictions": predictions,
        }

    def predict_all(
        self,
        queue_estimates: Dict[str, Dict[str, Any]],
        signal_states: Dict[str, bool] = None,
        remaining_greens: Dict[str, float] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Runs predictions across all monitored edges."""
        signal_states = signal_states or {}
        remaining_greens = remaining_greens or {}

        results = {}
        for edge_id, q_data in queue_estimates.items():
            is_green = signal_states.get(edge_id, False)
            rem_green = remaining_greens.get(edge_id, 0.0)
            results[edge_id] = self.predict_edge_queue(
                edge_id=edge_id,
                current_queue_data=q_data,
                is_green_phase=is_green,
                remaining_green_time=rem_green
            )
        return results
