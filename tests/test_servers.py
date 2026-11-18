"""Media server integration: Navidrome (Subsonic API), Plex, the ListenBrainz-compatible scrobble
API, library search, "owned" flags and the audio proxy. All servers are fakes."""
import hashlib
import time
from urllib.parse import urlsplit

import pytest

from app.models import db
from app.models.music import ListeningHistory, Playlist
from app.models.server import IncomingListen, MediaServer, ServerTrack
from app.services.media import base as media_base
from tests.conftest import NUDE, PASSWORD, TEARDROP

ND = "http://nd.test"
PLEX = "http://plex.test"
ND_PASSWORD = "nd-secret"


class FakeResponse:
    def __init__(self, status=200, data=None, headers=None, content=b""):
        self.status_code = status
        self._data = data
        self.headers = headers or {"Content-Type": "application/json"}
        self.content = content
        self.ok = 200 <= status < 400

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data

    def iter_content(self, _size):
        yield self.content

    def close(self):
        pass


ND_SONGS = [
    {"id": "nd-1", "title": "Nude", "artist": "Radiohead", "album": "In Rainbows", "duration": 255},
    {"id": "nd-2", "title": "Weird Fishes/Arpeggi", "artist": "Radiohead", "album": "In Rainbows", "duration": 318},
    {"id": "nd-3", "title": "Teardrop (2019 Remaster)", "artist": "Massive Attack", "album": "Mezzanine",
     "duration": 330, "musicBrainzId": TEARDROP},
]

PLEX_TRACKS = {
    "101": {"ratingKey": "101", "type": "track", "title": "Nude", "grandparentTitle": "Radiohead",
            "parentTitle": "In Rainbows", "duration": 255000,
            "Media": [{"Part": [{"key": "/library/parts/9/1600/file.flac"}]}]},
    "102": {"ratingKey": "102", "type": "track", "title": "Some Unknown Demo", "grandparentTitle": "Nobody",
            "duration": 100000, "Media": [{"Part": [{"key": "/library/parts/10/1600/file.mp3"}]}]},
}


class FakeServers:
    def __init__(self):
        self.calls = []
        self.now_playing = []
        self.pin_claimed = False
        now = int(time.time())
        self.plex_history = [  # newest first, as Plex sorts with viewedAt:desc
            {"ratingKey": "102", "type": "track", "viewedAt": now - 100, "accountID": 1},
            {"ratingKey": "101", "type": "track", "viewedAt": now - 600, "accountID": 1},
            {"ratingKey": "999", "type": "episode", "viewedAt": now - 700, "accountID": 1},
        ]

    def subsonic(self, endpoint, params):
        token = hashlib.md5((ND_PASSWORD + params["s"]).encode()).hexdigest()
        if params.get("u") != "alice" or params.get("t") != token:
            return {"status": "failed", "error": {"code": 40, "message": "Wrong username or password"}}
        ok = {"status": "ok", "version": "1.16.1", "type": "navidrome"}
        if endpoint == "ping":
            return ok
        if endpoint == "search3":
            q = params["query"].lower()
            songs = [s for s in ND_SONGS if not q or q in s["title"].lower()]
            offset = int(params.get("songOffset", 0))
            return {**ok, "searchResult3": {"song": songs[offset: offset + int(params["songCount"])]}}
        if endpoint == "getNowPlaying":
            return {**ok, "nowPlaying": {"entry": self.now_playing}}
        if endpoint == "getPlaylists":
            return {**ok, "playlists": {"playlist": [{"id": "pl-1", "name": "Late night", "songCount": 3}]}}
        if endpoint == "getPlaylist":
            return {**ok, "playlist": {"id": "pl-1", "entry": [ND_SONGS[0], ND_SONGS[2], {"id": "nd-x", "title": "Zzz", "artist": "Nope"}]}}
        if endpoint == "getSong":
            return {**ok, "song": next(s for s in ND_SONGS if s["id"] == params["id"])}
        return {"status": "failed", "error": {"code": 70, "message": "not found"}}

    def __call__(self, method, url, **kwargs):
        parts = urlsplit(url)
        params = kwargs.get("params") or {}
        headers = kwargs.get("headers") or {}
        self.calls.append((method, url, params))
        if url.startswith(ND + "/rest/"):
            return FakeResponse(data={"subsonic-response": self.subsonic(parts.path.rsplit("/", 1)[-1], params)})
        if url.startswith(PLEX):
            if headers.get("X-Plex-Token") != "server-token":
                return FakeResponse(401, {})
            path = parts.path
            if path == "/identity":
                return FakeResponse(data={"MediaContainer": {"machineIdentifier": "abc"}})
            if path == "/library/sections/all":
                return FakeResponse(data={"MediaContainer": {"Directory": [{"key": "1", "type": "artist"}, {"key": "2", "type": "movie"}]}})
            if path == "/library/sections/1/all":
                return FakeResponse(data={"MediaContainer": {"Metadata": list(PLEX_TRACKS.values())}})
            if path == "/status/sessions/history/all":
                return FakeResponse(data={"MediaContainer": {"Metadata": self.plex_history}})
            if path.startswith("/library/metadata/"):
                md = PLEX_TRACKS.get(path.rsplit("/", 1)[-1])
                return FakeResponse(data={"MediaContainer": {"Metadata": [md] if md else []}})
            if path == "/playlists":
                return FakeResponse(data={"MediaContainer": {"Metadata": []}})
            return FakeResponse(404, {})
        if url == "https://plex.tv/api/v2/pins":
            return FakeResponse(data={"id": 4242, "code": "ABCD"})
        if url == "https://plex.tv/api/v2/pins/4242":
            return FakeResponse(data={"id": 4242, "authToken": "user-token" if self.pin_claimed else None})
        if url == "https://clients.plex.tv/api/v2/resources":
            return FakeResponse(data=[
                {"name": "Living room", "provides": "server", "owned": True, "clientIdentifier": "srv-1",
                 "accessToken": "server-token",
                 "connections": [{"uri": "https://relay.example:443", "relay": True, "local": False},
                                 {"uri": PLEX, "local": True, "relay": False}]},
                {"name": "My phone", "provides": "client,player", "clientIdentifier": "phone"},
            ])
        raise AssertionError(f"unexpected request {method} {url}")


@pytest.fixture()
def servers(monkeypatch):
    fake = FakeServers()
    monkeypatch.setattr(media_base, "http", fake)
    return fake


@pytest.fixture()
def alice(make_user):
    return make_user("alice")


def connect_navidrome(client, headers, password=ND_PASSWORD, **extra):
    return client.post("/api/servers", json={"kind": "navidrome", "url": ND + "/", "username": "alice",
                                             "password": password, **extra}, headers=headers)


# --- connecting -------------------------------------------------------------------------------


def test_connect_navidrome_indexes_library_and_encrypts_password(client, auth, alice, servers):
    headers = auth(alice)
    assert connect_navidrome(client, headers, password="wrong").status_code == 400
    res = connect_navidrome(client, headers)
    assert res.status_code == 201
    server = res.get_json()["server"]
    assert server["name"] == "Navidrome" and server["url"] == ND
    assert server["library_count"] == 3
    assert "password" not in server and "secret" not in server

    row = db.session.get(MediaServer, server["id"])
    assert ND_PASSWORD not in row.secret  # stored encrypted
    assert connect_navidrome(client, headers).status_code == 409  # one per kind

    me = client.get("/api/me", headers=headers).get_json()
    assert me["has_servers"] is True


def test_owned_flags_only_with_a_server(client, auth, alice, servers):
    headers = auth(alice)
    items = client.get("/api/songs?q=nude", headers=headers).get_json()["items"]
    assert "owned" not in items[0]  # no server: no icons at all

    connect_navidrome(client, headers)
    items = {t["id"]: t for t in client.get("/api/songs?q=nude teardrop", headers=headers).get_json()["items"]}
    assert items[NUDE]["owned"] is True  # same title + artist
    assert items[TEARDROP]["owned"] is True  # via the MusicBrainz id ("2019 Remaster" is ignored too)

    detail = client.get(f"/api/songs/{NUDE}", headers=headers).get_json()
    assert detail["owned"] is True


def test_library_search_and_match(client, auth, alice, servers):
    headers = auth(alice)
    assert client.get("/api/library?q=nude", headers=headers).get_json()["items"] == []
    connect_navidrome(client, headers)

    found = client.get("/api/library?q=radiohead", headers=headers).get_json()
    assert found["total"] == 2
    weird = next(t for t in found["items"] if t["title"].startswith("Weird"))
    assert weird["library_only"] is True and weird["id"] is None  # not in the fake catalog

    nude = client.get("/api/library?q=nude", headers=headers).get_json()["items"][0]
    matched = client.post(f"/api/library/tracks/{nude['track_id']}/match", headers=headers).get_json()
    assert matched["id"] == NUDE and matched["owned"] is True
    assert client.post(f"/api/library/tracks/{weird['track_id']}/match", headers=headers).status_code == 404


def test_navidrome_now_playing_is_logged_once(client, auth, alice, servers):
    from app.services.sync import sync_server

    headers = auth(alice)
    sid = connect_navidrome(client, headers).get_json()["server"]["id"]
    servers.now_playing = [{**ND_SONGS[0], "username": "alice", "minutesAgo": 1},
                           {**ND_SONGS[1], "username": "someone-else", "minutesAgo": 0}]
    sync_server(sid, ["listens"])
    sync_server(sid, ["listens"])  # still playing on the next poll: not logged twice
    rows = ListeningHistory.query.all()
    assert len(rows) == 1 and rows[0].source == "navidrome"
    assert rows[0].song.mbid == NUDE


def test_playlist_sync_mirrors_the_server(client, auth, alice, servers):
    from app.services.sync import sync_server

    headers = auth(alice)
    sid = connect_navidrome(client, headers, sync_playlists=True).get_json()["server"]["id"]
    playlists = client.get("/api/playlists", headers=headers).get_json()["items"]
    assert [p["name"] for p in playlists] == ["Late night"]
    assert playlists[0]["synced_from"] == "navidrome"
    detail = client.get(f"/api/playlists/{playlists[0]['id']}", headers=headers).get_json()
    assert [s["id"] for s in detail["songs"]] == [NUDE, TEARDROP]  # the unknown track is skipped

    sync_server(sid, ["playlists"])
    assert Playlist.query.count() == 1
    assert len(client.get(f"/api/playlists/{playlists[0]['id']}", headers=headers).get_json()["songs"]) == 2


def test_disconnect_keeps_playlists(client, auth, alice, servers):
    headers = auth(alice)
    sid = connect_navidrome(client, headers, sync_playlists=True).get_json()["server"]["id"]
    assert client.delete(f"/api/servers/{sid}", headers=auth(alice)).status_code == 200
    assert ServerTrack.query.count() == 0
    playlist = client.get("/api/playlists", headers=headers).get_json()["items"][0]
    assert playlist["synced_from"] is None
    assert client.get("/api/me", headers=headers).get_json()["has_servers"] is False


def test_servers_are_private(client, auth, alice, make_user, servers):
    bob = auth(make_user("bobby"))
    sid = connect_navidrome(client, auth(alice)).get_json()["server"]["id"]
    assert client.get("/api/servers", headers=bob).get_json()["items"] == []
    assert client.delete(f"/api/servers/{sid}", headers=bob).status_code == 404
    assert client.patch(f"/api/servers/{sid}", json={"sync_listens": False}, headers=bob).status_code == 404
    track = ServerTrack.query.first()
    assert client.get(f"/api/stream/{track.id}", headers=bob).status_code == 404
    assert client.post(f"/api/library/tracks/{track.id}/match", headers=bob).status_code == 404
    assert client.post("/api/history", json={"track_id": track.id}, headers=bob).status_code == 404


def test_private_urls_can_be_blocked(client, auth, alice, servers, monkeypatch):
    from app.utility import config

    monkeypatch.setattr(config, "ALLOW_PRIVATE_SERVER_URLS", False)
    res = client.post("/api/servers", json={"kind": "navidrome", "url": "http://127.0.0.1:4533",
                                            "username": "alice", "password": ND_PASSWORD}, headers=auth(alice))
    assert res.status_code == 400
    assert "Private" in res.get_json()["error"]


# --- Plex ---------------------------------------------------------------------------------------


def test_plex_pin_sign_in_and_history_import(client, make_user, servers):
    make_user("alice")
    client.post("/auth/login", json={"email": "alice@example.com", "password": PASSWORD})

    pin = client.post("/api/servers/plex/pin", json={}).get_json()
    assert pin["auth_url"].startswith("https://app.plex.tv/auth#?clientID=")
    assert "code=ABCD" in pin["auth_url"]
    assert client.get(f"/api/servers/plex/pin/{pin['pin_id']}").get_json() == {"status": "waiting"}
    assert client.get("/api/servers/plex/pin/1").status_code == 404  # not our PIN

    servers.pin_claimed = True
    ready = client.get(f"/api/servers/plex/pin/{pin['pin_id']}").get_json()
    assert ready["servers"] == [{"id": "srv-1", "name": "Living room", "owned": True}]

    res = client.post("/api/servers", json={"kind": "plex", "server": "srv-1"})
    assert res.status_code == 201, res.get_json()
    server = res.get_json()["server"]
    assert server["url"] == PLEX  # the local connection that answered, not the relay
    assert server["library_count"] == 2

    # history: owner token sees everyone, so WAYL asks for the owner's account only
    history_calls = [p for _, u, p in servers.calls if u.endswith("/status/sessions/history/all")]
    assert history_calls[0]["accountID"] == 1
    listens = ListeningHistory.query.all()
    assert [l.song.mbid for l in listens] == [NUDE] and listens[0].source == "plex"
    unmatched = client.get("/api/me/unmatched").get_json()
    assert unmatched["unmatched"] == 1 and unmatched["items"][0]["title"] == "Some Unknown Demo"

    from app.services.sync import sync_server

    sync_server(server["id"], ["listens"])  # cursor: nothing new
    assert ListeningHistory.query.count() == 1


def test_plex_manual_connection(client, auth, alice, servers):
    headers = auth(alice)
    bad = client.post("/api/servers", json={"kind": "plex", "url": PLEX, "token": "nope"}, headers=headers)
    assert bad.status_code == 400
    ok = client.post("/api/servers", json={"kind": "plex", "url": PLEX, "token": "server-token"}, headers=headers)
    assert ok.status_code == 201


# --- streaming ------------------------------------------------------------------------------------


def test_sources_and_stream_proxy(client, auth, alice, servers, monkeypatch):
    import app.routes.stream as stream_mod

    headers = auth(alice)
    client.post("/api/servers", json={"kind": "plex", "url": PLEX, "token": "server-token"}, headers=headers)
    sources = client.get(f"/api/songs/{NUDE}/sources", headers=headers).get_json()["items"]
    assert len(sources) == 1 and sources[0]["server"] == "plex"

    seen = {}

    def fake_get(url, params=None, headers=None, stream=False, timeout=None):
        seen.update(url=url, headers=headers)
        return FakeResponse(206, headers={"Content-Type": "audio/flac", "Content-Range": "bytes 0-3/10",
                                          "Content-Length": "4"}, content=b"fLaC")

    monkeypatch.setattr(stream_mod.requests, "get", fake_get)
    res = client.get(sources[0]["stream_url"], headers={**headers, "Range": "bytes=0-3"})
    assert res.status_code == 206
    assert res.data == b"fLaC"
    assert res.headers["Content-Range"] == "bytes 0-3/10"
    assert seen["url"] == PLEX + "/library/parts/9/1600/file.flac"
    assert seen["headers"]["Range"] == "bytes=0-3"
    assert seen["headers"]["X-Plex-Token"] == "server-token"  # added server-side only

    # Subsonic errors come back as 200 + JSON: never pass them off as audio
    monkeypatch.setattr(stream_mod.requests, "get", lambda *a, **k: FakeResponse(200, {"x": 1}))
    assert client.get(sources[0]["stream_url"], headers=headers).status_code == 502


def test_player_listens_from_library_tracks(client, auth, alice, servers):
    headers = auth(alice)
    connect_navidrome(client, headers)
    nude = client.get("/api/library?q=nude", headers=headers).get_json()["items"][0]
    res = client.post("/api/history", json={"track_id": nude["track_id"], "source": "player"}, headers=headers)
    assert res.status_code == 201
    assert ListeningHistory.query.one().source == "player"


# --- ListenBrainz-compatible API -------------------------------------------------------------------


def lb_listen(title="Nude", artist="Radiohead", ts=None, **info):
    return {"listened_at": ts or int(time.time()) - 60,
            "track_metadata": {"artist_name": artist, "track_name": title, "additional_info": info}}


def test_listenbrainz_compatible_api(client, auth, alice):
    headers = auth(alice)
    token = client.post("/api/me/listen-token", headers=headers).get_json()["token"]
    lb = {"Authorization": f"Token {token}"}

    assert client.get("/listenbrainz/1/validate-token").status_code == 400
    bad = client.get("/listenbrainz/1/validate-token", headers={"Authorization": "Token nope"}).get_json()
    assert bad == {"code": 200, "message": "Token invalid.", "valid": False}
    good = client.get("/listenbrainz/1/validate-token", headers=lb).get_json()
    assert good["valid"] is True and good["user_name"] == "alice"

    assert client.post("/listenbrainz/1/submit-listens", json={"listen_type": "single", "payload": [lb_listen()]},
                       headers={"Authorization": "Token nope"}).status_code == 401
    assert client.post("/listenbrainz/1/submit-listens", json={"listen_type": "single", "payload": []},
                       headers=lb).status_code == 400

    now_playing = {"listen_type": "playing_now", "payload": [{"track_metadata": lb_listen()["track_metadata"]}]}
    assert client.post("/listenbrainz/1/submit-listens", json=now_playing, headers=lb).get_json() == {"status": "ok"}
    assert ListeningHistory.query.count() == 0

    single = {"listen_type": "single", "payload": [lb_listen(media_player="Navidrome")]}
    assert client.post("/listenbrainz/1/submit-listens", json=single, headers=lb).get_json() == {"status": "ok"}
    client.post("/listenbrainz/1/submit-listens", json=single, headers=lb)  # retried by the player
    rows = ListeningHistory.query.all()
    assert len(rows) == 1 and rows[0].source == "navidrome" and rows[0].song.mbid == NUDE

    now = int(time.time())
    batch = {"listen_type": "import", "payload": [
        lb_listen("Teardrop", "Massive Attack", ts=now - 4000, recording_mbid=TEARDROP),
        lb_listen("Unknown Song", "Unknown Band", ts=now - 5000),
        lb_listen("Nude", "Radiohead", ts=now - 9000),
        lb_listen("Nude", "Radiohead", ts=now - 20000),
    ]}
    assert client.post("/listenbrainz/1/submit-listens", json=batch, headers=lb).status_code == 200
    assert ListeningHistory.query.count() == 4
    unmatched = client.get("/api/me/unmatched", headers=headers).get_json()
    assert unmatched["unmatched"] == 1
    assert client.delete("/api/me/unmatched", headers=headers).status_code == 200
    assert IncomingListen.query.count() == 0

    client.delete("/api/me/listen-token", headers=headers)
    assert client.get("/listenbrainz/1/validate-token", headers=lb).get_json()["valid"] is False


def test_delete_account_with_server(client, auth, alice, servers):
    headers = auth(alice)
    connect_navidrome(client, headers, sync_playlists=True)
    client.post("/api/me/listen-token", headers=headers)
    assert client.delete("/api/me", json={"password": PASSWORD}, headers=headers).status_code == 200
    assert MediaServer.query.count() == 0 and ServerTrack.query.count() == 0


def test_healthz(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}


def test_title_normalization():
    from app.services.matching import artists_match, norm_artist, norm_title

    assert norm_title("Teardrop - 2006 Remaster") == "teardrop"
    assert norm_title("Get Lucky (feat. Pharrell Williams)") == "get lucky"
    assert norm_title("Bohemian Rhapsody (Remastered 2011)") == "bohemian rhapsody"
    assert norm_title("Live Forever (Live)") == "live forever live"  # live versions stay distinct
    assert artists_match(norm_artist("Daft Punk feat. Pharrell"), norm_artist("Daft Punk"))
    assert artists_match(norm_artist("Simon & Garfunkel"), norm_artist("Simon"))
    assert not artists_match(norm_artist("Queen"), norm_artist("Queensryche"))
