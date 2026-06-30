"""
Integration Monitor — error-checking agent for all QuantumLabs modules.

Probes each module boundary on demand. Each probe is fully isolated:
one module failing never blocks the others from running. Designed for
Flask startup validation, CI pipelines, and background health-checking.

Usage:
    from quantum.monitor import get_monitor
    report = get_monitor().check_all()
    print(report.summary())
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ModuleHealth:
    """Health status for a single module probe."""
    name:       str
    ok:         bool
    latency_ms: float
    error:      str = ""
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class HealthReport:
    """Aggregated health status across all registered modules."""
    all_ok:     bool
    modules:    list
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def summary(self) -> str:
        """Formatted health table suitable for logs and CI output."""
        lines = [f"[Monitor] Health check @ {self.checked_at}",
                 f"  {'Status':<6}  {'Module':<30}  {'ms':>6}  Notes",
                 "  " + "-" * 62]
        for m in self.modules:
            status = "OK   " if m.ok else "FAIL "
            note   = f"  ← {m.error[:55]}" if not m.ok else ""
            lines.append(f"  {status}  {m.name:<30}  {m.latency_ms:>6.0f}{note}")
        lines.append(f"\n  Overall: {'ALL OK' if self.all_ok else 'DEGRADED — see FAIL rows above'}")
        return "\n".join(lines)


# ── Monitor class ─────────────────────────────────────────────────────────────

class IntegrationMonitor:
    """
    Extensible module health checker.

    Register custom probes via register(name, probe_fn).
    Each probe should raise any exception on failure and return None on success.
    """

    def __init__(self):
        self._probes:  dict = {}
        self._history: list = []
        self._register_defaults()

    # ── Probe management ──────────────────────────────────────────────────

    def register(self, name: str, probe_fn: Callable) -> None:
        """Register a named probe function."""
        self._probes[name] = probe_fn

    def _register_defaults(self) -> None:
        """Register all built-in module probes."""
        self.register("rl_environment",    self._probe_rl_environment)
        self.register("rl_dual_agent",     self._probe_rl_dual_agent)
        self.register("rl_circuit",        self._probe_rl_circuit)
        self.register("ai_circuit",        self._probe_ai_circuit)
        self.register("hardware_selector", self._probe_hardware_selector)
        self.register("electron_backend",  self._probe_electron_backend)
        self.register("db1_storage",       self._probe_db1_storage)

    # ── Check execution ───────────────────────────────────────────────────

    def check_module(self, name: str) -> ModuleHealth:
        """
        Run a single named probe.

        Catches ALL exceptions — never re-raises. This is intentional:
        the monitor's job is to report failure, not propagate it.
        """
        probe = self._probes.get(name)
        if probe is None:
            return ModuleHealth(
                name=name, ok=False, latency_ms=0.0,
                error=f"No probe registered for '{name}'"
            )
        t0 = time.perf_counter()
        try:
            probe()
            return ModuleHealth(
                name=name, ok=True,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as exc:
            return ModuleHealth(
                name=name, ok=False,
                latency_ms=(time.perf_counter() - t0) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )

    def check_all(self) -> HealthReport:
        """Run every registered probe and return an aggregated HealthReport."""
        results = [self.check_module(name) for name in self._probes]
        report  = HealthReport(all_ok=all(m.ok for m in results), modules=results)
        self._history.append(report)
        return report

    def check_module_and_raise(self, name: str) -> None:
        """Convenience: raise RuntimeError when the named module is unhealthy."""
        health = self.check_module(name)
        if not health.ok:
            raise RuntimeError(f"Module '{name}' unhealthy: {health.error}")

    @property
    def last_report(self) -> Optional[HealthReport]:
        """Most recent HealthReport, or None if no checks have run yet."""
        return self._history[-1] if self._history else None

    # ── Default probes ────────────────────────────────────────────────────

    def _probe_rl_environment(self) -> None:
        """Verify QuantumCircuitEnv initialises and produces a correctly-shaped state."""
        from quantum.rl.environment import QuantumCircuitEnv
        env   = QuantumCircuitEnv("GHZ test", "E = mc²")
        state = env.reset()
        if state.shape != (QuantumCircuitEnv.STATE_SIZE,):
            raise ValueError(
                f"State shape {state.shape} != ({QuantumCircuitEnv.STATE_SIZE},)"
            )
        env.step(QuantumCircuitEnv.GATE_IDX["h"])   # one step must not raise

    def _probe_rl_dual_agent(self) -> None:
        """Verify DualDQNAgent.build_circuit() returns a complete result dict."""
        from quantum.rl.dual_agent import DualDQNAgent
        agent  = DualDQNAgent()
        result = agent.build_circuit("GHZ state", "")
        required = {
            "qasm", "n_qubits", "gates", "theoretically_correct",
            "is_quantum_application", "ai_confidence", "notes",
        }
        missing = required - set(result.keys())
        if missing:
            raise ValueError(f"build_circuit() missing keys: {missing}")
        if not result.get("qasm"):
            raise ValueError("build_circuit() returned empty QASM")

    def _probe_rl_circuit(self) -> None:
        """Verify the RL public API is reachable and returns valid QASM."""
        from quantum.rl_circuit import build_circuit_rl, is_rl_available
        if not is_rl_available():
            raise RuntimeError("RL agent failed to initialise")
        result = build_circuit_rl("GHZ state", "", input_type="query")
        if "OPENQASM" not in result.qasm:
            raise ValueError(f"Invalid QASM from RL: {result.qasm[:80]}")

    def _probe_ai_circuit(self) -> None:
        """Verify ai_circuit.build_circuit() returns valid QASM across all tiers."""
        from quantum.ai_circuit import build_circuit
        result = build_circuit("test circuit", "", input_type="query")
        if "OPENQASM" not in result.qasm:
            raise ValueError(f"Invalid QASM from ai_circuit: {result.qasm[:80]}")

    def _probe_hardware_selector(self) -> None:
        """Verify hardware ranking returns a non-empty list."""
        from quantum.hardware_selector import rank_hardware
        ranking = rank_hardware("quantum circuit", "H = ∑ σ_z")
        if not ranking or not isinstance(ranking, list):
            raise ValueError(f"rank_hardware returned: {ranking!r}")

    def _probe_electron_backend(self) -> None:
        """Verify ElectronBackend can be instantiated without error."""
        from quantum.electron import ElectronBackend
        backend = ElectronBackend()
        _ = backend.available   # property access must not raise

    def _probe_db1_storage(self) -> None:
        """Verify DB1Storage can be instantiated without error."""
        from storage.db1_gdrive import DB1Storage
        store = DB1Storage()
        _ = store.available     # property access must not raise


# ── Singleton ─────────────────────────────────────────────────────────────────

_monitor: Optional[IntegrationMonitor] = None


def get_monitor() -> IntegrationMonitor:
    """Return (or lazily create) the global IntegrationMonitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = IntegrationMonitor()
    return _monitor
