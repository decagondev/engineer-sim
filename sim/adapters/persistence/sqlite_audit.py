from __future__ import annotations

import sqlite3
from typing import Sequence

from sim.core.ports.audit import AuditEntry


class SqliteAuditLog:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
                target TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
                status INTEGER NOT NULL DEFAULT 200
            )
            """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS audit_ts ON audit_log(ts)")
        self._conn.commit()

    def append(self, entry: AuditEntry) -> AuditEntry:
        self._conn.execute(
            "INSERT INTO audit_log (ts, actor, action, target, summary, status) VALUES (?, ?, ?, ?, ?, ?)",
            (entry.ts, entry.actor, entry.action, entry.target, entry.summary, int(entry.status)))
        self._conn.commit()
        return entry

    def list(self, limit: int = 100, before: str = "") -> Sequence[AuditEntry]:
        if before:
            rows = self._conn.execute(
                "SELECT * FROM audit_log WHERE ts < ? ORDER BY ts DESC, id DESC LIMIT ?",
                (before, int(limit))).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM audit_log ORDER BY ts DESC, id DESC LIMIT ?", (int(limit),)).fetchall()
        return [AuditEntry(r["ts"], r["actor"], r["action"], r["target"] or "", r["summary"] or "",
                           int(r["status"])) for r in rows]
