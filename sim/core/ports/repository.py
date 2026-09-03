from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class StoredMessage:
    session_id: str
    sender: str          # persona key, "tester", or "system"
    channel: str
    content: str
    ts: str              # ISO-8601 timestamp
    kind: str = "message"  # "message" | "event"
    id: int | None = None


class MessageWriter(Protocol):
    """Write side of the transcript (ISP: writers don't read)."""

    def append(self, message: StoredMessage) -> StoredMessage: ...


class MessageReader(Protocol):
    """Read side of the transcript (ISP: the grader depends only on this)."""

    def list_for_session(self, session_id: str) -> Sequence[StoredMessage]: ...
