"""Scenario authoring: overrides in a store win over disk, new scenarios from a
template borrow its starter, validation refuses broken YAML, revert restores."""
from fastapi.testclient import TestClient

from sim.adapters.persistence.firestore_store import FirestoreScenarioStore
from sim.adapters.persistence.memory_scenarios import InMemoryScenarioStore
from sim.adapters.persistence.sqlite_scenarios import SqliteScenarioStore
from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.ports.scenarios import ScenarioOverride
from tests.unit.fake_firestore import FakeFirestore


def test_sa01_stores_roundtrip(tmp_path):
    for st in (InMemoryScenarioStore(), SqliteScenarioStore(str(tmp_path / "s.db")),
               FirestoreScenarioStore(FakeFirestore())):
        assert st.get("x") is None and list(st.list()) == []
        st.put(ScenarioOverride("x", "key: x\n", "t1", "a@t", "iv_parking"))
        st.put(ScenarioOverride("x", "key: x\ntitle: T\n", "t2", "a@t", "iv_parking"))
        o = st.get("x")
        assert o.yaml_text.endswith("title: T\n") and o.based_on == "iv_parking" and o.ts == "t2"
        assert [x.key for x in st.list()] == ["x"]
        assert st.delete("x") and not st.delete("x")


def _h(uid, role, email=""):
    return {"Authorization": f"Bearer fake:{uid}:{role}:{email or uid + '@t.local'}"}


def test_sa02_edit_validate_revert_and_new_from_template(tmp_path):
    cfg = Config(llm_provider="fake", auth_mode="fake", db_path=str(tmp_path / "f.db"),
                 sandbox_root=str(tmp_path / "b"), bootstrap_admin_email="admin@t.local")
    c = TestClient(build_app(cfg))
    admin = _h("a1", "admin", "admin@t.local")
    c.get("/api/auth/me", headers=admin)

    d = c.get("/api/admin/scenarios/iv_parking/yaml", headers=admin).json()
    assert d["source"] == "disk" and "key: iv_parking" in d["yaml"] and d["on_disk"] is True
    original = d["yaml"]

    # broken YAML and a wrong key are refused; validate=1 does not save
    r = c.put("/api/admin/scenarios/iv_parking/yaml", json={"yaml": "key: iv_parking\ntitle: [oops"}, headers=admin)
    assert r.status_code == 400 and "YAML error" in r.json()["error"]
    r = c.put("/api/admin/scenarios/iv_parking/yaml", json={"yaml": original.replace("key: iv_parking", "key: other")}, headers=admin)
    assert r.status_code == 400 and "'iv_parking'" in r.json()["error"]
    edited = original.replace("name: Sol", "name: Solveig")
    r = c.put("/api/admin/scenarios/iv_parking/yaml?validate=1", json={"yaml": edited}, headers=admin)
    assert r.status_code == 200 and r.json()["valid"] and "Solveig" in r.json()["personas"]
    assert c.get("/api/admin/scenarios/iv_parking/yaml", headers=admin).json()["source"] == "disk"

    # save: the registry reloads and a new session sees the edited persona
    r = c.put("/api/admin/scenarios/iv_parking/yaml", json={"yaml": edited}, headers=admin)
    assert r.status_code == 200 and r.json()["source"] == "override"
    listing = {s["key"]: s for s in c.get("/api/admin/scenarios", headers=admin).json()["scenarios"]}
    assert listing["iv_parking"]["customised"] is True and listing["iv_parking"]["store_only"] is False
    sid = "s-auth"
    c.post(f"/api/instructor/session/{sid}/scenario", json={"scenario": "iv_parking"}, headers=admin)
    names = [p["name"] for p in c.get(f"/api/session/{sid}/scenario", headers=admin).json()["personas"]]
    assert "Solveig" in names
    c.post(f"/api/session/{sid}/start", headers=admin)
    assert c.get(f"/api/session/{sid}/files/list", headers=admin).status_code == 200, "starter still resolves"

    # the override survives a restart; revert brings the file back
    c2 = TestClient(build_app(cfg))
    names = [p["name"] for p in c2.get(f"/api/session/{sid}/scenario", headers=admin).json()["personas"]]
    assert "Solveig" in names
    r = c2.delete("/api/admin/scenarios/iv_parking/yaml", headers=admin)
    assert r.status_code == 200 and r.json()["reverted_to_disk"] is True
    sid2 = "s-auth2"
    c2.post(f"/api/instructor/session/{sid2}/scenario", json={"scenario": "iv_parking"}, headers=admin)
    assert "Sol" in [p["name"] for p in c2.get(f"/api/session/{sid2}/scenario", headers=admin).json()["personas"]]
    assert c2.delete("/api/admin/scenarios/iv_parking/yaml", headers=admin).status_code == 404

    # a new scenario from a template: appears, borrows the starter, is deletable
    r = c2.post("/api/admin/scenarios", json={"based_on": "iv_parking", "key": "iv_bike_share", "title": "Interview: bike share"}, headers=admin)
    assert r.status_code == 200 and r.json()["based_on"] == "iv_parking", r.text
    listing = {s["key"]: s for s in c2.get("/api/admin/scenarios", headers=admin).json()["scenarios"]}
    assert listing["iv_bike_share"]["store_only"] is True and listing["iv_bike_share"]["title"] == "Interview: bike share"
    sid3 = "s-bike"
    c2.post(f"/api/instructor/session/{sid3}/scenario", json={"scenario": "iv_bike_share"}, headers=admin)
    c2.post(f"/api/session/{sid3}/start", headers=admin)
    names = [e["name"] for e in c2.get(f"/api/session/{sid3}/files/list", headers=admin).json()["entries"]]
    assert "DESIGN.md" in names, "starter borrowed from the template"
    assert c2.post("/api/admin/scenarios", json={"based_on": "iv_parking", "key": "iv_bike_share", "title": "x"}, headers=admin).status_code == 409
    assert c2.post("/api/admin/scenarios", json={"based_on": "iv_parking", "key": "Bad Key", "title": "x"}, headers=admin).status_code == 400
    r = c2.delete("/api/admin/scenarios/iv_bike_share/yaml", headers=admin).json()
    assert r["removed"] is True
    assert "iv_bike_share" not in {s["key"] for s in c2.get("/api/admin/scenarios", headers=admin).json()["scenarios"]}
    # audited
    actions = [e["summary"] for e in c2.get("/api/admin/audit", headers=admin).json()["entries"]]
    assert any("created scenario iv_bike_share" in a for a in actions)
