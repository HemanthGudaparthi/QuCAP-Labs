# QuCAP Labs — Quantum Computing Applications or Quantum Capabilities Laboratory

**Quantum Circuit Generator from Research Ideas & Papers — powered by Dual Deep Reinforcement Learning**

QuCAP Labs (Quantum Computing Applications or Quantum Capabilities Laboratory) is a secure, research-grade platform
that turns research submissions into executable quantum circuits. Describe your
problem as a formal title with equations, a domain keyword (e.g. `"cryptography"`),
or a free-form question (e.g. `"Build a 3-qubit GHZ state"`) — the system handles
the rest.

The primary circuit generation engine is a **Dual Deep Reinforcement Learning agent**
(Gudaparthi et al., 2026) — a hierarchical two-level DQN system that learns to build
OpenQASM 3.0 circuits from quantum research inputs without requiring an external API.
Claude AI (`claude-opus-4-7`) is available as a secondary fallback when
`ANTHROPIC_API_KEY` is set, with a built-in heuristic as the final fallback to ensure
the platform is always functional — no credentials required.

The system checks novelty against arXiv and Semantic Scholar, selects the best
hardware backend (electron via IBM Quantum, photonic, or neutrino), and executes the
circuit with a configurable shot count.

Results are private by default. An admin must explicitly approve publication
before anything appears on the public endpoint — ensuring quality control at
every stage of the research pipeline.

**At a glance:**
- **Dual Deep RL** as primary circuit generator — no API key required, always available
- Three-tier fallback: RL Agent → Claude AI → Heuristic (no single point of failure)
- Three input modes: formal research, topic keyword, or free-form query
- Novelty scoring with Innovation Level Point (ILP) token rewards for novel work
- Multi-backend quantum execution: IBM Quantum / AerSimulator / photonic (planned) / neutrino (planned)
- Admin-gated publication with full audit logging
- Integration monitor that continuously validates each module boundary

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Dual Deep RL Architecture](#dual-deep-rl-architecture)
3. [Prerequisites](#prerequisites)
4. [Environment Setup](#environment-setup)
5. [Running the Application](#running-the-application)
6. [Module Reference](#module-reference)
   - [app.py — Flask server & API routes](#apppy--flask-server--api-routes)
   - [config.py — Configuration loader](#configpy--configuration-loader)
   - [models.py — Database models](#modelspy--database-models)
   - [auth.py — Authentication & access control](#authpy--authentication--access-control)
   - [research.py — Research workflow](#researchpy--research-workflow)
   - [quantum/rl/ — Dual Deep RL framework](#quantumrl--dual-deep-rl-framework)
   - [quantum/rl_circuit.py — RL public API](#quantumrl_circuitpy--rl-public-api)
   - [quantum/ai_circuit.py — Three-tier circuit builder](#quantumai_circuitpy--three-tier-circuit-builder)
   - [quantum/monitor.py — Integration monitor](#quantummonitorpy--integration-monitor)
   - [quantum/electron.py — IBM Quantum backend](#quantumelectronpy--ibm-quantum-backend)
   - [quantum/photonic.py — Photonic backend (placeholder)](#quantumphonicpy--photonic-backend-placeholder)
   - [quantum/neutrino.py — Neutrino backend (placeholder)](#quantumneutrinopy--neutrino-backend-placeholder)
   - [quantum/limitations.py — Circuit limitations descriptor](#quantumlimitationspy--circuit-limitations-descriptor)
   - [storage/db1_gdrive.py — DB1 storage (Google Drive)](#storagedb1_gdrivepy--db1-storage-google-drive)
7. [.env Walkthrough](#env-walkthrough)
8. [API Quick Reference](#api-quick-reference)
9. [Workflow Overview](#workflow-overview)
10. [CI/CD Pipeline](#cicd-pipeline)
11. [Training the RL Agent](#training-the-rl-agent)

---

## Project Structure

```
QuCAP-Labs/
├── app.py                      # Flask factory, all API routes
├── auth.py                     # Login, JWT, lockout, role decorators
├── config.py                   # Loads .env into Flask config
├── models.py                   # SQLAlchemy ORM models
├── research.py                 # Research workflow business logic
├── schema.sql                  # PostgreSQL schema (reference)
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
├── quantum/
│   ├── __init__.py             # Backend registry (BACKENDS dict)
│   ├── base.py                 # QuantumBackend abstract class
│   ├── ai_circuit.py           # Three-tier builder: RL → Claude → Heuristic
│   ├── rl_circuit.py           # RL public API (Tier 1) — wraps DualDQNAgent
│   ├── monitor.py              # Integration monitor (health-check agent)
│   ├── hardware_selector.py    # Hardware ranking and selection
│   ├── electron.py             # IBM Quantum / Aer simulator
│   ├── photonic.py             # Placeholder
│   ├── neutrino.py             # Placeholder
│   ├── limitations.py          # Circuit limitations descriptor
│   └── rl/                     # Dual Deep RL framework (Gudaparthi et al., 2026)
│       ├── __init__.py         # Package exports
│       ├── policy.py           # CircuitPolicy abstract base class
│       ├── environment.py      # QuantumCircuitEnv (20-dim state, 10 gate actions)
│       ├── rule_policy.py      # Deterministic rule-based policy (always available)
│       ├── dqn_policy.py       # Gate DQN + Structure DQN (torch-optional)
│       ├── dual_agent.py       # DualDQNAgent — hierarchical two-level controller
│       ├── replay.py           # ReplayBuffer — experience deque for DQN training
│       └── model_store.py      # Path management for gate_dqn.pt / structure_dqn.pt
├── tests/
│   ├── test_rl_integration.py  # RL integration tests (environment, agent, monitor)
│   ├── test_ai_circuit.py      # ai_circuit tests
│   ├── test_api.py             # Flask API tests
│   ├── test_auth.py            # Auth tests
│   ├── test_hardware_selector.py
│   ├── test_limitations.py
│   └── test_research.py
└── storage/
    └── db1_gdrive.py           # Google Drive file store (DB1)
```

---

## Dual Deep RL Architecture

The Dual Deep RL framework (Gudaparthi et al., 2026) uses a hierarchical two-level
DQN system to construct quantum circuits step by step, mirroring how a researcher
iteratively builds a circuit from a problem specification.

### Agent hierarchy

```
DualDQNAgent
  ├── Structure DQN  (5-dim subgraph embedding → 3 structural decisions)
  │     EXTEND | BRANCH | FINALIZE
  └── Gate DQN      (20-dim full state → 10 gate Q-values)
        filtered by RuleBasedPolicy candidate set
```

**Structure DQN** decides at each step whether to extend the current gate sequence,
branch into a parallel subcircuit, or finalize and measure.

**Gate DQN** selects the specific gate to apply. Its action space is pre-filtered by
the rule-based policy, which maps equation keyword features to domain-appropriate gate
candidates — ensuring the agent only explores plausible gates at each depth.

### State vector (20 dimensions)

| Index | Feature |
|-------|---------|
| 0 | `is_research` input type flag |
| 1 | `is_query` input type flag |
| 2–8 | Equation keyword flags: superposition, entanglement, phase, rotation, chemistry, optimization, cryptography |
| 9 | `depth_ratio` — current depth / max depth |
| 10–18 | Gate frequency vector (one per gate type, normalized) |
| 19 | `n_qubits / 8` — qubit count, normalized |

### Gate action space (10 gates)

`h`, `cx`, `ccx`, `ry`, `rz`, `cz`, `t`, `s`, `x`, `measure`

### Reward function

| Event | Reward |
|-------|--------|
| Applying `cx`, `ccx`, or `cz` | +1.0 |
| Applying `h` | +0.3 |
| Applying `ry` or `rz` | +0.2 |
| Base step reward | +0.5 |
| Redundant gate (duplicate of previous) | −0.5 |
| Terminal: ≥ 3 gate types used | +3.0 |
| Terminal: entangling gates present | +3.0 |
| Terminal: H gate + entanglement | +2.0 |
| Terminal: depth in [3, 15] | +2.0 |
| Terminal: rotation gates present | +1.0 |
| Terminal: qubit count in [2, 8] | +1.0 |

### Three-tier fallback (no single point of failure)

```
build_circuit(title, equations)
  │
  ├─ Tier 1: Dual Deep RL agent
  │    └─ is_rl_available()? → DualDQNAgent.build_circuit()
  │    └─ on failure or unavailable ──────────────────────┐
  │                                                        │
  ├─ Tier 2: Claude AI                                     │
  │    └─ ANTHROPIC_API_KEY set? → claude-opus-4-7         │
  │    └─ on failure or missing key ──────────────────────┐│
  │                                                        ││
  └─ Tier 3: Heuristic                                     ││
       └─ _build_heuristic() ◄─────────────────────────────┘┘
            always available, no dependencies
```

The abstract `CircuitPolicy` base class ensures every policy (rule-based, Gate DQN,
Structure DQN) is independently swappable without changing the agent interface.

---

## Prerequisites

- Python 3.11+
- pip

Optional (required for specific modules):
- PyTorch ≥ 2.0 — for neural-network DQN training and inference
- IBM Quantum account — for real electron-based hardware execution
- Google Cloud service account — for DB1 (Google Drive) storage
- Anthropic API key — for Claude-powered circuit generation (Tier 2 fallback only)
- PostgreSQL — for production; SQLite is used automatically in development

---

## Environment Setup

```bash
# 1. Clone and enter the project
cd QuCAP-Labs

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies (includes torch for RL training)
pip install -r requirements.txt

# 4. Create your .env file from the template
cp .env.example .env
```

Edit `.env` and fill in at minimum:

```env
SECRET_KEY=<long random string>
JWT_SECRET_KEY=<another long random string>
BOOTSTRAP_ADMIN_ID=admin
BOOTSTRAP_ADMIN_PASSWORD=<strong password>
```

All other variables are optional and enable specific modules (see below).
The Dual Deep RL agent runs without any API keys.

---

## Running the Application

```bash
python app.py
```

On first run the bootstrap admin account is created automatically from
`BOOTSTRAP_ADMIN_ID` / `BOOTSTRAP_ADMIN_PASSWORD` in `.env`.

The server starts at `http://127.0.0.1:5000`.

To use PostgreSQL instead of the default SQLite dev database, set:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/quantumlabs
```

---

## Module Reference

### `quantum/rl/` — Dual Deep RL framework

The core RL framework implementing Gudaparthi et al. (2026). All modules are
independently importable and fail-safe.

#### `quantum/rl/policy.py` — abstract base class

```python
from quantum.rl.policy import CircuitPolicy
```

`CircuitPolicy(ABC)` defines the interface every policy must implement:
`select_action(state, **kwargs)`, `update(batch)`, `save(path)`, `load(path)`.
Ensures all policies are swappable without changing the agent or environment.

#### `quantum/rl/environment.py` — RL training environment

```python
from quantum.rl.environment import QuantumCircuitEnv
env   = QuantumCircuitEnv("Quantum Phase Estimation", "U|ψ⟩ = e^(2πiφ)|ψ⟩")
state = env.reset()                    # (20,) float32
state, reward, done, info = env.step(env.GATE_IDX["h"])
print(env.circuit_summary["qasm"])     # valid OPENQASM 3.0
```

Constants: `STATE_SIZE=20`, `ACTION_SIZE=10`, `MIN_DEPTH=3`, `max_depth=20`.

#### `quantum/rl/rule_policy.py` — deterministic fallback policy

Zero dependencies. Maps equation keyword features (state[2–8]) to an ordered
gate candidate list. Always available even when torch is absent. At
`depth_ratio ≥ 0.8` always returns `[MEASURE_IDX]`.

#### `quantum/rl/dqn_policy.py` — neural network policies

Requires PyTorch. Contains `GateDQNNetwork` (Linear 20→64→64→10) and
`StructureDQNNetwork` (Linear 5→64→64→3). Wrapped in try/except — stub classes
are used when torch is unavailable so the rest of the codebase never breaks.

#### `quantum/rl/dual_agent.py` — hierarchical DQN agent

```python
from quantum.rl.dual_agent import DualDQNAgent
agent  = DualDQNAgent()
result = agent.build_circuit("Grover Search", "∑_x |x⟩")
print(result["qasm"])
```

`build_circuit()` always returns a valid dict and never raises — on any exception
it returns a `_fallback_result()` with a minimal valid QASM circuit.

`train_episode(env)` runs one episode, pushing transitions to both replay buffers
and updating both networks.

`select_action(state, env, explore)` routes through Structure DQN →
(if not FINALIZE) → Gate DQN filtered by rule candidates.

#### `quantum/rl/replay.py` — experience replay buffer

```python
from quantum.rl.replay import ReplayBuffer
buf = ReplayBuffer(maxlen=10_000)
buf.push(state, action, reward, next_state, done)
batch = buf.sample(32)      # list of (s, a, r, s', done) tuples
```

#### `quantum/rl/model_store.py` — weight file paths

Manages paths to `gate_dqn.pt` and `structure_dqn.pt` in the project data directory.
`is_trained()` returns `True` when both weight files exist.

---

### `quantum/rl_circuit.py` — RL public API

Public interface for the Dual Deep RL agent. Matches the existing `build_circuit()`
interface exactly so no other module needs to change.

```python
from quantum.rl_circuit import build_circuit_rl, is_rl_available, train_agent

if is_rl_available():
    result = build_circuit_rl("Grover Search", "∑_x |x⟩", input_type="research")
    print(result.qasm)

# Train the agent on the built-in 8-scenario curriculum
rewards = train_agent(n_episodes=200)
```

`get_agent()` lazily initialises the singleton and loads saved weights when available.
`train_agent()` uses a built-in curriculum of 8 diverse quantum research scenarios.

---

### `quantum/ai_circuit.py` — Three-tier circuit builder

Entry point for all circuit generation. Implements the three-tier fallback:

**Tier 1 — Dual Deep RL** (always runs first):
Uses `build_circuit_rl()`. Available without any API keys. Falls back to Tier 2
only if the agent is unavailable or raises.

**Tier 2 — Claude AI** (requires `ANTHROPIC_API_KEY`):
Calls `claude-opus-4-7` with adaptive thinking to produce the circuit and assess
theoretical correctness. Falls back to Tier 3 on failure.

**Tier 3 — Heuristic** (always available):
Regex variable counting → gate selection → QASM template. No external dependencies.

```python
from quantum.ai_circuit import build_circuit

result = build_circuit(
    title="Quantum Phase Estimation",
    equations="U|ψ⟩ = e^(2πiφ)|ψ⟩",
)
print(result.qasm)
print("Theoretically correct:", result.theoretically_correct)
print("Confidence:", result.ai_confidence)
```

**Classical suggestion** — when `is_quantum_application` is `False`:

```json
{
  "is_quantum_application": false,
  "warning": "This research does not appear to require quantum hardware.",
  "classical_suggestion": {
    "reason": "...",
    "approach": "Gradient-based optimization",
    "libraries": ["scipy.optimize", "optuna"],
    "example_sketch": "from scipy.optimize import minimize\n..."
  }
}
```

Relevant `.env` key:

| Key | Default | Purpose |
|-----|---------|---------|
| `ANTHROPIC_API_KEY` | unset | Enables Claude (Tier 2 fallback). Tier 1 RL runs without it. |

---

### `quantum/monitor.py` — Integration monitor

A dedicated error-checking agent that validates each module boundary on demand.
Each probe is fully isolated — one failing module never blocks the others.
Designed for Flask startup validation, CI pipelines, and background health checking.

```python
from quantum.monitor import get_monitor

# Check all RL-workflow modules
report = get_monitor().check_all()
print(report.summary())

# Check a single module
health = get_monitor().check_module("rl_environment")
print(health.ok, health.error, health.latency_ms)
```

**Registered probes** (RL workflow only — DB and external server probes excluded):

| Probe name | What it checks |
|------------|----------------|
| `rl_environment` | `QuantumCircuitEnv` initialises and produces a (20,) state |
| `rl_dual_agent` | `DualDQNAgent.build_circuit()` returns a complete result dict |
| `rl_circuit` | Public `build_circuit_rl()` returns valid OPENQASM 3.0 |
| `ai_circuit` | Three-tier `build_circuit()` returns valid OPENQASM 3.0 |
| `hardware_selector` | `rank_hardware()` returns a non-empty list |

Database connectivity and external server reachability (IBM Quantum, Google Drive)
are intentionally excluded — they depend on credentials and network access
that are not guaranteed in CI or offline environments.

```python
# Register a custom probe
monitor = get_monitor()
monitor.register("my_module", lambda: my_module.check())
health = monitor.check_module("my_module")
```

---

### `app.py` — Flask server & API routes

Entry point. Calls `create_app()` which wires up all extensions and registers
every API route.

```bash
python app.py
```

To run with a production WSGI server:

```bash
pip install gunicorn
gunicorn "app:create_app()" --bind 127.0.0.1:5000 --workers 4
```

---

### `config.py` — Configuration loader

Reads all settings from environment variables (via `.env`).
`SECRET_KEY` and `JWT_SECRET_KEY` are required — the app will refuse to start
without them.

No direct invocation needed; `create_app()` calls `Config` automatically.

Relevant `.env` keys:

| Key | Default | Purpose |
|-----|---------|---------|
| `SECRET_KEY` | required | Flask session signing |
| `JWT_SECRET_KEY` | required | JWT signing |
| `FLASK_DEBUG` | `0` | Enable debug mode (`1` = on) |
| `DATABASE_URL` | SQLite dev file | Database connection string |
| `JWT_ACCESS_EXPIRES` | `3600` | Access token lifetime (seconds) |
| `JWT_REFRESH_EXPIRES` | `86400` | Refresh token lifetime (seconds) |
| `MAX_LOGIN_ATTEMPTS` | `5` | Failed attempts before lockout |
| `LOCKOUT_MINUTES` | `15` | Lockout duration |

---

### `models.py` — Database models

SQLAlchemy ORM definitions. Tables are created automatically on startup via
`db.create_all()` inside `create_app()`.

For PostgreSQL, you can also apply `schema.sql` directly:

```bash
psql -U <user> -d quantumlabs -f schema.sql
```

Models:

| Model | Description |
|-------|-------------|
| `User` | Researcher / admin accounts with bcrypt password and lockout state |
| `Session` | JWT revocation list (jti-indexed) |
| `Research` | Research submissions with equations, DB1 file ID, and RD entry |
| `NoveltyToken` | Issued when research passes the novelty check |
| `QuantumExperiment` | An experiment linking research to a hardware backend |
| `QuantumCircuit` | Versioned QASM circuits, with parent pointer for extensions |
| `ExperimentResult` | Raw + processed run output with reliability score |
| `AuditLog` | Immutable log of every security-sensitive action |

---

### `auth.py` — Authentication & access control

Handles password hashing, JWT issuance and revocation, login lockout, audit
logging, and role-check decorators.

Not run directly. Imported by `app.py` and `research.py`.

Key functions:

| Function | Purpose |
|----------|---------|
| `hash_password(plain)` | bcrypt hash (cost 12) |
| `check_password(plain, hashed)` | Verify bcrypt hash |
| `login(user_id, password)` | Authenticate; returns JWT pair or error string |
| `logout()` | Revokes current access token |
| `is_token_revoked(payload)` | Checks `sessions` table; used by JWT blocklist loader |
| `audit(user_id, action, ...)` | Writes to `audit_log` table |
| `@admin_required` | Decorator: 403 unless caller has `role = admin` |
| `@researcher_required` | Decorator: 403 unless caller has `role = admin` or `researcher` |

Login lockout: 5 consecutive failures lock the account for 15 minutes
(configurable via `MAX_LOGIN_ATTEMPTS` / `LOCKOUT_MINUTES`).

---

### `research.py` — Research workflow

Implements every step of the workflow diagram.

Not run directly. All functions are called through API routes in `app.py`.

**Input types** — `POST /api/research` accepts three modes via `input_type`:

| `input_type` | `title` field | `equations` | ILP tokens | Circuit prompt |
|---|---|---|---|---|
| `"research"` | Formal research title | Expected | Up to 100 (complexity-based) | Encodes equations into gates |
| `"topic"` | Domain keyword, e.g. `"cryptography"` | Optional | 15 (flat) | Canonical algorithm for that domain (Shor, QAOA, VQE, Grover…) |
| `"query"` | Free-form question or instruction, e.g. `"Build a 3-qubit GHZ state"` | Optional context | 5 (flat) | Agent interprets intent and builds the best-fit circuit |

Examples:

```bash
# Topic input — generates a Shor/BB84 circuit
curl -X POST http://127.0.0.1:5000/api/research \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"input_type": "topic", "title": "cryptography"}'

# Query input — generates the requested circuit directly
curl -X POST http://127.0.0.1:5000/api/research \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"input_type": "query", "title": "Build a 3-qubit GHZ state and measure all qubits"}'
```

| Function | Workflow step |
|----------|--------------|
| `submit_research(user_id, title, equations, input_type)` | Step 2 — Create research entry, upload to DB1, award ILP tokens |
| `check_novelty(research_id)` | Step 4 — Score novelty; issue `NoveltyToken` if novel. If not novel, returns the most recent correct `prior_circuit_id` from the RD to build upon |
| `select_hardware_and_check(research_id, hardware_type, user_id)` | Steps 5–6 — Create experiment, check hardware suitability |
| `build_experiment_circuit(experiment_id, prior_circuit_id)` | Step 7 — Generate QASM via three-tier circuit builder |
| `run_experiment(experiment_id, circuit_id, shots)` | Step 10 — Execute on backend, compute reliability score |
| `request_publication(experiment_id, user_id)` | Step 12a — Researcher requests public release |
| `approve_publication(experiment_id, admin_id)` | Step 12b — Admin approves; sets `results_public = True` |
| `extend_experiment(experiment_id, prior_circuit_id)` | Loop — Extend circuit and re-run |

---

### `quantum/electron.py` — IBM Quantum backend

Executes circuits on IBM Quantum hardware via `QiskitRuntimeService` and
`SamplerV2`. Falls back to Qiskit's local `AerSimulator` when
`IBM_QUANTUM_TOKEN` is not set.

To test standalone:

```python
from quantum.electron import ElectronBackend

backend = ElectronBackend()
print("Available:", backend.available)

qasm = """
OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
cx q[0], q[1];
c = measure q;
"""

counts = backend.run(qasm, shots=512)
print(counts)
print("Reliability:", backend.reliability_score(counts))
```

Relevant `.env` keys:

| Key | Default | Purpose |
|-----|---------|---------|
| `IBM_QUANTUM_TOKEN` | unset | IBM Quantum API token; omit to use local simulator |
| `IBM_QUANTUM_BACKEND` | `ibm_brisbane` | IBM backend name when token is set |

---

### `quantum/photonic.py` — Photonic backend (placeholder)

Satisfies the `QuantumBackend` interface. `available` always returns `False`.
All methods return placeholder responses.

Replace method bodies when photonic hardware (e.g. PsiQuantum, Xanadu) is
integrated. No configuration needed.

---

### `quantum/neutrino.py` — Neutrino backend (placeholder)

Same as the photonic placeholder. `available` always returns `False`.

Replace method bodies when neutrino-based quantum hardware becomes available.
No configuration needed.

---

### `quantum/limitations.py` — Circuit limitations descriptor

Generates a plain-English list of what a user will **not** see or experience
when they run a quantum circuit. Attached automatically to two API responses:

- `POST /api/quantum/experiments` — hardware-level limitations at experiment creation
- `POST /api/quantum/experiments/<id>/circuit` — full limitations at circuit build time

Limitations are grouped by category:

| Category | Example limitation |
|---|---|
| Hardware (no IBM token) | "Running on AerSimulator — results are noise-free and do not reflect real hardware" |
| Hardware (photonic / neutrino) | "Placeholder backend — no real hardware connected" |
| Universal QC | "No error correction applied", "Results are probabilistic samples" |
| Novelty system | "Hash-based novelty score, not real semantic search" |
| Input type: `topic` | "Illustrative circuit — not parameterised for your problem size" |
| Input type: `query` | "AI-interpreted best-effort approximation — verify gate logic" |
| Circuit quality | Low confidence warning, theoretical correctness failure notice |

---

### `storage/db1_gdrive.py` — DB1 storage (Google Drive)

Stores research JSON files in a Google Drive folder.

**With credentials:** uploads/downloads via the Google Drive API.

**Without credentials:** writes JSON files to `/tmp/db1_stub_<id>.json`
(development stub mode — no data is lost, just stored locally).

To test standalone:

```python
from storage.db1_gdrive import DB1Storage

store = DB1Storage()
print("Drive available:", store.available)

file_id = store.upload_research("test-001", {"title": "Test", "equations": "E=mc²"})
print("Stored as:", file_id)

data = store.download_research(file_id)
print(data)
```

Relevant `.env` keys:

| Key | Default | Purpose |
|-----|---------|---------|
| `GDRIVE_CREDENTIALS_FILE` | unset | Path to Google service account JSON |
| `GDRIVE_FOLDER_ID` | unset | Google Drive folder ID to use as DB1 |

To set up Google Drive credentials:

1. Create a project in [Google Cloud Console](https://console.cloud.google.com).
2. Enable the **Google Drive API**.
3. Create a **Service Account** and download the JSON key.
4. Share your target Drive folder with the service account email.
5. Set `GDRIVE_CREDENTIALS_FILE` to the JSON path and `GDRIVE_FOLDER_ID` to the folder ID.

---

## .env Walkthrough

Copy `.env.example` to `.env` and work through each section below.
Variables marked **required** will cause the app to refuse to start if missing.
Everything else is optional and enables a specific feature or backend.

```bash
cp .env.example .env
```

---

### Flask core

```env
SECRET_KEY=CHANGE_ME_LONG_RANDOM_STRING
JWT_SECRET_KEY=CHANGE_ME_ANOTHER_LONG_RANDOM_STRING
FLASK_DEBUG=0
```

| Variable | Required | Notes |
|----------|----------|-------|
| `SECRET_KEY` | yes | Signs Flask sessions. Use a long random string — generate one with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_SECRET_KEY` | yes | Signs JWT tokens. Use a different value from `SECRET_KEY` |
| `FLASK_DEBUG` | no | Set to `1` for auto-reload during development. **Never `1` in production.** |

---

### Bootstrap admin (first run only)

```env
BOOTSTRAP_ADMIN_ID=admin
BOOTSTRAP_ADMIN_PASSWORD=CHANGE_ME_STRONG_PASSWORD
```

| Variable | Required | Notes |
|----------|----------|-------|
| `BOOTSTRAP_ADMIN_ID` | first run | The username of the first admin account created on startup |
| `BOOTSTRAP_ADMIN_PASSWORD` | first run | Must be strong. After the account is created you can remove both variables from `.env` |

Once the admin exists, removing these lines from `.env` prevents accidental re-use.

---

### Database

```env
DATABASE_URL=postgresql://user:password@localhost:5432/quantumlabs
```

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | no | Standard SQLAlchemy connection string. If omitted, the app uses a local SQLite file (`quantumlabs_dev.db`) — fine for development, not for production |

---

### Claude AI — Tier 2 circuit builder fallback

```env
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY
```

| Variable | Required | Notes |
|----------|----------|-------|
| `ANTHROPIC_API_KEY` | no | Enables Claude (`claude-opus-4-7`) as Tier 2 fallback when the RL agent is unavailable. If absent, the app falls back directly to the heuristic builder. The Dual Deep RL agent (Tier 1) always runs first regardless of this setting. |

Get a key at [console.anthropic.com](https://console.anthropic.com). The key starts with `sk-ant-`.

---

### IBM Quantum — electron backend

```env
IBM_QUANTUM_TOKEN=YOUR_IBM_QUANTUM_API_TOKEN
IBM_QUANTUM_BACKEND=ibm_brisbane
```

| Variable | Required | Notes |
|----------|----------|-------|
| `IBM_QUANTUM_TOKEN` | no | IBM Quantum API token. If absent, the electron backend falls back to Qiskit's local `AerSimulator` |
| `IBM_QUANTUM_BACKEND` | no | Name of the IBM backend to target (default: `ibm_brisbane`) |

Get a token at [quantum.ibm.com](https://quantum.ibm.com).

---

### Google Drive — DB1 storage

```env
GDRIVE_CREDENTIALS_FILE=credentials/gdrive_service_account.json
GDRIVE_FOLDER_ID=YOUR_GOOGLE_DRIVE_FOLDER_ID
```

| Variable | Required | Notes |
|----------|----------|-------|
| `GDRIVE_CREDENTIALS_FILE` | no | Path to the Google service account JSON key file |
| `GDRIVE_FOLDER_ID` | no | ID of the Drive folder to use as DB1 |

If either variable is missing, research files are saved to `/tmp/db1_stub_<id>.json` locally instead.

---

### Security tuning

```env
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_MINUTES=15
```

| Variable | Required | Notes |
|----------|----------|-------|
| `MAX_LOGIN_ATTEMPTS` | no | How many consecutive failed logins before an account is locked (default: 5) |
| `LOCKOUT_MINUTES` | no | How long the lockout lasts (default: 15 minutes) |

---

### Minimal `.env` for local development

This is the smallest `.env` that will start the app with no external services:

```env
SECRET_KEY=dev-secret-change-me-in-production-abc123
JWT_SECRET_KEY=dev-jwt-secret-change-me-in-production-xyz789
FLASK_DEBUG=1
BOOTSTRAP_ADMIN_ID=admin
BOOTSTRAP_ADMIN_PASSWORD=Admin1234!
```

Everything else falls back gracefully: SQLite for the database, Dual Deep RL
as primary circuit builder (with heuristic as final fallback), AerSimulator
for quantum runs, and `/tmp` stubs for DB1.

---

## API Quick Reference

All endpoints except `POST /api/auth/login` and `GET /api/results/public`
require a `Bearer <token>` header.

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/api/auth/login` | — | Get JWT tokens |
| POST | `/api/auth/logout` | any | Revoke current token |
| GET | `/api/auth/me` | any | Current user info |
| POST | `/api/auth/users` | admin | Create a user |
| POST | `/api/research` | researcher | Submit research, topic, or free-form query |
| GET | `/api/research/<id>` | owner / admin | Get research entry |
| POST | `/api/research/<id>/novelty` | researcher | Run novelty check |
| GET | `/api/quantum/hardware` | any | List backend availability |
| POST | `/api/quantum/experiments` | researcher | Create experiment + suitability check |
| POST | `/api/quantum/experiments/<id>/circuit` | researcher | Build circuit (via RL agent) |
| POST | `/api/quantum/experiments/<id>/run` | researcher | Execute circuit |
| POST | `/api/quantum/experiments/<id>/extend` | researcher | Extend circuit (loop) |
| POST | `/api/results/<id>/request-publication` | researcher | Request public release |
| POST | `/api/results/<id>/approve` | admin | Approve public release |
| GET | `/api/results/public` | — | List approved public results |
| GET | `/api/results/<id>` | owner / admin | Get experiment result |
| GET | `/api/admin/audit-log` | admin | Paginated audit log |

Example login:

```bash
curl -s -X POST http://127.0.0.1:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"id": "admin", "password": "your_password"}' | python -m json.tool
```

Use the returned `access_token` in subsequent requests:

```bash
curl -s http://127.0.0.1:5000/api/auth/me \
  -H "Authorization: Bearer <access_token>"
```

---

## Workflow Overview

```
Login
  └─ Submit Research (title + equations)
       └─ Novelty Check
            ├─ Not novel → retrieve existing circuit from RD (prior_circuit_id returned)
            │                  └─ Build Circuit (extend existing circuit) ──────────────────┐
            └─ Novel → Novelty Token issued                                                  │
                 └─ Select Hardware (electron | photonic | neutrino)                        │
                      └─ Suitability Check                                                  │
                           ├─ Not suitable → stop                                           │
                           └─ Suitable                                                      │
                                └─ Build Circuit ◄──────────────────────────────────────────┘
                                     │  Tier 1: Dual Deep RL agent (Gudaparthi et al. 2026)
                                     │  Tier 2: Claude AI (if ANTHROPIC_API_KEY set)
                                     │  Tier 3: Heuristic (always available)
                                     ├─ Not a quantum application → classical suggestion returned
                                     └─ Run Experiment (shots)
                                          ├─ Reliability < 0.6 → Extend Circuit ──┐
                                          │                                        │ (loop)
                                          └─ Reliability ≥ 0.6                     ┘
                                               └─ Request Publication (researcher)
                                                    └─ Approve Publication (admin only)
                                                         └─ Results visible at /api/results/public
```

When research is **not novel**, the novelty check response includes a
`prior_circuit_id` pointing to the most recent theoretically-correct circuit
in the database. Pass that ID as `prior_circuit_id` in the body of
`POST /api/quantum/experiments/<id>/circuit` to build an extended circuit
instead of generating one from scratch.

Results are **private by default** and require explicit admin approval before
they appear on the public endpoint.

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/quCAP-rl.yml`) runs five jobs:

| Job | Trigger | What it does |
|-----|---------|--------------|
| `lint` | every push / PR | flake8 on `quantum/`, `tests/`, `app.py`, `research.py` |
| `unit-tests` | every push / PR | pytest `tests/` excluding `test_rl_integration.py` |
| `rl-integration-monitor` | every push / PR | Runs the IntegrationMonitor and fails if any RL probe is unhealthy |
| `rl-circuit-validate` | every push / PR | Builds circuits for all three input types and validates OPENQASM output |
| `rl-train` | schedule / manual dispatch | Trains the agent for 200 episodes and saves weights |

All CI jobs run without API keys. The monitor checks only the RL workflow
(`rl_environment`, `rl_dual_agent`, `ai_circuit`) — no database or external
server connectivity is required.

---

## Training the RL Agent

The agent ships untrained. Training uses a built-in 8-scenario curriculum
covering Quantum Phase Estimation, Grover Search, QAOA, VQE, Quantum Fourier
Transform, and several topic/query inputs.

```python
from quantum.rl_circuit import train_agent

# Train for 200 episodes (default)
rewards = train_agent(n_episodes=200)
print(f"Final episode reward: {rewards[-1]:.2f}")
```

Or via the CLI:

```bash
python -c "from quantum.rl_circuit import train_agent; train_agent(500)"
```

Trained weights are saved to `quantum/rl/weights/gate_dqn.pt` and
`quantum/rl/weights/structure_dqn.pt`. The agent loads them automatically
on the next application start — no configuration required.

To verify the agent is healthy after training:

```python
from quantum.monitor import get_monitor
report = get_monitor().check_all()
print(report.summary())
```
