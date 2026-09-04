from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class InstructorSettings:
    onboarded: bool = False
    default_level: str = "senior"


class SettingsStore(Protocol):
    """Durable instructor settings + per-session engineer level."""

    def get_instructor(self) -> InstructorSettings: ...

    def set_instructor(self, settings: InstructorSettings) -> None: ...

    def get_session_level(self, session_id: str) -> Optional[str]: ...

    def set_session_level(self, session_id: str, level: str) -> None: ...

    def get_session_scenario(self, session_id: str) -> Optional[str]: ...

    def set_session_scenario(self, session_id: str, scenario_key: str) -> None: ...

    def get_scenario_starter_url(self, scenario_key: str) -> Optional[str]: ...

    def set_scenario_starter_url(self, scenario_key: str, url: str) -> None: ...
