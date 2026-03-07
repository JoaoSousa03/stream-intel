import os
from flask import Blueprint, send_file, abort

well_known_bp = Blueprint("well_known", __name__)


@well_known_bp.route("/.well-known/assetlinks.json")
def assetlinks():
    path = os.path.join(os.path.dirname(__file__), "../../.well-known/assetlinks.json")
    path = os.path.abspath(path)
    if os.path.exists(path):
        return send_file(path, mimetype="application/json")
    abort(404)
