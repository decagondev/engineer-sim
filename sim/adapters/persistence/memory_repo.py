from __future__ import annotations

from typing import Sequence

from sim.core.ports.repository import StoredMessage


class InMemoryMessageRepository:
    """MessageWriter + MessageReader for tests. Auto-increments ids."""

    def __init__(self) -> None:
        self._rows: list[StoredMessage] = []

    def append(self, message: StoredMessage) -> StoredMessage:
        stored = StoredMessage(
            id=len(self._rows) + 1, session_id=message.session_id,
            sender=message.sender, channel=message.channel,
            content=message.content, ts=message.ts, kind=message.kind,
        )
        self._rows.append(stored)
        return stored

    def list_for_session(self, session_id: str) -> Sequence[StoredMessage]:
        return [m for m in self._rows if m.session_id == session_id]
