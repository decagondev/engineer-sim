from __future__ import annotations

import sqlite3
import uuid
from typing import Optional, Sequence

from sim.core.ports.tickets import Ticket


class SqliteTicketStore:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id TEXT NOT NULL, session_id TEXT NOT NULL,
                title TEXT NOT NULL, description TEXT NOT NULL,
                status TEXT NOT NULL, created_by TEXT NOT NULL, ts TEXT NOT NULL,
                seq INTEGER, PRIMARY KEY (session_id, id)
            )
            """)
        self._conn.commit()

    def create(self, session_id, title, description, status, created_by, ts) -> Ticket:
        tid = uuid.uuid4().hex[:8]
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq),0)+1 FROM tickets WHERE session_id=?",
            (session_id,)).fetchone()
        self._conn.execute(
            "INSERT INTO tickets (id,session_id,title,description,status,created_by,ts,seq)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (tid, session_id, title, description, status, created_by, ts, row[0]))
        self._conn.commit()
        return Ticket(tid, session_id, title, description, status, created_by, ts)

    def get(self, session_id, ticket_id) -> Optional[Ticket]:
        r = self._conn.execute(
            "SELECT * FROM tickets WHERE session_id=? AND id=?",
            (session_id, ticket_id)).fetchone()
        return self._row(r) if r else None

    def list(self, session_id) -> Sequence[Ticket]:
        rows = self._conn.execute(
            "SELECT * FROM tickets WHERE session_id=? ORDER BY seq", (session_id,)).fetchall()
        return [self._row(r) for r in rows]

    def update_status(self, session_id, ticket_id, status, ts) -> Optional[Ticket]:
        cur = self.get(session_id, ticket_id)
        if not cur:
            return None
        self._conn.execute(
            "UPDATE tickets SET status=?, ts=? WHERE session_id=? AND id=?",
            (status, ts, session_id, ticket_id))
        self._conn.commit()
        return Ticket(cur.id, cur.session_id, cur.title, cur.description,
                      status, cur.created_by, ts)

    @staticmethod
    def _row(r) -> Ticket:
        return Ticket(r["id"], r["session_id"], r["title"], r["description"],
                      r["status"], r["created_by"], r["ts"])
