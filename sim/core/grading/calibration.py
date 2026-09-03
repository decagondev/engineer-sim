from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

from sim.core.grading.rubric import Grade

# Pure grader-validity math. No I/O, no framework — testable deterministically
# with synthetic Grade pairs. Answers two separate questions:
#   validity     — does the grader agree with human scores?
#   reliability  — is the grader stable when it re-grades the same run?


@dataclass(frozen=True)
class CalibrationThresholds:
    """The bar the grader must clear before its scores are decision-grade."""

    tolerance: float = 0.15            # a criterion score counts as "agreeing"
    max_total_mae: float = 0.15        # avg absolute error on the total score
    min_within_tolerance: float = 0.80 # fraction of criterion scores within tol
    min_rank_correlation: float = 0.70 # does it rank runs like a human would


@dataclass(frozen=True)
class CriterionAgreement:
    key: str
    mae: float                         # mean absolute error
    bias: float                        # mean signed error (machine - human)


@dataclass(frozen=True)
class CalibrationReport:
    n: int
    total_mae: float
    total_bias: float
    within_tolerance_rate: float
    rank_correlation: Optional[float]
    per_criterion: tuple[CriterionAgreement, ...]
    passed: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "passed": self.passed,
            "total_mae": round(self.total_mae, 4),
            "total_bias": round(self.total_bias, 4),
            "within_tolerance_rate": round(self.within_tolerance_rate, 4),
            "rank_correlation": (None if self.rank_correlation is None
                                 else round(self.rank_correlation, 4)),
            "per_criterion": [
                {"key": c.key, "mae": round(c.mae, 4), "bias": round(c.bias, 4)}
                for c in self.per_criterion
            ],
            "notes": list(self.notes),
        }


def build_report(
    pairs: Sequence[tuple[Grade, Grade]],
    thresholds: CalibrationThresholds = CalibrationThresholds(),
) -> CalibrationReport:
    """pairs = [(human_grade, machine_grade), ...]."""
    n = len(pairs)
    if n == 0:
        return CalibrationReport(0, 0.0, 0.0, 0.0, None, (), False,
                                 ("no fixtures provided",))

    # --- total-score agreement --------------------------------------------
    human_totals = [h.total for h, _ in pairs]
    machine_totals = [m.total for _, m in pairs]
    total_mae = _mae(human_totals, machine_totals)
    total_bias = _bias(human_totals, machine_totals)
    rank_corr = _spearman(human_totals, machine_totals)

    # --- per-criterion agreement ------------------------------------------
    keys = [c.key for c in pairs[0][0].scores]
    per_criterion, within_hits, within_total = [], 0, 0
    for key in keys:
        hs = [_score_for(h, key) for h, _ in pairs]
        ms = [_score_for(m, key) for _, m in pairs]
        per_criterion.append(CriterionAgreement(key, _mae(hs, ms), _bias(hs, ms)))
        for a, b in zip(hs, ms):
            within_total += 1
            if abs(a - b) <= thresholds.tolerance:
                within_hits += 1
    within_rate = within_hits / within_total if within_total else 0.0

    notes = []
    if rank_corr is None:
        notes.append("rank correlation undefined (n<2 or no score variation)")
    if n < 10:
        notes.append(f"only {n} fixtures — aim for >=10 before trusting the verdict")

    corr_ok = rank_corr is None or rank_corr >= thresholds.min_rank_correlation
    passed = (
        total_mae <= thresholds.max_total_mae
        and within_rate >= thresholds.min_within_tolerance
        and corr_ok
    )
    return CalibrationReport(
        n=n, total_mae=total_mae, total_bias=total_bias,
        within_tolerance_rate=within_rate, rank_correlation=rank_corr,
        per_criterion=tuple(per_criterion), passed=passed, notes=tuple(notes),
    )


@dataclass(frozen=True)
class ConsistencyReport:
    """Grader self-consistency: re-grade one run K times, measure the spread."""

    k: int
    mean: float
    stdev: float
    spread: float                      # max - min

    def as_dict(self) -> dict:
        return {"k": self.k, "mean": round(self.mean, 4),
                "stdev": round(self.stdev, 4), "spread": round(self.spread, 4)}


def consistency(totals: Sequence[float]) -> ConsistencyReport:
    k = len(totals)
    if k == 0:
        return ConsistencyReport(0, 0.0, 0.0, 0.0)
    mean = sum(totals) / k
    var = sum((t - mean) ** 2 for t in totals) / k
    return ConsistencyReport(k, mean, math.sqrt(var),
                             max(totals) - min(totals))


# --- helpers --------------------------------------------------------------
def _score_for(grade: Grade, key: str) -> float:
    for s in grade.scores:
        if s.key == key:
            return s.score
    return 0.0


def _mae(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a) if a else 0.0


def _bias(human: Sequence[float], machine: Sequence[float]) -> float:
    return sum(m - h for h, m in zip(human, machine)) / len(human) if human else 0.0


def _spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    return _pearson(_rank(xs), _rank(ys))


def _rank(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # average rank, 1-based, handles ties
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)
