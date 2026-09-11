from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

ROLES = ("challenger", "instructor", "admin")


class IdentityError(Exception):
    """Invalid, expired, or missing identity token."""

    def __init__(self, detail: str = "unauthorized", status: int = 401) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class Principal:
    """Who is calling. Built only from a verified token + local directory."""

    uid: str
    email: str
    role: str = "challenger"          # challenger | instructor | admin
    disabled: bool = False
    email_verified: bool = False

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            object.__setattr__(self, "role", "challenger")


class IdentityVerifier(Protocol):
    """Turn a bearer token into a Principal. Adapters implement this (DIP)."""

    def verify(self, token: str) -> Principal: ...
