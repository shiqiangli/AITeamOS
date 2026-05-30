"""
Shared Kernel — Saga 补偿栈原语 (arch.md §3.5, 纪律 #11)。

任何分布式编排 Workflow 必须显式声明 Compensation Activity 栈；
正向路径每注册一项资源占用，异常时必须由 unwind() 反向释放。
补偿失败进入 DLQ（compensation_failure_dlq 表）。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Awaitable

from .types import ResourceKind

logger = logging.getLogger(__name__)


@dataclass
class CompensationItem:
    """Single item in the compensation stack.

    Attributes:
        activity: Name of the compensation activity to execute.
        args: Arguments for the compensation activity (JSON-serializable).
        kind: Resource category for audit and DLQ routing.
        correlation_id: Links to the forward activity output.
    """

    activity: str
    args: dict[str, Any]
    kind: ResourceKind
    correlation_id: str


# Type alias for async compensation executor
CompensationExecutor = Callable[[CompensationItem], Awaitable[None]]


class CompensationStack:
    """LIFO stack for saga compensation items.

    Push items as resources are acquired during the forward path.
    On any exit (success/failure/cancel), call :meth:`unwind` to
    release all resources in reverse order.

    Compensation activities MUST be idempotent (arch.md §3.5.2).
    Failures are routed to the DLQ handler if provided.

    Usage::

        stack = CompensationStack(executor=my_executor, dlq_handler=my_dlq)
        stack.push(CompensationItem(
            activity='release_member_concurrency',
            args={'task_id': task_id},
            kind=ResourceKind.MEMBER_CONCURRENCY,
            correlation_id=task_id,
        ))
        # On exit:
        await stack.unwind(reason='workflow_completed')
    """

    def __init__(
        self,
        *,
        executor: CompensationExecutor | None = None,
        dlq_handler: CompensationExecutor | None = None,
    ):
        self._items: list[CompensationItem] = []
        self._executor = executor
        self._dlq_handler = dlq_handler

    @property
    def items(self) -> list[CompensationItem]:
        """Read-only view of the current stack."""
        return list(self._items)

    @property
    def is_empty(self) -> bool:
        return len(self._items) == 0

    def __len__(self) -> int:
        return len(self._items)

    def push(self, item: CompensationItem) -> None:
        """Push a compensation item onto the stack."""
        self._items.append(item)
        logger.debug(
            "CompensationStack: push %s (kind=%s, correlation=%s)",
            item.activity,
            item.kind,
            item.correlation_id,
        )

    async def unwind(self, *, reason: str) -> None:
        """Unwind the stack in LIFO order, executing each compensation.

        Failed compensations are sent to the DLQ handler if available;
        otherwise they are logged as critical errors. Processing continues
        even if individual compensations fail.

        Args:
            reason: Human-readable reason for the unwind (for audit).
        """
        if not self._items:
            logger.debug("CompensationStack: empty, nothing to unwind")
            return

        logger.info(
            "CompensationStack: unwinding %d items (reason=%s)",
            len(self._items),
            reason,
        )

        failed_items: list[tuple[CompensationItem, Exception]] = []

        # Reverse order — LIFO
        for item in reversed(self._items):
            try:
                if self._executor:
                    await self._executor(item)
                logger.debug(
                    "CompensationStack: compensated %s (correlation=%s)",
                    item.activity,
                    item.correlation_id,
                )
            except Exception as exc:
                logger.error(
                    "CompensationStack: FAILED %s (correlation=%s): %s",
                    item.activity,
                    item.correlation_id,
                    exc,
                )
                failed_items.append((item, exc))

        # Clear the stack after unwind attempt
        self._items.clear()

        # Route failures to DLQ
        for item, exc in failed_items:
            if self._dlq_handler:
                try:
                    await self._dlq_handler(item)
                except Exception:
                    logger.critical(
                        "CompensationStack: DLQ handler FAILED for %s: %s",
                        item.activity,
                        exc,
                    )
            else:
                logger.critical(
                    "CompensationStack: no DLQ handler, LOST compensation: %s",
                    asdict(item),
                )

        if failed_items:
            logger.warning(
                "CompensationStack: %d/%d compensations failed and routed to DLQ",
                len(failed_items),
                len(failed_items) + (0),  # total attempted
            )

    def to_dicts(self) -> list[dict[str, Any]]:
        """Serialize the stack for persistence (e.g., workflow history)."""
        return [asdict(item) for item in self._items]

    @classmethod
    def from_dicts(cls, data: list[dict[str, Any]], **kwargs) -> CompensationStack:
        """Deserialize the stack from persisted data."""
        stack = cls(**kwargs)
        for d in data:
            d["kind"] = ResourceKind(d["kind"])
            stack.push(CompensationItem(**d))
        return stack
