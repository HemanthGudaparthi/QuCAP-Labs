"""
RL-based quantum circuit builder — public API.

Primary circuit generation tier (Tier 1) using the Dual Deep RL agent.
Returns CircuitResult matching the existing quantum/ai_circuit.py interface
so the rest of the platform needs no changes to consume RL-generated circuits.

Falls back gracefully when torch is absent or agent weights are unavailable.
"""

import random
from quantum.ai_circuit import CircuitResult

_agent = None


def get_agent():
    """Lazy-initialize the DualDQNAgent singleton and load weights if available."""
    global _agent
    if _agent is None:
        try:
            from quantum.rl.dual_agent import DualDQNAgent
            _agent = DualDQNAgent()
            if _agent.is_trained():
                _agent.load()
                print("[rl_circuit] Loaded trained Dual DQN weights.")
            else:
                print("[rl_circuit] No trained weights found — using untrained agent.")
        except Exception as exc:
            print(f"[rl_circuit] Agent init failed ({exc}); RL unavailable.")
            _agent = None
    return _agent


def build_circuit_rl(title: str, equations: str,
                     prior_qasm: str = None,
                     input_type: str = "research") -> CircuitResult:
    """
    Build a quantum circuit using the Dual DQN agent.

    Returns CircuitResult matching quantum.ai_circuit.build_circuit().
    Raises RuntimeError if the agent is unavailable so the caller can
    fall through to the next tier (Claude or heuristic).
    """
    agent = get_agent()
    if agent is None:
        raise RuntimeError("DualDQNAgent unavailable")

    result = agent.build_circuit(title, equations or "", prior_qasm, input_type)
    return CircuitResult(
        qasm                   = result["qasm"],
        metadata               = {"n_qubits": result["n_qubits"],
                                  "gates":    result["gates"]},
        theoretically_correct  = result["theoretically_correct"],
        is_quantum_application = result["is_quantum_application"],
        ai_confidence          = result["ai_confidence"],
        notes                  = result["notes"],
        algorithm_name         = result.get("algorithm_name", ""),
        interpretation         = result.get("interpretation", ""),
    )


def is_rl_available() -> bool:
    """True when the Dual DQN agent is initialised and functional."""
    return get_agent() is not None


def train_agent(n_episodes: int = 200) -> list:
    """
    Train the Dual DQN agent on a representative set of quantum research inputs.

    Uses a built-in curriculum of 8 diverse research scenarios.
    Returns list of per-episode total rewards.
    """
    from quantum.rl.environment import QuantumCircuitEnv

    DEFAULT_INPUTS = [
        ("Quantum Phase Estimation",
         "U|ψ⟩ = e^(2πiφ)|ψ⟩",                         "research"),
        ("Grover Search Algorithm",
         "∑_x |x⟩",                                      "research"),
        ("QAOA Combinatorial Optimization",
         "min_θ ⟨ψ(θ)|H_C|ψ(θ)⟩",                       "research"),
        ("cryptography",                "",               "topic"),
        ("Variational Quantum Eigensolver",
         "H = ∑_ij h_ij σ_i ⊗ σ_j",                     "research"),
        ("quantum chemistry",           "",               "topic"),
        ("Build a 3-qubit GHZ state",   "",              "query"),
        ("Quantum Fourier Transform",
         "F_N |j⟩ = (1/√N) ∑_k e^(2πijk/N)|k⟩",        "research"),
    ]

    agent = get_agent()
    if agent is None:
        raise RuntimeError("DualDQNAgent unavailable for training")

    def env_factory():
        title, eq, itype = random.choice(DEFAULT_INPUTS)
        return QuantumCircuitEnv(title, eq, itype)

    return agent.train(env_factory, n_episodes=n_episodes)
