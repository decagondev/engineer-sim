from __future__ import annotations

from typing import Sequence

from sim.core.ports.audit import AuditEntry


class InMemoryAuditLog:
    def __init__(self) -> None:
        self._rows: list[AuditEntry] = []

    def append(self, entry: AuditEntry) -> AuditEntry:
        self._rows.append(entry)
        return entry

    def list(self, limit: int = 100, before: str = "") -> Sequence[AuditEntry]:
        rows = [r for r in self._rows if not before or r.ts < before]
        rows.sort(key=lambda r: r.ts, reverse=True)
        return rows[:limit]
