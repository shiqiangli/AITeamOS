"""
Execution Context — Context Assembler (plan.md §2.2.2, arch.md §2.5)。

ACL 方式调用 Knowledge Context 的 Recall Engine，组装不可变 Context Snapshot。

流程:
1. 在 REPEATABLE READ 事务中执行
2. 调用 KnowledgeACL.recall() 获取 Memory 集合
3. 调用 Capability Context 获取 Skill Bundle
4. 组装不可变 Context Snapshot
5. 写入 task_context_snapshot 表
6. 发出 ContextSnapshotSealed 事件
"""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.types import MemberId, SkillId, TaskId, new_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class ContextSnapshotSealed(VersionedDomainEvent):
    """Context Snapshot 密封事件 — 快照写入后发出。"""

    event_type: str = "execution.context.snapshot_sealed"
    snapshot_id: UUID
    task_id: str
    memory_count: int
    skill_count: int
    total_tokens: int


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemorySnippet:
    """召回的 Memory 片段（ACL 转换后的视图）。"""

    memory_id: UUID
    title: str
    statement: str
    confidence: float
    score: float
    tokens: int
    has_conflict: bool = False


@dataclass(frozen=True)
class SkillBundle:
    """Skill 捆绑包（ACL 转换后的视图）。"""

    skill_id: UUID
    name: str
    version: str
    description: str = ""


@dataclass
class ContextSnapshot:
    """不可变 Context Snapshot (arch.md N1: 一旦持久化即只读)。"""

    id: UUID = field(default_factory=uuid4)
    task_id: str = ""
    run_id: UUID | None = None
    sealed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    memories: list[MemorySnippet] = field(default_factory=list)
    skills: list[SkillBundle] = field(default_factory=list)
    total_tokens: int = 0
    sha256: str = ""  # 不可变性校验

    def compute_sha256(self) -> str:
        """计算快照内容的 SHA-256 校验和。"""
        content = {
            "task_id": self.task_id,
            "sealed_at": self.sealed_at.isoformat(),
            "memories": [
                {
                    "memory_id": str(m.memory_id),
                    "title": m.title,
                    "statement": m.statement,
                    "score": m.score,
                }
                for m in self.memories
            ],
            "skills": [
                {"skill_id": str(s.skill_id), "name": s.name, "version": s.version}
                for s in self.skills
            ],
        }
        raw = json.dumps(content, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()

    def seal(self) -> None:
        """密封快照 — 计算 SHA-256。"""
        self.sha256 = self.compute_sha256()


# ---------------------------------------------------------------------------
# ACL Protocols (跨上下文访问 — 接口定义在 Execution 包内)
# ---------------------------------------------------------------------------


class KnowledgeACL(Protocol):
    """Knowledge Context 的 Anti-Corruption Layer。

    接口定义在 Execution 包内，实现在 Composition Root 注入。
    这样 Execution 不直接 import Knowledge 的仓储。
    """

    async def recall(
        self,
        *,
        task_id: str,
        member_id: UUID,
        project_ids: list[UUID],
        dept_id: UUID | None,
        max_recall_tokens: int,
    ) -> tuple[list[MemorySnippet], int]: ...


class CapabilityACL(Protocol):
    """Capability Context 的 ACL — 获取 Skill Bundle。"""

    async def get_skill_bundle(
        self, *, skill_ids: list[SkillId], member_id: UUID
    ) -> list[SkillBundle]: ...


class SnapshotRepository(Protocol):
    """Context Snapshot 持久化。"""

    async def save_snapshot(self, snapshot: ContextSnapshot, *, tx: Any) -> None: ...

    async def get_snapshot(self, snapshot_id: UUID) -> ContextSnapshot | None: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


# ---------------------------------------------------------------------------
# ContextAssembler
# ---------------------------------------------------------------------------


class ContextAssembler:
    """Context Assembler — 组装不可变 Context Snapshot (arch.md T3 阶段)。

    在 REPEATABLE READ 事务中:
    1. 调用 KnowledgeACL.recall() 获取 Memory
    2. 调用 CapabilityACL.get_skill_bundle() 获取 Skill
    3. 组装 ContextSnapshot
    4. 密封 (SHA-256)
    5. 持久化 + 发布事件
    """

    def __init__(
        self,
        *,
        knowledge_acl: KnowledgeACL,
        capability_acl: CapabilityACL,
        snapshot_repo: SnapshotRepository,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._knowledge = knowledge_acl
        self._capability = capability_acl
        self._repo = snapshot_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def assemble(
        self,
        *,
        task_id: str,
        member_id: UUID,
        project_ids: list[UUID] | None = None,
        dept_id: UUID | None = None,
        declared_skills: list[SkillId] | None = None,
        max_recall_tokens: int = 8000,
        run_id: UUID | None = None,
    ) -> ContextSnapshot:
        """组装 Context Snapshot。

        Args:
            task_id: Task ID
            member_id: 执行成员 ID
            project_ids: 关联项目 ID 列表
            dept_id: 部门 ID
            declared_skills: Task 声明的 Skill ID 列表
            max_recall_tokens: Memory 召回 Token 上限
            run_id: Run ID（可选）

        Returns:
            密封的 ContextSnapshot
        """
        project_ids = project_ids or []
        declared_skills = declared_skills or []

        async with self._tx.transaction() as tx:
            # 1. Memory Recall via Knowledge ACL
            memory_snippets, total_tokens = await self._knowledge.recall(
                task_id=task_id,
                member_id=member_id,
                project_ids=project_ids,
                dept_id=dept_id,
                max_recall_tokens=max_recall_tokens,
            )

            # 2. Skill Bundle via Capability ACL
            skill_bundles = await self._capability.get_skill_bundle(
                skill_ids=declared_skills, member_id=member_id
            )

            # 3. Assemble snapshot
            snapshot = ContextSnapshot(
                task_id=task_id,
                run_id=run_id,
                memories=memory_snippets,
                skills=skill_bundles,
                total_tokens=total_tokens,
            )

            # 4. Seal (compute SHA-256)
            snapshot.seal()

            # 5. Persist
            await self._repo.save_snapshot(snapshot, tx=tx)

            # 6. Publish event
            event = ContextSnapshotSealed(
                event_type="execution.context.snapshot_sealed",
                snapshot_id=snapshot.id,
                task_id=task_id,
                memory_count=len(memory_snippets),
                skill_count=len(skill_bundles),
                total_tokens=total_tokens,
            )
            await self._publisher.publish_events(
                [event], partition_key=task_id, tx=tx
            )

        logger.info(
            "ContextSnapshot %s sealed for task %s (memories=%d, skills=%d, tokens=%d)",
            snapshot.id,
            task_id,
            len(memory_snippets),
            len(skill_bundles),
            total_tokens,
        )
        return snapshot
