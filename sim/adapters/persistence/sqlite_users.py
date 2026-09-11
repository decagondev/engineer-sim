from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional, Sequence

from sim.core.ports.users import UserRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteUserDirectory:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                uid TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_login TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.commit()

    def get(self, uid: str) -> Optional[UserRecord]:
        r = self._conn.execute(
            "SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
        return self._row(r) if r else None

    def get_by_email(self, email: str) -> Optional[UserRecord]:
        r = self._conn.execute(
            "SELECT * FROM users WHERE lower(email)=lower(?)",
            (email or "",)).fetchone()
        return self._row(r) if r else None

    def upsert(self, user: UserRecord) -> UserRecord:
        existing = self.get(user.uid) or (
            self.get_by_email(user.email) if user.email else None)
        now = user.created_at or _now()
        if existing and existing.uid != user.uid and user.email:
            # email already owned by another uid
            pass
        created = user.created_at or (existing.created_at if existing else now)
        last = user.last_login or (existing.last_login if existing else "")
        self._conn.execute(
            "INSERT INTO users (uid, email, role, disabled, created_at, last_login) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(uid) DO UPDATE SET "
            "email=excluded.email, role=excluded.role, disabled=excluded.disabled, "
            "last_login=excluded.last_login",
            (user.uid, user.email, user.role, 1 if user.disabled else 0,
             created, last),
        )
        self._conn.commit()
        return self.get(user.uid)

    def list(self) -> Sequence[UserRecord]:
        rows = self._conn.execute(
            "SELECT * FROM users ORDER BY email").fetchall()
        return [self._row(r) for r in rows]

    def delete(self, uid: str) -> bool:
        cur = self._conn.execute("DELETE FROM users WHERE uid=?", (uid,))
        self._conn.commit()
        return cur.rowcount > 0

    def count_role(self, role: str) -> int:
        r = self._conn.execute(
            "SELECT COUNT(*) c FROM users WHERE role=? AND disabled=0",
            (role,)).fetchone()
        return int(r["c"] if r else 0)

    @staticmethod
    def _row(r) -> UserRecord:
        return UserRecord(
            uid=r["uid"], email=r["email"], role=r["role"],
            disabled=bool(r["disabled"]), created_at=r["created_at"] or "",
            last_login=r["last_login"] or "",
        )


class InMemoryUserDirectory:
    def __init__(self) -> None:
        self._by_uid: dict[str, UserRecord] = {}

    def get(self, uid: str) -> Optional[UserRecord]:
        return self._by_uid.get(uid)

    def get_by_email(self, email: str) -> Optional[UserRecord]:
        el = (email or "").lower()
        for u in self._by_uid.values():
            if u.email.lower() == el:
                return u
        return None

    def upsert(self, user: UserRecord) -> UserRecord:
        self._by_uid[user.uid] = user
        return user

    def list(self) -> Sequence[UserRecord]:
        return sorted(self._by_uid.values(), key=lambda u: u.email)

    def delete(self, uid: str) -> bool:
        return self._by_uid.pop(uid, None) is not None

    def count_role(self, role: str) -> int:
        return sum(1 for u in self._by_uid.values()
                   if u.role == role and not u.disabled)
