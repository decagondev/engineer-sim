from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass(frozen=True)
class StoredGrade:
    """The last grade computed for a session. One per session: a regrade
    replaces it, so dashboards and exports always show the latest verdict."""

    session_id: str
    total: float
    level: str
    ts: str                       # when it was graded (ISO-8601, UTC)
    graded_by: str = ""           # uid or label of whoever pressed Grade
    include_tickets: bool = False
    calibrated: bool = False
    body: dict = field(default_factory=dict)   # the full grade payload as returned by /grade


class GradeStore(Protocol):
    def save(self, grade: StoredGrade) -> StoredGrade: ...

    def get(self, session_id: str) -> Optional[StoredGrade]: ...

    def delete_for_session(self, session_id: str) -> None: ...
