from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

STATUSES = ("todo", "doing", "done")


@dataclass(frozen=True)
class Ticket:
    id: str
    session_id: str
    title: str
    description: str
    status: str            # one of STATUSES
    created_by: str        # "tester", a persona key, or "system"
    ts: str


class TicketStore(Protocol):
    def create(self, session_id: str, title: str, description: str, status: str,
               created_by: str, ts: str) -> Ticket: ...

    def get(self, session_id: str, ticket_id: str) -> Optional[Ticket]: ...

    def list(self, session_id: str) -> Sequence[Ticket]: ...

    def update_status(self, session_id: str, ticket_id: str, status: str,
                      ts: str) -> Optional[Ticket]: ...
