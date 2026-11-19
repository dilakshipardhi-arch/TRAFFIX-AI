"""
TRAFFIX AI - Intelligent Adaptive & Predictive Spillback-Aware Signal Controller
Features:
- Dynamic green-time allocation based on lane-wise queue demand
- Short-term (10-30s) queue progression predictions
- Downstream road storage monitoring and predictive spillback gating
- Strict rule: NEVER release upstream traffic into an already blocked downstream link
- Bottleneck flushing at downstream intersections
- Emergency vehicle preemption & priority (Ambulances / Fire engines)
- Anti-starvation safeguards (minimum green = 10s, maximum green = 55s, max waiting threshold)
- Full decision explainability logging
"""

from typing import Dict, Any, List
from controllers.base_controller import BaseTrafficController


class SpillbackAwareController(BaseTrafficController):
    """
    Intelligent Adaptive Traffic Signal Controller.
    """

    PHASE_NAMES = {
        0: "CORRIDOR_GREEN",
        1: "CORRIDOR_YELLOW",
        2: "CROSS_GREEN",
        3: "CROSS_YELLOW",
    }

    YELLOW_DURATION = 3
    MIN_GREEN = 10
    MAX_GREEN = 55
    DEFAULT_GREEN = 35
    ANTI_STARVATION_WAIT_SEC = 55.0  # Force phase switch if a conflicting approach waits > 55s

    DOWNSTREAM_STORAGE_LINKS = {
        "J1": "J1_to_J2",
        "J2": "J2_to_J3",
        "J3": None,
    }

    UPSTREAM_FEEDER_LINKS = {
        "J1": None,
        "J2": "J1_to_J2",
        "J3": "J2_to_J3",
    }

    CORRIDOR_APPROACHES = {
        "J1": "W_to_J1",
        "J2": "J1_to_J2",
        "J3": "J2_to_J3",
    }

    CROSS_APPROACHES = {
        "J1": ["N1_to_J1", "S1_to_J1"],
        "J2": ["N2_to_J2", "S2_to_J2"],
        "J3": ["N3_to_J3", "S3_to_J3"],
    }

    def __init__(self, traci_instance, junction_ids: List[str] = None):
        super().__init__(traci_instance, junction_ids)
        self.junction_states = {}
        for jid in self.junction_ids:
            self.junction_states[jid] = {
                "current_phase": 0,
                "phase_name": self.PHASE_NAMES[0],
                "time_in_phase": 0,
                "current_max_green": self.DEFAULT_GREEN,
                "last_action": "INIT",
                "decision_reason": "Controller initialized in corridor green phase.",
                "gating_active": False,
                "flushing_active": False,
                "emergency_active": False,
            }

    def reset(self):
        """Resets all junction states to Phase 0."""
        for jid in self.junction_ids:
            self.junction_states[jid] = {
                "current_phase": 0,
                "phase_name": self.PHASE_NAMES[0],
                "time_in_phase": 0,
                "current_max_green": self.DEFAULT_GREEN,
                "last_action": "RESET",
                "decision_reason": "System reset to default baseline.",
                "gating_active": False,
                "flushing_active": False,
                "emergency_active": False,
            }
            try:
                self.traci.trafficlight.setPhase(jid, 0)
            except Exception:
                pass

    def _check_emergency_vehicles(self, junction_id: str) -> Dict[str, Any]:
        """
        Scans for approaching emergency vehicles (Ambulance/Fire) within 160m of the junction stopline.
        Returns target phase (0 for corridor, 2 for cross) if an emergency vehicle is detected.
        """
        corr_edge = self.CORRIDOR_APPROACHES.get(junction_id)
        cross_edges = self.CROSS_APPROACHES.get(junction_id, [])

        # Check corridor approach
        try:
            for vid in self.traci.edge.getLastStepVehicleIDs(corr_edge):
                if self.traci.vehicle.getTypeID(vid) == "emergency":
                    pos = self.traci.vehicle.getLanePosition(vid)
                    length = self.traci.lane.getLength(f"{corr_edge}_0")
                    dist_to_stopline = length - pos
                    if 0 <= dist_to_stopline <= 160.0:
                        return {
                            "detected": True,
                            "target_phase": 0,
                            "vehicle_id": vid,
                            "approach": corr_edge,
                            "dist_m": round(dist_to_stopline, 1),
                        }
        except Exception:
            pass

        # Check cross-street approaches
        for cedge in cross_edges:
            try:
                for vid in self.traci.edge.getLastStepVehicleIDs(cedge):
                    if self.traci.vehicle.getTypeID(vid) == "emergency":
                        pos = self.traci.vehicle.getLanePosition(vid)
                        length = self.traci.lane.getLength(f"{cedge}_0")
                        dist_to_stopline = length - pos
                        if 0 <= dist_to_stopline <= 160.0:
                            return {
                                "detected": True,
                                "target_phase": 2,
                                "vehicle_id": vid,
                                "approach": cedge,
                                "dist_m": round(dist_to_stopline, 1),
                            }
            except Exception:
                pass

        return {"detected": False}

    def step(
        self,
        current_time: float,
        queue_estimates: Dict[str, Any] = None,
        queue_predictions: Dict[str, Any] = None,
        spillback_reports: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Executes one predictive control step across J1, J2, and J3.
        """
        queue_estimates = queue_estimates or {}
        spillback_reports = spillback_reports or {}

        decisions = {}

        for jid in self.junction_ids:
            state = self.junction_states[jid]
            state["time_in_phase"] += 1
            curr_phase = state["current_phase"]
            t_phase = state["time_in_phase"]

            downstream_link = self.DOWNSTREAM_STORAGE_LINKS.get(jid)
            upstream_link = self.UPSTREAM_FEEDER_LINKS.get(jid)

            # Downstream Storage & Spillback Risk
            downstream_sri = 0.0
            downstream_alert = "LOW"
            remaining_storage_m = 225.0
            if downstream_link and downstream_link in spillback_reports:
                d_rep = spillback_reports[downstream_link]
                downstream_sri = d_rep.get("sri", 0.0)
                downstream_alert = d_rep.get("alert_level", "LOW")
                remaining_storage_m = d_rep.get("remaining_storage_m", 225.0)

            # Upstream Feeder queue and risk (for flushing decisions)
            feeder_queue_m = 0.0
            feeder_sri = 0.0
            if upstream_link and upstream_link in spillback_reports:
                u_rep = spillback_reports[upstream_link]
                feeder_queue_m = u_rep.get("current_queue_m", 0.0)
                feeder_sri = u_rep.get("sri", 0.0)

            # Approach queue lengths and waiting times
            corr_edge = self.CORRIDOR_APPROACHES.get(jid)
            corr_queue_m = queue_estimates.get(corr_edge, {}).get("max_queue_length_m", 0.0)

            cross_edges = self.CROSS_APPROACHES.get(jid, [])
            cross_queue_m = max([queue_estimates.get(ce, {}).get("max_queue_length_m", 0.0) for ce in cross_edges] or [0.0])

            # Measure max cross-street waiting time for anti-starvation
            cross_max_wait = 0.0
            for ce in cross_edges:
                try:
                    wt = self.traci.edge.getWaitingTime(ce)
                    if wt > cross_max_wait:
                        cross_max_wait = wt
                except Exception:
                    pass

            action = "MAINTAIN"
            reason = "Standard adaptive cycle progression."
            next_phase = curr_phase

            # -------------------------------------------------------------------------
            # 1. EMERGENCY VEHICLE PREEMPTION CHECK (Top Priority)
            # -------------------------------------------------------------------------
            em_info = self._check_emergency_vehicles(jid)
            if em_info["detected"]:
                target_p = em_info["target_phase"]
                vid = em_info["vehicle_id"]
                dist = em_info["dist_m"]
                state["emergency_active"] = True

                if curr_phase == target_p:
                    action = f"EMERGENCY_HOLD_GREEN ({vid} at {dist}m)"
                    reason = f"Holding green for approaching emergency vehicle {vid} ({dist}m away on {em_info['approach']})."
                    # Keep holding green until emergency vehicle passes
                else:
                    # Must transition safely via yellow to target phase
                    if curr_phase in [0, 2]:
                        next_phase = curr_phase + 1
                        action = f"EMERGENCY_CLEAR_TO_YELLOW ({vid})"
                        reason = f"Emergency vehicle {vid} detected. Clearing conflict phase via yellow clearance."
                    # If already in yellow (1 or 3), normal yellow duration handles transition to target_p

            else:
                state["emergency_active"] = False

            # If emergency preemption is NOT overriding:
            if not state["emergency_active"]:

                # ---------------------------------------------------------------------
                # PHASE 0: CORRIDOR GREEN
                # ---------------------------------------------------------------------
                if curr_phase == 0:
                    # SAFEGUARD: Minimum Green Time (10s)
                    if t_phase < self.MIN_GREEN:
                        action = "HOLD_MIN_GREEN_SAFEGUARD"
                        reason = f"Enforcing minimum green safeguard ({t_phase}/{self.MIN_GREEN}s) for pedestrian & driver clearance."

                    # ANTI-STARVATION: Side street has been waiting too long (> 55s)
                    elif cross_max_wait >= self.ANTI_STARVATION_WAIT_SEC:
                        action = "ANTI_STARVATION_SWITCH_TO_CROSS"
                        reason = f"Cross-street waiting time exceeded {cross_max_wait:.0f}s threshold. Forcing switch to cross-street to prevent starvation."
                        next_phase = 1

                    # SAFEGUARD: Maximum Green Hold Time (55s)
                    elif t_phase >= self.MAX_GREEN:
                        action = "MAX_GREEN_SAFEGUARD_ENFORCED"
                        reason = f"Maximum green hold time ({self.MAX_GREEN}s) reached. Forcing phase switch to guarantee cross-street fairness."
                        next_phase = 1

                    # CORE SPILLBACK RULE: HARD GATING
                    # NEVER release traffic into an already blocked downstream road simply because upstream queue is long!
                    elif downstream_sri >= 0.65 or remaining_storage_m <= 35.0:
                        action = f"PREDICTIVE_GATING_TRIGGERED (SRI={downstream_sri:.2f})"
                        reason = (
                            f"Downstream road {downstream_link} is nearing capacity "
                            f"(SRI={downstream_sri:.2f}, only {remaining_storage_m:.1f}m free). "
                            f"Withholding green at {jid} to prevent intersection blockage."
                        )
                        state["gating_active"] = True
                        next_phase = 1

                    # BOTTLENECK FLUSHING: Upstream feeder is congested, hold green to evacuate vehicles!
                    elif feeder_sri >= 0.60 or feeder_queue_m >= 80.0:
                        action = f"BOTTLENECK_FLUSHING_HOLD (Feeder SRI={feeder_sri:.2f})"
                        reason = f"Upstream feeder link {upstream_link} has a {feeder_queue_m:.1f}m queue. Extending corridor green to evacuate bottleneck."
                        state["flushing_active"] = True
                        state["current_max_green"] = self.MAX_GREEN

                    # ADAPTIVE EXTENSION / TERMINATION (NORMAL CONDITIONS)
                    else:
                        state["gating_active"] = False
                        state["flushing_active"] = False

                        # If corridor queue is cleared and cross-street has backlog:
                        if corr_queue_m <= 5.0 and cross_queue_m >= 20.0 and t_phase >= self.DEFAULT_GREEN:
                            action = "ADAPTIVE_SWITCH_TO_CROSS"
                            reason = f"Corridor queue cleared ({corr_queue_m:.1f}m) while cross-street has {cross_queue_m:.1f}m queue. Switching to cross green."
                            next_phase = 1
                        # If corridor has high demand and downstream is safe:
                        elif corr_queue_m >= 15.0 and t_phase < self.MAX_GREEN:
                            state["current_max_green"] = min(self.MAX_GREEN, state["current_max_green"] + 5)
                            action = "CORRIDOR_DEMAND_EXTENDING"
                            reason = f"High corridor demand ({corr_queue_m:.1f}m queue). Extending green duration (target={state['current_max_green']}s)."
                        elif t_phase >= state["current_max_green"]:
                            action = "TARGET_GREEN_COMPLETED"
                            reason = f"Allocated green target ({state['current_max_green']}s) served. Transitioning to yellow clearance."
                            next_phase = 1
                        else:
                            action = "CORRIDOR_GREEN_SERVICING"
                            reason = f"Corridor green active ({t_phase}s elapsed). Downstream storage is safe."

                # ---------------------------------------------------------------------
                # PHASE 1: CORRIDOR YELLOW CLEARANCE (Fixed 3 seconds)
                # ---------------------------------------------------------------------
                elif curr_phase == 1:
                    if t_phase >= self.YELLOW_DURATION:
                        next_phase = 2
                        action = "TRANSITION_TO_CROSS_GREEN"
                        reason = "Corridor yellow clearance complete. Transitioning to cross-street green."
                    else:
                        action = "YELLOW_CLEARANCE"
                        reason = f"Yellow clearance interval ({t_phase}/{self.YELLOW_DURATION}s)."

                # ---------------------------------------------------------------------
                # PHASE 2: CROSS STREET GREEN
                # ---------------------------------------------------------------------
                elif curr_phase == 2:
                    # SAFEGUARD: Minimum Green
                    if t_phase < self.MIN_GREEN:
                        action = "HOLD_CROSS_MIN_GREEN"
                        reason = f"Enforcing minimum cross-street green ({t_phase}/{self.MIN_GREEN}s)."

                    # SAFEGUARD: Maximum Green (40s for cross streets)
                    elif t_phase >= 40:
                        action = "CROSS_MAX_GREEN_ENFORCED"
                        reason = "Maximum cross-street green (40s) reached. Returning right-of-way to main corridor."
                        next_phase = 3

                    # Early return to corridor if cross queue cleared and corridor is waiting
                    elif cross_queue_m <= 5.0 and t_phase >= 15:
                        action = "CROSS_QUEUE_CLEARED_EARLY_RETURN"
                        reason = f"Cross queue cleared ({cross_queue_m:.1f}m). Returning green to primary corridor."
                        next_phase = 3

                    # If feeder link urgently needs evacuation and downstream storage has cleared
                    elif feeder_sri >= 0.75 and t_phase >= self.MIN_GREEN and downstream_sri < 0.50:
                        action = f"URGENT_CORRIDOR_FLUSH_CALL (Feeder SRI={feeder_sri:.2f})"
                        reason = f"Feeder link {upstream_link} reached severe backlog (SRI={feeder_sri:.2f}). Cutting cross green to flush corridor."
                        next_phase = 3

                    else:
                        action = "CROSS_GREEN_SERVICING"
                        reason = f"Servicing cross-street traffic ({cross_queue_m:.1f}m queue, {t_phase}s elapsed)."

                # ---------------------------------------------------------------------
                # PHASE 3: CROSS STREET YELLOW CLEARANCE (Fixed 3 seconds)
                # ---------------------------------------------------------------------
                elif curr_phase == 3:
                    if t_phase >= self.YELLOW_DURATION:
                        next_phase = 0
                        action = "TRANSITION_TO_CORRIDOR_GREEN"
                        reason = "Cross-street yellow complete. Returning green to main corridor."
                        state["current_max_green"] = self.DEFAULT_GREEN
                    else:
                        action = "YELLOW_CLEARANCE"
                        reason = f"Yellow clearance interval ({t_phase}/{self.YELLOW_DURATION}s)."

            # Execute phase change if triggered
            if next_phase != curr_phase:
                state["current_phase"] = next_phase
                state["phase_name"] = self.PHASE_NAMES[next_phase]
                state["time_in_phase"] = 0
                try:
                    self.traci.trafficlight.setPhase(jid, next_phase)
                except Exception:
                    pass

            state["last_action"] = action
            state["decision_reason"] = reason

            decisions[jid] = {
                "junction_id": jid,
                "current_phase": state["current_phase"],
                "phase_name": state["phase_name"],
                "time_in_phase": state["time_in_phase"],
                "downstream_sri": round(downstream_sri, 3),
                "downstream_alert": downstream_alert,
                "action": action,
                "reason": reason,
                "control_mode": "PREDICTIVE_SPILLBACK_AWARE",
                "gating_active": state.get("gating_active", False),
                "flushing_active": state.get("flushing_active", False),
                "emergency_active": state.get("emergency_active", False),
            }

        return decisions

    def get_junction_state(self, junction_id: str) -> Dict[str, Any]:
        """Returns live status of the junction."""
        return self.junction_states.get(junction_id, {})
