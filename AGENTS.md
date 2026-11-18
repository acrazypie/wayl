## Context

- **Stack:** Flask 3, Flask-SQLAlchemy, Flask-Login, Flask-RESTful, Flask-Limiter, SQLite, PyJWT,
  requests. Vanilla JS frontend in `app/static/app.js`, no build step.
- **Layout:** `app/api/` (REST resources), `app/models/`, `app/services/catalog.py` (MusicBrainz /
  ListenBrainz client), `app/utility/` (config, JWT, `auth_required`, mail), `app/routes/main.py`
  (serves the single-page app for every page URL), `tests/` (pytest, in-memory SQLite, fake catalog).
- **Auth:** email + password (`app/api/auth.py`), password reset by emailed signed link. Browsers
  use the Flask-Login session cookie, API clients use a Bearer JWT. Both go through `auth_required`
  in `app/utility/__init__.py`. `session_version` on the user revokes sessions/JWTs/reset links.
- **Songs:** come from the catalog, not a local library. Public song ids are MusicBrainz recording
  ids; a local `Song` row is created on first save/log/playlist-add (`ensure_song`). Tests must never
  hit the network: they monkeypatch `catalog._request` (see `tests/conftest.py`).

## Rules (don't break these)

1. **Every write endpoint uses `@auth_required`** and checks ownership. Private data must look
   missing (404) to non-owners.
2. **Never return `email`** (or other private fields) from endpoints other than `/api/me`. Use
   `public_user()`.
3. **No `innerHTML` with data.** The frontend builds DOM with the `h()` helper so user-supplied
   titles can't inject HTML.
4. **Register Flask-RESTful resources before `api.init_app(app)`**, otherwise they silently don't
   exist.
5. Timestamps are stored as naive UTC via `utcnow` (callable, no parentheses) and sent as `...Z`
   through `iso()`.
6. Every new endpoint or behavior gets a test in `tests/`. Never commit `.env` or `database.db`.
7. Don't add a dependency without adding it to `requirements.txt`.

## Phase 0: baseline

- [ ] Create a venv, `pip install -r requirements-dev.txt`, run `pytest -q` (all green).
- [ ] Run the app, load `/` in a browser, search songs, check the browser console for errors.
      The frontend was written without a browser test, so fix anything that's off.
- [ ] Test the password-reset email end to end with a real SMTP account (see README). Fix any
      issue found.

## Phase 1: make it deployable

- [ ] Add **Flask-Migrate** (Alembic) and create the initial migration. From here on, no more
      "delete the database" schema changes.
- [ ] Move config into a `Config` class with `DevelopmentConfig` / `ProductionConfig`; in
      production, refuse to start without `SECRET_KEY`, set `SESSION_COOKIE_SECURE=True`, and
      drop `ALLOW_INSECURE_OAUTH`.
- [ ] Add **Flask-Limiter**: strict limits on `/auth/*`, moderate on all writes.
- [ ] Add `ProxyFix` so OAuth redirects work behind a reverse proxy (https).
- [ ] Add `gunicorn`, a `Dockerfile`, and a `/healthz` route. Deploy notes in the README for one
      host (Fly.io, Render, or Railway) with Postgres instead of SQLite.
- [ ] GitHub Actions workflow running `pytest -q` on every push.

## Phase 2: make it feel like a product

- [ ] **Now playing:** `POST /api/now-playing {song_id}` stores a status that expires after ~5 min;
      show a "🎧 listening now" strip for followed users in the Friends tab.
- [ ] **Likes:** heart a song; "Liked songs" list; show like counts in search results.
- [ ] **Pagination:** "Load more" in search using `offset`/`total`.
- [ ] **Edit/delete your own songs.** Add `created_by` to `Song`; only creators can edit, and
      deleting a song someone has logged must be blocked or soft-deleted.
- [ ] **Duplicate cleanup:** normalize titles/artists (case, "feat.", punctuation) when adding.
- [ ] **Privacy toggle:** let users hide their listens from followers (and respect it in `/api/feed`).

## Phase 3: bring people's data in

- [ ] **CSV import** of listens (`title,artist,album,listened_at`) from the Recent tab.
- [ ] **Last.fm / ListenBrainz import** via their public APIs (read their current docs and terms
      first; don't assume endpoints from memory). Make imports idempotent.
- [ ] Spotify import only after checking Spotify's current developer terms and API availability.
      If it's restricted, skip it and say why.

## Phase 4: sharing (what makes people tell friends)

- [ ] Public profile page `/u/<username>`: top artists, recent public listens, follow button.
- [ ] Public playlist page `/p/<id>` for `is_public` playlists (+ Open Graph tags for link previews),
      and a share toggle in the Playlists tab.
- [ ] **"Wrapped"-style recap:** a shareable card (HTML page or generated PNG) of top songs/artists
      for a chosen period, built on `/api/stats`.
- [ ] Optional weekly digest email of friends' top listens (opt-in, with an unsubscribe link).

## Phase 5: polish and ship

- [ ] README screenshots/GIF, repo description and topics, a demo link.
- [ ] Accessibility pass (focus states, labels, contrast in light and dark mode).
- [ ] Add `LICENSE`, `CONTRIBUTING.md`, and a few `good first issue`s.

## Definition of done for any task

`pytest -q` passes, the app starts, the UI path works in a browser, rules above still hold,
README updated if behavior or setup changed.
