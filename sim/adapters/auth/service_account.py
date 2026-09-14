"""Resolve the Firebase service account from config or environment.

Accepts, in order:
  1. FIREBASE_CREDENTIALS_JSON as a path to a service-account file
  2. FIREBASE_CREDENTIALS_JSON as the raw JSON document itself (hosted
     platforms such as Railway inject secrets as plain strings)
  3. GOOGLE_APPLICATION_CREDENTIALS as a path

Returns None when nothing is configured so callers can fall back to
Application Default Credentials or raise their own error.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def service_account_info(value: str = "") -> dict | None:
    """Parse the configured service account into a dict, or None."""
    raw = (value or "").strip() or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                "FIREBASE_CREDENTIALS_JSON looks like JSON but does not parse") from e
        if not isinstance(info, dict) or info.get("type") != "service_account":
            raise RuntimeError(
                "FIREBASE_CREDENTIALS_JSON must be a service_account document")
        return info
    path = Path(raw)
    if not path.is_file():
        raise RuntimeError(f"FIREBASE_CREDENTIALS_JSON not found: {raw}")
    return json.loads(path.read_text(encoding="utf-8"))


def service_account_credentials(value: str = "", scopes: list[str] | None = None):
    """google.oauth2 Credentials built from the configured service account, or None."""
    info = service_account_info(value)
    if info is None:
        return None
    from google.oauth2 import service_account
    return service_account.Credentials.from_service_account_info(
        info, scopes=scopes or _SCOPES)
