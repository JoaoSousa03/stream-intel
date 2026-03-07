"""
Tests for episode-tracking routes:
  GET    /api/watched
  POST   /api/watched
  PATCH  /api/watched/backfill
"""

import pytest
from tests.conftest import auth_header


PLATFORM = "Netflix"
TITLE = "Breaking Bad"
SEASON = 1


# ── authentication guards ─────────────────────────────────────────────────────


def test_watched_get_requires_auth(client):
    rv = client.get("/api/watched")
    assert rv.status_code == 401


def test_watched_post_requires_auth(client):
    rv = client.post("/api/watched", json={})
    assert rv.status_code == 401


def test_watched_backfill_requires_auth(client):
    rv = client.patch("/api/watched/backfill", json={})
    assert rv.status_code == 401


# ── empty state ───────────────────────────────────────────────────────────────


def test_watched_empty_for_new_user(client, admin_headers):
    rv = client.get("/api/watched", headers=admin_headers)
    assert rv.status_code == 200
    data = rv.get_json()
    assert "watched" in data


# ── mark episodes watched ─────────────────────────────────────────────────────


def test_mark_episode_watched(client, admin_headers):
    rv = client.post(
        "/api/watched",
        json={
            "platform": PLATFORM,
            "title": TITLE,
            "season_num": SEASON,
            "episode_num": 1,
            "runtime_mins": 47,
            "watched": True,
        },
        headers=admin_headers,
    )
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True


def test_get_watched_specific_title(client, admin_headers):
    """After marking an episode, querying with platform+title returns that data."""
    client.post(
        "/api/watched",
        json={
            "platform": PLATFORM,
            "title": TITLE,
            "season_num": SEASON,
            "episode_num": 1,
            "runtime_mins": 47,
            "watched": True,
        },
        headers=admin_headers,
    )
    rv = client.get(
        f"/api/watched?platform={PLATFORM}&title={TITLE}",
        headers=admin_headers,
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert "watched" in data
    # Should contain episode 1 of season 1
    ep_entry = next(
        (
            w
            for w in data["watched"]
            if w["season_num"] == SEASON and w["episode_num"] == 1
        ),
        None,
    )
    assert ep_entry is not None


def test_mark_multiple_episodes(client, admin_headers):
    for ep in [1, 2, 3]:
        client.post(
            "/api/watched",
            json={
                "platform": PLATFORM,
                "title": TITLE,
                "season_num": SEASON,
                "episode_num": ep,
                "runtime_mins": 47,
                "watched": True,
            },
            headers=admin_headers,
        )
    rv = client.get(
        f"/api/watched?platform={PLATFORM}&title={TITLE}",
        headers=admin_headers,
    )
    # Episodes 1, 2, 3 should all be in the response
    ep_nums = {
        w["episode_num"] for w in rv.get_json()["watched"] if w["season_num"] == SEASON
    }
    assert {1, 2, 3}.issubset(ep_nums)


def test_unmark_episode(client, admin_headers):
    """Marking an episode unwatched clears its bit."""
    # First mark it
    client.post(
        "/api/watched",
        json={
            "platform": PLATFORM,
            "title": TITLE,
            "season_num": SEASON,
            "episode_num": 1,
            "runtime_mins": 47,
            "watched": True,
        },
        headers=admin_headers,
    )
    # Now unmark it
    rv = client.post(
        "/api/watched",
        json={
            "platform": PLATFORM,
            "title": TITLE,
            "season_num": SEASON,
            "episode_num": 1,
            "runtime_mins": 47,
            "watched": False,
        },
        headers=admin_headers,
    )
    assert rv.status_code == 200
    # Season row should be gone (ep_mask = 0 triggers auto-delete)
    rv2 = client.get(
        f"/api/watched?platform={PLATFORM}&title={TITLE}",
        headers=admin_headers,
    )
    rows = [w for w in rv2.get_json()["watched"] if w["season_num"] == SEASON]
    assert rows == []


def test_watched_missing_fields(client, admin_headers):
    """Posting without required fields returns 400."""
    rv = client.post("/api/watched", json={}, headers=admin_headers)
    assert rv.status_code == 400


# ── PATCH /api/watched/backfill ───────────────────────────────────────────────


def test_backfill_empty_updates_ok(client, admin_headers):
    rv = client.patch(
        "/api/watched/backfill",
        json={"updates": []},
        headers=admin_headers,
    )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert data["updated"] == 0


def test_backfill_updates_runtime(client, admin_headers):
    # First create a watched season row
    client.post(
        "/api/watched",
        json={
            "platform": PLATFORM,
            "title": TITLE,
            "season_num": SEASON,
            "episode_num": 1,
            "runtime_mins": 47,
            "watched": True,
        },
        headers=admin_headers,
    )
    # Now backfill with new runtime total
    rv = client.patch(
        "/api/watched/backfill",
        json={
            "updates": [
                {
                    "platform": PLATFORM,
                    "title": TITLE,
                    "season_num": SEASON,
                    "runtime_mins": 500,
                }
            ]
        },
        headers=admin_headers,
    )
    assert rv.status_code == 200
    assert rv.get_json()["updated"] == 1


def test_backfill_skips_zero_runtime(client, admin_headers):
    client.post(
        "/api/watched",
        json={
            "platform": PLATFORM,
            "title": TITLE,
            "season_num": SEASON,
            "episode_num": 1,
            "runtime_mins": 47,
            "watched": True,
        },
        headers=admin_headers,
    )
    rv = client.patch(
        "/api/watched/backfill",
        json={
            "updates": [
                {
                    "platform": PLATFORM,
                    "title": TITLE,
                    "season_num": SEASON,
                    "runtime_mins": 0,
                }
            ]
        },
        headers=admin_headers,
    )
    assert rv.get_json()["updated"] == 0
