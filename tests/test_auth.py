"""
Tests for authentication routes:
  POST   /api/auth/register
  POST   /api/auth/login
  POST   /api/auth/logout
  GET    /api/auth/me
  GET    /api/auth/ping
  GET    /api/auth/setup-status
  POST   /api/auth/change-password
"""

import pytest
from tests.conftest import register, login, get_token, auth_header


# ── /api/auth/setup-status ────────────────────────────────────────────────────


def test_setup_status_fresh_db(client):
    """Before any users exist, needs_setup must be True."""
    rv = client.get("/api/auth/setup-status")
    assert rv.status_code == 200
    assert rv.get_json()["needs_setup"] is True


def test_setup_status_after_registration(client):
    """After the first user registers, needs_setup must be False."""
    register(client, "alice", "password1")
    rv = client.get("/api/auth/setup-status")
    assert rv.get_json()["needs_setup"] is False


# ── /api/auth/ping ────────────────────────────────────────────────────────────


def test_ping_returns_ok(client):
    rv = client.get("/api/auth/ping")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert "ts" in data


# ── /api/auth/register ────────────────────────────────────────────────────────


def test_register_first_user(client):
    """First registration is always free — no token required."""
    rv = register(client, "alice", "password1")
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["ok"] is True
    assert data["username"] == "alice"


def test_register_second_user_requires_auth(client, app):
    """Registering a second user without a valid token returns 403."""
    register(client, "alice", "password1")
    # Use a fresh client that has no session cookie from the prior registration
    fresh = app.test_client()
    rv = register(fresh, "bob", "password1")
    assert rv.status_code == 403


def test_register_second_user_with_auth(client):
    """Registering a second user with a valid token succeeds."""
    register(client, "alice", "password1")
    token = get_token(client, "alice", "password1")
    rv = register(client, "bob", "password1", auth_token=token)
    assert rv.status_code == 201


def test_register_duplicate_username(client):
    """Duplicate username returns 409."""
    register(client, "alice", "password1")
    token = get_token(client, "alice", "password1")
    rv = register(client, "alice", "password2", auth_token=token)
    assert rv.status_code == 409
    assert "already taken" in rv.get_json()["error"].lower()


def test_register_username_too_short(client):
    rv = register(client, "ab", "password1")
    assert rv.status_code == 400
    assert "3 characters" in rv.get_json()["error"]


def test_register_username_too_long(client):
    rv = register(client, "a" * 31, "password1")
    assert rv.status_code == 400


def test_register_password_too_short(client):
    rv = register(client, "alice", "pw")
    assert rv.status_code == 400
    assert "6 characters" in rv.get_json()["error"]


def test_register_missing_fields(client):
    rv = client.post("/api/auth/register", json={})
    assert rv.status_code == 400


# ── /api/auth/login ───────────────────────────────────────────────────────────


def test_login_success(client):
    register(client, "alice", "password1")
    rv = login(client, "alice", "password1")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data.get("ok") is True
    # token is delivered via Set-Cookie (not in JSON body)
    assert "si_token" in rv.headers.get("Set-Cookie", "")


def test_login_wrong_password(client):
    register(client, "alice", "password1")
    rv = login(client, "alice", "wrongpassword")
    assert rv.status_code == 401


def test_login_unknown_user(client):
    rv = login(client, "nobody", "password1")
    assert rv.status_code == 401


def test_login_missing_fields(client):
    rv = client.post("/api/auth/login", json={})
    assert rv.status_code == 400


# ── /api/auth/me ──────────────────────────────────────────────────────────────


def test_me_unauthenticated(client):
    rv = client.get("/api/auth/me")
    assert rv.status_code == 200
    assert rv.get_json()["authenticated"] is False


def test_me_authenticated(client):
    register(client, "alice", "password1")
    token = get_token(client, "alice", "password1")
    rv = client.get("/api/auth/me", headers=auth_header(token))
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["authenticated"] is True
    assert data["username"] == "alice"


def test_me_returns_stats_shape(client):
    """me endpoint must include favourites / watching / finished keys."""
    register(client, "alice", "password1")
    token = get_token(client, "alice", "password1")
    data = client.get("/api/auth/me", headers=auth_header(token)).get_json()
    for key in ("favourites", "watching", "finished"):
        assert key in data


# ── /api/auth/logout ──────────────────────────────────────────────────────────


def test_logout_success(client):
    register(client, "alice", "password1")
    token = get_token(client, "alice", "password1")
    rv = client.post("/api/auth/logout", headers=auth_header(token))
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True


def test_logout_revokes_token(client):
    """After logout, the same token must be rejected by a protected endpoint."""
    register(client, "alice", "password1")
    token = get_token(client, "alice", "password1")
    client.post("/api/auth/logout", headers=auth_header(token))
    # A protected endpoint should now return 401
    rv = client.get("/api/library", headers=auth_header(token))
    assert rv.status_code == 401


def test_logout_requires_auth(client):
    rv = client.post("/api/auth/logout")
    assert rv.status_code == 401


# ── /api/auth/change-password ─────────────────────────────────────────────────


def test_change_password_success(client):
    register(client, "alice", "password1")
    token = get_token(client, "alice", "password1")
    rv = client.post(
        "/api/auth/change-password",
        json={"old_password": "password1", "new_password": "newpass123"},
        headers=auth_header(token),
    )
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True
    # Can now log in with new password
    rv2 = login(client, "alice", "newpass123")
    assert rv2.status_code == 200


def test_change_password_wrong_old(client):
    register(client, "alice", "password1")
    token = get_token(client, "alice", "password1")
    rv = client.post(
        "/api/auth/change-password",
        json={"old_password": "wrongpass", "new_password": "newpass123"},
        headers=auth_header(token),
    )
    assert rv.status_code == 401


def test_change_password_new_too_short(client):
    register(client, "alice", "password1")
    token = get_token(client, "alice", "password1")
    rv = client.post(
        "/api/auth/change-password",
        json={"old_password": "password1", "new_password": "abc"},
        headers=auth_header(token),
    )
    assert rv.status_code == 400


def test_change_password_requires_auth(client):
    rv = client.post(
        "/api/auth/change-password",
        json={"old_password": "password1", "new_password": "newpass123"},
    )
    assert rv.status_code == 401
