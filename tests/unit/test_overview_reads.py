"""The admin overview on Firestore must not read per session once the index
is in place, and the cache must answer at once after the first build."""
import time

from fastapi.testclient import TestClient

from sim.app.composition_root import build_app
from sim.app.config import Config
from tests.unit import fake_firestore
from tests.unit.fake_firestore import FakeFirestore


def _counting_db(monkeypatch):
    db = FakeFirestore()
    counts = {"get": 0, "stream": 0}
    orig_get, orig_stream = fake_firestore._Doc.get, fake_firestore._Col.stream

    def get(self):
        counts["get"] += 1
        return orig_get(self)

    def stream(self):
        counts["stream"] += 1
        return orig_stream(self)

    monkeypatch.setattr(fake_firestore._Doc, "get", get)
    monkeypatch.setattr(fake_firestore._Col, "stream", stream)
    monkeypatch.setattr("sim.adapters.persistence.firestore_client.make_firestore_client",
                        lambda cfg: db)
    return db, counts


def test_overview_reads_are_bounded_on_firestore(tmp_path, monkeypatch):
    db, counts = _counting_db(monkeypatch)
    cfg = Config(llm_provider="fake", auth_mode="fake", persistence="firestore",
                 firebase_project_id="x", sandbox_root=str(tmp_path / "b"),
                 bootstrap_admin_email="admin@t.local")
    c = TestClient(build_app(cfg))
    admin = {"Authorization": "Bearer fake:a1:admin:admin@t.local"}
    inst = {"Authorization": "Bearer fake:i1:instructor:i1@t.local"}
    c.get("/api/auth/me", headers=admin)
    co = c.post("/api/admin/cohorts", json={"name": "C"}, headers=admin).json()["id"]
    uids = []
    for i in range(12):
        u = c.post("/api/admin/users", json={"email": f"c{i}@t.local", "role": "challenger"},
                   headers=admin).json()
        uids.append(u["uid"])
        c.post(f"/api/admin/cohorts/{co}/members", json={"uid": u["uid"]}, headers=admin)
    r = c.post(f"/api/instructor/cohorts/{co}/sessions", json={"scenario": "iv_parking"}, headers=inst).json()
    pairs = [(x["session_id"], x["uid"]) for x in r["created"]]   # session -> its assignee
    sids = [p[0] for p in pairs]
    # two started, one submitted, one graded
    for sid, uid in pairs[:2]:
        h = {"Authorization": f"Bearer fake:{uid}:challenger:{uid}@t.local"}
        assert c.post(f"/api/session/{sid}/start", headers=h).status_code == 200
    h0 = {"Authorization": f"Bearer fake:{pairs[0][1]}:challenger:{pairs[0][1]}@t.local"}
    c.post(f"/api/session/{sids[0]}/submit", json={"content": "# d\nq\n"}, headers=h0)
    c.post(f"/api/session/{sids[0]}/grade", json={}, headers=admin)

    # first fresh build may backfill legacy docs; the second must be one pass
    c.get("/api/admin/overview?fresh=1", headers=admin)
    counts["get"] = counts["stream"] = 0
    d = c.get("/api/admin/overview?fresh=1", headers=admin).json()
    t = d["sessions"]["totals"]
    assert (t["sessions"], t["graded"], t["submitted"], t["active"], t["not_started"]) == (12, 1, 0, 1, 10)
    assert counts["get"] <= 6, f"per-session reads crept back in: {counts}"
    assert counts["stream"] <= 12, counts

    # cached answers do not touch the store at all
    counts["get"] = counts["stream"] = 0
    t0 = time.perf_counter()
    d2 = c.get("/api/admin/overview", headers=admin).json()
    # the one read left is the sign-in check on the request itself
    assert d2["cached_at"] and counts["stream"] == 0 and counts["get"] <= 1, counts
    assert time.perf_counter() - t0 < 0.5


def test_admin_sessions_list_reads_are_bounded(tmp_path, monkeypatch):
    db, counts = _counting_db(monkeypatch)
    cfg = Config(llm_provider="fake", auth_mode="fake", persistence="firestore",
                 firebase_project_id="x", sandbox_root=str(tmp_path / "b"),
                 bootstrap_admin_email="admin@t.local")
    c = TestClient(build_app(cfg))
    admin = {"Authorization": "Bearer fake:a1:admin:admin@t.local"}
    inst = {"Authorization": "Bearer fake:i1:instructor:i1@t.local"}
    c.get("/api/auth/me", headers=admin)
    co = c.post("/api/admin/cohorts", json={"name": "C"}, headers=admin).json()["id"]
    for i in range(15):
        u = c.post("/api/admin/users", json={"email": f"c{i}@t.local", "role": "challenger"},
                   headers=admin).json()
        c.post(f"/api/admin/cohorts/{co}/members", json={"uid": u["uid"]}, headers=admin)
    c.post(f"/api/instructor/cohorts/{co}/sessions", json={"scenario": "iv_parking"}, headers=inst)
    c.get("/api/admin/sessions", headers=admin)          # backfills the index once
    counts["get"] = counts["stream"] = 0
    rows = c.get("/api/admin/sessions", headers=admin).json()["sessions"]
    assert len(rows) == 15 and all(r["assignee"].endswith("@t.local") for r in rows)
    assert all(r["state"] == "not_started" for r in rows)
    assert counts["get"] <= 3 and counts["stream"] <= 6, f"per-row reads: {counts}"


def test_cohort_screens_reads_are_bounded(tmp_path, monkeypatch):
    db, counts = _counting_db(monkeypatch)
    cfg = Config(llm_provider="fake", auth_mode="fake", persistence="firestore",
                 firebase_project_id="x", sandbox_root=str(tmp_path / "b"),
                 bootstrap_admin_email="admin@t.local")
    c = TestClient(build_app(cfg))
    admin = {"Authorization": "Bearer fake:a1:admin:admin@t.local"}
    inst = {"Authorization": "Bearer fake:i1:instructor:i1@t.local"}
    c.get("/api/auth/me", headers=admin)
    co = c.post("/api/admin/cohorts", json={"name": "C"}, headers=admin).json()["id"]
    for i in range(20):
        u = c.post("/api/admin/users", json={"email": f"c{i}@t.local", "role": "challenger"},
                   headers=admin).json()
        c.post(f"/api/admin/cohorts/{co}/members", json={"uid": u["uid"]}, headers=admin)
    c.post(f"/api/instructor/cohorts/{co}/sessions", json={"scenario": "iv_parking"}, headers=inst)

    counts["get"] = counts["stream"] = 0
    lst = c.get("/api/instructor/cohorts", headers=inst).json()["cohorts"]
    assert lst[0]["challenger_count"] == 20
    assert counts["get"] <= 3 and counts["stream"] <= 4, f"cohort list: {counts}"

    counts["get"] = counts["stream"] = 0
    d = c.get(f"/api/instructor/cohorts/{co}?scenario=iv_parking", headers=inst).json()
    assert len(d["members"]) == 20 and all(len(m["sessions"]) == 1 for m in d["members"])
    assert all("has_groq_key" in m for m in d["members"])
    assert counts["get"] <= 3 and counts["stream"] <= 4, f"cohort detail: {counts}"

    # creating sessions for a second scenario is one stream to check who has it
    counts["get"] = counts["stream"] = 0
    r = c.post(f"/api/instructor/cohorts/{co}/sessions", json={"scenario": "iv_chat"}, headers=inst).json()
    assert len(r["created"]) == 20
    assert counts["stream"] <= 4, f"cohort create: {counts}"


def test_scoped_listings_use_firestore_filters(tmp_path, monkeypatch):
    """Instructor and challenger listings query by owner / assignee instead of
    streaming the whole sessions collection (roadmap items 11 and 12)."""
    db, counts = _counting_db(monkeypatch)
    where_calls = []
    orig_where = fake_firestore._Col.where

    def where(self, field, op, value):
        where_calls.append((field, value))
        return orig_where(self, field, op, value)
    monkeypatch.setattr(fake_firestore._Col, "where", where)

    cfg = Config(llm_provider="fake", auth_mode="fake", persistence="firestore",
                 firebase_project_id="x", sandbox_root=str(tmp_path / "b"),
                 bootstrap_admin_email="admin@t.local")
    c = TestClient(build_app(cfg))
    admin = {"Authorization": "Bearer fake:a1:admin:admin@t.local"}
    c.get("/api/auth/me", headers=admin)
    insts = []
    for i in range(2):
        c.post("/api/admin/users", json={"email": f"i{i}@t.local", "role": "instructor"}, headers=admin)
        insts.append({"Authorization": f"Bearer fake:i{i}:instructor:i{i}@t.local"})
    ch = c.post("/api/admin/users", json={"email": "c@t.local", "role": "challenger"}, headers=admin).json()
    chal = {"Authorization": f"Bearer fake:{ch['uid']}:challenger:c@t.local"}
    for i, h in enumerate(insts):
        for _ in range(3):
            c.post("/api/instructor/sessions", json={"scenario": "iv_parking",
                                                     "assignee_email": "c@t.local" if i == 0 else ""}, headers=h)

    c.get("/api/instructor/sessions", headers=insts[0])      # first listing backfills the index
    where_calls.clear(); counts["stream"] = counts["get"] = 0
    rows = c.get("/api/instructor/sessions", headers=insts[0]).json()["sessions"]
    assert len(rows) == 3 and all(r["owner"] == "i0@t.local" for r in rows)
    assert any(f == "owner_uid" for f, _ in where_calls), "instructor listing must be scoped in the query"
    assert counts["stream"] <= 3 and counts["get"] <= 6, counts

    where_calls.clear()
    mine = c.get("/api/me/sessions", headers=chal).json()["sessions"]
    assert len(mine) == 3 and all(m["state"] == "not_started" for m in mine)
    assert ("assignee_uid", ch["uid"]) in where_calls, where_calls
    # a grade shows up on the challenger's own list
    sid = mine[0]["session_id"]
    c.post(f"/api/session/{sid}/start", headers=chal)
    c.post(f"/api/session/{sid}/grade", json={}, headers=insts[0])
    mine = {m["session_id"]: m for m in c.get("/api/me/sessions", headers=chal).json()["sessions"]}
    assert mine[sid]["state"] == "graded" and isinstance(mine[sid]["grade_total"], float)


def test_health_reports_checks(tmp_path, monkeypatch):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"), sandbox_root=str(tmp_path / "b"))
    c = TestClient(build_app(cfg))
    r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["checks"]["store"]["ok"] is True
    assert body["checks"]["model"]["checked"] is False and "keys" in body["checks"]
    # a broken store turns the check red and the status code to 503
    c.app.state._health_cache = None
    from sim.adapters.web import app as webapp  # noqa: F401  (module import keeps linters quiet)
    class Broken:
        def get_instructor(self):
            raise RuntimeError("firestore unreachable")
    good = c.app.state.settings
    c.app.state.settings = Broken()
    # bust the 30 s cache by rebuilding the app state cache dict
    import time
    c.app.state.settings = Broken()
    # find the closure cache through a fresh app instead of poking closures
    c2 = TestClient(build_app(cfg))
    c2.app.state.settings = Broken()
    r = c2.get("/health")
    assert r.status_code == 503 and r.json()["status"] == "degraded"
    assert "unreachable" in r.json()["checks"]["store"]["error"]
    c.app.state.settings = good
