"""Per-user GitLab tokens. A pasted personal access token is stored as-is
(encrypted); a Connect GitLab token is stored as an encrypted JSON bundle
(access + refresh + expiry) because GitLab access tokens expire, two hours by
default. The resolver refreshes a stale bundle through the broker and writes
the new one back, so Files keeps committing for as long as the refresh token
lives."""
from __future__ import annotations

import dataclasses
import json
import time
from typing import Callable, Optional

from sim.core.ports.oauth import OAuthError, OAuthToken

REFRESH_SKEW = 90       # refresh this many seconds before expiry


def pack_token(token: OAuthToken, now: Optional[float] = None) -> str:
    """Plaintext bundle for a Connect GitLab token (encrypt before storing)."""
    now = time.time() if now is None else now
    return json.dumps({"access_token": token.access_token,
                       "refresh_token": token.refresh_token or "",
                       "expires_at": (now + token.expires_in) if token.expires_in else 0})


def unpack(raw: str) -> dict:
    """{'access_token', 'refresh_token', 'expires_at'} for a bundle, or the
    same shape wrapping a plain pasted token."""
    s = (raw or "").strip()
    if s.startswith("{"):
        try:
            d = json.loads(s)
            if isinstance(d, dict) and d.get("access_token"):
                return {"access_token": d["access_token"],
                        "refresh_token": d.get("refresh_token") or "",
                        "expires_at": float(d.get("expires_at") or 0)}
        except ValueError:
            pass
    return {"access_token": s, "refresh_token": "", "expires_at": 0}


def user_token_resolver(users, secret: str, server_token: str = "", broker=None,
                        now: Callable[[], float] = time.time) -> Callable[[], str]:
    """The signed-in user's GitLab token when they stored one (refreshed if it
    is about to expire), else the classroom token."""
    def resolve() -> str:
        from sim.adapters.llm.request_context import current_user, prime_user
        from sim.adapters.auth.secretbox import decrypt_secret, encrypt_secret
        rec = current_user(users)
        enc = getattr(rec, "gitlab_token_enc", "") if rec else ""
        if not enc:
            return server_token or ""
        try:
            bundle = unpack(decrypt_secret(secret, enc))
        except ValueError:
            return server_token or ""
        tok = bundle["access_token"]
        exp = bundle["expires_at"]
        if exp and now() >= exp - REFRESH_SKEW and bundle["refresh_token"] and broker is not None:
            try:
                fresh = broker.refresh(bundle["refresh_token"])
            except OAuthError:
                return tok if now() < exp else (server_token or "")
            prime_user(users.upsert(dataclasses.replace(rec, gitlab_token_enc=encrypt_secret(
                secret, pack_token(fresh, now())))))
            tok = fresh.access_token
        return tok or server_token or ""
    return resolve
