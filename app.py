"""
QuApp Labs (Quantum Applications Laboratory) — Flask application entry point.
CONFIDENTIAL: Do not deploy or publish without explicit authorization.

All routes require a valid JWT (Bearer token from POST /api/auth/login).
Results are NEVER public until an admin calls POST /api/results/<id>/approve.
"""

import json
import os

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity, get_jwt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from models import db, User
from auth import (
    login, logout, is_token_revoked, audit,
    admin_required, researcher_required, hash_password,
)
import research as wf

_HERE = os.path.dirname(os.path.abspath(__file__))


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── CORS (allow local HTML file and localhost) ────────────────────────────
    CORS(app, resources={r"/api/*": {
        "origins": ["http://localhost", "http://127.0.0.1",
                    "http://localhost:*", "http://127.0.0.1:*",
                    "null"],          # null = file:// origin
        "supports_credentials": False,
    }})

    # ── Extensions ────────────────────────────────────────────────────────────
    db.init_app(app)
    jwt = JWTManager(app)
    limiter = Limiter(get_remote_address, app=app, default_limits=["200 per hour"])

    with app.app_context():
        db.create_all()

    # ── JWT token revocation check ────────────────────────────────────────────
    @jwt.token_in_blocklist_loader
    def check_if_revoked(jwt_header, jwt_payload):
        return is_token_revoked(jwt_payload)

    @jwt.revoked_token_loader
    def revoked_response(jwt_header, jwt_payload):
        return jsonify({"error": "Token has been revoked. Please log in again."}), 401

    @jwt.expired_token_loader
    def expired_response(jwt_header, jwt_payload):
        return jsonify({"error": "Token has expired. Please log in again."}), 401

    @jwt.unauthorized_loader
    def missing_token_response(reason):
        return jsonify({"error": "Authentication required.", "detail": reason}), 401

    # =========================================================================
    # AUTH
    # =========================================================================

    @app.route("/api/auth/login", methods=["POST"])
    @limiter.limit("10 per minute")
    def api_login():
        """
        POST /api/auth/login
        Body: {"id": "...", "password": "..."}
        Returns: {"access_token": "...", "refresh_token": "..."}
        """
        body = request.get_json(silent=True) or {}
        user_id  = body.get("id",       "").strip()
        password = body.get("password", "")

        if not user_id or not password:
            return jsonify({"error": "id and password are required"}), 400

        tokens, err = login(user_id, password)
        if err:
            return jsonify({"error": err}), 401
        return jsonify(tokens), 200

    @app.route("/api/auth/logout", methods=["POST"])
    @jwt_required()
    def api_logout():
        """POST /api/auth/logout — revokes the current access token."""
        logout()
        return jsonify({"message": "Logged out successfully"}), 200

    @app.route("/api/auth/me", methods=["GET"])
    @jwt_required()
    def api_me():
        user = User.query.get(get_jwt_identity())
        if not user:
            return jsonify({"error": "User not found"}), 404
        return jsonify(user.to_public_dict()), 200

    # ── Admin: create user (bootstrap only) ───────────────────────────────────
    @app.route("/api/auth/signup", methods=["POST"])
    @limiter.limit("5 per minute")
    def api_signup():
        """
        POST /api/auth/signup
        Body: {"name": "...", "id": "...", "email": "...", "password": "..."}
        Creates a researcher account and returns JWT tokens (auto-login).
        Signup is open; role is always 'researcher' — never admin.
        """
        import re as _re
        body     = request.get_json(silent=True) or {}
        name     = body.get("name",     "").strip()
        user_id  = body.get("id",       "").strip()
        email    = body.get("email",    "").strip().lower()
        password = body.get("password", "")

        # ── Field-level validation ────────────────────────────────────────────
        if not all([name, user_id, email, password]):
            return jsonify({"error": "All fields (name, id, email, password) are required"}), 400
        if len(name) > 100:
            return jsonify({"error": "Name must be 100 characters or fewer"}), 400
        if not _re.match(r'^[a-zA-Z0-9_\-]{3,50}$', user_id):
            return jsonify({
                "error": "User ID must be 3–50 characters: letters, numbers, _ or - only"
            }), 400
        if not _re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            return jsonify({"error": "Invalid email address"}), 400
        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400
        if len(password) > 128:
            return jsonify({"error": "Password is too long (max 128 characters)"}), 400

        # ── Uniqueness checks ─────────────────────────────────────────────────
        if User.query.get(user_id):
            return jsonify({"error": "User ID is already taken"}), 409
        if User.query.filter_by(email=email).first():
            return jsonify({"error": "Email is already registered"}), 409

        # ── Create user ───────────────────────────────────────────────────────
        user = User(
            id            = user_id,
            name          = name,
            email         = email,
            password_hash = hash_password(password),
            role          = "researcher",     # signup never grants admin
        )
        db.session.add(user)
        db.session.commit()
        audit(user_id, "SIGNUP", "user", user_id, {"name": name, "email": email})

        # Auto-login: issue tokens so the client is signed in immediately.
        tokens, err = login(user_id, password)
        if err:
            # Unlikely, but fall back gracefully.
            return jsonify({"message": "Account created. Please sign in.", "user_id": user_id}), 201

        return jsonify({
            "message": "Account created successfully",
            "user": user.to_public_dict(),
            **tokens,
        }), 201

    @app.route("/api/auth/users", methods=["POST"])
    @admin_required
    def api_create_user():
        """POST /api/auth/users — admin only."""
        body     = request.get_json(silent=True) or {}
        user_id  = body.get("id",       "").strip()
        password = body.get("password", "")
        role     = body.get("role",     "researcher")

        if not user_id or not password:
            return jsonify({"error": "id and password are required"}), 400
        if role not in ("admin", "researcher", "viewer"):
            return jsonify({"error": "Invalid role"}), 400
        if User.query.get(user_id):
            return jsonify({"error": "User already exists"}), 409

        user = User(id=user_id, password_hash=hash_password(password), role=role)
        db.session.add(user)
        db.session.commit()
        audit(get_jwt_identity(), "USER_CREATED", "user", user_id)
        return jsonify({"message": f"User {user_id} created", "role": role}), 201

    # =========================================================================
    # RESEARCH  (Step 2 → 4 in workflow)
    # =========================================================================

    @app.route("/api/research", methods=["POST"])
    @researcher_required
    def api_submit_research():
        """
        POST /api/research
        Body:
          {
            "input_type": "research" | "topic" | "query",   // default: "research"
            "title":      "...",   // research title, topic keyword, or question
            "equations":  "..."    // optional for topic/query inputs
          }

        input_type values:
          "research" — formal research with title + equations (full workflow)
          "topic"    — domain keyword, e.g. "cryptography" or "optimization"
                       (generates a canonical circuit for that domain)
          "query"    — free-form question, e.g. "How does a Bell state work?"
                       (AI interprets and builds the most appropriate circuit)

        Creates research entry, stores in DB1, awards ILP tokens.
        """
        body       = request.get_json(silent=True) or {}
        user_id    = get_jwt_identity()
        title      = body.get("title",      "").strip()
        equations  = body.get("equations",  "").strip() or None
        input_type = body.get("input_type", "research").strip()

        r, err = wf.submit_research(user_id, title, equations, input_type)
        if err:
            return jsonify({"error": err}), 400

        audit(user_id, "RESEARCH_SUBMITTED", "research", r.id,
              {"input_type": input_type})
        return jsonify({"research": r.to_dict()}), 201

    @app.route("/api/research/<research_id>", methods=["GET"])
    @jwt_required()
    def api_get_research(research_id):
        from models import Research
        r = Research.query.get(research_id)
        if not r:
            return jsonify({"error": "Not found"}), 404
        user_id = get_jwt_identity()
        user    = User.query.get(user_id)
        if r.user_id != user_id and not user.is_admin():
            return jsonify({"error": "Access denied"}), 403
        return jsonify({"research": r.to_dict()}), 200

    @app.route("/api/research/<research_id>/novelty", methods=["POST"])
    @researcher_required
    def api_check_novelty(research_id):
        """
        POST /api/research/<id>/novelty
        Runs novelty check.

        Novel     → issues Novelty Tokens, stores in RD.
                    Response: {is_novel: true, novelty_score, next_step: "select_hardware"}

        Not novel → retrieves the most recent correct circuit from the RD to
                    build upon. Response includes prior_circuit_id so the caller
                    can pass it straight to POST /api/quantum/experiments/<id>/circuit.
                    Response: {is_novel: false, novelty_score, prior_circuit_id,
                               next_step: "build_circuit"}
        """
        from models import Research
        r = Research.query.get(research_id)
        if not r:
            return jsonify({"error": "Not found"}), 404
        if r.user_id != get_jwt_identity():
            return jsonify({"error": "Access denied"}), 403

        is_novel, score, prior_circuit_id, assessment = wf.check_novelty(research_id)

        # Hardware suitability pre-check (runs alongside novelty in this phase).
        from models import Research as _Research
        from quantum.hardware_selector import full_ranking
        _r    = _Research.query.get(research_id)
        hw_rec = full_ranking(
            _r.title, _r.equations or "", _r.input_type
        ) if _r else {}

        audit(get_jwt_identity(), "NOVELTY_CHECKED", "research", research_id,
              {"is_novel": is_novel, "score": score,
               "prior_circuit_id": prior_circuit_id})

        response = {
            "is_novel":               is_novel,
            "novelty_score":          score,
            "assessment":             assessment,
            "hardware_recommendation": hw_rec,
        }
        if is_novel:
            response["next_step"] = "select_hardware"
        else:
            response["next_step"]        = "build_circuit"
            response["prior_circuit_id"] = prior_circuit_id
            response["message"] = (
                "Research is not novel. Use prior_circuit_id as the starting "
                "point when calling POST /api/quantum/experiments/<id>/circuit."
                if prior_circuit_id else
                "Research is not novel but no prior circuit exists yet. "
                "Proceed with hardware selection and build a new circuit."
            )
        return jsonify(response), 200

    # =========================================================================
    # QUANTUM EXPERIMENTS  (Steps 5 → 11)
    # =========================================================================

    @app.route("/api/quantum/hardware", methods=["GET"])
    @jwt_required()
    def api_hardware_list():
        """GET /api/quantum/hardware — list available backends and their status."""
        from quantum import BACKENDS
        result = {}
        for hw, cls in BACKENDS.items():
            backend = cls()
            result[hw] = {"available": backend.available}
        return jsonify({"hardware": result}), 200

    @app.route("/api/quantum/experiments", methods=["POST"])
    @researcher_required
    def api_create_experiment():
        """
        POST /api/quantum/experiments
        Body: {
          "research_id":   "...",
          "hardware_type": "electron|photonic|neutrino"  // optional
        }

        If hardware_type is omitted the system auto-selects by trying
        electron → photonic → neutrino in priority order based on the
        research content. If none are suitable, is_suitable=false and
        a classical_suggestion is included in the response.
        """
        body          = request.get_json(silent=True) or {}
        user_id       = get_jwt_identity()
        research_id   = body.get("research_id", "")
        hardware_type = body.get("hardware_type", "").strip() or None

        exp, is_suitable, reason = wf.select_hardware_and_check(
            research_id, hardware_type, user_id
        )
        if exp is None:
            return jsonify({"error": reason}), 400

        selected_hw = exp.hardware_type
        audit(user_id, "EXPERIMENT_CREATED", "experiment", exp.id,
              {"hardware": selected_hw, "suitable": is_suitable,
               "auto_selected": hardware_type is None})

        from quantum.limitations import describe_limitations
        from quantum import get_backend as _get_hw
        from models import Research as _Research
        _r       = _Research.query.get(research_id)
        _backend = _get_hw(selected_hw)
        hw_limitations = describe_limitations(
            hardware_type     = selected_hw,
            backend_available = _backend.available,
            input_type        = _r.input_type if _r else "research",
        )

        resp_body = {
            "experiment":    exp.to_dict(),
            "is_suitable":   is_suitable,
            "reason":        reason,
            "limitations":   hw_limitations,
        }
        if hardware_type is None:
            resp_body["auto_selected_hardware"] = selected_hw

        # If nothing was suitable (auto-select fell through), add classical hint.
        if not is_suitable and _r:
            from quantum.ai_circuit import suggest_classical_approach
            resp_body["classical_suggestion"] = suggest_classical_approach(
                _r.title, _r.equations or ""
            )

        return jsonify(resp_body), 201

    @app.route("/api/quantum/experiments/<int:exp_id>/circuit", methods=["POST"])
    @researcher_required
    def api_build_circuit(exp_id):
        """
        POST /api/quantum/experiments/<id>/circuit
        Optional body: {"prior_circuit_id": <int>}  for the extend loop.
        AI builds (or extends) the quantum circuit.
        """
        body             = request.get_json(silent=True) or {}
        prior_circuit_id = body.get("prior_circuit_id")

        qc, err = wf.build_experiment_circuit(exp_id, prior_circuit_id)
        if err:
            return jsonify({"error": err}), 400

        audit(get_jwt_identity(), "CIRCUIT_BUILT", "circuit", qc.id,
              {"version": qc.version, "theoretically_correct": qc.theoretically_correct,
               "is_quantum_application": qc.is_quantum_application})

        from models import QuantumExperiment, Research
        from quantum.limitations import describe_limitations
        from quantum import get_backend as _get_backend
        exp = QuantumExperiment.query.get(exp_id)
        r   = Research.query.get(exp.research_id) if exp else None
        _backend = _get_backend(exp.hardware_type) if exp else None

        limitations = describe_limitations(
            hardware_type          = exp.hardware_type if exp else "electron",
            backend_available      = _backend.available if _backend else False,
            input_type             = r.input_type if r else "research",
            theoretically_correct  = qc.theoretically_correct,
            is_quantum_application = qc.is_quantum_application,
            ai_confidence          = qc.ai_confidence,
        )

        response = {
            "circuit_id":             qc.id,
            "version":                qc.version,
            "theoretically_correct":  qc.theoretically_correct,
            "is_quantum_application": qc.is_quantum_application,
            "ai_confidence":          qc.ai_confidence,
            "qasm_preview":           qc.circuit_qasm[:300],
            "limitations":            limitations,
        }

        # Surface algorithm name / query interpretation when present.
        meta = json.loads(qc.circuit_metadata or "{}")
        if meta.get("algorithm_name"):
            response["algorithm_name"] = meta["algorithm_name"]
        if meta.get("interpretation"):
            response["interpretation"] = meta["interpretation"]

        if not qc.is_quantum_application:
            from quantum.ai_circuit import suggest_classical_approach
            suggestion = suggest_classical_approach(
                r.title     if r else "",
                r.equations if r else "",
            )
            response["warning"] = (
                "This research does not appear to require quantum hardware. "
                "It can likely be solved more efficiently on a regular computer."
            )
            response["classical_suggestion"] = suggestion

        return jsonify(response), 201

    @app.route("/api/quantum/experiments/<int:exp_id>/run", methods=["POST"])
    @researcher_required
    def api_run_experiment(exp_id):
        """
        POST /api/quantum/experiments/<id>/run
        Body: {"circuit_id": <int>, "shots": 1024}
        Executes the circuit on the selected hardware backend.
        """
        body       = request.get_json(silent=True) or {}
        circuit_id = body.get("circuit_id")
        shots      = int(body.get("shots", 1024))

        if not circuit_id:
            return jsonify({"error": "circuit_id required"}), 400

        result, err = wf.run_experiment(exp_id, circuit_id, shots)
        if err:
            return jsonify({"error": err}), 400

        audit(get_jwt_identity(), "EXPERIMENT_RUN", "experiment", exp_id,
              {"reliability_score": result.reliability_score})

        return jsonify({
            "result_id":        result.id,
            "reliability_score": result.reliability_score,
            "reliability_passed": result.reliability_score >= 0.6,
        }), 200

    @app.route("/api/quantum/experiments/<int:exp_id>/extend", methods=["POST"])
    @researcher_required
    def api_extend_circuit(exp_id):
        """
        POST /api/quantum/experiments/<id>/extend
        Body: {"prior_circuit_id": <int>}
        'Build upon existing results and extend the Quantum Circuit' loop.
        """
        body             = request.get_json(silent=True) or {}
        prior_circuit_id = body.get("prior_circuit_id")
        if not prior_circuit_id:
            return jsonify({"error": "prior_circuit_id required"}), 400

        qc, err = wf.extend_experiment(exp_id, prior_circuit_id)
        if err:
            return jsonify({"error": err}), 400

        audit(get_jwt_identity(), "CIRCUIT_EXTENDED", "circuit", qc.id,
              {"version": qc.version})

        return jsonify({
            "circuit_id": qc.id,
            "version":    qc.version,
            "theoretically_correct":  qc.theoretically_correct,
            "is_quantum_application": qc.is_quantum_application,
        }), 201

    # =========================================================================
    # RESULTS & PUBLICATION  (Step 12 — gated behind admin approval)
    # =========================================================================

    @app.route("/api/results/<int:exp_id>/request-publication", methods=["POST"])
    @researcher_required
    def api_request_publication(exp_id):
        """
        POST /api/results/<id>/request-publication
        Researcher submits a request to make results public.
        An admin must separately call /approve before anything is visible.
        """
        ok, msg = wf.request_publication(exp_id, get_jwt_identity())
        if not ok:
            return jsonify({"error": msg}), 400
        audit(get_jwt_identity(), "PUBLICATION_REQUESTED", "experiment", exp_id)
        return jsonify({"message": msg}), 200

    @app.route("/api/results/<int:exp_id>/approve", methods=["POST"])
    @admin_required
    def api_approve_publication(exp_id):
        """
        POST /api/results/<id>/approve  — ADMIN ONLY.
        Makes experiment results publicly visible.
        Nothing is published without this step.
        """
        ok, msg = wf.approve_publication(exp_id, get_jwt_identity())
        if not ok:
            return jsonify({"error": msg}), 400
        audit(get_jwt_identity(), "PUBLICATION_APPROVED", "experiment", exp_id)
        return jsonify({"message": msg}), 200

    @app.route("/api/results/public", methods=["GET"])
    def api_public_results():
        """GET /api/results/public — only returns admin-approved public results."""
        from models import QuantumExperiment
        public_exps = QuantumExperiment.query.filter_by(results_public=True).all()
        return jsonify({"results": [e.to_dict() for e in public_exps]}), 200

    @app.route("/api/results/<int:exp_id>", methods=["GET"])
    @jwt_required()
    def api_get_result(exp_id):
        """GET /api/results/<id> — owner or admin only."""
        from models import QuantumExperiment
        exp = QuantumExperiment.query.get(exp_id)
        if not exp:
            return jsonify({"error": "Not found"}), 404
        user_id = get_jwt_identity()
        user    = User.query.get(user_id)
        if exp.user_id != user_id and not user.is_admin():
            return jsonify({"error": "Access denied"}), 403
        return jsonify({"experiment": exp.to_dict()}), 200

    # =========================================================================
    # ADMIN utilities
    # =========================================================================

    @app.route("/api/admin/audit-log", methods=["GET"])
    @admin_required
    def api_audit_log():
        from models import AuditLog
        limit  = min(int(request.args.get("limit",  100)), 500)
        offset = int(request.args.get("offset", 0))
        logs   = AuditLog.query.order_by(AuditLog.timestamp.desc())\
                               .limit(limit).offset(offset).all()
        return jsonify({"logs": [
            {"id": l.id, "user_id": l.user_id, "action": l.action,
             "resource": f"{l.resource_type}/{l.resource_id}",
             "ip": l.ip_address, "timestamp": l.timestamp.isoformat()}
            for l in logs
        ]}), 200

    @app.route("/api/admin/users", methods=["GET"])
    @admin_required
    def api_list_users():
        """GET /api/admin/users — admin only, list all users."""
        users = User.query.all()
        return jsonify({"users": [u.to_public_dict() for u in users]}), 200

    # =========================================================================
    # GEODESIC MODULE  (UNPUBLISHED — admin only)
    # =========================================================================

    @app.route("/api/geodesic/module", methods=["GET"])
    @admin_required
    def api_geodesic_module():
        """
        GET /api/geodesic/module — ADMIN ONLY.
        Returns the JS source of the unpublished Geodesic Experiment module.
        This endpoint exists to ensure the geodesic module code never appears
        in the public HTML file. All access is JWT-gated and audit-logged.
        """
        module_path = os.path.join(_HERE, "geodesic_module.js")
        if not os.path.exists(module_path):
            return jsonify({"error": "Geodesic module file not found on server."}), 404

        with open(module_path, "r", encoding="utf-8") as fh:
            code = fh.read()

        user_id = get_jwt_identity()
        audit(user_id, "GEODESIC_MODULE_ACCESSED", "module", "geodesic")
        return jsonify({"code": code, "published": False}), 200

    @app.route("/api/geodesic/status", methods=["GET"])
    @admin_required
    def api_geodesic_status():
        """GET /api/geodesic/status — admin only, returns publication status."""
        return jsonify({
            "published": False,
            "label": "Hemanth Geodesic Experiment — Christoffel Gate Angles (2026)",
            "note": "Pending publication. Access restricted to admin only.",
        }), 200

    return app


# ─── Bootstrap admin on first run ────────────────────────────────────────────

def bootstrap_admin(app, admin_id: str, admin_password: str):
    """Call once to create the initial admin user."""
    with app.app_context():
        if not User.query.get(admin_id):
            u = User(
                id            = admin_id,
                password_hash = hash_password(admin_password),
                role          = "admin",
            )
            db.session.add(u)
            db.session.commit()
            print(f"[Bootstrap] Admin user '{admin_id}' created.")
        else:
            print(f"[Bootstrap] Admin '{admin_id}' already exists.")


if __name__ == "__main__":
    import os
    application = create_app()

    # Create the first admin from env vars on first run.
    admin_id  = os.environ.get("BOOTSTRAP_ADMIN_ID")
    admin_pwd = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if admin_id and admin_pwd:
        bootstrap_admin(application, admin_id, admin_pwd)

    application.run(host="127.0.0.1", port=5000, debug=Config.DEBUG)
