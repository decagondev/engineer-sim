from sim.adapters.auth.secretbox import decrypt_secret, encrypt_secret
from sim.adapters.llm.request_context import current_uid, set_current_uid
from sim.adapters.llm.scoped_client import ScopedLLMClient, user_key_resolver
from sim.adapters.persistence.sqlite_users import InMemoryUserDirectory
from sim.core.ports.users import UserRecord


def test_secretbox_roundtrip_and_bad_token():
    token = encrypt_secret("unit-secret", "gsk_live")
    assert token != "gsk_live"
    assert decrypt_secret("unit-secret", token) == "gsk_live"
    try:
        decrypt_secret("other-secret", token)
        assert False, "expected decrypt failure"
    except ValueError:
        pass


def test_scoped_llm_uses_user_key(monkeypatch):
    seen = {}

    class Fallback:
        def complete(self, *, system, messages):
            seen["used"] = "fallback"
            return "fallback"

    class FakeGroq:
        def __init__(self, model, api_key):
            seen["key"] = api_key

        def complete(self, *, system, messages):
            seen["used"] = "byok"
            return "byok"

    monkeypatch.setattr("sim.adapters.llm.groq_client.GroqClient", FakeGroq)
    users = InMemoryUserDirectory()
    secret = "unit-secret"
    users.upsert(UserRecord(
        "c1", "c@t.local", "challenger",
        groq_key_enc=encrypt_secret(secret, "gsk_user")))
    client = ScopedLLMClient(
        Fallback(), resolve_key=user_key_resolver(users, secret), groq_model="x")
    set_current_uid("c1")
    assert client.complete(system="s", messages=[]) == "byok"
    assert seen["key"] == "gsk_user" and seen["used"] == "byok"
    set_current_uid("")
    assert client.complete(system="s", messages=[]) == "fallback"
    current_uid.set("")


def test_scoped_llm_swallows_corrupt_key():
    class Fallback:
        def complete(self, *, system, messages):
            return "fallback"

    users = InMemoryUserDirectory()
    users.upsert(UserRecord("c1", "c@t.local", "challenger", groq_key_enc="not-fernet"))
    client = ScopedLLMClient(
        Fallback(), resolve_key=user_key_resolver(users, "unit-secret"), groq_model="x")
    set_current_uid("c1")
    assert client.complete(system="s", messages=[]) == "fallback"
    current_uid.set("")
