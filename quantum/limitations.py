"""
Limitations descriptor.

Builds a plain-English list of what a user will NOT see or experience when
they run a quantum circuit under the current system configuration. Attached
to circuit-build and experiment-creation API responses so researchers know
exactly what they're getting before they interpret results.
"""


def describe_limitations(
    hardware_type: str,
    backend_available: bool,
    input_type: str,
    theoretically_correct: bool | None = None,
    is_quantum_application: bool | None = None,
    ai_confidence: float | None = None,
) -> list[str]:
    """
    Return an ordered list of limitation strings relevant to this execution.

    Args:
        hardware_type:          "electron" | "photonic" | "neutrino"
        backend_available:      True if real hardware credentials are configured
        input_type:             "research" | "topic" | "query"
        theoretically_correct:  from CircuitResult / QuantumCircuit (None = not yet built)
        is_quantum_application: from CircuitResult / QuantumCircuit (None = not yet built)
        ai_confidence:          from CircuitResult / QuantumCircuit (None = not yet built)
    """
    lims: list[str] = []

    # ── Hardware ──────────────────────────────────────────────────────────────
    if hardware_type == "electron":
        if not backend_available:
            lims.append(
                "No IBM Quantum token is configured. The circuit will run on a local "
                "AerSimulator instead of real hardware. Simulation results are noise-free "
                "and do not reflect decoherence, gate errors, or readout errors present "
                "on actual quantum processors."
            )
        else:
            lims.append(
                "Real IBM hardware introduces gate and readout noise. Results are "
                "probabilistic and may differ between runs. Error mitigation is not applied."
            )
    elif hardware_type == "photonic":
        lims.append(
            "The photonic backend is a placeholder — no photonic hardware is connected. "
            "Circuit execution returns a stub response. Real photonic results (boson "
            "sampling, continuous-variable gates) are not available."
        )
    elif hardware_type == "neutrino":
        lims.append(
            "The neutrino backend is a placeholder — neutrino-based quantum computing "
            "has no commercially available hardware. Circuit execution returns a stub "
            "response only."
        )

    # ── Universal quantum execution limits ────────────────────────────────────
    lims.append(
        "No quantum error correction (QEC) is applied. Logical qubit encoding, "
        "syndrome measurement, and fault-tolerant gates are out of scope."
    )
    lims.append(
        "Measurement outcomes are probabilistic samples. Running with more shots "
        "improves statistical accuracy but will not yield a deterministic result."
    )
    lims.append(
        "Circuit depth is not optimised for the target backend. Deep circuits may "
        "accumulate significant noise on real hardware."
    )

    # ── Novelty & research database ───────────────────────────────────────────
    lims.append(
        "Novelty detection uses a hash-based placeholder score, not real semantic "
        "similarity search against the Research Database. Novel and non-novel "
        "classifications may not reflect the true state of the literature."
    )

    # ── Input-type specific ───────────────────────────────────────────────────
    if input_type == "topic":
        lims.append(
            "Topic-based input generates an illustrative circuit for the chosen "
            "domain (e.g. a textbook Shor, Grover, or QAOA instance). The circuit "
            "is NOT parameterised for your specific problem size or dataset."
        )
    elif input_type == "query":
        lims.append(
            "Free-form query circuits are AI-interpreted best-effort approximations. "
            "The circuit may not accurately encode the full intent of your question. "
            "Verify gate-level logic before drawing scientific conclusions."
        )

    # ── Circuit quality flags (only when circuit has been built) ──────────────
    if theoretically_correct is False:
        lims.append(
            "This circuit did NOT pass the theoretical correctness check. "
            "Results should be treated as exploratory only."
        )
    if is_quantum_application is False:
        lims.append(
            "The AI determined this problem does not require quantum hardware. "
            "A classical solution will likely be faster and more accurate — "
            "see the classical_suggestion field."
        )
    if ai_confidence is not None and ai_confidence < 0.70:
        lims.append(
            f"AI confidence in the generated circuit is {ai_confidence:.0%}. "
            "Consider using the /extend endpoint to refine it before running."
        )

    return lims
