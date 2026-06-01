"""
API Gateway — ACL Bridges (arch.md §2.5, plan.md §2.2.2)。

连接 Execution Context 的 KnowledgeACL / CapabilityACL Protocol
到 Knowledge / Capability 的实际实现，在 Composition Root 注入。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from aiteamos_execution.application.context_assembler import (
    MemorySnippet,
    SkillBundle,
)
from aiteamos_knowledge.application.recall_engine import (
    MemoryRecallEngine,
    RecallBudget,
    TaskContext,
)

logger = logging.getLogger(__name__)


class RecallEngineKnowledgeACL:
    """KnowledgeACL 实现 — 委托 MemoryRecallEngine 执行召回。

    将 RecallCandidate 映射为 Execution 上下文的 MemorySnippet。
    """

    def __init__(self, *, recall_engine: MemoryRecallEngine) -> None:
        self._engine = recall_engine

    async def recall(
        self,
        *,
        task_id: str,
        member_id: UUID,
        project_ids: list[UUID],
        dept_id: UUID | None,
        max_recall_tokens: int,
    ) -> tuple[list[MemorySnippet], int]:
        ctx = TaskContext(
            task_id=task_id,
            member_id=member_id,
            project_ids=project_ids,
            dept_id=dept_id,
        )
        budget = RecallBudget(max_recall_tokens=max_recall_tokens)
        result = await self._engine.recall(ctx, budget)

        snippets = [
            MemorySnippet(
                memory_id=c.memory_id,
                title=c.title,
                statement=c.statement,
                confidence=c.confidence,
                score=c.score,
                tokens=c.tokens,
                has_conflict=c.has_conflict,
            )
            for c in result.memories
        ]

        if result.degraded_channels:
            logger.warning(
                "Recall for task %s: degraded channels %s",
                task_id,
                result.degraded_channels,
            )

        return snippets, result.total_tokens


# ---------------------------------------------------------------------------
# SQL query for Capability ACL
# ---------------------------------------------------------------------------

_FETCH_PUBLISHED_SKILLS = """
    SELECT id, name,
           version,
           description
    FROM skill
    WHERE id = ANY($1)
      AND status = 'published'
"""


class SqlCapabilityACL:
    """CapabilityACL 实现 — SQL 查询已发布的 Skill 并映射为 SkillBundle。"""

    def __init__(self, *, db: Any) -> None:
        self._db = db

    async def get_skill_bundle(
        self, *, skill_ids: list[UUID], member_id: UUID
    ) -> list[SkillBundle]:
        if not skill_ids:
            return []
        rows = await self._db.fetch(_FETCH_PUBLISHED_SKILLS, skill_ids)
        return [
            SkillBundle(
                skill_id=row["id"],
                name=row["name"],
                version=str(row["version"]),
                description=row.get("description", ""),
            )
            for row in rows
        ]
