"""A small ListenBrainz-compatible API, so players can scrobble straight to WAYL.

Navidrome: set ND_LISTENBRAINZ_BASEURL=<APP_URL>/listenbrainz/1/ and paste your WAYL scrobble
token in Navidrome's "Scrobble to ListenBrainz" setting. Any other app that lets you change the
ListenBrainz server URL works the same way.

Only the two endpoints scrobblers use are implemented: validate-token and submit-listens.
"""
import threading
import time
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from app.models import db, utcnow
from app.models.server import IncomingListen, ListenToken
from app.models.user import UserModel
from app.services import catalog
from app.services.matching import process_incoming
from app.services.sync import process_pending
from app.utility import hash_token, limiter

lb_bp = Blueprint("listenbrainz", __name__, url_prefix="/listenbrainz/1")

LISTEN_MINIMUM_TS = 1033430400  # from the ListenBrainz docs
MAX_LISTENS = 1000
INLINE = 3  # match this many right away; the rest is done in the background


def _error(code, message):
    return jsonify({"code": code, "error": message}), code


def _token_from_request():
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("token "):
        return header[6:].strip()
    return request.args.get("token", "").strip() or None


def _user_for(token):
    if not token:
        return None
    row = ListenToken.query.filter_by(token_hash=hash_token(token)).first()
    if row is None:
        return None
    row.last_used_at = utcnow()
    return db.session.get(UserModel, row.user_id)


@lb_bp.get("/validate-token")
@limiter.limit("60 per minute")
def validate_token():
    token = _token_from_request()
    if not token:
        return _error(400, "You need to provide an Authorization token.")
    user = _user_for(token)
    db.session.commit()
    if user is None:
        return jsonify({"code": 200, "message": "Token invalid.", "valid": False})
    return jsonify({"code": 200, "message": "Token valid.", "valid": True, "user_name": user.username})


def _source(info):
    client = " ".join(str(info.get(k) or "") for k in ("media_player", "submission_client")).lower()
    if "navidrome" in client:
        return "navidrome"
    if "plex" in client:
        return "plex"
    return "scrobbler"


@lb_bp.post("/submit-listens")
@limiter.limit("120 per minute")
def submit_listens():
    user = _user_for(_token_from_request())
    if user is None:
        db.session.commit()
        return _error(401, "Invalid authorization token.")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error(400, "Cannot parse JSON document.")
    listen_type = body.get("listen_type")
    payload = body.get("payload")
    if listen_type not in ("single", "import", "playing_now") or not isinstance(payload, list) or not payload:
        return _error(400, "JSON document must contain listen_type and a non-empty payload list.")
    if len(payload) > MAX_LISTENS or (listen_type != "import" and len(payload) != 1):
        return _error(400, "Too many listens in this request.")
    if listen_type == "playing_now":
        db.session.commit()
        return jsonify({"status": "ok"})  # WAYL only stores finished listens

    now = time.time()
    rows = []
    for item in payload:
        meta = (item or {}).get("track_metadata") or {}
        artist, title = meta.get("artist_name"), meta.get("track_name")
        listened_at = (item or {}).get("listened_at")
        if not isinstance(artist, str) or not isinstance(title, str) or not artist.strip() or not title.strip():
            return _error(400, "track_metadata.artist_name and track_name are required.")
        if not isinstance(listened_at, int) or not LISTEN_MINIMUM_TS <= listened_at <= now + 300:
            return _error(400, "listened_at must be a unix timestamp.")
        info = meta.get("additional_info") if isinstance(meta.get("additional_info"), dict) else {}
        duration = info.get("duration_ms")
        duration = round(duration / 1000) if isinstance(duration, (int, float)) and duration > 0 else (
            info.get("duration") if isinstance(info.get("duration"), int) else None
        )
        mbid = str(info.get("recording_mbid") or "").lower()
        release = meta.get("release_name")
        rows.append(IncomingListen(
            user_id=user.id,
            source=_source(info),
            artist=artist.strip()[:300],
            title=title.strip()[:300],
            album=release.strip()[:300] if isinstance(release, str) and release.strip() else None,
            mbid=mbid if catalog.is_mbid(mbid) else None,
            duration=duration if duration and duration < 86_400 else None,
            listened_at=datetime.fromtimestamp(listened_at, timezone.utc).replace(tzinfo=None),
            status="pending",
        ))
    db.session.add_all(rows)
    db.session.commit()

    for row in rows[:INLINE]:
        try:
            process_incoming(row)
            db.session.commit()
        except catalog.CatalogError:
            db.session.rollback()
            break  # stays pending; the worker retries
    if len(rows) > INLINE:
        _process_later(user.id)
    return jsonify({"status": "ok"})


def _process_later(user_id):
    app = current_app._get_current_object()
    if app.testing:
        process_pending(limit=MAX_LISTENS, user_id=user_id)
        return

    def run():
        with app.app_context():
            process_pending(limit=MAX_LISTENS, user_id=user_id)

    threading.Thread(target=run, daemon=True, name="lb-import").start()
