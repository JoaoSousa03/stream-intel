"""
Tests for library routes:
  GET    /api/library
  POST   /api/library
  GET    /api/ratings
  PATCH  /api/titles/runtime
  PATCH  /api/titles/end_year
  PATCH  /api/titles/is_ongoing
"""

import pytest
from tests.conftest import register, get_token, auth_header


# ── helpers ───────────────────────────────────────────────────────────────────


def _add(
    client,
    headers,
    *,
    platform="Netflix",
    title="Test Show",
    status="watching",
    is_fav=False,
    user_rating=None,
    notes=None,
):
    payload = {"platform": platform, "title": title, "status": status, "is_fav": is_fav}
    if user_rating is not None:
        payload["user_rating"] = user_rating
    if notes is not None:
        payload["notes"] = notes
    return client.post("/api/library", json=payload, headers=headers)


# ── authentication guards ─────────────────────────────────────────────────────


def test_library_get_requires_auth(client):
    rv = client.get("/api/library")
    assert rv.status_code == 401


def test_library_post_requires_auth(client):
    rv = client.post(
        "/api/library", json={"platform": "Netflix", "title": "X", "status": "watching"}
    )
    assert rv.status_code == 401


def test_ratings_requires_auth(client):
    rv = client.get("/api/ratings")
    assert rv.status_code == 401


# ── empty state ───────────────────────────────────────────────────────────────


def test_library_empty_for_new_user(client, admin_token, admin_headers):
    rv = client.get("/api/library", headers=admin_headers)
    assert rv.status_code == 200
    assert rv.get_json()["library"] == []


def test_ratings_empty_for_new_user(client, admin_token, admin_headers):
    rv = client.get("/api/ratings", headers=admin_headers)
    assert rv.status_code == 200
    assert rv.get_json()["ratings"] == []


# ── add to library ────────────────────────────────────────────────────────────


def test_add_to_library(client, admin_headers):
    rv = _add(client, admin_headers)
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True


def test_library_contains_added_entry(client, admin_headers):
    _add(
        client,
        admin_headers,
        title="Breaking Bad",
        platform="Netflix",
        status="finished",
    )
    rv = client.get("/api/library", headers=admin_headers)
    lib = rv.get_json()["library"]
    assert any(e["title"] == "Breaking Bad" for e in lib)


def test_add_with_fav_flag(client, admin_headers):
    _add(client, admin_headers, title="Fav Show", is_fav=True)
    rv = client.get("/api/library", headers=admin_headers)
    entry = next(e for e in rv.get_json()["library"] if e["title"] == "Fav Show")
    assert entry["is_fav"] in (1, True)


def test_add_with_notes(client, admin_headers):
    _add(client, admin_headers, title="Noted", notes="Great series!")
    rv = client.get("/api/library", headers=admin_headers)
    entry = next(e for e in rv.get_json()["library"] if e["title"] == "Noted")
    assert entry["notes"] == "Great series!"


# ── status validation ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["not-started", "watching", "finished", "watchlist"])
def test_valid_statuses_accepted(client, admin_headers, status):
    rv = _add(client, admin_headers, title=f"Show-{status}", status=status)
    assert rv.status_code == 200


def test_invalid_status_rejected(client, admin_headers):
    rv = _add(client, admin_headers, status="invalid_value")
    assert rv.status_code == 400
    assert "status" in rv.get_json()["error"].lower()


# ── rating validation ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("rating", [0, 1, 3, 5])
def test_valid_ratings_accepted(client, admin_headers, rating):
    rv = _add(client, admin_headers, title=f"Rated-{rating}", user_rating=rating)
    assert rv.status_code == 200


def test_rating_above_max_rejected(client, admin_headers):
    rv = _add(client, admin_headers, user_rating=6)
    assert rv.status_code == 400


def test_negative_rating_rejected(client, admin_headers):
    rv = _add(client, admin_headers, user_rating=-1)
    assert rv.status_code == 400


# ── upsert behaviour ──────────────────────────────────────────────────────────


def test_upsert_updates_existing_entry(client, admin_headers):
    _add(client, admin_headers, title="Upsert Show", status="watching")
    _add(client, admin_headers, title="Upsert Show", status="finished")
    rv = client.get("/api/library", headers=admin_headers)
    matches = [e for e in rv.get_json()["library"] if e["title"] == "Upsert Show"]
    assert len(matches) == 1  # still exactly one row
    assert matches[0]["status"] == "finished"


# ── ratings endpoint ──────────────────────────────────────────────────────────


def test_rated_titles_appear_in_ratings(client, admin_headers):
    _add(client, admin_headers, title="Highly Rated", user_rating=5)
    rv = client.get("/api/ratings", headers=admin_headers)
    assert any(e["title"] == "Highly Rated" for e in rv.get_json()["ratings"])


def test_unrated_titles_absent_from_ratings(client, admin_headers):
    _add(client, admin_headers, title="Not Rated", user_rating=0)
    rv = client.get("/api/ratings", headers=admin_headers)
    assert not any(e["title"] == "Not Rated" for e in rv.get_json()["ratings"])


# ── PATCH /api/titles/runtime ─────────────────────────────────────────────────


def test_patch_runtime_requires_auth(client):
    rv = client.patch(
        "/api/titles/runtime",
        json={"platform": "Netflix", "title": "X", "runtime_mins": 45},
    )
    assert rv.status_code == 401


def test_patch_runtime_ok(client, admin_headers, app):
    """Insert a title row with runtime=0 then patch it."""
    with app.app_context():
        from backend.database import get_db

        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO titles"
            " (platform, region, title, content_type, runtime_mins, scraped_at)"
            " VALUES ('Netflix','US','Runtime Show','tv',0, datetime('now'))"
        )
        db.commit()
    rv = client.patch(
        "/api/titles/runtime",
        json={"platform": "Netflix", "title": "Runtime Show", "runtime_mins": 45},
        headers=admin_headers,
    )
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True


def test_patch_runtime_skips_nonzero(client, admin_headers, app):
    """Runtime must not be overwritten when it already has a value."""
    with app.app_context():
        from backend.database import get_db

        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO titles"
            " (platform, region, title, content_type, runtime_mins, scraped_at)"
            " VALUES ('Netflix','US','Has Runtime','tv',60, datetime('now'))"
        )
        db.commit()
    rv = client.patch(
        "/api/titles/runtime",
        json={"platform": "Netflix", "title": "Has Runtime", "runtime_mins": 30},
        headers=admin_headers,
    )
    assert rv.status_code == 200
    # Verify the value is unchanged
    with app.app_context():
        from backend.database import get_db

        row = (
            get_db()
            .execute("SELECT runtime_mins FROM titles WHERE title='Has Runtime'")
            .fetchone()
        )
    assert row["runtime_mins"] == 60


# ── PATCH /api/titles/end_year & is_ongoing ───────────────────────────────────


def test_patch_end_year_ok(client, admin_headers, app):
    with app.app_context():
        from backend.database import get_db

        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO titles"
            " (platform, region, title, content_type, scraped_at)"
            " VALUES ('HBO','US','End Year Show','tv', datetime('now'))"
        )
        db.commit()
    rv = client.patch(
        "/api/titles/end_year",
        json={"platform": "HBO", "title": "End Year Show", "end_year": "2023"},
        headers=admin_headers,
    )
    assert rv.status_code == 200


def test_patch_is_ongoing_ok(client, admin_headers, app):
    with app.app_context():
        from backend.database import get_db

        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO titles"
            " (platform, region, title, content_type, scraped_at)"
            " VALUES ('HBO','US','Ongoing Show','tv', datetime('now'))"
        )
        db.commit()
    rv = client.patch(
        "/api/titles/is_ongoing",
        json={"platform": "HBO", "title": "Ongoing Show", "is_ongoing": 1},
        headers=admin_headers,
    )
    assert rv.status_code == 200
