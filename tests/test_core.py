"""The personal-log core without social features (the default), the instance info endpoint, the
/api/v1 aliases and bearer-token access for other clients."""
import pytest

from app.models import db
from app.models.social import Follow
from app.services.media import base as media_base
from app.version import API_VERSION, APP_VERSION
from tests.conftest import NUDE, PASSWORD
from tests.test_servers import ND, ND_PASSWORD, FakeResponse, FakeServers

SOCIAL_PATHS = [
    ("GET", "/api/feed"),
    ("GET", "/api/users?q=al"),
    ("GET", "/api/users/1/listens"),
    ("POST", "/api/users/2/follow"),
    ("DELETE", "/api/users/2/follow"),
    ("GET", "/api/me/following"),
    ("GET", "/api/me/followers"),
]


def test_social_routes_are_missing_by_default(client, make_user, auth):
    headers = auth(make_user("alice"))
    make_user("bobby")
    for method, path in SOCIAL_PATHS:
        for p in (path, path.replace("/api/", "/api/v1/", 1)):
            res = client.open(p, method=method, headers=headers, json={} if method != "GET" else None)
            assert res.status_code == 404, (method, p, res.status_code)


def test_instance_info_without_social(client):
    for path in ("/api/instance", "/api/v1/instance"):
        info = client.get(path).get_json()
        assert info == {
            "name": "WAYL",
            "version": APP_VERSION,
            "api_version": API_VERSION,
            "features": {"social": False, "sharing": True, "streaming": True},
        }


@pytest.mark.social
def test_instance_info_with_social(client):
    assert client.get("/api/instance").get_json()["features"]["social"] is True


def test_profiles_leave_out_social_fields(client, make_user, auth):
    alice, bob = make_user("alice"), make_user("bobby")
    profile = client.get(f"/api/users/{bob.id}", headers=auth(alice)).get_json()
    assert profile["username"] == "bobby" and profile["is_me"] is False
    for key in ("followers", "following", "is_following", "listens_visible", "email"):
        assert key not in profile
    me = client.get("/api/me", headers=auth(alice)).get_json()
    assert "followers" not in me and "following" not in me


@pytest.mark.social
def test_profiles_include_social_fields_when_on(client, make_user, auth):
    alice, bob = make_user("alice"), make_user("bobby")
    profile = client.get(f"/api/users/{bob.id}", headers=auth(alice)).get_json()
    assert profile["followers"] == 0 and profile["is_following"] is False
    assert "followers" in client.get("/api/me", headers=auth(alice)).get_json()


def test_account_deletion_removes_follows_even_with_social_off(client, make_user, auth):
    alice, bob = make_user("alice"), make_user("bobby")
    db.session.add_all([Follow(follower_id=alice.id, followed_id=bob.id), Follow(follower_id=bob.id, followed_id=alice.id)])
    db.session.commit()
    assert client.delete("/api/me", json={"password": PASSWORD}, headers=auth(alice)).status_code == 200
    assert Follow.query.count() == 0


def test_core_flow_works_without_social(client, make_user, auth):
    headers = auth(make_user("alice"))
    assert client.get("/api/songs?q=nude").status_code == 200
    assert client.post("/api/history", json={"song_id": NUDE}, headers=headers).status_code == 201
    pid = client.post("/api/playlists", json={"name": "Mine"}, headers=headers).get_json()["id"]
    assert client.post(f"/api/playlists/{pid}", json={"song_id": NUDE}, headers=headers).status_code == 201
    assert client.get("/api/stats", headers=headers).get_json()["total_listens"] == 1
    assert client.get("/api/servers", headers=headers).get_json() == {"items": []}


def test_v1_aliases_cover_core_and_auth(client, make_user):
    make_user("alice")
    login = client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD, "tokens": True})
    assert login.status_code == 200
    bearer = {"Authorization": "Bearer " + login.get_json()["access_token"]}
    other = client.application.test_client()  # no session cookie: bearer only
    for path in ["/api/v1/me", "/api/v1/me/songs", "/api/v1/history", "/api/v1/stats", "/api/v1/playlists",
                 "/api/v1/servers", "/api/v1/library", "/api/v1/me/listen-token", "/api/v1/me/unmatched",
                 "/api/v1/songs?q=nude", f"/api/v1/songs/{NUDE}"]:
        assert other.get(path, headers=bearer).status_code == 200, path
    assert other.get("/api/v1/auth/session", headers=bearer).get_json()["user"]["username"] == "alice"
    # writes with a bearer token don't need the cookie-CSRF JSON rule, but JSON works too
    assert other.post("/api/v1/history", json={"song_id": NUDE}, headers=bearer).status_code == 201
    assert other.get("/api/v1/me").status_code == 401


def test_login_bearer_stream(client, make_user, monkeypatch):
    """What a mobile client does: password login for tokens, then everything with the bearer,
    including the audio stream (media HTTP faked)."""
    import app.routes.stream as stream_mod

    monkeypatch.setattr(media_base, "http", FakeServers())
    make_user("alice")
    api = client.application.test_client()
    tokens = api.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD, "tokens": True}).get_json()
    bearer = {"Authorization": "Bearer " + tokens["access_token"]}

    res = api.post("/api/v1/servers", json={"kind": "navidrome", "url": ND, "username": "alice", "password": ND_PASSWORD}, headers=bearer)
    assert res.status_code == 201
    track = api.get("/api/v1/library?q=nude", headers=bearer).get_json()["items"][0]

    monkeypatch.setattr(stream_mod.requests, "get", lambda *a, **k: FakeResponse(200, headers={"Content-Type": "audio/mpeg"}, content=b"ID3x"))
    for path in (f"/api/v1/stream/{track['track_id']}", f"/api/stream/{track['track_id']}"):
        audio = api.get(path, headers=bearer)
        assert audio.status_code == 200 and audio.data == b"ID3x", path
    stranger = client.application.test_client()  # no token, no cookie
    assert stranger.get(f"/api/v1/stream/{track['track_id']}").status_code == 404

    refreshed = api.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).get_json()
    assert api.get("/api/v1/me", headers={"Authorization": "Bearer " + refreshed["access_token"]}).status_code == 200
