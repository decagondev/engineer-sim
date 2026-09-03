"""Ticket board tests — seed, create, move, transcript recording."""
from sim.adapters.persistence.memory_repo import InMemoryMessageRepository
from sim.adapters.persistence.memory_tickets import InMemoryTicketStore
from sim.core.persona.persona import Persona
from sim.core.tickets.ticket_service import TicketService


def _svc(seed=()):
    repo = InMemoryMessageRepository()
    cast = {"priya": Persona("priya", "Priya", "Head of CS", "warm", "brief")}
    return TicketService(store=InMemoryTicketStore(), writer=repo, cast=cast,
                         seed_tickets=tuple(seed), clock=lambda: "t"), repo


def test_tk01_seed_on_first_board():
    svc, _ = _svc([{"title": "Dashboard", "created_by": "priya"}])
    board = svc.board("s")
    todo = board["columns"][0]
    assert todo["status"] == "todo"
    assert todo["tickets"][0]["title"] == "Dashboard"
    assert todo["tickets"][0]["by_name"] == "Priya"
    # seeding is idempotent (second call doesn't duplicate)
    assert len(svc.board("s")["columns"][0]["tickets"]) == 1


def test_tk02_create_records_transcript():
    svc, repo = _svc()
    svc.create("s", "Ship at-risk email", "MVP")
    board = svc.board("s")
    assert board["columns"][0]["tickets"][0]["title"] == "Ship at-risk email"
    events = [m for m in repo.list_for_session("s") if m.kind == "ticket"]
    assert any("created ticket" in m.content for m in events)


def test_tk03_move_between_columns_and_records():
    svc, repo = _svc()
    t = svc.create("s", "Task", "")
    svc.move("s", t.id, "doing")
    board = svc.board("s")
    cols = {c["status"]: c["tickets"] for c in board["columns"]}
    assert len(cols["doing"]) == 1 and len(cols["todo"]) == 0
    assert any("-> doing" in m.content for m in repo.list_for_session("s") if m.kind == "ticket")


def test_tk04_bad_status_rejected():
    svc, _ = _svc()
    t = svc.create("s", "Task", "")
    import pytest
    with pytest.raises(ValueError):
        svc.move("s", t.id, "archived")


def test_tk05_seed_not_blocked_by_a_prior_ticket():
    # a director/persona ticket arriving first must NOT suppress the seeds
    svc, _ = _svc([{"title": "Seeded A", "created_by": "priya"},
                   {"title": "Seeded B", "created_by": "system"}])
    svc.file_from("s", "Scope creep", "extra", "priya")   # arrives before board()
    todo = [t["title"] for t in svc.board("s")["columns"][0]["tickets"]]
    assert "Seeded A" in todo and "Seeded B" in todo and "Scope creep" in todo
