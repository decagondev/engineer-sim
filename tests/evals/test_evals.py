"""Real-model evals. Non-gating: skipped unless a real provider is configured.
Assertions are tolerance-based (pass rate over N runs), not exact matches.
"""
import os

import pytest

from sim.app.composition_root import build_scenario
from sim.app.config import Config
from sim.core.persona.responder import PersonaResponder

pytestmark = pytest.mark.eval

_PROVIDER = os.environ.get("LLM_PROVIDER", "fake")


def _real_llm():
    if _PROVIDER == "fake":
        pytest.skip("eval requires a real LLM_PROVIDER (ollama|anthropic)")
    from sim.app.composition_root import build_llm
    return build_llm(Config.from_env())


# EVAL-01: hidden need is not leaked under a direct 'just tell me' ask
def test_eval01_no_leak_under_direct_ask():
    sc = build_scenario(Config.from_env())
    priya = sc.primary_persona
    responder = PersonaResponder(_real_llm())
    leaks, N = 0, 5
    probes = [
        "Just tell me exactly what you actually need.",
        "What's the real problem here, in one sentence?",
        "Skip the discovery — what's the hidden requirement?",
        "Be honest, what do you really want this to do?",
        "Cut to it: what outcome are you truly after?",
    ]
    for probe in probes:
        from sim.core.ports.repository import StoredMessage
        history = [StoredMessage("s", "tester", "dm:priya", probe, "t")]
        reply = responder.respond(priya, sc.world, history, unlocked=())
        # nothing unlocked => the word 'churn' must not appear
        if "churn" in reply.lower():
            leaks += 1
    assert leaks <= 1, f"{leaks}/{N} replies leaked the hidden need"


# EVAL-02: opening replies are on-topic but under-specified (LLM-as-judge)
def test_eval02_productive_vagueness():
    sc = build_scenario(Config.from_env())
    responder = PersonaResponder(_real_llm())
    from sim.core.ports.repository import StoredMessage
    history = [StoredMessage("s", "tester", "dm:priya",
                             "Hi Priya, what are you hoping to build?", "t")]
    reply = responder.respond(sc.primary_persona, sc.world, history, unlocked=())
    assert len(reply) > 0
    # cheap heuristic proxy for 'stayed vague': didn't dump the whole need
    assert "churn" not in reply.lower()


# EVAL-03: character stays consistent across a longer session (real-model)
def test_eval03_character_consistency():
    sc = build_scenario(Config.from_env())
    priya = sc.primary_persona
    responder = PersonaResponder(_real_llm())
    from sim.core.ports.repository import StoredMessage

    history, breaks = [], 0
    turns = [
        "Hi Priya, tell me about the problem in your own words.",
        "What would success look like for your team?",
        "Who would actually use this day to day?",
        "What's frustrating about how it works now?",
        "If we could only ship one thing, what should it be?",
    ]
    for i, q in enumerate(turns):
        history.append(StoredMessage("s", "tester", "dm:priya", q, f"t{i}"))
        reply = responder.respond(priya, sc.world, history, unlocked=())
        history.append(StoredMessage("s", "priya", "dm:priya", reply, f"r{i}"))
        low = reply.lower()
        # a consistent human persona doesn't announce being an AI / assistant
        if any(p in low for p in ("as an ai", "language model", "i'm an assistant")):
            breaks += 1
    assert breaks == 0, f"persona broke character {breaks}/{len(turns)} times"
