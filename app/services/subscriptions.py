"""Subscriptions to share links from other instances: fetch, refresh, annotate, copy."""
import json
from datetime import timedelta

from app.models import db, utcnow
from app.models.music import Playlist, PlaylistSong
from app.models.server import ServerTrack
from app.models.sharing import Subscription
from app.services import catalog
from app.services.matching import artists_match, norm_artist, norm_title, owned_song_ids, user_server_ids
from app.services.remote_share import ShareError, fetch, normalize_share_url
from app.utility import config, iso

MAX_PAYLOAD = 1024 * 1024
REFRESH_BATCH = 20
MAX_BACKOFF_STEPS = 5


def _store(sub, fetched):
    payload = json.dumps(fetched.doc, ensure_ascii=False, separators=(",", ":"))
    if len(payload.encode()) > MAX_PAYLOAD:
        raise ShareError("The shared document is too big (over 1 MB)")
    doc = fetched.doc
    sub.kind = doc["kind"]
    sub.title = doc["name"][:300]
    sub.owner_name = (doc.get("owner") or {}).get("name") if doc["kind"] == "playlist" else doc["name"]
    sub.payload = payload
    sub.etag = (fetched.etag or "")[:200] or None
    sub.last_modified = (fetched.last_modified or "")[:100] or None


def subscribe(user, url, parent=None):
    """The user's subscription to `url` (existing one if they already have it), fetched now.
    Raises ShareError if the link doesn't give a valid document."""
    url = normalize_share_url(url)
    existing = Subscription.query.filter_by(user_id=user.id, url=url).first()
    if existing:
        if parent is None and existing.parent_id is not None:
            existing.parent_id = None  # subscribed directly now: show it in the list
            db.session.commit()
        return existing, False
    fetched = fetch(url)
    sub = Subscription(user_id=user.id, url=url, parent_id=parent.id if parent else None, payload="{}")
    _store(sub, fetched)
    sub.fetched_at = sub.checked_at = utcnow()
    db.session.add(sub)
    db.session.commit()
    return sub, True


def refresh(sub):
    """Fetch again (conditional request). On failure the last good copy is kept. Returns True
    if the fetch worked (changed or not)."""
    sub.checked_at = utcnow()
    try:
        fetched = fetch(sub.url, sub.etag, sub.last_modified)
        if fetched.status == 200:
            _store(sub, fetched)
        sub.fetched_at = utcnow()
        sub.last_error, sub.error_count = None, 0
        ok = True
    except ShareError as exc:
        sub.last_error = str(exc)[:300]
        sub.error_count = (sub.error_count or 0) + 1
        ok = False
    db.session.commit()
    return ok


def is_due(sub, now=None):
    now = now or utcnow()
    last = sub.checked_at or sub.fetched_at
    if last is None:
        return True
    interval = timedelta(hours=config.SHARE_REFRESH_HOURS) * (2 ** min(sub.error_count or 0, MAX_BACKOFF_STEPS))
    return now - last >= interval


def refresh_due(limit=REFRESH_BATCH):
    """Worker job: refresh the stalest due subscriptions, oldest first."""
    now = utcnow()
    candidates = Subscription.query.order_by(Subscription.checked_at.is_(None).desc(), Subscription.checked_at).limit(limit * 5).all()
    done = 0
    for sub in candidates:
        if done >= limit:
            break
        if is_due(sub, now):
            refresh(sub)
            done += 1
    return done


def doc_of(sub):
    try:
        return json.loads(sub.payload)
    except ValueError:
        return {}


def open_playlist(user, parent, playlist_url):
    """A playlist listed by a subscribed profile, as a (cached) child subscription."""
    url = normalize_share_url(playlist_url)
    listed = {normalize_share_url(p["url"]) for p in doc_of(parent).get("playlists", []) if p.get("url")}
    if url not in listed:
        raise ShareError("That playlist isn't on this profile")
    sub, created = subscribe(user, url, parent=parent)
    if not created and is_due(sub):
        refresh(sub)
    return sub


# --- annotating ------------------------------------------------------------------------------


def _song_shape(track):
    """Remote track -> the song object shape the web app uses everywhere."""
    return {
        "id": track["mbid"],
        "title": track["title"],
        "artist": track["artist"],
        "artist_id": track.get("artist_mbid"),
        "album": track.get("album"),
        "cover": track.get("cover"),
        "duration": track.get("duration"),
    }


def _server_track_id(server_ids, song):
    """The user's library track for a remote song (by MusicBrainz id, else title + artist)."""
    from app.models.music import Song

    hit = ServerTrack.query.filter(ServerTrack.server_id.in_(server_ids), ServerTrack.mbid == song["id"]).first()
    if hit is None:
        hit = (
            ServerTrack.query.join(Song, Song.id == ServerTrack.song_id)
            .filter(ServerTrack.server_id.in_(server_ids), Song.mbid == song["id"])
            .first()
        )
    if hit is None:
        title, artist = norm_title(song["title"]), norm_artist(song["artist"])
        for c in ServerTrack.query.filter(ServerTrack.server_id.in_(server_ids), ServerTrack.norm_title == title).all():
            if artists_match(c.norm_artist, artist):
                hit = c
                break
    return hit.id if hit else None


def annotate_tracks(user, tracks):
    """Song-shaped tracks with "owned" (None when no server is connected) and, for owned ones,
    the "track_id" the player streams from."""
    songs = [_song_shape(t) for t in tracks]
    owned = owned_song_ids(user, songs)
    server_ids = user_server_ids(user) if owned else []
    for s in songs:
        s["owned"] = None if owned is None else s["id"] in owned
        if s["owned"]:
            s["track_id"] = _server_track_id(server_ids, s)
    return songs


def subscription_summary(sub):
    doc = doc_of(sub)
    count = len(doc.get("tracks", [])) if sub.kind == "playlist" else len(doc.get("playlists", []))
    return {
        "id": sub.id,
        "kind": sub.kind,
        "url": sub.url,
        "title": sub.title,
        "owner_name": sub.owner_name,
        "count": count,
        "updated_at": doc.get("updated_at"),
        "fetched_at": iso(sub.fetched_at),
        "last_error": sub.last_error,
    }


def subscription_detail(user, sub):
    doc = doc_of(sub)
    data = {**subscription_summary(sub), "parent_id": sub.parent_id}
    if sub.kind == "playlist":
        tracks = annotate_tracks(user, doc.get("tracks", []))
        data["owner_profile_url"] = (doc.get("owner") or {}).get("profile_url")
        data["tracks"] = tracks
        data["total"] = len(tracks)
        has_server = bool(user_server_ids(user))
        data["owned_count"] = sum(1 for t in tracks if t.get("owned")) if has_server else None
        return data

    children = {c.url: c.id for c in Subscription.query.filter_by(user_id=user.id, parent_id=sub.id)}
    data["bio"] = doc.get("bio")
    data["playlists"] = [
        {**p, "subscription_id": children.get(normalize_url_safe(p["url"]))} for p in doc.get("playlists", [])
    ]
    if "recent_listens" in doc:
        songs = annotate_tracks(user, [item["track"] for item in doc["recent_listens"]])
        data["recent_listens"] = [{"listened_at": item["listened_at"], "song": s} for item, s in zip(doc["recent_listens"], songs)]
    if "top_artists" in doc:
        data["top_artists"] = doc["top_artists"]
    return data


def normalize_url_safe(url):
    try:
        return normalize_share_url(url)
    except ShareError:
        return url


# --- copying ----------------------------------------------------------------------------------


def copy_to_playlist(user, sub):
    """Copy a subscribed playlist into a new local playlist. Returns (playlist, skipped).

    Songs are created through ensure_song, i.e. from MusicBrainz, not from the remote payload:
    the songs table is shared by everyone on this instance, and a friend's document must not be
    able to rename a song for all users. The catalog lookup is batched (25 recordings per
    request), so copying 200 tracks costs about 8 requests, not 200.
    """
    from app.api.music import ensure_song

    doc = doc_of(sub)
    tracks = doc.get("tracks", [])
    mbids = [t["mbid"] for t in tracks]
    catalog.lookup_recordings(mbids)  # warms the cache in batches; ensure_song then hits the cache
    owner = (doc.get("owner") or {}).get("name") or "a friend"
    playlist = Playlist(name=f"{doc.get('name', 'Playlist')} (from {owner})"[:120], user_id=user.id, is_public=False)
    db.session.add(playlist)
    db.session.flush()
    added, skipped = set(), 0
    for mbid in mbids:
        song = ensure_song(mbid)
        if song is None or song.id in added:
            skipped += song is None
            continue
        added.add(song.id)
        db.session.add(PlaylistSong(playlist_id=playlist.id, song_id=song.id))
    db.session.commit()
    return playlist, skipped
