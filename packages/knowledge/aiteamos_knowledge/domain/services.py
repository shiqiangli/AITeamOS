"""
Knowledge Context — 领域服务 (arch.md §2.6, §2.7)。

ConfidenceAdjustmentService: 置信度计算（实时反馈 + 每日衰减）
MemoryConflictDetector: 冲突检测协议
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from aiteamos_shared.types import MemberId, MemoryId

from .events import MemoryFeedbackRecorded, MemoryQuarantinedEvent
from .invariants import (
    CONFIDENCE_MAX,
    CONFIDENCE_MIN,
    THRESHOLD_QUARANTINE,
    compute_decay_factor,
    is_decay_eligible,
    validate_confidence_value,
)
from .models import (
    ConfidenceState,
    LifecycleState,
    MemoryContent,
    MemoryNode,
    Provenance,
    Tier,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Repository Protocol（领域服务依赖倒置）
# ---------------------------------------------------------------------------


class MemoryNodeRepositoryLike(Protocol):
    """Repository protocol for domain services."""

    async def get_by_id(self, id: Any, *, tx: Any = None) -> MemoryNode | None: ...
    async def save(self, aggregate: MemoryNode, *, tx: Any = None) -> None: ...
    async def lock_for_update(self, id: Any, *, tx: Any) -> MemoryNode | None: ...


class TransactionManagerLike(Protocol):
    """Transaction context manager protocol."""

    async def __aenter__(self) -> Any: ...
    async def __aexit__(self, *args: Any) -> None: ...


class EventBusLike(Protocol):
    """Event publisher protocol."""

    async def publish(self, event: Any, *, partition_key: str) -> None: ...


# ---------------------------------------------------------------------------
# ConfidenceAdjustmentService (arch.md §2.6)
# ---------------------------------------------------------------------------


@dataclass
class DecayParameters:
    """衰减参数配置。"""

    alpha: Decimal = Decimal("0.30")  # 正反馈系数 (Patterns)
    beta: Decimal = Decimal("0.20")  # 负反馈系数 (Patterns)
    threshold_quarantine: Decimal = THRESHOLD_QUARANTINE


class ConfidenceAdjustmentService:
    """置信度调整服务 (arch.md §2.6)。

    双通道:
    1. 实时事件驱动: Memory 反馈写入即触发
    2. 每日批处理: 时间衰减
    """

    def __init__(
        self,
        *,
        repository: MemoryNodeRepositoryLike,
        event_bus: EventBusLike | None = None,
        params: DecayParameters | None = None,
    ):
        self._repo = repository
        self._bus = event_bus
        self._params = params or DecayParameters()

    async def on_feedback(
        self,
        evt: MemoryFeedbackRecorded,
        *,
        tx: Any = None,
    ) -> MemoryNode | None:
        """通道 1: 实时反馈驱动置信度调整。

        元递归隔离: system_meta 反馈不参与置信度。
        """
        # 元递归隔离
        if evt.is_system_meta:
            logger.debug(
                "Skipping system_meta feedback for memory %s", evt.memory_id
            )
            return None

        node = await self._repo.lock_for_update(evt.memory_id, tx=tx)
        if node is None:
            logger.warning("Memory %s not found for feedback", evt.memory_id)
            return None

        old_value = node.confidence.value
        new_value = self._compute_step(node, evt)

        # 钳位 [0, 1]
        new_value = max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, new_value))
        validate_confidence_value(new_value)

        # 判断状态变更
        new_state = node.confidence.state
        if new_value < self._params.threshold_quarantine:
            new_state = ConfidenceState.NEEDS_VERIFY
            node.change_lifecycle(LifecycleState.NEEDS_VERIFY)

        node.adjust_confidence(new_value, state=new_state)
        await self._repo.save(node, tx=tx)

        logger.debug(
            "Confidence adjusted: memory=%s, %.3f → %.3f",
            evt.memory_id,
            old_value,
            new_value,
        )
        return node

    def _compute_step(
        self, node: MemoryNode, evt: MemoryFeedbackRecorded
    ) -> Decimal:
        """根据反馈计算新的置信度值。"""
        params = self._get_params_for_tier(node.tier)
        current = node.confidence.value

        if evt.outcome == "positive":
            delta = params["alpha"] * (Decimal("1") - current)
        elif evt.outcome == "negative":
            delta = -params["beta"] * current
        else:  # neutral
            delta = Decimal("0")

        return current + delta

    def _get_params_for_tier(self, tier: Tier) -> dict[str, Decimal]:
        """获取特定层级的反馈系数。"""
        # arch.md §2.6 表格
        table = {
            Tier.FACTS: {"alpha": Decimal("0.30"), "beta": Decimal("0.20")},
            Tier.PATTERNS: {"alpha": Decimal("0.20"), "beta": Decimal("0.15")},
            Tier.PRINCIPLES: {"alpha": Decimal("0.10"), "beta": Decimal("0.10")},
        }
        return table.get(tier, table[Tier.PATTERNS])

    async def apply_decay(
        self,
        node: MemoryNode,
        *,
        days_elapsed: float,
        tx: Any = None,
    ) -> MemoryNode | None:
        """通道 2: 时间衰减。

        I-K-2: tier=Facts 不参与时间衰减。
        """
        if not is_decay_eligible(node):
            return None

        factor = compute_decay_factor(node.tier.value, days_elapsed)
        new_value = (node.confidence.value * factor).quantize(Decimal("0.001"))
        new_value = max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, new_value))

        if new_value == node.confidence.value:
            return None

        node.adjust_confidence(new_value)

        if new_value < self._params.threshold_quarantine:
            node.change_lifecycle(LifecycleState.NEEDS_VERIFY)

        await self._repo.save(node, tx=tx)
        return node


# ---------------------------------------------------------------------------
# MemoryConflictDetector (arch.md §2.7)
# ---------------------------------------------------------------------------


@dataclass
class ConflictCandidate:
    """冲突候选。"""

    memory_a_id: MemoryId
    memory_b_id: MemoryId
    conflict_kind: str  # 'semantic' | 'scope' | 'temporal'
    detected_by: str  # 'auto_admission' | 'periodic_scan' | 'recall_collision'
    similarity_score: float = 0.0


class MemoryConflictDetector:
    """Memory 冲突检测服务。

    检测策略:
    1. auto_admission: 新 Memory 入库时检查语义相似性
    2. periodic_scan: 定期全量扫描
    3. recall_collision: 召回时检测同一查询返回矛盾结论

    Stage 1.2 仅定义接口，完整实现在 Stage 4.3。
    """

    def __init__(
        self,
        *,
        repository: MemoryNodeRepositoryLike,
        event_bus: EventBusLike | None = None,
    ):
        self._repo = repository
        self._bus = event_bus

    async def detect_semantic_conflicts(
        self,
        new_memory: MemoryNode,
        *,
        candidates: list[MemoryNode] | None = None,
        threshold: float = 0.85,
    ) -> list[ConflictCandidate]:
        """检测语义冲突 (Stage 1.2: 基础框架)。

        通过比较 content.statement 的简单字符串相似度进行初筛。
        完整向量相似度比较在 Stage 4.3 (pgvector 投影就绪后) 实现。
        """
        conflicts: list[ConflictCandidate] = []
        if candidates is None:
            return conflicts

        for candidate in candidates:
            if candidate.id == new_memory.id:
                continue
            if not candidate.is_recallable():
                continue

            # 简单的标签重叠检测作为初步筛选
            tags_a = set(new_memory.content.tags)
            tags_b = set(candidate.content.tags)
            if not tags_a or not tags_b:
                continue

            overlap = len(tags_a & tags_b) / max(len(tags_a | tags_b), 1)
            if overlap >= threshold:
                conflicts.append(
                    ConflictCandidate(
                        memory_a_id=new_memory.id,
                        memory_b_id=candidate.id,
                        conflict_kind="semantic",
                        detected_by="auto_admission",
                        similarity_score=overlap,
                    )
                )

        return conflicts

    async def detect_scope_conflicts(
        self,
        new_memory: MemoryNode,
        *,
        candidates: list[MemoryNode] | None = None,
    ) -> list[ConflictCandidate]:
        """检测作用域冲突 (同一 statement 在不同 scope 有矛盾结论)。"""
        conflicts: list[ConflictCandidate] = []
        if candidates is None:
            return conflicts

        for candidate in candidates:
            if candidate.id == new_memory.id:
                continue
            # 同层级、同标题但不同 scope → 可能的 scope 冲突
            if (
                candidate.tier == new_memory.tier
                and candidate.title == new_memory.title
                and candidate.scope.kind != new_memory.scope.kind
            ):
                conflicts.append(
                    ConflictCandidate(
                        memory_a_id=new_memory.id,
                        memory_b_id=candidate.id,
                        conflict_kind="scope",
                        detected_by="auto_admission",
                    )
                )

        return conflicts

    async def detect_temporal_conflicts(
        self,
        new_memory: MemoryNode,
        *,
        candidates: list[MemoryNode] | None = None,
    ) -> list[ConflictCandidate]:
        """检测时间冲突 (同一主题在不同时间有矛盾结论)。

        当两条 Memory 标题相同、层级相同，但生命周期状态矛盾
        (一条 active 另一条 deprecated/needs_verify) 时标记为 temporal 冲突。
        """
        conflicts: list[ConflictCandidate] = []
        if candidates is None:
            return conflicts

        for candidate in candidates:
            if candidate.id == new_memory.id:
                continue
            if (
                candidate.title == new_memory.title
                and candidate.tier == new_memory.tier
                and candidate.lifecycle != new_memory.lifecycle
            ):
                active_states = {LifecycleState.ACTIVE}
                stale_states = {LifecycleState.DEPRECATED, LifecycleState.NEEDS_VERIFY}
                a_active = new_memory.lifecycle in active_states
                b_stale = candidate.lifecycle in stale_states
                b_active = candidate.lifecycle in active_states
                a_stale = new_memory.lifecycle in stale_states
                if (a_active and b_stale) or (b_active and a_stale):
                    conflicts.append(
                        ConflictCandidate(
                            memory_a_id=new_memory.id,
                            memory_b_id=candidate.id,
                            conflict_kind="temporal",
                            detected_by="auto_admission",
                        )
                    )

        return conflicts
