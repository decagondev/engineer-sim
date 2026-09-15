"""Wave 2 of docs/WORKSPACE-PLAN.md: one workflow per (track, hosted)."""
import pytest
from fastapi.testclient import TestClient

from sim.app.composition_root import build_app
from sim.app.config import Config
from sim.core.workflow import resolve_workflow

TOKEN = {"X-Instructor-Token": "$T0mV13w"}


@pytest.mark.parametrize("track,hosted,kind,editable,needs_repo", [
    ("interview", False, "doc", True, False),
    ("interview", True, "doc", True, False),
    ("systems", False, "doc", True, False),
    ("systems", True, "doc", True, False),
    ("product", False, "sandbox", True, False),
    ("product", True, "repo", False, True),
])
def test_wf01_matrix(track, hosted, kind, editable, needs_repo):
    wf = resolve_workflow(track, hosted)
    assert (wf.kind, wf.editable, wf.needs_repo_url) == (kind, editable, needs_repo)
    assert wf.submit_label and wf.submit_hint


def test_wf02_config_hosted_inference():
    assert Config().hosted is False
    assert Config(auth_mode="firebase").hosted is True
    assert Config(persistence="firestore", firebase_project_id="x").hosted is True
    assert Config(auth_mode="firebase", work_mode="local").hosted is False
    assert Config(work_mode="hosted").hosted is True


def _client(tmp_path, **kw):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"),
                 sandbox_root=str(tmp_path / "b"), **kw)
    return TestClient(build_app(cfg))


def test_wf03_scenario_payload_carries_workflow(tmp_path):
    c = _client(tmp_path)
    sid = "s-wf"
    sc = c.get(f"/api/session/{sid}/scenario").json()
    assert sc["workflow"]["kind"] == "sandbox" and sc["hosted"] is False
    c.post(f"/api/instructor/session/{sid}/scenario",
           json={"scenario": "iv_parking"}, headers=TOKEN)
    assert c.get(f"/api/session/{sid}/scenario").json()["workflow"]["kind"] == "doc"
    listing = c.get("/api/scenarios", headers=TOKEN).json()
    kinds = {s["key"]: s["workflow"]["kind"] for s in listing["scenarios"]}
    assert kinds["churn_dashboard"] == "sandbox" and kinds["sys_feed"] == "doc"


def test_wf04_hosted_refuses_patch_and_zip_for_product(tmp_path):
    c = _client(tmp_path, work_mode="hosted")
    sid = "s-hosted"
    assert c.get(f"/api/session/{sid}/scenario").json()["workflow"]["kind"] == "repo"
    r = c.post(f"/api/session/{sid}/submit", json={"content": "diff"})
    assert r.status_code == 405
    assert c.get(f"/api/session/{sid}/starter.zip").status_code == 404
    # doc tracks still accept a pasted design when hosted
    c.post(f"/api/instructor/session/{sid}/scenario",
           json={"scenario": "iv_parking"}, headers=TOKEN)
    r = c.post(f"/api/session/{sid}/submit", json={"content": "# design\nqueue\n"})
    assert r.status_code == 200 and r.json()["ok"]


def test_wf05_grade_build_record_per_workflow(tmp_path):
    c = _client(tmp_path, work_mode="hosted")
    sid = "s-hosted-grade"
    llm = c.app.state.grader._llm
    calls = getattr(llm, "calls", None) or llm._fallback.calls
    c.post(f"/api/session/{sid}/start")
    c.post(f"/api/session/{sid}/grade", json={})
    assert "no repository linked" in calls[-1]["messages"][0].content
