from __future__ import annotations

from typing import Optional, Sequence

from sim.core.ports.mail import MailStore, MailThread


class InMemoryMailStore:
    """MailStore for tests."""

    def __init__(self) -> None:
        self._threads: dict[tuple[str, str], MailThread] = {}
        self._read: dict[tuple[str, str], str] = {}
        self._persona: dict[tuple[str, str], str] = {}
        self._seq = 0

    def create_thread(self, session_id, subject, participant, ts) -> MailThread:
        self._seq += 1
        tid = f"t{self._seq}"
        th = MailThread(tid, session_id, subject, participant, ts)
        self._threads[(session_id, tid)] = th
        return th

    def get_thread(self, session_id, thread_id) -> Optional[MailThread]:
        return self._threads.get((session_id, thread_id))

    def list_threads(self, session_id) -> Sequence[MailThread]:
        return [t for (s, _), t in self._threads.items() if s == session_id]

    def mark_read(self, session_id, thread_id, ts) -> None:
        self._read[(session_id, thread_id)] = ts

    def touch_persona(self, session_id, thread_id, ts) -> None:
        self._persona[(session_id, thread_id)] = ts

    def unread_count(self, session_id) -> int:
        n = 0
        for (s, tid) in self._threads:
            if s != session_id:
                continue
            p = self._persona.get((s, tid), "")
            r = self._read.get((s, tid), "")
            if p and p > r:
                n += 1
        return n
