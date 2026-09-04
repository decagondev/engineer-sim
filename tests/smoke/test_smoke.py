"""Smoke suite — fast, deterministic (FakeLLMClient), run on every change."""
import ast
import pathlib

import pytest
from fastapi.testclient import TestClient

from sim.app.composition_root import build_app, build_scenario, build_session_service
from sim.app.config import Config
from sim.adapters.llm.fake_client import FakeLLMClient
from sim.adapters.persistence.sqlite_repo import SqliteMessageRepository
from sim.adapters.web.app import create_web_app
from sim.core.grading.grader import LLMGrader
from sim.core.persona.responder import PersonaResponder
from sim.core.ports.repository import StoredMessage
from sim.core.scenario.scenario import Scenario, ScenarioError

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORE_DIR = ROOT / "sim" / "core"
FORBIDDEN_TOP = {"fastapi", "starlette", "uvicorn", "sqlite3", "subprocess",
                 "anthropic", "yaml", "urllib"}


def _cfg(tmp_path):
    return Config(llm_provider="fake", db_path=str(tmp_path / "t.db"))


def _svc(tmp_path, reply="ok", judge="NO"):
    return build_session_service(
        _cfg(tmp_path),
        llm=FakeLLMClient(responses=[reply], default=reply),
        judge_llm=FakeLLMClient(default=judge),
    )

def _app_with(tmp_path, reply="ok", judge="NO"):
    """Manager-backed app with injected deterministic LLMs."""
    from sim.app.composition_root import build_manager
    from sim.adapters.web.app import create_web_app
    from sim.core.grading.grader import LLMGrader
    cfg = _cfg(tmp_path)
    mgr = build_manager(cfg, llm=FakeLLMClient(default=reply),
                        judge_llm=FakeLLMClient(default=judge))
    return create_web_app(mgr, LLMGrader(FakeLLMClient()), instructor_password="$T0mV13w")



# SMK-01
def test_smk01_app_boots(tmp_path):
    client = TestClient(build_app(_cfg(tmp_path)))
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


# SMK-02  (core stays pure)
def _imports(pyfile):
    for node in ast.walk(ast.parse(pyfile.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for n in node.names:
                yield n.name.split(".")[0], n.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            yield mod.split(".")[0], mod


def test_smk02_core_stays_pure():
    offenders = []
    for py in CORE_DIR.rglob("*.py"):
        for top, full in _imports(py):
            if top in FORBIDDEN_TOP or full.startswith("sim.adapters"):
                offenders.append((py.relative_to(ROOT).as_posix(), full))
    assert not offenders, f"core must not import adapters/frameworks: {offenders}"


# SMK-03  (WS round trip)
def test_smk03_ws_round_trip(tmp_path):
    app = _app_with(tmp_path, reply="Hi, I'm Priya.")
    with TestClient(app).websocket_connect("/ws/s1") as ws:
        ws.send_json({"content": "hello", "target": "priya"})
        msg = ws.receive_json()
    assert msg["sender"] == "priya" and msg["content"]


def test_smk03_ws_groq_missing_key_stays_connected(tmp_path, monkeypatch):
    """The old groq SDK import crashed the ASGI websocket on the first chat turn."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cfg = Config(llm_provider="groq", db_path=str(tmp_path / "g.db"),
                 sandbox_root=str(tmp_path / "b"))
    with TestClient(build_app(cfg)).websocket_connect("/ws/s-groq") as ws:
        ws.send_json({"content": "hello", "target": "priya"})
        err = ws.receive_json()
        assert err.get("kind") == "error" and "GROQ_API_KEY" in err["error"]
        ws.send_json({"content": "again", "target": "priya"})
        assert ws.receive_json().get("kind") == "error"


def test_smk03_ws_llm_error_stays_connected(tmp_path):
    from sim.app.composition_root import build_manager
    from sim.adapters.web.app import create_web_app
    from sim.core.grading.grader import LLMGrader

    class BoomLLM:
        def complete(self, *, system, messages):
            raise RuntimeError("GROQ_API_KEY is not set")

    cfg = _cfg(tmp_path)
    boom = BoomLLM()
    mgr = build_manager(cfg, llm=boom, judge_llm=boom)
    app = create_web_app(mgr, LLMGrader(boom), instructor_password="$T0mV13w")
    with TestClient(app).websocket_connect("/ws/s-err") as ws:
        ws.send_json({"content": "hello", "target": "priya"})
        err = ws.receive_json()
        assert err.get("kind") == "error" and "GROQ_API_KEY" in err["error"]
        ws.send_json({"content": "again", "target": "priya"})
        err2 = ws.receive_json()
        assert err2.get("kind") == "error"


# SMK-04  (persistence round trip)
def test_smk04_persistence_round_trip(tmp_path):
    repo = SqliteMessageRepository(str(tmp_path / "p.db"))
    repo.append(StoredMessage("s", "tester", "general", "one", "t1"))
    repo.append(StoredMessage("s", "priya", "general", "two", "t2"))
    rows = repo.list_for_session("s")
    assert [r.content for r in rows] == ["one", "two"]
    assert rows[0].id == 1 and rows[1].id == 2


# SMK-05  (persona replies; hidden need not in prompt)
def test_smk05_persona_replies():
    fake = FakeLLMClient(responses=["Let's talk about what you need."])
    sc = build_scenario(Config(llm_provider="fake"))
    reply = PersonaResponder(fake).respond(sc.primary_persona, sc.world, [])
    assert reply and isinstance(reply, str)
    assert "Priya" in fake.calls[0]["system"]


# SMK-06  (scenario loads)
def test_smk06_scenario_from_dict():
    sc = build_scenario(Config(llm_provider="fake"))
    assert sc.key and sc.primary_persona.name == "Priya" and len(sc.personas) == 3


def test_smk06_scenario_from_file():
    from sim.adapters.persistence.scenario_files import load_scenario_file
    sc = load_scenario_file(
        ROOT / "sim" / "scenarios" / "churn_dashboard" / "scenario.yaml")
    assert sc.primary_persona.key == "priya"
    assert len(sc.primary_persona.reveal_ladder) == 3
    assert len(sc.triggers) == 3 and len(sc.rubric.criteria) == 4


def test_smk06_invalid_scenario_raises():
    with pytest.raises(ScenarioError):
        Scenario.from_dict({"key": "x", "title": "y", "personas": []})


# SMK-07  (session lifecycle)
def test_smk07_session_lifecycle(tmp_path):
    svc = _svc(tmp_path, reply="reply one")
    svc.start("s7")
    svc.post_tester_message("s7", "hi", target="priya")
    svc.end("s7")
    kinds = [m["kind"] for m in svc.export("s7")]
    assert kinds[0] == "event" and kinds[-1] == "event"
    assert "message" in kinds


# SMK-08  (grader plumbing)
def test_smk08_grader_plumbing(tmp_path):
    grade_json = ('{"scores":[{"key":"discovery","score":0.8,"evidence":"e"},'
                  '{"key":"scoping","score":0.5,"evidence":"e"},'
                  '{"key":"stakeholders","score":0.4,"evidence":"e"},'
                  '{"key":"communication","score":0.6,"evidence":"e"}],'
                  '"summary":"ok"}')
    repo = SqliteMessageRepository(str(tmp_path / "g.db"))
    repo.append(StoredMessage("s", "tester", "dm:priya", "what drives churn?", "t"))
    sc = build_scenario(Config(llm_provider="fake"))
    grade = LLMGrader(FakeLLMClient(responses=[grade_json])).grade("s", repo, sc.rubric)
    keys = {s.key for s in grade.scores}
    assert keys == {"discovery", "scoping", "stakeholders", "communication"}
    assert 0.0 <= grade.total <= 1.0


# SMK-09  (second scenario proves OCP: swap the client, no code change)
def test_smk09_second_scenario_swaps_in():
    from sim.adapters.persistence.scenario_files import load_scenario_file
    sc = load_scenario_file(
        ROOT / "sim" / "scenarios" / "support_copilot" / "scenario.yaml")
    assert sc.key == "support_copilot"
    assert sc.primary_persona.key == "dev"
    assert len(sc.primary_persona.reveal_ladder) == 3
    assert len(sc.triggers) == 1 and len(sc.rubric.criteria) == 4


def test_smk09_scenario_is_config_selected(tmp_path):
    path = ROOT / "sim" / "scenarios" / "support_copilot" / "scenario.yaml"
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"),
                 scenario_path=str(path))
    svc = build_session_service(cfg)
    assert "dev" in svc.cast and "robin" in svc.cast


# SMK-10  (environment provisions through the API; starter resolves)
def test_smk10_provision_endpoint(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "e.db"),
                 sandbox_root=str(tmp_path / "boxes"))
    client = TestClient(build_app(cfg))
    r = client.post("/api/session/s-smk10/environment/provision")
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True
    import pathlib as _pl
    wd = _pl.Path(body["workdir"])
    assert (wd / "README.md").exists()           # churn_dashboard starter copied in
    # idempotent
    assert client.post("/api/session/s-smk10/environment/provision").json()["created"] is False


def test_smk10_scenario_carries_starter():
    sc = build_scenario(Config(llm_provider="fake"))
    assert sc.starter_template and sc.starter_template != "STARTER_PLACEHOLDER"
    import pathlib as _pl
    assert (_pl.Path(sc.starter_template) / "README.md").exists()


# SMK-11  (desktop shell + app modules are served)
def test_smk11_desktop_assets_served(tmp_path):
    client = TestClient(build_app(Config(llm_provider="fake",
                                         db_path=str(tmp_path / "d.db"),
                                         sandbox_root=str(tmp_path / "b"))))
    for path in ["/", "/static/shell.js", "/static/md.js", "/static/apps/chat.js",
                 "/static/apps/workspace.js", "/static/apps/email.js",
                 "/static/apps/files.js"]:
        assert client.get(path).status_code == 200, path
    idx = client.get("/").text
    assert "SimApps.boot()" in idx
    assert "/static/md.js" in idx
    for a in ("chat", "workspace", "email", "files"):
        assert f"/static/apps/{a}.js" in idx


def test_smk11_markdown_render():
    import json, shutil, subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node not required for the suite")
    js = ROOT / "sim" / "adapters" / "web" / "static" / "md.js"
    script = f"""
const fs = require('fs');
const vm = require('vm');
const g = {{ window: {{}}, globalThis: {{}} }};
vm.runInNewContext(fs.readFileSync({json.dumps(str(js))}, 'utf8'), g);
const md = g.window.SimMD;
const html = md.render('**Budget:** x\\n\\n- **A:** one\\n- **B:** two\\n\\n```python\\nprint("hi")\\n```');
if (!html.includes('<strong>Budget:</strong>')) process.exit(2);
if (!html.includes('<ul>') || !html.includes('<li>')) process.exit(3);
if (!html.includes('md-code') || !html.includes('tok-str')) process.exit(4);
if (md.render('<script>alert(1)</script>').includes('<script>')) process.exit(5);
if (md.render('<img src=x onerror=alert(1)>').includes('<img')) process.exit(6);
"""
    r = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout


# SMK-12  (mail endpoints + app asset)
def test_smk12_mail_surface(tmp_path):
    client = TestClient(_app_with(tmp_path, reply="Hi,\n\nOK.\n\nP"))
    assert client.get("/api/session/s/mail/threads").json()["threads"] == []
    t = client.post("/api/session/s/mail/compose",
                    json={"to": "priya", "subject": "Q", "body": "hello"}).json()
    assert [e["sender"] for e in t["emails"]] == ["tester", "priya"]
    assert client.get("/api/session/s/mail/threads").json()["threads"][0]["subject"] == "Q"
    assert client.get("/static/apps/email.js").status_code == 200


# SMK-13  (files + tickets apps served; tickets board works)
def test_smk13_files_tickets(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "ft.db"),
                 sandbox_root=str(tmp_path / "b"))
    client = TestClient(build_app(cfg))
    # tickets seed
    board = client.get("/api/session/s/tickets").json()
    assert board["columns"][0]["tickets"], "expected seeded tickets"
    seed = board["columns"][0]["tickets"][0]
    assert seed["key"] and seed["issue_type"] and seed["priority"]
    tid = seed["id"]
    moved = client.post(f"/api/session/s/tickets/{tid}/move",
                        json={"status": "doing"}).json()
    cols = {c["status"]: c["tickets"] for c in moved["columns"]}
    assert any(t["id"] == tid for t in cols["doing"])
    # files needs a workspace
    assert client.get("/api/session/s/files/list").status_code == 409
    client.post("/api/session/s/environment/provision")
    names = [e["name"] for e in client.get("/api/session/s/files/list").json()["entries"]]
    assert "README.md" in names
    # app modules served
    for a in ("files", "tickets"):
        assert client.get(f"/static/apps/{a}.js").status_code == 200
    assert "/static/apps/tickets.js" in client.get("/").text


# SMK-14  (instructor gate + replay payload)
def test_smk14_instructor_gate(tmp_path):
    c = TestClient(_app_with(tmp_path, reply="hi"))
    # record a session via the API
    c.post("/api/session/s-rec/start")
    with c.websocket_connect("/ws/s-rec") as ws:
        ws.send_json({"content": "hello", "target": "priya"})
        ws.receive_json()
    # page served
    assert c.get("/instructor").status_code == 200
    # wrong password -> not ok; no token -> 401
    assert c.post("/api/instructor/auth", json={"password": "nope"}).json()["ok"] is False
    assert c.get("/api/instructor/sessions").status_code == 401
    ok = c.post("/api/instructor/auth", json={"password": "$T0mV13w"}).json()
    assert ok["ok"] is True
    h = {"X-Instructor-Token": "$T0mV13w"}
    sessions = c.get("/api/instructor/sessions", headers=h).json()["sessions"]
    assert any(s["session_id"] == "s-rec" for s in sessions)
    detail = c.get("/api/instructor/session/s-rec", headers=h).json()
    assert len(detail["transcript"]) >= 2 and detail["personas"]


# SMK-15  (level + instructor settings endpoints)
def test_smk15_levels_and_settings(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "l.db"),
                 sandbox_root=str(tmp_path / "b"))
    c = TestClient(build_app(cfg))
    assert len(c.get("/api/levels").json()["levels"]) == 7
    # default level when none set
    assert c.get("/api/session/s/level").json()["level"] == "senior"
    h = {"X-Instructor-Token": "$T0mV13w"}
    # first run: not onboarded
    assert c.get("/api/instructor/settings", headers=h).json()["onboarded"] is False
    # onboard with a default, then set a session level
    assert c.post("/api/instructor/settings", json={"onboarded": True, "default_level": "staff"}, headers=h).json()["ok"]
    assert c.get("/api/instructor/settings", headers=h).json()["default_level"] == "staff"
    # unset session now inherits the instructor default
    assert c.get("/api/session/s2/level").json()["level"] == "staff"
    # explicit per-session level wins
    assert c.post("/api/instructor/session/s2/level", json={"level": "intern"}, headers=h).json()["ok"]
    assert c.get("/api/session/s2/level").json()["level"] == "intern"
    # bad level rejected; unauthorized rejected
    assert c.post("/api/instructor/session/s2/level", json={"level": "wizard"}, headers=h).status_code == 400
    assert c.post("/api/instructor/session/s2/level", json={"level": "mid"}).status_code == 401


# SMK-16  (multi-scenario endpoints)
def test_smk16_multiscenario(tmp_path):
    c = TestClient(build_app(Config(llm_provider="fake", db_path=str(tmp_path / "ms.db"),
                                    sandbox_root=str(tmp_path / "b"))))
    scs = c.get("/api/scenarios").json()
    keys = {s["key"] for s in scs["scenarios"]}
    assert {"churn_dashboard", "support_copilot"} <= keys
    # default session scenario
    assert c.get("/api/session/z/scenario").json()["key"] == scs["default"]
    # assign a different scenario (gated)
    h = {"X-Instructor-Token": "$T0mV13w"}
    assert c.post("/api/instructor/session/z2/scenario",
                  json={"scenario": "support_copilot"}, headers=h).json()["ok"]
    assert c.get("/api/session/z2/scenario").json()["key"] == "support_copilot"
    # unknown scenario rejected; unauthorized rejected
    assert c.post("/api/instructor/session/z2/scenario", json={"scenario": "nope"}, headers=h).status_code == 400
    assert c.post("/api/instructor/session/z2/scenario", json={"scenario": "churn_dashboard"}).status_code == 401


# SMK-17  (a newly-authored scenario runs end to end)
def test_smk17_new_scenario_runs(tmp_path):
    c = TestClient(_app_with(tmp_path, reply="Sure, let me explain."))
    h = {"X-Instructor-Token": "$T0mV13w"}
    c.post("/api/instructor/session/sx/scenario", json={"scenario": "staff_pipeline"}, headers=h)
    sc = c.get("/api/session/sx/scenario").json()
    assert sc["key"] == "staff_pipeline" and sc["difficulty"] == "staff"
    assert {"ravi", "marcus2", "dana2"} <= {p["key"] for p in sc["personas"]}
    c.post("/api/session/sx/start")
    with c.websocket_connect("/ws/sx") as ws:
        ws.send_json({"content": "what does 'too slow' actually cost you?", "target": "ravi"})
        msg = ws.receive_json()
    assert msg["sender"] == "ravi" and msg["content"]


# SMK-18  (Version A: starter download + submit + grade-from-submission)
def test_smk18_submission_flow(tmp_path):
    import io, zipfile
    c = TestClient(build_app(Config(llm_provider="fake", db_path=str(tmp_path / "s.db"),
                                    sandbox_root=str(tmp_path / "b"))))
    sid = "s-sub"
    c.post(f"/api/session/{sid}/start")
    # starter zip streams real files
    z = c.get(f"/api/session/{sid}/starter.zip")
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "README.md" in names
    # empty submission rejected; real one accepted + recorded
    assert c.post(f"/api/session/{sid}/submit", json={"content": "  "}).status_code == 400
    r = c.post(f"/api/session/{sid}/submit",
               json={"filename": "work.patch", "content": "diff\n+x\n"}).json()
    assert r["ok"] and r["lines"] == 3
    assert c.get(f"/api/session/{sid}/submissions").json()["submissions"][0]["filename"] == "work.patch"
    # instructor detail carries the submission for review + a transcript marker
    h = {"X-Instructor-Token": "$T0mV13w"}
    det = c.get(f"/api/instructor/session/{sid}", headers=h).json()
    assert det["submissions"][0]["content"].startswith("diff")
    assert any("Submitted work" in m["content"] for m in det["transcript"])
    # the submit app module is served
    assert c.get("/static/apps/submit.js").status_code == 200


# SMK-19  (GitHub submission: starter URL + repo submit + grade-from-repo)
def test_smk19_github_submission(tmp_path):
    from sim.app.composition_root import build_manager
    from sim.adapters.web.app import create_web_app
    from sim.core.grading.grader import LLMGrader

    class FakeGH:
        def validate(self, url):
            return (True, "owner/good ok") if "/good" in url else (False, "make it public")
        def summary(self, url):
            return f"REPO: {url}\nCOMMITS (2):\n  a work\n  b more"

    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "g.db"),
                 sandbox_root=str(tmp_path / "b"))
    mgr = build_manager(cfg, llm=FakeLLMClient(default="hi"),
                        judge_llm=FakeLLMClient(default="NO"))
    app = create_web_app(mgr, LLMGrader(FakeLLMClient()),
                         instructor_password="$T0mV13w", github_observer=FakeGH())
    c = TestClient(app)
    h = {"X-Instructor-Token": "$T0mV13w"}
    # teacher sets a starter URL; learner sees it
    assert c.post("/api/instructor/scenario/churn_dashboard/starter-url",
                  json={"url": "https://github.com/t/starter"}, headers=h).json()["ok"]
    assert c.get("/api/session/s1/scenario").json()["starter_url"] == "https://github.com/t/starter"
    # unauthorized set is rejected
    assert c.post("/api/instructor/scenario/churn_dashboard/starter-url",
                  json={"url": "x"}).status_code == 401
    # learner submits a bad repo -> validation error; good repo -> stored as kind=repo
    assert c.post("/api/session/s1/submit-repo", json={"url": "https://github.com/x/private"}).status_code == 400
    assert c.post("/api/session/s1/submit-repo", json={"url": "https://github.com/owner/good"}).json()["ok"]
    subs = c.get("/api/session/s1/submissions").json()["submissions"]
    assert subs[-1]["kind"] == "repo"
