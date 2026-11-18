"""Fetch and validate share documents from other WAYL instances.

Every remote request goes through fetch() -> _http_get(); tests replace _http_get. Remote data
is untrusted: parse_document() keeps only known fields, with type and length caps, and drops bad
items instead of failing the whole document. See docs/sharing-protocol.md.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import requests

from app.services.catalog import is_mbid
from app.services.media.base import UnsafeURL, check_fetch_url
from app.version import APP_VERSION

MAX_BYTES = 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = (5, 15)  # connect, read
MAX_TRACKS, MAX_LISTENS, MAX_TOP_ARTISTS, MAX_PLAYLISTS = 500, 50, 10, 200
TITLE, NAME, URL_MAX, BIO = 300, 60, 500, 300

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_session = requests.Session()


class ShareError(Exception):
    """Couldn't get a valid share document; the message is safe to show the user."""


@dataclass
class Fetched:
    status: int  # 200 or 304
    doc: dict = None  # validated document (None on 304)
    etag: str = None
    last_modified: str = None


def normalize_share_url(url):
    try:
        return check_fetch_url(url, default_scheme="https")
    except UnsafeURL as exc:
        raise ShareError(str(exc)) from exc


def _http_get(url, headers):
    """One GET without following redirects; returns a streaming response. Tests replace this."""
    return _session.get(url, headers=headers, timeout=TIMEOUT, stream=True, allow_redirects=False)


def fetch(url, etag=None, last_modified=None):
    """GET a share document: validated URL (and every redirect), size and type limits, and
    conditional request headers. Returns Fetched, or raises ShareError."""
    current = normalize_share_url(url)
    headers = {"Accept": "application/json", "User-Agent": f"WAYL/{APP_VERSION} (share reader)"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    for _ in range(MAX_REDIRECTS + 1):
        try:
            res = _http_get(current, headers)
        except requests.RequestException as exc:
            raise ShareError(f"Couldn't reach {current.split('/')[2]} ({exc.__class__.__name__})") from exc
        try:
            if res.status_code in (301, 302, 303, 307, 308):
                location = res.headers.get("Location")
                if not location:
                    raise ShareError("The link redirected nowhere")
                try:
                    current = check_fetch_url(urljoin(current, location), default_scheme="https")
                except UnsafeURL as exc:
                    raise ShareError(f"The link redirected somewhere WAYL won't go: {exc}") from exc
                continue
            if res.status_code == 304:
                return Fetched(304, None, etag, last_modified)
            if res.status_code == 404:
                raise ShareError("This share link doesn't exist any more (it may have been turned off)")
            if res.status_code != 200:
                raise ShareError(f"The other instance answered HTTP {res.status_code}")
            if "json" not in res.headers.get("Content-Type", "").lower():
                raise ShareError("That address isn't a WAYL share link")
            body = bytearray()
            for chunk in res.iter_content(64 * 1024):
                body += chunk
                if len(body) > MAX_BYTES:
                    raise ShareError("The shared document is too big (over 1 MB)")
            try:
                data = json.loads(bytes(body))
            except ValueError as exc:
                raise ShareError("That address isn't a WAYL share link") from exc
            return Fetched(200, parse_document(data), res.headers.get("ETag"), res.headers.get("Last-Modified"))
        finally:
            res.close()
    raise ShareError("Too many redirects")


# --- validation ------------------------------------------------------------------------------


def _str(value, limit):
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())  # no control characters or runs of whitespace
    return value[:limit] or None


def _url(value):
    if not isinstance(value, str) or len(value) > URL_MAX or not value.startswith(("https://", "http://")):
        return None
    return value


def _mbid(value):
    value = value.lower() if isinstance(value, str) else None
    return value if is_mbid(value) else None


def _time(value):
    if not isinstance(value, str) or not _ISO.match(value):
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


def _int(value, lo=0, hi=10**9):
    return value if isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi else None


def _track(t):
    if not isinstance(t, dict):
        return None
    mbid, title, artist = _mbid(t.get("mbid")), _str(t.get("title"), TITLE), _str(t.get("artist"), TITLE)
    if not (mbid and title and artist):
        return None
    return {
        "mbid": mbid,
        "title": title,
        "artist": artist,
        "artist_mbid": _mbid(t.get("artist_mbid")),
        "album": _str(t.get("album"), TITLE),
        "cover": _url(t.get("cover")),
        "duration": _int(t.get("duration"), 1, 86_400),
    }


def _list(value, limit):
    return value[: limit * 4] if isinstance(value, list) else []  # bound the work on junk input


def parse_document(data):
    """Validated copy of a share document, or ShareError."""
    if not isinstance(data, dict) or data.get("wayl_share") != 1:
        raise ShareError("That address isn't a WAYL share link (or uses a newer format)")
    kind = data.get("kind")
    if kind not in ("playlist", "profile"):
        raise ShareError("Unknown kind of share link")
    name = _str(data.get("name"), TITLE if kind == "playlist" else NAME)
    if not name:
        raise ShareError("The shared document has no name")
    doc = {
        "wayl_share": 1,
        "kind": kind,
        "id": _str(data.get("id"), 64),
        "url": _url(data.get("url")),
        "name": name,
        "updated_at": _time(data.get("updated_at")),
    }
    if kind == "playlist":
        owner = data.get("owner") if isinstance(data.get("owner"), dict) else {}
        doc["owner"] = {"name": _str(owner.get("name"), NAME), "profile_url": _url(owner.get("profile_url"))}
        doc["tracks"] = [t for t in map(_track, _list(data.get("tracks"), MAX_TRACKS)) if t][:MAX_TRACKS]
        return doc

    doc["bio"] = _str(data.get("bio"), BIO)
    playlists = []
    for p in _list(data.get("playlists"), MAX_PLAYLISTS):
        if isinstance(p, dict) and _url(p.get("url")) and _str(p.get("name"), TITLE):
            playlists.append({
                "name": _str(p["name"], TITLE),
                "url": _url(p["url"]),
                "track_count": _int(p.get("track_count"), 0, 100_000),
                "updated_at": _time(p.get("updated_at")),
            })
    doc["playlists"] = playlists[:MAX_PLAYLISTS]
    if "recent_listens" in data:
        listens = []
        for item in _list(data.get("recent_listens"), MAX_LISTENS):
            if isinstance(item, dict) and _time(item.get("listened_at")) and (track := _track(item.get("track"))):
                listens.append({"listened_at": item["listened_at"], "track": track})
        doc["recent_listens"] = listens[:MAX_LISTENS]
    if "top_artists" in data:
        artists = []
        for a in _list(data.get("top_artists"), MAX_TOP_ARTISTS):
            if isinstance(a, dict) and _str(a.get("name"), TITLE):
                artists.append({"name": _str(a["name"], TITLE), "mbid": _mbid(a.get("mbid")), "plays": _int(a.get("plays")) or 0})
        doc["top_artists"] = artists[:MAX_TOP_ARTISTS]
    return doc
