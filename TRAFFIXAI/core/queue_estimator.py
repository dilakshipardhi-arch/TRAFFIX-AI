"""
TRAFFIX AI - Queue Estimator Module
Estimates real-time queued vehicle counts and spatial queue lengths (meters)
on each intersection approach lane using TraCI vehicle state telemetry.
"""

from typing import Dict, List, Any


class QueueEstimator:
    """Estimates physical spatial queue length (m) and vehicle queue counts."""

    def __init__(self, traci_instance, queue_speed_threshold: float = 1.0):
        """
        Args:
            traci_instance: Active TraCI connection.
            queue_speed_threshold: Maximum speed (m/s) to classify a vehicle as queued/halting.
                                   Default 1.0 m/s (~3.6 km/h) accounts for crawl in queue.
        """
        self.traci = traci_instance
        self.speed_threshold = queue_speed_threshold
        # Cache lane lengths so we don't query static topology repeatedly
        self._lane_lengths: Dict[str, float] = {}

    def get_lane_length(self, lane_id: str) -> float:
        """Retrieves and caches lane length."""
        if lane_id not in self._lane_lengths:
            try:
                self._lane_lengths[lane_id] = self.traci.lane.getLength(lane_id)
            except Exception:
                self._lane_lengths[lane_id] = 250.0  # fallback default
        return self._lane_lengths[lane_id]

    def estimate_lane_queue(self, lane_id: str) -> Dict[str, Any]:
        """
        Estimates spatial queue length (in meters) and queued vehicle count on a single lane.
        
        Spatial Queue Length:
        Measured from the downstream stopline back to the rear bumper of the furthest queued vehicle.
        L_queue = lane_length - min(pos_front - veh_length) for all queued vehicles.
        """
        lane_len = self.get_lane_length(lane_id)
        veh_ids = self.traci.lane.getLastStepVehicleIDs(lane_id)

        if not veh_ids:
            return {
                "lane_id": lane_id,
                "lane_length_m": lane_len,
                "queue_count": 0,
                "total_count": 0,
                "queue_length_m": 0.0,
                "occupancy_pct": 0.0,
            }

        queued_veh_count = 0
        min_rear_pos = lane_len
        total_veh_space = 0.0

        for vid in veh_ids:
            try:
                speed = self.traci.vehicle.getSpeed(vid)
                pos = self.traci.vehicle.getLanePosition(vid) # front bumper from lane start
                length = self.traci.vehicle.getLength(vid)
                min_gap = 2.0  # default spacing

                total_veh_space += (length + min_gap)

                # A vehicle is part of the queue if it is below the crawl speed threshold
                if speed <= self.speed_threshold:
                    queued_veh_count += 1
                    rear_pos = pos - length
                    if rear_pos < min_rear_pos:
                        min_rear_pos = rear_pos
            except Exception:
                continue

        # Spatial queue length from stopline to furthest queued vehicle
        if queued_veh_count > 0:
            spatial_queue_m = max(0.0, lane_len - min_rear_pos)
        else:
            spatial_queue_m = 0.0

        occupancy_pct = min(100.0, (total_veh_space / lane_len) * 100.0)

        return {
            "lane_id": lane_id,
            "lane_length_m": round(lane_len, 1),
            "queue_count": queued_veh_count,
            "total_count": len(veh_ids),
            "queue_length_m": round(spatial_queue_m, 2),
            "occupancy_pct": round(occupancy_pct, 1),
        }

    def estimate_edge_queue(self, edge_id: str) -> Dict[str, Any]:
        """
        Aggregates queue metrics across all lanes of an edge approach.
        """
        try:
            num_lanes = self.traci.edge.getLaneNumber(edge_id)
        except Exception:
            num_lanes = 2

        lane_data = []
        max_queue_m = 0.0
        sum_queue_m = 0.0
        total_queue_count = 0
        total_veh_count = 0
        edge_len = 0.0

        for i in range(num_lanes):
            lane_id = f"{edge_id}_{i}"
            ldata = self.estimate_lane_queue(lane_id)
            lane_data.append(ldata)
            max_queue_m = max(max_queue_m, ldata["queue_length_m"])
            sum_queue_m += ldata["queue_length_m"]
            total_queue_count += ldata["queue_count"]
            total_veh_count += ldata["total_count"]
            edge_len = ldata["lane_length_m"]

        avg_queue_m = (sum_queue_m / num_lanes) if num_lanes > 0 else 0.0

        return {
            "edge_id": edge_id,
            "edge_length_m": edge_len,
            "num_lanes": num_lanes,
            "max_queue_length_m": round(max_queue_m, 2),
            "avg_queue_length_m": round(avg_queue_m, 2),
            "total_queued_vehicles": total_queue_count,
            "total_vehicles": total_veh_count,
            "lanes": lane_data,
        }

    def estimate_all_queues(self, edge_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Estimates queues for all requested edges."""
        return {eid: self.estimate_edge_queue(eid) for eid in edge_ids}
