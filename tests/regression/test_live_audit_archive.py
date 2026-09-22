"""Roadmap items 10 (live view), 14 (audit log) and 13 (archive)."""
import asyncio
import time

from fastapi.testclient import TestClient

from sim.adapters.persistence.firestore_store import FirestoreArchiveStore, FirestoreAuditLog
from sim.adapters.persistence.memory_archive import InMemoryArchiveStore
from sim.adapters.persistence.memory_audit import InMemoryAuditLog
from sim.adapters.persistence.sqlite_archive import SqliteArchiveStore
from sim.adapters.persistence.sqlite_audit import SqliteAuditLog
from sim.adapters.web.live import SessionBus
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.ports.archive import ArchiveRecord
from sim.core.ports.audit import AuditEntry
from tests.unit.fake_firestore import FakeFirestore


def _h(uid, role, email=""):
    return {"Authorization": f"Bearer fake:{uid}:{role}:{email or uid + '@t.local'}"}


def _fake(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake", db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"), bootstrap_admin_email="admin@t.local")
    return TestClient(build_app(cfg))


# ---- live ---------------------------------------------------------------
def test_lv01_bus_wakes_subscribers_from_another_thread():
    async def scenario():
        bus = SessionBus()
        q = bus.subscribe("s1")
        assert bus.watchers("s1") == 1 and bus.notify("other") == 0
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, bus.notify, "s1", "turn")
        assert await asyncio.wait_for(q.get(), timeout=2) == "turn"
        bus.unsubscribe("s1", q)
        assert bus.watchers("s1") == 0
    asyncio.run(scenario())


def test_lv02_watch_socket_streams_new_rows(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"), sandbox_root=str(tmp_path / "b"))
    c = TestClient(build_app(cfg))
    sid = "s-live"
    c.post(f"/api/session/{sid}/start")
    with c.websocket_connect(f"/ws/watch/{sid}?itoken=$T0mV13w") as ws:
        first = ws.receive_json()
        assert any("Session started" in r["content"] for r in first["rows"])
        c.post(f"/api/session/{sid}/submit", json={"filename": "DESIGN.md", "content": "# d\nq\n"})
        nxt = ws.receive_json()
        assert any("Submitted work" in r["content"] for r in nxt["rows"])
        assert all(r["id"] > max(x["id"] for x in first["rows"]) for r in nxt["rows"])
    # wrong password is refused
    try:
        with c.websocket_connect(f"/ws/watch/{sid}?itoken=nope"):
            assert False, "should have closed"
    except Exception:
        pass


# ---- audit --------------------------------------------------------------
def test_au01_audit_stores_roundtrip(tmp_path):
    for st in (InMemoryAuditLog(), SqliteAuditLog(str(tmp_path / "a.db")), FirestoreAuditLog(FakeFirestore())):
        for i in range(3):
            st.append(AuditEntry(f"2026-01-0{i+1}T00:00:00+00:00", "a@t", f"POST /x{i}", f"t{i}", "", 200))
        rows = st.list(limit=2)
        assert [r.action for r in rows] == ["POST /x2", "POST /x1"]
        assert [r.action for r in st.list(limit=5, before="2026-01-02T00:00:00+00:00")] == ["POST /x0"]


def test_au02_admin_writes_are_logged(tmp_path):
    c = _fake(tmp_path)
    admin = _h("a1", "admin", "admin@t.local")
    c.get("/api/auth/me", headers=admin)
    u = c.post("/api/admin/users", json={"email": "x@t.local", "role": "challenger"}, headers=admin).json()
    c.put("/api/admin/settings", json={"announcement": "hi"}, headers=admin)
    c.get("/api/admin/users", headers=admin)                       # reads are not logged
    c.post("/api/admin/users", json={"email": "", "role": "challenger"}, headers=admin)   # a 400 is logged too
    sid = "s-del"
    c.post(f"/api/session/{sid}/start", headers=admin)
    c.delete(f"/api/admin/sessions/{sid}", headers=admin)
    entries = c.get("/api/admin/audit", headers=admin).json()["entries"]
    actions = [e["action"] for e in entries]
    assert actions[0] == f"DELETE /api/admin/sessions/{sid}"
    assert entries[0]["target"] == sid and "deleted session" in entries[0]["summary"]
    assert entries[0]["actor"] == "admin@t.local"
    assert "POST /api/admin/users" in actions and "PUT /api/admin/settings" in actions
    assert not any(a.startswith("GET") for a in actions)
    assert any(e["status"] == 400 for e in entries if e["action"] == "POST /api/admin/users")
    assert c.get("/api/admin/audit", headers=_h("i1", "instructor")).status_code == 403


# ---- archive ------------------------------------------------------------
def test_ar01_archive_stores_roundtrip(tmp_path):
    for st in (InMemoryArchiveStore(), SqliteArchiveStore(str(tmp_path / "r.db")), FirestoreArchiveStore(FakeFirestore())):
        assert st.get("s") is None and list(st.list()) == []
        st.put(ArchiveRecord("s", "2026-01-01T00:00:00+00:00", "T", "iv_parking", "c@t", "graded", 0, "# audit\nbody"))
        rec = st.get("s")
        assert rec.markdown.startswith("# audit") and rec.title == "T"
        listed = st.list()
        assert listed[0].session_id == "s" and listed[0].markdown == "" and listed[0].size > 0


def test_ar02_archive_job_exports_then_deletes(tmp_path):
    c = _fake(tmp_path)
    admin, inst = _h("a1", "admin", "admin@t.local"), _h("i1", "instructor")
    c.get("/api/auth/me", headers=admin)
    c.post("/api/admin/users", json={"email": "i1@t.local", "role": "instructor"}, headers=admin)
    sids = []
    for i in range(2):
        sid = c.post("/api/instructor/sessions", json={"scenario": "iv_parking"}, headers=inst).json()["session_id"]
        c.post(f"/api/session/{sid}/start", headers=inst)
        c.post(f"/api/session/{sid}/submit", json={"filename": "DESIGN.md", "content": f"# d{i}\n"}, headers=inst)
        c.post(f"/api/session/{sid}/grade", json={}, headers=inst)
        sids.append(sid)
    idle = c.post("/api/instructor/sessions", json={"scenario": "iv_parking"}, headers=inst).json()["session_id"]

    # dry run: graded sessions, any age
    d = c.post("/api/admin/sessions/archive", json={"older_than_days": 0, "states": ["graded"], "dry_run": True},
               headers=admin).json()
    assert d["dry_run"] and d["count"] == 2 and {s["session_id"] for s in d["sessions"]} == set(sids)
    # only old ones
    d = c.post("/api/admin/sessions/archive", json={"older_than_days": 30, "states": ["graded"], "dry_run": True},
               headers=admin).json()
    assert d["count"] == 0

    r = c.post("/api/admin/sessions/archive", json={"older_than_days": 0, "states": ["graded"], "dry_run": False},
               headers=admin).json()
    assert r["count"] == 2
    for _ in range(50):
        job = c.get("/api/admin/sessions/archive", headers=admin).json()["job"]
        if job["status"] == "done":
            break
        time.sleep(0.1)
    assert job["status"] == "done" and job["done"] == 2 and job["failed"] == []

    archives = c.get("/api/admin/archives", headers=admin).json()["archives"]
    assert {a["session_id"] for a in archives} == set(sids) and all(a["state"] == "graded" for a in archives)
    md = c.get(f"/api/admin/archives/{sids[0]}.md", headers=admin).text
    assert "Assessment audit" in md and "Scores" in md
    # the live sessions are gone, the idle one survives
    live = {s["session_id"] for s in c.get("/api/admin/sessions?fresh=1", headers=admin).json()["sessions"]}
    assert idle in live and not (set(sids) & live)
    assert c.get(f"/api/session/{sids[0]}/grade", headers=admin).status_code == 404
    entries = c.get("/api/admin/audit", headers=admin).json()["entries"]
    assert any("started archive of 2" in e["summary"] for e in entries)
