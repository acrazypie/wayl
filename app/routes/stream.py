"""GET /api/stream/<track id>: play a track from your own server through WAYL.

The browser never sees the server's address or credentials: WAYL fetches the audio and passes
it through, including Range requests so seeking works.
"""
import requests
from flask import Blueprint, Response, abort, request, stream_with_context

from app.models import db
from app.models.server import ServerTrack
from app.services.media import MediaServerError, RemoteTrack, client_for
from app.services.media.base import USER_AGENT
from app.utility import get_current_user

stream_bp = Blueprint("stream", __name__)

PASS_HEADERS = ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "Last-Modified", "ETag")
CHUNK = 64 * 1024


@stream_bp.get("/api/stream/<int:track_id>")
@stream_bp.get("/api/v1/stream/<int:track_id>")
def stream(track_id):
    user, _ = get_current_user()
    st = db.session.get(ServerTrack, track_id)
    if user is None or st is None or st.server.user_id != user.id:
        abort(404)  # other people's tracks look missing
    try:
        client = client_for(st.server)
        url, params, headers = client.stream_request(
            RemoteTrack(remote_id=st.remote_id, title=st.title, artist=st.artist, stream_key=st.stream_key)
        )
    except MediaServerError as exc:
        return {"error": str(exc)}, 502
    headers = {"User-Agent": USER_AGENT, **headers}
    if request.headers.get("Range"):
        headers["Range"] = request.headers["Range"]
    try:
        upstream = requests.get(url, params=params, headers=headers, stream=True, timeout=(5, 60))
    except requests.RequestException:
        return {"error": "Your music server is not reachable right now"}, 502
    if upstream.status_code not in (200, 206):
        upstream.close()
        return {"error": f"Your music server refused to stream this track (HTTP {upstream.status_code})"}, 502
    content_type = upstream.headers.get("Content-Type", "")
    if content_type.startswith(("text/", "application/json", "application/xml")):
        upstream.close()  # Subsonic reports errors as a 200 with a JSON/XML body
        return {"error": "Your music server couldn't stream this track"}, 502

    def body():
        try:
            yield from upstream.iter_content(CHUNK)
        finally:
            upstream.close()

    out = Response(stream_with_context(body()), status=upstream.status_code, direct_passthrough=True)
    for name in PASS_HEADERS:
        if name in upstream.headers:
            out.headers[name] = upstream.headers[name]
    out.headers.setdefault("Accept-Ranges", "bytes")
    out.headers["Cache-Control"] = "private, max-age=3600"
    out.headers["X-Content-Type-Options"] = "nosniff"
    return out
