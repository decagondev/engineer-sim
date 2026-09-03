from __future__ import annotations

from sim.core.persona.persona import RevealRung
from sim.core.ports.llm import LLMClient, LLMMessage

_JUDGE_SYSTEM = (
    "You judge whether an engineer's message counts as a good discovery "
    "question that gets at a specific hidden need. Answer with exactly YES or NO."
)


class UnlockEvaluator:
    """Decides whether the tester's latest message unlocks the next rung.

    Uses the LLMClient port so it is testable with a scripted fake (LSP/DIP).
    Single responsibility: the unlock decision — nothing else.
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def unlocks(self, question: str, rung: RevealRung) -> bool:
        prompt = (
            f"Hidden need to probe: {rung.unlock_when}\n"
            f"Engineer's message: {question}\n"
            "Does the message specifically get at that hidden need? YES or NO."
        )
        out = self._llm.complete(
            system=_JUDGE_SYSTEM, messages=[LLMMessage("user", prompt)]
        )
        return out.strip().upper().startswith("Y")
