"""
AI-driven quantum circuit builder.

Uses Claude (claude-opus-4-7) when ANTHROPIC_API_KEY is set.
Falls back to heuristic generation when the key is absent or the call fails.

Follows the workflow diagram:
  1. build(research)        → produces a QuantumCircuit (QASM string)
  2. check_theoretical()    → validates the circuit conceptually
  3. is_quantum_application → determines if this constitutes a full QApp
  4. extend(circuit, result) → builds a new, improved circuit on prior results
"""

import json
import math
import os
import re
from dataclasses import dataclass, field

try:
    import anthropic as _anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

_MODEL = "claude-opus-4-7"

_CLASSICAL_SYSTEM = """\
You are a computer science expert. Given a research title and equations, \
explain why this problem does not need quantum computing and suggest the \
best classical approach.

Respond with ONLY a JSON object — no prose, no markdown fences:
{
  "reason": "<one sentence: why quantum hardware adds no advantage here>",
  "approach": "<name of the recommended classical method>",
  "libraries": ["<lib1>", "<lib2>"],
  "example_sketch": "<concise Python code sketch, 8-15 lines>",
  "documentation_links": ["<url1>", "<url2>"]
}
"""

_SYSTEM_RESEARCH = """\
You are a quantum computing expert. Given a research title and equations, \
generate a valid OpenQASM 3.0 quantum circuit that encodes the mathematical \
structure of the equations, then assess it.

Respond with ONLY a JSON object — no prose, no markdown fences:
{
  "qasm": "<full OpenQASM 3.0 circuit string>",
  "theoretically_correct": true|false,
  "is_quantum_application": true|false,
  "ai_confidence": <float 0.0-1.0>,
  "notes": "<brief explanation of how the circuit encodes the equations>",
  "n_qubits": <int>,
  "gates": [<gate name strings>]
}

Rules:
- Use OPENQASM 3.0; include "stdgates.inc";
- Include qubit and bit declarations, gate operations, and a measurement.
- theoretically_correct: true only if the circuit is well-formed and the \
  gates reflect the equations.
- is_quantum_application: true if the circuit gives a genuine quantum \
  advantage over a classical approach.
- ai_confidence: your confidence in the generated circuit (0.0–1.0).
"""

_SYSTEM_TOPIC = """\
You are a quantum computing expert. Given a domain keyword (e.g. \
"cryptography", "optimization", "chemistry"), generate a canonical \
illustrative OpenQASM 3.0 circuit for the most well-known quantum \
algorithm in that domain, then assess it.

Respond with ONLY a JSON object — no prose, no markdown fences:
{
  "qasm": "<full OpenQASM 3.0 circuit string>",
  "algorithm_name": "<e.g. Shor's Algorithm, QAOA, VQE, Grover's Search>",
  "theoretically_correct": true|false,
  "is_quantum_application": true|false,
  "ai_confidence": <float 0.0-1.0>,
  "notes": "<which algorithm this represents and why it suits the topic>",
  "n_qubits": <int>,
  "gates": [<gate name strings>]
}

Rules:
- Use OPENQASM 3.0; include "stdgates.inc";
- Include qubit and bit declarations, gate operations, and a measurement.
- Pick the algorithm most strongly associated with the topic.
- is_quantum_application: true if a quantum speedup exists for this domain.
- ai_confidence: your confidence in the circuit's correctness (0.0–1.0).
"""

_SYSTEM_QUERY = """\
You are a quantum computing expert. The user has asked a free-form question \
or given an instruction about quantum circuits. Interpret their intent and \
generate the most appropriate OpenQASM 3.0 circuit that answers or \
demonstrates it.

Respond with ONLY a JSON object — no prose, no markdown fences:
{
  "qasm": "<full OpenQASM 3.0 circuit string>",
  "interpretation": "<one sentence: how you interpreted the query>",
  "theoretically_correct": true|false,
  "is_quantum_application": true|false,
  "ai_confidence": <float 0.0-1.0>,
  "notes": "<what the circuit does and any caveats>",
  "n_qubits": <int>,
  "gates": [<gate name strings>]
}

Rules:
- Use OPENQASM 3.0; include "stdgates.inc";
- Include qubit and bit declarations, gate operations, and a measurement.
- If the query cannot be meaningfully expressed as a quantum circuit, set \
  is_quantum_application to false and explain in notes.
- ai_confidence: your confidence in the circuit matching the user's intent \
  (0.0–1.0).
"""

# Legacy alias used internally — default to research prompt.
_SYSTEM_PROMPT = _SYSTEM_RESEARCH


@dataclass
class CircuitResult:
    qasm:                   str
    metadata:               dict = field(default_factory=dict)
    theoretically_correct:  bool = False
    is_quantum_application: bool = False
    ai_confidence:          float = 0.0
    notes:                  str = ""
    # topic inputs: name of the canonical algorithm generated
    algorithm_name:         str = ""
    # query inputs: one-sentence description of how the query was interpreted
    interpretation:         str = ""


# ─── Public API ───────────────────────────────────────────────────────────────

def build_circuit(title: str, equations: str,
                  prior_qasm: str | None = None,
                  input_type: str = "research") -> CircuitResult:
    """
    Build a quantum circuit.

    input_type controls how the AI interprets the input:
      "research" — title + equations encode a formal research problem
      "topic"    — title is a domain keyword (e.g. "cryptography")
      "query"    — title is a free-form question or instruction

    Uses Claude when ANTHROPIC_API_KEY is set; falls back to heuristics otherwise.
    `prior_qasm` triggers extension mode (build upon existing results).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key and _HAS_ANTHROPIC:
        try:
            return _build_with_claude(title, equations, prior_qasm, api_key, input_type)
        except Exception as exc:
            print(f"[ai_circuit] Claude call failed ({exc}); falling back to heuristics.")

    return _build_heuristic(title, equations, prior_qasm)


def extend_circuit(prior_qasm: str, result_counts: dict,
                   title: str, equations: str) -> CircuitResult:
    """Build upon an existing circuit using the outcome of a prior run."""
    return build_circuit(title, equations, prior_qasm=prior_qasm)


def suggest_classical_approach(title: str, equations: str) -> dict:
    """
    When a circuit is flagged as not a quantum application, suggest how the
    same problem can be solved on a regular computer.

    Uses Claude when ANTHROPIC_API_KEY is set; falls back to keyword heuristics.
    Returns a dict with keys: reason, approach, libraries, example_sketch,
    documentation_links.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key and _HAS_ANTHROPIC:
        try:
            return _suggest_classical_with_claude(title, equations, api_key)
        except Exception as exc:
            print(f"[ai_circuit] Classical suggestion via Claude failed ({exc}); using heuristic.")
    return _suggest_classical_heuristic(title, equations)


# ─── Claude backend ───────────────────────────────────────────────────────────

_INPUT_TYPE_SYSTEM = {
    "research": _SYSTEM_RESEARCH,
    "topic":    _SYSTEM_TOPIC,
    "query":    _SYSTEM_QUERY,
}

_INPUT_TYPE_USER_PREFIX = {
    "research": lambda t, eq: f"Research title: {t}\n\nEquations:\n{eq or '(none provided)'}",
    "topic":    lambda t, _:  f"Topic / domain keyword: {t}",
    "query":    lambda t, eq: f"Query: {t}" + (f"\n\nAdditional context:\n{eq}" if eq else ""),
}


def _build_with_claude(title: str, equations: str,
                       prior_qasm: str | None, api_key: str,
                       input_type: str = "research") -> CircuitResult:
    client = _anthropic.Anthropic(api_key=api_key)

    prefix_fn    = _INPUT_TYPE_USER_PREFIX.get(input_type, _INPUT_TYPE_USER_PREFIX["research"])
    user_content = prefix_fn(title, equations)
    if prior_qasm:
        user_content += f"\n\nExtend this existing circuit (add layers before the final measurement):\n{prior_qasm}"

    system_prompt = _INPUT_TYPE_SYSTEM.get(input_type, _SYSTEM_RESEARCH)

    with client.messages.stream(
        model=_MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        message = stream.get_final_message()

    raw = ""
    for block in message.content:
        if block.type == "text":
            raw = block.text.strip()
            break

    # Strip accidental markdown fences if Claude added them.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    data = json.loads(raw)

    return CircuitResult(
        qasm                   = data["qasm"],
        metadata               = {"n_qubits": data.get("n_qubits", 2),
                                  "gates":    data.get("gates", [])},
        theoretically_correct  = bool(data.get("theoretically_correct", False)),
        is_quantum_application = bool(data.get("is_quantum_application", False)),
        ai_confidence          = float(data.get("ai_confidence", 0.0)),
        notes                  = data.get("notes", ""),
        algorithm_name         = data.get("algorithm_name", ""),
        interpretation         = data.get("interpretation", ""),
    )


# ─── Classical suggestion: Claude ────────────────────────────────────────────

def _suggest_classical_with_claude(title: str, equations: str, api_key: str) -> dict:
    client = _anthropic.Anthropic(api_key=api_key)
    user_content = (
        f"Research title: {title}\n\nEquations:\n{equations or '(none provided)'}"
    )
    with client.messages.stream(
        model=_MODEL,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=_CLASSICAL_SYSTEM,
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

    return json.loads(raw)


# ─── Classical suggestion: heuristic ─────────────────────────────────────────

def _suggest_classical_heuristic(title: str, equations: str) -> dict:
    text = (title + " " + (equations or "")).lower()

    if any(k in text for k in ["optimiz", "minimiz", "maximiz", "gradient", "loss"]):
        return {
            "reason": "Optimization over a smooth or well-structured landscape has no quantum advantage at this scale.",
            "approach": "Gradient-based or metaheuristic optimization",
            "libraries": ["scipy.optimize", "optuna", "pyomo"],
            "example_sketch": (
                "from scipy.optimize import minimize\n"
                "import numpy as np\n\n"
                "def objective(x):\n"
                "    return x[0]**2 + x[1]**2  # replace with your function\n\n"
                "result = minimize(objective, x0=[1.0, 1.0], method='L-BFGS-B')\n"
                "print('Optimal x:', result.x)\n"
                "print('Minimum value:', result.fun)"
            ),
            "documentation_links": [
                "https://docs.scipy.org/doc/scipy/reference/optimize.html",
                "https://optuna.readthedocs.io/",
            ],
        }

    if any(k in text for k in ["matrix", "linear", "eigen", "svd", "decompos", "determinant"]):
        return {
            "reason": "Linear algebra operations on matrices of this size are highly efficient on classical hardware.",
            "approach": "Numerical linear algebra with NumPy / SciPy",
            "libraries": ["numpy", "scipy.linalg"],
            "example_sketch": (
                "import numpy as np\n"
                "from scipy.linalg import eig, svd\n\n"
                "A = np.array([[2, 1], [1, 3]])  # replace with your matrix\n\n"
                "eigenvalues, eigenvectors = eig(A)\n"
                "print('Eigenvalues:', eigenvalues)\n\n"
                "U, s, Vh = svd(A)\n"
                "print('Singular values:', s)"
            ),
            "documentation_links": [
                "https://numpy.org/doc/stable/reference/routines.linalg.html",
                "https://docs.scipy.org/doc/scipy/reference/linalg.html",
            ],
        }

    if any(k in text for k in ["graph", "network", "path", "search", "sort", "tree", "route"]):
        return {
            "reason": "Graph traversal and path-finding algorithms are well-solved in classical computer science.",
            "approach": "Classical graph algorithms with NetworkX",
            "libraries": ["networkx", "heapq", "collections"],
            "example_sketch": (
                "import networkx as nx\n\n"
                "G = nx.Graph()\n"
                "G.add_weighted_edges_from([(0, 1, 1.5), (1, 2, 2.0), (0, 2, 4.0)])\n\n"
                "path = nx.shortest_path(G, source=0, target=2, weight='weight')\n"
                "print('Shortest path:', path)\n\n"
                "print('All pairs shortest paths:')\n"
                "for p in nx.all_pairs_shortest_path(G):\n"
                "    print(p)"
            ),
            "documentation_links": [
                "https://networkx.org/documentation/stable/reference/algorithms/",
            ],
        }

    if any(k in text for k in ["simulate", "monte carlo", "stochastic", "random", "probab", "distribution"]):
        return {
            "reason": "Probabilistic simulation scales well classically and does not benefit from quantum superposition here.",
            "approach": "Monte Carlo simulation with NumPy / SciPy",
            "libraries": ["numpy", "scipy.stats", "simpy"],
            "example_sketch": (
                "import numpy as np\n"
                "from scipy import stats\n\n"
                "rng = np.random.default_rng(seed=42)\n"
                "N = 1_000_000\n\n"
                "# Example: estimate π via Monte Carlo\n"
                "x, y = rng.uniform(-1, 1, N), rng.uniform(-1, 1, N)\n"
                "pi_estimate = 4 * np.sum(x**2 + y**2 <= 1) / N\n"
                "print('π ≈', pi_estimate)"
            ),
            "documentation_links": [
                "https://numpy.org/doc/stable/reference/random/",
                "https://docs.scipy.org/doc/scipy/reference/stats.html",
            ],
        }

    if any(k in text for k in ["learn", "classify", "predict", "neural", "regression", "cluster"]):
        return {
            "reason": "Classical machine learning algorithms are mature and well-optimized for this class of problem.",
            "approach": "Classical machine learning with scikit-learn or PyTorch",
            "libraries": ["scikit-learn", "torch", "pandas"],
            "example_sketch": (
                "from sklearn.ensemble import RandomForestClassifier\n"
                "from sklearn.model_selection import train_test_split\n"
                "from sklearn.metrics import accuracy_score\n\n"
                "X_train, X_test, y_train, y_test = train_test_split(\n"
                "    X, y, test_size=0.2, random_state=42)\n\n"
                "clf = RandomForestClassifier(n_estimators=100, random_state=42)\n"
                "clf.fit(X_train, y_train)\n"
                "print('Accuracy:', accuracy_score(y_test, clf.predict(X_test)))"
            ),
            "documentation_links": [
                "https://scikit-learn.org/stable/user_guide.html",
                "https://pytorch.org/tutorials/",
            ],
        }

    if any(k in text for k in ["differential", "integral", "ode", "pde", "equation", "numerical"]):
        return {
            "reason": "Numerical solvers for differential equations are highly efficient on classical hardware.",
            "approach": "Numerical integration / ODE solving with SciPy",
            "libraries": ["scipy.integrate", "numpy", "matplotlib"],
            "example_sketch": (
                "from scipy.integrate import solve_ivp\n"
                "import numpy as np\n\n"
                "def system(t, y):\n"
                "    return [-y[0] + y[1], -2 * y[1]]  # replace with your equations\n\n"
                "sol = solve_ivp(system, t_span=[0, 10], y0=[1.0, 0.5],\n"
                "                dense_output=True)\n"
                "t = np.linspace(0, 10, 300)\n"
                "print(sol.sol(t))"
            ),
            "documentation_links": [
                "https://docs.scipy.org/doc/scipy/reference/integrate.html",
            ],
        }

    # Generic fallback
    return {
        "reason": "The problem structure does not exhibit the superposition, entanglement, or interference properties that give quantum computers an advantage.",
        "approach": "General-purpose classical computation with NumPy and SciPy",
        "libraries": ["numpy", "scipy", "pandas"],
        "example_sketch": (
            "import numpy as np\n"
            "import scipy\n\n"
            "# Implement your equations using standard numerical methods.\n"
            "# numpy arrays for vectorized math.\n"
            "# scipy for integration, optimization, and signal processing.\n\n"
            "# Example: evaluate an expression over a range\n"
            "x = np.linspace(0, 10, 1000)\n"
            "y = np.sin(x) * np.exp(-0.1 * x)  # replace with your equation\n"
            "print('Result range:', y.min(), 'to', y.max())"
        ),
        "documentation_links": [
            "https://numpy.org/doc/stable/",
            "https://docs.scipy.org/doc/scipy/",
        ],
    }


# ─── Heuristic fallback ───────────────────────────────────────────────────────

def _build_heuristic(title: str, equations: str,
                     prior_qasm: str | None) -> CircuitResult:
    n_qubits, gates = _analyze_equations(equations)

    if prior_qasm:
        qasm  = _extend_qasm(prior_qasm, gates)
        notes = "Extended from prior circuit (heuristic fallback)."
    else:
        qasm  = _generate_qasm(n_qubits, gates)
        notes = "New circuit generated from equations (heuristic fallback)."

    correct, confidence = _check_theoretical(qasm, equations)
    is_app              = _is_quantum_application(qasm, title)

    return CircuitResult(
        qasm                   = qasm,
        metadata               = {"n_qubits": n_qubits, "gates": gates},
        theoretically_correct  = correct,
        is_quantum_application = is_app,
        ai_confidence          = confidence,
        notes                  = notes,
    )


def _analyze_equations(equations: str) -> tuple[int, list[str]]:
    if not equations:
        return 2, ["h", "cx"]

    variables = set(re.findall(r'\b[a-zA-Z]\b', equations))
    n_qubits  = max(2, min(len(variables), 10))

    gates = ["h"]
    if "∑" in equations or "sum" in equations.lower():
        gates.append("qft")
    if "×" in equations or "*" in equations or "·" in equations:
        gates.append("cx")
    if "²" in equations or "^2" in equations or "**2" in equations:
        gates.append("ccx")
    if "sin" in equations or "cos" in equations:
        gates.append("ry")
    if not any(g in gates for g in ("cx", "ccx")):
        gates.append("cx")

    return n_qubits, gates


def _generate_qasm(n_qubits: int, gates: list[str]) -> str:
    lines = [
        "OPENQASM 3.0;",
        'include "stdgates.inc";',
        f"qubit[{n_qubits}] q;",
        f"bit[{n_qubits}] c;",
    ]

    for i in range(n_qubits):
        lines.append(f"h q[{i}];")

    if "cx" in gates or "ccx" in gates:
        for i in range(n_qubits - 1):
            lines.append(f"cx q[{i}], q[{i+1}];")

    if "ry" in gates:
        angle = round(math.pi / 4, 6)
        for i in range(n_qubits):
            lines.append(f"ry({angle}) q[{i}];")

    if "ccx" in gates and n_qubits >= 3:
        lines.append("ccx q[0], q[1], q[2];")

    lines.append("c = measure q;")
    return "\n".join(lines)


def _extend_qasm(prior_qasm: str, new_gates: list[str]) -> str:
    lines         = prior_qasm.strip().splitlines()
    measure_lines = [l for l in lines if l.strip().startswith("c =")]
    body          = [l for l in lines if not l.strip().startswith("c =")]

    n_qubits = 2
    for l in lines:
        m = re.match(r'qubit\[(\d+)\]', l.strip())
        if m:
            n_qubits = int(m.group(1))
            break

    body.append("// --- extended layer ---")
    if "cx" in new_gates:
        for i in range(n_qubits - 1):
            body.append(f"cx q[{i}], q[{i+1}];")
    if "ry" in new_gates:
        angle = round(math.pi / 8, 6)
        for i in range(n_qubits):
            body.append(f"ry({angle}) q[{i}];")

    return "\n".join(body + measure_lines)


def _check_theoretical(qasm: str, equations: str) -> tuple[bool, float]:
    issues = 0
    if "OPENQASM" not in qasm:
        issues += 1
    if "measure" not in qasm and "c =" not in qasm:
        issues += 1
    if "qubit" not in qasm:
        issues += 1

    confidence = max(0.0, 1.0 - issues * 0.35)
    correct    = issues == 0
    return correct, round(confidence, 3)


def _is_quantum_application(qasm: str, title: str) -> bool:
    has_entanglement = "cx" in qasm or "ccx" in qasm or "cz" in qasm
    has_measurement  = "measure" in qasm or "c =" in qasm
    app_keywords     = {"application", "app", "system", "platform", "solver", "optimizer"}
    title_is_app     = any(kw in title.lower() for kw in app_keywords)
    return has_entanglement and has_measurement and title_is_app
