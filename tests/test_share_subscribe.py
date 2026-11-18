"""Subscribing to share links. Remote fetches go to a fake _http_get that, for wayl.test URLs,
calls the real publishing views of the same test app, so real documents go through the real
validator. Other hosts serve canned (often hostile) responses."""
import json
import socket
from datetime import timedelta

import pytest

from app.models import db, utcnow
from app.models.music import Playlist
from app.models.sharing import Subscription
from app.services import remote_share
from app.services.media import base as media_base
from app.services.remote_share import ShareError, parse_document
from tests.conftest import NUDE, PASSWORD, TEARDROP
from tests.test_servers import ND, ND_PASSWORD, FakeServers

OTHER = "33333333-aaaa-4aaa-8aaa-333333333333"


class Resp:
    def __init__(self, status=200, body=b"", headers=None):
        self.status_code = status
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = {"Content-Type": "application/json", **(headers or {})}

    def iter_content(self, size):
        for i in range(0, len(self.body), size):
            yield self.body[i : i + size]

    def close(self):
        pass


class FakeRemote:
    def __init__(self, app):
        self.app = app
        self.routes = {}  # url -> Resp (for non-wayl.test hosts)
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        if url.startswith("https://wayl.test/"):
            res = self.app.test_client().get(url[len("https://wayl.test"):], headers=headers)  # no cookies
            return Resp(res.status_code, res.data, dict(res.headers))
        if url in self.routes:
            return self.routes[url]
        return Resp(404, {"error": "nope"})


@pytest.fixture()
def remote(app, monkeypatch):
    fake = FakeRemote(app)
    monkeypatch.setattr(remote_share, "_http_get", fake)
    return fake


@pytest.fixture()
def shared(client, make_user, auth):
    """alice shares a playlist with Nude + Teardrop; returns (url, alice headers, playlist id)."""
    headers = auth(make_user("alice"))
    pid = client.post("/api/playlists", json={"name": "Late night"}, headers=headers).get_json()["id"]
    for mbid in (NUDE, TEARDROP):
        client.post(f"/api/playlists/{pid}", json={"song_id": mbid}, headers=headers)
    url = client.put(f"/api/playlists/{pid}/share", headers=headers).get_json()["url"]
    return url, headers, pid


def playlist_doc(tracks, name="Mix", **extra):
    return {"wayl_share": 1, "kind": "playlist", "id": "t", "url": "https://friend.example/share/v1/p/t",
            "name": name, "owner": {"name": "sam", "profile_url": None}, "updated_at": "2026-11-18T17:00:00Z",
            "tracks": tracks, **extra}


def track(mbid=NUDE, title="Nude", artist="Radiohead", **extra):
    return {"mbid": mbid, "title": title, "artist": artist, "artist_mbid": None, "album": None,
            "cover": None, "duration": 255, **extra}


# --- adding ------------------------------------------------------------------------------------


def test_subscribe_list_and_detail_without_server(client, make_user, auth, remote, shared):
    url, _, _ = shared
    bob = auth(make_user("bobby"))
    res = client.post("/api/subscriptions", json={"url": url}, headers=bob)
    assert res.status_code == 201
    sub = res.get_json()
    assert sub["kind"] == "playlist" and sub["title"] == "Late night" and sub["owner_name"] == "alice"
    assert sub["count"] == 2 and sub["fetched_at"].endswith("Z") and sub["last_error"] is None

    again = client.post("/api/subscriptions", json={"url": url + "/"}, headers=bob)  # same link, pasted differently
    assert again.status_code == 200 and again.get_json()["id"] == sub["id"]
    assert [s["id"] for s in client.get("/api/subscriptions", headers=bob).get_json()["items"]] == [sub["id"]]

    detail = client.get(f"/api/subscriptions/{sub['id']}", headers=bob).get_json()
    assert [t["id"] for t in detail["tracks"]] == [NUDE, TEARDROP]
    assert all(t["owned"] is None for t in detail["tracks"])  # bob has no server: unknown, not "no"
    assert detail["owned_count"] is None and detail["total"] == 2


def test_owned_annotation_with_a_server(client, make_user, auth, remote, shared, monkeypatch):
    monkeypatch.setattr(media_base, "http", FakeServers())
    url, _, _ = shared
    bob = auth(make_user("bobby"))
    client.post("/api/servers", json={"kind": "navidrome", "url": ND, "username": "alice", "password": ND_PASSWORD}, headers=bob)
    sid = client.post("/api/subscriptions", json={"url": url}, headers=bob).get_json()["id"]
    detail = client.get(f"/api/subscriptions/{sid}", headers=bob).get_json()
    by_id = {t["id"]: t for t in detail["tracks"]}
    assert by_id[NUDE]["owned"] is True and isinstance(by_id[NUDE]["track_id"], int)
    assert by_id[TEARDROP]["owned"] is True  # via the MusicBrainz id on the server's file
    assert detail["owned_count"] == 2
    # the track_id plays through the normal stream endpoint (it's bob's own library track)
    assert client.get(f"/api/library?q=nude", headers=bob).get_json()["items"][0]["track_id"] == by_id[NUDE]["track_id"]


@pytest.mark.parametrize("resp, message", [
    (Resp(200, {"hello": "world"}), "isn't a WAYL share link"),
    (Resp(200, {"wayl_share": 2, "kind": "playlist", "name": "x"}), "newer format"),
    (Resp(200, {"wayl_share": 1, "kind": "something", "name": "x"}), "Unknown kind"),
    (Resp(200, b"<html>hi</html>", {"Content-Type": "text/html"}), "isn't a WAYL share link"),
    (Resp(200, b"{" + b" " * (1024 * 1024 + 10) + b"}"), "too big"),
    (Resp(404, {"error": "gone"}), "doesn't exist"),
    (Resp(500, {"error": "boom"}), "HTTP 500"),
])
def test_bad_documents_are_rejected(client, make_user, auth, remote, resp, message):
    remote.routes["https://friend.example/share/v1/p/x"] = resp
    res = client.post("/api/subscriptions", json={"url": "https://friend.example/share/v1/p/x"}, headers=auth(make_user("bobby")))
    assert res.status_code == 400
    assert message in res.get_json()["error"]
    assert Subscription.query.count() == 0


def test_private_addresses_rejected_when_not_allowed(client, make_user, auth, remote, monkeypatch):
    from app.utility import config

    monkeypatch.setattr(config, "ALLOW_PRIVATE_SERVER_URLS", False)
    bob = auth(make_user("bobby"))
    for url in ("http://127.0.0.1/share/v1/p/x", "http://10.1.2.3:8000/share/v1/p/x", "http://[::1]/share/v1/p/x"):
        res = client.post("/api/subscriptions", json={"url": url}, headers=bob)
        assert res.status_code == 400 and "Private" in res.get_json()["error"], url
    assert remote.calls == []  # never fetched

    real = socket.getaddrinfo

    def fake_dns(host, *args, **kwargs):
        ips = {"friend.example": "93.184.216.34", "evil.example": "10.0.0.5"}
        if host in ips:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ips[host], 443))]
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_dns)
    remote.routes["https://friend.example/share/v1/p/x"] = Resp(302, b"", {"Location": "https://evil.example/admin"})
    res = client.post("/api/subscriptions", json={"url": "https://friend.example/share/v1/p/x"}, headers=bob)
    assert res.status_code == 400 and "redirected somewhere WAYL won't go" in res.get_json()["error"]
    assert [u for u, _ in remote.calls] == ["https://friend.example/share/v1/p/x"]  # evil.example never requested


def test_redirect_limit(client, make_user, auth, remote):
    for i in range(5):
        remote.routes[f"https://friend.example/{i}"] = Resp(302, b"", {"Location": f"https://friend.example/{i + 1}"})
    res = client.post("/api/subscriptions", json={"url": "https://friend.example/0"}, headers=auth(make_user("bobby")))
    assert res.status_code == 400 and "Too many redirects" in res.get_json()["error"]


# --- refreshing ----------------------------------------------------------------------------------


def test_worker_refresh_interval_304_and_errors(client, make_user, auth, remote, shared):
    from app.services.subscriptions import refresh_due

    url, alice, pid = shared
    bob = auth(make_user("bobby"))
    sid = client.post("/api/subscriptions", json={"url": url}, headers=bob).get_json()["id"]
    sub = db.session.get(Subscription, sid)

    remote.calls.clear()
    assert refresh_due() == 0 and remote.calls == []  # just fetched: not due

    sub.checked_at = sub.fetched_at = utcnow() - timedelta(hours=7)
    db.session.commit()
    assert refresh_due() == 1
    assert remote.calls[-1][1]["If-None-Match"] == sub.etag  # conditional request -> 304
    assert sub.last_error is None and utcnow() - sub.fetched_at < timedelta(minutes=1)

    # the owner turns sharing off: the refresh fails, the last good copy stays
    client.delete(f"/api/playlists/{pid}/share", headers=alice)
    sub.checked_at = utcnow() - timedelta(hours=7)
    db.session.commit()
    good_payload = sub.payload
    refresh_due()
    assert sub.error_count == 1 and "doesn't exist" in sub.last_error
    assert sub.payload == good_payload
    assert client.get(f"/api/subscriptions/{sid}", headers=bob).get_json()["total"] == 2

    # backoff: after one error the next try waits 2x the interval
    sub.checked_at = utcnow() - timedelta(hours=7)
    db.session.commit()
    assert refresh_due() == 0
    sub.checked_at = utcnow() - timedelta(hours=13)
    db.session.commit()
    assert refresh_due() == 1 and sub.error_count == 2


def test_manual_refresh_picks_up_changes(client, make_user, auth, remote, shared):
    url, alice, pid = shared
    bob = auth(make_user("bobby"))
    sid = client.post("/api/subscriptions", json={"url": url}, headers=bob).get_json()["id"]
    client.delete(f"/api/playlists/{pid}/songs/{TEARDROP}", headers=alice)
    detail = client.post(f"/api/subscriptions/{sid}/refresh", headers=bob).get_json()
    assert detail["total"] == 1 and detail["last_error"] is None


# --- copying ---------------------------------------------------------------------------------------


def test_copy_uses_batched_catalog_lookup(client, make_user, auth, remote, fake_catalog):
    remote.routes["https://friend.example/share/v1/p/t"] = Resp(200, playlist_doc([
        track(NUDE, "Renamed by a friend"), track(TEARDROP, "Teardrop", "Massive Attack"), track(OTHER, "Not in MusicBrainz"),
    ]))
    bob = auth(make_user("bobby"))
    sid = client.post("/api/subscriptions", json={"url": "https://friend.example/share/v1/p/t"}, headers=bob).get_json()["id"]
    fake_catalog.calls.clear()
    res = client.post(f"/api/subscriptions/{sid}/copy", headers=bob)
    assert res.status_code == 201
    assert res.get_json()["skipped"] == 1  # the unknown recording
    metadata_calls = [u for u in fake_catalog.calls if "/metadata/recording/" in u]
    assert len(metadata_calls) == 1  # one batched lookup for all tracks, not one per track

    playlist = db.session.get(Playlist, res.get_json()["playlist_id"])
    assert playlist.name == "Mix (from sam)" and playlist.user_id is not None
    titles = [ps.song.title for ps in playlist.songs]
    assert titles == ["Nude", "Teardrop"]  # titles come from MusicBrainz, not the remote document


def test_copy_from_the_same_instance(client, make_user, auth, remote, shared):
    url, _, _ = shared
    bob = auth(make_user("bobby"))
    sid = client.post("/api/subscriptions", json={"url": url}, headers=bob).get_json()["id"]
    pid = client.post(f"/api/subscriptions/{sid}/copy", headers=bob).get_json()["playlist_id"]
    mine = client.get(f"/api/playlists/{pid}", headers=bob).get_json()
    assert mine["name"] == "Late night (from alice)" and [s["id"] for s in mine["songs"]] == [NUDE, TEARDROP]


# --- profiles ----------------------------------------------------------------------------------------


def test_profile_subscription_open_and_copy(client, make_user, auth, remote, shared):
    url, alice, _ = shared
    profile_url = client.patch("/api/me/sharing", json={"enabled": True, "share_listens": True}, headers=alice).get_json()["url"]
    client.post("/api/history", json={"song_id": NUDE}, headers=alice)
    bob = auth(make_user("bobby"))
    sub = client.post("/api/subscriptions", json={"url": profile_url}, headers=bob).get_json()
    assert sub["kind"] == "profile" and sub["title"] == "alice" and sub["count"] == 1

    detail = client.get(f"/api/subscriptions/{sub['id']}", headers=bob).get_json()
    assert detail["playlists"][0]["name"] == "Late night" and detail["playlists"][0]["subscription_id"] is None
    assert detail["recent_listens"][0]["song"]["id"] == NUDE
    assert "top_artists" not in detail

    opened = client.post(f"/api/subscriptions/{sub['id']}/open", json={"url": url}, headers=bob).get_json()
    assert opened["kind"] == "playlist" and opened["parent_id"] == sub["id"] and opened["total"] == 2
    # children aren't listed on their own, but the profile links to them
    assert [s["id"] for s in client.get("/api/subscriptions", headers=bob).get_json()["items"]] == [sub["id"]]
    assert client.get(f"/api/subscriptions/{sub['id']}", headers=bob).get_json()["playlists"][0]["subscription_id"] == opened["id"]

    bad = client.post(f"/api/subscriptions/{sub['id']}/open", json={"url": "https://friend.example/share/v1/p/zzz"}, headers=bob)
    assert bad.status_code == 400  # only playlists listed by that profile

    copied = client.post(f"/api/subscriptions/{sub['id']}/copy", json={"playlist_url": url}, headers=bob)
    assert copied.status_code == 201

    assert client.delete(f"/api/subscriptions/{sub['id']}", headers=bob).status_code == 200
    assert Subscription.query.count() == 0  # child removed with its parent


def test_other_users_subscriptions_are_404(client, make_user, auth, remote, shared):
    url, _, _ = shared
    bob, carol = auth(make_user("bobby")), auth(make_user("carol"))
    sid = client.post("/api/subscriptions", json={"url": url}, headers=bob).get_json()["id"]
    assert client.get(f"/api/subscriptions/{sid}", headers=carol).status_code == 404
    assert client.post(f"/api/subscriptions/{sid}/refresh", headers=carol).status_code == 404
    assert client.post(f"/api/subscriptions/{sid}/copy", headers=carol).status_code == 404
    assert client.post(f"/api/subscriptions/{sid}/open", json={"url": url}, headers=carol).status_code == 404
    assert client.delete(f"/api/subscriptions/{sid}", headers=carol).status_code == 404
    assert client.get("/api/subscriptions", headers=carol).get_json()["items"] == []
    assert client.get("/api/subscriptions").status_code == 401


def test_account_deletion_removes_subscriptions(client, make_user, auth, remote, shared):
    url, alice, _ = shared
    profile_url = client.patch("/api/me/sharing", json={"enabled": True}, headers=alice).get_json()["url"]
    bobby = make_user("bobby")
    bob = auth(bobby)
    sid = client.post("/api/subscriptions", json={"url": profile_url}, headers=bob).get_json()["id"]
    client.post(f"/api/subscriptions/{sid}/open", json={"url": url}, headers=bob)
    assert client.delete("/api/me", json={"password": PASSWORD}, headers=bob).status_code == 200
    assert Subscription.query.count() == 0
    assert client.delete("/api/me", json={"password": PASSWORD}, headers=alice).status_code == 200


# --- the validator ----------------------------------------------------------------------------------


def test_validator_drops_bad_items_and_unknown_fields():
    doc = parse_document(playlist_doc(
        [
            track(),
            track(mbid="not-a-uuid"),
            track(title=""),
            "junk",
            track(TEARDROP, "T" * 1000, cover="javascript:alert(1)", duration=-5, extra="x"),
        ],
        name="  Late\nnight  ",
        evil="<script>",
        owner={"name": "s" * 500, "profile_url": "ftp://x", "email": "a@b.c"},
    ))
    assert set(doc) == {"wayl_share", "kind", "id", "url", "name", "updated_at", "owner", "tracks"}
    assert doc["name"] == "Late night"
    assert doc["owner"] == {"name": "s" * 60, "profile_url": None}
    assert [t["mbid"] for t in doc["tracks"]] == [NUDE, TEARDROP]
    t = doc["tracks"][1]
    assert len(t["title"]) == 300 and t["cover"] is None and t["duration"] is None and "extra" not in t


def test_validator_profile_caps():
    listens = [{"listened_at": "2026-11-18T17:00:00Z", "track": track()} for _ in range(80)]
    doc = parse_document({
        "wayl_share": 1, "kind": "profile", "name": "sam", "bio": "b" * 999,
        "playlists": [{"name": "ok", "url": "https://x.example/share/v1/p/a", "track_count": 3},
                      {"name": "no url"}, {"name": "bad", "url": "javascript:x"}],
        "recent_listens": listens + [{"listened_at": "yesterday", "track": track()}],
        "top_artists": [{"name": f"a{i}", "plays": i} for i in range(20)],
    })
    assert len(doc["bio"]) == 300
    assert [p["name"] for p in doc["playlists"]] == ["ok"]
    assert len(doc["recent_listens"]) == 50
    assert len(doc["top_artists"]) == 10


def test_validator_requires_a_name():
    with pytest.raises(ShareError):
        parse_document({"wayl_share": 1, "kind": "playlist", "name": "   "})


def test_subscribe_is_rate_limited_but_listing_is_not(client, make_user, auth, remote):
    bob = auth(make_user("bobby"))
    codes = [client.post("/api/subscriptions", json={"url": "https://friend.example/nope"}, headers=bob).status_code for _ in range(31)]
    assert codes[:30] == [400] * 30 and codes[30] == 429
    assert all(client.get("/api/subscriptions", headers=bob).status_code == 200 for _ in range(40))
