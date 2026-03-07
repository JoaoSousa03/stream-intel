# run.py  — project entry point
# Usage: python run.py
import os
from dotenv import load_dotenv

load_dotenv()  # reads .env into os.environ if the file exists (safe to run even if missing)

from backend.app import create_app
from werkzeug.serving import run_simple, WSGIRequestHandler

# app is a module-level name so gunicorn can find it: gunicorn run:app
app = create_app()


# define a request handler that drops the noisy POST / 405 entries
class QuietHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        if self.path == "/" and self.command == "POST" and str(code).startswith("405"):
            return
        super().log_request(code, size)


if __name__ == "__main__":
    # Railway (and most PaaS hosts) inject PORT into the environment.
    # Locally we default to 5000 and bind only to localhost.
    port = int(os.environ.get("PORT", 5000))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"

    try:
        run_simple(
            host,
            port,
            app,
            request_handler=QuietHandler,
            use_reloader=False,
            use_debugger=False,
            threaded=True,
        )
    except TypeError:
        # fallback for older werkzeug versions
        app.run(debug=False, host=host, port=port, threaded=True)
