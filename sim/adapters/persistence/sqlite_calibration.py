from __future__ import annotations

import json
import sqlite3
from typing import Optional

from sim.core.ports.calibration import CalibrationRun


class SqliteCalibrationRunStore:
    """Every run is kept; latest() is the newest by start time."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calibration_runs (
                id TEXT PRIMARY KEY,
                started TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """)
        self._conn.commit()

    def save(self, run: CalibrationRun) -> CalibrationRun:
        self._conn.execute(
            "INSERT INTO calibration_runs (id, started, status, payload) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload",
            (run.id, run.started, run.status, json.dumps(run.as_dict())))
        self._conn.commit()
        return run

    def latest(self) -> Optional[CalibrationRun]:
        r = self._conn.execute(
            "SELECT payload FROM calibration_runs ORDER BY started DESC LIMIT 1").fetchone()
        if not r:
            return None
        try:
            return CalibrationRun(**json.loads(r["payload"]))
        except (ValueError, TypeError):
            return None
