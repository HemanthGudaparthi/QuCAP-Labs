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
   - [storage/db1_gdrive.py — DB1 storage (Google Drive)](#storagedb1_gdrivepy--db1-storage-google-drive)
6. [API Quick Reference](#api-quick-reference)
7. [Workflow Overview](#workflow-overview)

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

| Function | Workflow step |
|----------|--------------|
| `submit_research(user_id, title, equations)` | Step 2 — Create research entry, upload to DB1, award ILP tokens |
| `check_novelty(research_id)` | Step 4 — Score novelty; issue `NoveltyToken` if novel |
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
from quantum.ai_circuit import build_circuit

result = build_circuit(
    title="Quantum Phase Estimation",
    equations="U|ψ⟩ = e^(2πiφ)|ψ⟩",
)
print(result.qasm)
print("Theoretically correct:", result.theoretically_correct)
print("Confidence:", result.ai_confidence)
```

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

## API Quick Reference

All endpoints except `POST /api/auth/login` and `GET /api/results/public`
require a `Bearer <token>` header.

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/api/auth/login` | — | Get JWT tokens |
| POST | `/api/auth/logout` | any | Revoke current token |
| GET | `/api/auth/me` | any | Current user info |
| POST | `/api/auth/users` | admin | Create a user |
| POST | `/api/research` | researcher | Submit research |
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
            ├─ Not novel → stop
            └─ Novel → Novelty Token issued
                 └─ Select Hardware (electron | photonic | neutrino)
                      └─ Suitability Check
                           ├─ Not suitable → stop
                           └─ Suitable
                                └─ Build Circuit (Claude AI / heuristic)
                                     └─ Run Experiment (shots)
                                          ├─ Reliability < 0.6 → Extend Circuit ──┐
                                          │                                        │ (loop)
                                          └─ Reliability ≥ 0.6                    ┘
                                               └─ Request Publication (researcher)
                                                    └─ Approve Publication (admin only)
                                                         └─ Results visible at /api/results/public
```

Results are **private by default** and require explicit admin approval before
they appear on the public endpoint.
