from __future__ import annotations

from typing import Sequence

from sim.core.persona.persona import Persona, RevealRung
from sim.core.ports.llm import LLMClient, LLMMessage
from sim.core.ports.repository import StoredMessage
from sim.core.world.world_state import WorldState


class PersonaResponder:
    """Turns (channel-scoped) history into an in-character reply. Depends only
    on the LLMClient port (DIP); knows nothing of transport or storage.
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def respond(
        self,
        persona: Persona,
        world: WorldState,
        history: Sequence[StoredMessage],
        unlocked: Sequence[RevealRung] = (),
        style: str = "chat",
        posture: str = "",
        extra_context: str = "",
    ) -> str:
        system = persona.system_prompt(
            world, unlocked, style=style, posture=posture,
            extra_context=extra_context)
        messages = [
            LLMMessage(
                role="assistant" if m.sender == persona.key else "user",
                content=m.content,
            )
            for m in history
            if m.kind != "event"
        ]
        return self._llm.complete(system=system, messages=messages)
