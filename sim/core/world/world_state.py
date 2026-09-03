from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorldState:
    """Single source of truth for shared facts (deadline, budget, ...).

    Injected identically into every persona so they can't contradict each other.
    """

    facts: dict[str, str] = field(default_factory=dict)

    def render(self) -> str:
        if not self.facts:
            return "(no shared facts defined)"
        return "\n".join(f"- {k}: {v}" for k, v in sorted(self.facts.items()))
