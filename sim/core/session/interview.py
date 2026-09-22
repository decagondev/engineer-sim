"""Interview-assessment helpers. Pure functions — no I/O."""
from __future__ import annotations

import re

_READY_CUES = (
    "finished the design",
    "finished my design",
    "finished the document",
    "finished my document",
    "submitted the design",
    "submitted my design",
    "done with the design",
    "done with my design",
    "done with the document",
    "completed the design",
    "completed my design",
    "design is done",
    "design is ready",
    "document is done",
    "document is ready",
    "ready for review",
    "ready for assessment",
    "that's my design",
    "thats my design",
    "i submitted",
    "i've submitted",
    "i have submitted",
    "i've written the design",
    "i have written the design",
)


def signals_design_ready(text: str) -> bool:
    """True when the candidate tells the interviewer the design doc is done."""
    t = (text or "").lower()
    return any(cue in t for cue in _READY_CUES)


_LABEL = re.compile(r'(\b[A-Za-z_][\w-]*)\[(?!")([^\]"]*?)\]')
_SPECIAL = re.compile(r'[()\\/{}<>|:#;,&"\']')


def repair_mermaid(src: str) -> str:
    """Make an LLM-written flowchart parse: quote node labels that contain
    characters mermaid treats as syntax (parentheses, slashes, colons ...)
    and turn literal \\n inside labels into <br/>. Pure text surgery; a
    diagram that was already valid comes back unchanged."""
    if not src:
        return src

    def fix(m):
        name, label = m.group(1), m.group(2)
        text = label.replace("\\n", "<br/>").replace('"', "'")
        if _SPECIAL.search(label) or "\\n" in label:
            return f'{name}["{text}"]'
        return m.group(0)
    out = []
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("subgraph", "%%", "classDef", "class ", "style ", "linkStyle")):
            out.append(line)
            continue
        out.append(_LABEL.sub(fix, line))
    return "\n".join(out)


def extract_mermaid(raw: str) -> str:
    """Pull a mermaid diagram out of an LLM reply, or return empty."""
    text = (raw or "").strip()
    if not text:
        return ""
    fence = re.search(r"```(?:mermaid)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()
    head = text.splitlines()[0].strip().lower() if text else ""
    if head.startswith(("flowchart", "graph ", "sequencediagram",
                        "classdiagram", "statediagram", "erdiagram",
                        "c4context", "c4container")):
        return text
    if "-->" in text or "-.->" in text:
        return text
    return ""


def _ts(value: str):
    from datetime import datetime, timezone
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def started_at(rows) -> str:
    """Timestamp of the session-start signal, or ''."""
    for m in rows:
        if m.kind == "event" and m.content.startswith("Session started"):
            return m.ts
    return ""


def timebox_overrun(rows, timebox_minutes: int):
    """Minutes between the session start and the latest submission, minus the
    timebox. Positive = over, negative = under, None = untimed or not submitted."""
    if not timebox_minutes:
        return None
    start = _ts(started_at(rows))
    submitted = None
    for m in rows:
        if m.kind == "event" and "Submitted work" in m.content:
            submitted = _ts(m.ts) or submitted
    if start is None or submitted is None:
        return None
    return round((submitted - start).total_seconds() / 60.0 - timebox_minutes, 1)


class AssessmentStats:
    """How the defense went, counted from the assessor's DM."""

    def __init__(self, probes: int, answered: int, mean_answer_words: float) -> None:
        self.probes = probes
        self.answered = answered
        self.mean_answer_words = mean_answer_words

    @property
    def unanswered(self) -> int:
        return self.probes - self.answered

    def summary(self) -> str:
        if not self.probes:
            return "no assessor probes yet"
        return (f"answered {self.answered} of {self.probes} assessor probes"
                f"{'' if self.answered == self.probes else f' ({self.unanswered} left unanswered)'}"
                f"; answers averaged {self.mean_answer_words:.0f} words")


def assessment_stats(rows, assessor_key: str) -> AssessmentStats:
    """A probe is an assessor message after the assessment opened; it counts
    as answered when the candidate replied before the next probe."""
    channel = f"dm:{assessor_key}"
    opened = False
    probes = answered = 0
    words = []
    awaiting = False
    for m in rows:
        if m.kind == "event" and "[fired:assessment_open]" in m.content:
            opened = True
            continue
        if not opened or m.channel != channel or m.kind != "message":
            continue
        if m.sender == assessor_key:
            probes += 1
            awaiting = True
        elif m.sender == "tester" and awaiting:
            answered += 1
            awaiting = False
            words.append(len(m.content.split()))
    mean = sum(words) / len(words) if words else 0.0
    return AssessmentStats(probes, answered, mean)


def pair_channel_qa(rows, channel: str) -> list[tuple[str, str, str, str]]:
    """Group tester/persona turns on one DM into (who_q, q, who_a, a) pairs.

    Returns list of (asker, question, answerer, answer). Events are skipped.
    """
    msgs = [m for m in rows
            if m.channel == channel and m.kind == "message"]
    pairs: list[tuple[str, str, str, str]] = []
    i = 0
    while i < len(msgs):
        a = msgs[i]
        if i + 1 < len(msgs) and msgs[i + 1].sender != a.sender:
            b = msgs[i + 1]
            pairs.append((a.sender, a.content, b.sender, b.content))
            i += 2
        else:
            pairs.append((a.sender, a.content, "", ""))
            i += 1
    return pairs
