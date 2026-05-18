"""Tests for research.py — submission, ILP tokens, novelty heuristic, hardware selection,
run_experiment, and publication control."""
import pytest
from unittest.mock import patch
from auth import hash_password
from research import (
    submit_research, _award_ilp_tokens,
    _assess_heuristic, _search_arxiv, _search_semantic_scholar,
    select_hardware_and_check, run_experiment,
    request_publication, approve_publication,
)


# ── _award_ilp_tokens ─────────────────────────────────────────────────────────

def test_tokens_topic_flat():
    assert _award_ilp_tokens(None, "topic") == 15


def test_tokens_query_flat():
    assert _award_ilp_tokens(None, "query") == 5


def test_tokens_research_no_equations():
    assert _award_ilp_tokens(None, "research") == 10


def test_tokens_research_with_short_equations():
    assert _award_ilp_tokens("a+b", "research") >= 10


def test_tokens_research_complexity_increases_award():
    short = _award_ilp_tokens("x", "research")
    long  = _award_ilp_tokens("x" * 200, "research")
    assert long > short


def test_tokens_research_capped_at_100():
    assert _award_ilp_tokens("x" * 10_000, "research") == 100


# ── submit_research ───────────────────────────────────────────────────────────

def test_submit_research_missing_title(app, db):
    with app.app_context():
        r, err = submit_research("user1", "", None, "research")
        assert r is None
        assert err is not None


def test_submit_research_invalid_input_type(app, db):
    with app.app_context():
        r, err = submit_research("user1", "Some title", None, "invalid_type")
        assert r is None
        assert "input_type" in err.lower()


def test_submit_research_type_creates_entry(app, db):
    from models import User
    from auth import hash_password
    with app.app_context():
        db.session.add(User(id="u_res", password_hash=hash_password("P1!"), role="researcher"))
        db.session.commit()
        r, err = submit_research("u_res", "Quantum Grover", "H|ψ⟩", "research")
        assert err is None
        assert r is not None
        assert r.input_type == "research"


def test_submit_topic_type(app, db):
    from models import User
    from auth import hash_password
    with app.app_context():
        db.session.add(User(id="u_top", password_hash=hash_password("P1!"), role="researcher"))
        db.session.commit()
        r, err = submit_research("u_top", "cryptography", None, "topic")
        assert err is None
        assert r.input_type == "topic"
        assert r.tokens_awarded == 15


def test_submit_query_type(app, db):
    from models import User
    from auth import hash_password
    with app.app_context():
        db.session.add(User(id="u_qry", password_hash=hash_password("P1!"), role="researcher"))
        db.session.commit()
        r, err = submit_research("u_qry", "Build a Bell state", None, "query")
        assert err is None
        assert r.input_type == "query"
        assert r.tokens_awarded == 5


# ── _assess_heuristic ─────────────────────────────────────────────────────────

class _FakeResearch:
    def __init__(self, title="Test", equations=""):
        self.title     = title
        self.equations = equations
        self.id        = "fake-id"


def test_heuristic_zero_results_online_scores_high(monkeypatch):
    # requests available but returned nothing → score 0.85 (likely novel)
    monkeypatch.setattr("research._HAS_REQUESTS", True)
    is_novel, score, assessment = _assess_heuristic(_FakeResearch(), [], [])
    assert score == 0.85
    assert is_novel is True
    assert "no related" in assessment.lower() or "novel" in assessment.lower()


def test_heuristic_offline_uses_deterministic_hash(monkeypatch):
    # requests unavailable → hash-based score, same input yields same score
    monkeypatch.setattr("research._HAS_REQUESTS", False)
    _, score1, assessment = _assess_heuristic(_FakeResearch(), [], [])
    _, score2, _          = _assess_heuristic(_FakeResearch(), [], [])
    assert 0.0 <= score1 <= 1.0
    assert score1 == score2
    assert "unavailable" in assessment.lower() or "hash" in assessment.lower()


def test_heuristic_many_papers_not_novel():
    papers = [{"title": f"Paper {i}", "abstract": "abstract"} for i in range(5)]
    is_novel, score, _ = _assess_heuristic(_FakeResearch(), papers, papers)
    assert is_novel is False
    assert score < 0.5


def test_heuristic_few_papers_possibly_novel():
    papers = [{"title": "One related paper", "abstract": "abstract"}]
    _, score, _ = _assess_heuristic(_FakeResearch(), papers, [])
    assert score >= 0.5


# ── _search_arxiv — graceful failure ─────────────────────────────────────────

def test_search_arxiv_returns_list_on_network_failure():
    with patch("research._requests") as mock_req:
        mock_req.get.side_effect = Exception("network error")
        result = _search_arxiv("quantum test", None)
        assert isinstance(result, list)


def test_search_arxiv_returns_list_on_bad_status():
    with patch("research._requests") as mock_req:
        mock_req.get.return_value.status_code = 503
        result = _search_arxiv("quantum test", None)
        assert result == []


def test_search_arxiv_parses_entries():
    xml = """<?xml version="1.0"?>
<feed>
<entry>
  <title>Quantum Algorithm Test</title>
  <summary>This paper describes a quantum algorithm.</summary>
</entry>
</feed>"""
    with patch("research._requests") as mock_req:
        mock_req.get.return_value.status_code = 200
        mock_req.get.return_value.text = xml
        result = _search_arxiv("quantum algorithm", None)
        assert len(result) >= 1
        assert "title" in result[0]


# ── _search_semantic_scholar — graceful failure ───────────────────────────────

def test_search_scholar_returns_list_on_failure():
    with patch("research._requests") as mock_req:
        mock_req.get.side_effect = Exception("timeout")
        result = _search_semantic_scholar("quantum test")
        assert isinstance(result, list)


def test_search_scholar_parses_json():
    with patch("research._requests") as mock_req:
        mock_req.get.return_value.status_code = 200
        mock_req.get.return_value.json.return_value = {
            "data": [{"title": "Quantum Paper", "abstract": "abstract", "year": 2023}]
        }
        result = _search_semantic_scholar("quantum")
        assert len(result) == 1
        assert result[0]["title"] == "Quantum Paper"


# ── select_hardware_and_check ─────────────────────────────────────────────────

def test_select_invalid_hardware_type(app, db):
    from models import User, Research
    from auth import hash_password
    with app.app_context():
        db.session.add(User(id="u_hw", password_hash=hash_password("P1!"), role="researcher"))
        r = Research(id="r_hw1", user_id="u_hw", input_type="research",
                     title="Test", tokens_awarded=10, is_novel=False)
        db.session.add(r)
        db.session.commit()
        exp, ok, reason = select_hardware_and_check("r_hw1", "laser", "u_hw")
        assert exp is None
        assert ok is False


def test_select_manual_electron_creates_experiment(app, db):
    from models import User, Research
    from auth import hash_password
    with app.app_context():
        db.session.add(User(id="u_hw2", password_hash=hash_password("P1!"), role="researcher"))
        r = Research(id="r_hw2", user_id="u_hw2", input_type="research",
                     title="Quantum gate circuit qubit", tokens_awarded=10, is_novel=True)
        db.session.add(r)
        db.session.commit()
        exp, ok, reason = select_hardware_and_check("r_hw2", "electron", "u_hw2")
        assert exp is not None
        assert exp.hardware_type == "electron"


def test_select_auto_creates_experiment(app, db):
    from models import User, Research
    from auth import hash_password
    with app.app_context():
        db.session.add(User(id="u_hw3", password_hash=hash_password("P1!"), role="researcher"))
        r = Research(id="r_hw3", user_id="u_hw3", input_type="research",
                     title="quantum algorithm grover search qubit gate",
                     tokens_awarded=10, is_novel=True)
        db.session.add(r)
        db.session.commit()
        exp, ok, reason = select_hardware_and_check("r_hw3", None, "u_hw3")
        assert exp is not None
        assert exp.hardware_type in ("electron", "photonic", "neutrino")


def test_select_returns_error_for_missing_research(app, db):
    with app.app_context():
        exp, ok, reason = select_hardware_and_check("nonexistent", "electron", "u_any")
        assert exp is None
        assert "not found" in reason.lower()


# ── run_experiment ────────────────────────────────────────────────────────────

_VALID_QASM = (
    'OPENQASM 3.0;\ninclude "stdgates.inc";\n'
    'qubit[2] q;\nbit[2] c;\nh q[0];\ncx q[0],q[1];\nc = measure q;'
)


def _make_run_fixtures(db, user_id, research_id, correct):
    """Create User + Research + QuantumExperiment + QuantumCircuit in the session."""
    from models import User, Research, QuantumExperiment, QuantumCircuit
    db.session.add(User(id=user_id, password_hash=hash_password("P1!"), role="researcher"))
    db.session.add(Research(id=research_id, user_id=user_id, input_type="research",
                            title="Run Test", tokens_awarded=10, is_novel=True))
    exp = QuantumExperiment(research_id=research_id, user_id=user_id,
                            hardware_type="electron", is_suitable=True)
    db.session.add(exp)
    db.session.commit()
    qc = QuantumCircuit(experiment_id=exp.id, version=1, circuit_qasm=_VALID_QASM,
                        circuit_metadata="{}", theoretically_correct=correct,
                        is_quantum_application=False, ai_confidence=0.9)
    db.session.add(qc)
    db.session.commit()
    return exp, qc


def test_run_experiment_success(app, db):
    with app.app_context():
        exp, qc = _make_run_fixtures(db, "u_run1", "r_run1", correct=True)
        with patch("research.get_backend") as mock_hw:
            mock_hw.return_value.run.return_value          = {"00": 600, "11": 424}
            mock_hw.return_value.reliability_score.return_value = 0.70
            result, err = run_experiment(exp.id, qc.id, shots=1024)
        assert err is None
        assert result.reliability_score == 0.70
        from models import QuantumExperiment as QE
        assert QE.query.get(exp.id).reliability_passed is True


def test_run_experiment_rejects_unverified_circuit(app, db):
    with app.app_context():
        exp, qc = _make_run_fixtures(db, "u_run2", "r_run2", correct=False)
        result, err = run_experiment(exp.id, qc.id)
        assert result is None
        assert err is not None


def test_run_experiment_missing_experiment(app, db):
    with app.app_context():
        result, err = run_experiment(9999, 9999)
        assert result is None
        assert err is not None


# ── request_publication / approve_publication ─────────────────────────────────

def test_publication_workflow(app, db):
    from models import User, Research, QuantumExperiment
    with app.app_context():
        db.session.add(User(id="u_pub1", password_hash=hash_password("P1!"), role="researcher"))
        db.session.add(User(id="adm_pub1", password_hash=hash_password("P1!"), role="admin"))
        db.session.add(Research(id="r_pub1", user_id="u_pub1", input_type="research",
                                title="Pub test", tokens_awarded=10, is_novel=True))
        exp = QuantumExperiment(research_id="r_pub1", user_id="u_pub1",
                                hardware_type="electron", is_suitable=True,
                                reliability_passed=True, reliability_score=0.75)
        db.session.add(exp)
        db.session.commit()

        # Wrong user cannot request
        ok, _ = request_publication(exp.id, "adm_pub1")
        assert not ok

        # Owner can request when reliability passed
        ok, msg = request_publication(exp.id, "u_pub1")
        assert ok and "awaiting" in msg.lower()

        # Non-admin cannot approve
        ok, _ = approve_publication(exp.id, "u_pub1")
        assert not ok

        # Admin approves → results_public flips
        ok, _ = approve_publication(exp.id, "adm_pub1")
        assert ok
        assert QuantumExperiment.query.get(exp.id).results_public is True


def test_request_publication_requires_reliability(app, db):
    from models import User, Research, QuantumExperiment
    with app.app_context():
        db.session.add(User(id="u_pub2", password_hash=hash_password("P1!"), role="researcher"))
        db.session.add(Research(id="r_pub2", user_id="u_pub2", input_type="research",
                                title="Unreliable", tokens_awarded=10, is_novel=True))
        exp = QuantumExperiment(research_id="r_pub2", user_id="u_pub2",
                                hardware_type="electron", is_suitable=True,
                                reliability_passed=False)
        db.session.add(exp)
        db.session.commit()
        ok, msg = request_publication(exp.id, "u_pub2")
        assert not ok
        assert "reliability" in msg.lower()
ty" in msg.lower()
wer()
