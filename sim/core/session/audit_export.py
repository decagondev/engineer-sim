"""Build a defensible markdown audit of an interview (or any) session."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sim.core.session.interview import pair_channel_qa


def _name(key: str, personas: dict[str, str]) -> str:
    return personas.get(key, "You" if key == "tester" else key)


def _qa_section(title: str, rows, channel: str, personas: dict[str, str]) -> str:
    pairs = pair_channel_qa(rows, channel)
    if not pairs:
        return f"## {title}\n\n_(no messages on this channel)_\n"
    lines = [f"## {title}", ""]
    for i, (ask, q, ans, a) in enumerate(pairs, 1):
        lines.append(f"### Turn {i}")
        lines.append("")
        lines.append(f"**{_name(ask, personas)}**")
        lines.append("")
        lines.append(q.strip() or "_(empty)_")
        lines.append("")
        if ans and a:
            lines.append(f"**{_name(ans, personas)}**")
            lines.append("")
            lines.append(a.strip())
            lines.append("")
    return "\n".join(lines)


def build_audit_markdown(
    *,
    session_id: str,
    title: str,
    track: str,
    difficulty: str,
    level: str,
    level_label: str,
    personas: Sequence[object],
    rows: Sequence[object],
    grade: dict | None = None,
    design: str = "",
    mermaid: str = "",
    tickets: Sequence[dict] | None = None,
    submissions: Sequence[object] | None = None,
) -> str:
    names = {p.key: p.name for p in personas}
    lanes = {getattr(p, "lane", ""): p for p in personas}
    interviewer = lanes.get("interviewer") or (personas[0] if personas else None)
    assessor = lanes.get("assessor")
    exported = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    parts = [
        f"# Assessment audit — {title}",
        "",
        f"- **Session:** `{session_id}`",
        f"- **Track:** {track}",
        f"- **Scenario difficulty:** {difficulty}",
        f"- **Graded at:** {level_label} (`{level}`)",
        f"- **Exported:** {exported}",
        "",
        "This file is the defensible record of the run: clarifying interview, "
        "design, assessment defense, scores, and the full transcript.",
        "",
    ]

    if grade:
        parts.append("## Scores")
        parts.append("")
        if grade.get("include_tickets"):
            parts.append(
                f"**Base:** {round(float(grade.get('total_base', 0)) * 100)}%  ·  "
                f"**With tickets extra credit:** {round(float(grade.get('total', 0)) * 100)}%"
            )
        else:
            parts.append(f"**Total:** {round(float(grade.get('total', 0)) * 100)}%")
        parts.append("")
        parts.append("| Criterion | Score | Evidence |")
        parts.append("| --- | --- | --- |")
        for s in grade.get("scores", []):
            ev = str(s.get("evidence", "")).replace("|", "\\|").replace("\n", " ")
            parts.append(
                f"| {s.get('key')} | {round(float(s.get('score', 0)) * 100)}% | {ev} |"
            )
        extra = grade.get("tickets_extra")
        if extra:
            ev = str(extra.get("evidence", "")).replace("|", "\\|").replace("\n", " ")
            parts.append(
                f"| tickets (extra credit) | "
                f"{round(float(extra.get('score', 0)) * 100)}% | {ev} |"
            )
        parts.append("")
        if grade.get("summary"):
            parts.append("### Grader summary")
            parts.append("")
            parts.append(grade["summary"].strip())
            parts.append("")
        if grade.get("caveat"):
            parts.append(f"> {grade['caveat']}")
            parts.append("")

    if interviewer:
        parts.append(_qa_section(
            f"Clarifying interview — {interviewer.name}",
            rows, f"dm:{interviewer.key}", names))
        parts.append("")

    parts.append("## Design document")
    parts.append("")
    parts.append((design or "").strip() or "_(no design document captured)_")
    parts.append("")

    parts.append("## Design diagram")
    parts.append("")
    if mermaid:
        parts.append("```mermaid")
        parts.append(mermaid.strip())
        parts.append("```")
    else:
        parts.append("_(no diagram generated)_")
    parts.append("")

    if assessor:
        parts.append(_qa_section(
            f"Assessment defense — {assessor.name}",
            rows, f"dm:{assessor.key}", names))
        parts.append("")

    if tickets:
        parts.append("## Tickets")
        parts.append("")
        for t in tickets:
            key = t.get("key") or t.get("title") or "ticket"
            parts.append(f"### {key} — {t.get('title', '')} ({t.get('status', '')})")
            parts.append("")
            parts.append((t.get("description") or "").strip() or "_(no description)_")
            parts.append("")

    if submissions:
        parts.append("## Submissions")
        parts.append("")
        for s in submissions:
            kind = getattr(s, "kind", "patch")
            name = getattr(s, "filename", "work")
            ts = getattr(s, "ts", "")
            lines = getattr(s, "lines", 0)
            parts.append(f"- `{name}` ({kind}, {lines} lines, {ts})")
        parts.append("")

    parts.append("## Full transcript")
    parts.append("")
    for m in rows:
        who = _name(getattr(m, "sender", "?"), names)
        kind = getattr(m, "kind", "message")
        ch = getattr(m, "channel", "")
        ts = getattr(m, "ts", "")
        content = (getattr(m, "content", "") or "").rstrip()
        parts.append(f"### {ts} · {kind} · {who} · `{ch}`")
        parts.append("")
        parts.append(content)
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"
