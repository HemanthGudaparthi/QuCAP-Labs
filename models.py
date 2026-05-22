from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id               = db.Column(db.String(50),  primary_key=True)
    name             = db.Column(db.String(100), nullable=True)
    email            = db.Column(db.String(255), nullable=True, unique=True)
    password_hash    = db.Column(db.String(255), nullable=False)
    role             = db.Column(db.String(20),  nullable=False, default="researcher")
    ilp_tokens       = db.Column(db.Integer,     nullable=False, default=0)
    created_at       = db.Column(db.DateTime,    nullable=False, default=utcnow)
    last_login       = db.Column(db.DateTime)
    is_active        = db.Column(db.Boolean,     nullable=False, default=True)
    login_attempts   = db.Column(db.Integer,     nullable=False, default=0)
    locked_until     = db.Column(db.DateTime)
    geodesic_access  = db.Column(db.Boolean,     nullable=False, default=False)

    research     = db.relationship("Research",          back_populates="user", lazy="dynamic")
    experiments  = db.relationship("QuantumExperiment", back_populates="user",
                                   foreign_keys="QuantumExperiment.user_id", lazy="dynamic")

    def is_admin(self):
        return self.role == "admin"

    def is_locked(self):
        if self.locked_until and self.locked_until > utcnow():
            return True
        return False

    def to_public_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "ilp_tokens": self.ilp_tokens,
            "failed_logins": self.login_attempts,
            "geodesic_access": self.geodesic_access,
        }


class Session(db.Model):
    __tablename__ = "sessions"

    jti        = db.Column(db.String(255), primary_key=True)
    user_id    = db.Column(db.String(50),  db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime,    nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime,    nullable=False)
    revoked    = db.Column(db.Boolean,     nullable=False, default=False)


class Research(db.Model):
    __tablename__ = "research"

    id             = db.Column(db.String(50),  primary_key=True)
    user_id        = db.Column(db.String(50),  db.ForeignKey("users.id"), nullable=False)
    # input_type: "research" (title + equations), "topic" (keyword), "query" (free-form)
    input_type     = db.Column(db.String(20),  nullable=False, default="research")
    title          = db.Column(db.String(255), nullable=False)
    equations      = db.Column(db.Text)
    tokens_awarded = db.Column(db.Integer,     nullable=False, default=0)
    is_novel       = db.Column(db.Boolean,     nullable=False, default=False)
    novelty_score  = db.Column(db.Float)
    db1_file_id    = db.Column(db.String(255))   # Google Drive file ID
    rd_entry_id    = db.Column(db.String(255))   # Research Database reference
    created_at     = db.Column(db.DateTime,    nullable=False, default=utcnow)
    updated_at     = db.Column(db.DateTime,    nullable=False, default=utcnow, onupdate=utcnow)

    user           = db.relationship("User",              back_populates="research")
    novelty_tokens = db.relationship("NoveltyToken",      back_populates="research", lazy="dynamic")
    experiments    = db.relationship("QuantumExperiment", back_populates="research", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id, "input_type": self.input_type, "title": self.title,
            "is_novel": self.is_novel, "novelty_score": self.novelty_score,
            "tokens_awarded": self.tokens_awarded, "created_at": self.created_at.isoformat(),
        }


class NoveltyToken(db.Model):
    __tablename__ = "novelty_tokens"

    id            = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    research_id   = db.Column(db.String(50),  db.ForeignKey("research.id"), nullable=False)
    user_id       = db.Column(db.String(50),  db.ForeignKey("users.id"),    nullable=False)
    novelty_score = db.Column(db.Float,       nullable=False)
    token_value   = db.Column(db.Integer,     nullable=False)
    token_hash    = db.Column(db.String(255), nullable=False, unique=True)
    issued_at     = db.Column(db.DateTime,    nullable=False, default=utcnow)

    research = db.relationship("Research", back_populates="novelty_tokens")


class QuantumExperiment(db.Model):
    __tablename__ = "quantum_experiments"

    id                      = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    research_id             = db.Column(db.String(50),  db.ForeignKey("research.id"), nullable=False)
    user_id                 = db.Column(db.String(50),  db.ForeignKey("users.id"),    nullable=False)
    hardware_type           = db.Column(db.String(20),  nullable=False)
    is_suitable             = db.Column(db.Boolean)
    circuit_version         = db.Column(db.Integer,     nullable=False, default=1)
    run_count               = db.Column(db.Integer,     nullable=False, default=0)
    reliability_passed      = db.Column(db.Boolean)
    reliability_score       = db.Column(db.Float)
    results_public          = db.Column(db.Boolean,     nullable=False, default=False)
    publication_approved_by = db.Column(db.String(50),  db.ForeignKey("users.id"))
    publication_approved_at = db.Column(db.DateTime)
    created_at              = db.Column(db.DateTime,    nullable=False, default=utcnow)

    research = db.relationship("Research",        back_populates="experiments")
    user     = db.relationship("User",            back_populates="experiments", foreign_keys=[user_id])
    circuits = db.relationship("QuantumCircuit",  back_populates="experiment",  lazy="dynamic")
    results  = db.relationship("ExperimentResult", back_populates="experiment", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id, "hardware_type": self.hardware_type,
            "is_suitable": self.is_suitable, "circuit_version": self.circuit_version,
            "run_count": self.run_count, "reliability_passed": self.reliability_passed,
            "reliability_score": self.reliability_score, "results_public": self.results_public,
        }


class QuantumCircuit(db.Model):
    __tablename__ = "quantum_circuits"

    id                     = db.Column(db.Integer,  primary_key=True, autoincrement=True)
    experiment_id          = db.Column(db.Integer,  db.ForeignKey("quantum_experiments.id"), nullable=False)
    version                = db.Column(db.Integer,  nullable=False, default=1)
    circuit_qasm           = db.Column(db.Text,     nullable=False)
    circuit_metadata       = db.Column(db.Text)      # JSON
    theoretically_correct  = db.Column(db.Boolean)
    is_quantum_application = db.Column(db.Boolean)
    ai_confidence          = db.Column(db.Float)
    parent_circuit_id      = db.Column(db.Integer,  db.ForeignKey("quantum_circuits.id"))
    created_at             = db.Column(db.DateTime, nullable=False, default=utcnow)

    experiment = db.relationship("QuantumExperiment", back_populates="circuits")


class ExperimentResult(db.Model):
    __tablename__ = "experiment_results"

    id                  = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    experiment_id       = db.Column(db.Integer,     db.ForeignKey("quantum_experiments.id"), nullable=False)
    circuit_id          = db.Column(db.Integer,     db.ForeignKey("quantum_circuits.id"),    nullable=False)
    raw_results         = db.Column(db.Text)         # JSON
    processed_results   = db.Column(db.Text)         # JSON
    reliability_score   = db.Column(db.Float)
    is_public           = db.Column(db.Boolean,     nullable=False, default=False)
    approved_by         = db.Column(db.String(50),  db.ForeignKey("users.id"))
    approved_at         = db.Column(db.DateTime)
    created_at          = db.Column(db.DateTime,    nullable=False, default=utcnow)

    experiment = db.relationship("QuantumExperiment", back_populates="results")


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id            = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    user_id       = db.Column(db.String(50),  db.ForeignKey("users.id"))
    action        = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50))
    resource_id   = db.Column(db.String(100))
    detail        = db.Column(db.Text)        # JSON
    ip_address    = db.Column(db.String(45))
    timestamp     = db.Column(db.DateTime,    nullable=False, default=utcnow)


class GeodesicAccessRequest(db.Model):
    __tablename__ = "geodesic_access_requests"

    id           = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    user_id      = db.Column(db.String(50),  db.ForeignKey("users.id"), nullable=False)
    message      = db.Column(db.Text)
    status       = db.Column(db.String(20),  nullable=False, default="pending")  # pending/approved/denied
    requested_at = db.Column(db.DateTime,    nullable=False, default=utcnow)
    reviewed_at  = db.Column(db.DateTime)
    reviewed_by  = db.Column(db.String(50),  db.ForeignKey("users.id"))

    user     = db.relationship("User", foreign_keys=[user_id])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])
