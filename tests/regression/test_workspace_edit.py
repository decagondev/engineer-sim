"""Wave 3 of docs/WORKSPACE-PLAN.md: an editable, durable workspace."""
import pytest
from fastapi.testclient import TestClient

from sim.adapters.persistence.memory_session_files import InMemorySessionFileStore
from sim.adapters.persistence.sqlite_session_files import SqliteSessionFileStore
from sim.adapters.persistence.firestore_store import FirestoreSessionFileStore
from sim.adapters.workspace.local_reader import LocalWorkspaceReader
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.workspace.service import WorkspaceService, WorkspaceWriteError
from tests.unit.fake_firestore import FakeFirestore

TOKEN = {"X-Instructor-Token": "$T0mV13w"}


# ---- adapter: local writes -------------------------------------------------
def test_we01_local_write_is_atomic_and_path_safe(tmp_path):
    files = LocalWorkspaceReader()
    files.write_file(str(tmp_path), "docs/new.md", "# hi\n")
    assert (tmp_path / "docs" / "new.md").read_text(encoding="utf-8") == "# hi\n"
    assert not list(tmp_path.glob("docs/.sim-*"))
    with pytest.raises(ValueError):
        files.write_file(str(tmp_path), "../escape.md", "x")
    with pytest.raises(ValueError):
        files.write_file(str(tmp_path), ".git/config", "x")


# ---- stores ----------------------------------------------------------------
@pytest.mark.parametrize("make", [
    lambda tmp: InMemorySessionFileStore(),
    lambda tmp: SqliteSessionFileStore(str(tmp / "f.db")),
    lambda tmp: FirestoreSessionFileStore(FakeFirestore()),
])
def test_we02_session_file_store_roundtrip(tmp_path, make):
    st = make(tmp_path)
    assert st.get("s", "DESIGN.md") is None
    st.put("s", "DESIGN.md", "v1", "t1")
    st.put("s", "docs/notes.md", "n", "t1")
    st.put("s", "DESIGN.md", "v2", "t2")
    assert st.get("s", "DESIGN.md") == "v2"
    assert list(st.list("s")) == ["DESIGN.md", "docs/notes.md"]
    assert st.list("other") == []
    st.delete_session("s")
    assert st.list("s") == []


# ---- service ---------------------------------------------------------------
def test_we03_service_writes_overlay_first_and_hydrates(tmp_path):
    store = InMemorySessionFileStore()
    svc = WorkspaceService(files=LocalWorkspaceReader(), store=store)
    wd = tmp_path / "wd"; wd.mkdir()
    (wd / "DESIGN.md").write_text("starter\n", encoding="utf-8")
    svc.write(str(wd), "s1", "DESIGN.md", "mine\n")
    assert store.get("s1", "DESIGN.md") == "mine\n"
    assert (wd / "DESIGN.md").read_text(encoding="utf-8") == "mine\n"

    # the folder is lost (redeploy); a fresh service rebuilds it from the store
    wd2 = tmp_path / "wd2"; wd2.mkdir()
    (wd2 / "DESIGN.md").write_text("starter\n", encoding="utf-8")
    svc2 = WorkspaceService(files=LocalWorkspaceReader(), store=store)
    assert svc2.read(str(wd2), "s1", "DESIGN.md").text == "mine\n"
    assert svc2.hydrate(str(wd2), "s1") == 0, "second hydrate is a no-op"

    with pytest.raises(WorkspaceWriteError):
        svc.write(str(wd), "s1", "../x", "y")
    with pytest.raises(WorkspaceWriteError):
        svc.write(str(wd), "s1", ".git/HEAD", "y")
    with pytest.raises(WorkspaceWriteError):
        WorkspaceService(files=LocalWorkspaceReader(), store=store, max_bytes=10).write(
            str(wd), "s1", "big.md", "x" * 11)


def test_we04_design_text_joins_design_and_tickets(tmp_path):
    svc = WorkspaceService(files=LocalWorkspaceReader(), store=None)
    (tmp_path / "DESIGN.md").write_bytes(b"# D\n")
    (tmp_path / "TICKETS.md").write_bytes(b"- t1\n")
    out = svc.design_text(str(tmp_path), "s")
    assert out.startswith("# D\n") and "# TICKETS.md" in out and "- t1" in out


# ---- routes ----------------------------------------------------------------
def _client(tmp_path, **kw):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"),
                 sandbox_root=str(tmp_path / "b"), **kw)
    return cfg, TestClient(build_app(cfg))


def test_we05_doc_workflow_edits_and_submits_without_pasting(tmp_path):
    cfg, c = _client(tmp_path)
    sid = "s-doc"
    c.post(f"/api/instructor/session/{sid}/scenario",
           json={"scenario": "iv_rate_limiter"}, headers=TOKEN)
    c.post(f"/api/session/{sid}/start")
    # no Workspace app step: the folder appears on first file access
    r = c.get(f"/api/session/{sid}/files/list")
    assert r.status_code == 200, r.text
    names = [e["name"] for e in r.json()["entries"]]
    assert "DESIGN.md" in names and r.json()["editable"] is True

    design = "# Rate limiter\n\nSliding window in Redis, per API key.\n"
    r = c.put(f"/api/session/{sid}/files/write", json={"path": "DESIGN.md", "text": design})
    assert r.status_code == 200 and r.json()["ok"], r.text
    assert c.get(f"/api/session/{sid}/files/read?path=DESIGN.md").json()["text"] == design
    assert c.post(f"/api/session/{sid}/files/refresh").json()["ok"]

    r = c.post(f"/api/session/{sid}/submit-doc")
    assert r.status_code == 200 and r.json()["ok"], r.text
    rows = c.get(f"/api/session/{sid}/transcript").json()
    texts = [m["content"] for m in rows]
    assert any("[fired:assessment_open]" in t for t in texts)
    assert any(m["sender"] == "rowan" for m in rows)
    subs = c.get(f"/api/session/{sid}/submissions").json()["submissions"]
    assert subs[-1]["kind"] == "doc" and subs[-1]["filename"] == "DESIGN.md"

    # a restart with the sandbox wiped: the edit comes back from the store
    import shutil
    shutil.rmtree(tmp_path / "b", ignore_errors=True)
    c2 = TestClient(build_app(cfg))
    assert c2.get(f"/api/session/{sid}/files/read?path=DESIGN.md").json()["text"] == design
    svc = c2.app.state.manager.for_session(sid).session_service
    assert svc.design_text(sid).startswith("# Rate limiter")


def test_we06_write_refused_where_not_allowed(tmp_path):
    _, c = _client(tmp_path)
    sid = "s-sandbox"
    # product + local = sandbox: needs the Workspace app first
    assert c.get(f"/api/session/{sid}/files/list").status_code == 409
    c.post(f"/api/session/{sid}/environment/provision")
    r = c.put(f"/api/session/{sid}/files/write", json={"path": "../x", "text": "y"})
    assert r.status_code == 400
    r = c.put(f"/api/session/{sid}/files/write", json={"path": "notes.md", "text": 5})
    assert r.status_code == 400
    r = c.put(f"/api/session/{sid}/files/write", json={"path": "notes.md", "text": "ok"})
    assert r.status_code == 200
    assert c.post(f"/api/session/{sid}/submit-doc").status_code == 405

    # hosted product = repo: read-only, and nothing to browse until linked
    (tmp_path / "h").mkdir()
    _, h = _client(tmp_path / "h", work_mode="hosted")
    assert h.put(f"/api/session/{sid}/files/write",
                 json={"path": "a.md", "text": "x"}).status_code == 405
    assert h.get(f"/api/session/{sid}/files/list").status_code == 409


def test_we07_sandbox_submit_snapshots_and_fires_triggers(tmp_path):
    _, c = _client(tmp_path)
    sid = "s-sandbox-submit"
    c.post(f"/api/session/{sid}/start")
    assert c.post(f"/api/session/{sid}/submit-workspace").status_code == 409
    c.post(f"/api/session/{sid}/environment/provision")
    c.put(f"/api/session/{sid}/files/write",
          json={"path": "src/answer.py", "text": "ANSWER = 42\n"})
    r = c.post(f"/api/session/{sid}/submit-workspace")
    assert r.status_code == 200 and r.json()["ok"], r.text
    subs = c.get(f"/api/session/{sid}/submissions").json()["submissions"]
    assert subs[-1]["kind"] == "workspace"
    texts = [m["content"] for m in c.get(f"/api/session/{sid}/transcript").json()]
    assert any("Submitted work: workspace" in t for t in texts)
    c.post(f"/api/session/{sid}/grade", json={})
    llm = c.app.state.grader._llm
    calls = getattr(llm, "calls", None) or llm._fallback.calls
    prompt = calls[-1]["messages"][0].content
    assert "ANSWER = 42" in prompt or "answer.py" in prompt
