"""Experience replay buffer for Dual DQN training."""

import random
from collections import deque


class ReplayBuffer:
    """
    Fixed-capacity FIFO experience store for off-policy DQN training.

    Mirrors the dataset/experience collection pattern in the user's notebook
    but uses a sliding window deque rather than a static list.
    """

    def __init__(self, maxlen: int = 10_000):
        self._buf = deque(maxlen=maxlen)

    def push(self, state, action: int, reward: float, next_state, done: bool) -> None:
        """Store a (s, a, r, s', done) transition tuple."""
        self._buf.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int) -> list:
        """Random sample without replacement (capped at buffer size)."""
        return random.sample(self._buf, min(batch_size, len(self._buf)))

    def __len__(self) -> int:
        return len(self._buf)

    def is_ready(self, batch_size: int) -> bool:
        """True when the buffer contains at least batch_size experiences."""
        return len(self._buf) >= batch_size
