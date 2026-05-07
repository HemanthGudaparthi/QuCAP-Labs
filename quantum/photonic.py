"""
Photonic quantum backend — PLACEHOLDER.

Real photonic hardware (e.g. PsiQuantum, Xanadu PennyLane Bosonic) is not yet
integrated. This stub implements the same QuantumBackend interface so the rest
of the application works end-to-end. Replace the body of each method when
photonic hardware becomes available.
"""

from .base import QuantumBackend

_PLACEHOLDER_NOTE = (
    "Photonic quantum architecture is not yet available. "
    "This is a placeholder implementation."
)


class PhotonicBackend(QuantumBackend):

    name = "photonic"

    @property
    def available(self) -> bool:
        # Set to True and implement real methods when hardware is available.
        return False

    def check_suitability(self, circuit_qasm: str, research_metadata: dict) -> tuple[bool, str]:
        # TODO: Integrate photonic hardware suitability check.
        return False, _PLACEHOLDER_NOTE

    def run(self, circuit_qasm: str, shots: int = 1024) -> dict:
        # TODO: Execute on photonic hardware.
        return {
            "status":  "placeholder",
            "message": _PLACEHOLDER_NOTE,
            "counts":  {},
            "shots":   shots,
            "backend": "photonic_placeholder",
        }

    def reliability_score(self, raw_results: dict) -> float:
        # TODO: Compute reliability from photonic measurement results.
        return 0.0
