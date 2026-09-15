from __future__ import annotations

from typing import Optional, Sequence


class InMemorySessionFileStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], str] = {}

    def put(self, session_id: str, relpath: str, text: str, ts: str) -> None:
        self._rows[(session_id, relpath)] = text

    def get(self, session_id: str, relpath: str) -> Optional[str]:
        return self._rows.get((session_id, relpath))

    def list(self, session_id: str) -> Sequence[str]:
        return sorted(p for (s, p) in self._rows if s == session_id)

    def delete_session(self, session_id: str) -> None:
        for k in [k for k in self._rows if k[0] == session_id]:
            del self._rows[k]
