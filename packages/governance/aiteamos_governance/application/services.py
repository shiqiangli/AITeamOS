"""
Governance Context — 应用服务 (plan.md §3.3)。

ReviewService: 审核流程管理 (创建、决策、查询)
ConflictService: 冲突检测与解决
"""

from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import UUID

from aiteamos_shared.types import MemberId, MemoryId, new_id

from ..domain.models import (
    ConflictCase,
    ConflictKind,
    DetectorKind,
    ResolutionKind,
    ReviewCase,
    ReviewTargetKind,
    Verdict,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 审核轮次上限 (plan.md §3.3.4)
# ---------------------------------------------------------------------------

MAX_REVIEW_ROUNDS = 3

# 语义冲突相似度阈值 (plan.md §3.3.5)
CONFLICT_SIMILARITY_THRESHOLD = 0.92


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class ReviewRepoLike(Protocol):
    async def save(self, aggregate: ReviewCase, *, tx: Any = None) -> None: ...
    async def get_by_id(self, review_id: UUID, *, tx: Any = None) -> ReviewCase | None: ...
    async def find_pending(self, *, tx: Any = None) -> list[ReviewCase]: ...
    async def find_by_target(
        self, target_kind: str, target_id: UUID, *, tx: Any = None
    ) -> list[ReviewCase]: ...
    async def count_by_target(
        self, target_kind: str, target_id: UUID, *, tx: Any = None
    ) -> int: ...


class ConflictRepoLike(Protocol):
    async def save(self, aggregate: ConflictCase, *, tx: Any = None) -> None: ...
    async def get_by_id(self, conflict_id: UUID, *, tx: Any = None) -> ConflictCase | None: ...
    async def find_unresolved(self, *, tx: Any = None) -> list[ConflictCase]: ...
    async def find_by_memory(
        self, memory_id: MemoryId, *, tx: Any = None
    ) -> list[ConflictCase]: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


# ---------------------------------------------------------------------------
# ReviewService — 审核流程管理
# ---------------------------------------------------------------------------


class ReviewService:
    """审核服务。

    管理 Task 交付物审核、Memory 候选审核、Memory 晋升审核。
    """

    def __init__(
        self,
        *,
        review_repo: ReviewRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = review_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def create_review(
        self,
        *,
        target_kind: ReviewTargetKind,
        target_id: UUID,
        reviewer_member_id: MemberId,
        triggered_by_system_meta: bool = False,
    ) -> ReviewCase:
        """创建审核案例。

        Returns:
            创建的 ReviewCase
        """
        case = ReviewCase(
            target_kind=target_kind,
            target_id=target_id,
            reviewer_member_id=reviewer_member_id,
            triggered_by_system_meta=triggered_by_system_meta,
        )

        from ..domain.events import ReviewCaseCreated

        event = ReviewCaseCreated(
            event_type="governance.review_case.created",
            review_case_id=case.id,
            target_kind=target_kind.value,
            target_id=target_id,
            reviewer_member_id=reviewer_member_id,
        )

        async with self._tx.transaction() as tx:
            await self._repo.save(case, tx=tx)
            await self._publisher.publish_events(
                [event], partition_key=str(target_id), tx=tx,
            )

        logger.info(
            "Review created: id=%s target=%s:%s",
            case.id, target_kind.value, target_id,
        )
        return case

    async def decide(
        self,
        review_id: UUID,
        *,
        verdict: Verdict,
        reason: str = "",
        correction: str | None = None,
    ) -> ReviewCase:
        """做出审核决策。

        Raises:
            ValueError: case 不存在或已决策
        """
        async with self._tx.transaction() as tx:
            case = await self._repo.get_by_id(review_id, tx=tx)
            if case is None:
                raise ValueError(f"ReviewCase {review_id} not found")

            case.decide(verdict=verdict, reason=reason, correction=correction)
            await self._repo.save(case, tx=tx)

            events = case.pending_events
            case.clear_pending_events()
            if events:
                await self._publisher.publish_events(
                    events, partition_key=str(case.target_id), tx=tx,
                )

        logger.info(
            "Review decided: id=%s verdict=%s target=%s",
            review_id, verdict.value, case.target_id,
        )
        return case

    async def check_review_limit(
        self,
        target_kind: ReviewTargetKind,
        target_id: UUID,
    ) -> bool:
        """检查审核轮次是否超限。

        Returns:
            True 表示已超限 (应拒绝再次审核)
        """
        count = await self._repo.count_by_target(target_kind.value, target_id)
        return count >= MAX_REVIEW_ROUNDS

    async def get_pending(self) -> list[ReviewCase]:
        """获取待审核队列。"""
        return await self._repo.find_pending()


# ---------------------------------------------------------------------------
# ConflictService — 冲突检测与解决
# ---------------------------------------------------------------------------


class ConflictService:
    """冲突检测与解决服务。

    管理 Memory 间语义冲突的检测、隔离和解决。
    """

    def __init__(
        self,
        *,
        conflict_repo: ConflictRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = conflict_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def report_conflict(
        self,
        *,
        memory_a_id: MemoryId,
        memory_b_id: MemoryId,
        conflict_kind: ConflictKind,
        detected_by: DetectorKind,
    ) -> ConflictCase:
        """报告冲突。

        幂等: 同一对 memory 的未解决冲突不会重复创建。
        """
        # 幂等检查
        existing = await self._repo.find_by_memory(memory_a_id)
        for case in existing:
            if (
                not case.is_resolved
                and (case.memory_b_id == memory_b_id or case.memory_a_id == memory_b_id)
            ):
                return case

        case = ConflictCase(
            memory_a_id=memory_a_id,
            memory_b_id=memory_b_id,
            conflict_kind=conflict_kind,
            detected_by=detected_by,
        )

        from ..domain.events import ConflictDetected

        event = ConflictDetected(
            event_type="governance.conflict_case.detected",
            conflict_case_id=case.id,
            memory_a_id=memory_a_id,
            memory_b_id=memory_b_id,
            conflict_kind=conflict_kind.value,
            detected_by=detected_by.value,
        )

        async with self._tx.transaction() as tx:
            await self._repo.save(case, tx=tx)
            await self._publisher.publish_events(
                [event], partition_key=str(memory_a_id), tx=tx,
            )

        logger.info(
            "Conflict reported: %s vs %s kind=%s",
            memory_a_id, memory_b_id, conflict_kind,
        )
        return case

    async def resolve_conflict(
        self,
        conflict_id: UUID,
        *,
        resolution: ResolutionKind,
        winner_id: MemoryId | None = None,
        resolved_by: MemberId,
    ) -> ConflictCase:
        """解决冲突。

        Raises:
            ValueError: case 不存在或已解决
        """
        async with self._tx.transaction() as tx:
            case = await self._repo.get_by_id(conflict_id, tx=tx)
            if case is None:
                raise ValueError(f"ConflictCase {conflict_id} not found")

            case.resolve(
                resolution=resolution,
                winner_id=winner_id,
                resolved_by=resolved_by,
            )
            await self._repo.save(case, tx=tx)

            events = case.pending_events
            case.clear_pending_events()
            if events:
                await self._publisher.publish_events(
                    events, partition_key=str(case.memory_a_id), tx=tx,
                )

        logger.info(
            "Conflict resolved: id=%s resolution=%s",
            conflict_id, resolution.value,
        )
        return case

    async def is_memory_in_conflict(self, memory_id: MemoryId) -> bool:
        """检查 Memory 是否有未解决的冲突 (召回路径硬屏蔽)。"""
        cases = await self._repo.find_by_memory(memory_id)
        return any(not c.is_resolved for c in cases)

    async def get_unresolved(self) -> list[ConflictCase]:
        """获取所有未解决的冲突。"""
        return await self._repo.find_unresolved()
