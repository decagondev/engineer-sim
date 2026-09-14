from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class CohortRecord:
    id: str
    name: str
    notes: str = ""
    created_at: str = ""


class CohortDirectory(Protocol):
    """Named groups of users (a classroom intake, a hiring week, …)."""

    def get(self, cohort_id: str) -> Optional[CohortRecord]: ...

    def upsert(self, cohort: CohortRecord) -> CohortRecord: ...

    def list(self) -> Sequence[CohortRecord]: ...

    def delete(self, cohort_id: str) -> bool: ...

    def members(self, cohort_id: str) -> Sequence[str]: ...

    def add_member(self, cohort_id: str, uid: str) -> None: ...

    def remove_member(self, cohort_id: str, uid: str) -> bool: ...

    def cohorts_for(self, uid: str) -> Sequence[str]: ...

    def remove_user(self, uid: str) -> None: ...
