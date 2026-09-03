"""Director ticket event: a persona files a scope-creep ticket, once, recorded."""
from sim.adapters.llm.fake_client import FakeLLMClient
from sim.adapters.persistence.memory_repo import InMemoryMessageRepository
from sim.adapters.persistence.memory_state import InMemoryUnlockStore
from sim.adapters.persistence.memory_tickets import InMemoryTicketStore
from sim.core.director.director import Director
from sim.core.director.events import Event
from sim.core.director.triggers import TurnCountTrigger
from sim.core.persona.persona import Persona
from sim.core.persona.responder import PersonaResponder
from sim.core.persona.unlock import UnlockEvaluator
from sim.core.session.session_service import SessionService
from sim.core.tickets.ticket_service import TicketService
from sim.core.world.world_state import WorldState


def _counter():
    n = {"i": 0}
    def c():
        n["i"] += 1
        return f"t{n['i']:03d}"
    return c


def test_director_files_ticket_once():
    repo = InMemoryMessageRepository()
    cast = {"priya": Persona("priya", "Priya", "Head of CS", "warm", "brief")}
    tickets = TicketService(store=InMemoryTicketStore(), writer=repo, cast=cast,
                            clock=_counter())
    ev = Event("scope", "priya", "dm:priya", "also add revenue chart",
               kind="ticket", subject="Revenue chart too?")
    director = Director([(TurnCountTrigger(at=1), ev)])
    svc = SessionService(
        writer=repo, reader=repo,
        responder=PersonaResponder(FakeLLMClient(default="ok")),
        unlock_store=InMemoryUnlockStore(),
        unlock_evaluator=UnlockEvaluator(FakeLLMClient(default="NO")),
        world=WorldState(), cast=cast, director=director,
        ticket_service=tickets, clock=_counter())

    appended = svc.post_tester_message("s", "hi", target="priya")
    # the ticket did NOT go to the chat stream
    assert all(m.channel == "dm:priya" and m.sender in ("tester", "priya")
               for m in appended)
    # it landed on the board, attributed to Priya, in To Do
    board = tickets.board("s")
    todo = board["columns"][0]["tickets"]
    assert any(t["title"] == "Revenue chart too?" and t["by_name"] == "Priya"
               for t in todo)
    # a chat signal announced it
    events = [m for m in repo.list_for_session("s") if m.kind == "event"]
    assert any("filed a ticket" in m.content for m in events)
    # fires exactly once
    svc.post_tester_message("s", "again", target="priya")
    assert len(tickets.board("s")["columns"][0]["tickets"]) == 1
