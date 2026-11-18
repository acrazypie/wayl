"""Match tracks from people's servers and scrobblers to catalog songs, and record listens.

Names on servers are messy ("Song - 2011 Remaster", "Artist feat. Someone"), so both sides are
normalized before comparing. The same normalization powers the "you own this" check, which is a
pure database lookup against the indexed library (no network).
"""
import re
from datetime import timedelta

from sqlalchemy import func

from app.models import db, utcnow
from app.models.music import ListeningHistory, Song
from app.models.server import IncomingListen, MediaServer, ServerTrack
from app.services import catalog

_VERSION_WORDS = r"remaster(?:ed)?|mono|stereo|deluxe|bonus(?: track)?|single version|album version|radio edit|explicit|clean|edit"
_BRACKETED = re.compile(rf"\s*[\(\[][^\)\]]*\b(?:{_VERSION_WORDS})\b[^\)\]]*[\)\]]", re.I)
_DASHED = re.compile(rf"\s+-\s+(?:\d{{4}}\s+)?(?:digital(?:ly)?\s+)?(?:{_VERSION_WORDS})\b.*$", re.I)
_FEAT = re.compile(r"\s*[\(\[]?\s*\b(?:feat\.?|ft\.?|featuring|with)\s.*$", re.I)
_ARTIST_SPLIT = re.compile(r"\s*(?:,|&|\+|/|\bx\b|\band\b|\bvs\.?\b)\s*", re.I)

RETRY_UNMATCHED_AFTER = timedelta(days=7)


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (text or "").lower())).strip()


def norm_title(title):
    t = _BRACKETED.sub("", title or "")
    t = _DASHED.sub("", t)
    t = _FEAT.sub("", t)
    return _norm(t)[:300]


def norm_artist(artist):
    return _norm(_FEAT.sub("", artist or ""))[:300]


def artists_match(a, b):
    """Same artist, or one credit contains the other ("Daft Punk" vs "Daft Punk, Pharrell")."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    if len(short) >= 3 and re.search(rf"(?:^| ){re.escape(short)}(?: |$)", long_):
        return True
    first = lambda s: _norm(_ARTIST_SPLIT.split(s)[0])  # noqa: E731
    return first(a) == first(b) and len(first(a)) >= 3


# --- ownership ------------------------------------------------------------------------


def user_server_ids(user):
    if user is None:
        return []
    return [sid for (sid,) in db.session.query(MediaServer.id).filter_by(user_id=user.id).all()]


def owned_song_ids(user, songs):
    """Which of these song dicts ({"id", "title", "artist"}) are on the user's servers.
    Returns None if the user has no server connected (so the UI shows no icons at all)."""
    server_ids = user_server_ids(user)
    if not server_ids:
        return None
    keys = {s["id"]: (norm_title(s.get("title")), norm_artist(s.get("artist"))) for s in songs if s.get("id")}
    titles = {t for t, _ in keys.values() if t}
    mbids = list(keys)
    if not keys:
        return set()
    rows = (
        db.session.query(ServerTrack.norm_title, ServerTrack.norm_artist, ServerTrack.mbid, Song.mbid)
        .outerjoin(Song, Song.id == ServerTrack.song_id)
        .filter(ServerTrack.server_id.in_(server_ids))
        .filter(db.or_(ServerTrack.norm_title.in_(titles), ServerTrack.mbid.in_(mbids), Song.mbid.in_(mbids)))
        .all()
    )
    owned = set()
    for sid, (title, artist) in keys.items():
        for r_title, r_artist, r_mbid, song_mbid in rows:
            if sid in (r_mbid, song_mbid) or (r_title == title and artists_match(r_artist, artist)):
                owned.add(sid)
                break
    return owned


def find_server_track(user, song, server=None):
    """A ServerTrack for this catalog song on one of the user's servers (index lookup only)."""
    server_ids = [server.id] if server else user_server_ids(user)
    if not server_ids:
        return None
    hit = ServerTrack.query.filter(ServerTrack.server_id.in_(server_ids), ServerTrack.song_id == song.id).first()
    if hit:
        return hit
    title, artist = norm_title(song.title), norm_artist(song.artist.name if song.artist else "")
    candidates = ServerTrack.query.filter(
        ServerTrack.server_id.in_(server_ids),
        db.or_(ServerTrack.norm_title == title, ServerTrack.mbid == song.mbid),
    ).all()
    for c in candidates:
        if c.mbid == song.mbid or artists_match(c.norm_artist, artist):
            if c.song_id is None:
                c.song_id, c.matched_at = song.id, utcnow()
            return c
    return None


# --- catalog matching -------------------------------------------------------------------


def _pick(tracks, title, artist, album, duration):
    best, best_score = None, None
    for i, t in enumerate(tracks):
        if norm_title(t.get("title")) != title or not artists_match(norm_artist(t.get("artist")), artist):
            continue
        score = -i
        if album and t.get("album") and _norm(t["album"]) == _norm(album):
            score += 5
        if duration and t.get("duration") and abs(t["duration"] - duration) <= 10:
            score += 3
        if best_score is None or score > best_score:
            best, best_score = t, score
    return best


def match_song(artist, title, album=None, duration=None, mbid=None):
    """The catalog Song for a track, importing it if needed; None if nothing matches.
    Raises catalog.CatalogError if the catalog is unreachable (try again later)."""
    from app.api.music import ensure_song

    if mbid and catalog.is_mbid(mbid.lower()):
        song = ensure_song(mbid.lower())
        if song:
            return song
    nt, na = norm_title(title), norm_artist(artist)
    if not nt or not na:
        return None

    # songs we already know about (no network)
    for song in Song.query.filter(func.lower(Song.title) == (title or "").strip().lower()[:300]).limit(25):
        if song.artist and artists_match(norm_artist(song.artist.name), na):
            return song
    for query in (f"{title} {artist}", title):
        pick = _pick(catalog.search_tracks(query[:100]), nt, na, album, duration)
        if pick:
            return ensure_song(pick["id"])
    return None


def resolve_server_track(st):
    """The catalog Song for a ServerTrack, matching (and remembering) it on first use."""
    if st.song_id:
        return st.song
    if st.matched_at and utcnow() - st.matched_at < RETRY_UNMATCHED_AFTER:
        return None
    song = match_song(st.artist, st.title, st.album, st.duration, st.mbid)
    st.matched_at = utcnow()
    st.song_id = song.id if song else None
    return song


def upsert_server_track(server, remote, *, seen=False):
    st = ServerTrack.query.filter_by(server_id=server.id, remote_id=remote.remote_id).first()
    if st is None:
        st = ServerTrack(server_id=server.id, remote_id=remote.remote_id)
        db.session.add(st)
    changed = (st.title, st.artist) != (remote.title[:300], remote.artist[:300])
    st.title, st.artist = remote.title[:300], remote.artist[:300]
    st.album = (remote.album or None) and remote.album[:300]
    st.duration = remote.duration
    st.mbid = remote.mbid
    st.stream_key = remote.stream_key or st.stream_key
    st.norm_title, st.norm_artist = norm_title(remote.title), norm_artist(remote.artist)
    if changed and st.song_id is None:
        st.matched_at = None  # names changed: worth matching again
    if seen:
        st.seen_at = utcnow()
    return st


# --- recording listens -------------------------------------------------------------------


def record_listen(user_id, song, listened_at, source):
    """Add a listen unless the same song was already logged around that time (the same play can
    arrive from the WAYL player, a server's history and a scrobbler). Returns True if added."""
    window = timedelta(seconds=max(90, int((song.duration or 180) * 0.6)))
    duplicate = ListeningHistory.query.filter(
        ListeningHistory.user_id == user_id,
        ListeningHistory.song_id == song.id,
        ListeningHistory.listened_at >= listened_at - window,
        ListeningHistory.listened_at <= listened_at + window,
    ).first()
    if duplicate:
        return False
    db.session.add(ListeningHistory(user_id=user_id, song_id=song.id, listened_at=listened_at, source=source))
    return True


def process_incoming(listen):
    """Try to turn an IncomingListen into a history entry. Returns "added", "duplicate" or
    "unmatched". Catalog errors propagate, leaving the listen pending for a later try."""
    song = match_song(listen.artist, listen.title, listen.album, listen.duration, listen.mbid)
    if song is None:
        listen.status = "unmatched"
        return "unmatched"
    added = record_listen(listen.user_id, song, listen.listened_at, listen.source)
    db.session.delete(listen)
    return "added" if added else "duplicate"
