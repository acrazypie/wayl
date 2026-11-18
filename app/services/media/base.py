import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import requests

from app.utility import config

USER_AGENT = "WAYL/1.0"
_session = requests.Session()


class MediaServerError(Exception):
    """The music server could not be reached, refused the login, or answered nonsense."""


@dataclass
class RemoteTrack:
    remote_id: str
    title: str
    artist: str
    album: str = None
    duration: int = None  # seconds
    mbid: str = None
    stream_key: str = None  # Plex part path


def http(method, url, **kwargs):
    """Every request to a media server goes through here (tests replace this function)."""
    kwargs.setdefault("timeout", 10)
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    try:
        return _session.request(method, url, headers=headers, **kwargs)
    except requests.RequestException as exc:
        raise MediaServerError(f"Can't reach {urlsplit(url).netloc}: {exc.__class__.__name__}") from exc


class UnsafeURL(ValueError):
    """A URL WAYL refuses to fetch (bad scheme, credentials, or a private address when those
    are not allowed)."""


def check_fetch_url(url, *, default_scheme="http"):
    """Validate a URL WAYL's server is about to fetch and return it normalized (no query, no
    fragment, no trailing slash). Shared by media servers and share links.

    With ALLOW_PRIVATE_SERVER_URLS off, every address the host resolves to must be public, so
    nobody can make WAYL reach into its own network. Call it again for each redirect target."""
    url = str(url or "").strip()
    if "://" not in url:
        url = f"{default_scheme}://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeURL("Enter a full address, like https://music.example.com")
    if parts.username or parts.password:
        raise UnsafeURL("Don't put a login in the URL")
    if not config.ALLOW_PRIVATE_SERVER_URLS:
        try:
            infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
        except OSError as exc:
            raise UnsafeURL(f"Can't find the host {parts.hostname}") from exc
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                raise UnsafeURL("Private network addresses are not allowed on this WAYL instance")
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def normalize_url(url):
    """Validate a media server URL typed by a user and return it without a trailing slash."""
    try:
        return check_fetch_url(url)
    except UnsafeURL as exc:
        message = str(exc)
        if message.startswith("Enter a full address"):
            message = "Enter the server's address, like http://192.168.1.10:4533"
        raise MediaServerError(message) from exc


def int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
