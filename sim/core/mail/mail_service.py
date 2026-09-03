from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sim.core.persona.persona import Persona
from sim.core.persona.responder import PersonaResponder
from sim.core.ports.mail import MailStore, MailThread
from sim.core.ports.repository import MessageReader, MessageWriter, StoredMessage
from sim.core.ports.state import UnlockStore
from sim.core.world.world_state import WorldState


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chan(thread_id: str) -> str:
    return f"mail:{thread_id}"


@dataclass
class MailService:
    """Email surface. Slower and more formal than chat, driven by the same
    persona engine. Bodies are recorded as StoredMessages (kind 'email') so the
    grader sees them; thread metadata + read state live in the MailStore.
    """

    writer: MessageWriter
    reader: MessageReader
    mail_store: MailStore
    responder: PersonaResponder
    unlock_store: UnlockStore
    world: WorldState
    cast: dict[str, Persona]
    settings: object = None
    default_level: str = "senior"
    clock: Callable[[], str] = _utcnow_iso

    # -- tester actions ----------------------------------------------------
    def compose(self, session_id: str, to: str, subject: str, body: str) -> dict:
        persona = self.cast[to]
        thread = self.mail_store.create_thread(session_id, subject, to, self.clock())
        self._email(session_id, thread.id, "tester", body)
        self._persona_reply(session_id, persona, thread)
        return self._thread_payload(session_id, thread)

    def reply(self, session_id: str, thread_id: str, body: str) -> dict:
        thread = self.mail_store.get_thread(session_id, thread_id)
        if thread is None:
            raise KeyError(thread_id)
        self._email(session_id, thread_id, "tester", body)
        self._persona_reply(session_id, self.cast[thread.participant], thread)
        return self._thread_payload(session_id, thread)

    def open_thread(self, session_id: str, thread_id: str) -> dict:
        thread = self.mail_store.get_thread(session_id, thread_id)
        if thread is None:
            raise KeyError(thread_id)
        self.mail_store.mark_read(session_id, thread_id, self.clock())
        return self._thread_payload(session_id, thread)

    # -- director-driven inbound (a stakeholder emails you) ----------------
    def send_from_persona(self, session_id: str, persona_key: str,
                          subject: str, body: str) -> MailThread:
        thread = self.mail_store.create_thread(session_id, subject, persona_key,
                                               self.clock())
        self._email(session_id, thread.id, persona_key, body)
        self.mail_store.touch_persona(session_id, thread.id, self.clock())
        return thread

    # -- reads -------------------------------------------------------------
    def list_threads(self, session_id: str) -> list[dict]:
        out = []
        for th in self.mail_store.list_threads(session_id):
            emails = self._emails(session_id, th.id)
            last = emails[-1] if emails else None
            out.append({
                "id": th.id, "subject": th.subject,
                "with": th.participant,
                "with_name": self._name(th.participant),
                "last_from": (last.sender if last else ""),
                "preview": (last.content[:80] if last else ""),
                "count": len(emails),
            })
        return out

    def unread(self, session_id: str) -> int:
        return self.mail_store.unread_count(session_id)

    # -- helpers -----------------------------------------------------------
    def _persona_reply(self, session_id: str, persona: Persona,
                       thread: MailThread) -> StoredMessage:
        history = self._emails(session_id, thread.id)
        unlocked = persona.reveal_ladder[
            : self.unlock_store.get_unlocked(session_id, persona.key)]
        from sim.core.levels import profile
        level = self.default_level
        if self.settings is not None:
            level = (self.settings.get_session_level(session_id)
                     or self.settings.get_instructor().default_level)
        text = self.responder.respond(persona, self.world, history, unlocked,
                                      style="email", posture=profile(level).posture)
        msg = self._email(session_id, thread.id, persona.key, text)
        self.mail_store.touch_persona(session_id, thread.id, self.clock())
        return msg

    def _emails(self, session_id: str, thread_id: str) -> list[StoredMessage]:
        chan = _chan(thread_id)
        return [m for m in self.reader.list_for_session(session_id)
                if m.channel == chan]

    def _email(self, session_id, thread_id, sender, body) -> StoredMessage:
        return self.writer.append(StoredMessage(
            session_id=session_id, sender=sender, channel=_chan(thread_id),
            content=body, ts=self.clock(), kind="email"))

    def _thread_payload(self, session_id: str, thread: MailThread) -> dict:
        return {
            "id": thread.id, "subject": thread.subject,
            "with": thread.participant, "with_name": self._name(thread.participant),
            "emails": [
                {"sender": m.sender,
                 "sender_name": ("You" if m.sender == "tester" else self._name(m.sender)),
                 "body": m.content, "ts": m.ts}
                for m in self._emails(session_id, thread.id)
            ],
        }

    def _name(self, key: str) -> str:
        p = self.cast.get(key)
        return p.name if p else key
