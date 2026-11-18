"""Publishing share links: /share/v1/p/<token>, /share/v1/u/<token> and the owner endpoints."""
import json

from app.models import db
from app.models.music import Artist, Playlist, PlaylistSong, Song
from app.services import share_docs
from app.services.media import base as media_base
from tests.conftest import NUDE, RADIOHEAD, TEARDROP
from tests.test_servers import ND, ND_PASSWORD, FakeServers

TRACK_KEYS = {"mbid", "title", "artist", "artist_mbid", "album", "cover", "duration"}


def make_playlist(client, headers, songs=(NUDE, TEARDROP), name="Late night"):
    pid = client.post("/api/playlists", json={"name": name}, headers=headers).get_json()["id"]
    for mbid in songs:
        client.post(f"/api/playlists/{pid}", json={"song_id": mbid}, headers=headers)
    return pid


def share(client, headers, pid):
    res = client.put(f"/api/playlists/{pid}/share", headers=headers)
    assert res.status_code == 200
    return res.get_json()["url"]


def path_of(url):
    return url.replace("https://wayl.test", "")


def test_playlist_document(client, make_user, auth, monkeypatch):
    monkeypatch.setattr(media_base, "http", FakeServers())
    alice = make_user("alice")
    headers = auth(alice)
    # a connected server must not leak into the document
    client.post("/api/servers", json={"kind": "navidrome", "url": ND, "username": "alice", "password": ND_PASSWORD}, headers=headers)
    pid = make_playlist(client, headers)
    url = share(client, headers, pid)
    assert url.startswith("https://wayl.test/share/v1/p/")

    res = client.get(path_of(url))
    assert res.status_code == 200
    assert res.headers["Access-Control-Allow-Origin"] == "*"
    assert res.headers["Cache-Control"] == "public, max-age=300"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert "Set-Cookie" not in res.headers
    doc = res.get_json()
    assert set(doc) == {"wayl_share", "kind", "id", "url", "name", "owner", "updated_at", "tracks"}
    assert doc["wayl_share"] == 1 and doc["kind"] == "playlist" and doc["url"] == url
    assert doc["owner"] == {"name": "alice", "profile_url": None}
    assert doc["updated_at"].endswith("Z")
    assert [t["mbid"] for t in doc["tracks"]] == [NUDE, TEARDROP]
    assert all(set(t) == TRACK_KEYS for t in doc["tracks"])
    assert doc["tracks"][0]["artist_mbid"] == RADIOHEAD

    raw = res.get_data(as_text=True)
    for private in ("example.com", "email", "nd.test", "track_id", "user_id", "owner_id", "source", "password"):
        assert private not in raw, private


def test_unknown_unshared_and_reset_links_404(client, make_user, auth):
    headers = auth(make_user("alice"))
    assert client.get("/share/v1/p/nope").status_code == 404
    assert client.get("/share/v1/p/" + "x" * 200).status_code == 404
    pid = make_playlist(client, headers)
    old = share(client, headers, pid)
    assert share(client, headers, pid) == old  # PUT again keeps the same link

    new = client.post(f"/api/playlists/{pid}/share/reset", headers=headers).get_json()["url"]
    assert new != old
    assert client.get(path_of(old)).status_code == 404
    assert client.get(path_of(new)).status_code == 200

    client.delete(f"/api/playlists/{pid}/share", headers=headers)
    assert client.get(path_of(new)).status_code == 404
    assert client.get(f"/api/playlists/{pid}/share", headers=headers).get_json() == {"shared": False, "url": None}


def test_only_the_owner_can_share(client, make_user, auth):
    alice, bob = auth(make_user("alice")), auth(make_user("bobby"))
    pid = make_playlist(client, alice)
    for method in ("put", "delete", "get"):
        assert getattr(client, method)(f"/api/playlists/{pid}/share", headers=bob).status_code == 404
    assert client.post(f"/api/playlists/{pid}/share/reset", headers=bob).status_code == 404
    assert client.put(f"/api/playlists/{pid}/share").status_code == 401


def test_etag_304(client, make_user, auth):
    headers = auth(make_user("alice"))
    path = path_of(share(client, headers, make_playlist(client, headers)))
    first = client.get(path)
    etag = first.headers["ETag"]
    assert first.headers["Last-Modified"]
    again = client.get(path, headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.data == b""
    assert again.headers["Access-Control-Allow-Origin"] == "*"
    # content changes -> new ETag
    pid = Playlist.query.first().id
    client.delete(f"/api/playlists/{pid}/songs/{TEARDROP}", headers=headers)
    changed = client.get(path, headers={"If-None-Match": etag})
    assert changed.status_code == 200 and changed.headers["ETag"] != etag


def test_jspf(client, make_user, auth):
    headers = auth(make_user("alice"))
    path = path_of(share(client, headers, make_playlist(client, headers)))
    jspf = client.get(path + "?format=jspf").get_json()["playlist"]
    assert jspf["title"] == "Late night" and jspf["creator"] == "alice"
    assert jspf["track"][0]["identifier"] == [f"https://musicbrainz.org/recording/{NUDE}"]
    assert jspf["track"][0]["duration"] == 255000


def test_tracks_without_mbid_are_skipped_and_caps_apply(client, make_user, auth, monkeypatch):
    headers = auth(make_user("alice"))
    pid = make_playlist(client, headers)
    artist = Artist(name="Local band")
    db.session.add(artist)
    db.session.flush()
    nameless = Song(mbid="", title="Untagged", artist_id=artist.id)
    db.session.add(nameless)
    db.session.flush()
    db.session.add(PlaylistSong(playlist_id=pid, song_id=nameless.id))
    db.session.commit()
    path = path_of(share(client, headers, pid))
    titles = [t["title"] for t in client.get(path).get_json()["tracks"]]
    assert "Untagged" not in titles and len(titles) == 2

    monkeypatch.setattr(share_docs, "MAX_TRACKS", 1)
    assert len(client.get(path).get_json()["tracks"]) == 1


def test_profile_document_and_opt_ins(client, make_user, auth):
    alice = make_user("alice")
    headers = auth(alice)
    shared = make_playlist(client, headers, name="Shared one")
    make_playlist(client, headers, name="Private one")
    share(client, headers, shared)
    client.post("/api/history", json={"song_id": NUDE}, headers=headers)

    info = client.get("/api/me/sharing", headers=headers).get_json()
    assert info == {"enabled": False, "url": None, "share_listens": False, "share_top_artists": False, "display_name": "alice"}
    info = client.patch("/api/me/sharing", json={"enabled": True, "display_name": "Eli"}, headers=headers).get_json()
    profile_path = path_of(info["url"])

    doc = client.get(profile_path).get_json()
    assert doc["kind"] == "profile" and doc["name"] == "Eli"
    assert [p["name"] for p in doc["playlists"]] == ["Shared one"]
    assert doc["playlists"][0]["track_count"] == 2
    assert "recent_listens" not in doc and "top_artists" not in doc  # off by default
    assert "example.com" not in client.get(profile_path).get_data(as_text=True)

    # the shared playlist now points back at the profile, with the display name
    playlist_doc = client.get(path_of(client.get(f"/api/playlists/{shared}/share", headers=headers).get_json()["url"])).get_json()
    assert playlist_doc["owner"] == {"name": "Eli", "profile_url": info["url"]}

    client.patch("/api/me/sharing", json={"share_listens": True, "share_top_artists": True}, headers=headers)
    doc = client.get(profile_path).get_json()
    assert doc["recent_listens"][0]["track"]["mbid"] == NUDE
    assert set(doc["recent_listens"][0]) == {"listened_at", "track"}
    assert doc["top_artists"] == [{"name": "Radiohead", "mbid": RADIOHEAD, "plays": 1}]

    reset = client.post("/api/me/sharing/reset", headers=headers).get_json()["url"]
    assert client.get(profile_path).status_code == 404
    client.patch("/api/me/sharing", json={"enabled": False}, headers=headers)
    assert client.get(path_of(reset)).status_code == 404
    assert client.patch("/api/me/sharing", json={"display_name": "x" * 61}, headers=headers).status_code == 400


def test_localhost_app_url_warning(client, make_user, auth, monkeypatch):
    from app.utility import config

    headers = auth(make_user("alice"))
    pid = make_playlist(client, headers)
    assert "warning" not in client.put(f"/api/playlists/{pid}/share", headers=headers).get_json()
    monkeypatch.setattr(config, "APP_URL", "http://localhost:5000")
    res = client.get(f"/api/playlists/{pid}/share", headers=headers).get_json()
    assert res["url"].startswith("http://localhost:5000/share/v1/p/")
    assert "APP_URL" in res["warning"]
    assert "warning" in client.get("/api/me/sharing", headers=headers).get_json()


def test_owner_sees_share_state_on_the_playlist(client, make_user, auth):
    alice, bob = auth(make_user("alice")), auth(make_user("bobby"))
    pid = make_playlist(client, alice)
    share(client, alice, pid)
    client.patch(f"/api/playlists/{pid}", json={"is_public": True}, headers=alice)
    assert client.get(f"/api/playlists/{pid}", headers=alice).get_json()["share"]["shared"] is True
    assert "share" not in client.get(f"/api/playlists/{pid}", headers=bob).get_json()  # not the owner
    assert client.get("/api/playlists", headers=alice).get_json()["items"][0]["shared"] is True


def test_share_documents_are_valid_json_with_stable_etag(client, make_user, auth):
    headers = auth(make_user("alice"))
    path = path_of(share(client, headers, make_playlist(client, headers)))
    a, b = client.get(path), client.get(path)
    assert a.headers["ETag"] == b.headers["ETag"]
    json.loads(a.data)
