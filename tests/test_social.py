"""Social features (WAYL_SOCIAL=1): follows, feed, people search, followers' view of listens.
These are the original social tests, unchanged; the marker turns the feature on."""
import pytest

from tests.conftest import NUDE

pytestmark = pytest.mark.social


def test_users_endpoints_never_leak_email(client, make_user, auth):
    alice, bob = make_user("alice"), make_user("bobby")

    assert client.get("/api/users?q=bo").status_code == 401  # anonymous

    found = client.get("/api/users?q=bo", headers=auth(alice)).get_json()["items"]
    assert [u["username"] for u in found] == ["bobby"]
    assert "email" not in found[0]
    assert "email" not in client.get(f"/api/users/{bob.id}").get_json()

    assert client.patch(f"/api/users/{bob.id}", json={"username": "x"}).status_code == 405
    assert client.get("/api/me", headers=auth(alice)).get_json()["email"] == "alice@example.com"


def test_follow_feed_and_listen_privacy(client, make_user, auth):
    alice, bob = make_user("alice"), make_user("bobby")
    a, b = auth(alice), auth(bob)

    client.post("/api/history", json={"song_id": NUDE}, headers=b)
    assert client.get("/api/feed", headers=a).get_json()["items"] == []
    assert client.get(f"/api/users/{bob.id}/listens", headers=a).status_code == 404  # not following
    assert client.get(f"/api/users/{bob.id}/listens").status_code == 404

    assert client.post(f"/api/users/{alice.id}/follow", headers=a).status_code == 400  # self
    assert client.post("/api/users/9999/follow", headers=a).status_code == 404
    assert client.post(f"/api/users/{bob.id}/follow", headers=a).get_json()["is_following"] is True
    assert client.post(f"/api/users/{bob.id}/follow", headers=a).status_code == 200  # idempotent

    feed = client.get("/api/feed", headers=a).get_json()["items"]
    assert len(feed) == 1
    assert feed[0]["user"] == {"id": bob.id, "username": "bobby"}
    assert client.get(f"/api/users/{bob.id}/listens", headers=a).status_code == 200

    profile = client.get(f"/api/users/{bob.id}", headers=a).get_json()
    assert profile["is_following"] is True and profile["followers"] == 1

    following = client.get("/api/me/following", headers=a).get_json()["items"]
    assert [u["username"] for u in following] == ["bobby"]
    followers = client.get("/api/me/followers", headers=b).get_json()["items"]
    assert followers[0]["username"] == "alice" and followers[0]["is_following"] is False
    assert all("email" not in u for u in following + followers)

    client.delete(f"/api/users/{bob.id}/follow", headers=a)
    assert client.get("/api/feed", headers=a).get_json()["items"] == []
