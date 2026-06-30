"""
Quantum circuit construction environment for RL training.

State vector (20-dim float32):
  [0]    equation variable count / 10
  [1-8]  keyword flags: quantum/qubit, sum/superposition, entanglement/cx,
         phase/², sin/cos/rotation, hamiltonian/vqe, optimization/qaoa, cryptography/qkd
  [9]    current depth / max_depth
  [10-18] per-gate frequency (h,cx,ccx,ry,rz,cz,t,s,x) normalized by depth
  [19]   n_qubits / 10

Replaces notebook's GPT-2 perplexity-based state with quantum circuit features.
Reward replaces perplexity comparison rewards with circuit quality signals.
"""

import math
import re
import numpy as np


class QuantumCircuitEnv:
    """OpenQASM 3.0 circuit construction RL environment."""

    GATES     = ["h", "cx", "ccx", "ry", "rz", "cz", "t", "s", "x", "measure"]
    GATE_IDX  = {g: i for i, g in enumerate(GATES)}
    ACTION_SIZE = len(GATES)   # 10
    STATE_SIZE  = 20
    MIN_DEPTH   = 3            # minimum gates before MEASURE is allowed

    def __init__(self, title: str, equations: str,
                 input_type: str = "research", max_depth: int = 20):
        self.title      = title
        self.equations  = equations or ""
        self.input_type = input_type
        self.max_depth  = max_depth

        self._n_qubits:          int   = 2
        self._gates_applied:     list  = []
        self._done:              bool  = False
        self._research_features: np.ndarray = np.zeros(9, dtype=np.float32)

        self.reset()

    # ── Public interface ──────────────────────────────────────────────────

    def reset(self) -> np.ndarray:
        """Reset episode state and return initial state vector."""
        self._n_qubits         = self._detect_n_qubits(self.title, self.equations)
        self._gates_applied    = []
        self._done             = False
        self._research_features = self._encode_research_features()
        return self._encode_state()

    def step(self, action: int):
        """
        Apply gate action. Returns (next_state, reward, done, info).

        action index maps to GATES list. Out-of-range indices are wrapped.
        """
        if self._done:
            return self._encode_state(), 0.0, True, {}

        gate   = self.GATES[action % self.ACTION_SIZE]
        reward = 0.0

        if gate == "measure":
            self._done = True
            if len(self._gates_applied) < self.MIN_DEPTH:
                reward = -2.0   # penalise premature termination
            else:
                _, reward = self._finalize()
        else:
            reward = self._step_reward(gate)
            self._gates_applied.append(gate)
            if len(self._gates_applied) >= self.max_depth:
                self._done = True
                _, final = self._finalize()
                reward   += final

        return self._encode_state(), reward, self._done, {
            "gate": gate, "n_qubits": self._n_qubits,
        }

    @property
    def circuit_summary(self) -> dict:
        return {
            "gates":    list(self._gates_applied),
            "qasm":     self._build_qasm() if self._gates_applied else "",
            "depth":    len(self._gates_applied),
            "n_qubits": self._n_qubits,
        }

    # ── Reward shaping ────────────────────────────────────────────────────

    def _step_reward(self, gate: str) -> float:
        """Per-step reward — encourages entanglement and diversity."""
        reward = 0.5                          # base: any gate is progress
        if gate in ("cx", "ccx", "cz"):
            reward += 1.0                     # entangling gates valued highly
        if gate == "h":
            reward += 0.3                     # superposition setup
        if gate in ("ry", "rz"):
            reward += 0.2                     # rotation — variational utility
        if self._gates_applied and self._gates_applied[-1] == gate:
            reward -= 0.5                     # penalise redundant repetition
        return reward

    def _finalize(self):
        """Build QASM string and compute terminal reward."""
        qasm  = self._build_qasm()
        gates = self._gates_applied
        depth = len(gates)

        reward = 0.0
        if gates:
            reward += 3.0
        has_entanglement = any(g in ("cx", "ccx", "cz") for g in gates)
        has_h            = "h" in gates
        if has_entanglement:
            reward += 3.0
        if has_h and has_entanglement:
            reward += 2.0                     # canonical superposition → entanglement
        if 3 <= depth <= 15:
            reward += 2.0                     # good circuit depth
        elif depth > 15:
            reward -= 1.0                     # excessively deep
        if any(g in ("ry", "rz") for g in gates):
            reward += 1.0                     # variational capability
        if 2 <= self._n_qubits <= 8:
            reward += 1.0                     # reasonable qubit count

        return qasm, reward

    # ── QASM builder ─────────────────────────────────────────────────────

    def _build_qasm(self) -> str:
        """Assemble a valid OPENQASM 3.0 string from the applied gate sequence."""
        n     = self._n_qubits
        lines = [
            "OPENQASM 3.0;",
            'include "stdgates.inc";',
            f"qubit[{n}] q;",
            f"bit[{n}] c;",
        ]
        for gate in self._gates_applied:
            if gate == "h":
                lines += [f"h q[{i}];" for i in range(n)]
            elif gate == "cx":
                lines += [f"cx q[{i}], q[{i+1}];" for i in range(n - 1)]
            elif gate == "ccx" and n >= 3:
                lines.append("ccx q[0], q[1], q[2];")
            elif gate == "ry":
                angle = round(math.pi / 4, 6)
                lines += [f"ry({angle}) q[{i}];" for i in range(n)]
            elif gate == "rz":
                angle = round(math.pi / 8, 6)
                lines += [f"rz({angle}) q[{i}];" for i in range(n)]
            elif gate == "cz" and n >= 2:
                lines.append("cz q[0], q[1];")
            elif gate == "t":
                lines += [f"t q[{i}];" for i in range(n)]
            elif gate == "s":
                lines += [f"s q[{i}];" for i in range(n)]
            elif gate == "x":
                lines += [f"x q[{i}];" for i in range(n)]
        lines.append("c = measure q;")
        return "\n".join(lines)

    # ── State encoding ────────────────────────────────────────────────────

    def _encode_research_features(self) -> np.ndarray:
        """9-dim static feature vector derived from title + equations."""
        text  = f"{self.title} {self.equations}".lower()
        feats = np.zeros(9, dtype=np.float32)

        vars_    = set(re.findall(r'\b[a-zA-Z]\b', self.equations))
        feats[0] = min(len(vars_) / 10.0, 1.0)

        kw_groups = [
            ["quantum", "qubit", "gate", "circuit"],           # [1] general QC
            ["sum", "∑", "superposition", "hadamard"],         # [2] superposition
            ["entanglement", "cx", "cnot", "bell"],            # [3] entanglement
            ["²", "^2", "phase", "estimation"],                # [4] phase
            ["sin", "cos", "rotation", "angle"],               # [5] rotation
            ["hamiltonian", "chemistry", "vqe", "variational"],# [6] VQE/chem
            ["optimization", "qaoa", "grover", "search"],      # [7] optim/search
            ["cryptography", "key", "bb84", "qkd"],            # [8] QKD
        ]
        for i, kwlist in enumerate(kw_groups):
            feats[1 + i] = float(any(kw in text for kw in kwlist))
        return feats

    def _encode_state(self) -> np.ndarray:
        """Encode full 20-dim state: research features + circuit state."""
        state = np.zeros(self.STATE_SIZE, dtype=np.float32)
        state[:9] = self._research_features

        depth    = len(self._gates_applied)
        state[9] = depth / self.max_depth

        # Gate frequencies [10-18] — one slot per non-measure gate
        if depth > 0:
            for gate in self._gates_applied:
                idx = self.GATE_IDX.get(gate, -1)
                if 0 <= idx < 9:          # exclude measure (idx 9)
                    state[10 + idx] += 1
            state[10:19] /= depth

        state[19] = self._n_qubits / 10.0
        return state

    def _detect_n_qubits(self, title: str, equations: str) -> int:
        """Infer qubit count from single-letter variable count, capped 2-10."""
        if not equations:
            return 2
        vars_ = set(re.findall(r'\b[a-zA-Z]\b', equations))
        return max(2, min(len(vars_), 10))
