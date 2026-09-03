"""Multi-scenario: registry, per-session resolution, assignment, bundle caching."""
import tempfile

from sim.app.composition_root import build_manager, build_registry
from sim.app.config import Config
from sim.adapters.llm.fake_client import FakeLLMClient


def _cfg():
    tmp = tempfile.mkdtemp()
    return Config(llm_provider="fake", db_path=tmp + "/e.db", sandbox_root=tmp + "/b")


def _manager(cfg):
    return build_manager(cfg, llm=FakeLLMClient(default="hi"),
                         judge_llm=FakeLLMClient(default="NO"))


# MULTI-01: registry loads every scenario, keyed by key, with difficulty
def test_multi01_registry():
    reg = build_registry(_cfg())
    assert "churn_dashboard" in reg and "support_copilot" in reg
    assert reg["churn_dashboard"].difficulty == "mid"
    assert reg["support_copilot"].difficulty == "senior"


# MULTI-02: unassigned session -> default; assignment changes resolution
def test_multi02_resolution():
    mgr = _manager(_cfg())
    assert mgr.resolve_scenario_key("s1") == "churn_dashboard"     # default
    mgr.settings.set_session_scenario("s1", "support_copilot")
    assert mgr.resolve_scenario_key("s1") == "support_copilot"
    # unknown key falls back to default
    mgr.settings.set_session_scenario("s2", "nonsense")
    assert mgr.resolve_scenario_key("s2") == "churn_dashboard"


# MULTI-03: two sessions get different scenarios' casts, concurrently
def test_multi03_two_sessions_different_scenarios():
    mgr = _manager(_cfg())
    mgr.settings.set_session_scenario("sB", "support_copilot")
    a = mgr.for_session("sA").scenario
    b = mgr.for_session("sB").scenario
    assert a.key == "churn_dashboard" and "priya" in a.cast
    assert b.key == "support_copilot" and "dev" in b.cast
    # each bundle's session service carries the right primary persona
    assert mgr.for_session("sA").session_service.primary_key == "priya"
    assert mgr.for_session("sB").session_service.primary_key == "dev"


# MULTI-04: bundles are cached per scenario (same scenario -> same bundle)
def test_multi04_bundle_cache():
    mgr = _manager(_cfg())
    assert mgr.for_session("sA") is mgr.for_session("sC")          # both default
    mgr.settings.set_session_scenario("sB", "support_copilot")
    assert mgr.for_session("sB") is not mgr.for_session("sA")
