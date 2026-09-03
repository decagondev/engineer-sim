from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from sim.core.world.world_state import WorldState


@dataclass(frozen=True)
class RevealRung:
    """One step of the reveal ladder. `unlock_when` describes the kind of
    question that earns it; `content` is what the persona will then discuss.

    Anti-leak by construction: locked rungs are NEVER placed in the persona's
    prompt, so the model literally cannot reveal what it hasn't been given.
    """

    unlock_when: str
    content: str


@dataclass(frozen=True)
class Persona:
    """A character. Public layer is shared freely; specifics are gated behind
    the reveal ladder. `hidden_need` is ground-truth for grading and is NOT put
    in the persona prompt.
    """

    key: str
    name: str
    role: str
    voice: str
    public_brief: str
    hidden_need: str = ""            # ground truth for the grader, not the persona
    hidden_constraints: str = ""     # ground truth for the grader, not the persona
    reveal_ladder: tuple[RevealRung, ...] = field(default_factory=tuple)

    def system_prompt(self, world: WorldState,
                      unlocked: Sequence[RevealRung] = (),
                      style: str = "chat", posture: str = "") -> str:
        lines = [
            f"You are {self.name}, {self.role}.",
            f"Voice and manner: {self.voice}",
            "",
            "Shared facts everyone on this project knows:",
            world.render(),
            "",
            "What you are happy to say up front:",
            self.public_brief,
        ]
        if unlocked:
            lines += ["", "Because the engineer asked good questions, you can "
                          "now also discuss:"]
            lines += [f"- {r.content}" for r in unlocked]
        guard = ("Only discuss what is listed above. Do not invent extra needs or "
                 "volunteer information you haven't been given here. Stay "
                 "realistically vague — you're busy. Never break the fourth wall "
                 "or mention being an AI.")
        if posture:
            lines += ["", posture]
        if style == "email":
            lines += ["", guard + " Reply as a formal but concise email: a short "
                          "greeting, two to four sentences, then sign off with your "
                          "first name."]
        else:
            lines += ["", guard + " Keep replies short, like chat messages."]
        return "\n".join(lines)
