from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from sim.core.ports.cohorts import CohortRecord


class SqliteCohortDirectory:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cohorts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cohort_members (
                cohort_id TEXT NOT NULL,
                uid TEXT NOT NULL,
                PRIMARY KEY (cohort_id, uid)
            );
            """
        )
        self._conn.commit()

    def get(self, cohort_id: str) -> Optional[CohortRecord]:
        r = self._conn.execute(
            "SELECT * FROM cohorts WHERE id=?", (cohort_id,)).fetchone()
        return self._row(r) if r else None

    def upsert(self, cohort: CohortRecord) -> CohortRecord:
        existing = self.get(cohort.id)
        created = cohort.created_at or (existing.created_at if existing else "")
        self._conn.execute(
            "INSERT INTO cohorts (id, name, notes, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, notes=excluded.notes",
            (cohort.id, cohort.name, cohort.notes or "", created),
        )
        self._conn.commit()
        return self.get(cohort.id)

    def list(self) -> Sequence[CohortRecord]:
        rows = self._conn.execute(
            "SELECT * FROM cohorts ORDER BY name COLLATE NOCASE").fetchall()
        return [self._row(r) for r in rows]

    def delete(self, cohort_id: str) -> bool:
        self._conn.execute(
            "DELETE FROM cohort_members WHERE cohort_id=?", (cohort_id,))
        cur = self._conn.execute("DELETE FROM cohorts WHERE id=?", (cohort_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def members(self, cohort_id: str) -> Sequence[str]:
        rows = self._conn.execute(
            "SELECT uid FROM cohort_members WHERE cohort_id=? ORDER BY uid",
            (cohort_id,)).fetchall()
        return [r["uid"] for r in rows]

    def add_member(self, cohort_id: str, uid: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO cohort_members (cohort_id, uid) VALUES (?, ?)",
            (cohort_id, uid))
        self._conn.commit()

    def remove_member(self, cohort_id: str, uid: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM cohort_members WHERE cohort_id=? AND uid=?",
            (cohort_id, uid))
        self._conn.commit()
        return cur.rowcount > 0

    def cohorts_for(self, uid: str) -> Sequence[str]:
        rows = self._conn.execute(
            "SELECT cohort_id FROM cohort_members WHERE uid=?", (uid,)).fetchall()
        return [r["cohort_id"] for r in rows]

    def remove_user(self, uid: str) -> None:
        self._conn.execute("DELETE FROM cohort_members WHERE uid=?", (uid,))
        self._conn.commit()

    @staticmethod
    def _row(r) -> CohortRecord:
        return CohortRecord(
            id=r["id"], name=r["name"], notes=r["notes"] or "",
            created_at=r["created_at"] or "",
        )
