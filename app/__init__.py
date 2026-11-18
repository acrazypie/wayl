import sqlite3

from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from werkzeug.middleware.proxy_fix import ProxyFix

import app.models.music  # noqa: F401  (register every table with SQLAlchemy / Alembic)
import app.models.server  # noqa: F401
from app.api import register_routes
from app.api.listenbrainz import lb_bp
from app.models import db
from app.models.user import UserModel
from app.routes.main import main_bp
from app.routes.stream import stream_bp

from .utility import config, limiter

app = Flask(__name__)

if config.TRUST_PROXY_HOPS:
    # Behind a reverse proxy (Caddy, nginx, Traefik...): trust its X-Forwarded-* headers.
    hops = config.TRUST_PROXY_HOPS
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops, x_prefix=hops)

secure = config.APP_URL.startswith("https://")
app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = secure
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_SECURE"] = secure
app.config["RATELIMIT_ENABLED"] = config.RATELIMIT_ENABLED
app.config["RATELIMIT_HEADERS_ENABLED"] = True
app.secret_key = config.SECRET_KEY

login_manager = LoginManager(app)


@login_manager.user_loader
def load_user(session_id):
    """Session ids look like "<user id>:<session version>"; a stale version means signed out."""
    try:
        user_id, version = str(session_id).split(":", 1)
        user = db.session.get(UserModel, int(user_id))
        if user is None or int(version) != (user.session_version or 0):
            return None
        return user
    except (TypeError, ValueError):
        return None


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    """The web app and the worker share one SQLite file: WAL lets them read and write together."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


db.init_app(app)
Migrate(app, db, render_as_batch=True)  # batch mode: SQLite-friendly ALTER TABLE
limiter.init_app(app)


@app.errorhandler(429)
def too_many_requests(_error):
    return {"error": "Too many attempts. Please wait a bit and try again."}, 429


@app.get("/healthz")
@limiter.exempt
def healthz():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return {"status": "error", "database": "unreachable"}, 503
    return {"status": "ok"}


register_routes(app)

app.register_blueprint(main_bp)
app.register_blueprint(stream_bp)
app.register_blueprint(lb_bp)
