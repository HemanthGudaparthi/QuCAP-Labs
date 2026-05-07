"""
QuantumLabs research workflow — mirrors every decision node in the diagram.

Flow:
  login → submit_research → check_novelty → (select_hardware → check_suitability)
        → build_ai_circuit → run_experiments → check_reliability
        → request_publication / approve_publication → extend_circuit (loop)
"""

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone

from models import db, User, Research, NoveltyToken, QuantumExperiment, QuantumCircuit, ExperimentResult
from storage.db1_gdrive import DB1Storage
from quantum import get_backend
from quantum.ai_circuit import build_circuit, extend_circuit as ai_extend

_db1 = DB1Storage()


def utcnow():
    return datetime.now(timezone.utc)


# ─── Step 2: Research submission ─────────────────────────────────────────────

def submit_research(user_id: str, title: str, equations: str | None) -> tuple[Research | None, str | None]:
    """Create a research entry, persist to DB1, and award base ILP tokens."""
    if not title or not title.strip():
        return None, "Title is required"

    research_id = str(uuid.uuid4())[:16]
    db1_payload = {
        "research_id": research_id,
        "user_id":     user_id,
        "title":       title,
        "equations":   equations,
    }
    db1_file_id = _db1.upload_research(research_id, db1_payload)

    base_tokens = _award_ilp_tokens(equations)

    r = Research(
        id             = research_id,
        user_id        = user_id,
        title          = title,
        equations      = equations,
        tokens_awarded = base_tokens,
        db1_file_id    = db1_file_id,
    )
    db.session.add(r)

    user = User.query.get(user_id)
    if user:
        user.ilp_tokens += base_tokens

    db.session.commit()
    return r, None


def _award_ilp_tokens(equations: str | None) -> int:
    """Heuristic: more complex equations earn more ILP tokens."""
    if not equations:
        return 10
    complexity = len(equations)
    return min(10 + complexity // 20, 100)


# ─── Step 4: Novelty check → Novelty Tokens ──────────────────────────────────

def check_novelty(research_id: str) -> tuple[bool, float, int | None]:
    """
    Determine novelty of the research against the Research Database (RD).
    Placeholder: real implementation queries an embedding similarity index.

    Returns (is_novel, novelty_score 0–1, prior_circuit_id).

    - Novel     → issues a NoveltyToken; prior_circuit_id is None.
    - Not novel → looks up the most recent correct circuit in the DB to use
                  as the starting point for the build-circuit step;
                  prior_circuit_id is that circuit's ID (or None if none exist yet).
    """
    r = Research.query.get(research_id)
    if not r:
        return False, 0.0, None

    # Placeholder novelty score: hash-based pseudo-score.
    # Replace with vector similarity search against RD.
    seed = hashlib.sha256((r.title + (r.equations or "")).encode()).hexdigest()
    score = (int(seed[:8], 16) % 1000) / 1000.0  # deterministic but fake

    is_novel = score >= 0.5
    r.is_novel      = is_novel
    r.novelty_score = score

    prior_circuit_id = None
    if is_novel:
        _issue_novelty_token(r)
    else:
        # Not novel: surface the most recent theoretically-correct circuit from
        # the RD so the researcher can extend it instead of starting from scratch.
        existing = (QuantumCircuit.query
                    .filter_by(theoretically_correct=True)
                    .order_by(QuantumCircuit.id.desc())
                    .first())
        if existing:
            prior_circuit_id = existing.id
            # Point this research entry at the existing RD entry.
            r.rd_entry_id = f"rd:{existing.experiment_id}"

    db.session.commit()
    return is_novel, score, prior_circuit_id


def _issue_novelty_token(research: Research):
    """Create and store a novelty token in the RD."""
    raw         = f"{research.id}:{research.user_id}:{secrets.token_hex(16)}"
    token_hash  = hashlib.sha256(raw.encode()).hexdigest()
    token_value = int(research.novelty_score * 100)

    nt = NoveltyToken(
        research_id   = research.id,
        user_id       = research.user_id,
        novelty_score = research.novelty_score,
        token_value   = token_value,
        token_hash    = token_hash,
    )
    db.session.add(nt)

    user = User.query.get(research.user_id)
    if user:
        user.ilp_tokens += token_value

    # rd_entry_id: placeholder — real RD would be a vector DB / external service.
    research.rd_entry_id = f"rd:{research.id}"


# ─── Step 5/6: Hardware selection & suitability ───────────────────────────────

def select_hardware_and_check(research_id: str, hardware_type: str,
                              user_id: str) -> tuple[QuantumExperiment | None, bool, str]:
    """
    Create an experiment record and check hardware suitability.
    Returns (experiment, is_suitable, reason).
    """
    r = Research.query.get(research_id)
    if not r:
        return None, False, "Research not found"
    if hardware_type not in ("electron", "photonic", "neutrino"):
        return None, False, "Invalid hardware type"

    backend = get_backend(hardware_type)

    # Build a preliminary circuit just to assess suitability.
    circuit_result = build_circuit(r.title, r.equations or "")
    is_suitable, reason = backend.check_suitability(
        circuit_result.qasm, {"title": r.title}
    )

    exp = QuantumExperiment(
        research_id   = research_id,
        user_id       = user_id,
        hardware_type = hardware_type,
        is_suitable   = is_suitable,
    )
    db.session.add(exp)
    db.session.commit()
    return exp, is_suitable, reason


# ─── Step 7: AI circuit build ─────────────────────────────────────────────────

def build_experiment_circuit(experiment_id: int,
                             prior_circuit_id: int | None = None) -> tuple[QuantumCircuit | None, str | None]:
    """
    Use the AI circuit builder to produce (or extend) a quantum circuit
    and persist it. Returns (circuit, error).
    """
    exp = QuantumExperiment.query.get(experiment_id)
    if not exp:
        return None, "Experiment not found"

    r = Research.query.get(exp.research_id)

    prior_qasm = None
    parent_id  = None
    version    = 1

    if prior_circuit_id:
        pc = QuantumCircuit.query.get(prior_circuit_id)
        if pc:
            prior_qasm = pc.circuit_qasm
            parent_id  = pc.id
            version    = pc.version + 1

    result = build_circuit(r.title, r.equations or "", prior_qasm=prior_qasm)

    qc = QuantumCircuit(
        experiment_id          = experiment_id,
        version                = version,
        circuit_qasm           = result.qasm,
        circuit_metadata       = json.dumps(result.metadata),
        theoretically_correct  = result.theoretically_correct,
        is_quantum_application = result.is_quantum_application,
        ai_confidence          = result.ai_confidence,
        parent_circuit_id      = parent_id,
    )
    db.session.add(qc)
    exp.circuit_version = version
    db.session.commit()
    return qc, None


# ─── Step 10: Run experiments ─────────────────────────────────────────────────

def run_experiment(experiment_id: int, circuit_id: int,
                   shots: int = 1024) -> tuple[ExperimentResult | None, str | None]:
    """Execute the circuit on the selected hardware backend."""
    exp = QuantumExperiment.query.get(experiment_id)
    qc  = QuantumCircuit.query.get(circuit_id)

    if not exp or not qc:
        return None, "Experiment or circuit not found"
    if not qc.theoretically_correct:
        return None, "Circuit has not passed theoretical correctness check"

    backend = get_backend(exp.hardware_type)

    raw = backend.run(qc.circuit_qasm, shots=shots)
    score = backend.reliability_score(raw)
    passed = score >= 0.6

    result = ExperimentResult(
        experiment_id     = experiment_id,
        circuit_id        = circuit_id,
        raw_results       = json.dumps(raw),
        processed_results = json.dumps({"reliability_score": score}),
        reliability_score = score,
    )
    db.session.add(result)

    exp.run_count          += 1
    exp.reliability_passed  = passed
    exp.reliability_score   = score
    db.session.commit()
    return result, None


# ─── Step 12: Publication control ────────────────────────────────────────────

def request_publication(experiment_id: int, requesting_user_id: str) -> tuple[bool, str]:
    """Researcher requests that results be made public — requires admin approval."""
    exp = QuantumExperiment.query.get(experiment_id)
    if not exp:
        return False, "Experiment not found"
    if exp.user_id != requesting_user_id:
        return False, "Not your experiment"
    if not exp.reliability_passed:
        return False, "Reliability test has not passed"
    # Approval is handled separately by an admin via approve_publication().
    return True, "Publication request submitted. Awaiting admin approval."


def approve_publication(experiment_id: int, admin_user_id: str) -> tuple[bool, str]:
    """Admin approves making experiment results public."""
    admin = User.query.get(admin_user_id)
    if not admin or not admin.is_admin():
        return False, "Admin privileges required"

    exp = QuantumExperiment.query.get(experiment_id)
    if not exp:
        return False, "Experiment not found"

    exp.results_public          = True
    exp.publication_approved_by = admin_user_id
    exp.publication_approved_at = utcnow()

    # Mark all results public.
    for res in exp.results:
        res.is_public   = True
        res.approved_by = admin_user_id
        res.approved_at = utcnow()

    db.session.commit()
    return True, "Results approved for publication"


# ─── "Build upon & extend" loop ───────────────────────────────────────────────

def extend_experiment(experiment_id: int, prior_circuit_id: int) -> tuple[QuantumCircuit | None, str | None]:
    """
    Workflow loop: after a successful run, extend the circuit and create a
    new experiment iteration — 'Build upon existing results and extend the
    Quantum Circuit.'
    """
    return build_experiment_circuit(experiment_id, prior_circuit_id=prior_circuit_id)
