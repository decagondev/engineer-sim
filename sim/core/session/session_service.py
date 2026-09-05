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
    track: str = "product"
    role_label: str = "Engineer"
    clock: Callable[[], str] = _utcnow_iso
    design_lookup: Optional[Callable[[str], str]] = None
    _designs: dict = field(default_factory=dict)
    _diagrams: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.primary_key:
            self.primary_key = next(iter(self.cast))

    # -- lifecycle ---------------------------------------------------------
    def start(self, session_id: str) -> None:
        names = ", ".join(p.name for p in self.cast.values())
        self._event(session_id, "general", f"Session started. Online: {names}.")
        if self.track == "systems":
            self._event(
                session_id, "general",
                f"You are the {self.role_label}. Discover the real constraints, "
                "write a design in the starter docs, submit it, and defend it "
                "when the team pushes back.",
            )
        elif self.track == "interview":
            self._event(
                session_id, "general",
                f"You are the {self.role_label}. This is a timed system-design "
                "interview. Ask clarifying questions, write a detailed DESIGN.md, "
                "submit it, then defend your decisions with the assessor. "
                "The interviewer will not hand you the architecture.",
            )
        if self.ticket_service is not None:
            self.ticket_service.seed(session_id)
        if self.track == "interview":
            self._run_director(session_id, self.level(session_id), phase="start")

    def end(self, session_id: str) -> None:
        self._event(session_id, "general", "Session ended.")

    # -- main turn ---------------------------------------------------------
    def post_tester_message(
        self, session_id: str, content: str, target: str | None = None,
    ) -> list[StoredMessage]:
        persona = self.cast[target or self.primary_key]
        channel = _dm_channel(persona.key)

        self._msg(session_id, "tester", channel, content)

        if (self.track == "interview" and persona.lane == "assessor"
                and not self._assessment_open(session_id)):
            ev = self._event(
                session_id, channel,
                "[reveal] The assessor joins after you submit DESIGN.md and "
                "tell the interviewer you are done.",
            )
            return [ev]

        self._maybe_unlock(session_id, persona, content, channel)

        unlocked = persona.reveal_ladder[
            : self.unlock_store.get_unlocked(session_id, persona.key)
        ]
        history = [
            m for m in self.reader.list_for_session(session_id)
            if m.channel == channel
        ]
        level = self.level(session_id)
        extra = self._assessor_context(session_id) if persona.lane == "assessor" else ""
        reply_text = self.responder.respond(
            persona, self.world, history, unlocked,
            posture=self._posture(level, persona), extra_context=extra)
        appended = [self._msg(session_id, persona.key, channel, reply_text)]
        appended.extend(self._run_director(session_id, level))
        appended.extend(self._maybe_ready(session_id, content, channel))
        return appended

    def after_submission(self, session_id: str) -> list[StoredMessage]:
        """Director beats that wait for a submitted design/patch."""
        appended = self._run_director(session_id, self.level(session_id))
        appended.extend(self.maybe_begin_assessment(session_id))
        return appended

    def remember_design(self, session_id: str, text: str) -> None:
        if text and text.strip():
            self._designs[session_id] = text

    def remember_diagram(self, session_id: str, mermaid: str) -> None:
        if mermaid and mermaid.strip():
            self._diagrams[session_id] = mermaid.strip()

    def design_text(self, session_id: str) -> str:
        if session_id in self._designs:
            return self._designs[session_id]
        if self.design_lookup is not None:
            found = self.design_lookup(session_id) or ""
            if found.strip():
                self._designs[session_id] = found
                return found
        return ""

    def diagram_text(self, session_id: str) -> str:
        return self._diagrams.get(session_id, "")

    def maybe_begin_assessment(self, session_id: str) -> list[StoredMessage]:
        if self.track != "interview" or self._assessment_open(session_id):
            return []
        design = self.design_text(session_id)
        if not design.strip():
            return []
        assessor = next((p for p in self.cast.values() if p.lane == "assessor"), None)
        if assessor is None:
            return []
        channel = _dm_channel(assessor.key)
        self._event(session_id, "general", "[fired:assessment_open]")
        self._event(
            session_id, channel,
            f"[reveal] {assessor.name} is here to assess your design.",
        )
        history = [
            m for m in self.reader.list_for_session(session_id)
            if m.channel == channel
        ]
        q = self.responder.respond(
            assessor, self.world, history, unlocked=(),
            posture=self._posture(self.level(session_id), assessor),
            extra_context=self._assessor_context(session_id),
        )
        return [self._msg(session_id, assessor.key, channel, q)]

    def _maybe_ready(self, session_id, content, channel) -> list[StoredMessage]:
        if self.track != "interview":
            return []
        from sim.core.session.interview import signals_design_ready
        if not signals_design_ready(content):
            return []
        self._event(session_id, channel, "[ready:design]")
        if not self.design_text(session_id):
            return [self._event(
                session_id, channel,
                "[reveal] Submit DESIGN.md (Submit app) so the assessor can "
                "read it, then the defense will begin.",
            )]
        return self.maybe_begin_assessment(session_id)

    def _assessment_open(self, session_id: str) -> bool:
        return any(
            m.kind == "event" and "[fired:assessment_open]" in m.content
            for m in self.reader.list_for_session(session_id)
        )

    def _assessor_context(self, session_id: str) -> str:
        design = self.design_text(session_id)
        mermaid = self.diagram_text(session_id)
        parts = [
            "THE STUDENT'S DESIGN DOCUMENT (probe THIS; do not invent a better design):",
            design or "(they have not submitted a design yet)",
        ]
        if mermaid:
            parts += ["", "MERMAID OF THEIR DESIGN:", mermaid]
        return "\n".join(parts)

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

    def _posture(self, level: str, persona: Persona | None = None) -> str:
        from sim.core.levels import interview_posture, profile, systems_posture
        if self.track == "interview":
            lane = getattr(persona, "lane", "") if persona else "interviewer"
            return interview_posture(level, lane or "interviewer")
        if self.track == "systems":
            return systems_posture(level)
        return profile(level).posture

    def _run_director(self, session_id: str, level: str,
                      phase: str = "turn") -> list[StoredMessage]:
        appended: list[StoredMessage] = []
        if self.director is None:
            return appended
        for ev in self.director.after_turn(session_id, self.reader,
                                           self.cast, level=level, phase=phase):
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
