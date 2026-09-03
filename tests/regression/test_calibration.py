"""Calibration harness tests. The METRICS MATH is deterministic and gating.
The validity VERDICT (real model vs real human scores) is not a gating test.
"""
import json

from sim.app.calibrate import run_calibration
from sim.core.grading.calibration import (
    CalibrationThresholds, build_report, consistency,
)
from sim.core.grading.rubric import CriterionScore, Grade, Rubric


def _grade(scores: dict, weights: dict) -> Grade:
    cs = tuple(CriterionScore(k, v, "e") for k, v in scores.items())
    tw = sum(weights.values())
    total = sum(scores[k] * weights[k] for k in scores) / tw
    return Grade(cs, total, "")


_W = {"discovery": 2.0, "scoping": 1.0}


# CAL-01: perfect agreement passes
def test_cal01_perfect_agreement_passes():
    pairs = []
    for d, s in [(0.9, 0.8), (0.5, 0.4), (0.2, 0.3)]:
        g = _grade({"discovery": d, "scoping": s}, _W)
        pairs.append((g, g))
    report = build_report(pairs)
    assert report.total_mae == 0.0
    assert report.within_tolerance_rate == 1.0
    assert abs(report.rank_correlation - 1.0) < 1e-9
    assert report.passed is True


# CAL-02: a systematic offset is caught (bias + fail)
def test_cal02_systematic_offset_fails():
    pairs = []
    for d, s in [(0.9, 0.8), (0.5, 0.4), (0.2, 0.3)]:
        human = _grade({"discovery": d, "scoping": s}, _W)
        machine = _grade({"discovery": min(1.0, d + 0.3),
                          "scoping": min(1.0, s + 0.3)}, _W)
        pairs.append((human, machine))
    report = build_report(pairs)
    assert report.total_bias > 0.15          # grader runs hot
    assert report.passed is False


# CAL-03: rank correlation catches a grader that orders runs wrongly
def test_cal03_reversed_ranking_detected():
    humans = [0.9, 0.6, 0.3]
    machines = [0.3, 0.6, 0.9]               # reversed
    pairs = [
        (_grade({"discovery": h, "scoping": h}, _W),
         _grade({"discovery": m, "scoping": m}, _W))
        for h, m in zip(humans, machines)
    ]
    report = build_report(pairs)
    assert report.rank_correlation is not None
    assert report.rank_correlation < 0
    assert report.passed is False


# CAL-04: empty + small-n guards
def test_cal04_empty_and_small_n_notes():
    assert build_report([]).passed is False
    one = _grade({"discovery": 0.5, "scoping": 0.5}, _W)
    r = build_report([(one, one)])
    assert any("only 1 fixtures" in n for n in r.notes)


# CAL-05: self-consistency (reliability)
def test_cal05_consistency():
    assert consistency([0.5, 0.5, 0.5]).stdev == 0.0
    c = consistency([0.4, 0.6])
    assert abs(c.mean - 0.5) < 1e-9 and abs(c.spread - 0.2) < 1e-9


# CAL-06: runner wires fixtures -> grader -> report (stub grader)
def test_cal06_runner_over_fixtures(tmp_path):
    rubric = Rubric.from_list([
        {"key": "discovery", "weight": 2.0, "description": "d"},
        {"key": "scoping", "weight": 1.0, "description": "d"},
    ])

    class StubGrader:
        """Returns machine == human (read from the transcript marker)."""
        def grade(self, session_id, reader, rubric, build_record=""):
            rows = reader.list_for_session(session_id)
            d = float(rows[0].content)       # fixture encodes the score to echo
            return _grade({"discovery": d, "scoping": d}, _W)

    for i, d in enumerate([0.9, 0.4]):
        (tmp_path / f"{i}.json").write_text(json.dumps({
            "id": f"fx{i}",
            "transcript": [{"sender": "tester", "channel": "c",
                            "content": str(d), "kind": "message"}],
            "human": {"scores": {"discovery": d, "scoping": d}},
        }))
    report, details = run_calibration(tmp_path, rubric, StubGrader())
    assert report.n == 2
    assert report.total_mae == 0.0
    assert len(details) == 2
