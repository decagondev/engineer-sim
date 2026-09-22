"""Cohort results: how a group did on one scenario. Pure.

Input is the enriched session rows the dashboards already produce (state,
grade_total, review_total ...) plus the stored grade bodies keyed by session
id, so the report never touches a store itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from statistics import mean, median
from typing import Mapping, Optional, Sequence

from sim.core.grading.rubric import Rubric


@dataclass(frozen=True)
class CriterionStats:
    key: str
    n: int
    mean: float
    median: float
    q1: float
    q3: float
    lowest: float
    highest: float
    values: tuple = field(default_factory=tuple)   # sorted, for a distribution strip


@dataclass(frozen=True)
class MemberResult:
    uid: str
    email: str
    name: str
    session_id: str
    state: str
    model_total: Optional[float]
    review_total: Optional[float]
    scores: dict = field(default_factory=dict)     # criterion -> effective score


@dataclass(frozen=True)
class CohortReport:
    scenario_key: str
    members: tuple
    criteria: tuple
    graded: int
    submitted: int
    not_submitted: tuple                            # member uids with no submission
    total_mean: Optional[float]
    total_median: Optional[float]

    def as_dict(self) -> dict:
        d = asdict(self)
        d["members"] = [asdict(m) for m in self.members]
        d["criteria"] = [asdict(c) for c in self.criteria]
        return d


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def effective_scores(grade_body: Mapping) -> dict:
    """criterion -> score, taking the instructor's override where present."""
    return {s["key"]: float(s.get("score") or 0.0) for s in (grade_body or {}).get("scores", [])
            if s.get("key")}


def cohort_results(scenario_key: str, members: Sequence[Mapping], rows: Sequence[Mapping],
                   grades: Mapping[str, Mapping], rubric: Rubric) -> CohortReport:
    """members: cohort member dicts (uid, email, name). rows: enriched session
    rows for this scenario. grades: session id -> merged grade body."""
    by_assignee: dict = {}
    for r in rows:
        uid = r.get("assignee_uid") or ""
        if uid and (uid not in by_assignee or (r.get("last_ts") or "") > (by_assignee[uid].get("last_ts") or "")):
            by_assignee[uid] = r
    results, not_submitted = [], []
    for m in members:
        r = by_assignee.get(m.get("uid") or "")
        if r is None:
            results.append(MemberResult(m.get("uid", ""), m.get("email", ""), m.get("name", ""),
                                        "", "no_session", None, None))
            not_submitted.append(m.get("uid", ""))
            continue
        body = grades.get(r["session_id"]) or {}
        total = body.get("total") if body else r.get("grade_total")
        results.append(MemberResult(
            m.get("uid", ""), m.get("email", ""), m.get("name", ""), r["session_id"],
            r.get("state") or "not_started",
            model_total=(body.get("total_model") if body and body.get("total_model") is not None
                         else r.get("grade_total")),
            review_total=(total if body and body.get("review") else r.get("review_total")),
            scores=effective_scores(body) if body else {},
        ))
        if not r.get("submitted"):
            not_submitted.append(m.get("uid", ""))
    criteria = []
    for c in rubric.criteria:
        vals = sorted(res.scores[c.key] for res in results if c.key in res.scores)
        if vals:
            criteria.append(CriterionStats(c.key, len(vals), mean(vals), median(vals),
                                           _quantile(vals, .25), _quantile(vals, .75),
                                           vals[0], vals[-1], tuple(vals)))
        else:
            criteria.append(CriterionStats(c.key, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ()))
    totals = [res.review_total if res.review_total is not None else res.model_total
              for res in results if (res.review_total is not None or res.model_total is not None)]
    return CohortReport(
        scenario_key=scenario_key, members=tuple(results), criteria=tuple(criteria),
        graded=sum(1 for res in results if res.state in ("graded", "reviewed")),
        submitted=sum(1 for res in results if res.state in ("submitted", "graded", "reviewed")),
        not_submitted=tuple(not_submitted),
        total_mean=mean(totals) if totals else None,
        total_median=median(totals) if totals else None,
    )


def results_csv(report: CohortReport) -> str:
    keys = [c.key for c in report.criteria]
    lines = ["name,email,session_id,state,model_total,review_total," + ",".join(keys)]
    for m in report.members:
        cells = [m.name, m.email, m.session_id, m.state,
                 "" if m.model_total is None else f"{m.model_total:.3f}",
                 "" if m.review_total is None else f"{m.review_total:.3f}"]
        cells += ["" if k not in m.scores else f"{m.scores[k]:.3f}" for k in keys]
        lines.append(",".join('"' + str(c).replace('"', '""') + '"' if ("," in str(c) or '"' in str(c)) else str(c)
                              for c in cells))
    return "\n".join(lines) + "\n"
