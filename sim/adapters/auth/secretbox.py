"""Fernet helper for per-user secrets. Not imported by sim/core."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _fernet(secret: str) -> Fernet:
    digest = hashlib.sha256((secret or "sim-byok-unconfigured").encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def secret_from_config(config) -> str:
    explicit = (getattr(config, "byok_secret", "") or "").strip()
    if explicit:
        return explicit
    return "|".join((
        "sim-byok-v1",
        getattr(config, "firebase_project_id", "") or "local",
        getattr(config, "instructor_password", "") or "default",
    ))


def encrypt_secret(secret: str, plaintext: str) -> str:
    return _fernet(secret).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(secret: str, token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet(secret).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as e:
        raise ValueError("could not decrypt stored key") from e
