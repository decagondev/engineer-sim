from __future__ import annotations

from typing import Optional, Sequence

from sim.core.ports.scenarios import ScenarioOverride


class InMemoryScenarioStore:
    def __init__(self) -> None:
        self._rows: dict[str, ScenarioOverride] = {}

    def put(self, override: ScenarioOverride) -> ScenarioOverride:
        self._rows[override.key] = override
        return override

    def get(self, key: str) -> Optional[ScenarioOverride]:
        return self._rows.get(key)

    def list(self) -> Sequence[ScenarioOverride]:
        return sorted(self._rows.values(), key=lambda o: o.key)

    def delete(self, key: str) -> bool:
        return self._rows.pop(key, None) is not None
