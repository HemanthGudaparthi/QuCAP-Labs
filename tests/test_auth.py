"""Tests for auth.py — password hashing, login, lockout, JWT revocation, decorators."""
import pytest
from auth import hash_password, check_password


# ── Password helpers ──────────────────────────────────────────────────────────

def test_hash_password_produces_bcrypt():
    h = hash_password("secret")
    assert h.startswith("$2b$")


def test_hash_password_is_deterministically_different():
    # Two hashes of the same password must differ (bcrypt salt is random).
    assert hash_password("secret") != hash_password("secret")


def test_check_password_correct():
    h = hash_password("correct_horse")
    assert check_password("correct_horse", h) is True


def test_check_password_wrong():
    h = hash_password("correct_horse")
    assert check_password("wrong_horse", h) is False


def test_check_password_empty():
    h = hash_password("nonempty")
    assert check_password("", h) is False


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_success(client, researcher_user):
    resp = client.post("/api/auth/login",
                       json={"id": "researcher1", "password": "Researcher1!"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password(client, researcher_user):
    resp = client.post("/api/auth/login",
                       json={"id": "researcher1", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user(client, db):
    resp = client.post("/api/auth/login",
                       json={"id": "nobody", "password": "anything"})
    assert resp.status_code == 401


def test_login_missing_fields(client, db):
    resp = client.post("/api/auth/login", json={"id": "x"})
    assert resp.status_code == 400


def test_login_lockout_after_max_attempts(client, app, db):
    from models import User
    with app.app_context():
        u = User(id="lockout_user", password_hash=hash_password("L0ck0ut!"), role="researcher")
        db.session.add(u)
        db.session.commit()
    for _ in range(5):
        client.post("/api/auth/login",
                    json={"id": "lockout_user", "password": "badpass"})
    resp = client.post("/api/auth/login",
                       json={"id": "lockout_user", "password": "L0ck0ut!"})
    assert resp.status_code == 401
    assert "locked" in resp.get_json()["error"].lower()


# ── Logout & token revocation ─────────────────────────────────────────────────

def test_logout_revokes_token(client, researcher_headers):
    resp = client.post("/api/auth/logout", headers=researcher_headers)
    assert resp.status_code == 200

    # Token should now be rejected.
    resp2 = client.get("/api/auth/me", headers=researcher_headers)
    assert resp2.status_code == 401


def test_me_returns_user_info(client, researcher_headers):
    resp = client.get("/api/auth/me", headers=researcher_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == "researcher1"
    assert data["role"] == "researcher"


# ── Role enforcement ──────────────────────────────────────────────────────────

def test_admin_endpoint_rejects_researcher(client, researcher_headers):
    resp = client.get("/api/admin/audit-log", headers=researcher_headers)
    assert resp.status_code == 403


def test_admin_endpoint_accepts_admin(client, admin_headers):
    resp = client.get("/api/admin/audit-log", headers=admin_headers)
    assert resp.status_code == 200


def test_protected_endpoint_without_token(client, db):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_admin_can_create_user(client, admin_headers):
    resp = client.post("/api/auth/users",
                       headers=admin_headers,
                       json={"id": "newuser", "password": "Pass1234!", "role": "viewer"})
    assert resp.status_code == 201


def test_create_user_invalid_role(client, admin_headers):
    resp = client.post("/api/auth/users",
                       headers=admin_headers,
                       json={"id": "u2", "password": "Pass1234!", "role": "superuser"})
    assert resp.status_code == 400


def test_duplicate_user_rejected(client, admin_headers, researcher_user):
    resp = client.post("/api/auth/users",
                       headers=admin_headers,
                       json={"id": "researcher1", "password": "Pass1234!", "role": "researcher"})
    assert resp.status_code == 409


def test_viewer_cannot_access_researcher_endpoint(client, admin_headers):
    client.post("/api/auth/users", headers=admin_headers,
                json={"id": "viewer_auth", "password": "View1234!", "role": "viewer"})
    token = client.post("/api/auth/login",
                        json={"id": "viewer_auth", "password": "View1234!"}).get_json()["access_token"]
    resp = client.post("/api/research",
                       headers={"Authorization": f"Bearer {token}"},
                       json={"title": "test", "input_type": "topic"})
    assert resp.status_code == 403


def test_inactive_user_cannot_login(client, app, db):
    from models import User
    with app.app_context():
        u = User(id="inactive1", password_hash=hash_password("Pass1!"),
                 role="researcher", is_active=False)
        db.session.add(u)
        db.session.commit()
    resp = client.post("/api/auth/login",
                       json={"id": "inactive1", "password": "Pass1!"})
    assert resp.status_code == 401
