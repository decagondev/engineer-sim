from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional, Sequence

from sim.core.ports.session_registry import SessionRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteSessionRegistry:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_registry (
                id TEXT PRIMARY KEY,
                owner_uid TEXT NOT NULL DEFAULT '',
                assignee_uid TEXT NOT NULL DEFAULT '',
                scenario_key TEXT NOT NULL DEFAULT '',
                level TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'assigned',
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, session_id: str) -> Optional[SessionRecord]:
        r = self._conn.execute(
            "SELECT * FROM session_registry WHERE id=?", (session_id,)
        ).fetchone()
        return self._row(r) if r else None

    def upsert(self, record: SessionRecord) -> SessionRecord:
        existing = self.get(record.id)
        created = record.created_at or (existing.created_at if existing else _now())
        self._conn.execute(
            "INSERT INTO session_registry "
            "(id, owner_uid, assignee_uid, scenario_key, level, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "owner_uid=excluded.owner_uid, assignee_uid=excluded.assignee_uid, "
            "scenario_key=excluded.scenario_key, level=excluded.level, "
            "status=excluded.status",
            (record.id, record.owner_uid, record.assignee_uid, record.scenario_key,
             record.level, record.status or "assigned", created),
        )
        self._conn.commit()
        return self.get(record.id)

    def list_all(self) -> Sequence[SessionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM session_registry ORDER BY created_at DESC"
        ).fetchall()
        return [self._row(r) for r in rows]

    def list_by_owner(self, uid: str) -> Sequence[SessionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM session_registry WHERE owner_uid=? ORDER BY created_at DESC",
            (uid,)).fetchall()
        return [self._row(r) for r in rows]

    def list_by_assignee(self, uid: str) -> Sequence[SessionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM session_registry WHERE assignee_uid=? ORDER BY created_at DESC",
            (uid,)).fetchall()
        return [self._row(r) for r in rows]

    def delete(self, session_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM session_registry WHERE id=?", (session_id,))
        self._conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def _row(r) -> SessionRecord:
        return SessionRecord(
            id=r["id"], owner_uid=r["owner_uid"] or "",
            assignee_uid=r["assignee_uid"] or "",
            scenario_key=r["scenario_key"] or "",
            level=r["level"] or "",
            status=r["status"] or "assigned",
            created_at=r["created_at"] or "",
        )


class InMemorySessionRegistry:
    def __init__(self) -> None:
        self._rows: dict[str, SessionRecord] = {}

    def get(self, session_id: str) -> Optional[SessionRecord]:
        return self._rows.get(session_id)

    def upsert(self, record: SessionRecord) -> SessionRecord:
        existing = self._rows.get(record.id)
        if existing:
            record = SessionRecord(
                id=record.id,
                owner_uid=record.owner_uid or existing.owner_uid,
                assignee_uid=record.assignee_uid or existing.assignee_uid,
                scenario_key=record.scenario_key or existing.scenario_key,
                level=record.level or existing.level,
                status=record.status or existing.status,
                created_at=existing.created_at or record.created_at,
            )
        elif not record.created_at:
            record = SessionRecord(
                id=record.id, owner_uid=record.owner_uid,
                assignee_uid=record.assignee_uid, scenario_key=record.scenario_key,
                level=record.level, status=record.status or "assigned",
                created_at=_now())
        self._rows[record.id] = record
        return record

    def list_all(self) -> Sequence[SessionRecord]:
        return list(self._rows.values())

    def list_by_owner(self, uid: str) -> Sequence[SessionRecord]:
        return [r for r in self._rows.values() if r.owner_uid == uid]

    def list_by_assignee(self, uid: str) -> Sequence[SessionRecord]:
        return [r for r in self._rows.values() if r.assignee_uid == uid]

    def delete(self, session_id: str) -> bool:
        return self._rows.pop(session_id, None) is not None
