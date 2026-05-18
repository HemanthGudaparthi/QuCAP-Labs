"""
Shared pytest fixtures.
Must set env vars BEFORE any app import so config.py class body doesn't KeyError.
"""
import os
os.environ.setdefault("SECRET_KEY",     "pytest-secret-key-abc123longerthan32chars!!")
os.environ.setdefault("JWT_SECRET_KEY", "pytest-jwt-secret-xyz789longerthan32chars!!")

import pytest
from app import create_app
from models import db as _db, User
from auth import hash_password


class TestConfig:
    SECRET_KEY                    = "pytest-secret-key-abc123longerthan32chars!!"
    JWT_SECRET_KEY                = "pytest-jwt-secret-xyz789longerthan32chars!!"
    SQLALCHEMY_DATABASE_URI       = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS     = {
        "connect_args": {"check_same_thread": False},
        "poolclass": __import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
    }
    TESTING                       = True
    DEBUG                         = False
    JWT_ACCESS_TOKEN_EXPIRES      = 3600
    JWT_REFRESH_TOKEN_EXPIRES     = 86400
    MAX_LOGIN_ATTEMPTS            = 5
    LOCKOUT_MINUTES               = 15
    IBM_QUANTUM_TOKEN             = None
    IBM_QUANTUM_BACKEND           = "ibm_test"
    GDRIVE_CREDENTIALS_FILE       = None
    GDRIVE_FOLDER_ID              = None
    PUBLICATION_REQUIRES_ADMIN    = True


@pytest.fixture(scope="session")
def app():
    return create_app(TestConfig)


@pytest.fixture()
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app, db):
    return app.test_client()


@pytest.fixture()
def admin_user(app, db):
    with app.app_context():
        u = User(id="admin1", password_hash=hash_password("Admin1234!"), role="admin")
        _db.session.add(u)
        _db.session.commit()
    return "admin1"


@pytest.fixture()
def researcher_user(app, db):
    with app.app_context():
        u = User(id="researcher1",
                 password_hash=hash_password("Researcher1!"), role="researcher")
        _db.session.add(u)
        _db.session.commit()
    return "researcher1"


@pytest.fixture()
def admin_headers(client, admin_user):
    resp  = client.post("/api/auth/login",
                        json={"id": "admin1", "password": "Admin1234!"})
    token = resp.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def researcher_headers(client, researcher_user):
    resp  = client.post("/api/auth/login",
                        json={"id": "researcher1", "password": "Researcher1!"})
    token = resp.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
