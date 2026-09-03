from __future__ import annotations


class InMemoryUnlockStore:
    """UnlockStore for tests."""

    def __init__(self) -> None:
        self._state: dict[tuple[str, str], int] = {}

    def get_unlocked(self, session_id: str, persona_key: str) -> int:
        return self._state.get((session_id, persona_key), 0)

    def set_unlocked(self, session_id: str, persona_key: str, count: int) -> None:
        self._state[(session_id, persona_key)] = count
