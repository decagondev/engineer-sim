from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class MailThread:
    """Metadata for an email thread. Bodies live in the message repository
    (channel `mail:<id>`, kind 'email') so they're part of the graded transcript.
    """

    id: str
    session_id: str
    subject: str
    participant: str        # the persona key on the other end
    created_ts: str


class MailStore(Protocol):
    """Port: thread metadata + read state. Segregated from the message repo (ISP)."""

    def create_thread(self, session_id: str, subject: str, participant: str,
                      ts: str) -> MailThread: ...

    def get_thread(self, session_id: str, thread_id: str) -> Optional[MailThread]: ...

    def list_threads(self, session_id: str) -> Sequence[MailThread]: ...

    def mark_read(self, session_id: str, thread_id: str, ts: str) -> None: ...

    def touch_persona(self, session_id: str, thread_id: str, ts: str) -> None: ...

    def unread_count(self, session_id: str) -> int: ...
