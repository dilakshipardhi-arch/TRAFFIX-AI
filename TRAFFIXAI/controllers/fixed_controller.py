"""
TRAFFIX AI - Fixed-Time Traffic Controller (Baseline)
Implements standard non-adaptive fixed-time signal cycles across J1, J2, and J3.
Used as the benchmark against the proposed Predictive Spillback-Aware Controller.
"""

from typing import Dict, Any, List
from controllers.base_controller import BaseTrafficController


class FixedTimeController(BaseTrafficController):
    """
    Standard Fixed-Time Traffic Signal Controller.
    Cycle:
      Phase 0 (Corridor Green):  42s
      Phase 1 (Corridor Yellow):  3s
      Phase 2 (Cross Green):     42s
      Phase 3 (Cross Yellow):     3s
      Total Cycle:               90s
    """

    PHASE_NAMES = {
        0: "CORRIDOR_GREEN",
        1: "CORRIDOR_YELLOW",
        2: "CROSS_GREEN",
        3: "CROSS_YELLOW",
    }

    PHASE_DURATIONS = {
        0: 42,
        1: 3,
        2: 42,
        3: 3,
    }

    def __init__(self, traci_instance, junction_ids: List[str] = None):
        super().__init__(traci_instance, junction_ids)
        self.junction_states = {}
        for jid in self.junction_ids:
            self.junction_states[jid] = {
                "current_phase": 0,
                "phase_name": self.PHASE_NAMES[0],
                "time_in_phase": 0,
                "target_duration": self.PHASE_DURATIONS[0],
            }

    def reset(self):
        """Resets all junction states to Phase 0."""
        for jid in self.junction_ids:
            self.junction_states[jid] = {
                "current_phase": 0,
                "phase_name": self.PHASE_NAMES[0],
                "time_in_phase": 0,
                "target_duration": self.PHASE_DURATIONS[0],
            }
            try:
                self.traci.trafficlight.setPhase(jid, 0)
            except Exception:
                pass

    def step(
        self,
        current_time: float,
        queue_estimates: Dict[str, Any] = None,
        queue_predictions: Dict[str, Any] = None,
        spillback_reports: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Advances fixed-time cycles by 1 second for each junction."""
        decisions = {}

        for jid in self.junction_ids:
            state = self.junction_states[jid]
            state["time_in_phase"] += 1

            # Check if current phase duration has elapsed
            if state["time_in_phase"] >= state["target_duration"]:
                next_phase = (state["current_phase"] + 1) % 4
                state["current_phase"] = next_phase
                state["phase_name"] = self.PHASE_NAMES[next_phase]
                state["time_in_phase"] = 0
                state["target_duration"] = self.PHASE_DURATIONS[next_phase]

                # Apply to SUMO via TraCI
                self.traci.trafficlight.setPhase(jid, next_phase)

            decisions[jid] = {
                "junction_id": jid,
                "current_phase": state["current_phase"],
                "phase_name": state["phase_name"],
                "time_in_phase": state["time_in_phase"],
                "target_duration": state["target_duration"],
                "remaining_phase_time": max(0, state["target_duration"] - state["time_in_phase"]),
                "control_mode": "FIXED_TIME",
                "action": "CYCLE_MAINTAINED",
            }

        return decisions

    def get_junction_state(self, junction_id: str) -> Dict[str, Any]:
        """Returns live status of the junction."""
        return self.junction_states.get(junction_id, {})
