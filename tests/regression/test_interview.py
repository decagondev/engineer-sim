"""Interview assessment track — 20 scenarios, assessor after submit, export."""
from pathlib import Path

from fastapi.testclient import TestClient

from sim.app.composition_root import build_app, build_registry
from sim.app.config import Config
from sim.core.director.triggers import SessionStartTrigger, TurnContext, TurnCountTrigger
from sim.core.levels import interview_expectation, interview_posture
from sim.core.session.interview import extract_mermaid, signals_design_ready

IV_KEYS = (
    "iv_unique_id", "iv_rate_limiter", "iv_key_value", "iv_pastebin",
    "iv_url_shortener", "iv_web_crawler", "iv_autocomplete", "iv_job_queue",
    "iv_metrics", "iv_webhooks", "iv_file_upload", "iv_chat", "iv_presence",
    "iv_leaderboard", "iv_search", "iv_scheduler", "iv_comments",
    "iv_calendar", "iv_parking", "iv_tiny_analytics",
)


def _reg():
    return build_registry(Config(llm_provider="fake"))


def _client(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"),
                 sandbox_root=str(tmp_path / "b"))
    return TestClient(build_app(cfg)), {"X-Instructor-Token": "$T0mV13w"}


def test_iv01_twenty_interview_scenarios():
    reg = _reg()
    assert len(IV_KEYS) == 20
    for key in IV_KEYS:
        assert key in reg, key
        sc = reg[key]
        assert sc.track == "interview"
        assert sc.role_label == "Candidate"
        assert sc.primary_persona.lane == "interviewer"
        assert sc.primary_persona.hidden_need and sc.primary_persona.reveal_ladder
        assert any(p.lane == "assessor" for p in sc.personas), key
        assert any(t.kind == "session_start" for t in sc.triggers), key
        starter = Path(sc.starter_template)
        assert (starter / "DESIGN.md").exists(), key
        assert (starter / "TICKETS.md").exists(), key


def test_iv02_session_start_trigger():
    trig = SessionStartTrigger(min_level="intern")
    assert trig.evaluate(TurnContext(0, phase="start")) is True
    assert trig.evaluate(TurnContext(0, phase="turn")) is False
    gated = SessionStartTrigger(min_level="staff")
    assert gated.evaluate(TurnContext(0, level="mid", phase="start")) is False
    assert gated.evaluate(TurnContext(0, level="staff", phase="start")) is True
    # turn-count beats must not fire during the opening
    tc = TurnCountTrigger(at=1, min_level="intern")
    assert tc.evaluate(TurnContext(5, phase="start")) is False


def test_iv03_ready_and_mermaid_helpers():
    assert signals_design_ready("I've finished the design — take a look")
    assert signals_design_ready("that's my design")
    assert not signals_design_ready("can you tell me the QPS?")
    assert "flowchart" in extract_mermaid(
        "```mermaid\nflowchart TB\n  A --> B\n```")
    assert extract_mermaid("Sure — tell me more.") == ""


def test_iv04_posture_does_not_hand_over_the_answer():
    iv = interview_posture("senior", "interviewer").lower()
    assert "never outline the architecture" in iv
    asr = interview_posture("senior", "assessor").lower()
    assert "do not propose a better architecture" in asr
    assert "interview assessment" in interview_expectation("senior").lower()


def test_iv05_start_presents_problem(tmp_path):
    c, h = _client(tmp_path)
    sid = "s-iv"
    assert c.post(f"/api/instructor/session/{sid}/scenario",
                  json={"scenario": "iv_unique_id"}, headers=h).json()["ok"]
    sc = c.get(f"/api/session/{sid}/scenario").json()
    assert sc["track"] == "interview" and sc["role_label"] == "Candidate"
    assert any(p.get("lane") == "assessor" for p in sc["personas"])
    c.post(f"/api/session/{sid}/start")
    rows = c.get(f"/api/session/{sid}/transcript").json()
    texts = [m["content"] for m in rows]
    assert any("timed system-design interview" in t for t in texts)
    assert any("unique IDs" in t for t in texts)


def test_iv06_submit_starts_assessor_and_diagram(tmp_path):
    c, h = _client(tmp_path)
    sid = "s-iv-sub"
    c.post(f"/api/instructor/session/{sid}/scenario",
           json={"scenario": "iv_rate_limiter"}, headers=h)
    c.post(f"/api/session/{sid}/start")
    design = (
        "# Rate limiter\n\nPer API key, 100/min, Redis counters, fail-open.\n"
        "Workers check Redis before the handler. Custom caps in a table.\n"
    )
    r = c.post(f"/api/session/{sid}/submit",
               json={"filename": "DESIGN.md", "content": design})
    assert r.json()["ok"]
    rows = c.get(f"/api/session/{sid}/transcript").json()
    texts = [m["content"] for m in rows]
    assert any("Submitted work" in t for t in texts)
    assert any("assess your design" in t or "assessment" in t.lower() for t in texts)
    assert any(m["sender"] == "rowan" for m in rows)
    diag = c.get(f"/api/session/{sid}/diagram").json()
    assert "flowchart" in (diag.get("mermaid") or "")


def test_iv07_assessor_blocked_until_ready(tmp_path):
    c, h = _client(tmp_path)
    sid = "s-iv-early"
    c.post(f"/api/instructor/session/{sid}/scenario",
           json={"scenario": "iv_pastebin"}, headers=h)
    c.post(f"/api/session/{sid}/start")
    mgr = c.app.state.manager
    svc = mgr.for_session(sid).session_service
    out = svc.post_tester_message(sid, "can we start the defense?", target="rowan")
    assert any("joins after you submit" in m.content for m in out)


def test_iv08_grade_toggle_and_export(tmp_path):
    c, h = _client(tmp_path)
    sid = "s-iv-ex"
    c.post(f"/api/instructor/session/{sid}/scenario",
           json={"scenario": "iv_key_value"}, headers=h)
    c.post(f"/api/session/{sid}/start")
    c.post(f"/api/session/{sid}/submit",
           json={"filename": "DESIGN.md",
                 "content": "# KV\nGet/put/delete, WAL, 5k QPS mostly gets.\n"})
    base = c.post(f"/api/session/{sid}/grade",
                  json={"include_tickets": False}).json()
    assert "discovery" in {s["key"] for s in base["scores"]}
    assert "tickets" not in {s["key"] for s in base["scores"]}
    assert base.get("include_tickets") is False
    with_t = c.post(f"/api/session/{sid}/grade",
                    json={"include_tickets": True}).json()
    assert with_t.get("include_tickets") is True
    assert "tickets_extra" in with_t
    assert "total_base" in with_t
    exp = c.get(f"/api/instructor/session/{sid}/export.md?include_tickets=true",
                headers=h)
    assert exp.status_code == 200
    md = exp.text
    assert "Assessment audit" in md
    assert "Clarifying interview" in md
    assert "Assessment defense" in md
    assert "```mermaid" in md
    assert "Scores" in md


def test_iv09_meta_exposes_interview_track(tmp_path):
    c, _ = _client(tmp_path)
    keys = {s["key"]: s for s in c.get("/api/scenarios").json()["scenarios"]}
    assert keys["iv_tiny_analytics"]["track"] == "interview"
    assert keys["churn_dashboard"]["track"] == "product"
    assert keys["sys_shortlink"]["track"] == "systems"
