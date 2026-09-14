from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class UserRecord:
    uid: str
    email: str
    role: str
    disabled: bool = False
    created_at: str = ""
    last_login: str = ""
    name: str = ""
    groq_key_enc: str = ""


class UserDirectory(Protocol):
    """Local mirror of accounts so roles can be changed without a token refresh."""

    def get(self, uid: str) -> Optional[UserRecord]: ...

    def get_by_email(self, email: str) -> Optional[UserRecord]: ...

    def upsert(self, user: UserRecord) -> UserRecord: ...

    def list(self) -> Sequence[UserRecord]: ...

    def delete(self, uid: str) -> bool: ...

    def count_role(self, role: str) -> int: ...
