"""
QuApp Labs — research workflow — mirrors every decision node in the diagram.

Flow:
  login → submit_research → check_novelty → (select_hardware → check_suitability)
        → build_ai_circuit → run_experiments → check_reliability
        → request_publication / approve_publication → extend_circuit (loop)
"""

import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timezone

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    import anthropic as _anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

from models import db, User, Research, NoveltyToken, QuantumExperiment, QuantumCircuit, ExperimentResult
from storage.db1_gdrive import DB1Storage
from quantum import get_backend
from quantum.ai_circuit import build_circuit, extend_circuit as ai_extend
from quantum.hardware_selector import select_hardware, full_ranking

_MODEL = "claude-opus-4-7"

_db1 = DB1Storage()


def utcnow():
    return datetime.now(timezone.utc)


# ─── Step 2: Research submission ─────────────────────────────────────────────

_VALID_INPUT_TYPES = {"research", "topic", "query"}


def submit_research(user_id: str, title: str, equations: str | None,
                    input_type: str = "research") -> tuple[Research | None, str | None]:
    """
    Create a research entry, persist to DB1, and award base ILP tokens.

    input_type:
      "research" — formal research submission with title + equations
      "topic"    — domain keyword (e.g. "cryptography"); equations optional
      "query"    — free-form question or circuit request; equations optional
    """
    if not title or not title.strip():
        return None, "title is required"
    if input_type not in _VALID_INPUT_TYPES:
        return None, f"input_type must be one of: {', '.join(sorted(_VALID_INPUT_TYPES))}"

    research_id = str(uuid.uuid4())[:16]
    db1_payload = {
        "research_id": research_id,
        "user_id":     user_id,
        "input_type":  input_type,
        "title":       title,
        "equations":   equations,
    }
    db1_file_id = _db1.upload_research(research_id, db1_payload)

    base_tokens = _award_ilp_tokens(equations, input_type)

    r = Research(
        id             = research_id,
        user_id        = user_id,
        input_type     = input_type,
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


def _award_ilp_tokens(equations: str | None, input_type: str = "research") -> int:
    """
    ILP token awards by input type:
      research — up to 100 tokens based on equation complexity
      topic    — flat 15 tokens (exploratory)
      query    — flat 5 tokens (single inquiry)
    """
    if input_type == "topic":
        return 15
    if input_type == "query":
        return 5
    if not equations:
        return 10
    complexity = len(equations)
    return min(10 + complexity // 20, 100)


# ─── Step 4: Novelty check → Novelty Tokens ──────────────────────────────────

def check_novelty(research_id: str) -> tuple[bool, float, int | None, str]:
    """
    Search arXiv and Semantic Scholar for related work, then assess novelty.
    Also runs a hardware suitability pre-check to recommend electron/photonic/neutrino.

    Returns (is_novel, novelty_score 0–1, prior_circuit_id, assessment).

    Novel     → issues a NoveltyToken; prior_circuit_id is None.
    Not novel → returns ID of the most recent correct circuit to extend from.
    """
    r = Research.query.get(research_id)
    if not r:
        return False, 0.0, None, "Research not found."

    arxiv_hits   = _search_arxiv(r.title, r.equations)
    scholar_hits = _search_semantic_scholar(r.title)

    is_novel, score, assessment = _assess_novelty(r, arxiv_hits, scholar_hits)

    r.is_novel      = is_novel
    r.novelty_score = score

    prior_circuit_id = None
    if is_novel:
        _issue_novelty_token(r)
    else:
        existing = (QuantumCircuit.query
                    .filter_by(theoretically_correct=True)
                    .order_by(QuantumCircuit.id.desc())
                    .first())
        if existing:
            prior_circuit_id = existing.id
            r.rd_entry_id = f"rd:{existing.experiment_id}"

    db.session.commit()
    return is_novel, score, prior_circuit_id, assessment


# ── Novelty: internet search ──────────────────────────────────────────────────

def _search_arxiv(title: str, equations: str | None) -> list[dict]:
    """Query the arXiv API for papers related to the research title."""
    if not _HAS_REQUESTS:
        return []
    query = re.sub(r"[^\w\s]", "", title).strip().replace(" ", "+")
    url   = f"http://export.arxiv.org/api/query?search_query=ti:{query}&max_results=5"
    try:
        resp = _requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        titles    = re.findall(r"<entry>.*?<title>(.*?)</title>.*?<summary>(.*?)</summary>",
                               resp.text, re.DOTALL)
        return [{"title": t.strip(), "abstract": s.strip()[:300]}
                for t, s in titles][:5]
    except Exception as exc:
        print(f"[novelty] arXiv search failed: {exc}")
        return []


def _search_semantic_scholar(title: str) -> list[dict]:
    """Query Semantic Scholar for papers related to the research title."""
    if not _HAS_REQUESTS:
        return []
    url    = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": title, "limit": 5,
               "fields": "title,abstract,year,citationCount"}
    try:
        resp = _requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return []
        return resp.json().get("data", [])
    except Exception as exc:
        print(f"[novelty] Semantic Scholar search failed: {exc}")
        return []


# ── Novelty: assessment ───────────────────────────────────────────────────────

_NOVELTY_SYSTEM = """\
You are a research librarian and quantum computing expert. Given a research
submission and related papers found in online databases, assess novelty.

Respond with ONLY a JSON object — no prose, no markdown fences:
{
  "novelty_score": <0.0–1.0>,
  "is_novel": <true if score >= 0.5>,
  "assessment": "<2-3 sentences explaining the verdict>",
  "most_similar": "<title of most similar found paper, or null>"
}

Scoring:
  0.0–0.2 Nearly identical work exists
  0.2–0.4 Very similar, minor variations
  0.4–0.6 Related work but meaningful differences
  0.6–0.8 Novel angle or combination of ideas
  0.8–1.0 Highly novel — little prior art found
"""


def _assess_novelty(research: Research, arxiv_hits: list[dict],
                    scholar_hits: list[dict]) -> tuple[bool, float, str]:
    """Return (is_novel, score, assessment)."""
    api_key = (
        __import__("os").environ.get("ANTHROPIC_API_KEY")
        if _HAS_ANTHROPIC else None
    )
    if api_key:
        try:
            return _assess_with_claude(research, arxiv_hits, scholar_hits, api_key)
        except Exception as exc:
            print(f"[novelty] Claude assessment failed ({exc}); using heuristic.")

    return _assess_heuristic(research, arxiv_hits, scholar_hits)


def _assess_with_claude(research: Research, arxiv_hits: list, scholar_hits: list,
                        api_key: str) -> tuple[bool, float, str]:
    client = _anthropic.Anthropic(api_key=api_key)

    papers = ""
    if arxiv_hits:
        papers += "arXiv:\n" + "\n".join(
            f"- {p['title']}: {p['abstract'][:200]}" for p in arxiv_hits)
    if scholar_hits:
        papers += "\n\nSemantic Scholar:\n" + "\n".join(
            f"- {p.get('title','')}: {(p.get('abstract') or '')[:200]}"
            for p in scholar_hits)
    if not papers:
        papers = "No related papers found in online databases."

    user_content = (
        f"Title: {research.title}\n"
        f"Equations: {research.equations or '(none)'}\n\n"
        f"Related papers:\n{papers}"
    )
    with client.messages.stream(
        model=_MODEL,
        max_tokens=512,
        system=_NOVELTY_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        message = stream.get_final_message()

    raw = ""
    for block in message.content:
        if block.type == "text":
            raw = block.text.strip()
            break
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    data       = json.loads(raw)
    score      = float(data.get("novelty_score", 0.5))
    is_novel   = bool(data.get("is_novel", score >= 0.5))
    assessment = data.get("assessment", "")
    return is_novel, score, assessment


def _assess_heuristic(research: Research, arxiv_hits: list,
                      scholar_hits: list) -> tuple[bool, float, str]:
    """Score based on number of similar papers found; hash-based if no results."""
    total = len(arxiv_hits) + len(scholar_hits)

    if total == 0 and not _HAS_REQUESTS:
        # requests module unavailable → deterministic hash-based fallback
        seed  = hashlib.sha256((research.title + (research.equations or "")).encode()).hexdigest()
        score = (int(seed[:8], 16) % 1000) / 1000.0
        assessment = (
            "Online database search unavailable. Novelty assessed using a "
            "hash-based heuristic — treat this result as approximate."
        )
    elif total == 0:
        score      = 0.85
        assessment = "No related papers found in arXiv or Semantic Scholar — research appears highly novel."
    elif total <= 2:
        score      = 0.65
        assessment = f"Found {total} related paper(s). Research has meaningful differences from existing work."
    elif total <= 4:
        score      = 0.40
        assessment = f"Found {total} related papers. Some similarity to existing work detected."
    else:
        score      = 0.25
        assessment = f"Found {total} related papers. Strong similarity to existing literature."

    is_novel = score >= 0.5
    return is_novel, round(score, 3), assessment


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

def select_hardware_and_check(research_id: str, hardware_type: str | None,
                              user_id: str) -> tuple[QuantumExperiment | None, bool, str]:
    """
    Select quantum hardware and check content-based suitability.
    Returns (experiment, is_suitable, reason).

    hardware_type=None  → auto-select: electron → photonic → neutrino →
                          classical suggestion if none qualify.
    hardware_type=<str> → manual override; suitability still assessed by
                          content analysis, not just circuit parameters.
    """
    r = Research.query.get(research_id)
    if not r:
        return None, False, "Research not found"

    if hardware_type:
        if hardware_type not in ("electron", "photonic", "neutrino"):
            return None, False, "Invalid hardware type. Use electron, photonic, or neutrino."
        selected_type = hardware_type
        # Content-based suitability for the manually chosen backend.
        ranking  = __import__("quantum.hardware_selector", fromlist=["rank_hardware"]).rank_hardware(
            r.title, r.equations or "", r.input_type
        )
        score_map  = {item["type"]: item for item in ranking}
        item       = score_map.get(selected_type, {"score": 0.1, "reason": "Not assessed."})
        is_suitable = item["score"] >= 0.35
        reason      = item["reason"]
    else:
        # Auto-selection: tries electron → photonic → neutrino in priority order.
        selected_type, reason = select_hardware(
            r.title, r.equations or "", r.input_type
        )
        if selected_type is None:
            # Nothing suitable — create a logged experiment anyway so the
            # classical suggestion flows through to the response.
            selected_type = "electron"
            is_suitable   = False
        else:
            is_suitable = True

    exp = QuantumExperiment(
        research_id   = research_id,
        user_id       = user_id,
        hardware_type = selected_type,
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

    result = build_circuit(r.title, r.equations or "", prior_qasm=prior_qasm,
                           input_type=r.input_type)

    metadata = dict(result.metadata)
    if result.algorithm_name:
        metadata["algorithm_name"] = result.algorithm_name
    if result.interpretation:
        metadata["interpretation"] = result.interpretation

    qc = QuantumCircuit(
        experiment_id          = experiment_id,
        version                = version,
        circuit_qasm           = result.qasm,
        circuit_metadata       = json.dumps(metadata),
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
