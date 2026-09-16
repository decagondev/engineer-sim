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
