from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from sim.core.persona.persona import Persona
from sim.core.persona.responder import PersonaResponder
from sim.core.persona.unlock import UnlockEvaluator
from sim.core.ports.repository import MessageReader, MessageWriter, StoredMessage
from sim.core.ports.state import UnlockStore
from sim.core.world.world_state import WorldState


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dm_channel(persona_key: str) -> str:
    return f"dm:{persona_key}"


@dataclass
class SessionService:
    """Orchestrates one run across a cast of personas.

    Application/use-case layer: framework-free, depends only on ports + domain.
    Per turn it (1) records the tester message, (2) evaluates the reveal ladder,
    (3) gets an in-character reply scoped to that persona's channel, and
    (4) lets the director inject events. Returns every message it appended so
    the transport can stream them.
    """

    writer: MessageWriter
    reader: MessageReader
    responder: PersonaResponder
    unlock_store: UnlockStore
    unlock_evaluator: UnlockEvaluator
    world: WorldState
    cast: dict[str, Persona]
    director: Optional[object] = None      # set in Wave 2; duck-typed after_turn
    mail_service: Optional[object] = None  # set in Wave 6; routes email events
    ticket_service: Optional[object] = None  # set in Wave 7; routes ticket events
    settings: Optional[object] = None      # set in Wave 9; per-session level
    default_level: str = "senior"
    primary_key: str = ""
    clock: Callable[[], str] = _utcnow_iso

    def __post_init__(self) -> None:
        if not self.primary_key:
            self.primary_key = next(iter(self.cast))

    # -- lifecycle ---------------------------------------------------------
    def start(self, session_id: str) -> None:
        names = ", ".join(p.name for p in self.cast.values())
        self._event(session_id, "general", f"Session started. Online: {names}.")
        if self.ticket_service is not None:
            self.ticket_service.seed(session_id)

    def end(self, session_id: str) -> None:
        self._event(session_id, "general", "Session ended.")

    # -- main turn ---------------------------------------------------------
    def post_tester_message(
        self, session_id: str, content: str, target: str | None = None,
    ) -> list[StoredMessage]:
        persona = self.cast[target or self.primary_key]
        channel = _dm_channel(persona.key)

        self._msg(session_id, "tester", channel, content)
        self._maybe_unlock(session_id, persona, content, channel)

        unlocked = persona.reveal_ladder[
            : self.unlock_store.get_unlocked(session_id, persona.key)
        ]
        history = [
            m for m in self.reader.list_for_session(session_id)
            if m.channel == channel
        ]
        from sim.core.levels import profile
        level = self.level(session_id)
        posture = profile(level).posture
        reply_text = self.responder.respond(persona, self.world, history,
                                            unlocked, posture=posture)
        appended = [self._msg(session_id, persona.key, channel, reply_text)]

        if self.director is not None:
            for ev in self.director.after_turn(session_id, self.reader,
                                               self.cast, level=level):
                if getattr(ev, "kind", "chat") == "email" and self.mail_service:
                    self.mail_service.send_from_persona(
                        session_id, ev.persona_key, ev.subject, ev.content)
                    self._event(session_id, ev.channel,
                                f"[reveal] {self._name(ev.persona_key)} sent you an email.")
                    self._event(session_id, "general", f"[fired:{ev.event_id}]")
                elif getattr(ev, "kind", "chat") == "ticket" and self.ticket_service:
                    self.ticket_service.file_from(
                        session_id, ev.subject, ev.content, ev.persona_key,
                        issue_type=getattr(ev, "issue_type", "") or "story",
                        priority=getattr(ev, "priority", "") or "high",
                        labels=getattr(ev, "labels", "") or "scope-creep")
                    self._event(session_id, ev.channel,
                                f"[reveal] {self._name(ev.persona_key)} filed a ticket: {ev.subject}")
                    self._event(session_id, "general", f"[fired:{ev.event_id}]")
                else:
                    appended.append(
                        self._msg(session_id, ev.persona_key, ev.channel, ev.content))
                    self._event(session_id, ev.channel, f"[fired:{ev.event_id}]")
        return appended

    # -- reveal ladder -----------------------------------------------------
    def _maybe_unlock(self, session_id, persona: Persona, content, channel) -> None:
        count = self.unlock_store.get_unlocked(session_id, persona.key)
        if count >= len(persona.reveal_ladder):
            return
        next_rung = persona.reveal_ladder[count]
        if self.unlock_evaluator.unlocks(content, next_rung):
            self.unlock_store.set_unlocked(session_id, persona.key, count + 1)
            self._event(
                session_id, channel,
                f"[reveal] {persona.name} opened up (rung {count + 1}).",
            )

    # -- export ------------------------------------------------------------
    def export(self, session_id: str) -> list[dict]:
        return [
            {"id": m.id, "sender": m.sender, "channel": m.channel,
             "content": m.content, "ts": m.ts, "kind": m.kind}
            for m in self.reader.list_for_session(session_id)
        ]

    # -- helpers -----------------------------------------------------------
    def _msg(self, session_id, sender, channel, content) -> StoredMessage:
        return self.writer.append(StoredMessage(
            session_id=session_id, sender=sender, channel=channel,
            content=content, ts=self.clock(), kind="message"))

    def _name(self, key: str) -> str:
        p = self.cast.get(key)
        return p.name if p else key

    def level(self, session_id: str) -> str:
        if self.settings is not None:
            lvl = self.settings.get_session_level(session_id)
            if lvl:
                return lvl
            return self.settings.get_instructor().default_level
        return self.default_level

    def _event(self, session_id, channel, content) -> StoredMessage:
        return self.writer.append(StoredMessage(
            session_id=session_id, sender="system", channel=channel,
            content=content, ts=self.clock(), kind="event"))
