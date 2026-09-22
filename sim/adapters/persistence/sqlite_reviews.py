from __future__ import annotations

import json
import sqlite3
from typing import Optional

from sim.core.grading.review import HumanReview


class SqliteReviewStore:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                session_id TEXT PRIMARY KEY,
                scores TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                reviewer TEXT NOT NULL DEFAULT '',
                ts TEXT NOT NULL
            )
            """)
        self._conn.commit()

    def save(self, review: HumanReview) -> HumanReview:
        self._conn.execute(
            "INSERT INTO reviews (session_id, scores, comment, reviewer, ts) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET scores=excluded.scores, comment=excluded.comment, "
            "reviewer=excluded.reviewer, ts=excluded.ts",
            (review.session_id, json.dumps(review.scores), review.comment, review.reviewer, review.ts))
        self._conn.commit()
        return review

    def get(self, session_id: str) -> Optional[HumanReview]:
        r = self._conn.execute("SELECT * FROM reviews WHERE session_id=?", (session_id,)).fetchone()
        if not r:
            return None
        try:
            scores = json.loads(r["scores"] or "{}")
        except ValueError:
            scores = {}
        return HumanReview(session_id=r["session_id"], scores=scores, comment=r["comment"] or "",
                           reviewer=r["reviewer"] or "", ts=r["ts"])

    def delete_for_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM reviews WHERE session_id=?", (session_id,))
        self._conn.commit()
