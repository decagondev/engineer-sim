"""Systems Designer track — five design-review scenarios and submit pushback."""
from pathlib import Path

from fastapi.testclient import TestClient

from sim.app.composition_root import build_app, build_registry
from sim.app.config import Config
from sim.core.director.triggers import SubmissionTrigger, TurnContext
from sim.core.levels import systems_expectation, systems_posture

SYS_KEYS = (
    "sys_shortlink", "sys_notify", "sys_collab", "sys_apigw", "sys_feed",
)


def _reg():
    return build_registry(Config(llm_provider="fake"))


def test_sys01_five_systems_scenarios():
    reg = _reg()
    for key in SYS_KEYS:
        assert key in reg, key
        sc = reg[key]
        assert sc.track == "systems"
        assert sc.role_label == "Systems Designer"
        assert sc.primary_persona.hidden_need and sc.primary_persona.reveal_ladder
        assert any(t.kind == "submission" for t in sc.triggers), key
        starter = Path(sc.starter_template)
        assert (starter / "DESIGN.md").exists(), key
        assert (starter / "docs" / "constraints.md").exists(), key


def test_sys02_submission_trigger():
    trig = SubmissionTrigger(at=1, min_level="intern")
    assert trig.evaluate(TurnContext(tester_turns=0, submissions=0)) is False
    assert trig.evaluate(TurnContext(tester_turns=0, submissions=1)) is True
    gated = SubmissionTrigger(at=1, min_level="staff")
    assert gated.evaluate(TurnContext(0, level="mid", submissions=1)) is False
    assert gated.evaluate(TurnContext(0, level="staff", submissions=1)) is True


def test_sys03_posture_and_expectation():
    assert "system-design" in systems_posture("senior").lower()
    assert "defended architecture" in systems_expectation("senior").lower()


def test_sys04_submit_fires_design_review(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"),
                 sandbox_root=str(tmp_path / "b"))
    c = TestClient(build_app(cfg))
    h = {"X-Instructor-Token": "$T0mV13w"}
    sid = "s-sys"
    assert c.post(f"/api/instructor/session/{sid}/scenario",
                  json={"scenario": "sys_shortlink"}, headers=h).json()["ok"]
    sc = c.get(f"/api/session/{sid}/scenario").json()
    assert sc["track"] == "systems" and sc["role_label"] == "Systems Designer"
    c.post(f"/api/session/{sid}/start")
    started = c.get(f"/api/session/{sid}/transcript").json()
    assert any("Systems Designer" in m["content"] for m in started)
    r = c.post(f"/api/session/{sid}/submit",
               json={"filename": "DESIGN.md", "content": "# design\ncache then postgres\n"})
    assert r.json()["ok"]
    events = [m["content"] for m in c.get(f"/api/session/{sid}/transcript").json()]
    assert any("Submitted work" in e for e in events)
    assert any("filed a ticket" in e or "sent you an email" in e for e in events)
    mail = c.get(f"/api/session/{sid}/mail/threads").json()["threads"]
    assert mail, "expected a design-review email after submit"
    board = c.get(f"/api/session/{sid}/tickets").json()
    titles = [t["title"] for col in board["columns"] for t in col["tickets"]]
    assert any("Failure mode" in t or "cache empty" in t.lower() for t in titles)


def test_sys05_meta_exposes_track(tmp_path):
    c = TestClient(build_app(Config(llm_provider="fake",
                                    db_path=str(tmp_path / "m.db"),
                                    sandbox_root=str(tmp_path / "b"))))
    keys = {s["key"]: s for s in c.get("/api/scenarios").json()["scenarios"]}
    assert keys["sys_feed"]["track"] == "systems"
    assert keys["churn_dashboard"]["track"] == "product"
