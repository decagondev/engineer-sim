"""The scenario library spans every engineer level and every scenario is valid."""
from sim.app.composition_root import build_registry
from sim.app.config import Config
from sim.core.levels import LEVEL_ORDER


def _reg():
    return build_registry(Config(llm_provider="fake"))


def test_lib01_at_least_one_scenario_per_level():
    reg = _reg()
    difficulties = {sc.difficulty for sc in reg.values()}
    for lvl in LEVEL_ORDER:
        assert lvl in difficulties, f"no scenario pitched at '{lvl}'"


def test_lib02_every_scenario_is_wellformed():
    for key, sc in _reg().items():
        assert sc.key == key
        assert sc.title and sc.difficulty in LEVEL_ORDER
        assert sc.personas, f"{key} has no personas"
        # rubric uses the shared four criteria so level weight-shifts apply
        assert {c.key for c in sc.rubric.criteria} == {
            "discovery", "scoping", "stakeholders", "communication"}, key
        # the primary persona has a hidden need + reveal ladder (the point of the sim)
        assert sc.primary_persona.hidden_need, f"{key} primary has no hidden need"
        assert sc.primary_persona.reveal_ladder, f"{key} primary has no reveal ladder"


def test_lib03_trigger_gates_are_valid_levels():
    for key, sc in _reg().items():
        for t in sc.triggers:
            assert t.min_level in LEVEL_ORDER, f"{key}:{t.event_id} bad min_level"
            assert t.action in ("chat", "email", "ticket")


def test_lib04_every_scenario_provisions_a_non_empty_workspace(tmp_path):
    """No scenario should leave the Files/Workspace view empty — either it has a
    starter, or provisioning seeds a fallback README.
    """
    from sim.adapters.environment.local_folder import LocalFolderEnvironment
    for key, sc in _reg().items():
        env = LocalFolderEnvironment(root=str(tmp_path / key),
                                     starter_template=sc.starter_template)
        h = env.provision("s")
        from pathlib import Path
        visible = [p.name for p in Path(h.workdir).iterdir() if p.name != ".git"]
        assert visible, f"{key} provisions an empty workspace"
