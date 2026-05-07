from abc import ABC, abstractmethod


class QuantumBackend(ABC):
    """Common interface every quantum hardware backend must implement."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def available(self) -> bool:
        """True when real hardware/credentials are present."""
        ...

    @abstractmethod
    def check_suitability(self, circuit_qasm: str, research_metadata: dict) -> tuple[bool, str]:
        """Return (is_suitable, reason)."""
        ...

    @abstractmethod
    def run(self, circuit_qasm: str, shots: int = 1024) -> dict:
        """Execute the circuit and return raw result counts as a dict."""
        ...

    @abstractmethod
    def reliability_score(self, raw_results: dict) -> float:
        """Return a 0–1 reliability score for the run results."""
        ...
