from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Protocol, Sequence


@dataclass(frozen=True)
class AuditEntry:
    """One administrative write: who did what to which thing, and whether it
    succeeded. Append-only; never edited or deleted from the app."""

    ts: str
    actor: str            # email or uid
    action: str           # e.g. "POST /api/admin/users", or a route-supplied verb
    target: str = ""      # e.g. a uid, cohort id, session id
    summary: str = ""     # human sentence when the route supplies one
    status: int = 200

    def as_dict(self) -> dict:
        return asdict(self)


class AuditLog(Protocol):
    def append(self, entry: AuditEntry) -> AuditEntry: ...

    def list(self, limit: int = 100, before: str = "") -> Sequence[AuditEntry]:
        """Newest first; `before` is an ISO timestamp to page from."""
        ...
