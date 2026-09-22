from __future__ import annotations

from typing import Optional

from sim.core.ports.calibration import CalibrationRun


class InMemoryCalibrationRunStore:
    def __init__(self) -> None:
        self._latest: Optional[CalibrationRun] = None

    def save(self, run: CalibrationRun) -> CalibrationRun:
        self._latest = run
        return run

    def latest(self) -> Optional[CalibrationRun]:
        return self._latest
