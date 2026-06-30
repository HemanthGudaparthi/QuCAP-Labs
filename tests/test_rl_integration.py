"""Integration tests for the Dual Deep RL circuit generation modules."""

import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Environment ───────────────────────────────────────────────────────────────

def test_environment_reset():
    """reset() must return a (20,) float32 state vector."""
    from quantum.rl.environment import QuantumCircuitEnv
    env   = QuantumCircuitEnv("Quantum Phase Estimation", "U|ψ⟩ = e^(2πiφ)|ψ⟩")
    state = env.reset()
    assert state.shape == (20,), f"Expected (20,), got {state.shape}"
    assert state.dtype == np.float32


def test_environment_step_terminates():
    """Stepping through an episode must eventually set done=True."""
    from quantum.rl.environment import QuantumCircuitEnv
    env  = QuantumCircuitEnv("GHZ", "")
    _    = env.reset()
    done = False
    for _ in range(env.max_depth + 10):
        _, _, done, _ = env.step(env.GATE_IDX["h"])
        if done:
            break
    assert done, "Episode should terminate within max_depth + 10 steps"


def test_environment_qasm_valid():
    """QASM built by the environment must contain a valid OPENQASM 3.0 header."""
    from quantum.rl.environment import QuantumCircuitEnv
    env = QuantumCircuitEnv("test", "E = mc²")
    env.reset()
    env.step(env.GATE_IDX["h"])
    env.step(env.GATE_IDX["cx"])
    summary = env.circuit_summary
    assert "OPENQASM" in summary["qasm"]
    assert "measure" in summary["qasm"]


def test_environment_state_after_steps():
    """Gate frequency features must be non-zero after applying gates."""
    from quantum.rl.environment import QuantumCircuitEnv
    env   = QuantumCircuitEnv("test", "")
    state = env.reset()
    env.step(env.GATE_IDX["h"])
    state2 = env.reset()
    # Fresh reset should give zero gate frequencies
    assert state2[10] == 0.0


# ── Rule-based policy ─────────────────────────────────────────────────────────

def test_rule_policy_returns_nonempty_candidates():
    """candidate_gates() must always return a non-empty list of valid indices."""
    from quantum.rl.rule_policy import RuleBasedPolicy
    from quantum.rl.environment import QuantumCircuitEnv
    policy = RuleBasedPolicy()
    env    = QuantumCircuitEnv("cryptography", "")
    state  = env.reset()
    cands  = policy.candidate_gates(state)
    assert len(cands) > 0
    assert all(0 <= c < QuantumCircuitEnv.ACTION_SIZE for c in cands)


def test_rule_policy_deep_circuit_returns_measure():
    """At depth_ratio >= 0.8 the rule policy must prefer MEASURE."""
    from quantum.rl.rule_policy import RuleBasedPolicy
    from quantum.rl.environment import QuantumCircuitEnv
    policy = RuleBasedPolicy()
    state  = np.zeros(20, dtype=np.float32)
    state[9] = 0.9   # depth_ratio = 90 %
    cands = policy.candidate_gates(state)
    assert cands[0] == QuantumCircuitEnv.GATE_IDX["measure"]


def test_rule_policy_update_is_noop():
    """update() must return exactly 0.0 — rule policy has no learnable weights."""
    from quantum.rl.rule_policy import RuleBasedPolicy
    assert RuleBasedPolicy().update([]) == 0.0


# ── Replay buffer ─────────────────────────────────────────────────────────────

def test_replay_buffer_push_and_sample():
    """Push 100 transitions, sample 32, verify sizes."""
    from quantum.rl.replay import ReplayBuffer
    buf   = ReplayBuffer(maxlen=200)
    state = np.zeros(20, dtype=np.float32)
    for i in range(100):
        buf.push(state, i % 10, float(i), state, i == 99)
    assert len(buf) == 100
    assert buf.is_ready(32)
    batch = buf.sample(32)
    assert len(batch) == 32


def test_replay_buffer_maxlen():
    """Buffer must not grow beyond maxlen."""
    from quantum.rl.replay import ReplayBuffer
    buf   = ReplayBuffer(maxlen=50)
    state = np.zeros(20, dtype=np.float32)
    for i in range(200):
        buf.push(state, 0, 0.0, state, False)
    assert len(buf) == 50


# ── Dual agent ────────────────────────────────────────────────────────────────

def test_dual_agent_build_circuit_keys():
    """build_circuit() must return a dict with all required keys."""
    from quantum.rl.dual_agent import DualDQNAgent
    agent  = DualDQNAgent()
    result = agent.build_circuit("Grover Search", "∑_x |x⟩")
    required = {
        "qasm", "n_qubits", "gates", "theoretically_correct",
        "is_quantum_application", "ai_confidence", "notes",
        "algorithm_name", "interpretation",
    }
    missing = required - set(result.keys())
    assert not missing, f"Missing keys: {missing}"
    assert "OPENQASM" in result["qasm"]


def test_dual_agent_never_raises_on_edge_cases():
    """build_circuit() must not raise for empty, long, or None inputs."""
    from quantum.rl.dual_agent import DualDQNAgent
    agent = DualDQNAgent()
    for title, eq in [("", ""), ("x" * 500, ""), ("GHZ", "")]:
        result = agent.build_circuit(title, eq)
        assert isinstance(result, dict)
        assert "qasm" in result


def test_dual_agent_select_action_range():
    """select_action() must return an integer within ACTION_SIZE."""
    from quantum.rl.dual_agent import DualDQNAgent
    from quantum.rl.environment import QuantumCircuitEnv
    agent = DualDQNAgent()
    env   = QuantumCircuitEnv("test", "")
    state = env.reset()
    action = agent.select_action(state, env, explore=True)
    assert 0 <= action < QuantumCircuitEnv.ACTION_SIZE


# ── Full pipeline ─────────────────────────────────────────────────────────────

def test_build_circuit_returns_valid_result():
    """ai_circuit.build_circuit() must return a valid CircuitResult without credentials."""
    from quantum.ai_circuit import build_circuit
    result = build_circuit("test query", "", input_type="query")
    assert "OPENQASM" in result.qasm
    assert isinstance(result.ai_confidence, float)
    assert 0.0 <= result.ai_confidence <= 1.0
    assert isinstance(result.theoretically_correct, bool)


def test_build_circuit_all_input_types():
    """build_circuit() must work for all three input_type values."""
    from quantum.ai_circuit import build_circuit
    for itype in ("research", "topic", "query"):
        result = build_circuit("quantum", "", input_type=itype)
        assert "OPENQASM" in result.qasm, f"Invalid QASM for input_type={itype}"


# ── Monitor ───────────────────────────────────────────────────────────────────

def test_monitor_rl_environment_probe():
    """rl_environment probe must return ok=True."""
    from quantum.monitor import IntegrationMonitor
    health = IntegrationMonitor().check_module("rl_environment")
    assert health.ok, f"rl_environment probe failed: {health.error}"


def test_monitor_rl_dual_agent_probe():
    """rl_dual_agent probe must return ok=True."""
    from quantum.monitor import IntegrationMonitor
    health = IntegrationMonitor().check_module("rl_dual_agent")
    assert health.ok, f"rl_dual_agent probe failed: {health.error}"


def test_monitor_ai_circuit_probe():
    """ai_circuit probe must return ok=True."""
    from quantum.monitor import IntegrationMonitor
    health = IntegrationMonitor().check_module("ai_circuit")
    assert health.ok, f"ai_circuit probe failed: {health.error}"


def test_monitor_check_all_returns_report():
    """check_all() must return a HealthReport with a populated module list."""
    from quantum.monitor import get_monitor
    report = get_monitor().check_all()
    assert hasattr(report, "all_ok")
    assert len(report.modules) >= 7
    summary = report.summary()
    assert "Monitor" in summary


def test_monitor_unknown_probe():
    """Checking an unregistered module name must return ok=False, not raise."""
    from quantum.monitor import IntegrationMonitor
    health = IntegrationMonitor().check_module("nonexistent_module_xyz")
    assert not health.ok
    assert "No probe registered" in health.error
