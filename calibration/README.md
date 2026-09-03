# Calibration fixtures

Each JSON file is a past run: a transcript (+ optional build record) plus the
**human** score a real instructor gave it. `python -m sim.app.calibrate` grades
each with the LLM grader and compares.

> IMPORTANT: the `human` scores in these seed files are **illustrative
> placeholders** written to exercise the harness, not real instructor
> judgments. Replace them with genuine human scores — and add more (aim for
> >=10, spanning the quality range) — before treating a PASS as decision-grade.

Schema:
```json
{
  "id": "short-name",
  "build_record": "optional string",
  "transcript": [{"sender": "tester|<persona>", "channel": "dm:priya",
                  "content": "...", "kind": "message"}],
  "human": {"summary": "...", "scores": {"discovery": 0.9, "scoping": 0.8, ...}}
}
```
