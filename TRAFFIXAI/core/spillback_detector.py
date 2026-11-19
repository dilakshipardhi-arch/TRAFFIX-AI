"""
TRAFFIX AI - Advanced Spillback Detector Module
Monitors downstream link storage capacity and evaluates the Predictive Spillback Risk Index (SRI)
across inter-intersection links (J1->J2, J2->J3, J3->J2, J2->J1) to prevent gridlock.
"""

from typing import Dict, List, Any


class SpillbackDetector:
    """Monitors inter-intersection storage links and detects imminent spillback."""

    def __init__(self, critical_links: List[str] = None, safety_buffer_m: float = 25.0):
        """
        Args:
            critical_links: List of internal inter-intersection links.
            safety_buffer_m: Safety buffer before the upstream stopline (default: 25.0m).
        """
        self.critical_links = critical_links or ["J1_to_J2", "J2_to_J3", "J3_to_J2", "J2_to_J1"]
        self.safety_buffer = safety_buffer_m

        # Dynamic blockage/incident state per link
        self.blocked_links: Dict[str, bool] = {link: False for link in self.critical_links}

        # Spillback incident tracking
        self.spillback_events_count = {link: 0 for link in self.critical_links}
        self.in_spillback = {link: False for link in self.critical_links}
        self.spillback_duration_s = {link: 0.0 for link in self.critical_links}

    def set_link_blockage(self, link_id: str, is_blocked: bool):
        """Simulates or clears an artificial incident/blockage on an inter-intersection link."""
        if link_id in self.critical_links:
            self.blocked_links[link_id] = is_blocked

    def assess_link_storage(
        self,
        link_id: str,
        current_queue_m: float,
        link_length_m: float,
        predictions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluates remaining physical storage and predictive spillback risk on a link.

        Returns:
            Dict containing remaining storage, SRI, alert level, and actionable recommendation.
        """
        usable_storage_m = max(10.0, link_length_m - self.safety_buffer)

        # If manually blocked by incident simulation:
        is_manually_blocked = self.blocked_links.get(link_id, False)
        if is_manually_blocked:
            current_queue_m = max(current_queue_m, usable_storage_m)

        remaining_storage_m = max(0.0, usable_storage_m - current_queue_m)
        remaining_storage_pct = max(0.0, min(100.0, (remaining_storage_m / usable_storage_m) * 100.0))

        # Lookahead predicted queue lengths
        pred_10s_m = predictions.get("10s", {}).get("predicted_queue_m", current_queue_m)
        pred_20s_m = predictions.get("20s", {}).get("predicted_queue_m", current_queue_m)
        pred_30s_m = predictions.get("30s", {}).get("predicted_queue_m", current_queue_m)

        sri_10s = min(1.0, max(0.0, pred_10s_m / usable_storage_m))
        sri_20s = min(1.0, max(0.0, pred_20s_m / usable_storage_m))
        sri_30s = min(1.0, max(0.0, pred_30s_m / usable_storage_m))

        # Composite Spillback Risk Index (SRI)
        composite_sri = max(sri_10s, 0.92 * sri_20s, 0.85 * sri_30s)
        if is_manually_blocked:
            composite_sri = 1.0

        # Refined Alert Tiers: Low, Medium, High, Critical
        if composite_sri >= 0.85:
            alert_level = "CRITICAL"
            action_recommendation = "STRICT_UPSTREAM_GATING_AND_FLUSH_DOWNSTREAM"
            reason = f"Downstream {link_id} storage critical ({remaining_storage_m:.1f}m remaining). Gating upstream is mandatory to avoid intersection gridlock."
        elif composite_sri >= 0.65:
            alert_level = "HIGH_RISK"
            action_recommendation = "GATE_UPSTREAM_PREPARE_FLUSH"
            reason = f"Downstream {link_id} queue growing rapidly towards upstream stopline. Prioritizing downstream green extension."
        elif composite_sri >= 0.35:
            alert_level = "MEDIUM"
            action_recommendation = "MONITOR_GROWTH_ADAPTIVE_SPLIT"
            reason = f"Downstream {link_id} storage partially occupied ({remaining_storage_pct:.0f}% available). Operating under normal adaptive control."
        else:
            alert_level = "LOW"
            action_recommendation = "NORMAL_PROGRESSION"
            reason = f"Downstream {link_id} ample storage available ({remaining_storage_m:.1f}m free). Free corridor progression."

        # Active physical spillback detection
        is_spillback = current_queue_m >= usable_storage_m
        if is_spillback:
            if not self.in_spillback.get(link_id, False):
                self.spillback_events_count[link_id] = self.spillback_events_count.get(link_id, 0) + 1
                self.in_spillback[link_id] = True
            self.spillback_duration_s[link_id] = self.spillback_duration_s.get(link_id, 0.0) + 1.0
        else:
            self.in_spillback[link_id] = False

        return {
            "link_id": link_id,
            "link_length_m": round(link_length_m, 1),
            "usable_storage_m": round(usable_storage_m, 1),
            "current_queue_m": round(current_queue_m, 1),
            "remaining_storage_m": round(remaining_storage_m, 1),
            "remaining_storage_pct": round(remaining_storage_pct, 1),
            "sri": round(composite_sri, 3),
            "sri_10s": round(sri_10s, 3),
            "sri_20s": round(sri_20s, 3),
            "sri_30s": round(sri_30s, 3),
            "alert_level": alert_level,
            "action_recommendation": action_recommendation,
            "reason": reason,
            "is_active_spillback": is_spillback,
            "is_blocked": is_manually_blocked,
            "total_spillback_events": self.spillback_events_count.get(link_id, 0),
            "total_spillback_duration_s": round(self.spillback_duration_s.get(link_id, 0.0), 1),
        }

    def assess_all_links(
        self,
        queue_estimates: Dict[str, Dict[str, Any]],
        predictions: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Evaluates storage and spillback risk across all critical inter-intersection links."""
        reports = {}
        for link_id in self.critical_links:
            if link_id in queue_estimates and link_id in predictions:
                q_data = queue_estimates[link_id]
                pred_data = predictions[link_id].get("predictions", {})
                reports[link_id] = self.assess_link_storage(
                    link_id=link_id,
                    current_queue_m=q_data["max_queue_length_m"],
                    link_length_m=q_data["edge_length_m"],
                    predictions=pred_data
                )
        return reports
