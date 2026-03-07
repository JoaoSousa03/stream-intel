# backend/auth.py
import secrets
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import g, jsonify, request
from backend.database import get_db
from backend.config import settings

# ── In-memory token cache ─────────────────────────────────────────────────────
# Avoids a DB round-trip on every authenticated request.
# Structure: { token_str: (user_row_dict, cache_expires_unix_float) }
_token_cache: dict = {}
_token_cache_lock = threading.Lock()
_TOKEN_CACHE_TTL = 300  # re-validate from DB every 5 minutes


def _cache_set(token: str, user_row, db_expires_at: str) -> None:
    db_exp_unix = datetime.fromisoformat(db_expires_at).timestamp()
    cache_exp = min(db_exp_unix, time.time() + _TOKEN_CACHE_TTL)
    with _token_cache_lock:
        _token_cache[token] = (dict(user_row), cache_exp)


def _cache_get(token: str):
    with _token_cache_lock:
        entry = _token_cache.get(token)
    if not entry:
        return None
    user_dict, cache_exp = entry
    if time.time() > cache_exp:
        with _token_cache_lock:
            _token_cache.pop(token, None)
        return None
    return user_dict


def _cache_invalidate(token: str) -> None:
    with _token_cache_lock:
        _token_cache.pop(token, None)


def make_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(seconds=settings.TOKEN_TTL)).isoformat()
    db = get_db()
    db.execute(
        "INSERT INTO tokens (user_id, token, expires_at) VALUES (?,?,?)",
        (user_id, token, expires),
    )
    db.commit()
    return token


def verify_token(token: str):
    if not token:
        return None

    # Fast path — serve from cache
    cached = _cache_get(token)
    if cached is not None:
        return cached

    # Slow path — hit the DB and populate cache
    db = get_db()
    row = db.execute(
        """SELECT t.user_id, t.expires_at, t.revoked, u.username
           FROM tokens t JOIN users u ON u.id = t.user_id
           WHERE t.token = ?""",
        (token,),
    ).fetchone()
    if not row or row["revoked"]:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        return None
    _cache_set(token, row, row["expires_at"])
    return row


def _extract_token() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("si_token", "")


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = verify_token(_extract_token())
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        g.current_user = user
        return f(*args, **kwargs)

    return decorated
