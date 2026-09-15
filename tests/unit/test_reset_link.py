"""Set-password emails carry a continue URL back to /login."""
from fastapi.testclient import TestClient

from sim.adapters.auth.firebase_verifier import FirebaseVerifier
from sim.app.composition_root import build_app
from sim.app.config import Config


class _Resp:
    status_code = 200
    def json(self):
        return {}


def test_reset01_verifier_sends_continue_url(monkeypatch):
    fb = FirebaseVerifier("key", "proj")
    sent = []
    monkeypatch.setattr(fb._http, "post", lambda url, json=None, **kw: sent.append(json) or _Resp())
    fb.send_password_reset("x@t.local", continue_url="https://sim.example/login")
    assert sent[-1]["continueUrl"] == "https://sim.example/login"
    fb.send_password_reset("y@t.local")
    assert "continueUrl" not in sent[-1]


def test_reset02_origin_derived_from_request(tmp_path):
    """Without PUBLIC_BASE_URL the app learns its origin from the Host header."""
    cfg = Config(llm_provider="fake", auth_mode="fake",
                 db_path=str(tmp_path / "r.db"), sandbox_root=str(tmp_path / "b"))
    app = build_app(cfg)
    c = TestClient(app, base_url="https://worksim.example.org")
    c.get("/api/auth/config")
    assert app.state.public_base_url == "https://worksim.example.org"


def test_reset03_public_base_url_wins(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake",
                 db_path=str(tmp_path / "r.db"), sandbox_root=str(tmp_path / "b"),
                 public_base_url="https://fixed.example")
    app = build_app(cfg)
    c = TestClient(app, base_url="https://other.example")
    c.get("/api/auth/config")
    assert app.state.public_base_url == "https://fixed.example"
