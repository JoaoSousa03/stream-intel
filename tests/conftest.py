"""
Shared fixtures and helpers for the StreamIntel test suite.

Each test gets a fresh, isolated SQLite database via the `app` fixture
(backed by pytest's `tmp_path`).  No global state bleeds between tests.
"""

import pytest
from backend.config import settings
from backend.app import create_app


# ── core fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def app(tmp_path):
    """Flask app backed by a brand-new temp SQLite file per test."""
    original = settings.DB_PATH
    settings.DB_PATH = tmp_path / "test.db"
    application = create_app()  # also calls init_db() internally
    application.config["TESTING"] = True
    yield application
    settings.DB_PATH = original  # restore for subsequent fixtures


@pytest.fixture
def client(app):
    return app.test_client()


# ── auth helpers (module-level so test files can import them) ─────────────────


def register(client, username, password, *, auth_token=None):
    """POST /api/auth/register.  Pass auth_token when registering a non-first user."""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    return client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
        headers=headers,
    )


def login(client, username, password):
    """POST /api/auth/login.  Returns Response."""
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


def get_token(client, username, password):
    """Login and return the bearer token string extracted from the Set-Cookie header."""
    rv = login(client, username, password)
    if rv.status_code != 200:
        return None
    # Token is delivered via Set-Cookie: si_token=<value>; ...
    set_cookie = rv.headers.get("Set-Cookie", "")
    for part in set_cookie.split(";"):
        part = part.strip()
        if part.startswith("si_token="):
            return part[len("si_token=") :]
    return None


def auth_header(token):
    """Return Authorization header dict for the given bearer token."""
    return {"Authorization": f"Bearer {token}"}


# ── high-level fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def admin_token(client, app):
    """Register first user, grant is_admin=1, return their auth token.

    In production, is_admin is granted via a one-time DB migration.  Fresh
    test databases skip that migration path, so we set the flag directly.
    """
    register(client, "admin", "adminpass1")
    with app.app_context():
        from backend.database import get_db

        db = get_db()
        db.execute("UPDATE users SET is_admin=1 WHERE username='admin'")
        db.commit()
    return get_token(client, "admin", "adminpass1")


@pytest.fixture
def admin_headers(admin_token):
    return auth_header(admin_token)


@pytest.fixture
def user_token(client, admin_token):
    """Register a second non-admin user; return their auth token."""
    register(client, "user1", "userpass1", auth_token=admin_token)
    return get_token(client, "user1", "userpass1")


@pytest.fixture
def user_headers(user_token):
    return auth_header(user_token)
