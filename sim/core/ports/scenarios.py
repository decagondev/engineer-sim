from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Protocol, Sequence


@dataclass(frozen=True)
class ScenarioOverride:
    """A scenario authored or edited in the dashboard, kept as YAML text so the
    on-disk format stays the single schema. An override for an existing key
    replaces the file's version; a new key adds a scenario whose starter
    folder is borrowed from `based_on`."""

    key: str
    yaml_text: str
    ts: str
    author: str = ""
    based_on: str = ""

    def meta(self) -> dict:
        d = asdict(self)
        d.pop("yaml_text", None)
        return d


class ScenarioStore(Protocol):
    def put(self, override: ScenarioOverride) -> ScenarioOverride: ...

    def get(self, key: str) -> Optional[ScenarioOverride]: ...

    def list(self) -> Sequence[ScenarioOverride]: ...

    def delete(self, key: str) -> bool: ...
