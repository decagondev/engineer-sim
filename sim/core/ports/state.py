from __future__ import annotations

from typing import Protocol


class UnlockStore(Protocol):
    """Port: tracks how many reveal-ladder rungs each persona has unlocked in a
    session. Segregated from the message repository (ISP).
    """

    def get_unlocked(self, session_id: str, persona_key: str) -> int: ...

    def set_unlocked(self, session_id: str, persona_key: str, count: int) -> None: ...
