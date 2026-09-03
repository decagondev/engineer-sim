"""Tests for the save_fixture helper. Pure helpers are gating; the round-trip
proves a written fixture is consumable by the calibration runner.
"""
import json

import pytest

from sim.app.calibrate import run_calibration
from sim.app.save_fixture import (
    build_fixture, next_filename, parse_scores, rows_to_transcript,
    validate_scores, weighted_total, write_fixture,
)
from sim.core.grading.rubric import CriterionScore, Grade, Rubric
from sim.core.ports.repository import StoredMessage

_RUBRIC = Rubric.from_list([
    {"key": "discovery", "weight": 2.0, "description": "d"},
    {"key": "scoping", "weight": 1.0, "description": "d"},
])


def _rows():
    return [
        StoredMessage("s", "system", "general", "Session started.", "t0", "event"),
        StoredMessage("s", "tester", "dm:priya", "who uses this?", "t1", "message"),
        StoredMessage("s", "priya", "dm:priya", "my CSMs", "t2", "message"),
    ]


# FIX-01: score parsing + validation
def test_fix01_parse_scores():
    assert parse_scores(["discovery=0.75", "scoping=0.4"]) == \
        {"discovery": 0.75, "scoping": 0.4}


def test_fix01_validate_rejects_missing_and_extra():
    with pytest.raises(ValueError, match="missing"):
        validate_scores({"discovery": 0.5}, _RUBRIC)
    with pytest.raises(ValueError, match="unknown"):
        validate_scores({"discovery": 0.5, "scoping": 0.5, "bogus": 0.5}, _RUBRIC)
    with pytest.raises(ValueError, match="range"):
        validate_scores({"discovery": 1.5, "scoping": 0.5}, _RUBRIC)
    validate_scores({"discovery": 0.5, "scoping": 0.5}, _RUBRIC)  # ok


# FIX-02: weighted total matches the rubric weighting
def test_fix02_weighted_total():
    # (0.9*2 + 0.3*1)/3 = 0.7
    assert abs(weighted_total({"discovery": 0.9, "scoping": 0.3}, _RUBRIC) - 0.7) < 1e-9


# FIX-03: event rows dropped only when asked
def test_fix03_transcript_event_filter():
    assert len(rows_to_transcript(_rows())) == 3
    assert len(rows_to_transcript(_rows(), include_events=False)) == 2


# FIX-04: filename auto-increments
def test_fix04_next_filename(tmp_path):
    assert next_filename(tmp_path, "great run").name == "01_great_run.json"
    (tmp_path / "01_a.json").write_text("{}")
    (tmp_path / "07_b.json").write_text("{}")
    assert next_filename(tmp_path, "c").name == "08_c.json"


# FIX-05: written fixture is consumable by the calibration runner (round-trip)
def test_fix05_roundtrip_into_calibration(tmp_path):
    fixture = build_fixture(
        "found_need", _rows(),
        scores={"discovery": 0.9, "scoping": 0.3},
        summary="found it", build_record="COMMITS: x",
    )
    path = write_fixture(tmp_path, fixture)
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded["human"]["scores"] == {"discovery": 0.9, "scoping": 0.3}
    assert loaded["build_record"] == "COMMITS: x"

    class StubGrader:  # machine == human, so MAE 0
        def grade(self, sid, reader, rubric, build_record=""):
            return Grade((CriterionScore("discovery", 0.9, "e"),
                          CriterionScore("scoping", 0.3, "e")), 0.7, "s")

    report, details = run_calibration(tmp_path, _RUBRIC, StubGrader())
    assert report.n == 1
    assert report.total_mae < 1e-9
    assert details[0][0] == "found_need"
