from __future__ import annotations

import sqlite3
from typing import Sequence

from sim.core.ports.repository import StoredMessage


class SqliteMessageRepository:
    """MessageWriter + MessageReader over a single SQLite file (zero infra)."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                channel TEXT NOT NULL,
                content TEXT NOT NULL,
                ts TEXT NOT NULL,
                kind TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def append(self, message: StoredMessage) -> StoredMessage:
        cur = self._conn.execute(
            "INSERT INTO messages (session_id, sender, channel, content, ts, kind)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (message.session_id, message.sender, message.channel,
             message.content, message.ts, message.kind),
        )
        self._conn.commit()
        return StoredMessage(
            id=cur.lastrowid, session_id=message.session_id, sender=message.sender,
            channel=message.channel, content=message.content, ts=message.ts,
            kind=message.kind,
        )

    def list_sessions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT session_id, COUNT(*) c, MIN(ts) first_ts, MAX(ts) last_ts "
            "FROM messages GROUP BY session_id ORDER BY last_ts DESC"
        ).fetchall()
        return [{"session_id": r["session_id"], "count": r["c"],
                 "first_ts": r["first_ts"], "last_ts": r["last_ts"]} for r in rows]

    def list_for_session(self, session_id: str) -> Sequence[StoredMessage]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [
            StoredMessage(
                id=r["id"], session_id=r["session_id"], sender=r["sender"],
                channel=r["channel"], content=r["content"], ts=r["ts"],
                kind=r["kind"],
            )
            for r in rows
        ]
