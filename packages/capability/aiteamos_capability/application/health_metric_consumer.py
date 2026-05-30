"""
Capability Context — Skill Health Metric Projection Consumer (arch.md §2.2.2).

消费 Execution 上下文事件，按 rolling window 更新 skill_health_metric 表，
为 Skill 熔断器提供数据支撑。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer

logger = logging.getLogger(__name__)


class SkillHealthMetricConsumer(IdempotentProjectionConsumer):
    """消费 Execution run 事件，更新 skill_health_metric 投影。

    处理事件:
    - execution.run.finished → 按成功/失败更新 skill 关联的 health metric

    使用 rolling 24h window，通过 UPSERT + 原子增量保证幂等。
    """

    consumer_id = "skill-health-metric-v1"

    _UPSERT_METRIC = """
        INSERT INTO skill_health_metric (
            id, skill_id, window_start, success_count, failure_count,
            distinct_failed_tasks, success_rate
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (id) DO UPDATE SET
            success_count = skill_health_metric.success_count + EXCLUDED.success_count,
            failure_count = skill_health_metric.failure_count + EXCLUDED.failure_count,
            distinct_failed_tasks = skill_health_metric.distinct_failed_tasks + EXCLUDED.distinct_failed_tasks,
            success_rate = CASE
                WHEN (skill_health_metric.success_count + skill_health_metric.failure_count
                      + EXCLUDED.success_count + EXCLUDED.failure_count) > 0
                THEN (skill_health_metric.success_count + EXCLUDED.success_count)::numeric
                     / (skill_health_metric.success_count + skill_health_metric.failure_count
                        + EXCLUDED.success_count + EXCLUDED.failure_count)::numeric
                ELSE 1.0
            END
    """

    # Find skill_ids associated with a task via declared_skills
    _GET_TASK_SKILLS = """
        SELECT unnest(declared_skills) AS skill_id FROM task WHERE id = $1
    """

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        if event.event_type != "execution.run.finished":
            return

        data = event.model_dump()
        task_id = str(data.get("task_id", ""))
        outcome = data.get("outcome", "success")

        if not task_id:
            return

        # Look up skills associated with this task
        rows = await self._db.fetch(self._GET_TASK_SKILLS, task_id)

        is_success = outcome == "success"
        success_inc = 1 if is_success else 0
        failure_inc = 0 if is_success else 1
        failed_task_inc = 0 if is_success else 1

        # Truncate to hour for window grouping
        now = datetime.now(timezone.utc)
        window_start = now.replace(minute=0, second=0, microsecond=0)

        for row in rows:
            skill_id = row["skill_id"]
            metric_id = uuid4()
            initial_rate = 1.0 if is_success else 0.0

            await self._db.execute(
                self._UPSERT_METRIC,
                metric_id,
                skill_id,
                window_start,
                success_inc,
                failure_inc,
                failed_task_inc,
                initial_rate,
            )

        if rows:
            logger.info(
                "SkillHealth: task %s outcome=%s, updated %d skill metrics",
                task_id,
                outcome,
                len(rows),
            )
