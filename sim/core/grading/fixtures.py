"""Calibration fixtures: a past run plus the human verdict on it. Pure.

A fixture is the JSON shape documented in calibration/README.md. Two ways in:
the CLI (`sim/app/save_fixture.py`) with scores typed by hand, and the
dashboard, where every session an instructor has reviewed becomes one.
"""
from __future__ import annotations

from typing import Mapping, Optional, Sequence

from sim.core.grading.rubric import CriterionScore, Grade, Rubric


def rows_to_transcript(rows: Sequence[object], include_events: bool = True) -> list[dict]:
    return [
        {"sender": m.sender, "channel": m.channel, "content": m.content, "kind": m.kind}
        for m in rows
        if include_events or m.kind == "message"
    ]


def weighted_total(scores: Mapping[str, float], rubric: Rubric) -> float:
    tw = sum(c.weight for c in rubric.criteria)
    return sum(float(scores.get(c.key, 0.0)) * c.weight for c in rubric.criteria) / tw if tw else 0.0


def build_fixture(fixture_id: str, rows: Sequence[object], scores: Mapping[str, float],
                  summary: str, build_record: str = "", include_events: bool = True,
                  scenario_key: str = "", level: str = "", expectation: str = "") -> dict:
    fx = {
        "id": fixture_id,
        "build_record": build_record,
        "transcript": rows_to_transcript(rows, include_events),
        "human": {"summary": summary, "scores": dict(scores)},
    }
    if scenario_key:
        fx["scenario"] = scenario_key
    if level:
        fx["level"] = level
    if expectation:
        fx["expectation"] = expectation
    return fx


def human_grade(fixture: Mapping, rubric: Rubric) -> Grade:
    """The fixture's human scores as a Grade (missing criteria count as 0)."""
    scores, weighted, total_w = [], 0.0, 0.0
    human_scores = fixture["human"]["scores"]
    for c in rubric.criteria:
        v = float(human_scores.get(c.key, 0.0))
        scores.append(CriterionScore(c.key, v, "human score"))
        weighted += v * c.weight
        total_w += c.weight
    total = weighted / total_w if total_w else 0.0
    return Grade(tuple(scores), total, fixture["human"].get("summary", ""))


def fixture_from_review(session_id: str, rows: Sequence[object], merged_grade: Mapping,
                        rubric: Rubric, scenario_key: str = "", level: str = "",
                        build_record: str = "", expectation: str = "") -> Optional[dict]:
    """A reviewed session as a fixture. The human scores are the instructor's
    overrides plus the model scores they left standing (accepting a score is a
    verdict too). None when the grade has no review."""
    review = merged_grade.get("review")
    if not review:
        return None
    scores = {}
    for s in merged_grade.get("scores", []):
        if s.get("key") in {c.key for c in rubric.criteria}:
            scores[s["key"]] = float(s.get("score") or 0.0)
    if len(scores) < len(rubric.criteria):
        return None
    summary = review.get("comment") or merged_grade.get("summary") or ""
    return build_fixture(session_id, rows, scores, summary, build_record=build_record,
                         scenario_key=scenario_key, level=level, expectation=expectation)


def group_by_rubric(fixtures: Sequence[Mapping], rubric_for) -> list[tuple[str, Rubric, list]]:
    """Fixtures grouped by the criterion keys of their scenario's rubric, so a
    report never compares scores across different criteria. `rubric_for(scenario_key)`
    returns the Rubric (or None). Fixtures without a known rubric are skipped."""
    groups: dict[tuple, tuple[Rubric, list, list]] = {}
    for fx in fixtures:
        rubric = rubric_for(fx.get("scenario") or "")
        if rubric is None or not rubric.criteria:
            continue
        key = tuple(c.key for c in rubric.criteria)
        if key not in groups:
            groups[key] = (rubric, [], [])
        groups[key][1].append(fx)
        sc = fx.get("scenario") or ""
        if sc and sc not in groups[key][2]:
            groups[key][2].append(sc)
    return [(", ".join(names) or "unknown", rubric, items)
            for (rubric, items, names) in groups.values()]
