"""Adaptive difficulty: level scales pressure, posture, and grading."""
from sim.core.director.director import Director
from sim.core.director.events import Event
from sim.core.director.triggers import TurnContext, TurnCountTrigger
from sim.core.levels import DEFAULT_LEVEL, PROFILES, profile, rank
from sim.core.persona.persona import Persona
from sim.core.world.world_state import WorldState
from sim.adapters.persistence.memory_settings import InMemorySettingsStore
from sim.core.ports.settings import InstructorSettings


# LEVEL-01: min_level gates a beat by seniority
def test_level01_min_level_gate():
    trig = TurnCountTrigger(at=1, min_level="senior")
    assert trig.evaluate(TurnContext(tester_turns=5, level="junior")) is False
    assert trig.evaluate(TurnContext(tester_turns=5, level="senior")) is True
    assert trig.evaluate(TurnContext(tester_turns=5, level="staff")) is True


# LEVEL-02: beat timing scales with level (juniors get beats later)
def test_level02_timing_scales():
    trig = TurnCountTrigger(at=4)   # base threshold
    # intern scale 1.8 -> ~7; senior 1.0 -> 4; distinguished 0.6 -> ~2
    assert trig.evaluate(TurnContext(4, level="senior")) is True
    assert trig.evaluate(TurnContext(4, level="intern")) is False      # not yet
    assert trig.evaluate(TurnContext(7, level="intern")) is True
    assert trig.evaluate(TurnContext(3, level="distinguished")) is True


# LEVEL-03: posture text lands in the persona prompt
def test_level03_posture_in_prompt():
    p = Persona("priya", "Priya", "Head of CS", "warm", "brief")
    prompt = p.system_prompt(WorldState(), posture=profile("intern").posture)
    assert "intern" in prompt.lower()
    plain = p.system_prompt(WorldState())
    assert "intern" not in plain.lower()


# LEVEL-04: ranks are ordered and profiles complete
def test_level04_profiles():
    assert rank("intern") < rank("mid") < rank("staff") < rank("distinguished")
    for k, prof in PROFILES.items():
        assert prof.posture and prof.expectation and prof.beat_scale > 0
    assert profile("nonsense").key == DEFAULT_LEVEL   # safe fallback


# LEVEL-05: settings store round-trips instructor + session level
def test_level05_settings_store():
    s = InMemorySettingsStore()
    assert s.get_instructor().onboarded is False        # first run
    s.set_instructor(InstructorSettings(onboarded=True, default_level="staff"))
    assert s.get_instructor().onboarded is True
    assert s.get_instructor().default_level == "staff"
    assert s.get_session_level("s1") is None
    s.set_session_level("s1", "intern")
    assert s.get_session_level("s1") == "intern"


# LEVEL-06: director fires level-appropriate beats end to end
def test_level06_director_respects_level():
    from sim.adapters.persistence.memory_repo import InMemoryMessageRepository
    from sim.core.ports.repository import StoredMessage
    repo = InMemoryMessageRepository()
    for i in range(6):
        repo.append(StoredMessage("s", "tester", "dm:priya", f"q{i}", f"t{i}"))
    rules = [
        (TurnCountTrigger(at=3, min_level="intern"), Event("a", "m", "c", "hi")),
        (TurnCountTrigger(at=4, min_level="senior"), Event("b", "d", "c", "hi")),
    ]
    d = Director(rules)
    fired_intern = {e.event_id for e in d.after_turn("s", repo, {}, level="intern")}
    fired_senior = {e.event_id for e in d.after_turn("s", repo, {}, level="senior")}
    assert fired_intern == {"a"}              # senior-only beat gated out
    assert fired_senior == {"a", "b"}
