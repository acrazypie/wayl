"""Encrypt media server credentials at rest (Fernet, key derived from SECRET_KEY).

If SECRET_KEY changes, old secrets can't be decrypted any more: decrypt() returns None and the
user is asked to reconnect the server.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.utility import config


def _fernet():
    key = hashlib.sha256(("wayl-media-secrets:" + config.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str):
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return None
