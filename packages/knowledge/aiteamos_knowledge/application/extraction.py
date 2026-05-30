"""
Knowledge Context — Memory 自动提取 Pipeline (plan.md §2.6)。

从 Task 执行过程中自动提炼 Memory 候选：
1. 监听 RunFinished 事件
2. 基于 (Snapshot + Run Trace + Outcome) 调用 LLM 提取 Memory 候选
3. 候选写入 memory_node 表 (lifecycle=candidate)
4. 元递归隔离: provenance.system_meta=true 的事件不进入提取

边缘场景:
- 单 Task 产出 Memory 爆炸限流 (默认上限 10 条)
- 审核超时降级 (7 天未审核 → 高置信度自动入库)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid4

from aiteamos_shared.llm import llm_extract
from aiteamos_shared.types import MemberId, MemoryId, RunId, TaskId, new_id

from ..domain.models import (
    Confidence,
    ConfidenceState,
    LifecycleState,
    MemoryContent,
    MemoryNode,
    Provenance,
    Scope,
    ScopeKind,
    SourceKind,
    Tier,
)

logger = logging.getLogger(__name__)

# 单 Task 提取候选数量上限 (PRD "50+ 条" 场景防护)
MAX_CANDIDATES_PER_TASK = 10

# 审核超时天数
REVIEW_TIMEOUT_DAYS = 7

# 高置信度自动入库阈值
AUTO_APPROVE_CONFIDENCE = Decimal("0.85")

# 提取 prompt 模板
EXTRACTION_SYSTEM_PROMPT = """You are a knowledge extraction agent for AITeamOS.
Given the context of a completed task execution (including snapshot, run trace, and outcome),
extract actionable knowledge entries ("Memory candidates") that could help future tasks.

Output format: JSON array of objects, each with:
- title: short descriptive title
- statement: the core knowledge claim (1-2 sentences)
- applicable_when: when this knowledge is useful
- counter_example: when this knowledge might NOT apply
- tier: one of "facts", "patterns", "principles"
- tags: list of relevant tags

Return ONLY valid JSON. If no useful knowledge can be extracted, return []."""


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractionInput:
    """Memory 提取输入数据。"""
    task_id: TaskId
    run_id: RunId
    member_id: MemberId
    department_id: UUID
    project_ids: list[UUID] = field(default_factory=list)
    snapshot_content: dict[str, Any] = field(default_factory=dict)
    run_trace: dict[str, Any] = field(default_factory=dict)
    outcome: str = "success"  # success | failure | cancelled
    retry_count: int = 0


@dataclass
class MemoryCandidate:
    """提取出的 Memory 候选。"""
    title: str
    statement: str
    applicable_when: str = ""
    counter_example: str = ""
    tier: str = "facts"
    tags: list[str] = field(default_factory=list)
    confidence: Decimal = Decimal("0.500")


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class MemoryNodeRepoLike(Protocol):
    async def save(self, aggregate: MemoryNode, *, tx: Any = None) -> None: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


# ---------------------------------------------------------------------------
# ReflectionEngine — 简化版 (arch.md §5.1.4)
# ---------------------------------------------------------------------------


class ReflectionEngine:
    """Memory 自动提取引擎 — 从 Task 执行结果中提取知识候选。

    核心职责:
    1. 接收 RunFinished 事件
    2. 调用 LLM 提取 Memory 候选
    3. 候选写入 memory_node (lifecycle=candidate)
    4. 元递归隔离 (system_meta=true 不进入提取)
    5. 单 Task 候选数量限流
    """

    def __init__(
        self,
        *,
        memory_repo: MemoryNodeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = memory_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def extract_from_run(self, input_data: ExtractionInput) -> list[MemoryNode]:
        """从一次 Run 完成中提取 Memory 候选。

        Args:
            input_data: 提取输入 (snapshot + run trace + outcome)

        Returns:
            创建的 Memory 候选列表
        """
        # 元递归隔离: system_meta 事件不进入提取
        if self._is_system_meta(input_data):
            logger.debug("Skipping system_meta event for task=%s", input_data.task_id)
            return []

        # 调用 LLM 提取
        candidates = await self._extract_candidates(input_data)
        if not candidates:
            return []

        # 限流: 单 Task 产出上限
        if len(candidates) > MAX_CANDIDATES_PER_TASK:
            logger.warning(
                "Task %s produced %d candidates, truncating to %d",
                input_data.task_id, len(candidates), MAX_CANDIDATES_PER_TASK,
            )
            candidates = candidates[:MAX_CANDIDATES_PER_TASK]

        # 高价值来源标记: 经历过 retry 的 Task
        is_high_value = input_data.retry_count > 0
        source_kind = SourceKind.HARNESS_DEBUG if is_high_value else SourceKind.TASK_EXECUTION
        initial_confidence = Decimal("0.700") if is_high_value else Decimal("0.500")

        # 创建 Memory 候选节点
        created_nodes: list[MemoryNode] = []
        async with self._tx.transaction() as tx:
            for candidate in candidates:
                node = self._build_candidate_node(
                    candidate=candidate,
                    input_data=input_data,
                    source_kind=source_kind,
                    initial_confidence=initial_confidence,
                )
                await self._repo.save(node, tx=tx)
                created_nodes.append(node)

            # 发布事件
            events = []
            for node in created_nodes:
                events.extend(node.pending_events)
                node.clear_pending_events()
            if events:
                await self._publisher.publish_events(
                    events,
                    partition_key=str(input_data.task_id),
                    tx=tx,
                )

        logger.info(
            "Extracted %d Memory candidates from task=%s run=%s",
            len(created_nodes), input_data.task_id, input_data.run_id,
        )
        return created_nodes

    async def _extract_candidates(
        self, input_data: ExtractionInput
    ) -> list[MemoryCandidate]:
        """调用 LLM 提取 Memory 候选。"""
        prompt = self._build_prompt(input_data)

        try:
            response = await llm_extract(
                prompt=prompt,
                system=EXTRACTION_SYSTEM_PROMPT,
            )
            return self._parse_response(response)
        except Exception as e:
            logger.error(
                "LLM extraction failed for task=%s: %s",
                input_data.task_id, str(e),
            )
            return []

    @staticmethod
    def _build_prompt(input_data: ExtractionInput) -> str:
        """构建 LLM 提取 prompt。"""
        return json.dumps({
            "task_id": input_data.task_id,
            "outcome": input_data.outcome,
            "retry_count": input_data.retry_count,
            "snapshot_summary": str(input_data.snapshot_content)[:2000],
            "run_trace_summary": str(input_data.run_trace)[:2000],
        })

    @staticmethod
    def _parse_response(response: str) -> list[MemoryCandidate]:
        """解析 LLM 响应为 MemoryCandidate 列表。"""
        try:
            # 尝试从响应中提取 JSON
            text = response.strip()
            # 处理 markdown 代码块
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

            data = json.loads(text)
            if not isinstance(data, list):
                return []

            candidates = []
            for item in data:
                if not isinstance(item, dict) or "title" not in item or "statement" not in item:
                    continue
                candidates.append(MemoryCandidate(
                    title=item["title"],
                    statement=item["statement"],
                    applicable_when=item.get("applicable_when", ""),
                    counter_example=item.get("counter_example", ""),
                    tier=item.get("tier", "facts"),
                    tags=item.get("tags", []),
                ))
            return candidates
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to parse LLM extraction response: %s", str(e))
            return []

    @staticmethod
    def _is_system_meta(input_data: ExtractionInput) -> bool:
        """检查是否为系统元活动（应被隔离）。"""
        meta = input_data.run_trace.get("system_meta", False)
        return bool(meta)

    @staticmethod
    def _build_candidate_node(
        *,
        candidate: MemoryCandidate,
        input_data: ExtractionInput,
        source_kind: SourceKind,
        initial_confidence: Decimal,
    ) -> MemoryNode:
        """构建 Memory 候选节点。"""
        tier = Tier(candidate.tier) if candidate.tier in ("facts", "patterns", "principles") else Tier.FACTS

        # 确定 scope: 有 project 则 project 级，否则 department 级
        if input_data.project_ids:
            scope = Scope(kind=ScopeKind.PROJECT, ref=input_data.project_ids[0])
        else:
            scope = Scope(kind=ScopeKind.DEPARTMENT, ref=input_data.department_id)

        content = MemoryContent(
            statement=candidate.statement,
            applicable_when=candidate.applicable_when,
            counter_example=candidate.counter_example,
            tags=candidate.tags,
        )

        provenance = Provenance(
            source_kind=source_kind,
            task_id=input_data.task_id,
            run_id=input_data.run_id,
            member_id=input_data.member_id,
            system_meta=False,
        )

        confidence = Confidence(
            value=initial_confidence,
            state=ConfidenceState.NEEDS_VERIFY,
            last_updated=datetime.now(timezone.utc),
            last_decay_at=datetime.now(timezone.utc),
        )

        return MemoryNode(
            id=new_id(),
            tier=tier,
            scope=scope,
            title=candidate.title,
            content=content,
            confidence=confidence,
            provenance=provenance,
            lifecycle=LifecycleState.CANDIDATE,
        )


# ---------------------------------------------------------------------------
# ReviewQueue — Memory 候选审核队列
# ---------------------------------------------------------------------------


class MemoryReviewQueue:
    """Memory 候选审核队列。

    提供:
    - 查询待审核候选
    - 批准入库 (candidate → active)
    - 拒绝 (candidate → deprecated)
    - 合并到已有节点
    - 超时自动处理
    """

    def __init__(
        self,
        *,
        memory_repo: MemoryNodeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = memory_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def approve(self, memory_id: MemoryId) -> MemoryNode:
        """批准候选 → active。"""
        async with self._tx.transaction() as tx:
            node = await self._repo.lock_for_update(memory_id, tx=tx)
            if node is None:
                raise ValueError(f"Memory {memory_id} not found")
            if node.lifecycle != LifecycleState.CANDIDATE:
                raise ValueError(f"Memory {memory_id} is not a candidate (state={node.lifecycle})")

            node.lifecycle = LifecycleState.ACTIVE
            await self._repo.save(node, tx=tx)

            events = node.pending_events
            node.clear_pending_events()
            if events:
                await self._publisher.publish_events(
                    events, partition_key=str(memory_id), tx=tx
                )
        return node

    async def reject(self, memory_id: MemoryId) -> MemoryNode:
        """拒绝候选 → deprecated。"""
        async with self._tx.transaction() as tx:
            node = await self._repo.lock_for_update(memory_id, tx=tx)
            if node is None:
                raise ValueError(f"Memory {memory_id} not found")
            if node.lifecycle != LifecycleState.CANDIDATE:
                raise ValueError(f"Memory {memory_id} is not a candidate")

            node.lifecycle = LifecycleState.DEPRECATED
            await self._repo.save(node, tx=tx)

            events = node.pending_events
            node.clear_pending_events()
            if events:
                await self._publisher.publish_events(
                    events, partition_key=str(memory_id), tx=tx
                )
        return node

    async def process_expired_reviews(self) -> int:
        """处理超时未审核的候选 — 高置信度自动入库。

        Returns:
            处理的候选数量
        """
        logger.info("Processing expired memory candidate reviews")

        # Query candidate memories older than REVIEW_TIMEOUT_DAYS with high confidence
        candidates = await self._find_expired_candidates()
        if not candidates:
            return 0

        approved_count = 0
        for node in candidates:
            # Only auto-approve candidates above the confidence threshold
            if node.confidence.value >= AUTO_APPROVE_CONFIDENCE:
                try:
                    node.lifecycle = LifecycleState.ACTIVE
                    async with self._tx.transaction() as tx:
                        await self._repo.save(node, tx=tx)
                        events = node.pending_events
                        node.clear_pending_events()
                        if events:
                            await self._publisher.publish_events(
                                events, partition_key=str(node.id), tx=tx,
                            )
                    approved_count += 1
                    logger.info(
                        "Auto-approved memory candidate %s (confidence=%.3f)",
                        node.id, float(node.confidence.value),
                    )
                except Exception:
                    logger.exception("Failed to auto-approve memory %s", node.id)
            else:
                logger.debug(
                    "Memory %s below auto-approve threshold (%.3f < %.3f), keeping as candidate",
                    node.id, float(node.confidence.value), float(AUTO_APPROVE_CONFIDENCE),
                )

        logger.info("Processed %d expired reviews, approved %d", len(candidates), approved_count)
        return approved_count

    async def _find_expired_candidates(self) -> list[MemoryNode]:
        """Find candidate memories older than REVIEW_TIMEOUT_DAYS."""
        from datetime import datetime, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=REVIEW_TIMEOUT_DAYS)

        # Use repository protocol extension
        if hasattr(self._repo, "find_candidates_older_than"):
            return await self._repo.find_candidates_older_than(cutoff)

        # Fallback: no-op if repo doesn't support the query
        logger.debug("Repository does not support find_candidates_older_than")
        return []
