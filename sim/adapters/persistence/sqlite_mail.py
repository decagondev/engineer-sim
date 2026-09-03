from __future__ import annotations

import sqlite3
import uuid
from typing import Optional, Sequence

from sim.core.ports.mail import MailThread


class SqliteMailStore:
    """MailStore over the same SQLite file as the transcript (separate table)."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mail_threads (
                id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                participant TEXT NOT NULL,
                created_ts TEXT NOT NULL,
                last_persona_ts TEXT DEFAULT '',
                last_read_ts TEXT DEFAULT '',
                PRIMARY KEY (session_id, id)
            )
            """
        )
        self._conn.commit()

    def create_thread(self, session_id, subject, participant, ts) -> MailThread:
        tid = uuid.uuid4().hex[:8]
        self._conn.execute(
            "INSERT INTO mail_threads (id, session_id, subject, participant, created_ts)"
            " VALUES (?, ?, ?, ?, ?)",
            (tid, session_id, subject, participant, ts),
        )
        self._conn.commit()
        return MailThread(tid, session_id, subject, participant, ts)

    def get_thread(self, session_id, thread_id) -> Optional[MailThread]:
        r = self._conn.execute(
            "SELECT * FROM mail_threads WHERE session_id=? AND id=?",
            (session_id, thread_id),
        ).fetchone()
        return self._row(r) if r else None

    def list_threads(self, session_id) -> Sequence[MailThread]:
        rows = self._conn.execute(
            "SELECT * FROM mail_threads WHERE session_id=? ORDER BY created_ts",
            (session_id,),
        ).fetchall()
        return [self._row(r) for r in rows]

    def mark_read(self, session_id, thread_id, ts) -> None:
        self._conn.execute(
            "UPDATE mail_threads SET last_read_ts=? WHERE session_id=? AND id=?",
            (ts, session_id, thread_id))
        self._conn.commit()

    def touch_persona(self, session_id, thread_id, ts) -> None:
        self._conn.execute(
            "UPDATE mail_threads SET last_persona_ts=? WHERE session_id=? AND id=?",
            (ts, session_id, thread_id))
        self._conn.commit()

    def unread_count(self, session_id) -> int:
        r = self._conn.execute(
            "SELECT COUNT(*) FROM mail_threads WHERE session_id=? "
            "AND last_persona_ts != '' AND last_persona_ts > last_read_ts",
            (session_id,)).fetchone()
        return int(r[0])

    @staticmethod
    def _row(r) -> MailThread:
        return MailThread(r["id"], r["session_id"], r["subject"],
                          r["participant"], r["created_ts"])
