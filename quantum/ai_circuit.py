"""
AI-driven quantum circuit builder.

Follows the workflow diagram:
  1. build(research)        → produces a QuantumCircuit (QASM string)
  2. check_theoretical()    → validates the circuit conceptually
  3. is_quantum_application → determines if this constitutes a full QApp
  4. extend(circuit, result) → builds a new, improved circuit on prior results
"""

import json
import math
import re
from dataclasses import dataclass, field


@dataclass
class CircuitResult:
    qasm:                   str
    metadata:               dict = field(default_factory=dict)
    theoretically_correct:  bool = False
    is_quantum_application: bool = False
    ai_confidence:          float = 0.0
    notes:                  str = ""


# ─── Public API ───────────────────────────────────────────────────────────────

def build_circuit(title: str, equations: str, prior_qasm: str | None = None) -> CircuitResult:
    """
    Parse equations to infer circuit structure, then generate OpenQASM 3.

    `prior_qasm` is set during the "extend" loop so the AI can build
    upon existing results rather than starting from scratch.
    """
    n_qubits, gates = _analyze_equations(equations)

    if prior_qasm:
        # Extension: append new gate layers to the prior circuit.
        qasm = _extend_qasm(prior_qasm, gates)
        notes = "Extended from prior circuit."
    else:
        qasm = _generate_qasm(n_qubits, gates)
        notes = "New circuit generated from equations."

    correct, confidence = _check_theoretical(qasm, equations)
    is_app              = _is_quantum_application(qasm, title)

    return CircuitResult(
        qasm                   = qasm,
        metadata               = {"n_qubits": n_qubits, "gates": gates},
        theoretically_correct  = correct,
        is_quantum_application = is_app,
        ai_confidence          = confidence,
        notes                  = notes,
    )


def extend_circuit(prior_qasm: str, result_counts: dict,
                   title: str, equations: str) -> CircuitResult:
    """Build upon an existing circuit using the outcome of a prior run."""
    return build_circuit(title, equations, prior_qasm=prior_qasm)


# ─── Internals ────────────────────────────────────────────────────────────────

def _analyze_equations(equations: str) -> tuple[int, list[str]]:
    """
    Heuristic: count unique variables as qubits; map operators to gates.
    Replace this with a real ML/LLM call for production use.
    """
    if not equations:
        return 2, ["h", "cx"]

    variables = set(re.findall(r'\b[a-zA-Z]\b', equations))
    n_qubits  = max(2, min(len(variables), 10))

    gates = ["h"]   # superposition layer always present
    if "∑" in equations or "sum" in equations.lower():
        gates.append("qft")
    if "×" in equations or "*" in equations or "·" in equations:
        gates.append("cx")
    if "²" in equations or "^2" in equations or "**2" in equations:
        gates.append("ccx")
    if "sin" in equations or "cos" in equations:
        gates.append("ry")
    if not any(g in gates for g in ("cx", "ccx")):
        gates.append("cx")

    return n_qubits, gates


def _generate_qasm(n_qubits: int, gates: list[str]) -> str:
    lines = [
        "OPENQASM 3.0;",
        'include "stdgates.inc";',
        f"qubit[{n_qubits}] q;",
        f"bit[{n_qubits}] c;",
    ]

    # Hadamard layer — superposition
    for i in range(n_qubits):
        lines.append(f"h q[{i}];")

    # Entanglement layer
    if "cx" in gates or "ccx" in gates:
        for i in range(n_qubits - 1):
            lines.append(f"cx q[{i}], q[{i+1}];")

    # Rotation layer
    if "ry" in gates:
        angle = round(math.pi / 4, 6)
        for i in range(n_qubits):
            lines.append(f"ry({angle}) q[{i}];")

    if "ccx" in gates and n_qubits >= 3:
        lines.append(f"ccx q[0], q[1], q[2];")

    # Measurement
    lines.append(f"c = measure q;")

    return "\n".join(lines)


def _extend_qasm(prior_qasm: str, new_gates: list[str]) -> str:
    """Append a new gate layer before the measurement in an existing circuit."""
    lines = prior_qasm.strip().splitlines()

    # Strip existing measurement line so we can re-append it last.
    measure_lines = [l for l in lines if l.strip().startswith("c =")]
    body          = [l for l in lines if not l.strip().startswith("c =")]

    n_qubits = 2
    for l in lines:
        m = re.match(r'qubit\[(\d+)\]', l.strip())
        if m:
            n_qubits = int(m.group(1))
            break

    body.append("// --- extended layer ---")
    if "cx" in new_gates:
        for i in range(n_qubits - 1):
            body.append(f"cx q[{i}], q[{i+1}];")
    if "ry" in new_gates:
        angle = round(math.pi / 8, 6)
        for i in range(n_qubits):
            body.append(f"ry({angle}) q[{i}];")

    return "\n".join(body + measure_lines)


def _check_theoretical(qasm: str, equations: str) -> tuple[bool, float]:
    """
    Lightweight theoretical-correctness check.
    Production: replace with a proper formal verifier or LLM call.
    """
    issues = 0
    if "OPENQASM" not in qasm:
        issues += 1
    if "measure" not in qasm and "c =" not in qasm:
        issues += 1
    if "qubit" not in qasm:
        issues += 1

    confidence = max(0.0, 1.0 - issues * 0.35)
    correct    = issues == 0
    return correct, round(confidence, 3)


def _is_quantum_application(qasm: str, title: str) -> bool:
    """
    Decides whether the circuit constitutes a standalone quantum application.
    Heuristic: entanglement + measurement + title implies application intent.
    """
    has_entanglement = "cx" in qasm or "ccx" in qasm or "cz" in qasm
    has_measurement  = "measure" in qasm or "c =" in qasm
    app_keywords     = {"application", "app", "system", "platform", "solver", "optimizer"}
    title_is_app     = any(kw in title.lower() for kw in app_keywords)
    return has_entanglement and has_measurement and title_is_app
