"""Tests for quantum/limitations.py — limitation string generation."""
import pytest
from quantum.limitations import describe_limitations


def _lims(**kwargs):
    defaults = dict(
        hardware_type="electron", backend_available=False,
        input_type="research",
        theoretically_correct=None, is_quantum_application=None, ai_confidence=None,
    )
    defaults.update(kwargs)
    return describe_limitations(**defaults)


# ── Return type ───────────────────────────────────────────────────────────────

def test_returns_list():
    assert isinstance(_lims(), list)


def test_all_items_are_strings():
    for item in _lims():
        assert isinstance(item, str) and len(item) > 0


# ── Universal limitations always present ─────────────────────────────────────

def test_always_includes_qec_limitation():
    text = " ".join(_lims())
    assert "error correction" in text.lower()


def test_always_includes_probabilistic_limitation():
    text = " ".join(_lims())
    assert "probabilistic" in text.lower() or "shots" in text.lower()


def test_always_includes_depth_limitation():
    text = " ".join(_lims())
    assert "depth" in text.lower()


def test_always_includes_novelty_limitation():
    text = " ".join(_lims())
    assert "novelty" in text.lower()


# ── Electron without IBM token ────────────────────────────────────────────────

def test_electron_no_token_warns_about_simulator():
    lims = _lims(hardware_type="electron", backend_available=False)
    combined = " ".join(lims).lower()
    assert "aersimu" in combined or "simulator" in combined


def test_electron_no_token_mentions_no_noise():
    lims = _lims(hardware_type="electron", backend_available=False)
    combined = " ".join(lims).lower()
    assert "noise" in combined


# ── Electron with IBM token ───────────────────────────────────────────────────

def test_electron_with_token_mentions_noise():
    lims = _lims(hardware_type="electron", backend_available=True)
    combined = " ".join(lims).lower()
    assert "noise" in combined


def test_electron_with_token_no_simulator_warning():
    lims = _lims(hardware_type="electron", backend_available=True)
    combined = " ".join(lims).lower()
    assert "aersimu" not in combined


# ── Photonic backend ──────────────────────────────────────────────────────────

def test_photonic_includes_placeholder_warning():
    lims = _lims(hardware_type="photonic", backend_available=False)
    combined = " ".join(lims).lower()
    assert "placeholder" in combined


def test_photonic_warns_no_real_hardware():
    lims = _lims(hardware_type="photonic", backend_available=False)
    combined = " ".join(lims).lower()
    assert "photonic" in combined


# ── Neutrino backend ──────────────────────────────────────────────────────────

def test_neutrino_includes_placeholder_warning():
    lims = _lims(hardware_type="neutrino", backend_available=False)
    combined = " ".join(lims).lower()
    assert "placeholder" in combined or "neutrino" in combined


def test_neutrino_no_commercially_available():
    lims = _lims(hardware_type="neutrino", backend_available=False)
    combined = " ".join(lims).lower()
    assert "neutrino" in combined


# ── Input-type specific ───────────────────────────────────────────────────────

def test_topic_input_adds_illustrative_warning():
    lims = _lims(input_type="topic")
    combined = " ".join(lims).lower()
    assert "illustrative" in combined or "topic" in combined


def test_query_input_adds_interpreted_warning():
    lims = _lims(input_type="query")
    combined = " ".join(lims).lower()
    assert "interpret" in combined or "query" in combined or "free-form" in combined


def test_research_input_no_extra_warning():
    lims_r = _lims(input_type="research")
    lims_t = _lims(input_type="topic")
    # Topic should have more limitations than research.
    assert len(lims_t) >= len(lims_r)


# ── Circuit quality flags ─────────────────────────────────────────────────────

def test_not_theoretically_correct_adds_warning():
    lims = _lims(theoretically_correct=False)
    combined = " ".join(lims).lower()
    assert "correctness" in combined or "theoretically" in combined


def test_theoretically_correct_no_extra_warning():
    lims_ok  = _lims(theoretically_correct=True)
    lims_bad = _lims(theoretically_correct=False)
    assert len(lims_bad) > len(lims_ok)


def test_not_quantum_application_adds_warning():
    lims = _lims(is_quantum_application=False)
    combined = " ".join(lims).lower()
    assert "classical" in combined or "quantum application" in combined or "quantum hardware" in combined


def test_low_ai_confidence_adds_warning():
    lims = _lims(ai_confidence=0.50)
    combined = " ".join(lims).lower()
    assert "confidence" in combined or "extend" in combined


def test_high_ai_confidence_no_warning():
    lims_high = _lims(ai_confidence=0.90)
    lims_low  = _lims(ai_confidence=0.50)
    assert len(lims_low) > len(lims_high)
