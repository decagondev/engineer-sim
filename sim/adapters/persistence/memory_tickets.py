from __future__ import annotations

from typing import Optional, Sequence

from sim.core.ports.tickets import Ticket


class InMemoryTicketStore:
    def __init__(self) -> None:
        self._t: dict[tuple[str, str], Ticket] = {}
        self._seq = 0

    def create(self, session_id, title, description, status, created_by, ts, *,
               issue_type: str = "task", priority: str = "medium",
               labels: str = "") -> Ticket:
        self._seq += 1
        tid = f"k{self._seq}"
        t = Ticket(tid, session_id, title, description, status, created_by, ts,
                   self._seq, issue_type, priority, labels)
        self._t[(session_id, tid)] = t
        return t

    def get(self, session_id, ticket_id) -> Optional[Ticket]:
        return self._t.get((session_id, ticket_id))

    def list(self, session_id) -> Sequence[Ticket]:
        return [t for (s, _), t in self._t.items() if s == session_id]

    def update_status(self, session_id, ticket_id, status, ts) -> Optional[Ticket]:
        cur = self._t.get((session_id, ticket_id))
        if not cur:
            return None
        upd = Ticket(cur.id, cur.session_id, cur.title, cur.description,
                     status, cur.created_by, ts, cur.seq, cur.issue_type,
                     cur.priority, cur.labels)
        self._t[(session_id, ticket_id)] = upd
        return upd
