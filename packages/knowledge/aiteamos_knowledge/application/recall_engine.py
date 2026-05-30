"""
Knowledge Context — Memory Recall Engine (arch.md §2.5)。

CQRS 读侧：根据 Task 上下文召回 Memory，受 Token 预算约束。

6 阶段 Pipeline:
  Stage 1: 候选生成（4 通道并行: assigned / scope / vector / graph）
  Stage 2: 过滤（隔离区屏蔽 + 冲突屏蔽）
  Stage 3: 排序（综合 confidence + 相关性 + 分配权重 + 新鲜度）
  Stage 4: 预算裁剪（max_recall_tokens）
  Stage 5: 冲突标注
  Stage 6: 写入召回审计

召回通道容错：单通道故障降级（结果为空），不阻塞整体流程。
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid4

from aiteamos_shared.types import MemoryId, new_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskContext:
    """Task 上下文 — 召回引擎的输入。"""

    task_id: str
    member_id: UUID
    project_ids: list[UUID] = field(default_factory=list)
    dept_id: UUID | None = None
    embedding: list[float] | None = None  # Task embedding for vector search
    snapshot_id: UUID | None = None
    run_id: UUID | None = None


@dataclass(frozen=True)
class RecallBudget:
    """召回预算。"""

    max_recall_tokens: int = 8000


@dataclass
class RecallCandidate:
    """召回候选 — 一条 Memory 的召回视图。"""

    memory_id: MemoryId
    title: str
    statement: str
    lifecycle_state: str
    confidence: float
    tokens: int = 0  # estimated tokens
    # Scoring components (raw values, normalized later)
    assigned_weight: float = 0.0
    cos_distance: float = 1.0  # 1.0 = worst, 0.0 = best
    scope_match: float = 0.0
    freshness: float = 0.0
    # Conflict annotation
    has_conflict: bool = False
    conflict_note: str = ""
    # Computed score
    score: float = 0.0
    # Source channel(s)
    channels: set[str] = field(default_factory=set)


@dataclass
class RecallResult:
    """召回结果。"""

    memories: list[RecallCandidate]
    total_tokens: int = 0
    degraded_channels: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocols — 通道数据源
# ---------------------------------------------------------------------------


class AssignedMemoryFetcher(Protocol):
    """获取显式分配给 Member 的 Memory。"""

    async def fetch_assigned(self, member_id: UUID) -> set[MemoryId]: ...


class ScopeMemoryFetcher(Protocol):
    """按作用域匹配 Memory。"""

    async def fetch_by_scope(
        self, project_ids: list[UUID], dept_id: UUID | None
    ) -> set[MemoryId]: ...


class VectorMemoryFetcher(Protocol):
    """pgvector top-K 语义搜索。"""

    async def fetch_vector_topk(
        self, embedding: list[float] | None, k: int
    ) -> set[MemoryId]: ...


class GraphMemoryFetcher(Protocol):
    """图遍历 2-hop 邻居 (M2: PostgreSQL 递归 CTE)。"""

    async def fetch_graph_neighbors(
        self, seed_ids: set[MemoryId], depth: int
    ) -> set[MemoryId]: ...


class MemoryDetailFetcher(Protocol):
    """批量获取 Memory 详情用于排序。"""

    async def fetch_details(
        self, memory_ids: set[MemoryId]
    ) -> list[RecallCandidate]: ...


class RecallAuditLogger(Protocol):
    """召回审计日志写入。"""

    async def log_recall(
        self,
        snapshot_id: UUID | None,
        run_id: UUID | None,
        candidates: list[RecallCandidate],
    ) -> None: ...


class ConflictChecker(Protocol):
    """检查未解决的冲突。"""

    async def get_unresolved_conflicts(
        self, memory_ids: set[MemoryId]
    ) -> set[MemoryId]: ...


# ---------------------------------------------------------------------------
# RecallChannelOrchestrator (arch.md §2.5)
# ---------------------------------------------------------------------------


class RecallChannelOrchestrator:
    """召回通道编排器：每通道独立超时，超时降级而非失败。

    设计约束：任何单通道失败不得导致 recall 报错，仅降低召回质量。
    """

    CHANNEL_TIMEOUTS: dict[str, timedelta] = {
        "assigned": timedelta(milliseconds=100),
        "scope": timedelta(milliseconds=200),
        "vector": timedelta(milliseconds=300),
        "graph": timedelta(milliseconds=500),
    }
    TOTAL_DEADLINE: timedelta = timedelta(milliseconds=700)
    VECTOR_TOP_K: int = 200

    def __init__(
        self,
        *,
        assigned_fetcher: AssignedMemoryFetcher,
        scope_fetcher: ScopeMemoryFetcher,
        vector_fetcher: VectorMemoryFetcher,
        graph_fetcher: GraphMemoryFetcher,
    ):
        self._assigned = assigned_fetcher
        self._scope = scope_fetcher
        self._vector = vector_fetcher
        self._graph = graph_fetcher

    async def fetch_all_channels(
        self, ctx: TaskContext
    ) -> tuple[set[MemoryId], list[str]]:
        """并行获取所有通道的候选 Memory ID。

        Returns:
            (candidates, degraded_channels)
        """
        # Build channel coroutines
        channel_coros = {
            "assigned": self._assigned.fetch_assigned(ctx.member_id),
            "scope": self._scope.fetch_by_scope(ctx.project_ids, ctx.dept_id),
            "vector": self._vector.fetch_vector_topk(ctx.embedding, k=self.VECTOR_TOP_K),
        }

        # Create tasks with individual timeouts
        tasks: dict[str, asyncio.Task] = {}
        for name, coro in channel_coros.items():
            timeout_sec = self.CHANNEL_TIMEOUTS[name].total_seconds()
            tasks[name] = asyncio.create_task(
                asyncio.wait_for(coro, timeout=timeout_sec),
                name=name,
            )

        # Graph channel depends on scope results, but we can start with ctx
        graph_timeout = self.CHANNEL_TIMEOUTS["graph"].total_seconds()
        tasks["graph"] = asyncio.create_task(
            asyncio.wait_for(
                self._graph.fetch_graph_neighbors(set(), depth=2),
                timeout=graph_timeout,
            ),
            name="graph",
        )

        # Wait for all with total deadline
        done, pending = await asyncio.wait(
            set(tasks.values()),
            timeout=self.TOTAL_DEADLINE.total_seconds(),
            return_when=asyncio.ALL_COMPLETED,
        )

        candidates: set[MemoryId] = set()
        degraded: list[str] = []

        for name, task in tasks.items():
            if task in done:
                try:
                    result = task.result()
                    candidates |= result
                except (asyncio.TimeoutError, Exception) as exc:
                    logger.warning(
                        "Recall channel '%s' degraded: %s", name, exc
                    )
                    degraded.append(name)
            else:
                task.cancel()
                logger.warning("Recall channel '%s' timed out (deadline)", name)
                degraded.append(name)

        return candidates, degraded


# ---------------------------------------------------------------------------
# MemoryRecallEngine (arch.md §2.5)
# ---------------------------------------------------------------------------


class MemoryRecallEngine:
    """读路径：根据 Task 上下文召回 Memory，受 Token 预算约束。

    强制约束：调用方必须在 REPEATABLE READ 事务内调用 recall()。
    """

    # Ranking weights (arch.md §2.5)
    W_ASSIGNED = 0.30
    W_CONFIDENCE = 0.25
    W_SIMILARITY = 0.20
    W_SCOPE = 0.15
    W_FRESHNESS = 0.10

    # Scope match scores
    SCOPE_MATCH_SCORES: dict[str, float] = {
        "project": 1.0,
        "tech_stack": 0.75,
        "department": 0.5,
        "global": 0.25,
    }

    # Blocked lifecycle states
    BLOCKED_STATES = {"quarantined", "deprecated", "archived"}

    def __init__(
        self,
        *,
        channel_orchestrator: RecallChannelOrchestrator,
        detail_fetcher: MemoryDetailFetcher,
        audit_logger: RecallAuditLogger,
        conflict_checker: ConflictChecker,
    ):
        self._orchestrator = channel_orchestrator
        self._details = detail_fetcher
        self._audit = audit_logger
        self._conflicts = conflict_checker

    async def recall(
        self, ctx: TaskContext, budget: RecallBudget
    ) -> RecallResult:
        """执行 6 阶段召回 pipeline。"""

        # Stage 1: 候选生成（多通道并行）
        candidate_ids, degraded = await self._orchestrator.fetch_all_channels(ctx)

        if not candidate_ids:
            return RecallResult(memories=[], total_tokens=0, degraded_channels=degraded)

        # Fetch details for scoring
        candidates = await self._details.fetch_details(candidate_ids)

        # Tag channels
        for c in candidates:
            c.channels = {"combined"}

        # Stage 2: 过滤
        candidates = self._filter(candidates)

        if not candidates:
            return RecallResult(memories=[], total_tokens=0, degraded_channels=degraded)

        # Mask unresolved conflicts
        conflict_ids = await self._conflicts.get_unresolved_conflicts(
            {c.memory_id for c in candidates}
        )
        candidates = [c for c in candidates if c.memory_id not in conflict_ids]

        if not candidates:
            return RecallResult(memories=[], total_tokens=0, degraded_channels=degraded)

        # Stage 3: 排序
        self._rank(candidates, ctx)

        # Stage 4: 预算裁剪
        selected = self._truncate_to_budget(candidates, budget.max_recall_tokens)

        # Stage 5: 冲突标注
        await self._annotate_conflicts(selected)

        # Stage 6: 写入召回审计
        await self._audit.log_recall(ctx.snapshot_id, ctx.run_id, selected)

        total_tokens = sum(m.tokens for m in selected)
        return RecallResult(
            memories=selected, total_tokens=total_tokens, degraded_channels=degraded
        )

    # -- Stage 2: Filter --

    def _filter(self, candidates: list[RecallCandidate]) -> list[RecallCandidate]:
        """过滤隔离区/废弃/归档的 Memory。"""
        return [
            c for c in candidates if c.lifecycle_state not in self.BLOCKED_STATES
        ]

    # -- Stage 3: Rank --

    def _rank(
        self, candidates: list[RecallCandidate], ctx: TaskContext
    ) -> None:
        """排序公式 (arch.md §2.5):
        score(m) = 0.30·σ(assigned_weight) + 0.25·σ(confidence)
                 + 0.20·σ(1-cos_distance) + 0.15·σ(scope_match) + 0.10·σ(freshness)
        where σ = min-max normalize within candidate set
        """
        if not candidates:
            return

        # Compute scope_match for each candidate
        for c in candidates:
            c.scope_match = self._compute_scope_match(c, ctx)

        # Min-max normalize each dimension
        self._normalize_field(candidates, "assigned_weight")
        self._normalize_field(candidates, "confidence")

        # For similarity: use (1 - cos_distance)
        for c in candidates:
            c._similarity = 1.0 - c.cos_distance  # type: ignore[attr-defined]
        self._normalize_field(candidates, "_similarity")

        self._normalize_field(candidates, "scope_match")
        self._normalize_field(candidates, "freshness")

        # Compute final score
        for c in candidates:
            sim = getattr(c, "_similarity", 0.0)
            c.score = (
                self.W_ASSIGNED * c.assigned_weight
                + self.W_CONFIDENCE * c.confidence
                + self.W_SIMILARITY * sim
                + self.W_SCOPE * c.scope_match
                + self.W_FRESHNESS * c.freshness
            )

        # Sort descending by score
        candidates.sort(key=lambda c: c.score, reverse=True)

    @staticmethod
    def _normalize_field(
        candidates: list[RecallCandidate], field_name: str
    ) -> None:
        """Min-max normalization of a field across all candidates."""
        values = [getattr(c, field_name) for c in candidates]
        min_val = min(values)
        max_val = max(values)
        rng = max_val - min_val
        if rng < 1e-12:
            # All same value — normalize to 0.5
            for c in candidates:
                setattr(c, field_name, 0.5)
        else:
            for c in candidates:
                raw = getattr(c, field_name)
                setattr(c, field_name, (raw - min_val) / rng)

    @staticmethod
    def _compute_scope_match(
        candidate: RecallCandidate, ctx: TaskContext
    ) -> float:
        """Compute scope match score based on candidate scope kind."""
        # Default: use the pre-set scope_match from detail fetcher
        return candidate.scope_match

    # -- Stage 4: Budget trim --

    @staticmethod
    def _truncate_to_budget(
        candidates: list[RecallCandidate], max_tokens: int
    ) -> list[RecallCandidate]:
        """裁剪到 Token 预算上限。"""
        selected: list[RecallCandidate] = []
        total = 0
        for c in candidates:
            if total + c.tokens > max_tokens:
                break
            selected.append(c)
            total += c.tokens
        return selected

    # -- Stage 5: Conflict annotation --

    async def _annotate_conflicts(self, candidates: list[RecallCandidate]) -> None:
        """标注选中候选集中仍存在未解决冲突的 Memory。

        Stage 2 已过滤掉冲突 Memory，但如果裁剪后新产生的子集中
        存在配对冲突，此处重新标记。
        """
        if not candidates:
            return
        ids = {c.memory_id for c in candidates}
        conflict_ids = await self._conflicts.get_unresolved_conflicts(ids)
        for c in candidates:
            if c.memory_id in conflict_ids:
                c.has_conflict = True
