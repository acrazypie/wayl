# WAYL sharing protocol, version 1

How one WAYL instance publishes playlists and a profile, and how another instance (or any other
client) reads them. Only **metadata** crosses instances: MusicBrainz ids plus display fields.
Never audio, never anything from a media server.

## Model

- **Capability URLs.** A share is a URL with an unguessable token (`secrets.token_urlsafe(16)`,
  about 128 bits). Anyone who has the link can read it; nobody else can find it. The owner revokes
  a link by turning sharing off or resetting the token (the old URL then returns 404).
- **Read-only.** There are no accounts across instances and nothing can be written remotely.
- **Two documents:** a single `playlist`, and a `profile` (display name, the owner's shared
  playlists, and, only if the owner opted in, recent listens and top artists).

## Endpoints (on the publishing instance)

| URL | Document |
| --- | --- |
| `GET <APP_URL>/share/v1/p/<token>` | playlist |
| `GET <APP_URL>/share/v1/p/<token>?format=jspf` | the same playlist as [JSPF](https://www.xspf.org/jspf) |
| `GET <APP_URL>/share/v1/u/<token>` | profile |

Responses:

- `200` with `Content-Type: application/json`, or `404 {"error": ...}` for an unknown or revoked
  token.
- `Access-Control-Allow-Origin: *` (no cookies are read or set), `Cache-Control: public,
  max-age=300`, `X-Content-Type-Options: nosniff`.
- `ETag` (quoted SHA-256 of the body, so it changes whenever the content does) and
  `Last-Modified` (the document's `updated_at`). Send `If-None-Match` to get `304 Not Modified`.
- Rate limited (60 requests per minute per IP).

## Track object

```json
{"mbid": "<recording mbid>", "title": "…", "artist": "…", "artist_mbid": "<mbid>|null",
 "album": "…|null", "cover": "https://coverartarchive.org/…|null", "duration": 215}
```

`mbid` is a MusicBrainz **recording** id and is required: tracks without one are left out.
`duration` is in seconds, or `null`.

## Playlist document

```json
{
  "wayl_share": 1,
  "kind": "playlist",
  "id": "<share token>",
  "url": "https://music.friend.tld/share/v1/p/<token>",
  "name": "Late night",
  "owner": {"name": "eli", "profile_url": "https://music.friend.tld/share/v1/u/<token>"},
  "updated_at": "2026-11-18T17:00:00Z",
  "tracks": [ /* track objects, in playlist order, at most 500 */ ]
}
```

`owner.profile_url` is `null` unless the owner also shares their profile.

## Profile document

```json
{
  "wayl_share": 1,
  "kind": "profile",
  "id": "<token>",
  "url": "https://music.friend.tld/share/v1/u/<token>",
  "name": "eli",
  "bio": "…|null",
  "updated_at": "2026-11-18T17:00:00Z",
  "playlists": [{"name": "…", "url": "…/share/v1/p/<token>", "track_count": 20, "updated_at": "…Z"}],
  "recent_listens": [{"listened_at": "…Z", "track": { /* track object */ }}],
  "top_artists": [{"name": "…", "mbid": "…|null", "plays": 12}]
}
```

- `playlists`: only the owner's playlists that have a share link.
- `recent_listens` (at most 50, newest first) and `top_artists` (at most 10, last 30 days) appear
  **only** if the owner turned them on. Otherwise the keys are absent, not empty.

## What is never in a document

Email addresses, user ids, the owner's account details, local playlist ids, media server names or
URLs, library track ids, listen `source`, play counts other than `top_artists[].plays`, and
anything read from a media server.

## Rules for readers

Treat every document as untrusted input. WAYL's reader:

- fetches over http(s) only, with timeouts (5 s connect, 15 s read), at most 3 redirects (each hop
  re-validated), a 1 MB body limit and a JSON content type;
- honours the instance's `ALLOW_PRIVATE_SERVER_URLS`: on by default (friends on a LAN or
  Tailscale), off on public instances, where URLs resolving to private, loopback or link-local
  addresses are refused, including after a redirect;
- requires `wayl_share == 1` and a known `kind`; drops unknown fields; caps strings (titles and
  albums 300, names 60, URLs 500, bio 300); requires MBIDs to be UUIDs and cover/profile/playlist
  URLs to be http(s); drops bad tracks, listens or playlists instead of rejecting the document;
- keeps the last good copy when a refresh fails, and refreshes every `SHARE_REFRESH_HOURS` (6 by
  default) with exponential backoff after errors.

## Versioning

`wayl_share` is the format version. Additive changes (new optional keys) keep version 1; readers
ignore keys they don't know. Anything that changes or removes a key bumps it and gets new URLs
(`/share/v2/…`), and publishers keep serving `/share/v1/` for a while.
