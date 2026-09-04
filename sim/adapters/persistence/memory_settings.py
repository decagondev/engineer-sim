from __future__ import annotations

from typing import Optional

from sim.core.ports.settings import InstructorSettings


class InMemorySettingsStore:
    def __init__(self) -> None:
        self._instr = InstructorSettings()
        self._levels: dict[str, str] = {}
        self._scenarios: dict[str, str] = {}
        self._starter_urls: dict[str, str] = {}

    def get_instructor(self) -> InstructorSettings:
        return self._instr

    def set_instructor(self, settings: InstructorSettings) -> None:
        self._instr = settings

    def get_session_level(self, session_id: str) -> Optional[str]:
        return self._levels.get(session_id)

    def set_session_level(self, session_id: str, level: str) -> None:
        self._levels[session_id] = level

    def get_session_scenario(self, session_id: str):
        return self._scenarios.get(session_id)

    def set_session_scenario(self, session_id: str, scenario_key: str) -> None:
        self._scenarios[session_id] = scenario_key

    def get_scenario_starter_url(self, scenario_key: str):
        return self._starter_urls.get(scenario_key)

    def set_scenario_starter_url(self, scenario_key: str, url: str) -> None:
        self._starter_urls[scenario_key] = url
