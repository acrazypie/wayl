"""Clients for people's own music servers.

    client = client_for(server)      # MediaServer row -> PlexClient / SubsonicClient
    client.search_tracks("Nude")     # -> [RemoteTrack]
    client.stream_request(track)     # -> (url, headers) for the audio proxy
"""
from app.services.media.base import MediaServerError, RemoteTrack, normalize_url  # noqa: F401
from app.services.media.plex import PlexClient
from app.services.media.subsonic import SubsonicClient
from app.services.secrets_box import decrypt


def client_for(server):
    secret = decrypt(server.secret)
    if secret is None:
        raise MediaServerError("Saved login can't be read (the app's SECRET_KEY changed). Reconnect this server.")
    if server.kind == "plex":
        return PlexClient(server.base_url, secret)
    if server.kind == "navidrome":
        return SubsonicClient(server.base_url, server.username, secret)
    raise MediaServerError(f"Unknown server type {server.kind}")
