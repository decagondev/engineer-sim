"""Turn a finished session into a calibration fixture (Wave 4 helper).

One command instead of hand-editing JSON. Reads the transcript straight from the
session store, attaches your human scores, optionally captures a git build record
and/or runs the grader for an on-the-spot comparison, and writes a fixture the
calibration harness can consume.

    # after a playtest session with id s-abc123:
    python -m sim.app.save_fixture s-abc123 \
        --id found_need_thin_scope \
        --score discovery=0.75 --score scoping=0.4 \
        --score stakeholders=0.6 --score communication=0.7 \
        --summary "Found the need, scoped too thin, brushed off Marcus." \
        --repo /path/to/testers/repo --grade

Score keys must exactly match the scenario's rubric. Scores are 0.0-1.0.
Run it from the same directory / SIM_DB_PATH the app used, so it finds the DB.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

from sim.core.grading.rubric import Rubric
from sim.core.ports.repository import StoredMessage


# --- pure helpers (unit-tested) ------------------------------------------
def parse_scores(pairs: Sequence[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for p in pairs:
        if "=" not in p:
            raise ValueError(f"bad --score '{p}', expected key=value")
        k, v = p.split("=", 1)
        out[k.strip()] = float(v)
    return out


def validate_scores(scores: dict[str, float], rubric: Rubric) -> None:
    rubric_keys = {c.key for c in rubric.criteria}
    given = set(scores)
    missing, extra = rubric_keys - given, given - rubric_keys
    if missing:
        raise ValueError(f"missing scores for: {sorted(missing)}")
    if extra:
        raise ValueError(f"unknown score keys (not in rubric): {sorted(extra)}")
    for k, v in scores.items():
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"score {k}={v} out of range 0.0-1.0")


def weighted_total(scores: dict[str, float], rubric: Rubric) -> float:
    tw = sum(c.weight for c in rubric.criteria)
    return sum(scores[c.key] * c.weight for c in rubric.criteria) / tw if tw else 0.0


def rows_to_transcript(rows: Sequence[StoredMessage],
                       include_events: bool = True) -> list[dict]:
    return [
        {"sender": m.sender, "channel": m.channel,
         "content": m.content, "kind": m.kind}
        for m in rows
        if include_events or m.kind == "message"
    ]


def build_fixture(fixture_id: str, rows: Sequence[StoredMessage],
                  scores: dict[str, float], summary: str,
                  build_record: str = "",
                  include_events: bool = True) -> dict:
    return {
        "id": fixture_id,
        "build_record": build_record,
        "transcript": rows_to_transcript(rows, include_events),
        "human": {"summary": summary, "scores": scores},
    }


def next_filename(out_dir: Path, fixture_id: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", fixture_id.lower()).strip("_") or "run"
    nums = []
    for f in out_dir.glob("*.json"):
        m = re.match(r"(\d+)_", f.name)
        if m:
            nums.append(int(m.group(1)))
    n = (max(nums) + 1) if nums else 1
    return out_dir / f"{n:02d}_{slug}.json"


def write_fixture(out_dir: Path, fixture: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = next_filename(out_dir, fixture["id"])
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    return path


# --- CLI (I/O) ------------------------------------------------------------
def main(argv=None) -> int:
    from sim.app.composition_root import build_grader, build_scenario
    from sim.app.config import Config
    from sim.adapters.persistence.sqlite_repo import SqliteMessageRepository

    ap = argparse.ArgumentParser(description="Save a session as a calibration fixture")
    ap.add_argument("session_id")
    ap.add_argument("--id", default="run", help="short label for the fixture")
    ap.add_argument("--score", action="append", default=[],
                    metavar="key=value", help="repeatable; must match rubric keys")
    ap.add_argument("--summary", default="")
    ap.add_argument("--repo", default="", help="tester's git repo to capture as build record")
    ap.add_argument("--build-record", default="", help="build record text (overrides --repo)")
    ap.add_argument("--messages-only", action="store_true",
                    help="drop system/event rows from the fixture transcript")
    ap.add_argument("--grade", action="store_true",
                    help="also run the grader and print a human-vs-machine comparison")
    ap.add_argument("--db", default="", help="session DB path (default: SIM_DB_PATH or sim.db)")
    ap.add_argument("--out", default="", help="output dir (default: calibration/<scenario>)")
    args = ap.parse_args(argv)

    config = Config.from_env()
    scenario = build_scenario(config)
    rubric = scenario.rubric
    if not rubric.criteria:
        print("scenario has no rubric — nothing to score against", file=sys.stderr)
        return 2

    try:
        scores = parse_scores(args.score)
        validate_scores(scores, rubric)
    except ValueError as e:
        print(f"score error: {e}", file=sys.stderr)
        print(f"expected keys: {[c.key for c in rubric.criteria]}", file=sys.stderr)
        return 2

    db_path = args.db or config.db_path
    repo = SqliteMessageRepository(db_path)
    rows = list(repo.list_for_session(args.session_id))
    if not rows:
        print(f"no messages for session '{args.session_id}' in {db_path}. "
              f"Wrong id or wrong DB (run from the app's directory / SIM_DB_PATH).",
              file=sys.stderr)
        return 2

    build_record = args.build_record
    if not build_record and args.repo:
        from sim.adapters.build.git_observer import GitBuildObserver
        build_record = GitBuildObserver().summary(args.repo)

    fixture = build_fixture(
        fixture_id=args.id, rows=rows, scores=scores, summary=args.summary,
        build_record=build_record, include_events=not args.messages_only,
    )

    h_total = weighted_total(scores, rubric)
    if args.grade:
        if config.llm_provider == "fake":
            print("(--grade skipped: set LLM_PROVIDER=ollama|anthropic to grade)")
        else:
            grade = build_grader(config).grade(
                args.session_id, repo, rubric, build_record)
            fixture["_machine_reference"] = {"note": "not calibrated; for review only",
                                             **grade.as_dict()}
            print("\nhuman vs machine:")
            print(f"  total   human {h_total:.2f}   machine {grade.total:.2f}   "
                  f"Δ {grade.total - h_total:+.2f}")
            m = {s.key: s.score for s in grade.scores}
            for c in rubric.criteria:
                print(f"  {c.key:14} human {scores[c.key]:.2f}   "
                      f"machine {m.get(c.key, 0.0):.2f}   "
                      f"Δ {m.get(c.key, 0.0) - scores[c.key]:+.2f}")

    out_dir = Path(args.out) if args.out else \
        Path(__file__).resolve().parents[2] / "calibration" / scenario.key
    path = write_fixture(out_dir, fixture)

    print(f"\nwrote {path}")
    print(f"  {len(fixture['transcript'])} transcript rows, "
          f"human weighted total {h_total:.2f}")
    existing = len(list(out_dir.glob('*.json')))
    print(f"  {existing} fixtures now in {out_dir.name}/ "
          f"({'enough' if existing >= 10 else f'aim for >=10, {10 - existing} to go'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
