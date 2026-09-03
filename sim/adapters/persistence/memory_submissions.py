from __future__ import annotations

from typing import Optional, Sequence

from sim.core.ports.submissions import Submission


class InMemorySubmissionStore:
    def __init__(self) -> None:
        self._rows: list[Submission] = []

    def save(self, session_id, filename, content, ts) -> Submission:
        seq = 1 + sum(1 for r in self._rows if r.session_id == session_id)
        s = Submission(session_id, seq, filename, content,
                       content.count("\n") + 1, ts)
        self._rows.append(s)
        return s

    def latest(self, session_id) -> Optional[Submission]:
        subs = [r for r in self._rows if r.session_id == session_id]
        return subs[-1] if subs else None

    def list(self, session_id) -> Sequence[Submission]:
        return [r for r in self._rows if r.session_id == session_id]
