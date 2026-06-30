"""
Rule-based circuit policy — deterministic, zero external dependencies.

Maps equation feature flags in the 20-dim state vector to an ordered gate
candidate set. Replaces the notebook's perplexity-based rule classification
with quantum domain heuristics derived from the research input type.

Always available as fallback when torch / trained weights are absent.
"""

import numpy as np
from .policy import CircuitPolicy
from .environment import QuantumCircuitEnv


class RuleBasedPolicy(CircuitPolicy):
    """
    Deterministic policy: research keyword features → ordered gate candidates.

    State layout (from QuantumCircuitEnv):
      [2] superposition kw  [3] entanglement kw  [4] phase kw
      [5] rotation kw       [6] chemistry kw      [7] optimisation kw
      [8] cryptography kw   [9] depth_ratio
    """

    # Gate index shortcuts — sourced from environment to stay consistent
    _G   = QuantumCircuitEnv.GATE_IDX
    H    = _G["h"];    CX  = _G["cx"];   CCX = _G["ccx"]
    RY   = _G["ry"];   RZ  = _G["rz"];   CZ  = _G["cz"]
    T    = _G["t"];    S   = _G["s"];    X   = _G["x"]
    MSR  = _G["measure"]

    def select_action(self, state: np.ndarray, **kwargs) -> int:
        """Return the highest-priority candidate gate for this state."""
        return self.candidate_gates(state)[0]

    def candidate_gates(self, state: np.ndarray) -> list:
        """
        Return an ordered list of gate indices appropriate for this state.

        The Gate DQN uses this list to constrain its action search,
        mirroring the rule-based edge classification in the user's notebook.
        """
        if len(state) <= 9:
            return [self.H, self.CX, self.RY, self.MSR]

        depth_ratio = float(state[9])
        if depth_ratio >= 0.8:
            return [self.MSR]

        super_kw  = state[2] > 0.5
        entangle  = state[3] > 0.5
        phase_kw  = state[4] > 0.5
        trig_kw   = state[5] > 0.5
        chem_kw   = state[6] > 0.5
        optim_kw  = state[7] > 0.5
        crypto_kw = state[8] > 0.5

        candidates = []
        if super_kw or crypto_kw:
            candidates += [self.H, self.CX]
        if entangle:
            candidates += [self.CX, self.H, self.CZ]
        if chem_kw:
            candidates += [self.RY, self.RZ, self.CX, self.H]
        if optim_kw:
            candidates += [self.RY, self.CX, self.H]
        if phase_kw:
            candidates += [self.H, self.T, self.S, self.CX]
        if trig_kw:
            candidates += [self.RY, self.RZ]

        if not candidates:
            candidates = [self.H, self.CX, self.RY]

        # Deduplicate preserving priority order
        seen, unique = set(), []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique.append(c)

        if self.MSR not in unique:
            unique.append(self.MSR)

        return unique

    def update(self, batch: list) -> float:
        """No-op — rule policy is deterministic and has no learnable weights."""
        return 0.0
