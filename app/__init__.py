import sqlite3

from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from werkzeug.middleware.proxy_fix import ProxyFix

import app.models.music  # noqa: F401  (register every table with SQLAlchemy / Alembic)
import app.models.server  # noqa: F401
import app.models.social  # noqa: F401  (always: keeps the follows table even with social off)
from app.api import register_routes
from app.api.listenbrainz import lb_bp
from app.models import db
from app.models.user import UserModel
from app.routes.main import main_bp
from app.routes.stream import stream_bp

from .utility import config, limiter


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    """The web app and the worker share one SQLite file: WAL lets them read and write together."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def _load_user(session_id):
    """Session ids look like "<user id>:<session version>"; a stale version means signed out."""
    try:
        user_id, version = str(session_id).split(":", 1)
        user = db.session.get(UserModel, int(user_id))
        if user is None or int(version) != (user.session_version or 0):
            return None
        return user
    except (TypeError, ValueError):
        return None


def create_app(config_overrides=None):
    """Build the Flask app. `config_overrides` (a dict of app.config keys) is mostly for tests,
    e.g. create_app({"SOCIAL_ENABLED": True}); production reads everything from the env."""
    flask_app = Flask(__name__)

    if config.TRUST_PROXY_HOPS:
        # Behind a reverse proxy (Caddy, nginx, Traefik...): trust its X-Forwarded-* headers.
        hops = config.TRUST_PROXY_HOPS
        flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops, x_prefix=hops)

    secure = config.APP_URL.startswith("https://")
    flask_app.config.update(
        SQLALCHEMY_DATABASE_URI=config.DATABASE_URL,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=secure,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=secure,
        RATELIMIT_ENABLED=config.RATELIMIT_ENABLED,
        RATELIMIT_HEADERS_ENABLED=True,
        SOCIAL_ENABLED=config.SOCIAL_ENABLED,
        SECRET_KEY=config.SECRET_KEY,
    )
    flask_app.config.update(config_overrides or {})

    login_manager = LoginManager(flask_app)
    login_manager.user_loader(_load_user)

    db.init_app(flask_app)
    Migrate(flask_app, db, render_as_batch=True)  # batch mode: SQLite-friendly ALTER TABLE
    limiter.init_app(flask_app)

    @flask_app.errorhandler(429)
    def too_many_requests(_error):
        return {"error": "Too many attempts. Please wait a bit and try again."}, 429

    @flask_app.get("/healthz")
    @limiter.exempt
    def healthz():
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            return {"status": "error", "database": "unreachable"}, 503
        return {"status": "ok"}

    register_routes(flask_app)
    flask_app.register_blueprint(main_bp)
    flask_app.register_blueprint(stream_bp)
    flask_app.register_blueprint(lb_bp)
    return flask_app


# What gunicorn ("app:app"), the worker and `flask --app app` use.
app = create_app()
