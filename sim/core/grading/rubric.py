from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Criterion:
    key: str
    description: str
    weight: float = 1.0


@dataclass(frozen=True)
class Rubric:
    criteria: tuple[Criterion, ...] = field(default_factory=tuple)

    @staticmethod
    def from_list(items) -> "Rubric":
        return Rubric(criteria=tuple(
            Criterion(key=i["key"], description=i["description"],
                      weight=float(i.get("weight", 1.0)))
            for i in (items or [])
        ))

    def __bool__(self) -> bool:
        return bool(self.criteria)


@dataclass(frozen=True)
class CriterionScore:
    key: str
    score: float          # 0.0 .. 1.0
    evidence: str


@dataclass(frozen=True)
class Grade:
    scores: tuple[CriterionScore, ...]
    total: float          # weighted 0.0 .. 1.0
    summary: str

    def as_dict(self) -> dict:
        return {
            "total": round(self.total, 3),
            "summary": self.summary,
            "scores": [
                {"key": s.key, "score": round(s.score, 3), "evidence": s.evidence}
                for s in self.scores
            ],
        }
