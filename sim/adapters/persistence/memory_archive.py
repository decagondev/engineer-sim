from __future__ import annotations

from typing import Optional, Sequence

from sim.core.ports.archive import ArchiveRecord


class InMemoryArchiveStore:
    def __init__(self) -> None:
        self._rows: dict[str, ArchiveRecord] = {}

    def put(self, record: ArchiveRecord) -> ArchiveRecord:
        import dataclasses
        record = dataclasses.replace(record, size=len(record.markdown.encode("utf-8")))
        self._rows[record.session_id] = record
        return record

    def get(self, session_id: str) -> Optional[ArchiveRecord]:
        return self._rows.get(session_id)

    def list(self) -> Sequence[ArchiveRecord]:
        rows = sorted(self._rows.values(), key=lambda r: r.ts, reverse=True)
        return [ArchiveRecord(**{**r.meta(), "markdown": ""}) for r in rows]
