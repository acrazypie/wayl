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


def normalize_url(url):
    """Validate a server URL typed by a user and return it without a trailing slash."""
    url = str(url or "").strip()
    if "://" not in url:
        url = "http://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise MediaServerError("Enter the server's address, like http://192.168.1.10:4533")
    if parts.username or parts.password:
        raise MediaServerError("Don't put the login in the URL")
    if not config.ALLOW_PRIVATE_SERVER_URLS:
        try:
            infos = socket.getaddrinfo(parts.hostname, parts.port or 80)
        except OSError as exc:
            raise MediaServerError(f"Can't find the host {parts.hostname}") from exc
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise MediaServerError("Private network addresses are not allowed on this WAYL instance")
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
