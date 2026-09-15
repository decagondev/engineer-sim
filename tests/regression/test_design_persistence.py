"""Wave 1 of docs/WORKSPACE-PLAN.md: the design doc survives a restart and a
repo submission feeds the assessor and grader like a pasted one."""
import base64

from fastapi.testclient import TestClient

from sim.adapters.build.github_api import GitHubApi
from sim.adapters.build.github_observer import GitHostBuildObserver
from sim.app.composition_root import build_app
from sim.app.config import Config

TOKEN = {"X-Instructor-Token": "$T0mV13w"}
DESIGN = "# Rate limiter\n\nToken bucket in Redis, 100 req/min per key, fail-open.\n"


def _client(tmp_path):
    cfg = Config(llm_provider="fake", db_path=str(tmp_path / "s.db"),
                 sandbox_root=str(tmp_path / "b"))
    return cfg, TestClient(build_app(cfg))


class FakeRepo:
    """Stands in for GitHostBuildObserver: a public repo that contains DESIGN.md."""

    def __init__(self, files=None):
        self.files = files if files is not None else {"DESIGN.md": DESIGN}

    def validate(self, url):
        return True, "fake/repo looks good"

    def summary(self, url):
        return "REPO: fake/repo\nCOMMITS (1):\n  abc1234 2026-01-01 work"

    def read_file(self, url, path):
        return self.files.get(path)


def _grader_calls(c):
    llm = c.app.state.grader._llm
    return getattr(llm, "calls", None) or llm._fallback.calls


def _install(c, repo):
    c.app.state.github_observer = repo
    c.app.state.manager.repo_files = repo


def test_dp01_design_survives_restart(tmp_path):
    cfg, c = _client(tmp_path)
    sid = "s-restart"
    c.post(f"/api/instructor/session/{sid}/scenario",
           json={"scenario": "iv_rate_limiter"}, headers=TOKEN)
    c.post(f"/api/session/{sid}/start")
    assert c.post(f"/api/session/{sid}/submit",
                  json={"filename": "work.patch", "content": DESIGN}).json()["ok"]

    # a brand-new process over the same database: nothing in memory
    c2 = TestClient(build_app(cfg))
    svc = c2.app.state.manager.for_session(sid).session_service
    assert svc.design_text(sid) == DESIGN
    c2.post(f"/api/session/{sid}/grade", json={})
    prompt = _grader_calls(c2)[-1]["messages"][0].content
    assert "Token bucket in Redis" in prompt


def test_dp02_repo_submission_opens_assessor(tmp_path):
    _, c = _client(tmp_path)
    _install(c, FakeRepo())
    sid = "s-repo-iv"
    c.post(f"/api/instructor/session/{sid}/scenario",
           json={"scenario": "iv_rate_limiter"}, headers=TOKEN)
    c.post(f"/api/session/{sid}/start")
    r = c.post(f"/api/session/{sid}/submit-repo",
               json={"url": "https://github.com/fake/repo"})
    assert r.status_code == 200 and r.json()["ok"], r.text
    rows = c.get(f"/api/session/{sid}/transcript").json()
    texts = [m["content"] for m in rows]
    assert any("[fired:assessment_open]" in t for t in texts)
    assert any(m["sender"] == "rowan" for m in rows), "assessor should have spoken"
    assert "flowchart" in c.get(f"/api/session/{sid}/diagram").json()["mermaid"]
    svc = c.app.state.manager.for_session(sid).session_service
    assert "Token bucket" in svc.design_text(sid)


def test_dp03_repo_without_design_does_not_open_assessor(tmp_path):
    _, c = _client(tmp_path)
    _install(c, FakeRepo(files={}))
    sid = "s-repo-nodesign"
    c.post(f"/api/instructor/session/{sid}/scenario",
           json={"scenario": "iv_rate_limiter"}, headers=TOKEN)
    c.post(f"/api/session/{sid}/start")
    c.post(f"/api/session/{sid}/submit-repo", json={"url": "https://github.com/fake/repo"})
    texts = [m["content"] for m in c.get(f"/api/session/{sid}/transcript").json()]
    assert not any("[fired:assessment_open]" in t for t in texts)


def test_dp04_product_patch_is_not_a_design(tmp_path):
    _, c = _client(tmp_path)
    sid = "s-prod-patch"
    c.post(f"/api/session/{sid}/start")   # default scenario is churn_dashboard (product)
    c.post(f"/api/session/{sid}/submit",
           json={"filename": "work.patch", "content": "diff --git a/x b/x\n+print(1)\n"})
    svc = c.app.state.manager.for_session(sid).session_service
    assert svc.design_text(sid) == ""
    c.post(f"/api/session/{sid}/grade", json={})
    prompt = _grader_calls(c)[-1]["messages"][0].content
    assert prompt.count("print(1)") == 1, "patch must appear once, as the build record"


def test_dp05_github_api_decodes_files_and_summary_includes_docs():
    seen = []

    def fetch(path):
        seen.append(path)
        if path == "/repos/o/r":
            return {"default_branch": "main", "fork": False}
        if path.startswith("/repos/o/r/commits"):
            return [{"sha": "abcdef0", "commit": {"message": "first\nbody",
                                                  "author": {"date": "2026-01-01"}}}]
        if path.startswith("/repos/o/r/contents/DESIGN.md"):
            return {"type": "file", "size": len(DESIGN), "encoding": "base64",
                    "content": base64.b64encode(DESIGN.encode()).decode()}
        from sim.adapters.build.github_api import GitHubReadError
        raise GitHubReadError("repo not found")

    api = GitHubApi(token="", fetch=fetch)
    assert api.file_text("o", "r", "DESIGN.md") == DESIGN
    assert api.file_text("o", "r", "missing.md") is None
    obs = GitHostBuildObserver(api=api)
    out = obs.summary("https://github.com/o/r")
    assert "abcdef0 2026-01-01 first" in out
    assert "DESIGN.md:\n# Rate limiter" in out
    assert obs.read_file("https://github.com/o/r", "DESIGN.md") == DESIGN
    assert obs.validate("https://github.com/o/r") == (True, "o/r looks good")
