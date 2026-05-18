"""Tests for quantum/ai_circuit.py — heuristic circuit building and classical suggestions."""
import pytest
from quantum.ai_circuit import (
    build_circuit, CircuitResult,
    _analyze_equations, _generate_qasm, _extend_qasm,
    _check_theoretical, _is_quantum_application,
    suggest_classical_approach, _suggest_classical_heuristic,
)


# ── CircuitResult dataclass ───────────────────────────────────────────────────

def test_circuit_result_defaults():
    r = CircuitResult(qasm="OPENQASM 3.0;")
    assert r.theoretically_correct is False
    assert r.is_quantum_application is False
    assert r.ai_confidence == 0.0
    assert r.algorithm_name == ""
    assert r.interpretation == ""


# ── _analyze_equations ────────────────────────────────────────────────────────

def test_analyze_equations_default_for_empty():
    n, gates = _analyze_equations("")
    assert n == 2
    assert "h" in gates


def test_analyze_equations_counts_variables():
    n, gates = _analyze_equations("a + b + c = d")
    assert n >= 2


def test_analyze_equations_adds_cx_for_multiplication():
    _, gates = _analyze_equations("a * b")
    assert "cx" in gates


def test_analyze_equations_adds_ry_for_trig():
    _, gates = _analyze_equations("sin(θ) + cos(φ)")
    assert "ry" in gates


def test_analyze_equations_caps_qubits_at_10():
    # Many unique single-letter variables.
    long_eq = " ".join(list("abcdefghijklmnop"))
    n, _ = _analyze_equations(long_eq)
    assert n <= 10


# ── _generate_qasm ────────────────────────────────────────────────────────────

def test_generate_qasm_valid_openqasm():
    qasm = _generate_qasm(2, ["h", "cx"])
    assert "OPENQASM 3.0" in qasm
    assert 'include "stdgates.inc"' in qasm
    assert "qubit[2]" in qasm
    assert "measure" in qasm or "c =" in qasm


def test_generate_qasm_includes_hadamard():
    qasm = _generate_qasm(3, ["h"])
    assert qasm.count("h q[") == 3


def test_generate_qasm_includes_cx_when_requested():
    qasm = _generate_qasm(3, ["h", "cx"])
    assert "cx" in qasm


def test_generate_qasm_includes_ry_when_requested():
    qasm = _generate_qasm(2, ["h", "ry"])
    assert "ry(" in qasm


def test_generate_qasm_ccx_requires_3_qubits():
    qasm = _generate_qasm(3, ["h", "ccx"])
    assert "ccx" in qasm


def test_generate_qasm_ccx_skipped_for_2_qubits():
    qasm = _generate_qasm(2, ["h", "ccx"])
    assert "ccx" not in qasm


# ── _extend_qasm ─────────────────────────────────────────────────────────────

def test_extend_qasm_appends_new_layer():
    base = _generate_qasm(2, ["h", "cx"])
    extended = _extend_qasm(base, ["cx"])
    assert extended.count("cx") >= base.count("cx")


def test_extend_qasm_preserves_measurement():
    base = _generate_qasm(2, ["h"])
    extended = _extend_qasm(base, ["ry"])
    assert "c =" in extended or "measure" in extended


def test_extend_qasm_adds_extended_comment():
    base = _generate_qasm(2, ["h"])
    extended = _extend_qasm(base, ["cx"])
    assert "extended" in extended.lower()


# ── _check_theoretical ────────────────────────────────────────────────────────

def test_check_theoretical_valid_circuit():
    qasm = _generate_qasm(2, ["h", "cx"])
    correct, confidence = _check_theoretical(qasm, "")
    assert correct is True
    assert confidence >= 0.9


def test_check_theoretical_missing_openqasm():
    qasm = 'include "stdgates.inc";\nqubit[2] q;\nc = measure q;'
    correct, confidence = _check_theoretical(qasm, "")
    assert correct is False
    assert confidence < 1.0


def test_check_theoretical_missing_measurement():
    qasm = "OPENQASM 3.0;\nqubit[2] q;\nh q[0];"
    correct, confidence = _check_theoretical(qasm, "")
    assert correct is False


def test_check_theoretical_missing_qubit():
    qasm = "OPENQASM 3.0;\nc = measure q;"
    correct, confidence = _check_theoretical(qasm, "")
    assert correct is False


# ── _is_quantum_application ───────────────────────────────────────────────────

def test_is_quantum_application_true_with_app_title():
    qasm = _generate_qasm(2, ["h", "cx"])
    assert _is_quantum_application(qasm, "Quantum Optimization Solver") is True


def test_is_quantum_application_false_no_entanglement():
    qasm = "OPENQASM 3.0;\nqubit[1] q;\nh q[0];\nc = measure q;"
    assert _is_quantum_application(qasm, "Demo") is False


def test_is_quantum_application_false_plain_title():
    qasm = _generate_qasm(2, ["h", "cx"])
    assert _is_quantum_application(qasm, "My Research") is False


# ── build_circuit — heuristic path (no ANTHROPIC_API_KEY) ────────────────────

def test_build_circuit_returns_circuit_result(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = build_circuit("Test Research", "a + b = c")
    assert isinstance(result, CircuitResult)
    assert "OPENQASM" in result.qasm


def test_build_circuit_research_type(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = build_circuit("Quantum Optimization", "f(x) = x²", input_type="research")
    assert "OPENQASM" in result.qasm
    assert "heuristic" in result.notes.lower()


def test_build_circuit_topic_type(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = build_circuit("cryptography", "", input_type="topic")
    assert isinstance(result, CircuitResult)
    assert "OPENQASM" in result.qasm


def test_build_circuit_query_type(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = build_circuit("Build a Bell state", "", input_type="query")
    assert isinstance(result, CircuitResult)


def test_build_circuit_extends_prior_qasm(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    base = build_circuit("Test", "a+b")
    extended = build_circuit("Test", "a+b", prior_qasm=base.qasm)
    assert "extended" in extended.notes.lower()


# ── suggest_classical_approach ────────────────────────────────────────────────

def _assert_suggestion_structure(s: dict):
    assert "reason"         in s
    assert "approach"       in s
    assert "libraries"      in s
    assert "example_sketch" in s
    assert isinstance(s["libraries"], list) and len(s["libraries"]) > 0


def test_suggest_classical_optimization(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = _suggest_classical_heuristic("gradient descent optimization", "minimize f(x)")
    _assert_suggestion_structure(s)
    combined = " ".join(s["libraries"]).lower()
    assert "scipy" in combined or "optuna" in combined


def test_suggest_classical_linear_algebra(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = _suggest_classical_heuristic("matrix eigenvalue decomposition", "Ax = λx")
    _assert_suggestion_structure(s)
    combined = " ".join(s["libraries"]).lower()
    assert "numpy" in combined or "scipy" in combined


def test_suggest_classical_graph(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = _suggest_classical_heuristic("shortest path graph network search", "")
    _assert_suggestion_structure(s)
    combined = " ".join(s["libraries"]).lower()
    assert "networkx" in combined or "heapq" in combined


def test_suggest_classical_simulation(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = _suggest_classical_heuristic("monte carlo simulation probability distribution", "")
    _assert_suggestion_structure(s)
    combined = " ".join(s["libraries"]).lower()
    assert "numpy" in combined or "scipy" in combined


def test_suggest_classical_ml(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = _suggest_classical_heuristic("train classifier predict regression cluster", "")
    _assert_suggestion_structure(s)
    combined = " ".join(s["libraries"]).lower()
    assert "sklearn" in combined or "torch" in combined


def test_suggest_classical_ode(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = _suggest_classical_heuristic("differential equation numerical integration", "dy/dt = f(y)")
    _assert_suggestion_structure(s)
    combined = " ".join(s["libraries"]).lower()
    assert "scipy" in combined


def test_suggest_classical_generic_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = _suggest_classical_heuristic("something entirely unrelated", "")
    _assert_suggestion_structure(s)
    assert "numpy" in [l.lower() for l in s["libraries"]] or "scipy" in [l.lower() for l in s["libraries"]]
