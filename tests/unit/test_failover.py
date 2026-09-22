"""Model failover chain and the learner-key fallback."""
import pytest

from sim.adapters.llm.failover import FailoverLLMClient, is_transient
from sim.adapters.llm.scoped_client import ScopedLLMClient
from sim.app.composition_root import build_llm
from sim.app.config import Config


class Flaky:
    def __init__(self, error=None, reply="ok"):
        self.error, self.reply, self.calls = error, reply, 0

    def complete(self, *, system, messages):
        self.calls += 1
        if self.error:
            raise RuntimeError(self.error)
        return self.reply


def test_fo01_transient_detection():
    assert is_transient(RuntimeError("Groq returned 429: rate limit reached"))
    assert is_transient(TimeoutError("request timed out"))
    assert not is_transient(RuntimeError("Your Groq API key was rejected"))


def test_fo02_chain_falls_over_and_records_it():
    a, b, c = Flaky("429 rate limit"), Flaky("503 overloaded"), Flaky(None, "from c")
    chain = FailoverLLMClient(a, [("b", b), ("c", c)], primary_name="groq")
    assert chain.complete(system="s", messages=[]) == "from c"
    assert chain.failovers == 1 and chain.last_failover["from"] == "b" and chain.last_failover["to"] == "c"
    assert chain.chain == ["groq", "b", "c"]
    # a non-transient error is not masked
    bad = FailoverLLMClient(Flaky("key was rejected"), [("c", c)])
    with pytest.raises(RuntimeError, match="rejected"):
        bad.complete(system="s", messages=[])
    # every link transient: the last error surfaces
    dead = FailoverLLMClient(Flaky("429"), [("b", Flaky("503"))])
    with pytest.raises(RuntimeError, match="503"):
        dead.complete(system="s", messages=[])


def test_fo03_build_llm_wraps_when_configured():
    plain = build_llm(Config(llm_provider="fake"))
    assert not isinstance(plain, FailoverLLMClient)
    chain = build_llm(Config(llm_provider="fake", llm_fallback_providers="ollama, fake"))
    assert isinstance(chain, FailoverLLMClient) and chain.chain == ["fake", "ollama"]


def test_fo04_learner_key_falls_back_on_rate_limit(monkeypatch):
    class RateLimited:
        def __init__(self, model, api_key): pass
        def complete(self, *, system, messages): raise RuntimeError("Groq returned 429")
    monkeypatch.setattr("sim.adapters.llm.groq_client.GroqClient", RateLimited)
    classroom = Flaky(None, "classroom")
    client = ScopedLLMClient(classroom, resolve_key=lambda: "gsk_user", groq_model="m")
    assert client.complete(system="s", messages=[]) == "classroom"

    class Rejected(RateLimited):
        def complete(self, *, system, messages): raise RuntimeError("key was rejected")
    monkeypatch.setattr("sim.adapters.llm.groq_client.GroqClient", Rejected)
    with pytest.raises(RuntimeError, match="rejected"):
        client.complete(system="s", messages=[])
