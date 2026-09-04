"""GitHub submission: URL parsing, per-scenario starter URL, repo submit + grade."""
import pytest

from sim.adapters.build.github_observer import parse_repo
from sim.adapters.persistence.memory_settings import InMemorySettingsStore
from sim.adapters.persistence.memory_submissions import InMemorySubmissionStore


@pytest.mark.parametrize("url,owner,repo", [
    ("https://github.com/octocat/Hello-World", "octocat", "Hello-World"),
    ("https://github.com/octocat/Hello-World.git", "octocat", "Hello-World"),
    ("github.com/octocat/Hello-World/", "octocat", "Hello-World"),
    ("octocat/Hello-World", "octocat", "Hello-World"),
])
def test_gh01_parse_repo(url, owner, repo):
    assert parse_repo(url) == (owner, repo)


def test_gh01_parse_repo_rejects_junk():
    with pytest.raises(ValueError):
        parse_repo("not a url")


def test_gh02_scenario_starter_url_roundtrip():
    s = InMemorySettingsStore()
    assert s.get_scenario_starter_url("churn_dashboard") is None
    s.set_scenario_starter_url("churn_dashboard", "https://github.com/t/starter")
    assert s.get_scenario_starter_url("churn_dashboard") == "https://github.com/t/starter"


def test_gh03_submission_kind_repo():
    st = InMemorySubmissionStore()
    a = st.save("s", "work.patch", "diff\n+x\n", "t1")            # default patch
    b = st.save("s", "github-repo", "https://github.com/o/r", "t2", kind="repo")
    assert a.kind == "patch" and b.kind == "repo"
    assert st.latest("s").kind == "repo"
