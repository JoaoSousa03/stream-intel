"""
Tests for friends / social routes:
  GET    /api/friends
  GET    /api/friends/search
  POST   /api/friends/request
  POST   /api/friends/accept
  POST   /api/friends/reject
  POST   /api/friends/remove
  GET    /api/friends/requests
  GET    /api/friends/requests/sent
  DELETE /api/friends/request/<user_id>
"""

import pytest
from tests.conftest import register, get_token, auth_header


# ── helpers ───────────────────────────────────────────────────────────────────


def _get_user_id(client, username, password):
    """Log in and return the user_id via /api/auth/me."""
    token = get_token(client, username, password)
    rv = client.get("/api/auth/me", headers=auth_header(token))
    # me doesn't return user_id; look it up from the DB via the app fixture instead
    return token  # just return token; resolve ID from DB in tests that need it


@pytest.fixture
def two_users(client):
    """
    Returns (alice_token, bob_token, bob_id).
    alice is the first (admin) user; bob is registered by alice.
    """
    register(client, "alice", "alicepass1")
    alice_token = get_token(client, "alice", "alicepass1")
    register(client, "bob", "bobpass123", auth_token=alice_token)
    bob_token = get_token(client, "bob", "bobpass123")
    # resolve bob's id
    rv = client.get("/api/friends/search?q=bob", headers=auth_header(alice_token))
    users = rv.get_json()["users"]
    bob_id = users[0]["id"] if users else None
    return alice_token, bob_token, bob_id


# ── authentication guards ─────────────────────────────────────────────────────


def test_friends_requires_auth(client):
    assert client.get("/api/friends").status_code == 401


def test_search_requires_auth(client):
    assert client.get("/api/friends/search?q=alice").status_code == 401


def test_send_request_requires_auth(client):
    assert client.post("/api/friends/request", json={"user_id": 1}).status_code == 401


def test_pending_requests_requires_auth(client):
    assert client.get("/api/friends/requests").status_code == 401


# ── empty state ───────────────────────────────────────────────────────────────


def test_friends_empty_for_new_user(client, admin_headers):
    rv = client.get("/api/friends", headers=admin_headers)
    assert rv.status_code == 200
    assert rv.get_json()["friends"] == []


def test_search_short_query_returns_empty(client, admin_headers):
    rv = client.get("/api/friends/search?q=a", headers=admin_headers)
    assert rv.status_code == 200
    assert rv.get_json()["users"] == []


# ── user search ───────────────────────────────────────────────────────────────


def test_search_finds_other_user(client, two_users):
    alice_token, bob_token, bob_id = two_users
    rv = client.get("/api/friends/search?q=bob", headers=auth_header(alice_token))
    users = rv.get_json()["users"]
    assert any(u["username"] == "bob" for u in users)


def test_search_excludes_self(client, two_users):
    alice_token, bob_token, bob_id = two_users
    rv = client.get("/api/friends/search?q=alice", headers=auth_header(alice_token))
    users = rv.get_json()["users"]
    assert not any(u["username"] == "alice" for u in users)


# ── friend requests ───────────────────────────────────────────────────────────


def test_send_friend_request(client, two_users):
    alice_token, bob_token, bob_id = two_users
    rv = client.post(
        "/api/friends/request",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )
    assert rv.status_code == 200
    assert rv.get_json()["status"] in ("request_sent", "accepted")


def test_send_request_to_self_fails(client, admin_token, app):
    """Cannot send a friend request to yourself."""
    with app.app_context():
        from backend.database import get_db

        alice_id = (
            get_db()
            .execute("SELECT id FROM users WHERE username='admin'")
            .fetchone()["id"]
        )
    rv = client.post(
        "/api/friends/request",
        json={"user_id": alice_id},
        headers=auth_header(admin_token),
    )
    assert rv.status_code == 400


def test_send_request_to_nonexistent_user(client, admin_token):
    rv = client.post(
        "/api/friends/request",
        json={"user_id": 99999},
        headers=auth_header(admin_token),
    )
    assert rv.status_code == 404


def test_pending_incoming_requests(client, two_users):
    alice_token, bob_token, bob_id = two_users
    client.post(
        "/api/friends/request",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )
    rv = client.get("/api/friends/requests", headers=auth_header(bob_token))
    requests = rv.get_json()["requests"]
    assert any(r["username"] == "alice" for r in requests)


def test_sent_requests(client, two_users):
    alice_token, bob_token, bob_id = two_users
    client.post(
        "/api/friends/request",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )
    rv = client.get("/api/friends/requests/sent", headers=auth_header(alice_token))
    requests = rv.get_json()["requests"]
    assert any(r["username"] == "bob" for r in requests)


def test_search_shows_request_sent_status(client, two_users):
    alice_token, bob_token, bob_id = two_users
    client.post(
        "/api/friends/request",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )
    rv = client.get("/api/friends/search?q=bob", headers=auth_header(alice_token))
    user = rv.get_json()["users"][0]
    assert user["friendship_status"] == "request_sent"


# ── accept/reject ─────────────────────────────────────────────────────────────


def test_accept_friend_request(client, two_users):
    alice_token, bob_token, bob_id = two_users
    # alice sends to bob
    client.post(
        "/api/friends/request",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )
    # bob accepts — need alice's id
    with pytest.MonkeyPatch().context() as m:
        pass
    # Get alice id via search from bob's perspective
    rv_search = client.get(
        "/api/friends/search?q=alice", headers=auth_header(bob_token)
    )
    alice_id = rv_search.get_json()["users"][0]["id"]

    rv = client.post(
        "/api/friends/accept",
        json={"user_id": alice_id},
        headers=auth_header(bob_token),
    )
    assert rv.status_code == 200
    assert rv.get_json()["ok"] is True


def test_friends_list_after_accept(client, two_users):
    alice_token, bob_token, bob_id = two_users
    client.post(
        "/api/friends/request",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )
    rv_search = client.get(
        "/api/friends/search?q=alice", headers=auth_header(bob_token)
    )
    alice_id = rv_search.get_json()["users"][0]["id"]
    client.post(
        "/api/friends/accept",
        json={"user_id": alice_id},
        headers=auth_header(bob_token),
    )

    rv = client.get("/api/friends", headers=auth_header(alice_token))
    friends = rv.get_json()["friends"]
    assert any(f["username"] == "bob" for f in friends)


def test_reject_friend_request(client, two_users):
    alice_token, bob_token, bob_id = two_users
    client.post(
        "/api/friends/request",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )
    rv_search = client.get(
        "/api/friends/search?q=alice", headers=auth_header(bob_token)
    )
    alice_id = rv_search.get_json()["users"][0]["id"]

    rv = client.post(
        "/api/friends/reject",
        json={"user_id": alice_id},
        headers=auth_header(bob_token),
    )
    assert rv.status_code == 200

    # Pending requests should now be empty for bob
    rv2 = client.get("/api/friends/requests", headers=auth_header(bob_token))
    assert rv2.get_json()["requests"] == []


def test_cancel_friend_request(client, two_users):
    alice_token, bob_token, bob_id = two_users
    client.post(
        "/api/friends/request",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )

    rv = client.delete(
        f"/api/friends/request/{bob_id}",
        headers=auth_header(alice_token),
    )
    assert rv.status_code == 200

    # Sent requests should be empty
    rv2 = client.get("/api/friends/requests/sent", headers=auth_header(alice_token))
    assert rv2.get_json()["requests"] == []


# ── remove friend ─────────────────────────────────────────────────────────────


def test_remove_friend(client, two_users):
    alice_token, bob_token, bob_id = two_users
    # Establish friendship
    client.post(
        "/api/friends/request",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )
    rv_search = client.get(
        "/api/friends/search?q=alice", headers=auth_header(bob_token)
    )
    alice_id = rv_search.get_json()["users"][0]["id"]
    client.post(
        "/api/friends/accept",
        json={"user_id": alice_id},
        headers=auth_header(bob_token),
    )

    # Remove friendship
    rv = client.post(
        "/api/friends/remove",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )
    assert rv.status_code == 200

    rv2 = client.get("/api/friends", headers=auth_header(alice_token))
    assert rv2.get_json()["friends"] == []


# ── duplicate request guard ───────────────────────────────────────────────────


def test_duplicate_request_returns_409(client, two_users):
    alice_token, bob_token, bob_id = two_users
    client.post(
        "/api/friends/request",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )
    rv = client.post(
        "/api/friends/request",
        json={"user_id": bob_id},
        headers=auth_header(alice_token),
    )
    assert rv.status_code == 409
