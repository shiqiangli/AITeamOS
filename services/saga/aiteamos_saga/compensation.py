"""
Saga 补偿链 (arch.md §3.5, 不变量 N7, 纪律 #11)。

设计背景:
  forward-only Workflow 在异常退出时造成资源泄漏。
  "每次占用伴随一个补偿项"，异常路径 unwind。

CompensationStack:
  - push(item): 正向 Activity 占用资源后压入
  - unwind(): 反向释放所有已压入资源
  - 补偿 Activity 必须幂等
  - 补偿失败进入 governance DLQ
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ResourceKind
# ---------------------------------------------------------------------------


class ResourceKind(StrEnum):
    """资源种类 (arch.md §3.5.2)。"""

    MEMBER_CONCURRENCY = "member_concurrency"
    SANDBOX = "sandbox"
    SKILL_BUNDLE = "skill_bundle"
    OUTBOX_EVENT = "outbox_event"
    EXTERNAL_API = "external_api"


# ---------------------------------------------------------------------------
# CompensationItem
# ---------------------------------------------------------------------------


@dataclass
class CompensationItem:
    """补偿项 — 记录如何释放一项已占用的资源。"""

    activity: str  # 补偿 Activity 名称
    args: dict[str, Any]  # 补偿参数
    kind: ResourceKind  # 资源种类
    correlation_id: str = ""  # 与正向 Activity 关联


# ---------------------------------------------------------------------------
# CompensationFailure
# ---------------------------------------------------------------------------


@dataclass
class CompensationFailure:
    """补偿失败记录 — 进入 governance DLQ。"""

    item: CompensationItem
    reason: str
    error: str


# ---------------------------------------------------------------------------
# Activity executor protocol
# ---------------------------------------------------------------------------


ActivityExecutor = Callable[[str, dict[str, Any]], Awaitable[None]]
"""Async function that executes a compensation activity by name with args."""


# ---------------------------------------------------------------------------
# CompensationStack (arch.md §3.5.1)
# ---------------------------------------------------------------------------


class CompensationStack:
    """Saga 补偿栈 — 强制资源净闭环。

    不变量 N7: Workflow 终态可达时补偿栈必须为空。
    含残留项即判定资源泄漏。
    """

    def __init__(
        self,
        *,
        executor: ActivityExecutor | None = None,
        on_failure: Callable[[CompensationFailure], Awaitable[None]] | None = None,
    ):
        self._stack: list[CompensationItem] = []
        self._executor = executor or self._default_executor
        self._on_failure = on_failure or self._default_on_failure
        self._failures: list[CompensationFailure] = []

    @property
    def items(self) -> list[CompensationItem]:
        return list(self._stack)

    @property
    def size(self) -> int:
        return len(self._stack)

    @property
    def is_empty(self) -> bool:
        return len(self._stack) == 0

    @property
    def failures(self) -> list[CompensationFailure]:
        return list(self._failures)

    def push(self, item: CompensationItem) -> None:
        """压入补偿项 — 正向 Activity 占用资源后必须调用。"""
        self._stack.append(item)
        logger.debug(
            "CompensationStack.push: %s (kind=%s, correlation=%s)",
            item.activity,
            item.kind,
            item.correlation_id,
        )

    async def unwind(self, reason: str) -> None:
        """反向释放所有已压入资源。

        补偿 Activity 必须幂等；失败不阻塞后续补偿，
        但进入 governance DLQ。
        """
        logger.info(
            "CompensationStack.unwind: releasing %d items (reason=%s)",
            len(self._stack),
            reason,
        )

        while self._stack:
            item = self._stack.pop()
            try:
                await self._executor(item.activity, item.args)
                logger.debug(
                    "CompensationStack: released %s (kind=%s)",
                    item.activity,
                    item.kind,
                )
            except Exception as exc:
                # 补偿失败不能阻塞后续补偿
                logger.error(
                    "CompensationStack: compensation failed for %s: %s",
                    item.activity,
                    exc,
                )
                failure = CompensationFailure(
                    item=item, reason=reason, error=str(exc)
                )
                self._failures.append(failure)
                await self._on_failure(failure)

        assert self.is_empty, "compensation stack must be empty after unwind"

    async def assert_empty(self) -> None:
        """断言补偿栈为空 — 终态不变量 N7。"""
        if not self.is_empty:
            leaked = [
                f"{item.activity}(kind={item.kind}, id={item.correlation_id})"
                for item in self._stack
            ]
            raise ResourceLeakError(
                f"Compensation stack not empty at terminal state: {leaked}"
            )

    @staticmethod
    async def _default_executor(activity: str, args: dict[str, Any]) -> None:
        """Default no-op executor for testing."""
        logger.warning(
            "CompensationStack: no executor configured, skipping %s", activity
        )

    @staticmethod
    async def _default_on_failure(failure: CompensationFailure) -> None:
        """Default failure handler — log only."""
        logger.error(
            "CompensationStack: DLQ entry — activity=%s reason=%s error=%s",
            failure.item.activity,
            failure.reason,
            failure.error,
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ResourceLeakError(Exception):
    """资源泄漏 — 补偿栈在终态不为空。"""
    pass


class CompensationActivityError(Exception):
    """补偿 Activity 执行失败。"""
    pass
