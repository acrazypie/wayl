# WAYL mobile app: plan

Status: planned, not started. This is the plan for a native iOS and Android client for WAYL.

## Decisions

| Decision | Choice |
| --- | --- |
| Platforms | iOS and Android, built with Expo (React Native + TypeScript) |
| Who it connects to | Any self-hosted WAYL instance. The app asks for the instance URL on first launch, checks `GET /api/instance`, then signs in or registers. |
| Offline | Streaming only in v1. Offline support is limited to cached metadata (saved songs, playlists). No audio downloads. |
| Repo | `mobile/` folder in this repo, so API and client changes ship together |

Supporting choices (recommended, not yet confirmed):

- **Playback:** `react-native-track-player` (or `expo-audio`), giving background audio, lock-screen and Control Center controls, and an Android media notification.
- **Server state:** TanStack Query, with the cache persisted to MMKV for fast cold starts.
- **Tokens:** `expo-secure-store` (Keychain on iOS, Keystore on Android). Never store the account password. The refresh token lives only in secure storage.
- **Validation:** zod on every API response. Remote share data is untrusted input, so validate before rendering.

## Current API: what already works

- Bearer tokens: `POST /auth/login` with `"tokens": true` returns a 1-hour access token and a 30-day refresh token. `POST /auth/refresh` renews the access token.
- `/api/v1` is the stable base path for other clients. Every route is also served there.
- `GET /api/instance` reports the version and enabled features, so the app can adapt before sign-in.
- `GET /api/stream/<track_id>` accepts bearer auth and supports `Range`, so native players can seek.
- Listens are logged with `POST /api/history` (`source: "player"`). Repeats within 30 seconds are ignored.
- Plex sign-in uses a PIN flow (`/api/servers/plex/pin`) that the app can drive with an in-app browser and polling.

## Backend work needed before or during Phase 1

1. **Per-device sessions.** `UserModel.refresh_token` is a single column, so signing in on a second device overwrites the first device's refresh token. Replace it with a sessions table (device name, hashed refresh token, last used). Rotate the refresh token on each use.
2. **Logout that revokes.** `POST /auth/logout` only clears the cookie session. Revoke the device's refresh token on logout, and add `GET /api/me/sessions` and `DELETE /api/me/sessions/<id>` so users can sign out other devices.
3. **Rate limits behind carrier NAT.** Login is 50/hour per IP and refresh is 30/hour per IP. Phones on cellular share IPs, so real users could be locked out. Key limits by account where possible and raise the per-IP numbers.
4. **Search pagination.** `GET /api/songs` has no `offset` yet. Mobile lists need it.
5. **Tests.** Every new endpoint and behavior gets a pytest test, per the repo rules.

## Connection and network rules

- The first screen takes the instance URL. The app checks `GET /api/instance` before showing the sign-in form.
- Plain `http://` is allowed only for local addresses (LAN IPs and `localhost`). This needs an iOS App Transport Security exception for local networking and a cleartext config on Android for those domains.
- Public hosts must use HTTPS. The app refuses plain HTTP to any other host.
- Self-signed certificates are not supported in v1.
- The phone has to reach `APP_URL`. Recommend HTTPS through a reverse proxy or Tailscale, as the README describes.
- Navidrome and Plex credentials pass through the phone once, to connect a server. Never store server credentials on the device.

## Phases

### Phase 0: spikes (about 1 week)

- Stream one FLAC, one ALAC and one MP3 file from a real Navidrome or Plex server on both platforms, and confirm playback and seeking.
- Test HTTP to a LAN IP and HTTPS through a reverse proxy.
- Test the Plex PIN sign-in flow with an in-app browser and polling.

### Phase 1: MVP (about 6–8 weeks for one developer)

- Connect to an instance, register, sign in, forgot password (the reset link opens in the browser), and sign out.
- Search songs and artists, with a song page (save, log) and an artist page.
- Playlists: list, view, create, rename, add and remove songs, and share a link through the native share sheet.
- History, saved songs, and the stats screen (top songs and artists).
- Settings: connect Navidrome or Plex, library search with the "owned" badge, and the scrobble token.
- Playback: stream from the server, mini player, full player, lock-screen controls, and automatic listen logging using the web app's rule (half the song or 4 minutes), sent with `POST /api/history` and `source: "player"`.
- Friends: subscribe to a share link and view the playlist.

### Phase 2: polish (about 3–4 weeks)

- Cached metadata for offline viewing of saved songs and playlists. Audio downloads are out of scope.
- Universal links so `/share/v1/...` and `/u/...` URLs open in the app.
- Widgets and system integrations (home-screen widget, App Intents or Siri Shortcuts, and Android Auto or CarPlay, which need extra review).
- Accessibility pass: Dynamic Type, VoiceOver, TalkBack, and contrast in both themes.

### Phase 3: release (about 2 weeks plus review time)

- TestFlight and Play internal testing first.
- Store listings, privacy labels, screenshots, and review notes that explain the self-hosted model.
- Apple developer account (about $99/year) and Google Play developer account (about $25, one time).

## Risks and open items

- **GPL-3.0 and the App Store.** The repo is GPL-3.0, which can clash with Apple's distribution terms. Decide before Phase 3 whether the client stays GPL and what that means for App Store and F-Droid distribution.
- **Listen dedupe.** The API ignores repeats within 30 seconds. The client should not log the same play again on pause and resume.
- **Plain HTTP on public hosts** is blocked by design. Users with LAN-only instances need the local-address exception.
- **Offline audio downloads** stay out of v1. Storage management and media-server licensing questions would need their own plan.

## Suggested repo layout

```
mobile/
  PLAN.md          this file
  app/             Expo app (expo-router screens)
  src/api/         typed API client, zod schemas, token handling
  src/player/      playback wrapper
  README.md        setup, running on device, release steps
```

Add a mobile section to `AGENTS.md` with the rules that apply to the client (no secrets in logs, validate all responses, store tokens only in secure storage). Add a CI job that runs the mobile typecheck and tests on every push.
