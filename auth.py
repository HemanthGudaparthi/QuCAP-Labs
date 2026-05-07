import json
from datetime import datetime, timezone, timedelta
from functools import wraps

import bcrypt
from flask import request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    get_jwt, get_jwt_identity, jwt_required, verify_jwt_in_request,
)

from models import db, User, Session, AuditLog


def utcnow():
    return datetime.now(timezone.utc)


# ─── Password helpers ─────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()

def check_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ─── Audit logging ────────────────────────────────────────────────────────────

def audit(user_id, action, resource_type=None, resource_id=None, detail=None):
    entry = AuditLog(
        user_id       = user_id,
        action        = action,
        resource_type = resource_type,
        resource_id   = str(resource_id) if resource_id else None,
        detail        = json.dumps(detail) if detail else None,
        ip_address    = request.remote_addr if request else None,
    )
    db.session.add(entry)
    db.session.commit()


# ─── JWT token store (revocation) ────────────────────────────────────────────

def store_token(jti: str, user_id: str, expires_delta_seconds: int):
    s = Session(
        jti        = jti,
        user_id    = user_id,
        expires_at = utcnow() + timedelta(seconds=expires_delta_seconds),
    )
    db.session.add(s)
    db.session.commit()

def revoke_token(jti: str):
    s = Session.query.get(jti)
    if s:
        s.revoked = True
        db.session.commit()

def is_token_revoked(jwt_payload: dict) -> bool:
    jti = jwt_payload["jti"]
    s = Session.query.get(jti)
    return (s is None) or s.revoked


# ─── Login ────────────────────────────────────────────────────────────────────

def login(user_id: str, password: str):
    cfg = current_app.config
    user = User.query.get(user_id)

    if not user or not user.is_active:
        audit(None, "LOGIN_FAILED_UNKNOWN_USER", detail={"attempted_id": user_id})
        return None, "Invalid credentials"

    if user.is_locked():
        remaining = int((user.locked_until - utcnow()).total_seconds() // 60) + 1
        audit(user_id, "LOGIN_BLOCKED_LOCKED")
        return None, f"Account locked. Try again in {remaining} minute(s)."

    if not check_password(password, user.password_hash):
        user.login_attempts += 1
        if user.login_attempts >= cfg["MAX_LOGIN_ATTEMPTS"]:
            user.locked_until   = utcnow() + timedelta(minutes=cfg["LOCKOUT_MINUTES"])
            user.login_attempts = 0
            db.session.commit()
            audit(user_id, "ACCOUNT_LOCKED", detail={"lockout_minutes": cfg["LOCKOUT_MINUTES"]})
            return None, "Too many failed attempts. Account locked."
        db.session.commit()
        audit(user_id, "LOGIN_FAILED_BAD_PASSWORD",
              detail={"attempts": user.login_attempts})
        return None, "Invalid credentials"

    # Successful login
    user.login_attempts = 0
    user.locked_until   = None
    user.last_login     = utcnow()
    db.session.commit()

    access_token  = create_access_token(identity=user_id)
    refresh_token = create_refresh_token(identity=user_id)

    access_jti  = _decode_jti(access_token)
    refresh_jti = _decode_jti(refresh_token)
    store_token(access_jti,  user_id, cfg["JWT_ACCESS_TOKEN_EXPIRES"])
    store_token(refresh_jti, user_id, cfg["JWT_REFRESH_TOKEN_EXPIRES"])

    audit(user_id, "LOGIN_SUCCESS")
    return {"access_token": access_token, "refresh_token": refresh_token}, None


def logout():
    jti = get_jwt()["jti"]
    revoke_token(jti)
    user_id = get_jwt_identity()
    audit(user_id, "LOGOUT")


def _decode_jti(token: str) -> str:
    from flask_jwt_extended import decode_token
    return decode_token(token)["jti"]


# ─── Role decorators ─────────────────────────────────────────────────────────

def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user or not user.is_admin():
            audit(user_id, "UNAUTHORIZED_ADMIN_ACCESS",
                  detail={"endpoint": request.path})
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper

def researcher_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user or user.role not in ("admin", "researcher"):
            audit(user_id, "UNAUTHORIZED_RESEARCHER_ACCESS",
                  detail={"endpoint": request.path})
            return jsonify({"error": "Researcher access required"}), 403
        return fn(*args, **kwargs)
    return wrapper
