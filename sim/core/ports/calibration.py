from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, Protocol


@dataclass(frozen=True)
class CalibrationRun:
    """One attempt to check the grader against reviewed sessions. Only the
    latest matters to the dashboard; it is small enough to store whole."""

    id: str
    status: str                       # running | done | failed
    started: str
    finished: str = ""
    provider: str = ""
    model: str = ""
    total: int = 0                    # fixtures to grade
    done: int = 0                     # fixtures graded so far
    passed: bool = False
    reports: dict = field(default_factory=dict)   # group label -> CalibrationReport.as_dict()
    fixtures: list = field(default_factory=list)  # session ids used
    error: str = ""
    started_by: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class CalibrationRunStore(Protocol):
    def save(self, run: CalibrationRun) -> CalibrationRun: ...

    def latest(self) -> Optional[CalibrationRun]: ...
