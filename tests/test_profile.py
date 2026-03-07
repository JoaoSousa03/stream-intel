"""
Tests for profile routes:
  GET   /api/profile
  POST  /api/profile
"""

import pytest
from tests.conftest import register, get_token, auth_header


# ── authentication guards ─────────────────────────────────────────────────────


def test_get_profile_requires_auth(client):
    rv = client.get("/api/profile")
    assert rv.status_code == 401


def test_update_profile_requires_auth(client):
    rv = client.post("/api/profile", json={"display_name": "Test"})
    assert rv.status_code == 401


# ── GET /api/profile ──────────────────────────────────────────────────────────


def test_get_profile_returns_expected_shape(client, admin_token, admin_headers):
    rv = client.get("/api/profile", headers=admin_headers)
    assert rv.status_code == 200
    data = rv.get_json()
    for key in (
        "username",
        "display_name",
        "email",
        "auth_type",
        "member_since",
        "profile_pic",
        "home_country",
        "library_public",
        "stats",
    ):
        assert key in data, f"Missing key: {key}"


def test_get_profile_stats_shape(client, admin_headers):
    rv = client.get("/api/profile", headers=admin_headers)
    stats = rv.get_json()["stats"]
    for key in (
        "movies_finished",
        "movies_watching",
        "tv_finished",
        "tv_watching",
        "episodes_watched",
        "movie_watch_time",
        "tv_watch_time",
        "total_watch_time",
        "top_genres",
    ):
        assert key in stats, f"Missing stat key: {key}"


def test_profile_watch_time_shape(client, admin_headers):
    rv = client.get("/api/profile", headers=admin_headers)
    wt = rv.get_json()["stats"]["total_watch_time"]
    assert "total_minutes" in wt
    assert "label" in wt


def test_profile_username_matches(client, admin_token, admin_headers):
    rv = client.get("/api/profile", headers=admin_headers)
    assert rv.get_json()["username"] == "admin"


# ── POST /api/profile ─────────────────────────────────────────────────────────


def test_update_display_name(client, admin_headers):
    rv = client.post(
        "/api/profile",
        json={"display_name": "Admin Display"},
        headers=admin_headers,
    )
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True
    # verify it persisted
    profile = client.get("/api/profile", headers=admin_headers).get_json()
    assert profile["display_name"] == "Admin Display"


def test_clear_display_name(client, admin_headers):
    """Empty display_name is stored as None; username is shown as fallback."""
    client.post("/api/profile", json={"display_name": "Admin"}, headers=admin_headers)
    rv = client.post("/api/profile", json={"display_name": ""}, headers=admin_headers)
    assert rv.status_code == 200


def test_update_home_country_valid(client, admin_headers):
    rv = client.post(
        "/api/profile",
        json={"home_country": "us"},
        headers=admin_headers,
    )
    assert rv.status_code == 200
    profile = client.get("/api/profile", headers=admin_headers).get_json()
    assert profile["home_country"].upper() == "US"


def test_update_home_country_invalid(client, admin_headers):
    rv = client.post(
        "/api/profile",
        json={"home_country": "1X"},
        headers=admin_headers,
    )
    assert rv.status_code == 400


def test_update_library_public_true(client, admin_headers):
    rv = client.post(
        "/api/profile",
        json={"library_public": True},
        headers=admin_headers,
    )
    assert rv.status_code == 200
    profile = client.get("/api/profile", headers=admin_headers).get_json()
    assert profile["library_public"] is True


def test_update_library_public_false(client, admin_headers):
    # Set to true first
    client.post("/api/profile", json={"library_public": True}, headers=admin_headers)
    rv = client.post(
        "/api/profile", json={"library_public": False}, headers=admin_headers
    )
    assert rv.status_code == 200
    profile = client.get("/api/profile", headers=admin_headers).get_json()
    assert profile["library_public"] is False


def test_update_username_success(client, admin_token, admin_headers):
    rv = client.post(
        "/api/profile",
        json={"username": "newadmin"},
        headers=admin_headers,
    )
    assert rv.status_code == 200


def test_update_username_too_short(client, admin_headers):
    rv = client.post(
        "/api/profile",
        json={"username": "ab"},
        headers=admin_headers,
    )
    assert rv.status_code == 400


def test_update_username_too_long(client, admin_headers):
    rv = client.post(
        "/api/profile",
        json={"username": "a" * 31},
        headers=admin_headers,
    )
    assert rv.status_code == 400


def test_update_username_already_taken(client, admin_token, admin_headers):
    """Username conflict returns 409."""
    register(client, "other_user", "pass12345", auth_token=admin_token)
    rv = client.post(
        "/api/profile",
        json={"username": "other_user"},
        headers=admin_headers,
    )
    assert rv.status_code == 409


def test_update_nothing_returns_400(client, admin_headers):
    """Submitting an empty payload should return 400."""
    rv = client.post("/api/profile", json={}, headers=admin_headers)
    assert rv.status_code == 400


# ── stats accuracy ────────────────────────────────────────────────────────────


def test_profile_stats_update_after_library_add(client, admin_headers, app):
    """Adding an item to the library must cause the cached stats to reflect it.

    We add with is_fav=True then verify favourites increased, which is set
    purely from the library row (no titles JOIN needed).
    """
    before = client.get("/api/profile", headers=admin_headers).get_json()["stats"]

    client.post(
        "/api/library",
        json={
            "platform": "Netflix",
            "title": "Fav Movie",
            "status": "finished",
            "is_fav": True,
        },
        headers=admin_headers,
    )

    after = client.get("/api/profile", headers=admin_headers).get_json()["stats"]
    assert after["favourites"] > before["favourites"]
