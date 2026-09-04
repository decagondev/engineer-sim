from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from sim.core.ports.repository import MessageWriter, StoredMessage
from sim.core.ports.tickets import ISSUE_TYPES, PRIORITIES, STATUSES, Ticket, TicketStore


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_prefix(scenario_key: str) -> str:
    parts = [p for p in (scenario_key or "sim").replace("-", "_").split("_") if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return (parts[0][:3] if parts else "SIM").upper()


def _norm_labels(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):
        parts = [str(x).strip() for x in raw]
    else:
        parts = str(raw).split(",")
    return ",".join(p for p in parts if p)


def _norm_type(raw: str | None, default: str) -> str:
    v = (raw or default).strip().lower()
    return v if v in ISSUE_TYPES else default


def _norm_priority(raw: str | None, default: str) -> str:
    v = (raw or default).strip().lower()
    return v if v in PRIORITIES else default


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
    project_key: str = "SIM"
    clock: Callable[[], str] = _utcnow_iso

    def seed(self, session_id: str) -> None:
        """Create any missing seed tickets. Idempotent by title, so it can't be
        blocked by a director-filed ticket arriving first."""
        if not self.seed_tickets:
            return
        existing = {t.title for t in self.store.list(session_id)}
        for s in self.seed_tickets:
            if s["title"] not in existing:
                self.store.create(
                    session_id, s["title"], s.get("description", ""),
                    s.get("status", "todo"), s.get("created_by", "system"),
                    self.clock(),
                    issue_type=_norm_type(s.get("issue_type") or s.get("kind"), "task"),
                    priority=_norm_priority(s.get("priority"), "medium"),
                    labels=_norm_labels(s.get("labels", "")),
                )

    def board(self, session_id: str) -> dict:
        self.seed(session_id)
        tickets = list(self.store.list(session_id))
        cols = {k: [] for k in STATUSES}
        for t in tickets:
            cols.get(t.status, cols["todo"]).append(self._dto(t))
        return {"columns": [{"status": s, "tickets": cols[s]} for s in STATUSES],
                "project": self.project_key}

    def file_from(self, session_id: str, title: str, description: str,
                  created_by: str, issue_type: str = "story",
                  priority: str = "high", labels: str = "scope-creep") -> Ticket:
        """A persona (via the director) files a ticket — scope creep."""
        t = self.store.create(
            session_id, title, description, "todo", created_by, self.clock(),
            issue_type=_norm_type(issue_type, "story"),
            priority=_norm_priority(priority, "high"),
            labels=_norm_labels(labels) or "scope-creep",
        )
        self._record(session_id, f"{self._name(created_by)} filed a ticket: {title}",
                     sender=created_by)
        return t

    def create(self, session_id: str, title: str, description: str,
               issue_type: str = "task", priority: str = "medium",
               labels: str = "") -> Ticket:
        t = self.store.create(
            session_id, title, description, "todo", "tester", self.clock(),
            issue_type=_norm_type(issue_type, "task"),
            priority=_norm_priority(priority, "medium"),
            labels=_norm_labels(labels),
        )
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
        labels = [x for x in (t.labels or "").split(",") if x]
        return {
            "id": t.id,
            "key": f"{self.project_key}-{t.seq}",
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "created_by": t.created_by,
            "by_name": (p.name if p else ("You" if t.created_by == "tester" else t.created_by)),
            "issue_type": t.issue_type or "task",
            "priority": t.priority or "medium",
            "labels": labels,
            "ts": t.ts,
        }

    def _record(self, session_id: str, text: str, sender: str = "tester") -> None:
        self.writer.append(StoredMessage(
            session_id=session_id, sender=sender, channel="tickets",
            content=text, ts=self.clock(), kind="ticket"))
