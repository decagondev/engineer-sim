"""Per-user GitHub tokens (BYOK): resolver, request wiring, Settings round trip."""
from fastapi.testclient import TestClient

from sim.adapters.auth.secretbox import encrypt_secret, secret_from_config
from sim.adapters.build.github_api import GitHubApi, user_token_resolver
from sim.adapters.llm.request_context import current_uid, set_current_uid
from sim.adapters.persistence.sqlite_users import InMemoryUserDirectory
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.ports.users import UserRecord


def test_gh_byok01_resolver_prefers_user_token_then_server():
    users = InMemoryUserDirectory()
    users.upsert(UserRecord("c1", "c@t.local", "challenger",
                            github_token_enc=encrypt_secret("s", "ghp_user")))
    users.upsert(UserRecord("c2", "d@t.local", "challenger", github_token_enc="not-fernet"))
    resolve = user_token_resolver(users, "s", "ghp_server")
    set_current_uid("c1"); assert resolve() == "ghp_user"
    set_current_uid("c2"); assert resolve() == "ghp_server", "corrupt token falls back"
    set_current_uid("nobody"); assert resolve() == "ghp_server"
    set_current_uid(""); assert resolve() == "ghp_server"
    current_uid.set("")


def test_gh_byok02_api_sends_resolved_token(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"default_branch": "main"}'

    def fake_urlopen(req, timeout=0):
        seen["auth"] = req.get_header("Authorization")
        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    api = GitHubApi(token="ghp_server", resolve_token=lambda: "ghp_user")
    api.repo("o", "r")
    assert seen["auth"] == "Bearer ghp_user"
    api = GitHubApi(token="ghp_server", resolve_token=lambda: "")
    api.repo("o", "r")
    assert seen["auth"] is None, "no token means an anonymous call, not a stale header"


def test_gh_byok03_settings_roundtrip(tmp_path, monkeypatch):
    cfg = Config(llm_provider="fake", auth_mode="fake",
                 db_path=str(tmp_path / "f.db"), sandbox_root=str(tmp_path / "b"))
    c = TestClient(build_app(cfg))
    h = {"Authorization": "Bearer fake:c1:challenger:c1@t.local"}
    monkeypatch.setattr("sim.adapters.build.github_api.validate_token", lambda t: None)

    assert c.get("/api/auth/me", headers=h).json()["has_github_token"] is False
    r = c.patch("/api/me", json={"github_token": "ghp_mine"}, headers=h)
    assert r.status_code == 200 and r.json()["has_github_token"] is True, r.text
    assert c.get("/api/auth/me", headers=h).json()["has_github_token"] is True

    # stored encrypted; the request-scoped resolver hands it to GitHub calls
    users = c.app.state.auth.users
    rec = users.get("c1")
    assert rec.github_token_enc and "ghp_mine" not in rec.github_token_enc
    resolve = user_token_resolver(users, secret_from_config(cfg), "server")
    set_current_uid("c1"); assert resolve() == "ghp_mine"; current_uid.set("")

    # a name change must not wipe the token; a login refresh must not either
    c.patch("/api/me", json={"name": "Cee"}, headers=h)
    assert users.get("c1").github_token_enc == rec.github_token_enc
    assert c.get("/api/auth/me", headers=h).json()["has_groq_key"] is False

    r = c.patch("/api/me", json={"clear_github_token": True}, headers=h)
    assert r.json()["has_github_token"] is False
    assert c.patch("/api/me", json={"github_token": "  "}, headers=h).status_code == 400
