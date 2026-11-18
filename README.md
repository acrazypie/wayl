# WAYL: What Are You Listening?

![WAYL logo](app/static/logo-wordmark.svg)

A small social music log. Search any song, log what you're playing, save songs, build playlists,
follow friends and see what they're listening to, and check your top songs and artists.

Flask + SQLite, email/password accounts, vanilla JS frontend (no build step). Song data comes from
the free, open [MusicBrainz](https://musicbrainz.org) and [ListenBrainz](https://listenbrainz.org)
databases, so there's no song library to maintain and no API key to get.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then set SECRET_KEY (see below)
python create_db.py         # creates the tables
python run.py               # http://localhost:5000
```

> **Upgrading from the Google sign-in version?** The schema changed (users now have passwords,
> songs are keyed by MusicBrainz id, new `saved_songs` table). Delete `instance/database.db`
> (or `database.db`) and run `python create_db.py` again.

### Settings (`.env`)

| Variable | What it does |
| --- | --- |
| `SECRET_KEY` | Signs sessions, tokens and reset links. Use a long random string. |
| `APP_URL` | Public URL of the site, used in reset emails (default `http://localhost:5000`). |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`, `MAIL_USE_TLS` / `MAIL_USE_SSL` | SMTP for password-reset emails. |
| `CATALOG_USER_AGENT` | Sent to MusicBrainz/ListenBrainz. Put your site's URL in it when you deploy. |
| `RATELIMIT_STORAGE_URI` | Where rate-limit counters live (default in memory; use Redis with several workers). |

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

There is no audio playback. Each song page links out to YouTube, Spotify and Apple Music searches.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests never hit the network: `tests/conftest.py` swaps the catalog's HTTP layer for canned responses.

## Pages

`/search`, `/following`, `/playlists` (+ `/playlists/<id>`), `/songs` (saved + recently played),
`/profile`, plus `/song/<mbid>`, `/artist/<mbid>` and `/user/<id>`. Sign-in pages: `/login`,
`/register`, `/forgot`, `/reset`. Flask serves the same page for all of them and `app.js` picks
the view.

## API

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
| GET | `/api/feed` | ✔ | Recent listens from people you follow |
| GET | `/api/stats?days=30` | ✔ | Top songs, top artists, totals |
| GET / PATCH / DELETE | `/api/me` | ✔ | Your account: view, edit `{username?, bio?}`, delete `{password}` |
| POST | `/api/me/password` | ✔ | Change password `{current_password, new_password}` |
| GET | `/api/me/following`, `/api/me/followers` | ✔ | People you follow / who follow you |
| GET | `/api/users?q=` | ✔ | Find people by username |
| GET | `/api/users/<id>` | – | Public profile (no email) |
| GET | `/api/users/<id>/listens` | followers | Their recent listens (404 if you don't follow them) |
| GET | `/api/users/<id>/playlists` | – | Their public playlists |
| POST / DELETE | `/api/users/<id>/follow` | ✔ | Follow / unfollow |

Sign-in, registration and password reset are rate limited per IP.
