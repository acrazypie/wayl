import os

# Must be set before the app is imported.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-0123456789-0123456789-abcdef"
os.environ["APP_URL"] = "https://wayl.test"

import pytest
from flask import g

from app import create_app
from app.models import db
from app.models.user import UserModel
from app.services import catalog
from app.utility import create_jwt, limiter, mail


# The fixtures keep one app context open, so Flask's `g` (where Flask-Login caches the current
# user) would otherwise leak from one test request into the next. Real requests get a fresh one.
def _forget_cached_user():
    g.pop("_login_user", None)


def build_app(social=False):
    flask_app = create_app({"TESTING": True, "SOCIAL_ENABLED": social, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    flask_app.before_request(_forget_cached_user)
    return flask_app

PASSWORD = "correct horse battery"

NUDE = "11111111-1111-4111-8111-111111111111"
TEARDROP = "22222222-2222-4222-8222-222222222222"
NUDE_COVER = "33333333-3333-4333-8333-333333333333"
RADIOHEAD = "a74b1b7f-71a5-4011-9441-d0b5e4122711"
MASSIVE = "10adbe5e-a2c0-4bf3-8249-2b4cbf6e6ca8"

# Canned upstream responses, shaped like the real ListenBrainz / MusicBrainz JSON.
METADATA = {
    NUDE: {
        "artist": {"name": "Radiohead", "artists": [{
            "artist_mbid": RADIOHEAD, "name": "Radiohead", "area": "United Kingdom",
            "rels": {"youtube": "https://www.youtube.com/radiohead", "official homepage": "javascript:alert(1)"},
        }]},
        "recording": {
            "name": "Nude", "length": 255386, "first_release_date": "2007-10-10", "isrcs": ["GBSTK0700003"],
            "rels": [{"artist_mbid": "8ed2e0b3-aa4c-4e13-bec3-dc7393ed4d6b", "artist_name": "Thom Yorke",
                      "type": "performer"}],
        },
        "release": {"name": "In Rainbows", "mbid": "44444444-4444-4444-8444-444444444444", "year": 2007,
                    "caa_release_mbid": NUDE_COVER, "caa_id": 14926982777},
        "tag": {"recording": [{"tag": "alternative rock", "count": 4, "genre_mbid": "g1"},
                              {"tag": "seen live", "count": 9}]},
    },
    TEARDROP: {
        "artist": {"name": "Massive Attack", "artists": [{"artist_mbid": MASSIVE, "name": "Massive Attack"}]},
        "recording": {"name": "Teardrop", "length": 330026},
        "release": {"name": "Mezzanine", "mbid": "55555555-5555-4555-8555-555555555555", "year": 1998},
        "tag": {"artist": [{"tag": "trip hop", "count": 10, "genre_mbid": "g2"}]},
    },
}
POPULARITY = {NUDE: 2_600_000, TEARDROP: 900_000}


class FakeCatalog:
    def __init__(self):
        self.down = False
        self.calls = []

    def request(self, method, url, *, params=None, json=None, musicbrainz=False, retries=2):
        self.calls.append(url)
        if self.down:
            raise catalog.CatalogError("down")
        params = params or {}
        if url.endswith("/recording-search/json"):
            q = params["query"].lower()
            hits = []
            for mbid, meta in METADATA.items():
                words = f"{meta['recording']['name']} {meta['artist']['name']}".lower()
                if any(w in words for w in q.split()):
                    hits.append({"recording_mbid": mbid, "recording_name": meta["recording"]["name"],
                                 "artist_credit_name": meta["artist"]["name"]})
            return hits
        if "/metadata/recording/" in url:
            ids = params["recording_mbids"].split(",")
            return {m: METADATA[m] for m in ids if m in METADATA}
        if url.endswith("/popularity/recording"):
            return [{"recording_mbid": m, "total_listen_count": POPULARITY.get(m, 0)} for m in json["recording_mbids"]]
        if url.endswith("/ws/2/artist"):
            return {"artists": [{"id": RADIOHEAD, "name": "Radiohead", "score": 100, "type": "Group",
                                 "area": {"name": "United Kingdom"}}]}
        if "/top-recordings-for-artist/" in url:
            if url.endswith(RADIOHEAD):
                return [
                    {"recording_mbid": NUDE, "recording_name": "Nude", "artist_name": "Radiohead",
                     "release_name": "In Rainbows", "length": 255386, "total_listen_count": 10},
                    {"recording_mbid": "66666666-6666-4666-8666-666666666666", "recording_name": "Nude",
                     "artist_name": "Radiohead", "release_name": "Live", "total_listen_count": 1},
                ]
            return []
        if f"/ws/2/artist/{RADIOHEAD}" in url:
            return {"name": "Radiohead", "type": "Group", "area": {"name": "United Kingdom"},
                    "life-span": {"begin": "1985"}, "genres": [{"name": "art rock", "count": 30}]}
        return None


@pytest.fixture(autouse=True)
def fake_catalog(monkeypatch):
    fake = FakeCatalog()
    monkeypatch.setattr(catalog, "_request", fake.request)
    catalog.clear_caches()
    yield fake
    catalog.clear_caches()


@pytest.fixture()
def app(request):
    """A fresh app per test. Social features are off (the default) unless the test is marked
    @pytest.mark.social."""
    flask_app = build_app(social=request.node.get_closest_marker("social") is not None)
    mail.outbox.clear()
    limiter.reset()
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_user(app):
    def _make(name, password=PASSWORD):
        user = UserModel(email=f"{name}@example.com", username=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    return _make


@pytest.fixture()
def auth():
    def _auth(user):
        return {"Authorization": f"Bearer {create_jwt(user)}"}

    return _auth
