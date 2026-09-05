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
