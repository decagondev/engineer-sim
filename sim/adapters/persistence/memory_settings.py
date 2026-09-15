from __future__ import annotations

from typing import Optional

from sim.core.ports.settings import InstructorSettings


class InMemorySettingsStore:
    def __init__(self) -> None:
        self._instr = InstructorSettings()
        self._levels: dict[str, str] = {}
        self._scenarios: dict[str, str] = {}
        self._starter_urls: dict[str, str] = {}
        self._repo_urls: dict[str, str] = {}

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

    def get_session_repo_url(self, session_id: str):
        return self._repo_urls.get(session_id)

    def set_session_repo_url(self, session_id: str, url: str) -> None:
        self._repo_urls[session_id] = url

    def get_scenario_starter_url(self, scenario_key: str):
        return self._starter_urls.get(scenario_key)

    def set_scenario_starter_url(self, scenario_key: str, url: str) -> None:
        self._starter_urls[scenario_key] = url

    def get_scenario_enabled(self, scenario_key: str) -> bool:
        return True

    def set_scenario_enabled(self, scenario_key: str, enabled: bool) -> None:
        pass

    def delete_session_settings(self, session_id: str) -> None:
        self._levels.pop(session_id, None)
        self._scenarios.pop(session_id, None)
        self._repo_urls.pop(session_id, None)
