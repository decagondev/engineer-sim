from __future__ import annotations

from typing import Optional

from sim.core.ports.grades import StoredGrade


class InMemoryGradeStore:
    def __init__(self) -> None:
        self._rows: dict[str, StoredGrade] = {}

    def save(self, grade: StoredGrade) -> StoredGrade:
        self._rows[grade.session_id] = grade
        return grade

    def get(self, session_id: str) -> Optional[StoredGrade]:
        return self._rows.get(session_id)

    def delete_for_session(self, session_id: str) -> None:
        self._rows.pop(session_id, None)
