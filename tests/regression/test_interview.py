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


def test_iv10_repair_mermaid_quotes_awkward_labels():
    from sim.core.session.interview import repair_mermaid
    # the model writes a literal backslash-n inside labels, as Groq did in production
    src = "\n".join([
        "flowchart TB",
        "  subgraph Service_Layer",
        r"    API[API Service\n(POST /shorten, GET /<alias>)]",
        "  end",
        r"  DB[DB Table\n(alias PK, long_url)]",
        "  C[Client] --> LB[Load Balancer / TLS]",
        "  OK[Plain label]",
        '  Q["already quoted (fine)"]',
    ])
    out = repair_mermaid(src)
    assert 'API["API Service<br/>(POST /shorten, GET /<alias>)"]' in out
    assert 'DB["DB Table<br/>(alias PK, long_url)"]' in out
    assert 'LB["Load Balancer / TLS"]' in out
    assert "OK[Plain label]" in out and 'Q["already quoted (fine)"]' in out
    assert "subgraph Service_Layer" in out
    assert repair_mermaid("flowchart TB\n  A[Client] --> B[Store]\n") == "flowchart TB\n  A[Client] --> B[Store]"


def test_iv11_timebox_and_assessment_stats():
    from sim.core.ports.repository import StoredMessage
    from sim.core.session.interview import assessment_stats, started_at, timebox_overrun

    def m(i, sender, content, ts, kind="message", channel="dm:rowan"):
        return StoredMessage(session_id="s", sender=sender, channel=channel, content=content,
                             ts=ts, kind=kind, id=i)
    rows = [
        m(1, "system", "Session started. Online: Sol, Rowan.", "2026-01-01T10:00:00+00:00", "event", "general"),
        m(2, "system", "[timebox:20]", "2026-01-01T10:00:00+00:00", "event", "general"),
        m(3, "tester", "[reveal] Submitted work: DESIGN.md (5 lines).", "2026-01-01T10:24:30+00:00", "event", "general"),
        m(4, "system", "[fired:assessment_open]", "2026-01-01T10:24:31+00:00", "event", "general"),
        m(5, "rowan", "Why Redis?", "2026-01-01T10:25:00+00:00"),
        m(6, "tester", "Because counters need atomic increments and low latency.", "2026-01-01T10:26:00+00:00"),
        m(7, "rowan", "What if a sensor double-counts?", "2026-01-01T10:27:00+00:00"),
        m(8, "rowan", "And the daily report?", "2026-01-01T10:29:00+00:00"),
        m(9, "tester", "A nightly job reconciles from the raw events.", "2026-01-01T10:30:00+00:00"),
    ]
    assert started_at(rows) == "2026-01-01T10:00:00+00:00"
    assert timebox_overrun(rows, 20) == 4.5
    assert timebox_overrun(rows, 0) is None
    assert timebox_overrun(rows[:2], 20) is None
    st = assessment_stats(rows, "rowan")
    assert (st.probes, st.answered, st.unanswered) == (3, 2, 1)
    assert "answered 2 of 3" in st.summary() and "1 left unanswered" in st.summary()
    assert assessment_stats(rows[:4], "rowan").summary() == "no assessor probes yet"


def test_iv12_timebox_flows_to_shell_and_grader(tmp_path):
    c, h = _client(tmp_path)
    sid = "s-iv-tb"
    c.post(f"/api/instructor/session/{sid}/scenario", json={"scenario": "iv_parking"}, headers=h)
    sc = c.get(f"/api/session/{sid}/scenario").json()
    assert sc["timebox_minutes"] == 20 and sc["started_at"] == ""
    r = c.post(f"/api/session/{sid}/start").json()
    assert r["started_at"]
    assert c.get(f"/api/session/{sid}/scenario").json()["started_at"] == r["started_at"]
    texts = [m["content"] for m in c.get(f"/api/session/{sid}/transcript").json()]
    assert "[timebox:20]" in texts
    c.post(f"/api/session/{sid}/submit", json={"filename": "DESIGN.md", "content": "# d\nq\n"})
    svc = c.app.state.manager.for_session(sid).session_service
    svc.post_tester_message(sid, "Because the counters are per floor.", target="rowan")
    c.post(f"/api/session/{sid}/grade", json={})
    llm = c.app.state.grader._llm
    calls = getattr(llm, "calls", None) or llm._fallback.calls
    prompt = calls[-1]["messages"][0].content
    assert "ASSESSMENT: answered 1 of 2 assessor probes" in prompt
    assert "inside the 20-minute timebox" in prompt
