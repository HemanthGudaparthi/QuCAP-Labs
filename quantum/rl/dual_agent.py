"""
Dual Deep Q-Network Agent for quantum circuit generation.

Hierarchical control (adapted from user's Rule_based_dual_deep_RL.ipynb):

  Structure DQN (5-dim subgraph → 3 actions) — high-level decisions:
    EXTEND   keep adding gates (delegate to Gate DQN)
    BRANCH   reset qubit line and continue
    FINALIZE emit MEASURE and end the episode
  Mirrors the subgraph-level DQN in the notebook (Cell 5).

  Gate DQN (20-dim state → 10 actions) — low-level gate selection:
    Selects from the candidate set provided by RuleBasedPolicy.
  Mirrors the node-level DQN in the notebook (Cell 4).

  RuleBasedPolicy — provides deterministic candidate gate sets:
    Replaces the notebook's perplexity-based rule classification with
    quantum domain heuristics from equation feature flags.

No single point of failure: if torch is absent or any subcomponent raises,
build_circuit() catches the exception and returns a rule-based fallback.
"""

import math
import re
import numpy as np

from .rule_policy import RuleBasedPolicy
from .dqn_policy import DQNPolicy
from .environment import QuantumCircuitEnv
from .replay import ReplayBuffer
from .model_store import ModelStore


class DualDQNAgent:
    """Hierarchical Dual DQN for quantum circuit generation."""

    EXTEND   = 0
    BRANCH   = 1
    FINALIZE = 2

    def __init__(
        self,
        model_dir:     str   = "quantum/rl/models",
        gate_lr:       float = 0.001,
        structure_lr:  float = 0.001,
        gamma:         float = 0.99,
        epsilon:       float = 1.0,
        epsilon_decay: float = 0.995,
        epsilon_min:   float = 0.1,
        batch_size:    int   = 64,
        replay_maxlen: int   = 10_000,
    ):
        self.model_store = ModelStore(model_dir)
        self.batch_size  = batch_size

        self.rule_policy = RuleBasedPolicy()

        self.gate_policy = DQNPolicy(
            state_size    = QuantumCircuitEnv.STATE_SIZE,
            action_size   = QuantumCircuitEnv.ACTION_SIZE,
            lr            = gate_lr,
            gamma         = gamma,
            epsilon       = epsilon,
            epsilon_decay = epsilon_decay,
            epsilon_min   = epsilon_min,
        )
        self.structure_policy = DQNPolicy(
            state_size       = 5,
            action_size      = 3,
            lr               = structure_lr,
            gamma            = gamma,
            epsilon          = epsilon,
            epsilon_decay    = epsilon_decay,
            epsilon_min      = epsilon_min,
            is_structure_net = True,
        )
        self.gate_replay      = ReplayBuffer(replay_maxlen)
        self.structure_replay = ReplayBuffer(replay_maxlen)

    # ── Action selection ──────────────────────────────────────────────────

    def select_action(self, state: np.ndarray,
                      env: QuantumCircuitEnv = None,
                      explore: bool = True) -> int:
        """
        Hierarchical gate selection:
          1. Structure DQN reads 5-dim subgraph embedding → EXTEND/BRANCH/FINALIZE.
          2. FINALIZE → return MEASURE index immediately.
          3. Otherwise Gate DQN selects from RuleBasedPolicy candidate set.
        """
        subgraph = self._subgraph_embedding(env, state)
        eps_s    = self.structure_policy.epsilon if explore else 0.0
        struct   = self.structure_policy.select_action(subgraph, epsilon=eps_s)

        if struct == self.FINALIZE:
            return QuantumCircuitEnv.GATE_IDX["measure"]

        candidates  = self.rule_policy.candidate_gates(state)
        measure_idx = QuantumCircuitEnv.GATE_IDX["measure"]
        depth_ratio = float(state[9]) if len(state) > 9 else 0.0

        # Suppress premature measurement during active circuit building
        if depth_ratio < 0.6:
            candidates = [c for c in candidates if c != measure_idx]
        if not candidates:
            candidates = list(range(QuantumCircuitEnv.ACTION_SIZE - 1))

        eps_g = self.gate_policy.epsilon if explore else 0.0
        return self.gate_policy.select_action(state, candidates=candidates, epsilon=eps_g)

    # ── Training ──────────────────────────────────────────────────────────

    def train_episode(self, env: QuantumCircuitEnv, max_steps: int = 50) -> dict:
        """
        Run one training episode.

        Both DQNs accumulate experiences and update every step once their
        replay buffers are ready. Returns a metrics dict.
        """
        state          = env.reset()
        total_reward   = 0.0
        loss_gate      = 0.0
        loss_structure = 0.0
        steps          = 0
        prev_subgraph  = self._subgraph_embedding(env, state)

        for _ in range(max_steps):
            action                        = self.select_action(state, env, explore=True)
            next_state, reward, done, _   = env.step(action)
            next_subgraph                 = self._subgraph_embedding(env, next_state)

            # Gate-level replay
            self.gate_replay.push(state, action, reward, next_state, done)

            # Structure-level replay — structure agent shadows gate decisions
            struct_action = self.structure_policy.select_action(
                prev_subgraph, epsilon=self.structure_policy.epsilon)
            self.structure_replay.push(
                prev_subgraph, struct_action, reward, next_subgraph, done)

            if self.gate_replay.is_ready(self.batch_size):
                loss_gate += self.gate_policy.update(
                    self.gate_replay.sample(self.batch_size))

            if self.structure_replay.is_ready(self.batch_size):
                loss_structure += self.structure_policy.update(
                    self.structure_replay.sample(self.batch_size))

            total_reward  += reward
            prev_subgraph  = next_subgraph
            state          = next_state
            steps         += 1
            if done:
                break

        return {
            "total_reward":   total_reward,
            "loss_gate":      loss_gate / max(steps, 1),
            "loss_structure": loss_structure / max(steps, 1),
            "steps":          steps,
            "qasm":           env.circuit_summary["qasm"],
        }

    def train(self, env_factory, n_episodes: int = 200,
              save_interval: int = 50) -> list:
        """
        Full training loop.

        env_factory() should return a fresh QuantumCircuitEnv each call.
        Returns list of per-episode total rewards.
        """
        rewards = []
        for ep in range(n_episodes):
            env     = env_factory()
            metrics = self.train_episode(env)
            rewards.append(metrics["total_reward"])
            if (ep + 1) % 10 == 0:
                print(
                    f"[DualDQN] ep={ep+1}/{n_episodes}  "
                    f"reward={metrics['total_reward']:.2f}  "
                    f"loss_gate={metrics['loss_gate']:.4f}  "
                    f"eps={self.gate_policy.epsilon:.3f}"
                )
            if (ep + 1) % save_interval == 0:
                self.save()
        self.save()
        return rewards

    # ── Inference ─────────────────────────────────────────────────────────

    def build_circuit(self, title: str, equations: str,
                      prior_qasm: str = None,
                      input_type: str = "research") -> dict:
        """
        Build a quantum circuit via greedy inference (exploration disabled).

        Always returns a valid dict — never raises. Any exception triggers
        the rule-based fallback so the platform continues operating.
        """
        try:
            env   = QuantumCircuitEnv(title, equations or "", input_type)
            state = env.reset()

            for _ in range(env.max_depth + 5):
                action            = self.select_action(state, env, explore=False)
                state, _, done, _ = env.step(action)
                if done:
                    break

            summary = env.circuit_summary
            qasm    = summary["qasm"] or self._fallback_qasm(title, equations or "")
            gates   = summary["gates"]

            has_entanglement = any(g in ("cx", "ccx", "cz") for g in gates)
            has_h            = "h" in gates
            is_quantum       = has_entanglement and has_h
            is_correct       = bool(gates) and "OPENQASM" in qasm
            confidence       = (0.80 if (is_correct and is_quantum) else
                                0.55 if is_correct else 0.30)

            if prior_qasm and gates:
                qasm = self._extend_qasm(prior_qasm, gates, env._n_qubits)

            return {
                "qasm":                   qasm,
                "n_qubits":               env._n_qubits,
                "gates":                  gates,
                "theoretically_correct":  is_correct,
                "is_quantum_application": is_quantum,
                "ai_confidence":          confidence,
                "notes": (
                    f"Dual DQN generated — {len(gates)} gates, "
                    f"{env._n_qubits} qubits, input_type={input_type}"
                ),
                "algorithm_name":  self._infer_algorithm(title, input_type),
                "interpretation":  f"RL circuit for: {title[:80]}",
            }
        except Exception as exc:
            return self._fallback_result(title, equations or "", str(exc))

    # ── Subgraph embedding (5-dim) ────────────────────────────────────────

    def _subgraph_embedding(self, env: QuantumCircuitEnv,
                             state: np.ndarray) -> np.ndarray:
        """
        5-dim circuit graph embedding (mirrors notebook Cell 5 subgraph_to_vec):
          [0] depth / max_depth         — circuit progress
          [1] unique_gate_count / 9     — gate diversity
          [2] entangle_count / depth    — entanglement density
          [3] (has_h + has_cx) / 2      — entanglement readiness
          [4] has_measure               — measurement done flag
        """
        if env is None:
            return np.zeros(5, dtype=np.float32)

        gates       = env._gates_applied
        depth       = len(gates)
        unique      = len(set(gates)) if gates else 0
        entangle    = sum(1 for g in gates if g in ("cx", "ccx", "cz"))
        has_h       = float("h" in gates)
        has_cx      = float(any(g in ("cx", "ccx", "cz") for g in gates))
        has_measure = float("measure" in gates)

        return np.array([
            depth / env.max_depth,
            unique / 9.0,
            entangle / max(depth, 1),
            (has_h + has_cx) / 2.0,
            has_measure,
        ], dtype=np.float32)

    # ── Persistence ───────────────────────────────────────────────────────

    def save(self) -> None:
        """Save both policy weights to model_dir."""
        self.model_store.ensure_dir()
        self.gate_policy.save(self.model_store.gate_model_path())
        self.structure_policy.save(self.model_store.structure_model_path())

    def load(self) -> None:
        """Load both policy weights from model_dir."""
        self.gate_policy.load(self.model_store.gate_model_path())
        self.structure_policy.load(self.model_store.structure_model_path())

    def is_trained(self) -> bool:
        """True when saved model weight files exist on disk."""
        return self.model_store.exists()

    # ── Private helpers ───────────────────────────────────────────────────

    def _fallback_result(self, title: str, equations: str, error: str) -> dict:
        """Safe minimal circuit dict when RL inference fails."""
        return {
            "qasm":                   self._fallback_qasm(title, equations),
            "n_qubits":               2,
            "gates":                  ["h", "cx"],
            "theoretically_correct":  True,
            "is_quantum_application": False,
            "ai_confidence":          0.30,
            "notes":                  f"Rule-based fallback (RL error: {error[:120]})",
            "algorithm_name":         "",
            "interpretation":         "",
        }

    def _fallback_qasm(self, title: str, equations: str) -> str:
        """Minimal valid QASM based on equation variable count."""
        vars_ = set(re.findall(r'\b[a-zA-Z]\b', equations))
        n     = max(2, min(len(vars_), 6))
        lines = (
            ["OPENQASM 3.0;", 'include "stdgates.inc";',
             f"qubit[{n}] q;", f"bit[{n}] c;"]
            + [f"h q[{i}];"              for i in range(n)]
            + [f"cx q[{i}], q[{i+1}];"  for i in range(n - 1)]
            + ["c = measure q;"]
        )
        return "\n".join(lines)

    def _extend_qasm(self, prior_qasm: str, new_gates: list,
                     n_qubits: int) -> str:
        """Append RL-generated gates as an extension layer before measurement."""
        lines        = prior_qasm.strip().splitlines()
        measure_line = [l for l in lines if l.strip().startswith("c =")]
        body         = [l for l in lines if not l.strip().startswith("c =")]
        body.append("// --- RL extension layer ---")
        for gate in new_gates[-3:]:
            if gate == "cx" and n_qubits >= 2:
                body.append("cx q[0], q[1];")
            elif gate == "ry":
                body.append(f"ry({round(math.pi/8, 6)}) q[0];")
            elif gate == "h":
                body.append("h q[0];")
        return "\n".join(body + measure_line)

    def _infer_algorithm(self, title: str, input_type: str) -> str:
        """Map topic domain keywords to canonical algorithm names."""
        if input_type != "topic":
            return ""
        t = title.lower()
        if any(k in t for k in ("cryptograph", "qkd", "bb84", "key")):
            return "BB84 Quantum Key Distribution"
        if any(k in t for k in ("shor", "factor")):
            return "Shor's Algorithm"
        if any(k in t for k in ("grover", "search", "amplitude")):
            return "Grover's Search"
        if any(k in t for k in ("vqe", "chemistry", "variational", "eigensolver")):
            return "Variational Quantum Eigensolver (VQE)"
        if any(k in t for k in ("qaoa", "optimiz")):
            return "QAOA"
        if any(k in t for k in ("fourier", "qft")):
            return "Quantum Fourier Transform"
        return "Quantum Circuit"
