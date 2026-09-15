from __future__ import annotations

import sqlite3
from typing import Optional

from sim.core.ports.settings import InstructorSettings


class SqliteSettingsStore:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS instructor_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                onboarded INTEGER NOT NULL DEFAULT 0,
                default_level TEXT NOT NULL DEFAULT 'senior'
            );
            CREATE TABLE IF NOT EXISTS session_settings (
                session_id TEXT PRIMARY KEY,
                level TEXT,
                scenario TEXT
            );
            CREATE TABLE IF NOT EXISTS scenario_config (
                scenario_key TEXT PRIMARY KEY,
                starter_url TEXT,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            """)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(scenario_config)")}
        if "enabled" not in cols:
            self._conn.execute(
                "ALTER TABLE scenario_config ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(session_settings)")}
        if "repo_url" not in cols:
            self._conn.execute("ALTER TABLE session_settings ADD COLUMN repo_url TEXT")

    def get_instructor(self) -> InstructorSettings:
        r = self._conn.execute(
            "SELECT onboarded, default_level FROM instructor_settings WHERE id=1"
        ).fetchone()
        if not r:
            return InstructorSettings()
        return InstructorSettings(bool(r["onboarded"]), r["default_level"])

    def set_instructor(self, settings: InstructorSettings) -> None:
        self._conn.execute(
            "INSERT INTO instructor_settings (id, onboarded, default_level) "
            "VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "onboarded=excluded.onboarded, default_level=excluded.default_level",
            (1 if settings.onboarded else 0, settings.default_level))
        self._conn.commit()

    def get_session_level(self, session_id: str) -> Optional[str]:
        r = self._conn.execute(
            "SELECT level FROM session_settings WHERE session_id=?",
            (session_id,)).fetchone()
        return r["level"] if r else None

    def set_session_level(self, session_id: str, level: str) -> None:
        self._conn.execute(
            "INSERT INTO session_settings (session_id, level) VALUES (?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET level=excluded.level",
            (session_id, level))
        self._conn.commit()

    def get_session_scenario(self, session_id: str):
        r = self._conn.execute(
            "SELECT scenario FROM session_settings WHERE session_id=?",
            (session_id,)).fetchone()
        return r["scenario"] if r and r["scenario"] else None

    def set_session_scenario(self, session_id: str, scenario_key: str) -> None:
        self._conn.execute(
            "INSERT INTO session_settings (session_id, scenario) VALUES (?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET scenario=excluded.scenario",
            (session_id, scenario_key))
        self._conn.commit()

    def get_session_repo_url(self, session_id: str):
        r = self._conn.execute(
            "SELECT repo_url FROM session_settings WHERE session_id=?",
            (session_id,)).fetchone()
        return r["repo_url"] if r and r["repo_url"] else None

    def set_session_repo_url(self, session_id: str, url: str) -> None:
        self._conn.execute(
            "INSERT INTO session_settings (session_id, repo_url) VALUES (?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET repo_url=excluded.repo_url",
            (session_id, url))
        self._conn.commit()

    def get_scenario_starter_url(self, scenario_key: str):
        r = self._conn.execute(
            "SELECT starter_url FROM scenario_config WHERE scenario_key=?",
            (scenario_key,)).fetchone()
        return r["starter_url"] if r and r["starter_url"] else None

    def set_scenario_starter_url(self, scenario_key: str, url: str) -> None:
        self._conn.execute(
            "INSERT INTO scenario_config (scenario_key, starter_url) VALUES (?, ?) "
            "ON CONFLICT(scenario_key) DO UPDATE SET starter_url=excluded.starter_url",
            (scenario_key, url))
        self._conn.commit()

    def all_scenario_config(self) -> dict:
        out = {}
        for r in self._conn.execute("SELECT scenario_key, starter_url, enabled FROM scenario_config"):
            out[r["scenario_key"]] = {"starter_url": r["starter_url"] or None,
                                      "enabled": bool(r["enabled"]) if r["enabled"] is not None else True}
        return out

    def get_scenario_enabled(self, scenario_key: str) -> bool:
        r = self._conn.execute(
            "SELECT enabled FROM scenario_config WHERE scenario_key=?",
            (scenario_key,)).fetchone()
        if not r:
            return True
        return bool(r["enabled"]) if "enabled" in r.keys() else True

    def set_scenario_enabled(self, scenario_key: str, enabled: bool) -> None:
        url = self.get_scenario_starter_url(scenario_key) or ""
        self._conn.execute(
            "INSERT INTO scenario_config (scenario_key, starter_url, enabled) VALUES (?, ?, ?) "
            "ON CONFLICT(scenario_key) DO UPDATE SET enabled=excluded.enabled",
            (scenario_key, url, 1 if enabled else 0))
        self._conn.commit()

    def delete_session_settings(self, session_id: str) -> None:
        self._conn.execute(
            "DELETE FROM session_settings WHERE session_id=?", (session_id,))
        self._conn.commit()
