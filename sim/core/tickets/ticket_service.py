from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from sim.core.ports.repository import MessageWriter, StoredMessage
from sim.core.ports.tickets import STATUSES, Ticket, TicketStore


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TicketService:
    """A lightweight issue board. Scenario-seeded; the tester reshapes and moves
    tickets. Create/move are recorded in the transcript (kind 'ticket') so the
    grader can see how the engineer scoped the work.
    """

    store: TicketStore
    writer: MessageWriter
    cast: dict
    seed_tickets: tuple = field(default_factory=tuple)
    clock: Callable[[], str] = _utcnow_iso

    def seed(self, session_id: str) -> None:
        """Create any missing seed tickets. Idempotent by title, so it can't be
        blocked by a director-filed ticket arriving first."""
        if not self.seed_tickets:
            return
        existing = {t.title for t in self.store.list(session_id)}
        for s in self.seed_tickets:
            if s["title"] not in existing:
                self.store.create(session_id, s["title"], s.get("description", ""),
                                  s.get("status", "todo"), s.get("created_by", "system"),
                                  self.clock())

    def board(self, session_id: str) -> dict:
        self.seed(session_id)
        tickets = list(self.store.list(session_id))
        cols = {k: [] for k in STATUSES}
        for t in tickets:
            cols.get(t.status, cols["todo"]).append(self._dto(t))
        return {"columns": [{"status": s, "tickets": cols[s]} for s in STATUSES]}

    def file_from(self, session_id: str, title: str, description: str,
                  created_by: str) -> Ticket:
        """A persona (via the director) files a ticket — scope creep."""
        t = self.store.create(session_id, title, description, "todo",
                              created_by, self.clock())
        self._record(session_id, f"{self._name(created_by)} filed a ticket: {title}",
                     sender=created_by)
        return t

    def create(self, session_id: str, title: str, description: str) -> Ticket:
        t = self.store.create(session_id, title, description, "todo", "tester",
                              self.clock())
        self._record(session_id, f"created ticket: {title}")
        return t

    def move(self, session_id: str, ticket_id: str, status: str) -> Ticket | None:
        if status not in STATUSES:
            raise ValueError(f"bad status {status!r}")
        t = self.store.update_status(session_id, ticket_id, status, self.clock())
        if t:
            self._record(session_id, f"moved ticket '{t.title}' -> {status}")
        return t

    def _name(self, key: str) -> str:
        p = self.cast.get(key)
        return p.name if p else key

    def _dto(self, t: Ticket) -> dict:
        p = self.cast.get(t.created_by)
        return {"id": t.id, "title": t.title, "description": t.description,
                "status": t.status, "created_by": t.created_by,
                "by_name": (p.name if p else ("You" if t.created_by == "tester" else t.created_by))}

    def _record(self, session_id: str, text: str, sender: str = "tester") -> None:
        self.writer.append(StoredMessage(
            session_id=session_id, sender=sender, channel="tickets",
            content=text, ts=self.clock(), kind="ticket"))
