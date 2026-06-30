"""
Deep Q-Network policy for quantum circuit generation.

Two network architectures (from user's notebook):
  GateDQNNetwork      — 20-dim circuit state  → 10 gate Q-values   (Cell 4 DQN)
  StructureDQNNetwork — 5-dim subgraph embed  → 3 structure Q-values (Cell 5 DQN)

DQNPolicy wraps both via is_structure_net flag and provides epsilon-greedy
action selection with experience-replay training. Degrades gracefully when
torch is unavailable — falls back to random selection from candidate set.
"""

import os
import random
import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

from .policy import CircuitPolicy


# ── Neural network definitions ────────────────────────────────────────────────

if _HAS_TORCH:
    class GateDQNNetwork(nn.Module):
        """
        Gate-level DQN: maps 20-dim circuit state → per-gate Q-values.
        Architecture mirrors the DQNetwork in the user's notebook (Cell 4).
        """

        def __init__(self, state_size: int = 20, action_size: int = 10,
                     hidden: int = 64):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(state_size, hidden),
                nn.ReLU(),
                nn.Linear(hidden, hidden),
                nn.ReLU(),
                nn.Linear(hidden, action_size),
            )

        def forward(self, x):
            return self.net(x)

    class StructureDQNNetwork(nn.Module):
        """
        Structure-level DQN: maps 5-dim subgraph embedding → structure Q-values.
        Actions: 0=EXTEND, 1=BRANCH, 2=FINALIZE.
        Architecture mirrors the subgraph DQN in the user's notebook (Cell 5).
        """

        def __init__(self, subgraph_dim: int = 5, action_size: int = 3,
                     hidden: int = 64):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(subgraph_dim, hidden),
                nn.ReLU(),
                nn.Linear(hidden, hidden),
                nn.ReLU(),
                nn.Linear(hidden, action_size),
            )

        def forward(self, x):
            return self.net(x)

else:
    class GateDQNNetwork:           # type: ignore[no-redef]
        """Stub used when torch is not installed."""
        def __init__(self, *a, **kw): pass
        def __call__(self, x): return x

    class StructureDQNNetwork:      # type: ignore[no-redef]
        """Stub used when torch is not installed."""
        def __init__(self, *a, **kw): pass
        def __call__(self, x): return x


# ── Policy wrapper ────────────────────────────────────────────────────────────

class DQNPolicy(CircuitPolicy):
    """
    Deep Q-Network policy with epsilon-greedy exploration and target network.

    Wraps either GateDQNNetwork or StructureDQNNetwork depending on
    is_structure_net. Provides the same CircuitPolicy interface either way,
    degrading to random selection when torch is unavailable.
    """

    def __init__(
        self,
        state_size:      int   = 20,
        action_size:     int   = 10,
        hidden:          int   = 64,
        lr:              float = 0.001,
        gamma:           float = 0.99,
        epsilon:         float = 1.0,
        epsilon_decay:   float = 0.995,
        epsilon_min:     float = 0.1,
        is_structure_net: bool = False,
    ):
        self.state_size     = state_size
        self.action_size    = action_size
        self.gamma          = gamma
        self.epsilon        = epsilon
        self.epsilon_decay  = epsilon_decay
        self.epsilon_min    = epsilon_min
        self._torch_ok      = _HAS_TORCH
        self._update_count  = 0

        if self._torch_ok:
            if is_structure_net:
                self._net        = StructureDQNNetwork(state_size, action_size, hidden)
                self._target_net = StructureDQNNetwork(state_size, action_size, hidden)
            else:
                self._net        = GateDQNNetwork(state_size, action_size, hidden)
                self._target_net = GateDQNNetwork(state_size, action_size, hidden)

            self._target_net.load_state_dict(self._net.state_dict())
            self._optimizer = optim.Adam(self._net.parameters(), lr=lr)
            self._loss_fn   = nn.MSELoss()

    # ── Action selection ──────────────────────────────────────────────────

    def select_action(self, state: np.ndarray,
                      candidates: list = None,
                      epsilon: float = None,
                      **kwargs) -> int:
        """
        Epsilon-greedy gate selection, optionally restricted to a candidate list.

        candidates — if provided, only these action indices are eligible.
        epsilon    — override for exploration rate (uses self.epsilon if None).
        """
        eps   = epsilon if epsilon is not None else self.epsilon
        valid = candidates if candidates else list(range(self.action_size))

        if not self._torch_ok or random.random() < eps:
            return random.choice(valid)

        with torch.no_grad():
            t = torch.tensor(state, dtype=torch.float32).unsqueeze(0)
            q = self._net(t).squeeze(0).numpy()

        return max(valid, key=lambda a: float(q[a]))

    # ── Training ──────────────────────────────────────────────────────────

    def update(self, batch: list) -> float:
        """
        Standard DQN update: minimise MSE(Q(s,a), r + γ·max_a' Q_target(s',a')).
        Decays epsilon and periodically syncs the target network.
        Returns scalar loss (0.0 when torch unavailable or batch is empty).
        """
        if not self._torch_ok or not batch:
            return 0.0

        states      = torch.tensor(np.array([b[0] for b in batch]), dtype=torch.float32)
        actions     = torch.tensor([b[1] for b in batch],           dtype=torch.long)
        rewards     = torch.tensor([b[2] for b in batch],           dtype=torch.float32)
        next_states = torch.tensor(np.array([b[3] for b in batch]), dtype=torch.float32)
        dones       = torch.tensor([b[4] for b in batch],           dtype=torch.float32)

        q_values = self._net(states).gather(1, actions.unsqueeze(1)).squeeze(1)

        with torch.no_grad():
            next_q  = self._target_net(next_states).max(1)[0]
            targets = rewards + self.gamma * next_q * (1 - dones)

        loss = self._loss_fn(q_values, targets)
        self._optimizer.zero_grad()
        loss.backward()
        self._optimizer.step()

        # Epsilon decay
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        # Periodic target network sync (every 100 updates)
        self._update_count += 1
        if self._update_count % 100 == 0:
            self._target_net.load_state_dict(self._net.state_dict())

        return float(loss.item())

    # ── Persistence ───────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """Save network state_dict and current epsilon to disk."""
        if not self._torch_ok:
            return
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        torch.save({"net": self._net.state_dict(), "epsilon": self.epsilon}, path)

    def load(self, path: str) -> None:
        """Load network state_dict and epsilon from disk."""
        if not self._torch_ok or not os.path.exists(path):
            return
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        self._net.load_state_dict(ckpt["net"])
        self._target_net.load_state_dict(ckpt["net"])
        self.epsilon = ckpt.get("epsilon", self.epsilon_min)
