"""QOL-PLAN group B: conditional GitHub requests, bounded repo cache, brief
GitLab project cache, cheap admin-exists check."""
import io
import json
import urllib.error

import pytest

from sim.adapters.auth.services import AuthServices
from sim.adapters.build.github_api import ETagCache, GitHubApi, _default_fetch
from sim.adapters.build.gitlab_api import PROJECT_TTL, GitLabApi, GitLabHost
from sim.adapters.persistence.firestore_store import FirestoreUserDirectory, _aggregation_value
from sim.adapters.persistence.sqlite_users import InMemoryUserDirectory
from sim.adapters.workspace import github_files
from sim.adapters.workspace.github_files import RepoWorkspaceFiles
from sim.core.ports.repo_host import RepoRef, TreeNode
from sim.core.ports.users import UserRecord
from tests.unit.fake_firestore import FakeFirestore


# ---------------------------------------------------------------- B5
class _Resp:
    def __init__(self, body, etag):
        self._body = json.dumps(body).encode()
        self.headers = {"ETag": etag}

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body


def test_b5_conditional_get_serves_304_from_cache(monkeypatch):
    seen = []

    def fake_urlopen(req, timeout=0):
        seen.append(dict(req.header_items()))
        if req.get_header("If-none-match") == '"e1"':
            raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", {}, io.BytesIO(b""))
        return _Resp({"default_branch": "main"}, '"e1"')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    cache = ETagCache(max_entries=2)
    api = GitHubApi(token="", fetch=_default_fetch(lambda: "", etags=cache))
    assert api.repo("o", "r")["default_branch"] == "main"
    assert "If-none-match" not in seen[0]
    assert api.repo("o", "r")["default_branch"] == "main", "304 answered from the cache"
    assert seen[1]["If-none-match"] == '"e1"' and cache.hits == 1
    # bounded: three distinct paths keep only the two most recent
    api.repo("o", "a"); api.repo("o", "b")
    assert cache.etag("/repos/o/r") == "" and cache.etag("/repos/o/b") == '"e1"'
    # a write never sends the header
    api.put("/repos/o/r/contents/x", {"message": "m", "content": "eA=="})
    assert "If-none-match" not in seen[-1]


# ---------------------------------------------------------------- B6
class _Host:
    label = "T"; host = "t.example"

    def __init__(self): self.heads = 0
    def owns(self, url): return "t.example" in url
    def parse(self, url): return RepoRef("t.example", "o", url.rsplit("/", 1)[-1], url)
    def head(self, ref): self.heads += 1; return "main", "sha-" + ref.repo
    def tree(self, ref, sha): return [TreeNode("README.md", size=3, sha="b")]
    def file_text(self, ref, path, at="", max_bytes=0): return "abc"


def test_b6_snapshot_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(github_files, "MAX_CACHED_REPOS", 3)
    h = _Host()
    files = RepoWorkspaceFiles(host=h)
    for i in range(4):
        files.list_dir(f"https://t.example/o/r{i}")
    assert len(files._cache) == 3 and "t.example/o/r0" not in files._cache
    heads = h.heads
    files.list_dir("https://t.example/o/r3")
    assert h.heads == heads, "a cached repo costs no head read"
    files.list_dir("https://t.example/o/r1")       # touch r1, then add one: r2 is the oldest untouched
    files.list_dir("https://t.example/o/r9")
    assert "t.example/o/r1" in files._cache and "t.example/o/r2" not in files._cache


# ---------------------------------------------------------------- B7
def test_b7_gitlab_project_lookup_is_reused_briefly():
    calls = []
    clock = {"t": 100.0}

    def fetch(path, method="GET", body=None):
        calls.append(path)
        if path == "/projects/g%2Fp":
            return {"id": 5, "default_branch": "main", "path_with_namespace": "g/p"}
        if path.startswith("/projects/5/repository/branches/"):
            return {"commit": {"id": "abc"}}
        if path.startswith("/projects/5/repository/commits"):
            return [{"id": "abc", "title": "t"}]
        if path.startswith("/projects/5/repository/files/"):
            return {"file_path": "README.md", "size": 1, "encoding": "base64", "content": "eA=="}
        return {}

    h = GitLabHost("https://lab.test", api=GitLabApi("https://lab.test", fetch=fetch),
                   clock=lambda: clock["t"])
    ref = h.parse("https://lab.test/g/p")
    h.info(ref); h.head(ref); h.commits(ref); h.file_text(ref, "README.md")
    assert calls.count("/projects/g%2Fp") == 1
    assert sum(1 for c in calls if "/branches/" in c) == 2, "branch tips are read every time"
    clock["t"] += PROJECT_TTL + 1
    h.info(ref)
    assert calls.count("/projects/g%2Fp") == 2


# ---------------------------------------------------------------- B8
class _Agg:
    def __init__(self, n): self.value = n


class _CountingCol:
    """A users collection whose query supports count(); streaming it is a failure."""

    def __init__(self, n): self.n = n; self.counted = 0
    def where(self, *a): return self
    def count(self): return self
    def get(self): self.counted += 1; return [[_Agg(self.n)]]
    def stream(self): raise AssertionError("streamed the whole collection")
    def document(self, uid): raise AssertionError("unused")


class _CountingDb:
    def __init__(self, n): self.col = _CountingCol(n)
    def collection(self, name): return self.col


def test_b8_count_role_uses_aggregation_or_falls_back():
    assert _aggregation_value([[_Agg(3)]]) == 3 and _aggregation_value([_Agg(2)]) == 2
    assert _aggregation_value(4) == 4 and _aggregation_value([]) == 0
    db = _CountingDb(2)
    assert FirestoreUserDirectory(db).count_role("admin") == 2 and db.col.counted == 1
    # the fake has no count(): the stream fallback still answers
    fake = FakeFirestore()
    users = FirestoreUserDirectory(fake)
    users.upsert(UserRecord("a", "a@t", "admin")); users.upsert(UserRecord("b", "b@t", "admin", disabled=True))
    assert users.count_role("admin") == 1


class _Counting(InMemoryUserDirectory):
    def __init__(self): super().__init__(); self.counts = 0
    def count_role(self, role): self.counts += 1; return super().count_role(role)


def test_b8_admin_exists_is_remembered():
    users = _Counting()
    svc = AuthServices("fake", users=users, bootstrap_admin_email="boss@t.local")
    assert svc._has_admin() is False and svc._has_admin() is False and users.counts == 2
    users.upsert(UserRecord("x", "x@t.local", "admin"))
    assert svc._has_admin() is True and users.counts == 3
    assert svc._has_admin() is True and users.counts == 3, "answered from memory"
