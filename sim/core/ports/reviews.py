from __future__ import annotations

from typing import Optional, Protocol

from sim.core.grading.review import HumanReview


class ReviewStore(Protocol):
    """One instructor review per session. Kept apart from GradeStore so a
    regrade never erases the human verdict and a review never blocks a regrade."""

    def save(self, review: HumanReview) -> HumanReview: ...

    def get(self, session_id: str) -> Optional[HumanReview]: ...

    def delete_for_session(self, session_id: str) -> None: ...
