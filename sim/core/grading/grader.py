from __future__ import annotations

import json
from typing import Protocol, Sequence

from sim.core.grading.rubric import CriterionScore, Grade, Rubric
from sim.core.ports.llm import LLMClient, LLMMessage
from sim.core.ports.repository import MessageReader, StoredMessage

_GRADER_SYSTEM = (
    "You are a strict engineering assessor. You grade how well an engineer ran "
    "a client engagement, using ONLY the transcript and build record provided. "
    "For each rubric criterion return a score from 0.0 to 1.0 and one sentence "
    "of evidence quoting or pointing to what justifies it. Respond with ONLY a "
    "JSON object of the form "
    '{"scores":[{"key":"...","score":0.0,"evidence":"..."}],"summary":"..."} '
    "and no other text."
)


class Grader(Protocol):
    """Strategy port. Swap LLMGrader / HumanGrader / Hybrid without touching
    callers (OCP). Depends only on MessageReader (ISP: read-only).
    """

    def grade(self, session_id: str, reader: MessageReader, rubric: Rubric,
              build_record: str = "", expectation: str = "") -> Grade: ...


class LLMGrader:
    """Grades a session against a rubric via the LLM port. Deterministic under
    a scripted FakeLLMClient; validity vs. humans is checked by the calibration
    harness, not by gating tests.
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def grade(self, session_id: str, reader: MessageReader, rubric: Rubric,
              build_record: str = "", expectation: str = "") -> Grade:
        transcript = self._render(reader.list_for_session(session_id))
        crit_lines = "\n".join(
            f"- {c.key} (weight {c.weight}): {c.description}"
            for c in rubric.criteria
        )
        user = (
            f"RUBRIC:\n{crit_lines}\n\n"
            f"TRANSCRIPT:\n{transcript}\n\n"
            f"BUILD RECORD:\n{build_record or '(none provided)'}"
            + (f"\n\nEXPECTATION:\n{expectation}" if expectation else "")
        )
        raw = self._llm.complete(system=_GRADER_SYSTEM,
                                 messages=[LLMMessage("user", user)])
        data = self._parse(raw)
        return self._assemble(data, rubric)

    @staticmethod
    def _render(rows: Sequence[StoredMessage]) -> str:
        return "\n".join(
            f"[{m.kind}] {m.sender} ({m.channel}): {m.content}" for m in rows
        )

    @staticmethod
    def _parse(raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):]
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"grader did not return JSON: {raw[:200]!r}")
        return json.loads(text[start:end + 1])

    @staticmethod
    def _assemble(data: dict, rubric: Rubric) -> Grade:
        by_key = {s["key"]: s for s in data.get("scores", [])}
        scores, weighted, total_w = [], 0.0, 0.0
        for c in rubric.criteria:
            s = by_key.get(c.key, {"score": 0.0, "evidence": "no evidence found"})
            val = max(0.0, min(1.0, float(s.get("score", 0.0))))
            scores.append(CriterionScore(c.key, val, str(s.get("evidence", ""))))
            weighted += val * c.weight
            total_w += c.weight
        total = weighted / total_w if total_w else 0.0
        return Grade(tuple(scores), total, str(data.get("summary", "")))
