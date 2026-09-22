from __future__ import annotations

from typing import Optional

from sim.core.grading.review import HumanReview


class InMemoryReviewStore:
    def __init__(self) -> None:
        self._rows: dict[str, HumanReview] = {}

    def save(self, review: HumanReview) -> HumanReview:
        self._rows[review.session_id] = review
        return review

    def get(self, session_id: str) -> Optional[HumanReview]:
        return self._rows.get(session_id)

    def delete_for_session(self, session_id: str) -> None:
        self._rows.pop(session_id, None)
