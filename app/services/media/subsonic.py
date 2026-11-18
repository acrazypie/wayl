"""Subsonic API client (Navidrome, and other Subsonic-compatible servers).

Auth uses the salted token scheme from Subsonic 1.13+: t = md5(password + salt), sent with the
username and salt on every request, so the password itself never goes over the wire.
"""
import hashlib
import secrets

from app.services.catalog import is_mbid
from app.services.media import base
from app.services.media.base import MediaServerError, RemoteTrack, int_or_none

API_VERSION = "1.16.1"
CLIENT_NAME = "WAYL"


class SubsonicClient:
    kind = "navidrome"

    def __init__(self, base_url, username, password):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

    def _auth(self):
        salt = secrets.token_hex(8)
        token = hashlib.md5((self.password + salt).encode("utf-8")).hexdigest()  # noqa: S324 (protocol)
        return {"u": self.username, "t": token, "s": salt, "v": API_VERSION, "c": CLIENT_NAME}

    def call(self, endpoint, **params):
        res = base.http("GET", f"{self.base_url}/rest/{endpoint}", params={**self._auth(), "f": "json", **params})
        if res.status_code in (401, 403):
            raise MediaServerError("Wrong username or password")
        try:
            body = res.json()["subsonic-response"]
        except (ValueError, KeyError, TypeError) as exc:
            raise MediaServerError(
                f"That doesn't look like a Navidrome/Subsonic server (HTTP {res.status_code})"
            ) from exc
        if body.get("status") != "ok":
            error = body.get("error") or {}
            if error.get("code") in (40, 41):
                raise MediaServerError("Wrong username or password")
            raise MediaServerError(error.get("message") or "The server returned an error")
        return body

    # --- reading ---------------------------------------------------------------------

    @staticmethod
    def to_track(song):
        mbid = (song.get("musicBrainzId") or "").lower()
        return RemoteTrack(
            remote_id=str(song["id"]),
            title=song.get("title") or "Unknown title",
            artist=song.get("artist") or song.get("displayArtist") or "Unknown artist",
            album=song.get("album"),
            duration=int_or_none(song.get("duration")),
            mbid=mbid if is_mbid(mbid) else None,
        )

    def ping(self):
        body = self.call("ping")
        return {"name": "Navidrome" if body.get("type") == "navidrome" else (body.get("type") or "Subsonic").title()}

    def search_tracks(self, query, limit=20):
        body = self.call("search3", query=query, songCount=limit, artistCount=0, albumCount=0)
        songs = (body.get("searchResult3") or {}).get("song") or []
        return [self.to_track(s) for s in songs if s.get("id")]

    def all_tracks(self, page=500):
        """Every song on the server. An empty search3 query lists everything on Navidrome;
        if a server doesn't support that, walk the albums instead."""
        offset, seen_any = 0, False
        while True:
            body = self.call("search3", query="", songCount=page, songOffset=offset, artistCount=0, albumCount=0)
            songs = (body.get("searchResult3") or {}).get("song") or []
            for s in songs:
                if s.get("id"):
                    seen_any = True
                    yield self.to_track(s)
            if len(songs) < page:
                break
            offset += page
        if seen_any:
            return
        offset = 0
        while True:
            body = self.call("getAlbumList2", type="alphabeticalByName", size=500, offset=offset)
            albums = (body.get("albumList2") or {}).get("album") or []
            for album in albums:
                for s in (self.call("getAlbum", id=album["id"]).get("album") or {}).get("song") or []:
                    if s.get("id"):
                        yield self.to_track(s)
            if len(albums) < 500:
                break
            offset += 500

    def track(self, remote_id):
        body = self.call("getSong", id=remote_id)
        song = body.get("song")
        return self.to_track(song) if song else None

    def playlists(self):
        body = self.call("getPlaylists")
        items = (body.get("playlists") or {}).get("playlist") or []
        return [{"id": str(p["id"]), "name": p.get("name") or "Playlist", "count": p.get("songCount")} for p in items if p.get("id")]

    def playlist_tracks(self, remote_id):
        body = self.call("getPlaylist", id=remote_id)
        entries = (body.get("playlist") or {}).get("entry") or []
        return [self.to_track(e) for e in entries if e.get("id")]

    def now_playing(self):
        """[(RemoteTrack, minutes_ago)] for this user's current playback."""
        body = self.call("getNowPlaying")
        entries = (body.get("nowPlaying") or {}).get("entry") or []
        return [
            (self.to_track(e), int_or_none(e.get("minutesAgo")) or 0)
            for e in entries
            if e.get("id") and e.get("username") == self.username
        ]

    def stream_request(self, track):
        """(url, params, headers) to fetch the audio. format=raw: no transcoding."""
        return f"{self.base_url}/rest/stream", {**self._auth(), "id": track.remote_id, "format": "raw"}, {}
