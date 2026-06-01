"""
Execution Context — PostgreSQL Repository 实现 (arch.md §2.2.4)。

PostgresTaskRepository: Task 聚合根仓储
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from aiteamos_shared.repository import BaseRepository, DatabasePool
from aiteamos_shared.types import TaskId

from ..application.context_assembler import ContextSnapshot, MemorySnippet, SkillBundle
from ..domain.models import (
    CostAccrued,
    DeliverableSpec,
    RunState,
    Task,
    TaskBudget,
    TaskDependency,
    TaskRun,
    TaskState,
)
from ..application.queries import TaskSummary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task Repository
# ---------------------------------------------------------------------------


class PostgresTaskRepository(BaseRepository[Task]):
    """Task 聚合根的 PostgreSQL 仓储实现。"""

    # -- Write SQL --

    UPSERT_TASK = """
        INSERT INTO task (
            id, department_id, parent_task_id, state, priority,
            title, description, deliverable_spec,
            declared_skills, declared_memory_hints,
            budget, retry_count, review_round,
            workflow_id, created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8::jsonb,
            $9, $10,
            $11::jsonb, $12, $13,
            $14, $15, $16
        )
        ON CONFLICT (id) DO UPDATE SET
            state = EXCLUDED.state,
            priority = EXCLUDED.priority,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            deliverable_spec = EXCLUDED.deliverable_spec,
            declared_skills = EXCLUDED.declared_skills,
            declared_memory_hints = EXCLUDED.declared_memory_hints,
            budget = EXCLUDED.budget,
            retry_count = EXCLUDED.retry_count,
            review_round = EXCLUDED.review_round,
            workflow_id = EXCLUDED.workflow_id,
            updated_at = EXCLUDED.updated_at
    """

    UPSERT_RUN = """
        INSERT INTO task_run (run_id, task_id, member_id, snapshot_id, state, cost, started_at, finished_at)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
        ON CONFLICT (run_id) DO UPDATE SET
            state = EXCLUDED.state,
            cost = EXCLUDED.cost,
            finished_at = EXCLUDED.finished_at
    """

    UPSERT_DEPENDENCY = """
        INSERT INTO task_dependency (task_id, depends_on_id)
        VALUES ($1, $2)
        ON CONFLICT (task_id, depends_on_id) DO NOTHING
    """

    UPSERT_PROJECT = """
        INSERT INTO task_project (task_id, project_id)
        VALUES ($1, $2)
        ON CONFLICT (task_id, project_id) DO NOTHING
    """

    SELECT_TASK = """
        SELECT * FROM task WHERE id = $1
    """

    SELECT_TASK_FOR_UPDATE = """
        SELECT * FROM task WHERE id = $1 FOR UPDATE
    """

    SELECT_RUNS = """
        SELECT * FROM task_run WHERE task_id = $1 ORDER BY started_at
    """

    SELECT_DEPENDENCIES = """
        SELECT * FROM task_dependency WHERE task_id = $1
    """

    SELECT_PROJECTS = """
        SELECT project_id FROM task_project WHERE task_id = $1
    """

    # -- Read-Side SQL (CQRS) --

    LIST_TASKS = """
        SELECT id, title, state, priority,
               department_id, retry_count, review_round, created_at
        FROM task
        WHERE ($1::uuid IS NULL OR department_id = $1)
          AND ($2::text IS NULL OR state = $2)
        ORDER BY
            CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END,
            created_at DESC
        OFFSET $3 LIMIT $4
    """

    LIST_TASKS_BY_STATE = """
        SELECT id, state FROM task WHERE state = ANY($1) ORDER BY created_at
    """

    COUNT_ACTIVE_RUNS = """
        SELECT COUNT(*) FROM job
        WHERE member_id = $1 AND state IN ('running', 'pending')
    """

    async def get_by_id(self, id: Any, *, tx: Any = None) -> Task | None:
        """加载 Task 聚合（含 dependencies、project_ids）。"""
        executor = tx if tx else self._db
        row = await executor.fetchrow(self.SELECT_TASK, id)
        if row is None:
            return None

        deps_rows = await executor.fetch(self.SELECT_DEPENDENCIES, id)
        proj_rows = await executor.fetch(self.SELECT_PROJECTS, id)

        return self._row_to_task(row, deps_rows, proj_rows)

    async def lock_for_update(self, id: Any, *, tx: Any) -> Task | None:
        """FOR UPDATE 行锁加载。"""
        row = await tx.fetchrow(self.SELECT_TASK_FOR_UPDATE, id)
        if row is None:
            return None

        deps_rows = await tx.fetch(self.SELECT_DEPENDENCIES, id)
        proj_rows = await tx.fetch(self.SELECT_PROJECTS, id)

        return self._row_to_task(row, deps_rows, proj_rows)

    async def save(self, aggregate: Task, *, tx: Any = None) -> None:
        """持久化 Task 聚合。"""
        executor = tx if tx else self._db

        deliverable_spec_dict = {
            "kind": aggregate.deliverable_spec.kind,
            "acceptance_criteria": aggregate.deliverable_spec.acceptance_criteria,
            "output_format": aggregate.deliverable_spec.output_format,
        }
        budget_dict = {
            "max_tokens": aggregate.budget.max_tokens,
            "max_duration_seconds": aggregate.budget.max_duration_seconds,
            "max_cost_usd": str(aggregate.budget.max_cost_usd),
            "max_retry_count": aggregate.budget.max_retry_count,
            "max_review_rounds": aggregate.budget.max_review_rounds,
        }

        await executor.execute(
            self.UPSERT_TASK,
            aggregate.id,
            aggregate.department_id,
            aggregate.parent_task_id,
            aggregate.state.value,
            aggregate.priority,
            aggregate.title,
            aggregate.description,
            json.dumps(deliverable_spec_dict),
            [str(s) for s in aggregate.declared_skills],
            [str(m) for m in aggregate.declared_memory_hints],
            json.dumps(budget_dict),
            aggregate.retry_count,
            aggregate.review_round,
            None,  # workflow_id — set by Saga
            aggregate.created_at,
            aggregate.updated_at,
        )

        # 保存依赖
        for dep in aggregate.dependencies:
            await executor.execute(
                self.UPSERT_DEPENDENCY,
                aggregate.id,
                dep.depends_on_id,
            )

        # 保存 project 关联
        for pid in aggregate.project_ids:
            await executor.execute(
                self.UPSERT_PROJECT,
                aggregate.id,
                pid,
            )

    # -- Read-Side (CQRS) --

    async def list_tasks(
        self,
        *,
        department_id: str | None = None,
        state: str | None = None,
        assigned_member_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[TaskSummary]:
        dept_uuid = UUID(department_id) if department_id else None
        rows = await self._db.fetch(
            self.LIST_TASKS, dept_uuid, state, offset, limit
        )
        return [self._row_to_summary(r) for r in rows]

    async def get_task_detail(self, task_id: str) -> dict[str, Any] | None:
        """返回 Task 详情（含 dependencies）。"""
        task = await self.get_by_id(task_id)
        if task is None:
            return None

        deps = [
            {"task_id": d.task_id, "depends_on_id": d.depends_on_id}
            for d in task.dependencies
        ]
        return {
            "id": task.id,
            "department_id": str(task.department_id),
            "project_ids": [str(p) for p in task.project_ids],
            "parent_task_id": task.parent_task_id,
            "state": task.state.value,
            "priority": task.priority,
            "title": task.title,
            "description": task.description,
            "deliverable_spec": {
                "kind": task.deliverable_spec.kind,
                "acceptance_criteria": task.deliverable_spec.acceptance_criteria,
            },
            "deliverable_kind": task.deliverable_spec.kind,
            "acceptance_criteria": task.deliverable_spec.acceptance_criteria,
            "max_retry_count": task.budget.max_retry_count,
            "max_review_rounds": task.budget.max_review_rounds,
            "declared_skills": [str(s) for s in task.declared_skills],
            "declared_memory_hints": [str(m) for m in task.declared_memory_hints],
            "retry_count": task.retry_count,
            "review_round": task.review_round,
            "runs": [],
            "dependencies": deps,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    async def find_tasks_by_state(self, states: list[str]) -> list[TaskSummary]:
        """按状态查询 Task（用于僵尸扫描等）。"""
        rows = await self._db.fetch(self.LIST_TASKS_BY_STATE, states)
        return [
            TaskSummary(
                id=r["id"],
                title="",
                state=r["state"],
                priority="",
                department_id="",
                retry_count=0,
                review_round=0,
                created_at=None,
            )
            for r in rows
        ]

    async def count_active_runs(self, member_id: UUID) -> int:
        """统计 Member 当前活跃 run 数量（用于并发守卫）。"""
        result = await self._db.fetchrow(self.COUNT_ACTIVE_RUNS, member_id)
        return result["count"] if result else 0

    # -- Row Mapping --

    @staticmethod
    def _row_to_task(
        row: Any,
        deps_rows: list[Any],
        proj_rows: list[Any],
    ) -> Task:
        ds_data = row["deliverable_spec"]
        if isinstance(ds_data, str):
            ds_data = json.loads(ds_data)
        deliverable_spec = DeliverableSpec(
            kind=ds_data.get("kind", ""),
            acceptance_criteria=ds_data.get("acceptance_criteria", []),
            output_format=ds_data.get("output_format", ""),
        )

        budget_data = row["budget"]
        if isinstance(budget_data, str):
            budget_data = json.loads(budget_data)
        budget = TaskBudget(
            max_tokens=budget_data.get("max_tokens", 0),
            max_duration_seconds=budget_data.get("max_duration_seconds", 0.0),
            max_cost_usd=Decimal(str(budget_data.get("max_cost_usd", "0"))),
            max_retry_count=budget_data.get("max_retry_count", 3),
            max_review_rounds=budget_data.get("max_review_rounds", 3),
        )

        skills = row.get("declared_skills") or []
        memory_hints = row.get("declared_memory_hints") or []
        project_ids = [r["project_id"] for r in proj_rows]

        task = Task(
            id=row["id"],
            department_id=row["department_id"],
            project_ids=project_ids,
            parent_task_id=row.get("parent_task_id"),
            state=TaskState(row["state"]),
            priority=row["priority"],
            title=row["title"],
            description=row.get("description") or "",
            deliverable_spec=deliverable_spec,
            declared_skills=skills,
            declared_memory_hints=memory_hints,
            budget=budget,
            retry_count=row["retry_count"],
            review_round=row["review_round"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

        # Reconstruct dependencies
        for dr in deps_rows:
            task.dependencies.append(
                TaskDependency(
                    task_id=dr["task_id"],
                    depends_on_id=dr["depends_on_id"],
                )
            )

        return task

    @staticmethod
    def _row_to_summary(row: Any) -> TaskSummary:
        return TaskSummary(
            id=row["id"],
            title=row["title"],
            state=row["state"],
            priority=row["priority"],
            department_id=str(row["department_id"]),
            retry_count=row["retry_count"],
            review_round=row["review_round"],
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# Context Snapshot Repository
# ---------------------------------------------------------------------------


class SqlSnapshotRepository:
    """ContextSnapshot 持久化实现 (arch.md N1: 一旦写入即只读)。"""

    _INSERT_SNAPSHOT = """
        INSERT INTO task_context_snapshot (id, task_id, run_id, content, created_at)
        VALUES ($1, $2, $3, $4::jsonb, $5)
    """

    _SELECT_SNAPSHOT = """
        SELECT id, task_id, run_id, content, created_at
        FROM task_context_snapshot
        WHERE id = $1
    """

    def __init__(self, *, db: Any) -> None:
        self._db = db

    async def save_snapshot(self, snapshot: ContextSnapshot, *, tx: Any) -> None:
        content = {
            "memories": [
                {
                    "memory_id": str(m.memory_id),
                    "title": m.title,
                    "statement": m.statement,
                    "confidence": m.confidence,
                    "score": m.score,
                    "tokens": m.tokens,
                    "has_conflict": m.has_conflict,
                }
                for m in snapshot.memories
            ],
            "skills": [
                {
                    "skill_id": str(s.skill_id),
                    "name": s.name,
                    "version": s.version,
                    "description": s.description,
                }
                for s in snapshot.skills
            ],
            "total_tokens": snapshot.total_tokens,
            "sha256": snapshot.sha256,
        }
        await tx.execute(
            self._INSERT_SNAPSHOT,
            snapshot.id,
            snapshot.task_id,
            snapshot.run_id,
            json.dumps(content),
            snapshot.sealed_at,
        )

    async def get_snapshot(self, snapshot_id: UUID) -> ContextSnapshot | None:
        row = await self._db.fetchrow(self._SELECT_SNAPSHOT, snapshot_id)
        if row is None:
            return None

        data = row["content"]
        if isinstance(data, str):
            data = json.loads(data)

        memories = [
            MemorySnippet(
                memory_id=UUID(m["memory_id"]),
                title=m["title"],
                statement=m["statement"],
                confidence=m["confidence"],
                score=m["score"],
                tokens=m["tokens"],
                has_conflict=m.get("has_conflict", False),
            )
            for m in data.get("memories", [])
        ]
        skills = [
            SkillBundle(
                skill_id=UUID(s["skill_id"]),
                name=s["name"],
                version=s["version"],
                description=s.get("description", ""),
            )
            for s in data.get("skills", [])
        ]

        return ContextSnapshot(
            id=row["id"],
            task_id=row["task_id"],
            run_id=row["run_id"],
            sealed_at=row["created_at"],
            memories=memories,
            skills=skills,
            total_tokens=data.get("total_tokens", 0),
            sha256=data.get("sha256", ""),
        )
