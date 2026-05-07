"""
Neutrino-based quantum backend — PLACEHOLDER.

Neutrino quantum computing is an emerging research area with no commercially
available hardware at this time. This stub satisfies the QuantumBackend
interface. Replace internals when hardware/simulation becomes available.
"""

from .base import QuantumBackend

_PLACEHOLDER_NOTE = (
    "Neutrino quantum architecture is not yet available. "
    "This is a placeholder implementation."
)


class NeutrinoBackend(QuantumBackend):

    name = "neutrino"

    @property
    def available(self) -> bool:
        # Set to True and implement real methods when hardware is available.
        return False

    def check_suitability(self, circuit_qasm: str, research_metadata: dict) -> tuple[bool, str]:
        # TODO: Integrate neutrino hardware suitability check.
        return False, _PLACEHOLDER_NOTE

    def run(self, circuit_qasm: str, shots: int = 1024) -> dict:
        # TODO: Execute on neutrino hardware.
        return {
            "status":  "placeholder",
            "message": _PLACEHOLDER_NOTE,
            "counts":  {},
            "shots":   shots,
            "backend": "neutrino_placeholder",
        }

    def reliability_score(self, raw_results: dict) -> float:
        # TODO: Compute reliability from neutrino measurement results.
        return 0.0
