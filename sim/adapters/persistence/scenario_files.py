from __future__ import annotations

from pathlib import Path

import yaml

from sim.core.scenario.scenario import Scenario


SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"


def starter_dir_for(key: str) -> Path | None:
    """The on-disk starter folder of a scenario key, if it has one."""
    d = SCENARIOS_DIR / key / "starter"
    return d if d.is_dir() else None


def load_scenario_text(text: str, starter_base: str | Path | None = None) -> Scenario:
    """Parse YAML text (a dashboard override). A relative starter_template is
    resolved against `starter_base` (the folder of the scenario it is based on)."""
    import dataclasses
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict):
        raise ValueError("scenario YAML must be a mapping")
    scenario = Scenario.from_dict(data)
    st = scenario.starter_template
    if st and not Path(st).is_absolute():
        base = Path(starter_base) if starter_base else None
        resolved = (base / st).resolve() if base else None
        scenario = dataclasses.replace(scenario, starter_template=str(resolved) if resolved else "")
    return scenario


def load_scenario_file(path: str | Path) -> Scenario:
    """Adapter: read a YAML scenario file and parse it into the domain model.
    Resolves a relative starter_template against the scenario file's folder.
    """
    import dataclasses
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    scenario = Scenario.from_dict(data)
    if scenario.starter_template and not Path(scenario.starter_template).is_absolute():
        resolved = (p.parent / scenario.starter_template).resolve()
        scenario = dataclasses.replace(scenario, starter_template=str(resolved))
    return scenario
