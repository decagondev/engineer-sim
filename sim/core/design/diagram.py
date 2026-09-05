"""Turn a student's design document into a mermaid diagram of THEIR design."""
from __future__ import annotations

from sim.core.ports.llm import LLMClient, LLMMessage
from sim.core.session.interview import extract_mermaid

_FALLBACK = (
    "flowchart TB\n"
    "  Client[Client] --> Svc[Service]\n"
    "  Svc --> Store[Store]"
)

_SYSTEM = (
    "You draw architecture diagrams. Given a student's system-design document, "
    "output ONLY a mermaid flowchart that visualizes THEIR design — the "
    "components and data flows they actually named. Do not invent a better "
    "architecture. Do not add components they did not mention. No prose. "
    "Prefer `flowchart TB`. Keep node labels short. You may use subgraphs "
    "for stores, queues, and clients."
)


def render_design_diagram(llm: LLMClient, design: str) -> str:
    text = (design or "").strip()
    if not text:
        return _FALLBACK
    raw = llm.complete(
        system=_SYSTEM,
        messages=[LLMMessage("user", text[:12000])],
    )
    return extract_mermaid(raw) or _FALLBACK
