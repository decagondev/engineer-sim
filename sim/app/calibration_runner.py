"""Run the grader over reviewed sessions in the background and record the
verdict. Application layer: it owns the thread and the run store; the maths
(`build_report`) and the fixture shape live in sim/core."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from sim.core.grading.calibration import build_report
from sim.core.grading.fixtures import group_by_rubric, human_grade
from sim.core.ports.calibration import CalibrationRun, CalibrationRunStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CalibrationBusy(RuntimeError):
    """A run is already in progress."""


class CalibrationRunner:
    """`fixtures()` returns the fixture dicts to grade, `grader()` a Grader,
    `rubric_for(scenario_key)` the rubric, `reader_from(transcript)` a
    MessageReader over a fixture transcript (an adapter concern, injected)."""

    def __init__(self, store: CalibrationRunStore, *, fixtures: Callable[[], Sequence[dict]],
                 grader: Callable[[], object], rubric_for: Callable[[str], object],
                 reader_from: Callable[[Sequence[dict]], object],
                 provider: str = "", model: str = "") -> None:
        self._store = store
        self._fixtures = fixtures
        self._grader = grader
        self._rubric_for = rubric_for
        self._reader_from = reader_from
        self._provider = provider
        self._model = model
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    # -- state ---------------------------------------------------------------
    def latest(self) -> Optional[CalibrationRun]:
        return self._store.latest()

    def running(self) -> bool:
        run = self.latest()
        return bool(run and run.status == "running" and self._thread and self._thread.is_alive())

    # -- start --------------------------------------------------------------
    def start(self, started_by: str = "", sync: bool = False) -> CalibrationRun:
        with self._lock:
            if self.running():
                raise CalibrationBusy("a calibration run is already in progress")
            fixtures = list(self._fixtures())
            run = CalibrationRun(id=uuid.uuid4().hex[:10], status="running", started=_now(),
                                 provider=self._provider, model=self._model,
                                 total=len(fixtures), started_by=started_by,
                                 fixtures=[f.get("id", "") for f in fixtures])
            self._store.save(run)
            if sync:
                self._execute(run, fixtures)
                return self._store.latest() or run
            self._thread = threading.Thread(target=self._execute, args=(run, fixtures),
                                            name="calibration", daemon=True)
            self._thread.start()
            return run

    # -- the work -------------------------------------------------------------
    def _execute(self, run: CalibrationRun, fixtures: Sequence[dict]) -> None:
        import dataclasses
        try:
            if not fixtures:
                raise ValueError("no reviewed sessions to calibrate against")
            grader = self._grader()
            reports, done, all_passed = {}, 0, True
            for label, rubric, items in group_by_rubric(fixtures, self._rubric_for):
                pairs = []
                for fx in items:
                    reader = self._reader_from(fx["transcript"])
                    machine = grader.grade("fx", reader, rubric, fx.get("build_record", ""),
                                           fx.get("expectation", ""))
                    pairs.append((human_grade(fx, rubric), machine))
                    done += 1
                    self._store.save(dataclasses.replace(run, done=done))
                report = build_report(pairs)
                reports[label] = report.as_dict()
                all_passed = all_passed and report.passed
            if not reports:
                raise ValueError("none of the fixtures belong to a known scenario")
            self._store.save(dataclasses.replace(
                run, status="done", finished=_now(), done=done, reports=reports,
                passed=all_passed))
        except Exception as e:
            self._store.save(dataclasses.replace(
                run, status="failed", finished=_now(), error=str(e)[:500]))
