from datetime import timedelta

from flask import g, request
from flask_restful import Resource
from sqlalchemy import desc, func

from app.models import db, utcnow
from app.models.music import (
    Album,
    Artist,
    ListeningHistory,
    Playlist,
    PlaylistSong,
    SavedSong,
    Song,
)
from app.models.user import Follow
from app.services import catalog
from app.utility import auth_required, get_current_user, int_arg, iso, json_body

DUPLICATE_LISTEN_WINDOW = timedelta(seconds=30)
CATALOG_DOWN = {"error": "The music database is not responding right now. Try again in a moment."}, 502


# --- helpers --------------------------------------------------------------


def ensure_song(mbid):
    """Return the local Song for a MusicBrainz recording id, importing it on first use.

    Metadata always comes from the catalog, never from the client, so nobody can rename a
    song for everyone. Returns None for unknown ids; raises catalog.CatalogError if the
    catalog is down.
    """
    if not catalog.is_mbid(mbid):
        return None
    song = Song.query.filter_by(mbid=mbid).first()
    if song:
        return song
    track = catalog.lookup_recordings([mbid]).get(mbid)
    if track is None:
        return None

    artist = None
    if catalog.is_mbid(track.get("artist_id")):
        artist = Artist.query.filter_by(mbid=track["artist_id"]).first()
    if artist is None:
        artist = Artist(mbid=track.get("artist_id") if catalog.is_mbid(track.get("artist_id")) else None,
                        name=track["artist"][:300])
        db.session.add(artist)

    album = None
    if track.get("album"):
        if catalog.is_mbid(track.get("album_id")):
            album = Album.query.filter_by(mbid=track["album_id"]).first()
        if album is None:
            album = Album(
                mbid=track.get("album_id") if catalog.is_mbid(track.get("album_id")) else None,
                title=track["album"][:300],
                year=track.get("year"),
                cover_url=track.get("cover"),
            )
            db.session.add(album)

    song = Song(
        mbid=mbid,
        title=track["title"][:300],
        duration=track.get("duration"),
        genre=(track.get("genre") or None) and track["genre"][:100],
        artist=artist,
        album=album,
    )
    db.session.add(song)
    db.session.flush()
    return song


def song_from_body():
    """(song, error) for a {"song_id": "<mbid>"} request body."""
    mbid = str(json_body().get("song_id") or "").strip().lower()
    if not catalog.is_mbid(mbid):
        return None, ({"error": "song_id must be a MusicBrainz recording id"}, 400)
    try:
        song = ensure_song(mbid)
    except catalog.CatalogError:
        return None, CATALOG_DOWN
    if song is None:
        return None, ({"error": "Song not found"}, 404)
    return song, None


def saved_ids(user, mbids):
    """Which of these recording ids the user has saved."""
    if not user or not mbids:
        return set()
    rows = (
        db.session.query(Song.mbid)
        .join(SavedSong, SavedSong.song_id == Song.id)
        .filter(SavedSong.user_id == user.id, Song.mbid.in_(list(mbids)))
        .all()
    )
    return {r[0] for r in rows}


def with_saved(user, tracks):
    """Add the viewer's flags to song dicts: "saved", and "owned" (on one of their servers).
    "owned" is only present when the viewer has a server connected."""
    from app.services.matching import owned_song_ids

    saved = saved_ids(user, [t["id"] for t in tracks])
    owned = owned_song_ids(user, tracks)
    out = []
    for t in tracks:
        item = {**t, "saved": t["id"] in saved}
        if owned is not None:
            item["owned"] = t["id"] in owned
        out.append(item)
    return out


def listen_dict(entry):
    return {"id": entry.id, "song": entry.song.to_dict(), "listened_at": iso(entry.listened_at)}


def listens_for(viewer, entries, with_user=False):
    """Listen dicts with each song's "saved" (and "owned") flag for the viewer."""
    flagged = {s["id"]: s for s in with_saved(viewer, [e.song.to_dict() for e in entries])}
    items = []
    for e in entries:
        item = listen_dict(e)
        item["song"] = flagged[e.song.mbid]
        item["source"] = e.source
        if with_user:
            item["user"] = {"id": e.user.id, "username": e.user.username}
        items.append(item)
    return items


def _synced_from(playlist):
    """"plex"/"navidrome" if this playlist mirrors one on the owner's server."""
    from app.models.server import ImportedPlaylist

    link = ImportedPlaylist.query.filter_by(playlist_id=playlist.id).first()
    return link.server.kind if link else None


def playlist_dict(playlist, with_songs=False):
    covers = []
    for ps in playlist.songs:
        cover = ps.song.album.cover_url if ps.song.album else None
        if cover and cover not in covers:
            covers.append(cover)
        if len(covers) == 4:
            break
    data = {
        "id": playlist.id,
        "name": playlist.name,
        "is_public": playlist.is_public,
        "owner": {"id": playlist.user.id, "username": playlist.user.username},
        "song_count": len(playlist.songs),
        "covers": covers,
        "created_at": iso(playlist.created_at),
        "synced_from": _synced_from(playlist),
    }
    if with_songs:
        data["songs"] = [{**ps.song.to_dict(), "added_at": iso(ps.added_at)} for ps in playlist.songs]
    return data


def find_playlist(playlist_id, *, write):
    """Return (playlist, error). Private playlists look missing to everyone but the owner."""
    user, _ = get_current_user()
    playlist = db.session.get(Playlist, playlist_id)
    is_owner = bool(playlist and user and playlist.user_id == user.id)
    readable = bool(playlist and (is_owner or (playlist.is_public and not write)))
    if not readable:
        return None, ({"error": "Playlist not found"}, 404)
    return playlist, None


# --- catalog --------------------------------------------------------------


class SongSearch(Resource):
    """GET /api/songs?q=  Songs from MusicBrainz/ListenBrainz, best matches first."""

    def get(self):
        q = request.args.get("q", "").strip()[:100]
        if len(q) < 2:
            return {"total": 0, "items": []}
        try:
            tracks = catalog.search_tracks(q)
        except catalog.CatalogError:
            return CATALOG_DOWN
        user, _ = get_current_user()
        return {"total": len(tracks), "items": with_saved(user, tracks)}


class SongDetail(Resource):
    """GET /api/songs/<mbid>  Full details plus your plays and saved state."""

    def get(self, song_id):
        mbid = song_id.lower()
        if not catalog.is_mbid(mbid):
            return {"error": "Song not found"}, 404
        try:
            detail = catalog.track_detail(mbid)
        except catalog.CatalogError:
            return CATALOG_DOWN
        if detail is None:
            return {"error": "Song not found"}, 404

        user, _ = get_current_user()
        local = Song.query.filter_by(mbid=mbid).first()
        my_plays = community_plays = 0
        if local:
            community_plays = ListeningHistory.query.filter_by(song_id=local.id).count()
            if user:
                my_plays = ListeningHistory.query.filter_by(song_id=local.id, user_id=user.id).count()
        return {
            **with_saved(user, [detail])[0],
            "my_plays": my_plays,
            "wayl_plays": community_plays,
        }


class ArtistSearch(Resource):
    def get(self):
        q = request.args.get("q", "").strip()[:100]
        if len(q) < 2:
            return {"items": []}
        try:
            return {"items": catalog.search_artists(q)}
        except catalog.CatalogError:
            return CATALOG_DOWN


class ArtistDetail(Resource):
    def get(self, artist_id):
        try:
            data = catalog.artist(artist_id.lower())
        except catalog.CatalogError:
            return CATALOG_DOWN
        if data is None:
            return {"error": "Artist not found"}, 404
        user, _ = get_current_user()
        return {**data, "top_tracks": with_saved(user, data["top_tracks"])}


# --- my songs (library) ---------------------------------------------------


class SavedSongList(Resource):
    @auth_required
    def get(self):
        limit = int_arg("limit", 50, 1, 200)
        offset = int_arg("offset", 0, 0, 1_000_000)
        query = SavedSong.query.filter_by(user_id=g.current_user.id)
        total = query.count()
        rows = query.order_by(SavedSong.created_at.desc(), SavedSong.id.desc()).offset(offset).limit(limit).all()
        return {
            "total": total,
            "items": [{**r.song.to_dict(), "saved": True, "saved_at": iso(r.created_at)} for r in rows],
        }


class SavedSongDetail(Resource):
    @auth_required
    def put(self, song_id):
        mbid = song_id.lower()
        if not catalog.is_mbid(mbid):
            return {"error": "Song not found"}, 404
        try:
            song = ensure_song(mbid)
        except catalog.CatalogError:
            return CATALOG_DOWN
        if song is None:
            return {"error": "Song not found"}, 404
        if not SavedSong.query.filter_by(user_id=g.current_user.id, song_id=song.id).first():
            db.session.add(SavedSong(user_id=g.current_user.id, song_id=song.id))
        db.session.commit()
        return {"saved": True}

    @auth_required
    def delete(self, song_id):
        song = Song.query.filter_by(mbid=song_id.lower()).first()
        if song:
            SavedSong.query.filter_by(user_id=g.current_user.id, song_id=song.id).delete()
            db.session.commit()
        return {"saved": False}


# --- playlists ------------------------------------------------------------


class PlaylistList(Resource):
    @auth_required
    def get(self):
        playlists = Playlist.query.filter_by(user_id=g.current_user.id).order_by(Playlist.id.desc()).all()
        return {"items": [playlist_dict(p) for p in playlists]}

    @auth_required
    def post(self):
        data = json_body()
        name = str(data.get("name") or "").strip()[:120]
        if not name:
            return {"error": "name is required"}, 400
        playlist = Playlist(name=name, user_id=g.current_user.id, is_public=bool(data.get("is_public", False)))
        db.session.add(playlist)
        db.session.commit()
        return {"message": "Playlist created", "id": playlist.id, "playlist": playlist_dict(playlist)}, 201


class PlaylistDetail(Resource):
    def get(self, playlist_id):
        playlist, error = find_playlist(playlist_id, write=False)
        if error:
            return error
        user, _ = get_current_user()
        data = playlist_dict(playlist, with_songs=True)
        data["songs"] = with_saved(user, data["songs"])
        data["is_owner"] = bool(user and user.id == playlist.user_id)
        return data

    @auth_required
    def post(self, playlist_id):
        """Add a song: {"song_id": "<mbid>"}"""
        playlist, error = find_playlist(playlist_id, write=True)
        if error:
            return error
        song, error = song_from_body()
        if error:
            return error
        if PlaylistSong.query.filter_by(playlist_id=playlist.id, song_id=song.id).first():
            db.session.commit()
            return {"message": f"Already in {playlist.name}"}, 200
        db.session.add(PlaylistSong(playlist_id=playlist.id, song_id=song.id))
        db.session.commit()
        return {"message": f"Added to {playlist.name}"}, 201

    @auth_required
    def patch(self, playlist_id):
        playlist, error = find_playlist(playlist_id, write=True)
        if error:
            return error
        data = json_body()
        if "name" in data:
            name = str(data["name"] or "").strip()[:120]
            if not name:
                return {"error": "name cannot be empty"}, 400
            playlist.name = name
        if "is_public" in data:
            playlist.is_public = bool(data["is_public"])
        db.session.commit()
        return playlist_dict(playlist)

    @auth_required
    def delete(self, playlist_id):
        playlist, error = find_playlist(playlist_id, write=True)
        if error:
            return error
        db.session.delete(playlist)
        db.session.commit()
        return {"message": "Playlist deleted"}


class PlaylistSongDetail(Resource):
    @auth_required
    def delete(self, playlist_id, song_id):
        playlist, error = find_playlist(playlist_id, write=True)
        if error:
            return error
        song = Song.query.filter_by(mbid=song_id.lower()).first()
        if song:
            PlaylistSong.query.filter_by(playlist_id=playlist.id, song_id=song.id).delete()
            db.session.commit()
        return {"message": "Removed from playlist"}


# --- listening history, feed, stats --------------------------------------


class HistoryList(Resource):
    @auth_required
    def get(self):
        limit = int_arg("limit", 30, 1, 100)
        offset = int_arg("offset", 0, 0, 1_000_000)
        entries = (
            ListeningHistory.query.filter_by(user_id=g.current_user.id)
            .order_by(ListeningHistory.listened_at.desc(), ListeningHistory.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {"items": listens_for(g.current_user, entries)}

    @auth_required
    def post(self):
        """Log a listen: {"song_id": "<mbid>"}, or {"track_id": <library track>} for a song
        played from your server. Add "source": "player" when WAYL's player logged it.
        Repeats within 30s are ignored (double-clicks)."""
        data = json_body()
        source = "player" if data.get("source") == "player" else None
        if data.get("track_id") is not None:
            song, error = self._song_from_library(data.get("track_id"))
        else:
            song, error = song_from_body()
        if error:
            return error

        recent = (
            ListeningHistory.query.filter_by(user_id=g.current_user.id, song_id=song.id)
            .order_by(ListeningHistory.id.desc())
            .first()
        )
        if recent and utcnow() - recent.listened_at < DUPLICATE_LISTEN_WINDOW:
            db.session.commit()
            return {"message": "Listening recorded", "created": False, "item": listen_dict(recent)}, 200

        entry = ListeningHistory(user_id=g.current_user.id, song_id=song.id, source=source)
        db.session.add(entry)
        db.session.commit()
        return {"message": "Listening recorded", "created": True, "item": listen_dict(entry)}, 201

    @staticmethod
    def _song_from_library(track_id):
        from app.models.server import ServerTrack
        from app.services.matching import resolve_server_track

        try:
            st = db.session.get(ServerTrack, int(track_id))
        except (TypeError, ValueError):
            st = None
        if st is None or st.server.user_id != g.current_user.id:
            return None, ({"error": "Track not found"}, 404)
        try:
            song = resolve_server_track(st)
        except catalog.CatalogError:
            return None, CATALOG_DOWN
        if song is None:
            db.session.commit()
            return None, ({"error": "This track isn't in MusicBrainz, so it can't be logged"}, 404)
        return song, None


class FeedList(Resource):
    """What the people you follow have been listening to."""

    @auth_required
    def get(self):
        limit = int_arg("limit", 30, 1, 100)
        followed = db.session.query(Follow.followed_id).filter(Follow.follower_id == g.current_user.id)
        entries = (
            ListeningHistory.query.filter(ListeningHistory.user_id.in_(followed))
            .order_by(desc(ListeningHistory.listened_at), desc(ListeningHistory.id))
            .limit(limit)
            .all()
        )
        return {"items": listens_for(g.current_user, entries, with_user=True)}


class Stats(Resource):
    """Your top songs and artists. ?days=30 (1-3650)."""

    @auth_required
    def get(self):
        uid = g.current_user.id
        days = int_arg("days", 30, 1, 3650)
        since = utcnow() - timedelta(days=days)
        in_range = (ListeningHistory.user_id == uid, ListeningHistory.listened_at >= since)
        plays = func.count(ListeningHistory.id)

        top_songs = (
            db.session.query(Song, plays.label("plays"))
            .select_from(ListeningHistory)
            .join(Song, Song.id == ListeningHistory.song_id)
            .filter(*in_range)
            .group_by(Song.id)
            .order_by(desc("plays"), Song.title)
            .limit(10)
            .all()
        )
        top_artists = (
            db.session.query(Artist.mbid, Artist.name, plays.label("plays"))
            .select_from(ListeningHistory)
            .join(Song, Song.id == ListeningHistory.song_id)
            .join(Artist, Artist.id == Song.artist_id)
            .filter(*in_range)
            .group_by(Artist.id, Artist.mbid, Artist.name)
            .order_by(desc("plays"), Artist.name)
            .limit(10)
            .all()
        )
        total_plays, total_seconds = (
            db.session.query(plays, func.coalesce(func.sum(Song.duration), 0))
            .select_from(ListeningHistory)
            .join(Song, Song.id == ListeningHistory.song_id)
            .filter(*in_range)
            .one()
        )
        return {
            "days": days,
            "total_listens": total_plays,
            "total_minutes": round(total_seconds / 60),
            "top_songs": with_saved(g.current_user, [{**s.to_dict(), "plays": n} for s, n in top_songs]),
            "top_artists": [{"id": r[0], "name": r[1], "plays": r[2]} for r in top_artists],
        }
