"""
Execution Context — Task Execution Projection Consumer (arch.md §2.2.4).

消费 Task 生命周期事件，同步状态到 task 读侧表，
驱动依赖链推进和熔断标记。
"""

from __future__ import annotations

import logging
from typing import Any

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer

logger = logging.getLogger(__name__)


class TaskExecutionConsumer(IdempotentProjectionConsumer):
    """消费 Execution 上下文事件，维护 task / job 读侧投影。

    处理事件:
    - execution.task.created          → INSERT task row
    - execution.task.state_changed    → UPDATE task.state
    - execution.run.started           → INSERT job row
    - execution.run.finished          → UPDATE job.state + cost
    - execution.task.hard_circuit_triggered → UPDATE task.state = 'failed'
    - execution.task.dependency_resolved  → UPDATE task.state = 'ready'
    - execution.task.dependency_blocked   → UPDATE task.state = 'blocked'
    """

    consumer_id = "task-execution-v1"

    _UPSERT_TASK = """
        INSERT INTO task (id, department_id, title, priority, state, created_at)
        VALUES ($1, $2, $3, $4, $5, now())
        ON CONFLICT (id) DO UPDATE SET
            state = EXCLUDED.state
    """

    _UPDATE_TASK_STATE = """
        UPDATE task SET state = $2, updated_at = now() WHERE id = $1
    """

    _UPSERT_JOB = """
        INSERT INTO job (job_id, task_id, member_id, state, phase, started_at)
        VALUES ($1, $2, $3, 'running', 'calling', now())
        ON CONFLICT (job_id) DO UPDATE SET
            state = EXCLUDED.state
    """

    _FINISH_JOB = """
        UPDATE job SET state = $2, phase = $2, finished_at = now() WHERE job_id = $1
    """

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        data = event.model_dump()
        et = event.event_type

        if et == "execution.task.created":
            await self._db.execute(
                self._UPSERT_TASK,
                str(data["task_id"]),
                data["department_id"],
                data.get("title", ""),
                data.get("priority", "P2"),
                "draft",
            )

        elif et == "execution.task.state_changed":
            await self._db.execute(
                self._UPDATE_TASK_STATE,
                str(data["task_id"]),
                data["to_state"],
            )

        elif et == "execution.run.started":
            await self._db.execute(
                self._UPSERT_JOB,
                data["run_id"],
                str(data["task_id"]),
                data["member_id"],
            )

        elif et == "execution.run.finished":
            outcome = data.get("outcome", "success")
            run_state = "completed" if outcome == "success" else outcome
            await self._db.execute(
                self._FINISH_JOB,
                data["run_id"],
                run_state,
            )

        elif et == "execution.task.hard_circuit_triggered":
            await self._db.execute(
                self._UPDATE_TASK_STATE,
                str(data["task_id"]),
                "failed",
            )

        elif et == "execution.task.dependency_resolved":
            await self._db.execute(
                self._UPDATE_TASK_STATE,
                str(data["task_id"]),
                "ready",
            )

        elif et == "execution.task.dependency_blocked":
            await self._db.execute(
                self._UPDATE_TASK_STATE,
                str(data["task_id"]),
                "blocked",
            )

        else:
            logger.debug("TaskExecutionConsumer: ignoring %s", et)
