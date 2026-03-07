# backend/app.py
import logging
from flask import Flask, send_from_directory, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from backend.config import settings
from backend.database import init_db, close_db
from backend.routes import all_blueprints
from pathlib import Path


def _suppress_root_post_logs() -> None:
    """Monkey-patch WSGIRequestHandler.log_request to silently drop
    POST / access-log entries.  This is more reliable than a logging
    Filter because it intercepts at the source, before Werkzeug's dev
    server has a chance to reconfigure the werkzeug logger or its handlers."""
    try:
        from werkzeug.serving import WSGIRequestHandler

        _original = WSGIRequestHandler.log_request

        def _patched(self, code="-", size="-"):
            if (
                getattr(self, "command", None) == "POST"
                and getattr(self, "path", None) == "/"
            ):
                return  # silently drop POST / noise
            _original(self, code, size)

        WSGIRequestHandler.log_request = _patched
    except Exception:
        pass  # not in dev-server context (e.g. gunicorn) — nothing to patch


_suppress_root_post_logs()


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(settings.UI_DIR))
    app.secret_key = settings.SECRET_KEY

    # Trust the X-Forwarded-Proto/Host headers from Railway's proxy so that
    # request.url_root returns https://... instead of http://...
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Register teardown
    app.teardown_appcontext(close_db)

    # Register all blueprints
    for bp in all_blueprints:
        app.register_blueprint(bp)

    # Serve the frontend
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_ui(path):
        from flask import make_response

        target = settings.UI_DIR / path
        if path and target.exists():
            resp = make_response(send_from_directory(str(settings.UI_DIR), path))
            # CSS/JS: revalidate every time so stale assets are never served
            if path.endswith((".css", ".js")):
                resp.headers["Cache-Control"] = "no-cache, must-revalidate"
            return resp
        resp = make_response(send_from_directory(str(settings.UI_DIR), "index.html"))
        # HTML: never cache — always fetch fresh so asset references stay current
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # explicitly handle POSTs to root to avoid Werkzeug logging them as 405s
    @app.route("/", methods=["POST"])
    def reject_root_post():
        from flask import jsonify

        return jsonify({"error": "Method not allowed"}), 405

    # Initialise or migrate the database
    # init_db() will create the file if missing or apply migrations otherwise.
    with app.app_context():
        init_db()

    # global handler for 405 so we can log the offending requests
    @app.errorhandler(405)
    def method_not_allowed(e):
        # ignore noisy POSTs to root that browsers sometimes send
        from flask import request

        path = request.path
        if not (path == "/" and request.method == "POST"):
            # only log API-related 405s at warning level; others as debug
            msg = f"405 on {request.method} {path}"
            if path.startswith("/api"):
                app.logger.warning(msg)
            else:
                app.logger.debug(msg)
        return jsonify({"error": "Method not allowed"}), 405

    return app
