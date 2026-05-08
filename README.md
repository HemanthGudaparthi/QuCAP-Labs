# QuantumLabs

A secure Flask-based platform for managing quantum research experiments.
Researchers submit equations, the AI builds quantum circuits, and results
are never made public without explicit admin approval.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Prerequisites](#prerequisites)
3. [Environment Setup](#environment-setup)
4. [Running the Application](#running-the-application)
5. [Module Reference](#module-reference)
   - [app.py — Flask server & API routes](#apppy--flask-server--api-routes)
   - [config.py — Configuration loader](#configpy--configuration-loader)
   - [models.py — Database models](#modelspy--database-models)
   - [auth.py — Authentication & access control](#authpy--authentication--access-control)
   - [research.py — Research workflow](#researchpy--research-workflow)
   - [quantum/ai_circuit.py — AI circuit builder](#quantumai_circuitpy--ai-circuit-builder)
   - [quantum/electron.py — IBM Quantum backend](#quantumelectronpy--ibm-quantum-backend)
   - [quantum/photonic.py — Photonic backend (placeholder)](#quantumphonicpy--photonic-backend-placeholder)
   - [quantum/neutrino.py — Neutrino backend (placeholder)](#quantumneutrinopy--neutrino-backend-placeholder)
   - [quantum/limitations.py — Circuit limitations descriptor](#quantumlimitationspy--circuit-limitations-descriptor)
   - [storage/db1_gdrive.py — DB1 storage (Google Drive)](#storagedb1_gdrivepy--db1-storage-google-drive)
6. [.env Walkthrough](#env-walkthrough)
7. [API Quick Reference](#api-quick-reference)
8. [Workflow Overview](#workflow-overview)

---

## Project Structure

```
QuantumLabs/
├── app.py                  # Flask factory, all API routes
├── auth.py                 # Login, JWT, lockout, role decorators
├── config.py               # Loads .env into Flask config
├── models.py               # SQLAlchemy ORM models
├── research.py             # Research workflow business logic
├── schema.sql              # PostgreSQL schema (reference)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── quantum/
│   ├── __init__.py         # Backend registry (BACKENDS dict)
│   ├── base.py             # QuantumBackend abstract class
│   ├── ai_circuit.py       # AI circuit generation (Claude + heuristic fallback)
│   ├── electron.py         # IBM Quantum / Aer simulator
│   ├── photonic.py         # Placeholder
│   └── neutrino.py         # Placeholder
└── storage/
    └── db1_gdrive.py       # Google Drive file store (DB1)
```

---

## Prerequisites

- Python 3.11+
- pip

Optional (required for specific modules):
- IBM Quantum account — for real electron-based hardware execution
- Google Cloud service account — for DB1 (Google Drive) storage
- Anthropic API key — for Claude-powered circuit generation
- PostgreSQL — for production; SQLite is used automatically in development

---

## Environment Setup

```bash
# 1. Clone and enter the project
cd QuantumLabs

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
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
| `"query"` | Free-form question or instruction, e.g. `"Build a 3-qubit GHZ state"` | Optional context | 5 (flat) | AI interprets intent and builds the best-fit circuit |

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
| `build_experiment_circuit(experiment_id, prior_circuit_id)` | Step 7 — Generate QASM via AI circuit builder |
| `run_experiment(experiment_id, circuit_id, shots)` | Step 10 — Execute on backend, compute reliability score |
| `request_publication(experiment_id, user_id)` | Step 12a — Researcher requests public release |
| `approve_publication(experiment_id, admin_id)` | Step 12b — Admin approves; sets `results_public = True` |
| `extend_experiment(experiment_id, prior_circuit_id)` | Loop — Extend circuit and re-run |

---

### `quantum/ai_circuit.py` — AI circuit builder

Generates OpenQASM 3.0 circuits from a research title and equations.

**With `ANTHROPIC_API_KEY` set:** calls Claude (`claude-opus-4-7`) with
adaptive thinking to produce the circuit, assess theoretical correctness,
and determine whether it constitutes a quantum application.

**Without `ANTHROPIC_API_KEY`:** falls back to the built-in heuristic
(regex variable counting → gate selection → QASM template).

To test standalone:

```python
from quantum.ai_circuit import build_circuit, suggest_classical_approach

result = build_circuit(
    title="Quantum Phase Estimation",
    equations="U|ψ⟩ = e^(2πiφ)|ψ⟩",
)
print(result.qasm)
print("Theoretically correct:", result.theoretically_correct)
print("Confidence:", result.ai_confidence)
```

**Classical suggestion** — when `is_quantum_application` is `False`, the
circuit build API response includes a `warning` field and a
`classical_suggestion` block:

```json
{
  "is_quantum_application": false,
  "warning": "This research does not appear to require quantum hardware. It can likely be solved more efficiently on a regular computer.",
  "classical_suggestion": {
    "reason": "...",
    "approach": "Gradient-based optimization",
    "libraries": ["scipy.optimize", "optuna"],
    "example_sketch": "from scipy.optimize import minimize\n...",
    "documentation_links": ["https://docs.scipy.org/..."]
  }
}
```

The suggestion is generated by Claude when `ANTHROPIC_API_KEY` is set, or by
a keyword heuristic otherwise. Categories covered: optimization, linear
algebra, graph/search, Monte Carlo simulation, machine learning, and ODE
solving.

Relevant `.env` key:

| Key | Default | Purpose |
|-----|---------|---------|
| `ANTHROPIC_API_KEY` | unset | Enables Claude circuit generation |

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

The `limitations` array appears in both responses so researchers understand
the constraints before interpreting results. No configuration required.

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

PostgreSQL example: `postgresql://quantumlabs:mypassword@localhost:5432/quantumlabs`

SQLite is used automatically when this variable is absent — no configuration needed for local development.

---

### Claude AI — circuit builder

```env
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY
```

| Variable | Required | Notes |
|----------|----------|-------|
| `ANTHROPIC_API_KEY` | no | Enables Claude (`claude-opus-4-7`) for quantum circuit generation. If absent, the app falls back to the built-in heuristic circuit builder automatically |

Get a key at [console.anthropic.com](https://console.anthropic.com). The key starts with `sk-ant-`.

---

### IBM Quantum — electron backend

```env
IBM_QUANTUM_TOKEN=YOUR_IBM_QUANTUM_API_TOKEN
IBM_QUANTUM_BACKEND=ibm_brisbane
```

| Variable | Required | Notes |
|----------|----------|-------|
| `IBM_QUANTUM_TOKEN` | no | IBM Quantum API token. If absent, the electron backend falls back to Qiskit's local `AerSimulator` — experiments still run, just on a local simulator |
| `IBM_QUANTUM_BACKEND` | no | Name of the IBM backend to target (default: `ibm_brisbane`). Check available backends in the IBM Quantum dashboard |

Get a token at [quantum.ibm.com](https://quantum.ibm.com).

---

### Google Drive — DB1 storage

```env
GDRIVE_CREDENTIALS_FILE=credentials/gdrive_service_account.json
GDRIVE_FOLDER_ID=YOUR_GOOGLE_DRIVE_FOLDER_ID
```

| Variable | Required | Notes |
|----------|----------|-------|
| `GDRIVE_CREDENTIALS_FILE` | no | Path to the Google service account JSON key file, relative to the project root |
| `GDRIVE_FOLDER_ID` | no | ID of the Drive folder to use as DB1. Found in the folder's URL: `drive.google.com/drive/folders/<ID>` |

If either variable is missing, research files are saved to `/tmp/db1_stub_<id>.json` locally instead. No data is lost in development; just make sure to configure Drive before running in production.

Setup steps:
1. Create a project in [Google Cloud Console](https://console.cloud.google.com) and enable the **Drive API**.
2. Create a **Service Account**, download its JSON key, and place it at the path above.
3. Share your target Drive folder with the service account's email address (shown in the JSON file under `client_email`).

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

Everything else falls back gracefully: SQLite for the database, heuristic
circuit builder, AerSimulator for quantum runs, and `/tmp` stubs for DB1.

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
| POST | `/api/quantum/experiments/<id>/circuit` | researcher | Build circuit |
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
            │                  └─ Build Circuit (extend existing circuit) ──────────────┐
            └─ Novel → Novelty Token issued                                             │
                 └─ Select Hardware (electron | photonic | neutrino)                   │
                      └─ Suitability Check                                             │
                           ├─ Not suitable → stop                                      │
                           └─ Suitable                                                 │
                                └─ Build Circuit (Claude AI / heuristic) ◄─────────────┘
                                     ├─ Not a quantum application → classical suggestion returned
                                     └─ Run Experiment (shots)
                                          ├─ Reliability < 0.6 → Extend Circuit ──┐
                                          │                                        │ (loop)
                                          └─ Reliability ≥ 0.6                    ┘
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
