"""
Electron-based quantum backend — IBM Quantum via Qiskit Runtime.

Requires IBM_QUANTUM_TOKEN in environment.
Falls back to Qiskit's local AerSimulator when credentials are absent
so development works without hardware access.
"""

import json
import os

from .base import QuantumBackend


class ElectronBackend(QuantumBackend):

    name = "electron"

    def __init__(self):
        self._token   = os.environ.get("IBM_QUANTUM_TOKEN")
        self._backend_name = os.environ.get("IBM_QUANTUM_BACKEND", "ibm_brisbane")
        self._service = None
        self._backend  = None

        if self._token:
            self._init_ibm()

    def _init_ibm(self):
        try:
            from qiskit_ibm_runtime import QiskitRuntimeService
            self._service = QiskitRuntimeService(
                channel="ibm_quantum",
                token=self._token,
            )
            self._backend = self._service.backend(self._backend_name)
        except Exception as exc:
            print(f"[ElectronBackend] IBM init failed ({exc}); falling back to simulator.")
            self._service = None
            self._backend  = None

    @property
    def available(self) -> bool:
        return self._backend is not None or True   # simulator always available

    def _get_local_backend(self):
        from qiskit_aer import AerSimulator
        return AerSimulator()

    # ── suitability ───────────────────────────────────────────────────────────
    def check_suitability(self, circuit_qasm: str, research_metadata: dict) -> tuple[bool, str]:
        try:
            from qiskit import QuantumCircuit
            qc = QuantumCircuit.from_qasm_str(circuit_qasm)
            n_qubits = qc.num_qubits
            depth    = qc.depth()

            if self._backend:
                config     = self._backend.configuration()
                max_qubits = config.n_qubits
                if n_qubits > max_qubits:
                    return False, f"Circuit needs {n_qubits} qubits; backend has {max_qubits}"
            if depth > 1000:
                return False, f"Circuit depth {depth} exceeds practical limit"

            return True, "Circuit is suitable for electron-based execution"
        except Exception as exc:
            return False, f"Suitability check error: {exc}"

    # ── run ───────────────────────────────────────────────────────────────────
    def run(self, circuit_qasm: str, shots: int = 1024) -> dict:
        from qiskit import QuantumCircuit
        from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

        qc = QuantumCircuit.from_qasm_str(circuit_qasm)

        if self._backend:
            # Real IBM hardware path
            from qiskit_ibm_runtime import SamplerV2 as Sampler
            pm           = generate_preset_pass_manager(backend=self._backend, optimization_level=1)
            transpiled   = pm.run(qc)
            sampler      = Sampler(mode=self._backend)
            job          = sampler.run([transpiled], shots=shots)
            result       = job.result()
            counts       = result[0].data.meas.get_counts()
        else:
            # Local AerSimulator fallback
            from qiskit_aer import AerSimulator
            from qiskit import transpile
            sim        = AerSimulator()
            transpiled = transpile(qc, sim)
            job        = sim.run(transpiled, shots=shots)
            counts     = job.result().get_counts()

        return {"counts": counts, "shots": shots, "backend": self._backend_name}

    # ── reliability ───────────────────────────────────────────────────────────
    def reliability_score(self, raw_results: dict) -> float:
        counts = raw_results.get("counts", {})
        shots  = raw_results.get("shots", 1)
        if not counts:
            return 0.0
        top = max(counts.values())
        # Score = fraction of shots in the dominant outcome (simple measure)
        return round(top / shots, 4)
