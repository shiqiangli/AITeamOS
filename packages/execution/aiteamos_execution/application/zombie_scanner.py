"""
Execution Context — Zombie Task Scanner (plan.md §4.6.2, arch.md §3.3.2)。

定期扫描 state=running/suspended 但 Temporal 无活跃 Workflow 的 Task，
将其转为 Failed 状态。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZombieScanResult:
    """扫描结果。"""

    scanned_count: int = 0
    zombie_count: int = 0
    failed_task_ids: list[str] = field(default_factory=list)
    scan_started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scan_completed_at: datetime | None = None


@dataclass(frozen=True)
class ZombieTaskInfo:
    """僵尸 Task 信息。"""

    task_id: str = ""
    current_state: str = ""
    run_id: str | None = None
    last_updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class TaskStoreProtocol(Protocol):
    """Task 仓储协议 — 查询可疑僵尸 Task。"""

    async def find_active_tasks(self) -> list[dict[str, Any]]:
        """查找 state in (running, suspended) 的 Task 列表。

        返回 dict 包含: task_id, state, run_id, updated_at
        """
        ...

    async def fail_task(self, task_id: str, *, reason: str) -> None:
        """将 Task 标记为 Failed。"""
        ...


class WorkflowCheckerProtocol(Protocol):
    """Temporal Workflow 活跃性检查协议。"""

    async def is_workflow_active(self, run_id: str) -> bool:
        """检查给定 run_id 的 Temporal Workflow 是否仍在运行。"""
        ...


# ---------------------------------------------------------------------------
# ZombieTaskScanner (plan.md §4.6.2)
# ---------------------------------------------------------------------------


class ZombieTaskScanner:
    """僵尸 Task 扫描器。

    每 5 分钟扫描一次，检测 state=running/suspended 但 Temporal
    无活跃 Workflow 的 Task，将其转为 Failed。
    """

    DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes
    DEFAULT_GRACE_PERIOD_SECONDS = 600  # 10 minutes grace for recently updated tasks

    def __init__(
        self,
        *,
        task_store: TaskStoreProtocol,
        workflow_checker: WorkflowCheckerProtocol,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        grace_period_seconds: int = DEFAULT_GRACE_PERIOD_SECONDS,
    ):
        self._store = task_store
        self._checker = workflow_checker
        self._interval = interval_seconds
        self._grace_period = grace_period_seconds
        self._stopped = False
        self._scan_count = 0

    @property
    def scan_count(self) -> int:
        return self._scan_count

    async def run(self) -> None:
        """主扫描循环。"""
        logger.info(
            "ZombieTaskScanner: started (interval=%ds, grace=%ds)",
            self._interval,
            self._grace_period,
        )
        while not self._stopped:
            result = await self.scan_once()
            if result.zombie_count > 0:
                logger.warning(
                    "ZombieTaskScanner: found %d zombies, failed %d tasks",
                    result.zombie_count,
                    len(result.failed_task_ids),
                )
            await _sleep(self._interval)

    async def scan_once(
        self,
        *,
        now: datetime | None = None,
    ) -> ZombieScanResult:
        """执行一次扫描。"""
        current_time = now or datetime.now(timezone.utc)
        self._scan_count += 1

        active_tasks = await self._store.find_active_tasks()
        zombie_ids: list[str] = []
        scanned = 0

        for task in active_tasks:
            scanned += 1
            task_id = task["task_id"]
            state = task.get("state", "")
            run_id = task.get("run_id")
            updated_at = task.get("updated_at")

            # Grace period: skip recently updated tasks
            if updated_at and isinstance(updated_at, datetime):
                elapsed = (current_time - updated_at).total_seconds()
                if elapsed < self._grace_period:
                    continue

            # No run_id means no workflow to check
            if not run_id:
                zombie_ids.append(task_id)
                continue

            # Check if Temporal workflow is still active
            try:
                is_active = await self._checker.is_workflow_active(str(run_id))
                if not is_active:
                    zombie_ids.append(task_id)
            except Exception:
                logger.exception(
                    "ZombieTaskScanner: failed to check workflow for task %s (run=%s)",
                    task_id,
                    run_id,
                )

        # Fail zombie tasks
        failed_ids: list[str] = []
        for task_id in zombie_ids:
            try:
                await self._store.fail_task(
                    task_id,
                    reason="zombie_detected: no active Temporal workflow",
                )
                failed_ids.append(task_id)
                logger.info("ZombieTaskScanner: failed zombie task %s", task_id)
            except Exception:
                logger.exception("ZombieTaskScanner: failed to mark task %s as failed", task_id)

        return ZombieScanResult(
            scanned_count=scanned,
            zombie_count=len(zombie_ids),
            failed_task_ids=failed_ids,
            scan_started_at=current_time,
            scan_completed_at=datetime.now(timezone.utc),
        )

    def stop(self) -> None:
        """Signal the scanner to stop."""
        self._stopped = True


async def _sleep(seconds: int) -> None:
    """Async sleep helper."""
    import asyncio
    await asyncio.sleep(seconds)
