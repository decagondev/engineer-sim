from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

SESSION_STATUSES = ("assigned", "active", "ended")


@dataclass(frozen=True)
class SessionRecord:
    id: str
    owner_uid: str = ""
    assignee_uid: str = ""
    scenario_key: str = ""
    level: str = ""
    status: str = "assigned"
    created_at: str = ""


class SessionRegistry(Protocol):
    """Sessions as first-class rows (exist before the first chat message)."""

    def get(self, session_id: str) -> Optional[SessionRecord]: ...

    def upsert(self, record: SessionRecord) -> SessionRecord: ...

    def list_all(self) -> Sequence[SessionRecord]: ...

    def list_by_owner(self, uid: str) -> Sequence[SessionRecord]: ...

    def list_by_assignee(self, uid: str) -> Sequence[SessionRecord]: ...

    def delete(self, session_id: str) -> bool: ...
