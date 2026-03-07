# backend/routes/__init__.py
from backend.routes.auth import bp as auth_bp
from backend.routes.titles import bp as titles_bp
from backend.routes.library import bp as library_bp
from backend.routes.admin import bp as admin_bp
from backend.routes.profile import bp as profile_bp
from backend.routes.friends import bp as friends_bp

all_blueprints = [auth_bp, titles_bp, library_bp, admin_bp, profile_bp, friends_bp]
