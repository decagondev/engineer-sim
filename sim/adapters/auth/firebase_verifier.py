from __future__ import annotations

import json
import time

import httpx

from sim.core.ports.identity import IdentityError, Principal, ROLES

_CACHE_SEC = 240
_CACHE_MAX = 256

_LOOKUP = "https://identitytoolkit.googleapis.com/v1/accounts:lookup"
_SIGNUP = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
_OOB = "https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode"
_DELETE = "https://identitytoolkit.googleapis.com/v1/accounts:delete"


class FirebaseVerifier:
    """Verify Firebase ID tokens via Identity Toolkit REST (web API key).

    No firebase_admin SDK required for verification. Admin user-create uses
    the same web API key (signUp + password-reset email).
    """

    def __init__(self, api_key: str, project_id: str = "",
                 credentials_json: str = "") -> None:
        if not api_key:
            raise IdentityError("FIREBASE_WEB_API_KEY is not set", status=503)
        self._key = api_key
        self._project = project_id
        self._creds_path = (credentials_json or "").strip()
        self._sa = None
        self._http = httpx.Client(timeout=10.0)
        self._cache: dict[str, tuple[float, Principal]] = {}

    def verify(self, token: str) -> Principal:
        raw = (token or "").strip()
        if raw.lower().startswith("bearer "):
            raw = raw[7:].strip()
        if not raw:
            raise IdentityError("missing token")
        now = time.monotonic()
        hit = self._cache.get(raw)
        if hit and hit[0] > now:
            return hit[1]
        try:
            r = self._http.post(
                f"{_LOOKUP}?key={self._key}",
                json={"idToken": raw},
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
        principal = Principal(
            uid=uid, email=email, role=role,
            email_verified=bool(u.get("emailVerified")),
        )
        if len(self._cache) >= _CACHE_MAX:
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        self._cache[raw] = (now + _CACHE_SEC, principal)
        return principal

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
        r = self._http.post(
            f"{_OOB}?key={self._key}",
            json={"requestType": "PASSWORD_RESET", "email": email},
        )
        if r.status_code != 200:
            data = r.json() or {}
            msg = (data.get("error") or {}).get("message") or "reset failed"
            raise IdentityError(str(msg), status=400)

    def set_password(self, uid: str, password: str) -> None:
        pw = (password or "").strip()
        if len(pw) < 6:
            raise IdentityError("Password must be at least 6 characters.", status=400)
        self._admin_post("accounts:update", {"localId": uid, "password": pw})

    def update_email(self, uid: str, email: str) -> None:
        em = (email or "").strip()
        if not em:
            raise IdentityError("email required", status=400)
        self._admin_post("accounts:update", {"localId": uid, "email": em})

    def set_disabled(self, uid: str, disabled: bool) -> None:
        self._admin_post("accounts:update", {
            "localId": uid, "disableUser": bool(disabled)})

    def delete_account(self, uid: str) -> None:
        try:
            self._admin_post("accounts:delete", {"localId": uid})
        except IdentityError as e:
            if "USER_NOT_FOUND" in (e.detail or ""):
                return
            raise

    def delete_id_token_user(self, id_token: str) -> None:
        self._http.post(
            f"{_DELETE}?key={self._key}",
            json={"idToken": id_token},
        )

    def _admin_headers(self) -> dict:
        from google.auth.transport.requests import Request
        from sim.adapters.auth.service_account import service_account_credentials
        if self._sa is None:
            try:
                self._sa = service_account_credentials(self._creds_path)
            except RuntimeError as e:
                raise IdentityError(str(e), status=503) from e
        if self._sa is None:
            raise IdentityError(
                "Set FIREBASE_CREDENTIALS_JSON to change passwords or email.",
                status=503)
        if not self._sa.valid:
            self._sa.refresh(Request())
        return {"Authorization": f"Bearer {self._sa.token}"}

    def _admin_post(self, action: str, body: dict) -> dict:
        if not self._project:
            raise IdentityError("FIREBASE_PROJECT_ID is required", status=503)
        url = (f"https://identitytoolkit.googleapis.com/v1/projects/"
               f"{self._project}/{action}")
        try:
            r = self._http.post(url, json=body, headers=self._admin_headers())
        except httpx.HTTPError as e:
            raise IdentityError(f"firebase unreachable: {e}", status=503) from e
        data = r.json() or {}
        if r.status_code != 200:
            msg = (data.get("error") or {}).get("message") or f"firebase {r.status_code}"
            raise IdentityError(str(msg), status=400)
        return data
