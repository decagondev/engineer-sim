from __future__ import annotations

import json

import httpx

from sim.core.ports.identity import IdentityError, Principal, ROLES

_LOOKUP = "https://identitytoolkit.googleapis.com/v1/accounts:lookup"
_SIGNUP = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
_OOB = "https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode"
_DELETE = "https://identitytoolkit.googleapis.com/v1/accounts:delete"


class FirebaseVerifier:
    """Verify Firebase ID tokens via Identity Toolkit REST (web API key).

    No firebase_admin SDK required for verification. Admin user-create uses
    the same web API key (signUp + password-reset email).
    """

    def __init__(self, api_key: str, project_id: str = "") -> None:
        if not api_key:
            raise IdentityError("FIREBASE_WEB_API_KEY is not set", status=503)
        self._key = api_key
        self._project = project_id

    def verify(self, token: str) -> Principal:
        raw = (token or "").strip()
        if raw.lower().startswith("bearer "):
            raw = raw[7:].strip()
        if not raw:
            raise IdentityError("missing token")
        try:
            r = httpx.post(
                f"{_LOOKUP}?key={self._key}",
                json={"idToken": raw},
                timeout=10.0,
            )
        except httpx.HTTPError as e:
            raise IdentityError(f"firebase unreachable: {e}", status=503) from e
        if r.status_code != 200:
            raise IdentityError("invalid or expired token")
        users = (r.json() or {}).get("users") or []
        if not users:
            raise IdentityError("invalid or expired token")
        u = users[0]
        uid = u.get("localId") or ""
        email = u.get("email") or ""
        if not uid:
            raise IdentityError("invalid token (no uid)")
        role = "challenger"
        raw_claims = u.get("customAttributes") or "{}"
        try:
            claims = json.loads(raw_claims) if raw_claims else {}
            if isinstance(claims, dict) and claims.get("role") in ROLES:
                role = claims["role"]
        except json.JSONDecodeError:
            pass
        return Principal(
            uid=uid, email=email, role=role,
            email_verified=bool(u.get("emailVerified")),
        )

    def create_email_user(self, email: str, password: str) -> str:
        """Create a Firebase email/password user. Returns uid."""
        r = httpx.post(
            f"{_SIGNUP}?key={self._key}",
            json={"email": email, "password": password,
                  "returnSecureToken": True},
            timeout=10.0,
        )
        data = r.json() or {}
        if r.status_code != 200:
            msg = data.get("error", {}).get("message", "create user failed")
            raise IdentityError(str(msg), status=400)
        return data.get("localId") or ""

    def send_password_reset(self, email: str) -> None:
        httpx.post(
            f"{_OOB}?key={self._key}",
            json={"requestType": "PASSWORD_RESET", "email": email},
            timeout=10.0,
        )

    def delete_id_token_user(self, id_token: str) -> None:
        httpx.post(
            f"{_DELETE}?key={self._key}",
            json={"idToken": id_token},
            timeout=10.0,
        )
