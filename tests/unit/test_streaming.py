"""B9: streamed persona replies. The port helper, the Groq SSE adapter, and
the two wrappers (failover, per-user key) with the "never fail over after a
fragment went out" rule."""
import httpx
import pytest

from sim.adapters.llm.fake_client import FakeLLMClient
from sim.adapters.llm.failover import FailoverLLMClient
from sim.adapters.llm.groq_client import GroqClient, _sse_delta
from sim.adapters.llm.scoped_client import ScopedLLMClient
from sim.core.ports.llm import LLMMessage, StreamingLLMClient, complete_with_deltas

MSGS = [LLMMessage("user", "hi")]


class PlainLLM:
    def complete(self, *, system, messages):
        return "whole reply"


def test_st01_helper_uses_stream_when_present_else_one_delta():
    got = []
    assert complete_with_deltas(PlainLLM(), system="s", messages=MSGS, on_delta=got.append) == "whole reply"
    assert got == ["whole reply"]
    assert complete_with_deltas(PlainLLM(), system="s", messages=MSGS) == "whole reply"
    fake = FakeLLMClient(default="one two three four five six")
    assert isinstance(fake, StreamingLLMClient)
    got = []
    out = complete_with_deltas(fake, system="s", messages=MSGS, on_delta=got.append)
    assert "".join(got) == out == "one two three four five six" and len(got) >= 3


def test_st02_sse_parsing():
    assert _sse_delta("") is None and _sse_delta(": keepalive") is None
    assert _sse_delta("data: [DONE]") is None
    assert _sse_delta('data: {"choices":[{"delta":{"role":"assistant"}}]}') == ""
    assert _sse_delta('data: {"choices":[{"delta":{"content":"Hel"}}]}') == "Hel"
    assert _sse_delta("data: not json") is None


def test_st03_groq_stream_over_mock_transport():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        seen["auth"] = request.headers.get("authorization")
        sse = ("data: {\"choices\":[{\"delta\":{\"role\":\"assistant\"}}]}\n\n"
               "data: {\"choices\":[{\"delta\":{\"content\":\"Hello\"}}]}\n\n"
               "data: {\"choices\":[{\"delta\":{\"content\":\", world\"}}]}\n\n"
               "data: [DONE]\n\n")
        return httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})

    client = GroqClient(model="m", api_key="gsk_test", transport=httpx.MockTransport(handler))
    got = []
    out = client.stream(system="s", messages=MSGS, on_delta=got.append)
    assert out == "Hello, world" and got == ["Hello", ", world"]
    assert b'"stream":true' in seen["body"].replace(b" ", b"") and seen["auth"] == "Bearer gsk_test"

    def rate_limited(request):
        return httpx.Response(429, json={"error": {"message": "slow down"}})
    with pytest.raises(RuntimeError) as ei:
        GroqClient(model="m", api_key="k", transport=httpx.MockTransport(rate_limited)).stream(
            system="s", messages=MSGS, on_delta=got.append)
    assert "rate-limited" in str(ei.value)
    # the non-streaming call shares the transport
    def ok(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "plain"}}]})
    assert GroqClient(model="m", api_key="k", transport=httpx.MockTransport(ok)).complete(
        system="s", messages=MSGS) == "plain"


class Boom:
    """Streams `before` fragments, then fails with a transient error."""

    def __init__(self, before=0, text="partial "):
        self.before, self.text = before, text

    def complete(self, *, system, messages):
        raise RuntimeError("429 rate limit")

    def stream(self, *, system, messages, on_delta):
        for _ in range(self.before):
            on_delta(self.text)
        raise RuntimeError("429 rate limit")


def test_st04_failover_streams_and_never_splices_models():
    fb = FakeLLMClient(default="from the fallback model")
    chain = FailoverLLMClient(Boom(before=0), [("fb", fb)], primary_name="p")
    got = []
    assert chain.stream(system="s", messages=MSGS, on_delta=got.append) == "from the fallback model"
    assert "".join(got) == "from the fallback model" and chain.failovers == 1
    # a fragment already reached the reader: the error surfaces, no second model
    chain = FailoverLLMClient(Boom(before=1), [("fb", fb)], primary_name="p")
    got = []
    with pytest.raises(RuntimeError):
        chain.stream(system="s", messages=MSGS, on_delta=got.append)
    assert got == ["partial "] and chain.failovers == 0
    # plain complete still fails over
    assert chain.complete(system="s", messages=MSGS) == "from the fallback model"


def test_st05_scoped_client_streams_with_and_without_a_key(monkeypatch):
    fb = FakeLLMClient(default="classroom reply")
    scoped = ScopedLLMClient(fb, resolve_key=lambda: "", groq_model="m")
    got = []
    assert scoped.stream(system="s", messages=MSGS, on_delta=got.append) == "classroom reply"
    assert "".join(got) == "classroom reply"

    class FakeGroq(Boom):
        def __init__(self, **kw):
            super().__init__(before=0)
    monkeypatch.setattr("sim.adapters.llm.groq_client.GroqClient", FakeGroq)
    scoped = ScopedLLMClient(fb, resolve_key=lambda: "gsk_user", groq_model="m")
    got = []
    assert scoped.stream(system="s", messages=MSGS, on_delta=got.append) == "classroom reply", \
        "a rate-limited personal key falls back to the classroom chain before any fragment"

    class FakeGroqMid(Boom):
        def __init__(self, **kw):
            super().__init__(before=2)
    monkeypatch.setattr("sim.adapters.llm.groq_client.GroqClient", FakeGroqMid)
    with pytest.raises(RuntimeError):
        scoped.stream(system="s", messages=MSGS, on_delta=got.append)
