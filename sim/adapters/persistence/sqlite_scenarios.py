from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from sim.core.ports.scenarios import ScenarioOverride


class SqliteScenarioStore:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scenario_overrides (
                key TEXT PRIMARY KEY, yaml_text TEXT NOT NULL, ts TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT '', based_on TEXT NOT NULL DEFAULT ''
            )
            """)
        self._conn.commit()

    def put(self, override: ScenarioOverride) -> ScenarioOverride:
        self._conn.execute(
            "INSERT INTO scenario_overrides (key, yaml_text, ts, author, based_on) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET yaml_text=excluded.yaml_text, ts=excluded.ts, "
            "author=excluded.author, based_on=excluded.based_on",
            (override.key, override.yaml_text, override.ts, override.author, override.based_on))
        self._conn.commit()
        return override

    def get(self, key: str) -> Optional[ScenarioOverride]:
        r = self._conn.execute("SELECT * FROM scenario_overrides WHERE key=?", (key,)).fetchone()
        return self._row(r) if r else None

    def list(self) -> Sequence[ScenarioOverride]:
        return [self._row(r) for r in self._conn.execute(
            "SELECT * FROM scenario_overrides ORDER BY key")]

    def delete(self, key: str) -> bool:
        cur = self._conn.execute("DELETE FROM scenario_overrides WHERE key=?", (key,))
        self._conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def _row(r) -> ScenarioOverride:
        return ScenarioOverride(key=r["key"], yaml_text=r["yaml_text"], ts=r["ts"],
                                author=r["author"] or "", based_on=r["based_on"] or "")
