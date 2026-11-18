"""Connect your own music server (Plex / Navidrome), search and stream your library."""
import secrets
import threading

from flask import current_app, g, request, session
from flask_restful import Resource
from sqlalchemy import or_

from app.models import db, utcnow
from app.models.server import ImportedPlaylist, IncomingListen, ListenToken, MediaServer, ServerTrack
from app.services import catalog
from app.services.matching import _norm, find_server_track, resolve_server_track, upsert_server_track
from app.services.media import MediaServerError, client_for, normalize_url
from app.services.media import plex as plex_api
from app.services.media.subsonic import SubsonicClient
from app.services.secrets_box import decrypt, encrypt
from app.services.sync import process_pending, sync_server
from app.utility import auth_required, config, hash_token, int_arg, iso, json_body, limiter

CATALOG_DOWN = {"error": "The music database is not responding right now. Try again in a moment."}, 502


def server_dict(s):
    return {
        "id": s.id,
        "kind": s.kind,
        "name": s.name,
        "url": s.base_url,
        "username": s.username,
        "owned": s.plex_owned if s.kind == "plex" else None,
        "sync_listens": s.sync_listens,
        "sync_playlists": s.sync_playlists,
        "library_count": s.library_count,
        "syncing": s.syncing_since is not None,
        "last_library_sync_at": iso(s.last_library_sync_at),
        "last_listen_sync_at": iso(s.last_listen_sync_at),
        "last_playlist_sync_at": iso(s.last_playlist_sync_at),
        "imported_playlists": len(s.imported_playlists),
        "last_error": s.last_error,
        "created_at": iso(s.created_at),
    }


def my_server(server_id):
    server = db.session.get(MediaServer, server_id)
    if server is None or server.user_id != g.current_user.id:
        return None
    return server


def start_sync(server_id, jobs):
    """Run a sync in the background (synchronously in tests)."""
    app = current_app._get_current_object()
    if app.testing:
        return sync_server(server_id, jobs)

    def run():
        with app.app_context():
            sync_server(server_id, jobs)

    threading.Thread(target=run, daemon=True, name=f"sync-{server_id}").start()
    return None


# --- connecting -----------------------------------------------------------------------------


class ServerList(Resource):
    @auth_required
    def get(self):
        servers = MediaServer.query.filter_by(user_id=g.current_user.id).order_by(MediaServer.id).all()
        return {"items": [server_dict(s) for s in servers]}

    @auth_required
    def post(self):
        """Connect a server.
        Navidrome: {"kind": "navidrome", "url", "username", "password"}
        Plex (after the PIN sign-in): {"kind": "plex", "server": "<id from /api/servers/plex/pin>"}
        Plex (manual): {"kind": "plex", "url", "token"}
        """
        data = json_body()
        kind = data.get("kind")
        if kind not in ("plex", "navidrome"):
            return {"error": "kind must be plex or navidrome"}, 400
        if MediaServer.query.filter_by(user_id=g.current_user.id, kind=kind).first():
            return {"error": f"You already connected a {kind.title()} server. Disconnect it first."}, 409
        try:
            if kind == "navidrome":
                url = normalize_url(data.get("url"))
                username = str(data.get("username") or "").strip()
                password = str(data.get("password") or "")
                if not username or not password:
                    return {"error": "Username and password are required"}, 400
                info = SubsonicClient(url, username, password).ping()
                server = MediaServer(kind=kind, name=info["name"], base_url=url, username=username, secret=encrypt(password))
            elif data.get("server"):
                server = self._plex_from_pin(str(data["server"]))
                if isinstance(server, tuple):
                    return server
            else:
                url = normalize_url(data.get("url"))
                token = str(data.get("token") or "").strip()
                if not token:
                    return {"error": "The Plex token is required"}, 400
                plex_api.PlexClient(url, token).ping()
                owned = bool(data.get("owned", True))
                server = MediaServer(kind=kind, name="Plex", base_url=url, secret=encrypt(token), plex_owned=owned)
        except MediaServerError as exc:
            return {"error": str(exc)}, 400

        server.user_id = g.current_user.id
        server.sync_listens = bool(data.get("sync_listens", True))
        server.sync_playlists = bool(data.get("sync_playlists", False))
        db.session.add(server)
        db.session.commit()
        start_sync(server.id, ["library", "listens", "playlists"])
        return {"message": f"Connected to {server.name}", "server": server_dict(server)}, 201

    @staticmethod
    def _plex_from_pin(server_id):
        pending = session.get("plex_servers") or {}
        found = pending.get(server_id)
        if not found:
            return {"error": "Sign in with Plex again; that server list has expired."}, 400
        token = decrypt(found["token"])
        if token is None:
            return {"error": "Sign in with Plex again."}, 400
        url = plex_api.pick_connection({"connections": found["connections"], "token": token})
        session.pop("plex_servers", None)
        return MediaServer(kind="plex", name=found["name"][:120], base_url=url, secret=encrypt(token), plex_owned=found["owned"])


class PlexPin(Resource):
    """Sign in with Plex: POST to get the plex.tv URL to open, then GET with the pin id until the
    user has approved it; the answer then lists their servers."""

    decorators = [limiter.limit("30 per hour")]

    @auth_required
    def post(self):
        try:
            pin = plex_api.create_pin(forward_url=f"{config.APP_URL}/settings?plex=done")
        except MediaServerError as exc:
            return {"error": str(exc)}, 502
        session["plex_pin"] = pin["id"]
        return {"pin_id": pin["id"], "auth_url": pin["auth_url"]}


class PlexPinCheck(Resource):
    decorators = [limiter.limit("200 per hour")]

    @auth_required
    def get(self, pin_id):
        if session.get("plex_pin") != pin_id:
            return {"error": "Unknown sign-in attempt, start again"}, 404
        try:
            token = plex_api.check_pin(pin_id)
            if not token:
                return {"status": "waiting"}
            servers = plex_api.list_servers(token)
        except MediaServerError as exc:
            return {"error": str(exc)}, 502
        session.pop("plex_pin", None)
        # Remember the choices (tokens encrypted) until the user picks one.
        session["plex_servers"] = {
            s["id"]: {"name": s["name"], "owned": s["owned"], "token": encrypt(s["token"]), "connections": s["connections"][:8]}
            for s in servers if s.get("id")
        }
        return {
            "status": "ready",
            "servers": [{"id": s["id"], "name": s["name"], "owned": s["owned"]} for s in servers if s.get("id")],
        }


class ServerDetail(Resource):
    @auth_required
    def patch(self, server_id):
        server = my_server(server_id)
        if server is None:
            return {"error": "Server not found"}, 404
        data = json_body()
        for key in ("sync_listens", "sync_playlists"):
            if key in data:
                setattr(server, key, bool(data[key]))
        if data.get("url"):
            try:
                url = normalize_url(data["url"])
                probe = MediaServer(kind=server.kind, base_url=url, username=server.username, secret=server.secret)
                client_for(probe).ping()
            except MediaServerError as exc:
                return {"error": str(exc)}, 400
            server.base_url = url
        db.session.commit()
        if data.get("sync_playlists"):
            start_sync(server.id, ["playlists"])
        return server_dict(server)

    @auth_required
    def delete(self, server_id):
        server = my_server(server_id)
        if server is None:
            return {"error": "Server not found"}, 404
        # Imported playlists stay, as ordinary WAYL playlists.
        ImportedPlaylist.query.filter_by(server_id=server.id).delete()
        ServerTrack.query.filter_by(server_id=server.id).delete()
        db.session.delete(server)
        db.session.commit()
        return {"message": "Server disconnected"}


class ServerSync(Resource):
    decorators = [limiter.limit("20 per hour")]

    @auth_required
    def post(self, server_id):
        server = my_server(server_id)
        if server is None:
            return {"error": "Server not found"}, 404
        jobs = [j for j in json_body().get("jobs") or ["library", "listens", "playlists"] if j in ("library", "listens", "playlists")]
        if server.syncing_since:
            return {"message": "Already syncing"}, 202
        result = start_sync(server.id, jobs)
        return {"message": "Sync started", "result": result}, 202


# --- library & streaming ----------------------------------------------------------------------


def library_item(user, st):
    from app.api.music import with_saved

    base = {"track_id": st.id, "server": st.server.kind, "owned": True}
    if st.song_id:
        song = with_saved(user, [st.song.to_dict()])[0]
        return {**song, **base, "owned": True}
    return {
        **base,
        "id": None,
        "library_only": True,
        "title": st.title,
        "artist": st.artist,
        "artist_id": None,
        "album": st.album,
        "duration": st.duration,
        "cover": None,
        "saved": False,
    }


class LibrarySearch(Resource):
    """GET /api/library?q=  Search the tracks on your connected servers (from WAYL's index)."""

    @auth_required
    def get(self):
        q = _norm(request.args.get("q", ""))[:100]
        limit = int_arg("limit", 50, 1, 200)
        offset = int_arg("offset", 0, 0, 1_000_000)
        server_ids = [s.id for s in MediaServer.query.filter_by(user_id=g.current_user.id)]
        if not server_ids:
            return {"total": 0, "items": [], "servers": 0}
        query = ServerTrack.query.filter(ServerTrack.server_id.in_(server_ids))
        for word in q.split()[:6]:
            pattern = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            query = query.filter(or_(ServerTrack.norm_title.like(pattern, escape="\\"), ServerTrack.norm_artist.like(pattern, escape="\\")))
        total = query.count()
        rows = query.order_by(ServerTrack.norm_artist, ServerTrack.norm_title, ServerTrack.id).offset(offset).limit(limit).all()
        return {"total": total, "items": [library_item(g.current_user, st) for st in rows], "servers": len(server_ids)}


class LibraryTrackMatch(Resource):
    """POST /api/library/tracks/<id>/match  Find the catalog song for a library-only track."""

    @auth_required
    def post(self, track_id):
        st = db.session.get(ServerTrack, track_id)
        if st is None or st.server.user_id != g.current_user.id:
            return {"error": "Track not found"}, 404
        st.matched_at = None  # the user asked: try again now
        try:
            song = resolve_server_track(st)
        except catalog.CatalogError:
            return CATALOG_DOWN
        db.session.commit()
        if song is None:
            return {"error": "Couldn't find this track in MusicBrainz"}, 404
        return library_item(g.current_user, st)


class SongSources(Resource):
    """GET /api/songs/<mbid>/sources  Where you can play this song from (your servers)."""

    @auth_required
    def get(self, song_id):
        from app.api.music import ensure_song

        servers = MediaServer.query.filter_by(user_id=g.current_user.id).all()
        if not servers:
            return {"items": []}
        try:
            song = ensure_song(song_id.lower())
        except catalog.CatalogError:
            return CATALOG_DOWN
        if song is None:
            return {"error": "Song not found"}, 404
        items = []
        for server in servers:
            st = find_server_track(g.current_user, song, server)
            if st is None and not server.last_library_sync_at:
                st = self._live_search(server, song)  # library not indexed yet: ask the server
            if st:
                items.append({"track_id": st.id, "server": server.kind, "server_name": server.name,
                              "stream_url": f"/api/stream/{st.id}", "duration": st.duration})
        db.session.commit()
        return {"items": items}

    @staticmethod
    def _live_search(server, song):
        from app.services.matching import artists_match, norm_artist, norm_title

        try:
            results = client_for(server).search_tracks(song.title, limit=25)
        except MediaServerError:
            return None
        title, artist = norm_title(song.title), norm_artist(song.artist.name if song.artist else "")
        for remote in results:
            if (remote.mbid and remote.mbid == song.mbid) or (
                norm_title(remote.title) == title and artists_match(norm_artist(remote.artist), artist)
            ):
                st = upsert_server_track(server, remote)
                st.song_id, st.matched_at = song.id, utcnow()
                db.session.flush()
                return st
        return None


# --- scrobble token & unmatched listens ------------------------------------------------------


class ListenTokenResource(Resource):
    """Token for the ListenBrainz-compatible scrobble API. Shown once when created."""

    @auth_required
    def get(self):
        row = db.session.get(ListenToken, g.current_user.id)
        return {
            "exists": row is not None,
            "created_at": iso(row.created_at) if row else None,
            "last_used_at": iso(row.last_used_at) if row else None,
            "api_url": f"{config.APP_URL}/listenbrainz/1/",
        }

    @auth_required
    def post(self):
        token = "wayl_" + secrets.token_urlsafe(24)
        row = db.session.get(ListenToken, g.current_user.id)
        if row is None:
            row = ListenToken(user_id=g.current_user.id, token_hash="")
            db.session.add(row)
        row.token_hash = hash_token(token)
        row.created_at, row.last_used_at = utcnow(), None
        db.session.commit()
        return {"token": token, "api_url": f"{config.APP_URL}/listenbrainz/1/"}, 201

    @auth_required
    def delete(self):
        ListenToken.query.filter_by(user_id=g.current_user.id).delete()
        db.session.commit()
        return {"exists": False}


class UnmatchedListens(Resource):
    @auth_required
    def get(self):
        q = IncomingListen.query.filter_by(user_id=g.current_user.id)
        rows = q.order_by(IncomingListen.listened_at.desc()).limit(50).all()
        return {
            "unmatched": q.filter_by(status="unmatched").count(),
            "pending": IncomingListen.query.filter_by(user_id=g.current_user.id, status="pending").count(),
            "items": [
                {"id": r.id, "artist": r.artist, "title": r.title, "album": r.album, "source": r.source,
                 "status": r.status, "listened_at": iso(r.listened_at)}
                for r in rows
            ],
        }

    @auth_required
    def post(self):
        """Try matching them again (up to 50 at a time)."""
        counts = process_pending(limit=50, user_id=g.current_user.id, include_unmatched=True)
        return counts

    @auth_required
    def delete(self):
        IncomingListen.query.filter_by(user_id=g.current_user.id, status="unmatched").delete()
        db.session.commit()
        return {"message": "Cleared"}
