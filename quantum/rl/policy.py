"""Abstract base class for all quantum circuit generation policies."""

from abc import ABC, abstractmethod
import numpy as np


class CircuitPolicy(ABC):
    """
    Abstract base for all circuit generation policies.

    Concrete implementations: RuleBasedPolicy (deterministic),
    DQNPolicy (learned). Both share this interface so DualDQNAgent
    can swap them without code changes.
    """

    @abstractmethod
    def select_action(self, state: np.ndarray, **kwargs) -> int:
        """Select a gate action given the current 20-dim state vector."""
        ...

    @abstractmethod
    def update(self, batch: list) -> float:
        """Update policy from an experience batch. Returns scalar loss (0.0 if stateless)."""
        ...

    def save(self, path: str) -> None:
        """Persist weights to disk. No-op for stateless policies."""

    def load(self, path: str) -> None:
        """Load weights from disk. No-op for stateless policies."""

    @property
    def name(self) -> str:
        return self.__class__.__name__
