"""Public, read-only share documents: GET /share/v1/p/<token> and /share/v1/u/<token>.

No auth and nothing user-specific: the token in the URL is the capability. These views never
look at the session or the current user, so the response is the same for everybody.
"""
import hashlib
import json
from datetime import datetime, timezone

from flask import Blueprint, Response, request
from werkzeug.http import http_date

from app.models.music import Playlist
from app.models.sharing import ShareSettings
from app.services.share_docs import playlist_doc, playlist_jspf, profile_doc
from app.utility import limiter

share_bp = Blueprint("share", __name__, url_prefix="/share/v1")

TOKEN_MAX = 32


def _response(status, body=b"", headers=None):
    resp = Response(body, status=status, mimetype="application/json" if body else None)
    resp.headers["Access-Control-Allow-Origin"] = "*"  # read-only and cookie-free
    resp.headers["X-Content-Type-Options"] = "nosniff"
    for k, v in (headers or {}).items():
        resp.headers[k] = v
    return resp


def _encode(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()


def _not_found():
    return _response(404, _encode({"error": "This share link doesn't exist or was turned off."}), {"Cache-Control": "no-store"})


def _document(data, updated_at):
    """200 with caching headers, or 304 when the client already has this exact body."""
    body = _encode(data)
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00")) if updated_at else datetime.now(timezone.utc)
    headers = {"ETag": etag, "Last-Modified": http_date(updated), "Cache-Control": "public, max-age=300"}
    if etag in [t.strip() for t in request.headers.get("If-None-Match", "").split(",")]:
        return _response(304, headers=headers)
    return _response(200, body, headers)


@share_bp.get("/p/<token>")
@limiter.limit("60 per minute")
def shared_playlist(token):
    playlist = Playlist.query.filter_by(share_token=token).first() if len(token) <= TOKEN_MAX else None
    if playlist is None:
        return _not_found()
    doc = playlist_doc(playlist)
    if request.args.get("format") == "jspf":
        return _document(playlist_jspf(doc), doc["updated_at"])
    return _document(doc, doc["updated_at"])


@share_bp.get("/u/<token>")
@limiter.limit("60 per minute")
def shared_profile(token):
    settings = ShareSettings.query.filter_by(profile_share_token=token).first() if len(token) <= TOKEN_MAX else None
    if settings is None:
        return _not_found()
    doc = profile_doc(settings)
    return _document(doc, doc["updated_at"])
