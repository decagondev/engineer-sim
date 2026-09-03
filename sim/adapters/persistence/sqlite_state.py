from __future__ import annotations

import sqlite3


class SqliteUnlockStore:
    """UnlockStore over the same SQLite file as the transcript (separate table)."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS unlock_state (
                session_id TEXT NOT NULL,
                persona_key TEXT NOT NULL,
                unlocked INTEGER NOT NULL,
                PRIMARY KEY (session_id, persona_key)
            )
            """
        )
        self._conn.commit()

    def get_unlocked(self, session_id: str, persona_key: str) -> int:
        row = self._conn.execute(
            "SELECT unlocked FROM unlock_state WHERE session_id=? AND persona_key=?",
            (session_id, persona_key),
        ).fetchone()
        return int(row[0]) if row else 0

    def set_unlocked(self, session_id: str, persona_key: str, count: int) -> None:
        self._conn.execute(
            "INSERT INTO unlock_state (session_id, persona_key, unlocked) "
            "VALUES (?, ?, ?) ON CONFLICT(session_id, persona_key) "
            "DO UPDATE SET unlocked=excluded.unlocked",
            (session_id, persona_key, count),
        )
        self._conn.commit()
