"""GitHub device-flow OAuth (no redirect URL, works from any browser).

    broker = GitHubDeviceFlow(client_id)
    code = broker.start("public_repo")      # show code.user_code at code.verification_uri
    token = broker.poll(code.device_code)   # None while the user has not approved yet

`post` is injectable so tests never touch github.com.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

from sim.core.ports.oauth import DeviceCode, OAuthError, OAuthToken

DEVICE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
GRANT = "urn:ietf:params:oauth:grant-type:device_code"


def _default_post(url: str, form: dict) -> dict:
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Accept": "application/json", "User-Agent": "flight-sim"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raise OAuthError(f"GitHub returned {e.code}") from e
    except urllib.error.URLError as e:
        raise OAuthError(f"could not reach GitHub: {e.reason}") from e


class GitHubDeviceFlow:
    def __init__(self, client_id: str, post: Optional[Callable[[str, dict], dict]] = None) -> None:
        self._client_id = (client_id or "").strip()
        self._post = post or _default_post

    @property
    def configured(self) -> bool:
        return bool(self._client_id)

    def start(self, scope: str = "public_repo") -> DeviceCode:
        if not self._client_id:
            raise OAuthError("GitHub sign-in is not configured on this server (GITHUB_OAUTH_CLIENT_ID)")
        d = self._post(DEVICE_URL, {"client_id": self._client_id, "scope": scope})
        if not d.get("device_code"):
            raise OAuthError(d.get("error_description") or d.get("error") or "GitHub did not issue a device code")
        return DeviceCode(device_code=d["device_code"], user_code=d.get("user_code", ""),
                          verification_uri=d.get("verification_uri", "https://github.com/login/device"),
                          interval=int(d.get("interval") or 5), expires_in=int(d.get("expires_in") or 900))

    def poll(self, device_code: str) -> Optional[OAuthToken]:
        d = self._post(TOKEN_URL, {"client_id": self._client_id, "device_code": device_code,
                                   "grant_type": GRANT})
        if d.get("access_token"):
            return OAuthToken(access_token=d["access_token"], scope=d.get("scope", ""),
                              token_type=d.get("token_type", "bearer"))
        err = d.get("error", "")
        if err in ("authorization_pending", "slow_down"):
            return None
        if err == "expired_token":
            raise OAuthError("the code expired; start again")
        if err == "access_denied":
            raise OAuthError("you cancelled the sign-in on GitHub")
        raise OAuthError(d.get("error_description") or err or "GitHub did not issue a token")
