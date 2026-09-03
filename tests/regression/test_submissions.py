"""Learner submission store + grade-from-submission (Version A)."""
from sim.adapters.persistence.memory_submissions import InMemorySubmissionStore


def test_sub01_store_roundtrip():
    s = InMemorySubmissionStore()
    assert s.latest("x") is None
    a = s.save("x", "work.patch", "diff line one\nline two\n", "t1")
    assert a.seq == 1 and a.lines == 3
    b = s.save("x", "work2.patch", "more\n", "t2")
    assert b.seq == 2
    assert s.latest("x").filename == "work2.patch"
    assert len(s.list("x")) == 2
    assert s.list("y") == []
