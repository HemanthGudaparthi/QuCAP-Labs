"""
AI-driven quantum circuit builder.

Uses Claude (claude-opus-4-7) when ANTHROPIC_API_KEY is set.
Falls back to heuristic generation when the key is absent or the call fails.

Follows the workflow diagram:
  1. build(research)        → produces a QuantumCircuit (QASM string)
  2. check_theoretical()    → validates the circuit conceptually
  3. is_quantum_application → determines if this constitutes a full QApp
  4. extend(circuit, result) → builds a new, improved circuit on prior results
"""

import json
import math
import os
import re
from dataclasses import dataclass, field

try:
    import anthropic as _anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

_MODEL = "claude-opus-4-7"

_SYSTEM_PROMPT = """\
You are a quantum computing expert. Given a research title and equations, \
generate a valid OpenQASM 3.0 quantum circuit, then assess it.

Respond with ONLY a JSON object — no prose, no markdown fences:
{
  "qasm": "<full OpenQASM 3.0 circuit string>",
  "theoretically_correct": true|false,
  "is_quantum_application": true|false,
  "ai_confidence": <float 0.0-1.0>,
  "notes": "<brief explanation>",
  "n_qubits": <int>,
  "gates": [<gate name strings>]
}

Rules:
- Use OPENQASM 3.0; include "stdgates.inc";
- Include qubit and bit declarations, gate operations, and a measurement.
- theoretically_correct: true only if the circuit is well-formed and the \
  gates are appropriate for the equations.
- is_quantum_application: true if the circuit represents a meaningful \
  standalone quantum application (not just a demo).
- ai_confidence: your confidence in the generated circuit (0.0–1.0).
"""


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
    Build a quantum circuit for the given research title and equations.
    Uses Claude when ANTHROPIC_API_KEY is set; falls back to heuristics otherwise.
    `prior_qasm` triggers extension mode (build upon existing results).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key and _HAS_ANTHROPIC:
        try:
            return _build_with_claude(title, equations, prior_qasm, api_key)
        except Exception as exc:
            print(f"[ai_circuit] Claude call failed ({exc}); falling back to heuristics.")

    return _build_heuristic(title, equations, prior_qasm)


def extend_circuit(prior_qasm: str, result_counts: dict,
                   title: str, equations: str) -> CircuitResult:
    """Build upon an existing circuit using the outcome of a prior run."""
    return build_circuit(title, equations, prior_qasm=prior_qasm)


# ─── Claude backend ───────────────────────────────────────────────────────────

def _build_with_claude(title: str, equations: str,
                       prior_qasm: str | None, api_key: str) -> CircuitResult:
    client = _anthropic.Anthropic(api_key=api_key)

    user_content = f"Research title: {title}\n\nEquations:\n{equations or '(none provided)'}"
    if prior_qasm:
        user_content += f"\n\nExtend this existing circuit (add layers before the final measurement):\n{prior_qasm}"

    with client.messages.stream(
        model=_MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        message = stream.get_final_message()

    raw = ""
    for block in message.content:
        if block.type == "text":
            raw = block.text.strip()
            break

    # Strip accidental markdown fences if Claude added them.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    data = json.loads(raw)

    return CircuitResult(
        qasm                   = data["qasm"],
        metadata               = {"n_qubits": data.get("n_qubits", 2),
                                  "gates":    data.get("gates", [])},
        theoretically_correct  = bool(data.get("theoretically_correct", False)),
        is_quantum_application = bool(data.get("is_quantum_application", False)),
        ai_confidence          = float(data.get("ai_confidence", 0.0)),
        notes                  = data.get("notes", ""),
    )


# ─── Heuristic fallback ───────────────────────────────────────────────────────

def _build_heuristic(title: str, equations: str,
                     prior_qasm: str | None) -> CircuitResult:
    n_qubits, gates = _analyze_equations(equations)

    if prior_qasm:
        qasm  = _extend_qasm(prior_qasm, gates)
        notes = "Extended from prior circuit (heuristic fallback)."
    else:
        qasm  = _generate_qasm(n_qubits, gates)
        notes = "New circuit generated from equations (heuristic fallback)."

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


def _analyze_equations(equations: str) -> tuple[int, list[str]]:
    if not equations:
        return 2, ["h", "cx"]

    variables = set(re.findall(r'\b[a-zA-Z]\b', equations))
    n_qubits  = max(2, min(len(variables), 10))

    gates = ["h"]
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

    for i in range(n_qubits):
        lines.append(f"h q[{i}];")

    if "cx" in gates or "ccx" in gates:
        for i in range(n_qubits - 1):
            lines.append(f"cx q[{i}], q[{i+1}];")

    if "ry" in gates:
        angle = round(math.pi / 4, 6)
        for i in range(n_qubits):
            lines.append(f"ry({angle}) q[{i}];")

    if "ccx" in gates and n_qubits >= 3:
        lines.append("ccx q[0], q[1], q[2];")

    lines.append("c = measure q;")
    return "\n".join(lines)


def _extend_qasm(prior_qasm: str, new_gates: list[str]) -> str:
    lines         = prior_qasm.strip().splitlines()
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
    has_entanglement = "cx" in qasm or "ccx" in qasm or "cz" in qasm
    has_measurement  = "measure" in qasm or "c =" in qasm
    app_keywords     = {"application", "app", "system", "platform", "solver", "optimizer"}
    title_is_app     = any(kw in title.lower() for kw in app_keywords)
    return has_entanglement and has_measurement and title_is_app
