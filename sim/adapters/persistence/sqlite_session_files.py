from __future__ import annotations

import sqlite3
from typing import Optional, Sequence


class SqliteSessionFileStore:
    """Browser-edited workspace files, one row per (session, path)."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_files (
                session_id TEXT NOT NULL,
                relpath TEXT NOT NULL,
                content TEXT NOT NULL,
                ts TEXT NOT NULL,
                PRIMARY KEY (session_id, relpath)
            )
            """)
        self._conn.commit()

    def put(self, session_id: str, relpath: str, text: str, ts: str) -> None:
        self._conn.execute(
            "INSERT INTO session_files (session_id, relpath, content, ts) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(session_id, relpath) DO UPDATE SET "
            "content=excluded.content, ts=excluded.ts",
            (session_id, relpath, text, ts))
        self._conn.commit()

    def get(self, session_id: str, relpath: str) -> Optional[str]:
        r = self._conn.execute(
            "SELECT content FROM session_files WHERE session_id=? AND relpath=?",
            (session_id, relpath)).fetchone()
        return r[0] if r else None

    def list(self, session_id: str) -> Sequence[str]:
        return [r[0] for r in self._conn.execute(
            "SELECT relpath FROM session_files WHERE session_id=? ORDER BY relpath",
            (session_id,))]

    def delete_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM session_files WHERE session_id=?", (session_id,))
        self._conn.commit()
