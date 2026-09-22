"""Instructor review of a grade: per-criterion overrides and a comment, merged
over the model's grade. Pure: dicts in, dict out, no I/O.

The model grade is the payload /grade returns (scores, total, weights,
include_tickets, tickets_extra ...). A review replaces only the criteria the
instructor touched; the weighted total is recomputed with the same weights
the grader used, so a reviewed grade is comparable to an unreviewed one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from sim.core.grading.rubric import Rubric

TICKETS_KEY = "tickets"
TICKETS_BONUS = 0.15       # same as the extra-credit bonus applied at grade time


@dataclass(frozen=True)
class HumanReview:
    session_id: str
    scores: dict = field(default_factory=dict)   # criterion key -> 0..1
    comment: str = ""
    reviewer: str = ""
    ts: str = ""


class ReviewError(ValueError):
    """The review names an unknown criterion or a score outside 0..1."""


def validate_review(scores: Mapping[str, object], rubric: Rubric,
                    allow_tickets: bool = True) -> dict:
    """Coerce and check the scores an instructor submitted."""
    allowed = {c.key for c in rubric.criteria}
    if allow_tickets:
        allowed.add(TICKETS_KEY)
    out = {}
    for key, raw in (scores or {}).items():
        if key not in allowed:
            raise ReviewError(f"unknown criterion: {key}")
        try:
            val = float(raw)
        except (TypeError, ValueError):
            raise ReviewError(f"{key}: score must be a number between 0 and 1")
        if not 0.0 <= val <= 1.0:
            raise ReviewError(f"{key}: score must be between 0 and 1")
        out[key] = round(val, 3)
    return out


def merge_review(grade: dict, review: Optional[HumanReview], rubric: Rubric) -> dict:
    """The grade as the instructor sees it. Without a review, the model grade
    with every score marked source=model. With one, overridden scores are
    swapped in, totals recomputed, and a `review` block attached."""
    body = dict(grade or {})
    scores = [dict(s) for s in body.get("scores", [])]
    weights = dict(body.get("weights") or {c.key: c.weight for c in rubric.criteria})
    human = dict(review.scores) if review else {}
    for s in scores:
        if s.get("key") in human:
            s["model_score"] = s.get("score")
            s["score"] = human[s["key"]]
            s["source"] = "human"
        else:
            s["source"] = "model"
    body["scores"] = scores
    if review is None:
        body["review"] = None
        return body

    total_w = sum(weights.get(s["key"], 0.0) for s in scores if s["key"] in weights)
    base = (sum(float(s["score"]) * weights.get(s["key"], 0.0) for s in scores
                if s["key"] in weights) / total_w) if total_w else float(body.get("total") or 0.0)
    body["total_model"] = body.get("total_model", body.get("total"))
    if body.get("include_tickets"):
        extra = dict(body.get("tickets_extra") or {})
        if TICKETS_KEY in human:
            extra["model_score"] = extra.get("score")
            extra["score"] = human[TICKETS_KEY]
            extra["source"] = "human"
        else:
            extra.setdefault("source", "model")
        body["tickets_extra"] = extra
        body["total_base"] = round(base, 3)
        body["total"] = round(min(1.0, base + TICKETS_BONUS * float(extra.get("score") or 0.0)), 3)
    else:
        body["total"] = round(base, 3)
    body["review"] = {
        "scores": dict(review.scores), "comment": review.comment,
        "reviewer": review.reviewer, "ts": review.ts,
    }
    return body
