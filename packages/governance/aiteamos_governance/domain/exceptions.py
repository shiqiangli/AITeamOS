"""Governance Context — 领域异常。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class ReviewNotFoundError(Exception):
    review_id: UUID

    def __init__(self, review_id: UUID) -> None:
        self.review_id = review_id
        super().__init__(f"ReviewCase {review_id} not found")


@dataclass
class ReviewAlreadyDecided(Exception):
    review_id: UUID

    def __init__(self, review_id: UUID) -> None:
        self.review_id = review_id
        super().__init__(f"ReviewCase {review_id} already has a verdict")
