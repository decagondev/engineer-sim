"""Mail surface tests: compose/reply, email register, director email, transcript."""
from sim.adapters.llm.fake_client import FakeLLMClient
from sim.adapters.persistence.memory_mail import InMemoryMailStore
from sim.adapters.persistence.memory_repo import InMemoryMessageRepository
from sim.adapters.persistence.memory_state import InMemoryUnlockStore
from sim.core.director.director import Director
from sim.core.director.events import Event
from sim.core.director.triggers import TurnCountTrigger
from sim.core.mail.mail_service import MailService
from sim.core.persona.persona import Persona
from sim.core.persona.responder import PersonaResponder
from sim.core.persona.unlock import UnlockEvaluator
from sim.core.session.session_service import SessionService
from sim.core.world.world_state import WorldState


def _counter():
    n = {"i": 0}
    def clock():
        n["i"] += 1
        return f"t{n['i']:03d}"
    return clock


def _cast():
    return {
        "priya": Persona("priya", "Priya", "Head of CS", "warm", "wants a dashboard"),
        "dana": Persona("dana", "Dana", "Finance", "formal", "cost conscious"),
    }


def _mail(reply="Hi,\n\nOK.\n\nPriya"):
    repo = InMemoryMessageRepository()
    return MailService(
        writer=repo, reader=repo, mail_store=InMemoryMailStore(),
        responder=PersonaResponder(FakeLLMClient(default=reply)),
        unlock_store=InMemoryUnlockStore(), world=WorldState(),
        cast=_cast(), clock=_counter()), repo


# MAIL-01: compose creates a thread with the tester's email + a persona reply
def test_mail01_compose():
    mail, repo = _mail()
    t = mail.compose("s", "priya", "Question", "What should this drive?")
    senders = [e["sender"] for e in t["emails"]]
    assert senders == ["tester", "priya"]
    assert t["with_name"] == "Priya"


# MAIL-02: persona replies use the EMAIL register (system prompt differs)
def test_mail02_email_register_used():
    spy = FakeLLMClient(default="Hi,\n\nSure.\n\nPriya")
    repo = InMemoryMessageRepository()
    mail = MailService(writer=repo, reader=repo, mail_store=InMemoryMailStore(),
                       responder=PersonaResponder(spy), unlock_store=InMemoryUnlockStore(),
                       world=WorldState(), cast=_cast(), clock=_counter())
    mail.compose("s", "priya", "Q", "hello")
    assert "formal but concise email" in spy.calls[0]["system"]


# MAIL-03: emails are recorded in the transcript (kind 'email') for grading
def test_mail03_emails_in_transcript():
    mail, repo = _mail()
    mail.compose("s", "priya", "Q", "hello")
    emails = [m for m in repo.list_for_session("s") if m.kind == "email"]
    assert len(emails) == 2 and all(m.channel.startswith("mail:") for m in emails)


# MAIL-04: reply extends the same thread
def test_mail04_reply():
    mail, repo = _mail()
    t = mail.compose("s", "priya", "Q", "hello")
    t2 = mail.reply("s", t["id"], "thanks, follow-up")
    assert [e["sender"] for e in t2["emails"]] == ["tester", "priya", "tester", "priya"]


# MAIL-05: unread tracking — a persona email is unread until opened
def test_mail05_unread():
    mail, repo = _mail()
    mail.send_from_persona("s", "dana", "Budget", "please confirm scope")
    assert mail.unread("s") == 1
    tid = mail.list_threads("s")[0]["id"]
    mail.open_thread("s", tid)
    assert mail.unread("s") == 0


# MAIL-06: a director EMAIL event routes to mail (not chat) and fires once
def test_mail06_director_email_event():
    repo = InMemoryMessageRepository()
    mstore = InMemoryMailStore()
    cast = _cast()
    mail = MailService(writer=repo, reader=repo, mail_store=mstore,
                       responder=PersonaResponder(FakeLLMClient(default="x")),
                       unlock_store=InMemoryUnlockStore(), world=WorldState(),
                       cast=cast, clock=_counter())
    ev = Event("dana_email", "dana", "general", "confirm scope",
               kind="email", subject="Budget")
    director = Director([(TurnCountTrigger(at=1), ev)])
    svc = SessionService(writer=repo, reader=repo,
                         responder=PersonaResponder(FakeLLMClient(default="reply")),
                         unlock_store=InMemoryUnlockStore(),
                         unlock_evaluator=UnlockEvaluator(FakeLLMClient(default="NO")),
                         world=WorldState(), cast=cast, director=director,
                         mail_service=mail, clock=_counter())
    appended = svc.post_tester_message("s", "hi", target="priya")
    # the email went to mail, NOT to the chat stream
    assert all(m.sender != "dana" for m in appended)
    assert mail.unread("s") == 1 and mail.list_threads("s")[0]["subject"] == "Budget"
    # fires once
    svc.post_tester_message("s", "again", target="priya")
    assert len(mail.list_threads("s")) == 1
