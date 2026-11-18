import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from dotenv import load_dotenv
from flask import g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import current_user

from app.models import db

load_dotenv()

log = logging.getLogger(__name__)


def _secret_key():
    """SECRET_KEY from the environment, else from SECRET_KEY_FILE (created on first start, which
    is what the Docker image does), else a random one that only lasts until restart."""
    key = os.getenv("SECRET_KEY")
    if key:
        return key
    path = os.getenv("SECRET_KEY_FILE")
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                key = fh.read().strip()
        except FileNotFoundError:
            key = secrets.token_hex(32)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(key)
            log.warning("Generated a new SECRET_KEY in %s. Keep this file: it also encrypts media server logins.", path)
        except FileExistsError:  # another process created it at the same moment
            with open(path, encoding="utf-8") as fh:
                key = fh.read().strip()
        if key:
            return key
    log.warning("SECRET_KEY is not set: using a random key, so sessions and tokens reset on restart.")
    return secrets.token_hex(32)


def _flag(name, default="0"):
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = _secret_key()
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///database.db")

    # Public base URL of the app. Used to build password-reset links, never taken from the
    # request's Host header (that would let an attacker point reset links at their own site).
    APP_URL = os.getenv("APP_URL", "http://localhost:5000").rstrip("/")

    # Outgoing mail (password resets). If MAIL_SERVER is empty, emails are logged instead.
    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_FROM = os.getenv("MAIL_FROM", "") or os.getenv("MAIL_USERNAME", "") or "wayl@localhost"
    MAIL_USE_SSL = _flag("MAIL_USE_SSL")  # port 465
    MAIL_USE_TLS = _flag("MAIL_USE_TLS", "1")  # STARTTLS, port 587

    PASSWORD_RESET_MAX_AGE = 60 * 60  # seconds

    # Music catalog (MusicBrainz / ListenBrainz). They ask for a meaningful User-Agent.
    CATALOG_USER_AGENT = os.getenv("CATALOG_USER_AGENT", "WAYL/1.0 (self-hosted music log)")
    CATALOG_TIMEOUT = float(os.getenv("CATALOG_TIMEOUT", "8"))

    # Number of reverse proxies in front of the app (X-Forwarded-* headers are trusted only then).
    TRUST_PROXY_HOPS = int(os.getenv("TRUST_PROXY_HOPS", "0"))

    # Media servers (Plex / Navidrome). Self-hosted servers usually live on the local network, so
    # private addresses are allowed by default; turn this off on a public, multi-user instance.
    ALLOW_PRIVATE_SERVER_URLS = _flag("ALLOW_PRIVATE_SERVER_URLS", "1")
    HISTORY_IMPORT_DAYS = int(os.getenv("HISTORY_IMPORT_DAYS", "30"))  # first Plex sync looks back this far
    WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL", "60"))  # seconds between worker rounds
    PLEX_HISTORY_INTERVAL = int(os.getenv("PLEX_HISTORY_INTERVAL", "300"))
    PLAYLIST_SYNC_INTERVAL = int(os.getenv("PLAYLIST_SYNC_INTERVAL", str(6 * 3600)))

    RATELIMIT_ENABLED = _flag("RATELIMIT_ENABLED", "1")
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")


config = Config()

limiter = Limiter(key_func=get_remote_address, storage_uri=config.RATELIMIT_STORAGE_URI)


# --- Tokens ---------------------------------------------------------------


def create_jwt(user, expires_in=3600, refresh=False):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "ver": user.session_version or 0,
        "type": "refresh" if refresh else "access",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")


def verify_jwt(token, expected_type="access"):
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:  # includes expired signatures
        return None
    if payload.get("type") != expected_type:
        return None
    return payload


def user_from_jwt_payload(payload):
    """The user a token belongs to, or None if the user is gone or has changed password since."""
    from app.models.user import UserModel

    try:
        user = db.session.get(UserModel, int(payload["sub"]))
    except (KeyError, TypeError, ValueError):
        return None
    if user is None or payload.get("ver", 0) != (user.session_version or 0):
        return None
    return user


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


# --- Auth -----------------------------------------------------------------

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def get_current_user():
    """Return (user, how) from a Bearer token or the login session, or (None, None)."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        payload = verify_jwt(header[7:].strip())
        user = user_from_jwt_payload(payload) if payload else None
        return (user, "bearer") if user else (None, None)
    if current_user.is_authenticated:
        return current_user._get_current_object(), "session"
    return None, None


def json_only(fn):
    """Reject non-JSON writes. Browsers cannot send application/json cross-site without a CORS
    preflight, so this blocks CSRF via plain HTML forms."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method in MUTATING_METHODS and request.mimetype != "application/json":
            return {"error": "Content-Type must be application/json"}, 415
        return fn(*args, **kwargs)

    return wrapper


def auth_required(fn):
    """Require a signed-in user; exposes it as g.current_user.

    Cookie-authenticated writes must send Content-Type: application/json (see json_only).
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user, how = get_current_user()
        if user is None:
            return {"error": "Authentication required"}, 401
        if how == "session" and request.method in MUTATING_METHODS and request.mimetype != "application/json":
            return {"error": "Content-Type must be application/json"}, 415
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


# --- Small helpers --------------------------------------------------------


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def int_arg(name, default, lo, hi):
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(lo, min(hi, value))


def iso(dt):
    """Naive-UTC datetime -> '2026-10-10T12:00:00Z'."""
    return dt.replace(microsecond=0).isoformat() + "Z" if dt else None
