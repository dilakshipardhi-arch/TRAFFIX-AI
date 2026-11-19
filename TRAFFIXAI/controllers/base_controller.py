"""
TRAFFIX AI - Base Controller Interface
Defines the abstract interface for all traffic signal controllers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTrafficController(ABC):
    """Abstract base class for traffic light controllers."""

    def __init__(self, traci_instance, junction_ids: list[str] = None):
        self.traci = traci_instance
        self.junction_ids = junction_ids or ["J1", "J2", "J3"]

    @abstractmethod
    def step(
        self,
        current_time: float,
        queue_estimates: Dict[str, Any],
        queue_predictions: Dict[str, Any],
        spillback_reports: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes one control step.
        Returns a dictionary of junction control decisions and active states.
        """
        pass

    @abstractmethod
    def get_junction_state(self, junction_id: str) -> Dict[str, Any]:
        """Returns the current phase index, phase name, and time in phase for a junction."""
        pass

    @abstractmethod
    def reset(self):
        """Resets controller internal states."""
        pass
