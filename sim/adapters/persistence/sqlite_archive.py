from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from sim.core.ports.archive import ArchiveRecord


class SqliteArchiveStore:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS archives (
                session_id TEXT PRIMARY KEY, ts TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '', scenario TEXT NOT NULL DEFAULT '',
                assignee TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '',
                size INTEGER NOT NULL DEFAULT 0, markdown TEXT NOT NULL
            )
            """)
        self._conn.commit()

    def put(self, record: ArchiveRecord) -> ArchiveRecord:
        self._conn.execute(
            "INSERT INTO archives (session_id, ts, title, scenario, assignee, state, size, markdown) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET ts=excluded.ts, "
            "title=excluded.title, scenario=excluded.scenario, assignee=excluded.assignee, "
            "state=excluded.state, size=excluded.size, markdown=excluded.markdown",
            (record.session_id, record.ts, record.title, record.scenario, record.assignee,
             record.state, len(record.markdown.encode("utf-8")), record.markdown))
        self._conn.commit()
        return record

    def get(self, session_id: str) -> Optional[ArchiveRecord]:
        r = self._conn.execute("SELECT * FROM archives WHERE session_id=?", (session_id,)).fetchone()
        return self._row(r, with_markdown=True) if r else None

    def list(self) -> Sequence[ArchiveRecord]:
        rows = self._conn.execute(
            "SELECT session_id, ts, title, scenario, assignee, state, size FROM archives ORDER BY ts DESC").fetchall()
        return [self._row(r, with_markdown=False) for r in rows]

    @staticmethod
    def _row(r, with_markdown: bool) -> ArchiveRecord:
        return ArchiveRecord(session_id=r["session_id"], ts=r["ts"], title=r["title"] or "",
                             scenario=r["scenario"] or "", assignee=r["assignee"] or "",
                             state=r["state"] or "", size=int(r["size"] or 0),
                             markdown=(r["markdown"] if with_markdown else ""))
