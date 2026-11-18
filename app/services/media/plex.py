"""Plex Media Server client, plus the plex.tv PIN sign-in flow.

Sign-in: create a PIN on plex.tv, send the user to app.plex.tv/auth to approve it, poll the
PIN until it carries a user token, then list the user's servers (each has its own access token).
"""
import hashlib
from urllib.parse import quote, urlencode

from app.services.catalog import is_mbid
from app.services.media import base
from app.services.media.base import MediaServerError, RemoteTrack, int_or_none, normalize_url
from app.utility import config

PRODUCT = "WAYL"
PLEX_TV = "https://plex.tv"
PLEX_CLIENTS = "https://clients.plex.tv"
PAGE = 200


def client_identifier():
    """Stable per WAYL install (derived from SECRET_KEY, which it doesn't reveal)."""
    return hashlib.sha256(("wayl-plex-client:" + config.SECRET_KEY).encode()).hexdigest()[:32]


def _plex_headers(token=None):
    headers = {
        "Accept": "application/json",
        "X-Plex-Product": PRODUCT,
        "X-Plex-Client-Identifier": client_identifier(),
    }
    if token:
        headers["X-Plex-Token"] = token
    return headers


def _json(res, what):
    if res.status_code == 401:
        raise MediaServerError("Plex refused the token. Sign in again.")
    if not res.ok:
        raise MediaServerError(f"{what} failed (HTTP {res.status_code})")
    try:
        return res.json()
    except ValueError as exc:
        raise MediaServerError(f"{what} returned something that isn't JSON") from exc


# --- plex.tv sign-in ------------------------------------------------------------------


def create_pin(forward_url=None):
    data = _json(base.http("POST", f"{PLEX_TV}/api/v2/pins", params={"strong": "true"}, headers=_plex_headers()), "Creating a Plex PIN")
    params = {"clientID": client_identifier(), "code": data["code"], "context[device][product]": PRODUCT}
    if forward_url:
        params["forwardUrl"] = forward_url
    return {"id": data["id"], "auth_url": "https://app.plex.tv/auth#?" + urlencode(params, quote_via=quote)}


def check_pin(pin_id):
    """The user's plex.tv token once they approved the PIN, else None."""
    data = _json(base.http("GET", f"{PLEX_TV}/api/v2/pins/{int(pin_id)}", headers=_plex_headers()), "Checking the Plex PIN")
    return data.get("authToken") or None


def list_servers(user_token):
    """Servers this plex.tv account can use: [{id, name, owned, token, connections}]."""
    data = _json(
        base.http(
            "GET",
            f"{PLEX_CLIENTS}/api/v2/resources",
            params={"includeHttps": 1, "includeRelay": 1, "includeIPv6": 1},
            headers=_plex_headers(user_token),
        ),
        "Listing your Plex servers",
    )
    servers = []
    for dev in data if isinstance(data, list) else []:
        if "server" not in str(dev.get("provides", "")).split(",") or not dev.get("accessToken"):
            continue
        conns = [c for c in dev.get("connections") or [] if isinstance(c, dict) and c.get("uri")]
        # local first, relay last
        conns.sort(key=lambda c: (bool(c.get("relay")), not c.get("local")))
        servers.append({
            "id": dev.get("clientIdentifier"),
            "name": dev.get("name") or "Plex server",
            "owned": bool(dev.get("owned")),
            "token": dev["accessToken"],
            "connections": [c["uri"] for c in conns],
        })
    return servers


def pick_connection(server):
    """The first connection URI that answers from where WAYL runs."""
    errors = []
    for uri in server["connections"]:
        try:
            url = normalize_url(uri)
            PlexClient(url, server["token"], timeout=4).ping()
            return url
        except MediaServerError as exc:
            errors.append(str(exc))
    raise MediaServerError(
        "WAYL can't reach this Plex server from where it runs. "
        "Connect it manually with an address WAYL can reach (e.g. http://plex:32400)."
        + (f" ({errors[0]})" if errors else "")
    )


# --- server API ------------------------------------------------------------------------


class PlexClient:
    kind = "plex"

    def __init__(self, base_url, token, timeout=10):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def get(self, path, **params):
        res = base.http("GET", self.base_url + path, params=params, headers=_plex_headers(self.token), timeout=self.timeout)
        return _json(res, "Plex request").get("MediaContainer") or {}

    @staticmethod
    def to_track(md):
        mbid = None
        for guid in md.get("Guid") or []:
            gid = str((guid or {}).get("id") or "")
            if gid.startswith("mbid://") and is_mbid(gid[7:].lower()):
                mbid = gid[7:].lower()
        part_key = None
        for media in md.get("Media") or []:
            for part in media.get("Part") or []:
                if part.get("key"):
                    part_key = part["key"]
                    break
            if part_key:
                break
        duration = int_or_none(md.get("duration"))
        return RemoteTrack(
            remote_id=str(md["ratingKey"]),
            title=md.get("title") or "Unknown title",
            # originalTitle is the track artist when it differs from the album artist
            artist=md.get("originalTitle") or md.get("grandparentTitle") or "Unknown artist",
            album=md.get("parentTitle"),
            duration=round(duration / 1000) if duration else None,
            mbid=mbid,
            stream_key=part_key,
        )

    def ping(self):
        info = self.get("/identity")
        if not info.get("machineIdentifier"):
            raise MediaServerError("That doesn't look like a Plex server")
        return {"name": "Plex", "machine_id": info["machineIdentifier"]}

    def music_sections(self):
        sections = self.get("/library/sections/all").get("Directory") or []
        return [str(s["key"]) for s in sections if s.get("type") == "artist" and s.get("key")]

    def all_tracks(self):
        """Every track in every music library, page by page."""
        for section in self.music_sections():
            start = 0
            while True:
                res = base.http(
                    "GET",
                    f"{self.base_url}/library/sections/{section}/all",
                    params={"type": 10, "includeGuids": 1},
                    headers={**_plex_headers(self.token), "X-Plex-Container-Start": str(start), "X-Plex-Container-Size": str(PAGE)},
                    timeout=30,
                )
                items = (_json(res, "Listing Plex tracks").get("MediaContainer") or {}).get("Metadata") or []
                for md in items:
                    if md.get("ratingKey"):
                        yield self.to_track(md)
                if len(items) < PAGE:
                    break
                start += PAGE

    def search_tracks(self, query, limit=20):
        hubs = self.get("/hubs/search", query=query, limit=limit).get("Hub") or []
        tracks = []
        for hub in hubs:
            if hub.get("type") == "track":
                tracks += [self.to_track(m) for m in hub.get("Metadata") or [] if m.get("ratingKey")]
        return tracks

    def track(self, remote_id):
        items = self.get(f"/library/metadata/{int(remote_id)}", includeGuids=1).get("Metadata") or []
        return self.to_track(items[0]) if items and items[0].get("type") == "track" else None

    def history(self, since, account_id=None, max_items=5000):
        """Track plays newer than `since` (unix seconds), newest first: [(rating_key, viewed_at)]."""
        out, start = [], 0
        while len(out) < max_items:
            params = {"sort": "viewedAt:desc"}
            if account_id is not None:
                params["accountID"] = account_id
            res = base.http(
                "GET",
                f"{self.base_url}/status/sessions/history/all",
                params=params,
                headers={**_plex_headers(self.token), "X-Plex-Container-Start": str(start), "X-Plex-Container-Size": str(PAGE)},
            )
            items = (_json(res, "Reading Plex history").get("MediaContainer") or {}).get("Metadata") or []
            for item in items:
                viewed = int_or_none(item.get("viewedAt"))
                if viewed is None:
                    continue
                if viewed <= since:
                    return out
                if item.get("type") == "track" and item.get("ratingKey"):
                    out.append((str(item["ratingKey"]), viewed))
            if len(items) < PAGE:
                break
            start += PAGE
        return out

    def playlists(self):
        items = self.get("/playlists", playlistType="audio").get("Metadata") or []
        return [
            {"id": str(p["ratingKey"]), "name": p.get("title") or "Playlist", "count": p.get("leafCount")}
            for p in items
            if p.get("ratingKey") and not p.get("smart")
        ]

    def playlist_tracks(self, remote_id):
        items = self.get(f"/playlists/{int(remote_id)}/items").get("Metadata") or []
        return [self.to_track(m) for m in items if m.get("ratingKey") and m.get("type") == "track"]

    def now_playing(self):
        return []  # Plex listens come from the play history instead

    def stream_request(self, track):
        if not track.stream_key or not track.stream_key.startswith("/library/parts/"):
            raise MediaServerError("This track has no playable file")
        return self.base_url + track.stream_key, {}, {"X-Plex-Token": self.token, "X-Plex-Client-Identifier": client_identifier()}
