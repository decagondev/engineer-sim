"""GitLab device-flow OAuth (GitLab 17.2+; no redirect, works from any browser).

    broker = GitLabDeviceFlow("https://labs.gauntletai.com", application_id)
    code = broker.start("api")              # show code.user_code at code.verification_uri
    token = broker.poll(code.device_code)   # None while the user has not approved yet
    fresh = broker.refresh(token.refresh_token)   # GitLab access tokens expire (2 h default)

`post` is injectable so tests never touch the instance.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

from sim.core.ports.oauth import DeviceCode, OAuthError, OAuthToken

GRANT = "urn:ietf:params:oauth:grant-type:device_code"


def _default_post(url: str, form: dict) -> dict:
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Accept": "application/json", "User-Agent": "flight-sim"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        # GitLab answers 400/401 with a JSON error body while the code is pending
        try:
            body = json.loads(e.read().decode("utf-8") or "{}")
        except (ValueError, OSError):
            body = {}
        if isinstance(body, dict) and body.get("error"):
            return body
        raise OAuthError(f"GitLab returned {e.code}") from e
    except urllib.error.URLError as e:
        raise OAuthError(f"could not reach GitLab: {e.reason}") from e


class GitLabDeviceFlow:
    def __init__(self, base_url: str, client_id: str,
                 post: Optional[Callable[[str, dict], dict]] = None) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self._client_id = (client_id or "").strip()
        self._post = post or _default_post

    @property
    def configured(self) -> bool:
        return bool(self._client_id and self.base_url)

    @property
    def device_url(self) -> str:
        return self.base_url + "/oauth/authorize_device"

    @property
    def token_url(self) -> str:
        return self.base_url + "/oauth/token"

    def start(self, scope: str = "api") -> DeviceCode:
        if not self.configured:
            raise OAuthError("GitLab sign-in is not configured on this server "
                             "(GITLAB_URL + GITLAB_OAUTH_CLIENT_ID)")
        d = self._post(self.device_url, {"client_id": self._client_id, "scope": scope})
        if not d.get("device_code"):
            raise OAuthError(d.get("error_description") or d.get("error")
                             or "GitLab did not issue a device code")
        return DeviceCode(device_code=d["device_code"], user_code=d.get("user_code", ""),
                          verification_uri=d.get("verification_uri_complete")
                          or d.get("verification_uri") or (self.base_url + "/oauth/device"),
                          interval=int(d.get("interval") or 5),
                          expires_in=int(d.get("expires_in") or 300))

    def _token(self, d: dict) -> OAuthToken:
        return OAuthToken(access_token=d["access_token"], scope=d.get("scope", ""),
                          token_type=d.get("token_type", "bearer"),
                          refresh_token=d.get("refresh_token", ""),
                          expires_in=int(d.get("expires_in") or 0))

    def poll(self, device_code: str) -> Optional[OAuthToken]:
        d = self._post(self.token_url, {"client_id": self._client_id, "device_code": device_code,
                                        "grant_type": GRANT})
        if d.get("access_token"):
            return self._token(d)
        err = d.get("error", "")
        if err in ("authorization_pending", "slow_down"):
            return None
        if err == "expired_token":
            raise OAuthError("the code expired; start again")
        if err == "access_denied":
            raise OAuthError("you cancelled the sign-in on GitLab")
        raise OAuthError(d.get("error_description") or err or "GitLab did not issue a token")

    def refresh(self, refresh_token: str) -> OAuthToken:
        if not refresh_token:
            raise OAuthError("no refresh token; connect GitLab again")
        d = self._post(self.token_url, {"client_id": self._client_id, "refresh_token": refresh_token,
                                        "grant_type": "refresh_token"})
        if not d.get("access_token"):
            raise OAuthError(d.get("error_description") or d.get("error")
                             or "GitLab did not refresh the token; connect again")
        return self._token(d)
