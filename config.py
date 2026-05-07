import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── Flask core ────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ["SECRET_KEY"]               # hard-fail if missing
    DEBUG      = os.environ.get("FLASK_DEBUG", "0") == "1"

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY              = os.environ["JWT_SECRET_KEY"]
    JWT_ACCESS_TOKEN_EXPIRES    = int(os.environ.get("JWT_ACCESS_EXPIRES",  3600))   # 1 h
    JWT_REFRESH_TOKEN_EXPIRES   = int(os.environ.get("JWT_REFRESH_EXPIRES", 86400))  # 24 h
    JWT_BLACKLIST_ENABLED       = True
    JWT_BLACKLIST_TOKEN_CHECKS  = ["access", "refresh"]

    # ── Database ──────────────────────────────────────────────────────────────
    # Falls back to a local SQLite file for development only.
    SQLALCHEMY_DATABASE_URI         = os.environ.get(
        "DATABASE_URL", "sqlite:///quantumlabs_dev.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS  = False
    SQLALCHEMY_ENGINE_OPTIONS       = {"pool_pre_ping": True}

    # ── IBM Quantum (electron-based architecture) ─────────────────────────────
    IBM_QUANTUM_TOKEN   = os.environ.get("IBM_QUANTUM_TOKEN")
    IBM_QUANTUM_BACKEND = os.environ.get("IBM_QUANTUM_BACKEND", "ibm_brisbane")

    # ── Google Drive — DB1 placeholder ────────────────────────────────────────
    GDRIVE_CREDENTIALS_FILE = os.environ.get("GDRIVE_CREDENTIALS_FILE")
    GDRIVE_FOLDER_ID        = os.environ.get("GDRIVE_FOLDER_ID")

    # ── Security ──────────────────────────────────────────────────────────────
    MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", 5))
    LOCKOUT_MINUTES    = int(os.environ.get("LOCKOUT_MINUTES",    15))
    # Results MUST be explicitly approved by an admin before going public.
    PUBLICATION_REQUIRES_ADMIN = True
