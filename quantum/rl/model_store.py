"""Model weight path management for Dual DQN agents."""

import os


class ModelStore:
    """Manages file-system paths for saved RL policy weights."""

    def __init__(self, base_dir: str = "quantum/rl/models"):
        self.base_dir = base_dir

    def ensure_dir(self) -> None:
        """Create the model directory tree if it does not exist."""
        os.makedirs(self.base_dir, exist_ok=True)

    def gate_model_path(self) -> str:
        return os.path.join(self.base_dir, "gate_dqn.pt")

    def structure_model_path(self) -> str:
        return os.path.join(self.base_dir, "structure_dqn.pt")

    def exists(self) -> bool:
        """True when both gate and structure model files are present on disk."""
        return (os.path.exists(self.gate_model_path()) and
                os.path.exists(self.structure_model_path()))

    def checkpoint_path(self, episode: int) -> str:
        return os.path.join(self.base_dir, f"checkpoint_ep{episode}.pt")
