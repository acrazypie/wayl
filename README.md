# WAYL: What Are You Listening?

![WAYL logo](app/static/logo-wordmark.svg)

A small social music log. Search any song, log what you're playing, save songs, build playlists,
follow friends and see what they're listening to, and check your top songs and artists.

A **self-hosted personal music log**: search any song, log what you listen to, save songs, build
playlists and see your stats. Connect your own **Plex** or **Navidrome** server and WAYL logs what
you play there, imports your playlists, marks the songs you own, and streams your own music in the
browser. Share playlists with friends who run their own WAYL. (Follows and a feed between users of
one instance are optional: `WAYL_SOCIAL=1`.)

Flask + SQLite, email/password accounts, vanilla JS frontend (no build step). Song data comes from
the free, open [MusicBrainz](https://musicbrainz.org) and [ListenBrainz](https://listenbrainz.org)
databases, so there's no song library to maintain and no API key to get.

## Self-hosting with Docker

```bash
git clone <this repo> wayl && cd wayl
APP_URL=http://192.168.1.20:8000 docker compose up -d    # the address you'll open WAYL at
```

That starts two containers from the same image:

- **wayl**: the web app on port 8000. It applies database migrations on start.
- **worker**: keeps connected music servers in sync (library index every 12 h, Plex history every
  5 min, Navidrome "now playing" every minute, playlists every 6 h).

Data (the SQLite database and an auto-generated `secret_key`) lives in the `wayl-data` volume.
**Back up that volume**: the secret key also encrypts the saved Plex/Navidrome logins, so losing it
means reconnecting your servers and everyone signing in again. Set `SECRET_KEY` yourself if you prefer.

Put the settings in a `.env` file next to `docker-compose.yml` (Compose reads it automatically);
see the variables in [`docker-compose.yml`](docker-compose.yml) and the table below. Behind a reverse
proxy that terminates HTTPS, set `APP_URL=https://music.example.com` and `TRUST_PROXY_HOPS=1`.
`/healthz` returns `{"status": "ok"}` for monitoring.

Update: `git pull && docker compose up -d --build`. With Podman, build the image in Docker format
first so its health check (which the worker waits for) is kept:
`podman build --format docker -t wayl:latest . && podman compose up -d`.

## Connect your music server

Open **Settings → Music servers**.

**Navidrome** (or any Subsonic-compatible server): enter its address *as WAYL's server can reach
it* (`http://navidrome:4533` if both run in the same Compose project, otherwise its LAN address),
plus your Navidrome username and password. The password is stored encrypted and only a salted hash
of it is ever sent to Navidrome.

For instant, exact scrobbles, also point Navidrome's ListenBrainz integration at WAYL:

1. In Navidrome's config set `ND_LISTENBRAINZ_BASEURL=<APP_URL>/listenbrainz/1/` and restart it.
   This is server-wide: everyone's "Scrobble to ListenBrainz" on that Navidrome goes to WAYL.
2. In WAYL: **Settings → Scrobbling → Create token**.
3. In Navidrome: **Personal settings → Scrobble to ListenBrainz**, paste the token.

Without this, the worker still logs what you play by checking Navidrome's "now playing" list every
minute (tracks shorter than that can be missed).

**Plex**: click **Sign in with Plex**, approve WAYL in the Plex window, then pick a server. WAYL
tries the server's connections (local first) and keeps the first one it can reach. If none works
from where WAYL runs (common in Docker), use **Enter address and token instead** with an address
like `http://plex:32400` and your [Plex token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).
Your plays are imported from the server's play history (the last `HISTORY_IMPORT_DAYS` days on
the first sync, then only new ones). On a server you own, only the owner account's plays are
imported (WAYL assumes Plex's usual owner account id, 1); on a shared server Plex itself only shows
your own plays. No Plex Pass needed.

**What you get once connected**

- **Owned icon** next to every song that's on your server, everywhere in the app (only when a server
  is connected). Matching is by normalized title + artist ("Teardrop - 2006 Remaster" owns
  "Teardrop"), or by MusicBrainz id when your files are tagged with one.
- **Search → In my library**: searches only your server's tracks (WAYL's own index, so it's
  instant). The filter stays on until you switch it off.
- **Play** buttons on songs you own: audio streams from your server *through* WAYL, so your
  server's address and login never reach the browser. Plays count as a listen once half the song
  (or 4 minutes) has played. Files play as-is (no transcoding), so the browser must support the
  format: MP3, AAC/M4A, FLAC, Ogg and Opus work in current browsers; ALAC usually doesn't.
- **Imported playlists** (optional): your server's playlists are mirrored as WAYL playlists and
  re-synced, so edit them on the server.
- Tracks that aren't in MusicBrainz still show up in your library and can be played; their listens
  wait under **Settings → Listens WAYL couldn't match** (better tags on the server usually fix it).

Any other player that lets you set a custom ListenBrainz server (e.g. some Jellyfin plugins and
mobile scrobblers) can scrobble to WAYL the same way with the token.

## Sharing with friends

Each WAYL can publish **read-only share links**, and any other WAYL can subscribe to them. No
accounts across instances, no central server: a link is the permission.

- **Share a playlist:** open it and turn on **Share link**, then send the link. **Share your
  profile** (your display name, the playlists you share, and optionally your recent listens and top
  artists) under **Settings → Sharing**. Recent listens and top artists are **off by default**;
  when on, anyone with your profile link can see them.
- **Subscribe:** paste a friend's link under **Friends**. You see their playlist (or profile),
  which songs you already own on your own server, and can play those from your server or copy the
  playlist into yours. WAYL re-checks subscribed links every `SHARE_REFRESH_HOURS` (6 by default).
- **What crosses instances:** song metadata only (MusicBrainz ids, titles, artists, albums, cover
  URLs, durations). Never audio, your email, your server's address, or anything from your media
  server. The format is documented in [`docs/sharing-protocol.md`](docs/sharing-protocol.md);
  `?format=jspf` gives a playlist as JSPF for other tools.
- **Friends must be able to reach your `APP_URL`.** `http://localhost…` only works on your own
  machine (Settings shows a warning). Put WAYL behind a reverse proxy with a domain, or share over
  [Tailscale](https://tailscale.com) (`APP_URL=http://wayl.your-tailnet.ts.net:8000`).
- **Revoking:** turn a link off, or reset it (the old link stops working right away; friends need
  the new one).
- `is_public` on a playlist is different: it makes the playlist visible to people signed in to
  *your* instance. Share links work from anywhere.
- On a public instance, set `ALLOW_PRIVATE_SERVER_URLS=0` so subscribing can't be used to make your
  server fetch addresses on its own network.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then set SECRET_KEY (see below)
python create_db.py         # creates/updates the tables (Alembic migrations)
python run.py               # http://localhost:5000
python -m app.worker        # in a second terminal, if you connect a music server
```

Schema changes go through migrations from now on: after changing a model, run
`flask --app app db migrate -m "what changed"`, review the file in `migrations/versions/`, and
commit it. `python create_db.py` (or `flask --app app db upgrade`) applies it.

> **Coming from an earlier version?** The databases created before migrations existed can't be
> upgraded in place. Delete `instance/database.db` (or `database.db`) once and run
> `python create_db.py`.

### Settings (`.env`)

| Variable | What it does |
| --- | --- |
| `SECRET_KEY` | Signs sessions, tokens and reset links. Use a long random string. |
| `APP_URL` | Public URL of the site, used in reset emails (default `http://localhost:5000`). |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`, `MAIL_USE_TLS` / `MAIL_USE_SSL` | SMTP for password-reset emails. |
| `CATALOG_USER_AGENT` | Sent to MusicBrainz/ListenBrainz. Put your site's URL in it when you deploy. |
| `RATELIMIT_STORAGE_URI` | Where rate-limit counters live (default in memory; use Redis with several workers). |
| `SECRET_KEY_FILE` | Read the secret key from this file, creating it on first start (the Docker image uses `/data/secret_key`). |
| `TRUST_PROXY_HOPS` | Number of reverse proxies in front of WAYL (0 = none). |
| `ALLOW_PRIVATE_SERVER_URLS` | `1` (default) lets users connect servers on private/LAN addresses. Set `0` on a public instance. |
| `HISTORY_IMPORT_DAYS` | How far back the first Plex sync imports plays (default 30). |
| `WAYL_SOCIAL` | `1` turns on follows and a feed between users of this instance. Off by default: WAYL is a personal log first. |
| `SHARE_REFRESH_HOURS` | How often subscribed share links are re-fetched (default 6; longer after errors). |
| `WORKER_INTERVAL`, `PLEX_HISTORY_INTERVAL`, `PLAYLIST_SYNC_INTERVAL` | Worker timings in seconds (60 / 300 / 21600). |

### Password reset emails

Leave `MAIL_SERVER` empty in development: the reset email, including its link, is printed in the
server log. For real emails any SMTP account works, including free ones:

- **Gmail:** `MAIL_SERVER=smtp.gmail.com`, `MAIL_PORT=587`, your address as `MAIL_USERNAME`, and an
  [app password](https://myaccount.google.com/apppasswords) as `MAIL_PASSWORD`.
- **Brevo** (free tier): `smtp-relay.brevo.com`, port 587, with the SMTP key from your account.

Reset links expire after 1 hour and work once. Resetting or changing the password signs the account
out everywhere else (sessions, API tokens and older reset links all stop working).

## Where the music data comes from

| Service | Used for | Cost / key |
| --- | --- | --- |
| ListenBrainz Labs recording search | Song search | Free, no key |
| ListenBrainz metadata + popularity API | Album, year, genres, credits, cover ids, play counts, artist top tracks | Free, no key |
| MusicBrainz web service | Artist search and details | Free for non-commercial use, no key, max 1 request/second (the app throttles itself) |
| Cover Art Archive | Album covers | Free, images linked directly |

MusicBrainz core data is [CC0](https://musicbrainz.org/doc/About/Data_License) (public domain), so
storing it in your database is fine. A song is copied into the local `songs` table the first time
someone saves, logs or adds it to a playlist. Search results are cached in memory for 10 minutes.
If you run WAYL commercially, check the MusicBrainz commercial terms first.

Why not Deezer, Spotify or iTunes? Deezer's current API terms require approved developer access and
forbid storing their metadata or playing previews outside their widget. Spotify needs a developer
account and has restricted its API. The iTunes Search API is meant for promoting Apple content.
None of them is a good fit for a free app that keeps listening history.

Without a connected server there is no audio playback: each song page links out to YouTube,
Spotify and Apple Music searches.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests never hit the network: `tests/conftest.py` swaps the catalog's HTTP layer for canned responses,
and `tests/test_servers.py` uses fake Plex, plex.tv and Navidrome servers.

## Pages

`/search`, `/following`, `/playlists` (+ `/playlists/<id>`), `/songs` (saved + recently played),
`/profile`, `/settings` (music servers, scrobbling, sharing, account), `/friends`
(+ `/friends/<id>`), plus `/song/<mbid>`, `/artist/<mbid>` and `/user/<id>`. Sign-in pages: `/login`,
`/register`, `/forgot`, `/reset`. Flask serves the same page for all of them and `app.js` picks
the view.

## API

The full reference, including the stable `/api/v1` paths for other clients, is in
[`docs/api.md`](docs/api.md). Summary:

JSON in, JSON out. Signed-in browsers use the session cookie; other clients sign in with
`POST /auth/login {"email", "password", "tokens": true}` to get an access token (send it as
`Authorization: Bearer <access_token>`) and a refresh token (renew with `POST /auth/refresh`).
Cookie-authenticated writes and all `/auth/*` POSTs must send `Content-Type: application/json`.
Song ids are MusicBrainz recording ids (UUIDs).

| Method | Path | Auth | What it does |
| --- | --- | --- | --- |
| POST | `/auth/register` | – | Create an account `{email, username, password}` and sign in |
| POST | `/auth/login` | – | Sign in `{email, password, tokens?}` |
| POST | `/auth/logout` | – | Sign out |
| GET | `/auth/session` | – | `{"user": ...}` or `{"user": null}` |
| POST | `/auth/forgot` | – | Email a reset link `{email}` (same answer whether or not the account exists) |
| POST | `/auth/reset` | – | Set a new password `{token, password}` |
| POST | `/auth/refresh` | – | New access token `{refresh_token}` |
| GET | `/api/songs?q=` | – | Search songs (title, artist, or both) |
| GET | `/api/songs/<mbid>` | – | Song details, credits, links, play counts |
| GET | `/api/artists?q=` / `/api/artists/<mbid>` | – | Find artists / artist with top tracks |
| GET | `/api/me/songs` | ✔ | Your saved songs |
| PUT / DELETE | `/api/me/songs/<mbid>` | ✔ | Save / unsave a song |
| GET / POST | `/api/playlists` | ✔ | List yours / create `{name, is_public?}` |
| GET | `/api/playlists/<id>` | public playlists only | Playlist with songs |
| POST | `/api/playlists/<id>` | owner | Add a song `{song_id}` |
| PATCH / DELETE | `/api/playlists/<id>` | owner | Rename, toggle `is_public` / delete |
| DELETE | `/api/playlists/<id>/songs/<mbid>` | owner | Remove a song |
| GET / POST | `/api/history` | ✔ | Your recent listens / log one `{song_id}` |
| GET | `/api/feed` | ✔ | Recent listens from people you follow (social only) |
| GET | `/api/stats?days=30` | ✔ | Top songs, top artists, totals |
| GET / PATCH / DELETE | `/api/me` | ✔ | Your account: view, edit `{username?, bio?}`, delete `{password}` |
| POST | `/api/me/password` | ✔ | Change password `{current_password, new_password}` |
| GET | `/api/me/following`, `/api/me/followers` | ✔ | People you follow / who follow you (social only) |
| GET | `/api/users?q=` | ✔ | Find people by username (social only) |
| GET | `/api/users/<id>` | – | Public profile (no email) |
| GET | `/api/users/<id>/listens` | followers | Their recent listens (404 if you don't follow them) (social only) |
| GET | `/api/users/<id>/playlists` | – | Their public playlists |
| POST / DELETE | `/api/users/<id>/follow` | ✔ | Follow / unfollow (social only) |
| GET / POST | `/api/servers` | ✔ | Your connected servers / connect one (`{kind: "navidrome", url, username, password}`, `{kind: "plex", url, token}` or `{kind: "plex", server}` after the PIN sign-in) |
| POST, GET | `/api/servers/plex/pin`, `/api/servers/plex/pin/<id>` | ✔ | Plex sign-in: get the plex.tv URL / poll until approved (lists your servers) |
| PATCH / DELETE | `/api/servers/<id>` | owner | Toggle `sync_listens` / `sync_playlists`, change `url` / disconnect |
| POST | `/api/servers/<id>/sync` | owner | Sync now `{jobs?: ["library", "listens", "playlists"]}` |
| GET | `/api/library?q=` | ✔ | Search the tracks on your servers |
| POST | `/api/library/tracks/<id>/match` | owner | Find the MusicBrainz song for a library-only track |
| GET | `/api/songs/<mbid>/sources` | ✔ | Where you can play a song from |
| GET | `/api/stream/<track id>` | owner | The audio, proxied from your server (supports `Range`) |
| GET / POST / DELETE | `/api/me/listen-token` | ✔ | Scrobble token: status / create (shown once) / revoke |
| GET / POST / DELETE | `/api/me/unmatched` | ✔ | Listens that didn't match / retry / dismiss |
| GET | `/listenbrainz/1/validate-token` | token | ListenBrainz-compatible |
| POST | `/listenbrainz/1/submit-listens` | token | ListenBrainz-compatible (`single`, `import`; `playing_now` is accepted and ignored) |
| GET | `/healthz` | – | Health check |

When you have a server connected, song objects also carry `"owned": true/false`.

Sign-in, registration and password reset are rate limited per IP.
