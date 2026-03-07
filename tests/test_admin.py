"""
Tests for admin routes:
  GET  /api/admin/users
  GET  /api/runs
  GET  /api/run/<mode>/<regions>   (SSE — just validate response headers)
"""

import pytest
from tests.conftest import register, get_token, auth_header


# ── /api/admin/users ──────────────────────────────────────────────────────────


def test_admin_users_requires_auth(client):
    rv = client.get("/api/admin/users")
    assert rv.status_code == 401


def test_admin_users_denied_for_non_admin(client, admin_token):
    """A non-admin (second) user gets 403."""
    register(client, "regular", "regularpass1", auth_token=admin_token)
    regular_token = get_token(client, "regular", "regularpass1")
    rv = client.get("/api/admin/users", headers=auth_header(regular_token))
    assert rv.status_code == 403
    assert "admin" in rv.get_json()["error"].lower()


def test_admin_users_allowed_for_admin(client, admin_headers):
    """The first (admin) user can list all accounts."""
    rv = client.get("/api/admin/users", headers=admin_headers)
    assert rv.status_code == 200
    data = rv.get_json()
    assert "users" in data
    assert isinstance(data["users"], list)
    assert len(data["users"]) >= 1


def test_admin_users_contains_expected_fields(client, admin_headers):
    rv = client.get("/api/admin/users", headers=admin_headers)
    user = rv.get_json()["users"][0]
    for field in ("id", "username", "email", "auth_type", "is_admin", "created_at"):
        assert field in user, f"Missing field: {field}"


def test_admin_users_shows_all_users(client, admin_token, admin_headers):
    register(client, "bob", "bobpass123", auth_token=admin_token)
    register(client, "carol", "carolpass1", auth_token=admin_token)
    rv = client.get("/api/admin/users", headers=admin_headers)
    usernames = {u["username"] for u in rv.get_json()["users"]}
    assert "admin" in usernames
    assert "bob" in usernames
    assert "carol" in usernames


# ── /api/runs ─────────────────────────────────────────────────────────────────


def test_list_runs_requires_auth(client):
    rv = client.get("/api/runs")
    assert rv.status_code == 401


def test_list_runs_returns_list(client, admin_headers):
    """Any authenticated user can view the scraper run history."""
    rv = client.get("/api/runs", headers=admin_headers)
    assert rv.status_code == 200
    data = rv.get_json()
    assert "runs" in data
    assert isinstance(data["runs"], list)


def test_list_runs_empty_initially(client, admin_headers):
    rv = client.get("/api/runs", headers=admin_headers)
    assert rv.get_json()["runs"] == []


def test_list_runs_shape_after_insert(client, admin_headers, app):
    """After inserting a scrape_run record the list is non-empty."""
    with app.app_context():
        from backend.database import get_db

        db = get_db()
        db.execute(
            """INSERT INTO scrape_runs (mode, regions, title_count, status)
               VALUES ('trending', '["US"]', 10, 'done')"""
        )
        db.commit()
    rv = client.get("/api/runs", headers=admin_headers)
    runs = rv.get_json()["runs"]
    assert len(runs) == 1
    run = runs[0]
    for field in ("id", "mode", "regions", "title_count", "status"):
        assert field in run, f"Missing scrape_run field: {field}"


# ── first-user is_admin flag ──────────────────────────────────────────────────


def test_first_user_is_admin(client, admin_headers, app):
    """The very first registered user must have is_admin=1."""
    with app.app_context():
        from backend.database import get_db

        row = (
            get_db()
            .execute("SELECT is_admin FROM users WHERE username='admin'")
            .fetchone()
        )
    assert row["is_admin"] == 1


def test_second_user_is_not_admin(client, admin_token, app):
    register(client, "regular", "regularpass1", auth_token=admin_token)
    with app.app_context():
        from backend.database import get_db

        row = (
            get_db()
            .execute("SELECT is_admin FROM users WHERE username='regular'")
            .fetchone()
        )
    # Second user should NOT be admin by default
    assert not row["is_admin"]
