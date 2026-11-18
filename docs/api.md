# WAYL HTTP API

JSON in, JSON out. Errors look like `{"error": "message"}` with a 4xx/5xx status.

**Base paths.** Every endpoint below is served at its plain path (what the web app uses) **and**
under `/api/v1` (what other clients should use): `/api/songs` → `/api/v1/songs`,
`/auth/login` → `/api/v1/auth/login`, `/api/stream/<id>` → `/api/v1/stream/<id>`. Breaking changes
to `/api/v1` bump `api_version` in `/api/instance`.

**Auth.** Browsers use the session cookie set by `/auth/login`. Other clients send
`Authorization: Bearer <access_token>`; get tokens with `POST /auth/login {"email", "password",
"tokens": true}` and renew the 1-hour access token with `POST /auth/refresh {"refresh_token"}` (30
days). Cookie-authenticated writes must send `Content-Type: application/json` (CSRF guard); bearer
requests don't need to. Changing or resetting the password revokes all tokens and sessions.

**Ids.** Songs and artists are MusicBrainz ids (UUID strings). Users, playlists, servers and
library tracks are integers. Timestamps are UTC ISO 8601 with a `Z`.

**Privacy.** Anything you don't own looks missing (404). `email` only ever appears in your own
account (`/api/me`, `/auth/session`, login/register responses).

Auth column: `–` public, `✔` signed in, `owner` signed in and it's yours (else 404).

## Instance

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/instance` | – | `{name, version, api_version, features: {social, sharing, streaming}}`. Check `features` before showing optional UI. |
| GET | `/healthz` | – | `{"status": "ok"}` (not versioned) |

## Core

### Account

| Method | Path | Auth | Request → response |
| --- | --- | --- | --- |
| POST | `/auth/register` | – | `{email, username, password}` → 201 `{user}`, signs in |
| POST | `/auth/login` | – | `{email, password, remember?, tokens?}` → `{user, access_token?, refresh_token?}` |
| POST | `/auth/refresh` | – | `{refresh_token}` → `{access_token}` |
| POST | `/auth/logout` | – | ends the cookie session |
| GET | `/auth/session` | – | `{user}` or `{user: null}`; never 401 |
| POST | `/auth/forgot` | – | `{email}` → same answer whether or not the account exists |
| POST | `/auth/reset` | – | `{token, password}` → `{user}`, signs in |
| GET | `/api/me` | ✔ | your account: `id, username, bio, joined_at, email, has_servers, servers[], saved_songs, listens, playlists` (+ `followers, following` with social on) |
| PATCH | `/api/me` | ✔ | `{username?, bio?}` |
| DELETE | `/api/me` | ✔ | `{password}`: deletes everything you own |
| POST | `/api/me/password` | ✔ | `{current_password, new_password}` |

`user` objects are `{id, username, bio, joined_at, email, has_servers, servers: [{id, kind, name}]}`.

### Songs, artists, library

Song objects: `{id (mbid), title, artist, artist_id, album, year, cover, genre, duration (s),
saved, owned?}`. `owned` is present only when you have a media server connected.

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/songs?q=` | – | catalog search (title, artist or both) → `{total, items[]}` |
| GET | `/api/songs/<mbid>` | – | details + `release_date, credits[], artist_links[], listenbrainz_listens, my_plays, wayl_plays` |
| GET | `/api/songs/<mbid>/sources` | ✔ | where you can play it: `[{track_id, server, server_name, stream_url, duration}]` |
| GET | `/api/artists?q=`, `/api/artists/<mbid>` | – | artist search / artist with `top_tracks[]` |
| GET | `/api/me/songs` | ✔ | saved songs, `?limit=&offset=` → `{total, items[]}` |
| PUT / DELETE | `/api/me/songs/<mbid>` | ✔ | save / unsave |
| GET / POST | `/api/history` | ✔ | your listens (`?limit=&offset=`) / log one: `{song_id}` or `{track_id}` (a library track), optional `source: "player"`. → `{created, item}`; repeats within 30 s aren't counted |
| GET | `/api/stats?days=30` | ✔ | `{total_listens, total_minutes, top_songs[], top_artists[]}` |

### Playlists

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET / POST | `/api/playlists` | ✔ | yours / create `{name, is_public?}` |
| GET | `/api/playlists/<id>` | owner, or anyone if `is_public` | `{id, name, is_public, owner, song_count, covers, synced_from, is_owner, songs[]}` |
| POST | `/api/playlists/<id>` | owner | add `{song_id}` |
| PATCH / DELETE | `/api/playlists/<id>` | owner | `{name?, is_public?}` / delete |
| DELETE | `/api/playlists/<id>/songs/<mbid>` | owner | remove a song |
| GET | `/api/users/<id>` | – | public profile `{id, username, bio, joined_at, is_me}` (+ social fields with social on) |
| GET | `/api/users/<id>/playlists` | – | their `is_public` playlists (all of them if it's you) |

`is_public` means visible to signed-in users *of this instance*. Sharing with other instances is
separate (see Sharing).

### Media servers and streaming

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET / POST | `/api/servers` | ✔ | list / connect: `{kind: "navidrome", url, username, password}`, `{kind: "plex", url, token, owned?}`, or `{kind: "plex", server}` after the PIN flow. Optional `sync_listens, sync_playlists`. Logins are never returned |
| POST | `/api/servers/plex/pin` | ✔ | → `{pin_id, auth_url}` (open `auth_url` for the user) |
| GET | `/api/servers/plex/pin/<pin_id>` | ✔ | `{status: "waiting"}` or `{status: "ready", servers: [{id, name, owned}]}` |
| PATCH / DELETE | `/api/servers/<id>` | owner | `{sync_listens?, sync_playlists?, url?}` / disconnect |
| POST | `/api/servers/<id>/sync` | owner | `{jobs?: ["library", "listens", "playlists"]}` → 202 |
| GET | `/api/library?q=&limit=&offset=` | ✔ | tracks on your servers → `{total, items[]}`; items have `track_id`, and `library_only: true` + `id: null` when not matched to MusicBrainz |
| POST | `/api/library/tracks/<track_id>/match` | owner | match a library-only track → song object, or 404 |
| GET | `/api/stream/<track_id>` | owner | the audio, proxied from your server; supports `Range`. Works with a bearer token |
| GET / POST / DELETE | `/api/me/listen-token` | ✔ | scrobble token: `{exists, created_at, last_used_at, api_url}` / create (returns `token` once) / revoke |
| GET / POST / DELETE | `/api/me/unmatched` | ✔ | listens not matched yet `{unmatched, pending, items[]}` / retry / dismiss |

### Scrobbling (ListenBrainz-compatible)

Authenticated with `Authorization: Token <listen token>` (not the bearer token). Not versioned:
players are configured with the base URL `<APP_URL>/listenbrainz/1/`.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/listenbrainz/1/validate-token` | `{code: 200, valid, user_name?}` |
| POST | `/listenbrainz/1/submit-listens` | ListenBrainz payload; `single` and `import` are stored, `playing_now` is accepted and ignored → `{status: "ok"}` |

## Sharing between instances

Read-only share links any WAYL (or other client) can read. Formats and rules:
[`sharing-protocol.md`](sharing-protocol.md). Only MusicBrainz metadata is shared, never audio.

### Publishing

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/share/v1/p/<token>` | – (the token) | playlist document; `?format=jspf` for JSPF. CORS `*`, `ETag`/`If-None-Match` → 304 |
| GET | `/share/v1/u/<token>` | – (the token) | profile document |
| GET / PUT / DELETE | `/api/playlists/<id>/share` | owner | `{shared, url, warning?}` / create the link (keeps an existing one) / remove it |
| POST | `/api/playlists/<id>/share/reset` | owner | new link; the old one 404s |
| GET / PATCH | `/api/me/sharing` | ✔ | `{enabled, url, share_listens, share_top_artists, display_name, warning?}`; PATCH any of `enabled, share_listens, share_top_artists, display_name` |
| POST | `/api/me/sharing/reset` | ✔ | new profile link |

`warning` appears when `APP_URL` is a localhost address friends can't open. The owner's
`GET /api/playlists/<id>` includes `share: {shared, url}`; `GET /api/playlists` items include
`shared`.

## Social (only when `features.social` is true)

Off by default (`WAYL_SOCIAL=0`); then these paths return 404.

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/feed` | ✔ | recent listens of people you follow, with `user: {id, username}` |
| GET | `/api/users?q=` | ✔ | people search → `[{id, username, bio, joined_at, is_following}]` |
| GET | `/api/users/<id>/listens` | ✔ them or a follower | their recent listens (404 otherwise) |
| POST / DELETE | `/api/users/<id>/follow` | ✔ | follow / unfollow → `{is_following}` |
| GET | `/api/me/following`, `/api/me/followers` | ✔ | user lists with `is_following` |

With social on, `/api/users/<id>` adds `followers, following, is_following, listens_visible` and
`/api/me` adds `followers, following`.
