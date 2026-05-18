"""
Hardware selector — ranks quantum backends by content suitability.

Priority order tried: electron → photonic → neutrino.
Returns (None, reason) when no backend scores above the threshold, signalling
that classical computing should be recommended instead.

Uses Claude when ANTHROPIC_API_KEY is set; keyword heuristics otherwise.
"""

import json
import os
import re

try:
    import anthropic as _anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

_MODEL = "claude-opus-4-7"
_SUITABILITY_THRESHOLD = 0.35

_SYSTEM_PROMPT = """\
You are a quantum hardware expert. Given research input, rank three quantum
hardware paradigms by how well-suited they are for the problem.

Hardware paradigms:
- electron: Gate-based quantum computing (qubits, gates, circuits).
  Best for: quantum algorithms (Grover, Shor, VQE, QAOA), quantum ML,
  quantum chemistry, combinatorial optimisation, most standard QC work.
- photonic: Linear-optical / continuous-variable quantum computing.
  Best for: quantum communication, QKD, boson sampling, squeezed-state
  computation, quantum networking, optical quantum simulation.
- neutrino: Neutrino-based quantum systems (emerging research).
  Best for: high-energy particle physics, neutrino oscillation modelling,
  weak-force quantum effects, matter-antimatter asymmetry studies.

Respond with ONLY a JSON object — no prose, no markdown fences:
{
  "ranking": [
    {"type": "electron", "score": <0.0–1.0>, "reason": "<one sentence>"},
    {"type": "photonic", "score": <0.0–1.0>, "reason": "<one sentence>"},
    {"type": "neutrino", "score": <0.0–1.0>, "reason": "<one sentence>"}
  ],
  "recommend_classical": <true if all scores < 0.35>,
  "notes": "<one-sentence overall assessment>"
}
"""

# ── Public API ─────────────────────────────────────────────────────────────────

def rank_hardware(title: str, equations: str,
                  input_type: str = "research") -> list[dict]:
    """
    Return [{"type", "score", "reason"}, ...] sorted by descending score.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key and _HAS_ANTHROPIC:
        try:
            return _rank_with_claude(title, equations, input_type, api_key)
        except Exception as exc:
            print(f"[hardware_selector] Claude failed ({exc}); using heuristic.")
    return _rank_heuristic(title, equations)


def select_hardware(title: str, equations: str,
                    input_type: str = "research") -> tuple[str | None, str]:
    """
    Try electron → photonic → neutrino in fixed priority order.
    Returns (hardware_type, reason) for the first suitable backend,
    or (None, reason) if none score above the threshold.
    """
    ranking = rank_hardware(title, equations, input_type)
    score_map = {item["type"]: item for item in ranking}

    for hw_type in ("electron", "photonic", "neutrino"):
        item = score_map.get(hw_type, {})
        if item.get("score", 0.0) >= _SUITABILITY_THRESHOLD:
            return hw_type, item.get("reason", f"Suitable for {hw_type}-based quantum computing.")

    return None, (
        "No quantum hardware type provides a meaningful advantage for this problem. "
        "Classical computing is recommended."
    )


def full_ranking(title: str, equations: str,
                 input_type: str = "research") -> dict:
    """
    Full ranking dict for API responses, including classical recommendation flag.
    """
    ranking = rank_hardware(title, equations, input_type)
    any_suitable = any(item.get("score", 0) >= _SUITABILITY_THRESHOLD for item in ranking)
    return {
        "ranking":             ranking,
        "recommend_classical": not any_suitable,
    }


# ── Claude backend ─────────────────────────────────────────────────────────────

def _rank_with_claude(title: str, equations: str,
                      input_type: str, api_key: str) -> list[dict]:
    client = _anthropic.Anthropic(api_key=api_key)
    user_content = (
        f"Input type: {input_type}\n"
        f"Title: {title}\n"
        f"Equations / context: {equations or '(none)'}"
    )
    with client.messages.stream(
        model=_MODEL,
        max_tokens=512,
        thinking={"type": "adaptive"},
        system=_SYSTEM_PROMPT,
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

    data = json.loads(raw)
    return sorted(data["ranking"], key=lambda x: x["score"], reverse=True)


# ── Heuristic backend ─────────────────────────────────────────────────────────

_ELECTRON_KW = {
    "quantum", "qubit", "gate", "circuit", "entanglement", "superposition",
    "algorithm", "hamiltonian", "grover", "shor", "vqe", "qaoa", "variational",
    "optimization", "optimisation", "chemistry", "cryptography", "factoring",
    "simulation", "annealing", "phase estimation", "amplitude", "interference",
    "oracle", "quantum walk", "quantum ml", "quantum advantage", "quantum search",
    "pauli", "unitary", "ansatz", "eigenvalue", "bloch sphere",
}
_PHOTONIC_KW = {
    "photon", "optical", "optics", "laser", "light", "boson", "gaussian",
    "squeezed", "coherent", "homodyne", "heterodyne", "fiber", "waveguide",
    "beam splitter", "quantum communication", "qkd", "key distribution",
    "quantum network", "linear optics", "continuous variable", "teleportation",
    "entanglement distribution", "quantum repeater", "photonic", "polarization",
    "interferometer", "mach-zehnder",
}
_NEUTRINO_KW = {
    "neutrino", "oscillation", "lepton", "flavor", "mixing angle",
    "particle physics", "standard model", "nuclear", "weak interaction",
    "muon", "dark matter", "reactor", "atmospheric", "solar neutrino",
    "mass eigenstate", "pmns", "pontecorvo", "mns matrix", "neutrino flux",
    "antineutrino", "electron neutrino", "muon neutrino", "tau neutrino",
}


def _kw_score(text: str, keywords: set) -> float:
    t = text.lower()
    hits = sum(1 for kw in keywords if kw in t)
    return min(hits / max(len(keywords) * 0.12, 1), 1.0)


def _rank_heuristic(title: str, equations: str) -> list[dict]:
    text = f"{title} {equations or ''}"

    e = min(_kw_score(text, _ELECTRON_KW) + 0.10, 1.0)   # small base boost
    p = _kw_score(text, _PHOTONIC_KW)
    n = _kw_score(text, _NEUTRINO_KW)

    ranking = [
        {"type": "electron", "score": round(e, 3),
         "reason": "Keyword analysis suggests gate-based quantum computing."},
        {"type": "photonic", "score": round(p, 3),
         "reason": "Keyword analysis suggests linear-optical quantum computing."},
        {"type": "neutrino", "score": round(n, 3),
         "reason": "Keyword analysis suggests neutrino-based quantum physics."},
    ]
    return sorted(ranking, key=lambda x: x["score"], reverse=True)
