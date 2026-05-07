-- QuantumLabs Database Schema
-- PostgreSQL syntax; for SQLite dev use SQLAlchemy models.py instead.
-- CONFIDENTIAL — Do not distribute without authorization.

-- ─── USERS ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                  VARCHAR(50)  PRIMARY KEY,
    password_hash       VARCHAR(255) NOT NULL,
    role                VARCHAR(20)  NOT NULL DEFAULT 'researcher'
                            CHECK (role IN ('admin', 'researcher', 'viewer')),
    ilp_tokens          INTEGER      NOT NULL DEFAULT 0,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login          TIMESTAMP,
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    login_attempts      INTEGER      NOT NULL DEFAULT 0,
    locked_until        TIMESTAMP
);

-- ─── SESSIONS (JWT revocation list) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    jti         VARCHAR(255) PRIMARY KEY,
    user_id     VARCHAR(50)  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMP    NOT NULL,
    revoked     BOOLEAN      NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- ─── RESEARCH ─────────────────────────────────────────────────────────────────
-- Stores research submissions. Files live in DB1 (Google Drive placeholder).
CREATE TABLE IF NOT EXISTS research (
    id              VARCHAR(50)  PRIMARY KEY,
    user_id         VARCHAR(50)  NOT NULL REFERENCES users(id),
    title           VARCHAR(255) NOT NULL,
    equations       TEXT,
    tokens_awarded  INTEGER      NOT NULL DEFAULT 0,
    is_novel        BOOLEAN      NOT NULL DEFAULT FALSE,
    novelty_score   FLOAT,
    db1_file_id     VARCHAR(255),   -- Google Drive file ID (DB1 placeholder)
    rd_entry_id     VARCHAR(255),   -- Research Database (RD) entry reference
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_research_user ON research(user_id);

-- ─── NOVELTY TOKENS ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS novelty_tokens (
    id              SERIAL       PRIMARY KEY,
    research_id     VARCHAR(50)  NOT NULL REFERENCES research(id),
    user_id         VARCHAR(50)  NOT NULL REFERENCES users(id),
    novelty_score   FLOAT        NOT NULL,
    token_value     INTEGER      NOT NULL,
    token_hash      VARCHAR(255) NOT NULL UNIQUE,
    issued_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_novelty_research ON novelty_tokens(research_id);

-- ─── QUANTUM EXPERIMENTS ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS quantum_experiments (
    id                      SERIAL      PRIMARY KEY,
    research_id             VARCHAR(50) NOT NULL REFERENCES research(id),
    user_id                 VARCHAR(50) NOT NULL REFERENCES users(id),
    hardware_type           VARCHAR(20) NOT NULL
                                CHECK (hardware_type IN ('electron', 'photonic', 'neutrino')),
    is_suitable             BOOLEAN,
    circuit_version         INTEGER     NOT NULL DEFAULT 1,
    run_count               INTEGER     NOT NULL DEFAULT 0,
    reliability_passed      BOOLEAN,
    reliability_score       FLOAT,
    results_public          BOOLEAN     NOT NULL DEFAULT FALSE,
    publication_approved_by VARCHAR(50) REFERENCES users(id),
    publication_approved_at TIMESTAMP,
    created_at              TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_experiments_research ON quantum_experiments(research_id);

-- ─── QUANTUM CIRCUITS ─────────────────────────────────────────────────────────
-- Each circuit is versioned; newer circuits build upon previous ones (the
-- "extend the Quantum Circuit" loop from the workflow diagram).
CREATE TABLE IF NOT EXISTS quantum_circuits (
    id                      SERIAL      PRIMARY KEY,
    experiment_id           INTEGER     NOT NULL REFERENCES quantum_experiments(id),
    version                 INTEGER     NOT NULL DEFAULT 1,
    circuit_qasm            TEXT        NOT NULL,   -- OpenQASM 3 representation
    circuit_metadata        TEXT,                   -- JSON: gates, depth, qubits
    theoretically_correct   BOOLEAN,
    is_quantum_application  BOOLEAN,
    ai_confidence           FLOAT,
    parent_circuit_id       INTEGER     REFERENCES quantum_circuits(id),  -- for extensions
    created_at              TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_circuits_experiment ON quantum_circuits(experiment_id);

-- ─── EXPERIMENT RESULTS ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS experiment_results (
    id                  SERIAL      PRIMARY KEY,
    experiment_id       INTEGER     NOT NULL REFERENCES quantum_experiments(id),
    circuit_id          INTEGER     NOT NULL REFERENCES quantum_circuits(id),
    raw_results         TEXT,       -- JSON: shot counts from hardware
    processed_results   TEXT,       -- JSON: cleaned/analyzed output
    reliability_score   FLOAT,
    is_public           BOOLEAN     NOT NULL DEFAULT FALSE,
    approved_by         VARCHAR(50) REFERENCES users(id),
    approved_at         TIMESTAMP,
    created_at          TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─── AUDIT LOG ────────────────────────────────────────────────────────────────
-- Immutable record of every security-relevant action.
CREATE TABLE IF NOT EXISTS audit_log (
    id              SERIAL       PRIMARY KEY,
    user_id         VARCHAR(50)  REFERENCES users(id),
    action          VARCHAR(100) NOT NULL,
    resource_type   VARCHAR(50),
    resource_id     VARCHAR(100),
    detail          TEXT,        -- JSON with extra context
    ip_address      VARCHAR(45),
    timestamp       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_user      ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
