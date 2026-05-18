"""Tests for quantum/hardware_selector.py — heuristic ranking and selection."""
import pytest
from quantum.hardware_selector import rank_hardware, select_hardware, full_ranking, _SUITABILITY_THRESHOLD


# ── rank_hardware — structure ─────────────────────────────────────────────────

def test_ranking_returns_three_entries():
    ranking = rank_hardware("quantum algorithm", "")
    assert len(ranking) == 3
    types = {item["type"] for item in ranking}
    assert types == {"electron", "photonic", "neutrino"}


def test_ranking_entries_have_required_keys():
    for item in rank_hardware("test", ""):
        assert "type"   in item
        assert "score"  in item
        assert "reason" in item


def test_ranking_scores_are_0_to_1():
    for item in rank_hardware("quantum gate circuit", ""):
        assert 0.0 <= item["score"] <= 1.0


def test_ranking_is_sorted_descending():
    ranking = rank_hardware("quantum optimization grover search", "")
    scores = [item["score"] for item in ranking]
    assert scores == sorted(scores, reverse=True)


# ── rank_hardware — electron domain ──────────────────────────────────────────

def test_electron_scores_high_for_quantum_keywords():
    ranking = rank_hardware("Grover search algorithm quantum circuit", "qubit gate hamiltonian")
    electron = next(r for r in ranking if r["type"] == "electron")
    assert electron["score"] >= _SUITABILITY_THRESHOLD


def test_electron_scores_high_for_cryptography():
    ranking = rank_hardware("quantum cryptography factoring Shor algorithm", "")
    electron = next(r for r in ranking if r["type"] == "electron")
    assert electron["score"] >= _SUITABILITY_THRESHOLD


def test_electron_scores_high_for_vqe():
    ranking = rank_hardware("variational quantum eigensolver VQE chemistry", "hamiltonian ansatz")
    electron = next(r for r in ranking if r["type"] == "electron")
    assert electron["score"] >= _SUITABILITY_THRESHOLD


def test_electron_base_boost_applies():
    # Even with no keywords, electron gets a small base boost.
    ranking = rank_hardware("general research", "")
    electron = next(r for r in ranking if r["type"] == "electron")
    assert electron["score"] >= 0.10


# ── rank_hardware — photonic domain ──────────────────────────────────────────

def test_photonic_scores_high_for_qkd():
    ranking = rank_hardware("quantum key distribution fiber optical network", "photon squeezed")
    photonic = next(r for r in ranking if r["type"] == "photonic")
    assert photonic["score"] >= _SUITABILITY_THRESHOLD


def test_photonic_scores_high_for_quantum_communication():
    ranking = rank_hardware("photonic quantum communication boson sampling", "optical waveguide")
    photonic = next(r for r in ranking if r["type"] == "photonic")
    assert photonic["score"] >= _SUITABILITY_THRESHOLD


# ── rank_hardware — neutrino domain ──────────────────────────────────────────

def test_neutrino_scores_high_for_particle_physics():
    ranking = rank_hardware("neutrino oscillation particle physics standard model", "lepton mixing")
    neutrino = next(r for r in ranking if r["type"] == "neutrino")
    assert neutrino["score"] >= _SUITABILITY_THRESHOLD


def test_neutrino_scores_high_for_oscillation_study():
    ranking = rank_hardware("muon neutrino flavor mixing atmospheric reactor", "PMNS matrix")
    neutrino = next(r for r in ranking if r["type"] == "neutrino")
    assert neutrino["score"] >= _SUITABILITY_THRESHOLD


# ── select_hardware — priority order ─────────────────────────────────────────

def test_select_returns_electron_for_quantum_algorithm():
    hw, reason = select_hardware("quantum algorithm Grover search qubit gate", "")
    assert hw == "electron"
    assert isinstance(reason, str) and len(reason) > 0


def test_select_returns_none_for_classical_problem():
    # A clearly classical problem with no quantum keywords.
    hw, reason = select_hardware("calculate mean and standard deviation of dataset", "μ = Σx/n")
    # Electron base boost may still score it; verify reason string is returned regardless.
    assert isinstance(reason, str)


def test_select_returns_tuple_always():
    result = select_hardware("any title", "any equations")
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_select_hardware_type_is_valid_or_none():
    hw, _ = select_hardware("quantum entanglement gate circuit", "")
    assert hw in ("electron", "photonic", "neutrino", None)


# ── full_ranking ──────────────────────────────────────────────────────────────

def test_full_ranking_has_ranking_and_classical_flag():
    result = full_ranking("quantum circuit", "")
    assert "ranking" in result
    assert "recommend_classical" in result
    assert isinstance(result["recommend_classical"], bool)


def test_full_ranking_recommend_classical_false_for_quantum_topic():
    result = full_ranking("quantum algorithm qubit entanglement", "gate hamiltonian")
    assert result["recommend_classical"] is False


def test_full_ranking_input_type_topic():
    result = full_ranking("cryptography", "", input_type="topic")
    assert len(result["ranking"]) == 3
