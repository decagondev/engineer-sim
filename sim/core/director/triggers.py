from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TurnContext:
    """What a trigger gets to look at. Kept small on purpose."""

    tester_turns: int
    level: str = "senior"


class Trigger(ABC):
    """Open/Closed seam: new trigger kinds subclass this; the Director never
    changes to support them.
    """

    @abstractmethod
    def evaluate(self, ctx: TurnContext) -> bool: ...


class TurnCountTrigger(Trigger):
    """Fires once the tester has sent at least `at` messages (scaled by the
    engineer level). `min_level` gates the beat so harder stakeholders only
    appear for more senior engineers. Deterministic and reconnect-safe.
    """

    def __init__(self, at: int, min_level: str = "intern") -> None:
        self._at = at
        self._min = min_level

    def evaluate(self, ctx: TurnContext) -> bool:
        from sim.core.levels import profile, rank
        if rank(ctx.level) < rank(self._min):
            return False
        threshold = max(1, round(self._at * profile(ctx.level).beat_scale))
        return ctx.tester_turns >= threshold
