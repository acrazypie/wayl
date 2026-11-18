from app.services import catalog
from tests.conftest import MASSIVE, NUDE, NUDE_COVER, PASSWORD, RADIOHEAD, TEARDROP

UNKNOWN = "99999999-9999-4999-8999-999999999999"


# --- catalog: search & details ---------------------------------------------------


def test_search_returns_catalog_tracks(client):
    res = client.get("/api/songs?q=nude radiohead")
    assert res.status_code == 200
    items = res.get_json()["items"]
    assert items[0]["id"] == NUDE
    assert items[0]["title"] == "Nude"
    assert items[0]["artist"] == "Radiohead"
    assert items[0]["album"] == "In Rainbows"
    assert items[0]["duration"] == 255
    assert items[0]["genre"] == "alternative rock"  # genre tags only, not "seen live"
    assert items[0]["cover"] == f"https://coverartarchive.org/release/{NUDE_COVER}/14926982777-250.jpg"
    assert items[0]["saved"] is False


def test_search_short_query_skips_catalog(client, fake_catalog):
    assert client.get("/api/songs?q=a").get_json() == {"total": 0, "items": []}
    assert fake_catalog.calls == []


def test_search_is_cached(client, fake_catalog):
    client.get("/api/songs?q=teardrop")
    n = len(fake_catalog.calls)
    client.get("/api/songs?q=Teardrop")
    assert len(fake_catalog.calls) == n


def test_catalog_down_returns_502(client, fake_catalog):
    fake_catalog.down = True
    assert client.get("/api/songs?q=nude").status_code == 502
    assert client.get(f"/api/songs/{NUDE}").status_code == 502


def test_song_detail(client, make_user, auth):
    headers = auth(make_user("alice"))
    client.post("/api/history", json={"song_id": NUDE}, headers=headers)

    data = client.get(f"/api/songs/{NUDE}", headers=headers).get_json()
    assert data["release_date"] == "2007-10-10"
    assert data["credits"][0]["name"] == "Thom Yorke"
    assert data["listenbrainz_listens"] == 2_600_000
    assert data["my_plays"] == 1 and data["wayl_plays"] == 1
    assert data["cover_large"].endswith("-500.jpg")
    # only http(s) artist links make it through
    assert [l["label"] for l in data["artist_links"]] == ["YouTube"]


def test_song_detail_unknown_or_invalid(client):
    assert client.get(f"/api/songs/{UNKNOWN}").status_code == 404
    assert client.get("/api/songs/not-an-id").status_code == 404


def test_artists(client):
    found = client.get("/api/artists?q=radiohead").get_json()["items"]
    assert found[0]["id"] == RADIOHEAD
    artist = client.get(f"/api/artists/{RADIOHEAD}").get_json()
    assert artist["name"] == "Radiohead"
    assert artist["genres"] == ["art rock"]
    assert [t["id"] for t in artist["top_tracks"]] == [NUDE]  # duplicate titles collapsed
    assert client.get(f"/api/artists/{UNKNOWN}").status_code == 404


def test_rank_tracks_prefers_exact_and_popular():
    a = {"id": "a", "title": "Get Lucky", "artist": "Somebody"}
    b = {"id": "b", "title": "Get Lucky", "artist": "Daft Punk"}
    c = {"id": "c", "title": "Get Lucky Tonight", "artist": "X"}
    ranked = catalog.rank_tracks("get lucky", [c, a, b], {"b": 5_000_000, "a": 10})
    assert [t["id"] for t in ranked] == ["b", "a", "c"]

    # "title artist" also matches when the credit is longer ("Daft Punk feat. ...")
    cover = {"id": "x", "title": "Get Lucky", "artist": "Daft Punk"}
    original = {"id": "y", "title": "Get Lucky", "artist": "Daft Punk feat. Pharrell Williams"}
    ranked = catalog.rank_tracks("get lucky daft punk", [cover, original], {"x": 200, "y": 900_000})
    assert [t["id"] for t in ranked] == ["y", "x"]


def test_cover_url_rejects_bad_ids():
    assert catalog.cover_url("../../etc") is None
    assert catalog.cover_url(NUDE_COVER) == f"https://coverartarchive.org/release/{NUDE_COVER}/front-250"


# --- my songs (library) ----------------------------------------------------------


def test_save_and_unsave_songs(client, make_user, auth):
    headers = auth(make_user("alice"))
    assert client.put(f"/api/me/songs/{NUDE}").status_code == 401
    assert client.put(f"/api/me/songs/{NUDE}", headers=headers).get_json() == {"saved": True}
    assert client.put(f"/api/me/songs/{NUDE}", headers=headers).status_code == 200  # idempotent
    assert client.put(f"/api/me/songs/{UNKNOWN}", headers=headers).status_code == 404

    mine = client.get("/api/me/songs", headers=headers).get_json()
    assert mine["total"] == 1
    assert mine["items"][0]["title"] == "Nude"
    assert mine["items"][0]["cover"].endswith("-250.jpg")

    search = client.get("/api/songs?q=nude", headers=headers).get_json()["items"]
    assert next(t for t in search if t["id"] == NUDE)["saved"] is True
    client.post("/api/history", json={"song_id": NUDE}, headers=headers)
    assert client.get("/api/history", headers=headers).get_json()["items"][0]["song"]["saved"] is True

    client.delete(f"/api/me/songs/{NUDE}", headers=headers)
    assert client.get("/api/me/songs", headers=headers).get_json()["total"] == 0


def test_songs_are_imported_once(client, make_user, auth):
    from app.models.music import Artist, Song

    headers = auth(make_user("alice"))
    client.put(f"/api/me/songs/{NUDE}", headers=headers)
    client.post("/api/history", json={"song_id": NUDE}, headers=headers)
    assert Song.query.count() == 1
    assert Artist.query.one().mbid == RADIOHEAD


# --- users ---------------------------------------------------------------


def test_users_endpoints_never_leak_email(client, make_user, auth):
    alice, bob = make_user("alice"), make_user("bobby")

    assert client.get("/api/users?q=bo").status_code == 401  # anonymous

    found = client.get("/api/users?q=bo", headers=auth(alice)).get_json()["items"]
    assert [u["username"] for u in found] == ["bobby"]
    assert "email" not in found[0]
    assert "email" not in client.get(f"/api/users/{bob.id}").get_json()

    assert client.patch(f"/api/users/{bob.id}", json={"username": "x"}).status_code == 405
    assert client.get("/api/me", headers=auth(alice)).get_json()["email"] == "alice@example.com"


def test_edit_profile_and_delete_account(client, make_user, auth):
    alice = make_user("alice")
    make_user("taken")
    headers = auth(alice)

    assert client.patch("/api/me", json={"username": "taken"}, headers=headers).status_code == 409
    assert client.patch("/api/me", json={"username": "bad name"}, headers=headers).status_code == 400
    res = client.patch("/api/me", json={"username": "alicia", "bio": "trip-hop forever"}, headers=headers)
    assert res.get_json()["bio"] == "trip-hop forever"

    client.post("/api/playlists", json={"name": "Mix"}, headers=headers)
    client.post("/api/history", json={"song_id": NUDE}, headers=headers)
    client.put(f"/api/me/songs/{NUDE}", headers=headers)

    assert client.delete("/api/me", json={"password": "wrong"}, headers=headers).status_code == 403
    assert client.delete("/api/me", json={"password": PASSWORD}, headers=headers).status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 401


# --- history & stats -----------------------------------------------------


def test_listening_history_and_stats(client, make_user, auth):
    headers = auth(make_user("alice"))

    first = client.post("/api/history", json={"song_id": NUDE}, headers=headers)
    assert first.status_code == 201 and first.get_json()["created"] is True
    dup = client.post("/api/history", json={"song_id": NUDE}, headers=headers)
    assert dup.status_code == 200  # double-click inside 30s is ignored
    assert dup.get_json()["created"] is False
    client.post("/api/history", json={"song_id": TEARDROP}, headers=headers)

    items = client.get("/api/history", headers=headers).get_json()["items"]
    assert len(items) == 2
    assert items[0]["listened_at"].endswith("Z")

    stats = client.get("/api/stats?days=7", headers=headers).get_json()
    assert stats["total_listens"] == 2
    assert stats["total_minutes"] == round((255 + 330) / 60)
    assert {s["id"] for s in stats["top_songs"]} == {NUDE, TEARDROP}
    assert {a["id"] for a in stats["top_artists"]} == {RADIOHEAD, MASSIVE}


def test_history_bad_song_ids(client, make_user, auth):
    headers = auth(make_user("alice"))
    assert client.post("/api/history", json={"song_id": UNKNOWN}, headers=headers).status_code == 404
    assert client.post("/api/history", json={"song_id": 5}, headers=headers).status_code == 400


# --- playlists -----------------------------------------------------------


def test_playlist_privacy_and_ownership(client, make_user, auth):
    alice, bob = make_user("alice"), make_user("bobby")
    a, b = auth(alice), auth(bob)

    pid = client.post("/api/playlists", json={"name": "Mine"}, headers=a).get_json()["id"]
    assert client.post(f"/api/playlists/{pid}", json={"song_id": NUDE}, headers=a).status_code == 201
    assert client.post(f"/api/playlists/{pid}", json={"song_id": NUDE}, headers=a).status_code == 200

    # private: invisible and untouchable for others
    assert client.get(f"/api/playlists/{pid}").status_code == 404
    assert client.get(f"/api/playlists/{pid}", headers=b).status_code == 404
    assert client.delete(f"/api/playlists/{pid}", headers=b).status_code == 404
    assert client.post(f"/api/playlists/{pid}", json={"song_id": NUDE}, headers=b).status_code == 404
    assert client.get(f"/api/users/{alice.id}/playlists", headers=b).get_json()["items"] == []

    # public: anyone can read, still only the owner can write
    client.patch(f"/api/playlists/{pid}", json={"is_public": True}, headers=a)
    shared = client.get(f"/api/playlists/{pid}").get_json()
    assert shared["songs"][0]["title"] == "Nude"
    assert shared["covers"] == [shared["songs"][0]["cover"]]
    assert shared["is_owner"] is False
    assert "email" not in shared["owner"]
    assert len(client.get(f"/api/users/{alice.id}/playlists", headers=b).get_json()["items"]) == 1
    assert client.delete(f"/api/playlists/{pid}", headers=b).status_code == 404

    assert client.delete(f"/api/playlists/{pid}/songs/{NUDE}", headers=a).status_code == 200
    assert client.get(f"/api/playlists/{pid}").get_json()["song_count"] == 0
    assert client.delete(f"/api/playlists/{pid}", headers=a).status_code == 200


def test_my_playlists_only_lists_mine(client, make_user, auth):
    alice, bob = make_user("alice"), make_user("bobby")
    client.post("/api/playlists", json={"name": "A"}, headers=auth(alice))
    client.post("/api/playlists", json={"name": "B"}, headers=auth(bob))
    names = [p["name"] for p in client.get("/api/playlists", headers=auth(alice)).get_json()["items"]]
    assert names == ["A"]


# --- social --------------------------------------------------------------


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


# --- pages ---------------------------------------------------------------


def test_pages_render(client):
    for path in ["/", "/search", "/following", "/playlists", "/playlists/3", "/songs", "/profile",
                 f"/song/{NUDE}", f"/artist/{RADIOHEAD}", "/user/1", "/login", "/register", "/forgot",
                 "/reset?token=x"]:
        res = client.get(path)
        assert res.status_code == 200, path
        assert b"WAYL" in res.data
    assert client.get("/nope").status_code == 404
