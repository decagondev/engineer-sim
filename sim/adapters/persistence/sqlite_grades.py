from __future__ import annotations

import json
import sqlite3
from typing import Optional

from sim.core.ports.grades import StoredGrade


class SqliteGradeStore:
    """One row per session; a regrade overwrites it."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS grades (
                session_id TEXT PRIMARY KEY,
                total REAL NOT NULL,
                level TEXT NOT NULL DEFAULT '',
                ts TEXT NOT NULL,
                graded_by TEXT NOT NULL DEFAULT '',
                include_tickets INTEGER NOT NULL DEFAULT 0,
                calibrated INTEGER NOT NULL DEFAULT 0,
                body TEXT NOT NULL
            )
            """)
        self._conn.commit()

    def save(self, grade: StoredGrade) -> StoredGrade:
        self._conn.execute(
            "INSERT INTO grades (session_id, total, level, ts, graded_by, include_tickets, calibrated, body) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
            "total=excluded.total, level=excluded.level, ts=excluded.ts, graded_by=excluded.graded_by, "
            "include_tickets=excluded.include_tickets, calibrated=excluded.calibrated, body=excluded.body",
            (grade.session_id, float(grade.total), grade.level, grade.ts, grade.graded_by,
             1 if grade.include_tickets else 0, 1 if grade.calibrated else 0,
             json.dumps(grade.body)))
        self._conn.commit()
        return grade

    def get(self, session_id: str) -> Optional[StoredGrade]:
        r = self._conn.execute("SELECT * FROM grades WHERE session_id=?", (session_id,)).fetchone()
        if not r:
            return None
        try:
            body = json.loads(r["body"] or "{}")
        except ValueError:
            body = {}
        return StoredGrade(session_id=r["session_id"], total=float(r["total"]), level=r["level"] or "",
                           ts=r["ts"], graded_by=r["graded_by"] or "",
                           include_tickets=bool(r["include_tickets"]), calibrated=bool(r["calibrated"]),
                           body=body)

    def delete_for_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM grades WHERE session_id=?", (session_id,))
        self._conn.commit()
