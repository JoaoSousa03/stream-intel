# backend/routes/library.py
from flask import Blueprint, g, jsonify, request
from backend.auth import require_auth
from backend.database import get_db
from backend.routes.profile import cache_stats

bp = Blueprint("library", __name__, url_prefix="/api")


@bp.route("/library", methods=["GET"])
@require_auth
def get_library():
    db = get_db()
    rows = db.execute(
        """SELECT l.platform, l.title, l.is_fav, l.status, l.notes, l.user_rating,
                  l.updated_at, COALESCE(t.runtime_mins, 0) AS runtime_mins
           FROM library l
           LEFT JOIN titles t ON t.platform = l.platform AND t.title = l.title
           WHERE l.user_id=?""",
        (g.current_user["user_id"],),
    ).fetchall()
    return jsonify({"library": [dict(r) for r in rows]})


@bp.route("/library", methods=["POST"])
@require_auth
def upsert_library():
    data = request.get_json(silent=True) or {}
    platform = (data.get("platform") or "").strip()
    title = (data.get("title") or "").strip()
    if not platform or not title:
        return jsonify({"error": "platform and title required"}), 400

    status = data.get("status", "not-started")
    if status not in ("not-started", "watching", "finished", "watchlist"):
        return jsonify({"error": "Invalid status"}), 400

    user_rating = int(data.get("user_rating") or 0)
    if not (0 <= user_rating <= 5):
        return jsonify({"error": "user_rating must be 0-5"}), 400

    db = get_db()
    db.execute(
        """INSERT INTO library (user_id, platform, title, is_fav, status, notes, user_rating, updated_at)
           VALUES (?,?,?,?,?,?,?,datetime('now'))
           ON CONFLICT(user_id, platform, title) DO UPDATE SET
               is_fav=excluded.is_fav,
               status=excluded.status,
               notes=excluded.notes,
               user_rating=excluded.user_rating,
               updated_at=excluded.updated_at""",
        (
            g.current_user["user_id"],
            platform,
            title,
            int(bool(data.get("is_fav", False))),
            status,
            data.get("notes"),
            user_rating,
        ),
    )
    db.commit()
    cache_stats(db, g.current_user["user_id"])
    return jsonify({"ok": True})


@bp.route("/ratings", methods=["GET"])
@require_auth
def get_ratings():
    """Return all titles the user has rated (user_rating > 0) with TMDB-friendly fields."""
    uid = g.current_user["user_id"]
    db = get_db()
    sort = request.args.get("sort", "rating")  # rating | title | year

    order_map = {
        "rating": "l.user_rating DESC, l.updated_at DESC",
        "title": "l.title ASC",
        "year": "CAST(MAX(t.release_year) AS INTEGER) DESC",
    }
    order = order_map.get(sort, order_map["rating"])

    rows = db.execute(
        f"""SELECT l.platform, l.title, l.user_rating, l.status, l.is_fav,
                   MAX(t.content_type)  AS content_type,
                   MAX(t.release_year)  AS year,
                   MAX(t.imdb_score)    AS imdb_score,
                   MAX(t.tomatometer)   AS tomatometer,
                   MAX(t.genre)         AS genre
            FROM library l
            LEFT JOIN titles t ON t.platform = l.platform AND t.title = l.title
            WHERE l.user_id = ? AND l.user_rating > 0
            GROUP BY l.platform, l.title
            ORDER BY {order}""",
        (uid,),
    ).fetchall()
    return jsonify({"ratings": [dict(r) for r in rows]})


@bp.route("/titles/runtime", methods=["PATCH"])
@require_auth
def save_runtime():
    """Save TMDB-sourced runtime to the titles table."""
    data = request.get_json(silent=True) or {}
    platform = (data.get("platform") or "").strip()
    title = (data.get("title") or "").strip()
    runtime = int(data.get("runtime_mins") or 0)
    if not platform or not title or runtime <= 0:
        return jsonify({"ok": False}), 200  # silent no-op
    db = get_db()
    db.execute(
        "UPDATE titles SET runtime_mins=? WHERE platform=? AND title=? AND runtime_mins=0",
        (runtime, platform, title),
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route("/titles/end_year", methods=["PATCH"])
@require_auth
def save_end_year():
    """Persist TMDB-sourced end year for an ended TV show."""
    data = request.get_json(silent=True) or {}
    platform = (data.get("platform") or "").strip()
    title = (data.get("title") or "").strip()
    end_year = (data.get("end_year") or "").strip()
    if not platform or not title or not end_year:
        return jsonify({"ok": False}), 200
    db = get_db()
    db.execute(
        "UPDATE titles SET end_year=? WHERE platform=? AND title=? AND (end_year IS NULL OR end_year='')",
        (end_year, platform, title),
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route("/titles/is_ongoing", methods=["PATCH"])
@require_auth
def save_is_ongoing():
    """Persist TMDB-sourced ongoing status for a TV show."""
    data = request.get_json(silent=True) or {}
    platform = (data.get("platform") or "").strip()
    title = (data.get("title") or "").strip()
    is_ongoing = data.get("is_ongoing")
    if not platform or not title or is_ongoing is None:
        return jsonify({"ok": False}), 200
    db = get_db()
    db.execute(
        "UPDATE titles SET is_ongoing=? WHERE platform=? AND title=? AND is_ongoing IS NULL",
        (1 if is_ongoing else 0, platform, title),
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route("/watched", methods=["GET"])
@require_auth
def get_watched():
    platform = request.args.get("platform", "").strip()
    title = request.args.get("title", "").strip()
    uid = g.current_user["user_id"]
    db = get_db()

    # If both platform and title are given, return episodes for that specific show.
    # Otherwise return everything the user has ever marked as watched.
    if platform and title:
        rows = db.execute(
            "SELECT season_num, ep_mask FROM watched_seasons WHERE user_id=? AND platform=? AND title=?",
            (uid, platform, title),
        ).fetchall()
        watched = []
        for r in rows:
            for bit in range(62):
                if r["ep_mask"] & (1 << bit):
                    watched.append(
                        {
                            "item_type": "episode",
                            "season_num": r["season_num"],
                            "episode_num": bit + 1,
                        }
                    )
    else:
        rows = db.execute(
            "SELECT platform, title, season_num, ep_mask FROM watched_seasons WHERE user_id=?",
            (uid,),
        ).fetchall()
        watched = []
        for r in rows:
            for bit in range(62):
                if r["ep_mask"] & (1 << bit):
                    watched.append(
                        {
                            "platform": r["platform"],
                            "title": r["title"],
                            "item_type": "episode",
                            "season_num": r["season_num"],
                            "episode_num": bit + 1,
                        }
                    )

    return jsonify({"watched": watched})


@bp.route("/watched", methods=["POST"])
@require_auth
def set_watched():
    data = request.get_json(silent=True) or {}
    platform = (data.get("platform") or "").strip()
    title = (data.get("title") or "").strip()
    if not platform or not title:
        return jsonify({"error": "platform and title required"}), 400

    item_type = data.get("item_type", "episode")
    season_num = int(data.get("season_num", 0))
    episode_num = int(data.get("episode_num", 0))
    runtime_mins = max(0, int(data.get("runtime_mins") or 0))
    watched = bool(data.get("watched", True))
    uid = g.current_user["user_id"]
    db = get_db()

    if watched:
        ep_bit = (1 << (episode_num - 1)) if 1 <= episode_num <= 62 else 0
        db.execute(
            """INSERT INTO watched_seasons
                   (user_id, platform, title, season_num, ep_mask, runtime_mins, updated_at)
               VALUES (?,?,?,?,?,?,datetime('now'))
               ON CONFLICT(user_id, platform, title, season_num)
               DO UPDATE SET ep_mask      = ep_mask | excluded.ep_mask,
                             runtime_mins = runtime_mins + excluded.runtime_mins,
                             updated_at   = datetime('now')""",
            (uid, platform, title, season_num, ep_bit, runtime_mins),
        )
    else:
        ep_bit = (1 << (episode_num - 1)) if 1 <= episode_num <= 62 else 0
        ep_bit_not = ~ep_bit  # two's-complement NOT for bitwise AND clear
        db.execute(
            """UPDATE watched_seasons
               SET ep_mask      = ep_mask & ?,
                   runtime_mins = MAX(0, runtime_mins - ?),
                   updated_at   = datetime('now')
               WHERE user_id=? AND platform=? AND title=? AND season_num=?""",
            (ep_bit_not, runtime_mins, uid, platform, title, season_num),
        )
        # clean up fully-unwatched season rows
        db.execute(
            """DELETE FROM watched_seasons
               WHERE user_id=? AND platform=? AND title=? AND season_num=? AND ep_mask=0""",
            (uid, platform, title, season_num),
        )

    db.commit()
    cache_stats(db, uid)
    return jsonify({"ok": True})


@bp.route("/watched/backfill", methods=["PATCH"])
@require_auth
def backfill_episode_runtimes():
    """Bulk-update runtime_mins for watched seasons.
    Expects: { "updates": [{"platform","title","season_num","runtime_mins"}, ...] }
    Overwrites the season total (computed from TMDB) for seasons that exist.
    """
    data = request.get_json(silent=True) or {}
    updates = data.get("updates") or []
    if not updates:
        return jsonify({"ok": True, "updated": 0})

    uid = g.current_user["user_id"]
    db = get_db()
    count = 0
    for u in updates[:2000]:  # hard cap
        mins = max(0, int(u.get("runtime_mins") or 0))
        if mins <= 0:
            continue
        cur = db.execute(
            """UPDATE watched_seasons
               SET runtime_mins=?, updated_at=datetime('now')
               WHERE user_id=? AND platform=? AND title=? AND season_num=?""",
            (
                mins,
                uid,
                str(u.get("platform", "")).strip(),
                str(u.get("title", "")).strip(),
                int(u.get("season_num", 0)),
            ),
        )
        count += cur.rowcount
    db.commit()
    if count > 0:
        cache_stats(db, uid)
    return jsonify({"ok": True, "updated": count})
