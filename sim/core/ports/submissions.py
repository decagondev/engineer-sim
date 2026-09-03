from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class Submission:
    session_id: str
    seq: int
    filename: str
    content: str          # the patch / diff text the learner submitted
    lines: int
    ts: str


class SubmissionStore(Protocol):
    """Where a learner's submitted work (a patch/diff from their own machine)
    is kept, so the grader can read it as the build record.
    """

    def save(self, session_id: str, filename: str, content: str,
             ts: str) -> Submission: ...

    def latest(self, session_id: str) -> Optional[Submission]: ...

    def list(self, session_id: str) -> Sequence[Submission]: ...
