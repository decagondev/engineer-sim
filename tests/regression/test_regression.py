"""Regression suite — guards specific behaviors. Deterministic (FakeLLMClient).
Real-model behavior lives in tests/evals (non-gating).
"""
from sim.adapters.llm.anthropic_client import AnthropicClient
from sim.adapters.llm.fake_client import FakeLLMClient
from sim.adapters.llm.groq_client import GroqClient
from sim.adapters.llm.ollama_client import OllamaClient
from sim.adapters.persistence.memory_repo import InMemoryMessageRepository
from sim.adapters.persistence.memory_state import InMemoryUnlockStore
from sim.core.director.director import Director
from sim.core.director.events import Event
from sim.core.director.triggers import TurnContext, TurnCountTrigger
from sim.core.grading.grader import LLMGrader
from sim.core.grading.rubric import Rubric
from sim.core.persona.persona import Persona, RevealRung
from sim.core.persona.responder import PersonaResponder
from sim.core.persona.unlock import UnlockEvaluator
from sim.core.ports.llm import LLMClient, LLMMessage
from sim.core.ports.repository import StoredMessage
from sim.core.session.session_service import SessionService
from sim.core.world.world_state import WorldState


def _counter():
    n = {"i": 0}

    def clock():
        n["i"] += 1
        return f"t{n['i']:03d}"

    return clock


def _persona(**kw):
    base = dict(key="priya", name="Priya", role="Head of CS", voice="warm",
                public_brief="I want a dashboard")
    base.update(kw)
    return Persona(**base)


def _service(reply="ok", judge="NO", clock=None):
    repo = InMemoryMessageRepository()
    p = _persona(
        hidden_need="churn early-warning",
        reveal_ladder=(RevealRung("asks who uses it", "the team is reactive"),),
    )
    svc = SessionService(
        writer=repo, reader=repo,
        responder=PersonaResponder(FakeLLMClient(default=reply)),
        unlock_store=InMemoryUnlockStore(),
        unlock_evaluator=UnlockEvaluator(FakeLLMClient(default=judge)),
        world=WorldState(facts={"deadline": "6 weeks"}),
        cast={p.key: p}, clock=clock or _counter(),
    )
    return svc, repo, p


# REG-01: Liskov / provider contract
def test_reg01_providers_satisfy_llm_port():
    for c in (FakeLLMClient(), OllamaClient(), AnthropicClient(), GroqClient()):
        assert isinstance(c, LLMClient)


def test_reg01_fake_returns_str():
    assert FakeLLMClient(responses=["x"]).complete(
        system="s", messages=[LLMMessage("user", "hi")]) == "x"


# REG-02: locked rungs are NEVER in the persona prompt (anti-leak by construction)
def test_reg02_locked_rungs_absent_from_prompt():
    p = _persona(
        hidden_need="churn early-warning",
        reveal_ladder=(RevealRung("asks who uses it",
                                  "SECRET-the-team-is-reactive"),),
    )
    prompt = p.system_prompt(WorldState())            # nothing unlocked
    assert "SECRET-the-team-is-reactive" not in prompt
    assert "churn early-warning" not in prompt        # hidden_need never leaks
    prompt2 = p.system_prompt(WorldState(), p.reveal_ladder)  # unlocked
    assert "SECRET-the-team-is-reactive" in prompt2


# REG-03: reveal ladder unlocks only on a good question
def test_reg03_ladder_unlocks_on_good_question():
    svc, repo, p = _service(judge="YES")
    svc.post_tester_message("s", "who uses this and when?", target="priya")
    events = [m for m in repo.list_for_session("s") if m.kind == "event"]
    assert any("opened up" in m.content for m in events)


def test_reg03_ladder_stays_locked_on_bad_question():
    svc, repo, p = _service(judge="NO")
    svc.post_tester_message("s", "make it blue", target="priya")
    events = [m for m in repo.list_for_session("s") if m.kind == "event"]
    assert not any("opened up" in m.content for m in events)


# REG-04: world state is the single source, injected identically
def test_reg04_world_state_injected_identically():
    world = WorldState(facts={"deadline": "6 weeks", "budget": "1 eng"})
    a, b = _persona(key="a"), _persona(key="b", name="B")
    rendered = world.render()
    assert rendered in a.system_prompt(world) and rendered in b.system_prompt(world)


# REG-05: director fires an event exactly once
def test_reg05_director_fires_once():
    trigger = TurnCountTrigger(at=2)
    event = Event("stake", "marcus", "dm:priya", "how big is this?")
    director = Director([(trigger, event)])
    repo = InMemoryMessageRepository()
    # simulate two tester turns
    for i in range(2):
        repo.append(StoredMessage("s", "tester", "dm:priya", f"q{i}", f"t{i}"))
    fired1 = director.after_turn("s", repo, {})
    assert len(fired1) == 1 and fired1[0].event_id == "stake"
    # record the fired marker as the service would, then re-check: no re-fire
    repo.append(StoredMessage("s", "system", "dm:priya", "[fired:stake]", "tx",
                              kind="event"))
    assert director.after_turn("s", repo, {}) == []


def test_reg05_trigger_ocp_new_kind_needs_no_director_change():
    class DummyTrigger(TurnCountTrigger):
        pass
    d = Director([(DummyTrigger(at=1), Event("x", "p", "c", "hi"))])
    repo = InMemoryMessageRepository()
    repo.append(StoredMessage("s", "tester", "c", "q", "t"))
    assert len(d.after_turn("s", repo, {})) == 1


# REG-06: director-injected message is streamed and recorded
def test_reg06_director_message_appended_on_turn():
    trigger = TurnCountTrigger(at=1)
    event = Event("stake", "marcus", "dm:priya", "how big is this?")
    repo = InMemoryMessageRepository()
    p = _persona()
    svc = SessionService(
        writer=repo, reader=repo,
        responder=PersonaResponder(FakeLLMClient(default="sure")),
        unlock_store=InMemoryUnlockStore(),
        unlock_evaluator=UnlockEvaluator(FakeLLMClient(default="NO")),
        world=WorldState(), cast={p.key: p}, director=Director([(trigger, event)]),
        clock=_counter(),
    )
    appended = svc.post_tester_message("s", "hi", target="priya")
    senders = [m.sender for m in appended]
    assert "marcus" in senders


# REG-07: transcript ordered, complete, timestamped
def test_reg07_transcript_ordered_and_complete():
    svc, repo, p = _service(reply="r", judge="NO", clock=_counter())
    svc.start("s")
    svc.post_tester_message("s", "m1", target="priya")
    svc.end("s")
    t = svc.export("s")
    ids = [m["id"] for m in t]
    assert ids == sorted(ids)
    assert all(m["ts"] for m in t)
    assert t[0]["kind"] == "event" and t[-1]["kind"] == "event"


# REG-08: grader is read-only over MessageReader (ISP) + clamps + weights
def test_reg08_grader_weighting_and_clamping():
    rubric = Rubric.from_list([
        {"key": "a", "weight": 3.0, "description": "d"},
        {"key": "b", "weight": 1.0, "description": "d"},
    ])
    grade_json = ('{"scores":[{"key":"a","score":1.5,"evidence":"e"},'
                  '{"key":"b","score":0.0,"evidence":"e"}],"summary":"s"}')
    repo = InMemoryMessageRepository()
    repo.append(StoredMessage("s", "tester", "c", "hi", "t"))
    grade = LLMGrader(FakeLLMClient(responses=[grade_json])).grade("s", repo, rubric)
    # 1.5 clamps to 1.0; weighted total = (1.0*3 + 0.0*1)/4 = 0.75
    assert abs(grade.total - 0.75) < 1e-9
    assert all(0.0 <= s.score <= 1.0 for s in grade.scores)
