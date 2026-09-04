from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from sim.core.ports.submissions import Submission


class SqliteSubmissionStore:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                session_id TEXT NOT NULL, seq INTEGER NOT NULL,
                filename TEXT NOT NULL, content TEXT NOT NULL,
                lines INTEGER NOT NULL, ts TEXT NOT NULL, kind TEXT DEFAULT 'patch',
                PRIMARY KEY (session_id, seq)
            )
            """)
        self._conn.commit()

    def save(self, session_id, filename, content, ts, kind="patch") -> Submission:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq),0)+1 FROM submissions WHERE session_id=?",
            (session_id,)).fetchone()
        seq = row[0]
        lines = content.count("\n") + 1
        self._conn.execute(
            "INSERT INTO submissions (session_id, seq, filename, content, lines, ts, kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, seq, filename, content, lines, ts, kind))
        self._conn.commit()
        return Submission(session_id, seq, filename, content, lines, ts, kind)

    def latest(self, session_id) -> Optional[Submission]:
        r = self._conn.execute(
            "SELECT * FROM submissions WHERE session_id=? ORDER BY seq DESC LIMIT 1",
            (session_id,)).fetchone()
        return self._row(r) if r else None

    def list(self, session_id) -> Sequence[Submission]:
        rows = self._conn.execute(
            "SELECT * FROM submissions WHERE session_id=? ORDER BY seq",
            (session_id,)).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(r) -> Submission:
        keys = r.keys()
        kind = r["kind"] if "kind" in keys and r["kind"] else "patch"
        return Submission(r["session_id"], r["seq"], r["filename"],
                          r["content"], r["lines"], r["ts"], kind)
