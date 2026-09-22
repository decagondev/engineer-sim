from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class DeviceCode:
    """What the user is shown: a short code to type at a URL."""

    device_code: str
    user_code: str
    verification_uri: str
    interval: int = 5          # seconds between polls
    expires_in: int = 900


@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    scope: str = ""
    token_type: str = "bearer"


class OAuthBroker(Protocol):
    """Device-flow sign-in with a third party (GitHub). start() returns a
    code for the user; poll() returns the token once they approve, None while
    pending, and raises OAuthError when the code expired or was denied."""

    def start(self, scope: str) -> DeviceCode: ...

    def poll(self, device_code: str) -> Optional[OAuthToken]: ...


class OAuthError(RuntimeError):
    """The device flow ended without a token (expired, denied, misconfigured)."""
