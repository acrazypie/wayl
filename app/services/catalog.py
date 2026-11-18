"""Song search and details from free, open music databases (no API key needed).

- ListenBrainz Labs recording search: finds canonical recordings for free-text queries.
- ListenBrainz metadata + popularity: album, year, cover art ids, credits, tags, play counts.
- MusicBrainz artist search/lookup (rate limited to 1 request/second per IP, so it is throttled).
- Cover Art Archive: album covers, hotlinked by URL.

MusicBrainz core data is CC0 (public domain). Non-commercial use of the web service is free;
see README for the details and links. Every function raises CatalogError when the upstream
service is unreachable, so the API can answer 502 instead of crashing.
"""
import logging
import math
import re
import threading
import time
from collections import OrderedDict

import requests

from app.utility import config

log = logging.getLogger(__name__)

LB_API = "https://api.listenbrainz.org/1"
LB_LABS = "https://labs.api.listenbrainz.org"
MB_API = "https://musicbrainz.org/ws/2"
CAA = "https://coverartarchive.org"

MBID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Only these artist links are shown on the song page (all are plain https links).
ARTIST_LINK_TYPES = {
    "official homepage": "Website",
    "youtube": "YouTube",
    "free streaming": "Stream",
    "streaming": "Stream",
    "bandcamp": "Bandcamp",
    "soundcloud": "SoundCloud",
    "wikidata": "Wikidata",
}


class CatalogError(Exception):
    """The music database could not be reached or answered with an error."""


def is_mbid(value):
    return isinstance(value, str) and bool(MBID_RE.match(value))


# --- HTTP plumbing ----------------------------------------------------------------


class _TTLCache:
    def __init__(self, ttl, size=512):
        self.ttl, self.size = ttl, size
        self._data = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._data.get(key)
            if hit is None:
                return None
            expires, value = hit
            if expires < time.monotonic():
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key, value):
        with self._lock:
            self._data[key] = (time.monotonic() + self.ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)

    def clear(self):
        with self._lock:
            self._data.clear()


_search_cache = _TTLCache(ttl=600)
_meta_cache = _TTLCache(ttl=3600, size=4096)
_artist_cache = _TTLCache(ttl=3600)

_session = requests.Session()
_mb_lock = threading.Lock()
_mb_last = 0.0


def _throttle_musicbrainz():
    """MusicBrainz allows one request per second per IP; wait our turn."""
    global _mb_last
    with _mb_lock:
        wait = 1.05 - (time.monotonic() - _mb_last)
        if wait > 0:
            time.sleep(wait)
        _mb_last = time.monotonic()


def _request(method, url, *, params=None, json=None, musicbrainz=False, retries=2):
    headers = {"User-Agent": config.CATALOG_USER_AGENT, "Accept": "application/json"}
    for attempt in range(retries + 1):
        if musicbrainz:
            _throttle_musicbrainz()
        try:
            res = _session.request(
                method, url, params=params, json=json, headers=headers, timeout=config.CATALOG_TIMEOUT
            )
        except requests.RequestException as exc:
            if attempt < retries:
                continue
            raise CatalogError(str(exc)) from exc
        if res.status_code in (429, 502, 503, 504) and attempt < retries:
            time.sleep(1 + attempt)  # busy or rate limited: back off and retry
            continue
        if res.status_code in (400, 404):
            return None
        if not res.ok:
            raise CatalogError(f"{url} answered {res.status_code}")
        try:
            return res.json()
        except ValueError as exc:
            raise CatalogError(f"{url} returned invalid JSON") from exc
    raise CatalogError(f"{url} is busy")  # pragma: no cover - loop always returns or raises


# --- parsing ----------------------------------------------------------------------


def cover_url(release_mbid, caa_id=None, size=250):
    """Cover Art Archive thumbnail. With caa_id the URL points at the exact image."""
    if not is_mbid(release_mbid):
        return None
    if caa_id:
        return f"{CAA}/release/{release_mbid}/{int(caa_id)}-{size}.jpg"
    return f"{CAA}/release/{release_mbid}/front-{size}"


def _safe_link(url):
    return url if isinstance(url, str) and url.startswith(("https://", "http://")) else None


def _genres(tags, limit=4):
    """Pick genre tags (they carry a genre_mbid), most voted first: recording, then artist."""
    tags = tags or {}
    for key in ("recording", "release_group", "artist"):
        items = [t for t in tags.get(key) or [] if t.get("genre_mbid") and t.get("tag")]
        if items:
            items.sort(key=lambda t: -(t.get("count") or 0))
            seen, out = set(), []
            for t in items:
                if t["tag"] not in seen:
                    seen.add(t["tag"])
                    out.append(t["tag"])
            return out[:limit]
    return []


def track_from_metadata(mbid, meta):
    """ListenBrainz /metadata/recording entry -> our track dict."""
    rec = meta.get("recording") or {}
    artist = meta.get("artist") or {}
    release = meta.get("release") or {}
    artists = artist.get("artists") or []
    length = rec.get("length")
    cover_release = release.get("caa_release_mbid") or release.get("mbid")
    genres = _genres(meta.get("tag"))
    return {
        "id": mbid,
        "title": rec.get("name") or "Unknown title",
        "artist": artist.get("name") or (artists[0].get("name") if artists else None) or "Unknown artist",
        "artist_id": artists[0].get("artist_mbid") if artists else None,
        "album": release.get("name"),
        "album_id": release.get("mbid"),
        "year": release.get("year"),
        "duration": round(length / 1000) if isinstance(length, (int, float)) and length > 0 else None,
        "cover": cover_url(cover_release, release.get("caa_id")),
        "genre": genres[0] if genres else None,
        "genres": genres,
    }


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (text or "").lower())).strip()


def rank_tracks(query, tracks, popularity):
    """Keep the search order but let exact matches and well-known recordings float up."""
    q = _norm(query)

    def exact(title, artist):
        """"title", "title artist" or "artist title" (artist may be part of a longer credit)."""
        if q == title:
            return True
        if q.startswith(title + " ") and q[len(title) + 1 :] in artist:
            return True
        return q.endswith(" " + title) and q[: -len(title) - 1] in artist

    def score(item):
        index, track = item
        title, artist = _norm(track["title"]), _norm(track["artist"])
        s = -0.15 * index + math.log10(1 + (popularity.get(track["id"]) or 0))
        if title and exact(title, artist):
            s += 3
        return s

    return [t for _, t in sorted(enumerate(tracks), key=score, reverse=True)]


# --- public API -------------------------------------------------------------------


def lookup_recordings(mbids):
    """{mbid: track dict} for the given recording ids (unknown ids are left out)."""
    wanted = [m for m in dict.fromkeys(mbids) if is_mbid(m)]
    found, missing = {}, []
    for m in wanted:
        cached = _meta_cache.get(("rec", m))
        if cached is not None:
            found[m] = cached
        else:
            missing.append(m)
    for i in range(0, len(missing), 25):
        chunk = missing[i : i + 25]
        data = _request(
            "GET",
            f"{LB_API}/metadata/recording/",
            params={"recording_mbids": ",".join(chunk), "inc": "artist release tag"},
        ) or {}
        for m in chunk:
            if isinstance(data.get(m), dict):
                found[m] = _meta_cache.get(("rec", m)) or track_from_metadata(m, data[m])
                _meta_cache.set(("rec", m), found[m])
                _meta_cache.set(("raw", m), data[m])
    return found


def popularity(mbids):
    """{mbid: total ListenBrainz listens}. Best effort: returns {} if the service fails."""
    ids = [m for m in dict.fromkeys(mbids) if is_mbid(m)]
    if not ids:
        return {}
    try:
        rows = _request("POST", f"{LB_API}/popularity/recording", json={"recording_mbids": ids}) or []
    except CatalogError:
        log.warning("ListenBrainz popularity lookup failed", exc_info=True)
        return {}
    return {r.get("recording_mbid"): r.get("total_listen_count") or 0 for r in rows if isinstance(r, dict)}


def search_tracks(query):
    """Free-text song search ("title", "artist", or both). Returns up to ~10 ranked tracks."""
    query = (query or "").strip()[:100]
    if len(query) < 2:
        return []
    key = query.lower()
    cached = _search_cache.get(("tracks", key))
    if cached is not None:
        return cached

    hits = _request("GET", f"{LB_LABS}/recording-search/json", params={"query": query}) or []
    ids = [h.get("recording_mbid") for h in hits if isinstance(h, dict)]
    meta = lookup_recordings(ids)
    tracks = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        m = h.get("recording_mbid")
        if m in meta:
            tracks.append(meta[m])
        elif is_mbid(m):  # metadata missing: fall back to what the search returned
            tracks.append({
                "id": m,
                "title": h.get("recording_name") or "Unknown title",
                "artist": h.get("artist_credit_name") or "Unknown artist",
                "artist_id": None,
                "album": h.get("release_name"),
                "album_id": h.get("release_mbid"),
                "year": None,
                "duration": None,
                "cover": cover_url(h.get("release_mbid")),
                "genre": None,
                "genres": [],
            })
    result = rank_tracks(query, tracks, popularity([t["id"] for t in tracks]))
    _search_cache.set(("tracks", key), result)
    return result


def search_artists(query, limit=6):
    query = (query or "").strip()[:100]
    if len(query) < 2:
        return []
    key = (query.lower(), limit)
    cached = _search_cache.get(("artists", key))
    if cached is not None:
        return cached
    data = _request(
        "GET", f"{MB_API}/artist", params={"query": query, "fmt": "json", "limit": limit}, musicbrainz=True
    ) or {}
    result = [
        {
            "id": a["id"],
            "name": a.get("name"),
            "type": a.get("type"),
            "country": (a.get("area") or {}).get("name") or a.get("country"),
            "disambiguation": a.get("disambiguation") or None,
        }
        for a in data.get("artists") or []
        if is_mbid(a.get("id")) and (a.get("score") or 0) >= 60
    ]
    _search_cache.set(("artists", key), result)
    return result


def artist(mbid, limit=30):
    """Artist name, details and their most-listened recordings, or None if unknown."""
    if not is_mbid(mbid):
        return None
    cached = _artist_cache.get(mbid)
    if cached is not None:
        return cached

    rows = _request("GET", f"{LB_API}/popularity/top-recordings-for-artist/{mbid}") or []
    rows = [r for r in rows if isinstance(r, dict) and is_mbid(r.get("recording_mbid"))]
    info = _request(
        "GET", f"{MB_API}/artist/{mbid}", params={"fmt": "json", "inc": "genres"}, musicbrainz=True
    )
    if info is None and not rows:
        return None

    tracks, seen = [], set()
    for r in rows:
        key = _norm(r.get("recording_name"))
        if key in seen:  # the same song often appears as several recordings
            continue
        seen.add(key)
        length = r.get("length")
        tracks.append({
            "id": r["recording_mbid"],
            "title": r.get("recording_name") or "Unknown title",
            "artist": r.get("artist_name") or "Unknown artist",
            "artist_id": mbid,
            "album": r.get("release_name"),
            "album_id": r.get("release_mbid"),
            "year": None,
            "duration": round(length / 1000) if isinstance(length, (int, float)) and length > 0 else None,
            "cover": cover_url(r.get("caa_release_mbid") or r.get("release_mbid"), r.get("caa_id")),
            "genre": None,
            "genres": [],
            "listens": r.get("total_listen_count") or 0,
        })
        if len(tracks) >= limit:
            break

    info = info or {}
    genres = sorted(info.get("genres") or [], key=lambda g: -(g.get("count") or 0))
    life = info.get("life-span") or {}
    result = {
        "id": mbid,
        "name": info.get("name") or (rows[0].get("artist_name") if rows else "Unknown artist"),
        "type": info.get("type"),
        "country": (info.get("area") or {}).get("name"),
        "disambiguation": info.get("disambiguation") or None,
        "begin": (life.get("begin") or "")[:4] or None,
        "genres": [g["name"] for g in genres[:5] if g.get("name")],
        "cover": tracks[0]["cover"] if tracks else None,
        "top_tracks": tracks,
    }
    _artist_cache.set(mbid, result)
    return result


def track_detail(mbid):
    """Everything the song page shows, or None if the recording does not exist."""
    track = lookup_recordings([mbid]).get(mbid)
    if track is None:
        return None
    raw = _meta_cache.get(("raw", mbid)) or {}
    rec = raw.get("recording") or {}
    release = raw.get("release") or {}
    artists = (raw.get("artist") or {}).get("artists") or []

    credits, seen = [], set()
    for rel in rec.get("rels") or []:
        name, role = rel.get("artist_name"), rel.get("instrument") or rel.get("type")
        if name and role and (name, role) not in seen:
            seen.add((name, role))
            credits.append({"name": name, "role": role, "artist_id": rel.get("artist_mbid")})

    links = []
    for a in artists[:1]:
        for kind, url in (a.get("rels") or {}).items():
            label = ARTIST_LINK_TYPES.get(kind)
            if label and _safe_link(url) and label not in {l["label"] for l in links}:
                links.append({"label": label, "url": url})

    plays = popularity([mbid]).get(mbid)
    cover_release = release.get("caa_release_mbid") or release.get("mbid")
    return {
        **track,
        "cover_large": cover_url(cover_release, release.get("caa_id"), size=500),
        "release_date": rec.get("first_release_date"),
        "isrc": (rec.get("isrcs") or [None])[0],
        "credits": credits[:12],
        "artist_links": links,
        "artist_area": artists[0].get("area") if artists else None,
        "listenbrainz_listens": plays,
        "musicbrainz_url": f"https://musicbrainz.org/recording/{mbid}",
    }


def clear_caches():
    for cache in (_search_cache, _meta_cache, _artist_cache):
        cache.clear()
