"""Grader calibration runner (Wave 4, Epic G3).

Loads human-scored fixtures, runs the grader against each, and reports how well
machine scores agree with human scores (validity) and how stable they are
(reliability). This is the gate: until a run passes, grader output is
directional only, not decision-grade.

    LLM_PROVIDER=anthropic ANTHROPIC_MODEL=<current> python -m sim.app.calibrate
    LLM_PROVIDER=ollama python -m sim.app.calibrate --consistency

The metrics math is tested deterministically; the *verdict* requires a real
model and real human scores in the fixtures.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from sim.adapters.persistence.memory_repo import InMemoryMessageRepository
from sim.core.grading.calibration import (
    ConsistencyReport, build_report, consistency,
)
from sim.core.grading.grader import Grader
from sim.core.grading.rubric import CriterionScore, Grade, Rubric
from sim.core.ports.repository import StoredMessage

_DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "calibration" / "churn_dashboard"


def _repo_from(transcript: Sequence[dict]) -> InMemoryMessageRepository:
    repo = InMemoryMessageRepository()
    for i, m in enumerate(transcript):
        repo.append(StoredMessage(
            session_id="fx", sender=m["sender"],
            channel=m.get("channel", "general"), content=m["content"],
            ts=f"t{i:03d}", kind=m.get("kind", "message"),
        ))
    return repo


def _human_grade(fixture: dict, rubric: Rubric) -> Grade:
    scores, weighted, total_w = [], 0.0, 0.0
    human_scores = fixture["human"]["scores"]
    for c in rubric.criteria:
        v = float(human_scores.get(c.key, 0.0))
        scores.append(CriterionScore(c.key, v, "human score"))
        weighted += v * c.weight
        total_w += c.weight
    total = weighted / total_w if total_w else 0.0
    return Grade(tuple(scores), total, fixture["human"].get("summary", ""))


def run_calibration(fixtures_dir, rubric: Rubric, grader: Grader):
    pairs, details = [], []
    for path in sorted(Path(fixtures_dir).glob("*.json")):
        fx = json.loads(path.read_text(encoding="utf-8"))
        repo = _repo_from(fx["transcript"])
        machine = grader.grade("fx", repo, rubric, fx.get("build_record", ""))
        human = _human_grade(fx, rubric)
        pairs.append((human, machine))
        details.append((fx.get("id", path.stem), human.total, machine.total))
    return build_report(pairs), details


def run_consistency(fixture_path, rubric: Rubric, grader: Grader,
                    k: int = 5) -> ConsistencyReport:
    fx = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    repo = _repo_from(fx["transcript"])
    totals = [grader.grade("fx", repo, rubric, fx.get("build_record", "")).total
              for _ in range(k)]
    return consistency(totals)


def _print_report(report, details) -> None:
    print("=" * 60)
    print(f"GRADER CALIBRATION — {report.n} fixtures — "
          f"{'PASS' if report.passed else 'FAIL'}")
    print("=" * 60)
    print(f"total MAE:            {report.total_mae:.3f}")
    print(f"total bias (mach-hum):{report.total_bias:+.3f}")
    print(f"within-tolerance:     {report.within_tolerance_rate:.0%}")
    rc = "n/a" if report.rank_correlation is None else f"{report.rank_correlation:.3f}"
    print(f"rank correlation:     {rc}")
    print("\nper criterion:")
    for c in report.per_criterion:
        print(f"  {c.key:14} MAE {c.mae:.3f}  bias {c.bias:+.3f}")
    print("\nhuman vs machine totals:")
    for name, h, m in details:
        print(f"  {name:22} human {h:.2f}  machine {m:.2f}  Δ {m - h:+.2f}")
    for note in report.notes:
        print(f"\n! {note}")


def main(argv=None) -> int:
    from sim.app.composition_root import build_grader, build_scenario
    from sim.app.config import Config

    parser = argparse.ArgumentParser(description="Grader calibration harness")
    parser.add_argument("--fixtures", default=str(_DEFAULT_FIXTURES))
    parser.add_argument("--consistency", action="store_true",
                        help="also measure grader self-consistency (K re-grades)")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args(argv)

    config = Config.from_env()
    if config.llm_provider == "fake":
        print("Calibration needs a real model. Set LLM_PROVIDER=ollama|anthropic.",
              file=sys.stderr)
        return 2

    scenario = build_scenario(config)
    grader = build_grader(config)
    report, details = run_calibration(args.fixtures, scenario.rubric, grader)
    _print_report(report, details)

    if args.consistency:
        first = sorted(Path(args.fixtures).glob("*.json"))[0]
        cons = run_consistency(first, scenario.rubric, grader, k=args.k)
        print(f"\nself-consistency on {first.stem} (k={cons.k}): "
              f"stdev {cons.stdev:.3f}, spread {cons.spread:.3f}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
