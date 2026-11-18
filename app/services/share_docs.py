"""Build the public share documents (docs/sharing-protocol.md).

Everything that leaves the instance is built here, field by field, from an allow-list: no
emails, user ids, media server data, library track ids or listen sources ever get in.
"""
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import desc, func

from app.models import db, utcnow
from app.models.music import Artist, ListeningHistory, Playlist, PlaylistSong, Song
from app.models.sharing import ShareSettings
from app.utility import config, iso

SHARE_VERSION = 1
MAX_TRACKS = 500
MAX_LISTENS = 50
MAX_TOP_ARTISTS = 10
TOP_ARTISTS_DAYS = 30
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def new_token():
    return secrets.token_urlsafe(16)


def playlist_share_url(token):
    return f"{config.APP_URL}/share/v1/p/{token}"


def profile_share_url(token):
    return f"{config.APP_URL}/share/v1/u/{token}"


def app_url_warning():
    """A warning for the UI when share links point at an address friends can't open."""
    host = (urlsplit(config.APP_URL).hostname or "").lower()
    if host in LOCAL_HOSTS or host.endswith(".localhost"):
        return (f"Share links use {config.APP_URL}, which only works on this computer. "
                "Set APP_URL to an address your friends can reach (a domain behind a reverse proxy, or Tailscale).")
    return None


def _http(url):
    return url if isinstance(url, str) and url.startswith(("https://", "http://")) else None


def track_object(song):
    if not song or not song.mbid:
        return None
    return {
        "mbid": song.mbid,
        "title": song.title,
        "artist": song.artist.name if song.artist else "Unknown artist",
        "artist_mbid": song.artist.mbid if song.artist else None,
        "album": song.album.title if song.album else None,
        "cover": _http(song.album.cover_url) if song.album else None,
        "duration": song.duration,
    }


def owner_name(user):
    settings = db.session.get(ShareSettings, user.id)
    return (settings.display_name if settings and settings.display_name else user.username)[:60]


def playlist_updated_at(playlist):
    last_added = db.session.query(func.max(PlaylistSong.added_at)).filter_by(playlist_id=playlist.id).scalar()
    return max(d for d in (playlist.created_at, last_added) if d) if (playlist.created_at or last_added) else utcnow()


def playlist_doc(playlist):
    settings = db.session.get(ShareSettings, playlist.user_id)
    tracks = [t for t in (track_object(ps.song) for ps in playlist.songs) if t][:MAX_TRACKS]
    return {
        "wayl_share": SHARE_VERSION,
        "kind": "playlist",
        "id": playlist.share_token,
        "url": playlist_share_url(playlist.share_token),
        "name": playlist.name,
        "owner": {
            "name": owner_name(playlist.user),
            "profile_url": profile_share_url(settings.profile_share_token)
            if settings and settings.profile_share_token else None,
        },
        "updated_at": iso(playlist_updated_at(playlist)),
        "tracks": tracks,
    }


def playlist_jspf(doc):
    """The playlist document as JSPF, for other tools (identifiers are MusicBrainz URLs)."""
    return {
        "playlist": {
            "title": doc["name"],
            "creator": doc["owner"]["name"],
            "identifier": doc["url"],
            "date": doc["updated_at"],
            "track": [
                {
                    "title": t["title"],
                    "creator": t["artist"],
                    **({"album": t["album"]} if t["album"] else {}),
                    **({"duration": t["duration"] * 1000} if t["duration"] else {}),
                    **({"image": t["cover"]} if t["cover"] else {}),
                    "identifier": [f"https://musicbrainz.org/recording/{t['mbid']}"],
                }
                for t in doc["tracks"]
            ],
        }
    }


def profile_doc(settings):
    user = settings.user
    shared = (
        Playlist.query.filter(Playlist.user_id == user.id, Playlist.share_token.isnot(None))
        .order_by(Playlist.id.desc())
        .all()
    )
    playlists = [
        {
            "name": p.name,
            "url": playlist_share_url(p.share_token),
            "track_count": min(len(p.songs), MAX_TRACKS),
            "updated_at": iso(playlist_updated_at(p)),
        }
        for p in shared
    ]
    stamps = [playlist_updated_at(p) for p in shared]
    doc = {
        "wayl_share": SHARE_VERSION,
        "kind": "profile",
        "id": settings.profile_share_token,
        "url": profile_share_url(settings.profile_share_token),
        "name": owner_name(user),
        "bio": user.bio or None,
        "updated_at": None,
        "playlists": playlists,
    }
    if settings.share_listens:
        entries = (
            ListeningHistory.query.filter_by(user_id=user.id)
            .order_by(ListeningHistory.listened_at.desc(), ListeningHistory.id.desc())
            .limit(MAX_LISTENS)
            .all()
        )
        doc["recent_listens"] = [
            {"listened_at": iso(e.listened_at), "track": t} for e in entries if (t := track_object(e.song))
        ]
        if entries:
            stamps.append(entries[0].listened_at)
    if settings.share_top_artists:
        since = utcnow() - timedelta(days=TOP_ARTISTS_DAYS)
        plays = func.count(ListeningHistory.id)
        rows = (
            db.session.query(Artist.name, Artist.mbid, plays.label("plays"))
            .select_from(ListeningHistory)
            .join(Song, Song.id == ListeningHistory.song_id)
            .join(Artist, Artist.id == Song.artist_id)
            .filter(ListeningHistory.user_id == user.id, ListeningHistory.listened_at >= since)
            .group_by(Artist.id, Artist.name, Artist.mbid)
            .order_by(desc("plays"), Artist.name)
            .limit(MAX_TOP_ARTISTS)
            .all()
        )
        doc["top_artists"] = [{"name": n, "mbid": m, "plays": c} for n, m, c in rows]
    doc["updated_at"] = iso(max(stamps) if stamps else (user.created_at or utcnow()))
    return doc
