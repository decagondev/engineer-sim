from __future__ import annotations

from typing import Sequence

from sim.core.director.events import Event
from sim.core.director.triggers import Trigger, TurnContext
from sim.core.ports.repository import MessageReader


class Director:
    """Evaluates trigger/event rules after each turn and fires each event at
    most once. Stateless: 'already fired' is derived from the transcript
    (an event marker `[fired:<id>]`), so it survives reconnects.
    """

    def __init__(self, rules: Sequence[tuple[Trigger, Event]]) -> None:
        self._rules = list(rules)

    def after_turn(self, session_id: str, reader: MessageReader,
                   cast: dict, level: str = "senior") -> list[Event]:
        rows = list(reader.list_for_session(session_id))
        tester_turns = sum(
            1 for m in rows if m.sender == "tester" and m.kind == "message"
        )
        already = {
            m.content for m in rows if m.kind == "event"
            and m.content.startswith("[fired:")
        }
        ctx = TurnContext(tester_turns=tester_turns, level=level)

        fired: list[Event] = []
        for trigger, event in self._rules:
            marker = f"[fired:{event.event_id}]"
            if marker in already:
                continue
            if trigger.evaluate(ctx):
                fired.append(event)
                already.add(marker)  # guard against duplicate rules in one pass
        return fired
