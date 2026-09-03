from __future__ import annotations

from pathlib import Path

import yaml

from sim.core.scenario.scenario import Scenario


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
