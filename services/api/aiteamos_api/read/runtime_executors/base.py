"""Runtime executor protocol and shared result helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Protocol

from ..execution_contract import ExecutionEvent, ExecutionRequest, ExecutionResult


class RuntimeExecutor(Protocol):
    id: str
    display_name: str
    capabilities: set[str]

    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        ...

    async def stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionEvent]:
        ...

    async def health(self) -> dict:
        ...


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def blocked_result(
    request: ExecutionRequest,
    *,
    executor_id: str,
    reason: str,
    detail: str = "",
) -> ExecutionResult:
    timestamp = utc_now()
    return ExecutionResult(
        request_id=request.request_id,
        executor_id=executor_id,
        status="blocked",
        report=detail or reason,
        output_ticket_id=request.ticket_id,
        trace_ref=str(request.trace_context.get("trace_ref") or ""),
        executor_session_ref=str(request.trace_context.get("executor_session_ref") or ""),
        checkpoint_ref=str(request.trace_context.get("checkpoint_ref") or ""),
        errors=[{"reason": reason, "detail": detail or reason}],
        started_at=timestamp,
        finished_at=timestamp,
    )
