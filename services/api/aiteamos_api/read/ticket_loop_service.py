"""Ticket-native autonomous loop primitives."""

from __future__ import annotations

import asyncio
import os
import time
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .chat_action_plan import ChatActionPlan
from .execution_context_service import ExecutionContextService
from .execution_contract import ExecutionRequest, ExecutionResult, TicketBinding
from .execution_dispatch_service import ExecutionDispatchService
from .execution_result_ingestion_service import ExecutionResultIngestionService
from .execution_session_store import record_execution_session_control
from .employee_profile_service import load_employee_profiles
from .ticket_service import (
    TicketHandoffRequest,
    TicketReportRequest,
    TicketStateTransitionRequest,
    add_ticket_report,
    get_ticket,
    record_ticket_handoff,
    ticket_assets_for_ticket,
    transition_ticket_state,
)


DEFAULT_STOP_STATUSES = [
    "validated",
    "completed",
    "done",
    "closed",
    "blocked",
    "failed",
    "waiting_approval",
    "waiting_changes",
    "waiting_evidence",
    "waiting_validation",
]
DEFAULT_ALLOWED_CAPABILITIES = ["tickets:read", "ticket:report:write", "assets:read", "memory:read"]
DEFAULT_APPROVAL_REQUIREMENTS = ["repo:write"]
APPROVAL_REVIEW_TICKET_STATUSES = {
    "approved": "ready_to_resume",
    "rejected": "blocked",
    "changes_requested": "waiting_changes",
    "evidence_requested": "waiting_evidence",
}
APPROVAL_REQUEST_TICKET_STATUS = "waiting_approval"
TERMINAL_TICKET_STATUSES = {"validated", "completed", "done", "closed", "cancelled"}
QUEUE_STALE_RUNNING_SECONDS = 15 * 60
QUEUE_FAILURE_RETROSPECTIVE_MIN_FAILED_ITEMS = 2


class TicketLoopSlaPolicy(BaseModel):
    response_due_seconds: int | None = Field(default=None, ge=60, le=30 * 24 * 60 * 60)
    review_due_seconds: int | None = Field(default=None, ge=60, le=30 * 24 * 60 * 60)
    escalation_employee_id: str = ""
    escalation_role: str = ""


class TicketLoopRecurrencePolicy(BaseModel):
    enabled: bool = False
    interval_seconds: int | None = Field(default=None, ge=60, le=30 * 24 * 60 * 60)
    max_occurrences: int | None = Field(default=None, ge=1, le=365)
    next_run_at: str = ""


class TicketLoopCloseoutPolicy(BaseModel):
    auto_propose_assets: bool = True
    auto_settle_assets: bool = False
    auto_approve_candidates: bool = False
    project_graphiti: bool = False
    project_relationships: bool = False
    require_validation_evidence: bool = True
    asset_types: list[str] = Field(default_factory=lambda: ["ticket_closeout", "solution", "validation_result"])


class TicketLoopPolicy(BaseModel):
    ticket_id: str
    max_steps: int = Field(default=3, ge=1, le=5)
    max_runtime_seconds: int = Field(default=60, ge=1, le=300)
    stop_statuses: list[str] = Field(default_factory=lambda: list(DEFAULT_STOP_STATUSES))
    allowed_capabilities: list[str] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_CAPABILITIES))
    approval_requirements: list[str] = Field(default_factory=lambda: list(DEFAULT_APPROVAL_REQUIREMENTS))
    validation_required: bool = False
    sla: TicketLoopSlaPolicy = Field(default_factory=TicketLoopSlaPolicy)
    recurrence: TicketLoopRecurrencePolicy = Field(default_factory=TicketLoopRecurrencePolicy)
    closeout: TicketLoopCloseoutPolicy = Field(default_factory=TicketLoopCloseoutPolicy)
    source: str = "default"
    saved_path: str = ""
    updated_by_employee_id: str = ""
    updated_at: str = ""


class TicketLoopPolicyUpdateRequest(BaseModel):
    max_steps: int | None = Field(default=None, ge=1, le=5)
    max_runtime_seconds: int | None = Field(default=None, ge=1, le=300)
    stop_statuses: list[str] | None = None
    allowed_capabilities: list[str] | None = None
    approval_requirements: list[str] | None = None
    validation_required: bool | None = None
    sla: TicketLoopSlaPolicy | None = None
    recurrence: TicketLoopRecurrencePolicy | None = None
    closeout: TicketLoopCloseoutPolicy | None = None
    actor_employee_id: str = "clara"
    actor_role: str = "AI Team OS Manager"
    reason: str = "Ticket loop policy updated."


class TicketLoopControlRequest(BaseModel):
    action: Literal["stop", "pause", "continue", "cancel"] = "stop"
    actor_employee_id: str = "clara"
    actor_role: str = "AI Team OS Manager"
    reason: str = "Ticket loop control requested."
    session_key: str = ""


class TicketLoopControlState(BaseModel):
    control_id: str
    ticket_id: str
    action: str
    status: str
    active: bool
    actor_employee_id: str
    actor_role: str
    reason: str
    session_key: str = ""
    updated_session_count: int = 0
    updated_at: str
    saved_path: str = ""


class TicketLoopControlResponse(BaseModel):
    ticket_id: str
    state: TicketLoopControlState
    report_id: str = ""
    updated_sessions: list[dict[str, Any]] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class TicketLoopApprovalSync(BaseModel):
    ticket_id: str
    approval_id: str
    approval_status: str
    ticket_status: str = ""
    previous_ticket_status: str = ""
    changed: bool = False
    reason: str = ""
    blocker_report_id: str = ""


class TicketLoopTimelineRef(BaseModel):
    kind: str
    ref: str
    target_route: str = ""


class TicketLoopTimelineItem(BaseModel):
    timeline_id: str
    ticket_id: str
    kind: str
    status: str = ""
    title: str
    detail: str = ""
    at: str = ""
    actor_employee_id: str = ""
    actor_role: str = ""
    source_kind: str = ""
    source_ref: str = ""
    target_route: str = ""
    refs: list[TicketLoopTimelineRef] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class TicketLoopRetryRequirement(BaseModel):
    id: str
    label: str
    satisfied: bool
    detail: str = ""
    target_route: str = ""


class TicketLoopApprovalResumeState(BaseModel):
    approval_id: str
    executor_id: str
    status: str
    required_capability: str = ""
    ready_to_run: bool = False
    needs_review: bool = False
    blocked: bool = False
    reviewed_at: str = ""
    last_run_request_id: str = ""
    last_run_status: str = ""
    last_ingestion_blocker: str = ""
    attempt_count: int = 0
    target_route: str = ""
    detail: str = ""


class TicketLoopQueueReliability(BaseModel):
    ticket_id: str
    status: str = "idle"
    detail: str = ""
    queued_count: int = 0
    duplicate_queued_count: int = 0
    running_count: int = 0
    stale_running_count: int = 0
    stale_running_after_seconds: int = QUEUE_STALE_RUNNING_SECONDS
    completed_count: int = 0
    failed_count: int = 0
    active_count: int = 0
    total_count: int = 0
    latest_activity_at: str = ""
    worker_status: str = ""
    worker_running: bool = False
    worker_last_error: str = ""


class TicketLoopPolicyStatus(BaseModel):
    ticket_id: str
    source: str = "default"
    validation_required: bool = False
    sla: TicketLoopSlaPolicy = Field(default_factory=TicketLoopSlaPolicy)
    recurrence: TicketLoopRecurrencePolicy = Field(default_factory=TicketLoopRecurrencePolicy)
    closeout: TicketLoopCloseoutPolicy = Field(default_factory=TicketLoopCloseoutPolicy)
    configured: dict[str, bool] = Field(default_factory=dict)
    saved_path: str = ""


class TicketLoopTimelineSummary(BaseModel):
    ticket_id: str
    status: str
    waiting_reason: str = ""
    next_action: str = ""
    can_run: bool = False
    can_resume: bool = False
    can_retry: bool = False
    latest_at: str = ""
    counts: dict[str, int] = Field(default_factory=dict)
    provider_blockers: list[dict[str, Any]] = Field(default_factory=list)
    retry_requirements: list[TicketLoopRetryRequirement] = Field(default_factory=list)
    approval_resume: list[TicketLoopApprovalResumeState] = Field(default_factory=list)
    queue_reliability: TicketLoopQueueReliability | None = None
    policy: TicketLoopPolicyStatus | None = None


class TicketLoopTimelineResponse(BaseModel):
    ticket_id: str
    summary: TicketLoopTimelineSummary
    items: list[TicketLoopTimelineItem] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)



class TicketLoopStepRequest(BaseModel):
    employee_id: str = ""
    message: str = ""
    selected_executor: str = "universal_employee_agent"
    selected_ai_engine: str = "universal_employee_agent"
    max_steps: int = Field(default=1, ge=1, le=1)
    stop_condition: str = "single_step"
    budget: dict[str, Any] = Field(default_factory=lambda: {"max_steps": 1})
    runtime_config: dict[str, Any] = Field(default_factory=dict)
    ingest_result: bool = True


class TicketLoopRunRequest(TicketLoopStepRequest):
    max_steps: int = Field(default=3, ge=1, le=5)
    max_runtime_seconds: int = Field(default=60, ge=1, le=300)
    stop_statuses: list[str] = Field(default_factory=lambda: list(DEFAULT_STOP_STATUSES))


class TicketLoopStepResponse(BaseModel):
    ticket_id: str
    status: str
    stop_reason: str
    request: dict[str, Any]
    result: dict[str, Any]
    ingested: bool = False
    ingestion_blocker: str = ""
    loop_state: dict[str, Any] = Field(default_factory=dict)


class TicketLoopRunResponse(BaseModel):
    ticket_id: str
    status: str
    stop_reason: str
    steps: list[TicketLoopStepResponse] = Field(default_factory=list)
    loop_state: dict[str, Any] = Field(default_factory=dict)


class TicketLoopRunRecord(BaseModel):
    run_id: str
    ticket_id: str
    status: str
    stop_reason: str = ""
    active: bool = False
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    step_count: int = 0
    policy: dict[str, Any] = Field(default_factory=dict)
    control: dict[str, Any] = Field(default_factory=dict)
    queued_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    updated_at: str = ""
    saved_path: str = ""


class TicketLoopEnqueueRequest(TicketLoopRunRequest):
    actor_employee_id: str = "clara"
    actor_role: str = "AI Team OS Manager"
    reason: str = "Ticket loop queued."
    priority: int = Field(default=100, ge=0, le=1000)


class TicketLoopQueueItem(BaseModel):
    queue_id: str
    run_id: str
    ticket_id: str
    status: str = "queued"
    priority: int = 100
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    actor_employee_id: str = ""
    actor_role: str = ""
    reason: str = ""
    report_id: str = ""
    enqueued_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    updated_at: str = ""
    saved_path: str = ""


class TicketLoopResumeRequest(BaseModel):
    action: Literal["resume", "retry_after_changes", "retry_after_evidence"] = "resume"
    employee_id: str = ""
    selected_executor: str = "universal_employee_agent"
    selected_ai_engine: str = "universal_employee_agent"
    message: str = ""
    max_steps: int = Field(default=2, ge=1, le=5)
    max_runtime_seconds: int = Field(default=60, ge=1, le=300)
    priority: int = Field(default=50, ge=0, le=1000)
    actor_employee_id: str = "clara"
    actor_role: str = "AI Team OS Manager"
    reason: str = "Ticket loop resume requested."
    runtime_config: dict[str, Any] = Field(default_factory=dict)
    ingest_result: bool = True


class TicketLoopResumeResponse(BaseModel):
    ticket_id: str
    status: str
    previous_status: str
    detail: str
    queue_item: TicketLoopQueueItem
    saved_paths: dict[str, str] = Field(default_factory=dict)


class TicketLoopQueuePumpRequest(BaseModel):
    max_items: int = Field(default=1, ge=1, le=5)


class TicketLoopPolicyAction(BaseModel):
    kind: str
    ticket_id: str
    status: str
    detail: str = ""
    candidate_ids: list[str] = Field(default_factory=list)
    queue_ids: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    handoff_refs: list[dict[str, str]] = Field(default_factory=list)
    report_id: str = ""


class TicketLoopQueuePumpResponse(BaseModel):
    status: str
    processed: list[TicketLoopQueueItem] = Field(default_factory=list)
    policy_actions: list[TicketLoopPolicyAction] = Field(default_factory=list)
    remaining_queued: int = 0
    saved_paths: dict[str, str] = Field(default_factory=dict)


class TicketLoopQueueStatus(BaseModel):
    status: str
    queued_count: int = 0
    running_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    active_count: int = 0
    total_count: int = 0
    oldest_queued_at: str = ""
    latest_activity_at: str = ""
    next_queue_id: str = ""
    next_ticket_id: str = ""
    next_run_id: str = ""
    saved_paths: dict[str, str] = Field(default_factory=dict)


class TicketLoopQueueWorkerControlRequest(BaseModel):
    interval_seconds: float = Field(default=5.0, ge=0.1, le=3600)
    max_items: int = Field(default=1, ge=1, le=5)
    reason: str = "Ticket loop queue worker control requested."


class TicketLoopQueueWorkerStatus(BaseModel):
    worker_id: str = "ticket-loop-queue-worker"
    status: str = "stopped"
    running: bool = False
    interval_seconds: float = 5.0
    max_items: int = 1
    started_at: str = ""
    stopped_at: str = ""
    last_tick_at: str = ""
    last_tick_status: str = ""
    last_error: str = ""
    total_ticks: int = 0
    total_processed: int = 0
    total_policy_actions: int = 0
    recent_policy_actions: list[TicketLoopPolicyAction] = Field(default_factory=list)
    last_control_reason: str = ""
    saved_path: str = ""


class TicketLoopQueueWorkerTickResponse(BaseModel):
    status: TicketLoopQueueWorkerStatus
    pump: TicketLoopQueuePumpResponse


class TicketLoopQueueWorker:
    """Async worker that daemonizes the existing governed queue pump."""

    def __init__(
        self,
        *,
        workspace_dir: Path | None = None,
        interval_seconds: float = 5.0,
        max_items: int = 1,
        service: TicketAutonomousLoopService | None = None,
    ) -> None:
        self.workspace_dir = (workspace_dir or _workspace_dir()).resolve()
        self.interval_seconds = interval_seconds
        self.max_items = max_items
        self.service = service or TicketAutonomousLoopService(workspace_dir=self.workspace_dir)
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._lock = asyncio.Lock()
        self._state = _load_worker_state(_worker_path(self.workspace_dir)) or TicketLoopQueueWorkerStatus(
            interval_seconds=interval_seconds,
            max_items=max_items,
            saved_path=_relative(_worker_path(self.workspace_dir)),
        )

    def status(self) -> TicketLoopQueueWorkerStatus:
        running = self._task is not None and not self._task.done()
        status = "running" if running else self._state.status
        if status == "running" and not running:
            status = "stopped"
        return self._state.model_copy(
            update={
                "status": status,
                "running": running,
                "interval_seconds": self.interval_seconds,
                "max_items": self.max_items,
                "saved_path": _relative(_worker_path(self.workspace_dir)),
            }
        )

    async def start(self, request: TicketLoopQueueWorkerControlRequest | None = None) -> TicketLoopQueueWorkerStatus:
        control = request or TicketLoopQueueWorkerControlRequest()
        self.interval_seconds = control.interval_seconds
        self.max_items = control.max_items
        if self._task is not None and not self._task.done():
            return self._persist(
                status="running",
                running=True,
                interval_seconds=self.interval_seconds,
                max_items=self.max_items,
                last_control_reason=control.reason,
            )
        now = datetime.now(UTC).isoformat()
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name=f"ticket-loop-queue-worker:{self.workspace_dir}")
        return self._persist(
            status="running",
            running=True,
            interval_seconds=self.interval_seconds,
            max_items=self.max_items,
            started_at=now,
            stopped_at="",
            last_error="",
            last_control_reason=control.reason,
        )

    async def stop(self, reason: str = "Ticket loop queue worker stopped.") -> TicketLoopQueueWorkerStatus:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None and not self._task.done():
            await self._task
        now = datetime.now(UTC).isoformat()
        return self._persist(
            status="stopped",
            running=False,
            stopped_at=now,
            last_control_reason=reason,
        )

    async def tick(self, request: TicketLoopQueueWorkerControlRequest | None = None) -> TicketLoopQueueWorkerTickResponse:
        control = request or TicketLoopQueueWorkerControlRequest(
            interval_seconds=self.interval_seconds,
            max_items=self.max_items,
            reason="Ticket loop queue worker tick.",
        )
        async with self._lock:
            self.interval_seconds = control.interval_seconds
            self.max_items = control.max_items
            try:
                pump = await pump_ticket_loop_queue(
                    TicketLoopQueuePumpRequest(max_items=control.max_items),
                    workspace_dir=self.workspace_dir,
                    service=self.service,
                )
                now = datetime.now(UTC).isoformat()
                running = self._task is not None and not self._task.done()
                status = self._persist(
                    status="running" if running else pump.status,
                    running=running,
                    interval_seconds=self.interval_seconds,
                    max_items=self.max_items,
                    last_tick_at=now,
                    last_tick_status=pump.status,
                    last_error="",
                    total_ticks=self._state.total_ticks + 1,
                    total_processed=self._state.total_processed + len(pump.processed),
                    total_policy_actions=self._state.total_policy_actions + len(pump.policy_actions),
                    recent_policy_actions=[*self._state.recent_policy_actions, *pump.policy_actions][-20:],
                    last_control_reason=control.reason,
                )
                return TicketLoopQueueWorkerTickResponse(status=status, pump=pump)
            except Exception as exc:
                now = datetime.now(UTC).isoformat()
                status = self._persist(
                    status="error",
                    running=self._task is not None and not self._task.done(),
                    last_tick_at=now,
                    last_tick_status="failed",
                    last_error=str(exc),
                    total_ticks=self._state.total_ticks + 1,
                    last_control_reason=control.reason,
                )
                raise RuntimeError(str(exc)) from exc

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            await self.tick(
                TicketLoopQueueWorkerControlRequest(
                    interval_seconds=self.interval_seconds,
                    max_items=self.max_items,
                    reason="Ticket loop queue worker daemon tick.",
                )
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass

    def _persist(self, **updates: Any) -> TicketLoopQueueWorkerStatus:
        path = _worker_path(self.workspace_dir)
        self._state = self._state.model_copy(update={**updates, "saved_path": _relative(path)})
        _write_worker_state(path, self._state)
        return self._state


class TicketAutonomousLoopService:
    def __init__(
        self,
        *,
        workspace_dir: Path | None = None,
        dispatch_service: ExecutionDispatchService | None = None,
        ingestion_service: ExecutionResultIngestionService | None = None,
        context_service: ExecutionContextService | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir or _workspace_dir()
        self.dispatch_service = dispatch_service or ExecutionDispatchService()
        self.ingestion_service = ingestion_service or ExecutionResultIngestionService(workspace_dir=self.workspace_dir)
        self.context_service = context_service or ExecutionContextService()

    async def run_loop(self, ticket_id: str, run_request: TicketLoopRunRequest) -> TicketLoopRunResponse:
        start = time.monotonic()
        policy = ticket_loop_policy(ticket_id, workspace_dir=self.workspace_dir)
        now = datetime.now(UTC).isoformat()
        run_id = str(run_request.runtime_config.get("loop_run_id") or f"ticket-loop-run-{ticket_id}-{uuid4().hex[:8]}")
        max_steps = min(run_request.max_steps, policy.max_steps)
        max_runtime_seconds = min(run_request.max_runtime_seconds, policy.max_runtime_seconds)
        normalized_stop_statuses = {
            status.strip().lower()
            for status in [*policy.stop_statuses, *run_request.stop_statuses]
            if status.strip()
        }
        steps: list[TicketLoopStepResponse] = []
        stop_reason = "max_steps_reached"
        status = "skipped"
        control_state = active_ticket_loop_control(ticket_id, workspace_dir=self.workspace_dir)
        _upsert_loop_run_record(
            self.workspace_dir,
            TicketLoopRunRecord(
                run_id=run_id,
                ticket_id=ticket_id,
                status="running",
                active=True,
                request=run_request.model_dump(mode="json"),
                policy=policy.model_dump(mode="json"),
                queued_at=now,
                started_at=now,
                updated_at=now,
                saved_path=_relative(_run_path(self.workspace_dir)),
            ),
        )

        for index in range(max_steps):
            if time.monotonic() - start > max_runtime_seconds:
                stop_reason = "runtime_budget_exhausted"
                break

            ticket = get_ticket(ticket_id)
            if ticket is None:
                raise KeyError(ticket_id)
            control_state = active_ticket_loop_control(ticket.id, workspace_dir=self.workspace_dir)
            if control_state is not None:
                status = control_state.status
                stop_reason = f"control:{control_state.action}"
                break
            ticket_status = str(ticket.status or "").strip().lower()
            if ticket_status in normalized_stop_statuses:
                status = ticket.status
                stop_reason = f"ticket_status:{ticket_status}"
                break

            step_response = await self.run_step(
                ticket.id,
                TicketLoopStepRequest(
                    employee_id=run_request.employee_id,
                    message=run_request.message,
                    selected_executor=run_request.selected_executor,
                    selected_ai_engine=run_request.selected_ai_engine,
                    max_steps=1,
                    stop_condition=run_request.stop_condition,
                    budget={**run_request.budget, "max_steps": 1, "loop_step": index + 1},
                    runtime_config={
                        **run_request.runtime_config,
                        "loop_step": index + 1,
                        "loop_thread_id": f"ticket-loop-{ticket.id}-step-{index + 1}",
                    },
                    ingest_result=run_request.ingest_result,
                ),
            )
            steps.append(step_response)
            status = step_response.status
            if step_response.stop_reason in {"approval_required", "blocked_or_failed"}:
                stop_reason = step_response.stop_reason
                break

            updated = get_ticket(ticket.id)
            updated_status = str(getattr(updated, "status", "") or "").strip().lower()
            control_state = active_ticket_loop_control(ticket.id, workspace_dir=self.workspace_dir)
            if control_state is not None:
                status = control_state.status
                stop_reason = f"control:{control_state.action}"
                break
            if updated_status in normalized_stop_statuses:
                stop_reason = f"ticket_status:{updated_status}"
                status = getattr(updated, "status", status)
                break
        else:
            stop_reason = "max_steps_reached"

        response = TicketLoopRunResponse(
            ticket_id=ticket_id,
            status=status,
            stop_reason=stop_reason,
            steps=steps,
            loop_state={
                "loop_kind": "ticket_native_loop",
                "run_id": run_id,
                "step_count": len(steps),
                "max_steps": max_steps,
                "requested_max_steps": run_request.max_steps,
                "max_runtime_seconds": max_runtime_seconds,
                "requested_max_runtime_seconds": run_request.max_runtime_seconds,
                "stop_statuses": sorted(normalized_stop_statuses),
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "policy": policy.model_dump(mode="json"),
                "control": control_state.model_dump(mode="json") if control_state is not None else {},
            },
        )
        finished_at = datetime.now(UTC).isoformat()
        _upsert_loop_run_record(
            self.workspace_dir,
            TicketLoopRunRecord(
                run_id=run_id,
                ticket_id=ticket_id,
                status=response.status,
                stop_reason=response.stop_reason,
                active=False,
                request=run_request.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
                step_count=len(response.steps),
                policy=policy.model_dump(mode="json"),
                control=response.loop_state.get("control") if isinstance(response.loop_state.get("control"), dict) else {},
                queued_at=now,
                started_at=now,
                finished_at=finished_at,
                updated_at=finished_at,
                saved_path=_relative(_run_path(self.workspace_dir)),
            ),
        )
        return response

    async def run_step(self, ticket_id: str, step_request: TicketLoopStepRequest) -> TicketLoopStepResponse:
        ticket = get_ticket(ticket_id)
        if ticket is None:
            raise KeyError(ticket_id)
        policy = ticket_loop_policy(ticket.id, workspace_dir=self.workspace_dir)
        profiles = _employee_profiles()
        employee_id = step_request.employee_id.strip() or ticket.assigned_employee_id or "clara"
        employee = _select_employee_profile(profiles, employee_id)
        task_message = step_request.message.strip() or self._default_message(ticket)
        selected_executor = step_request.selected_executor.strip() or "universal_employee_agent"
        selected_ai_engine = step_request.selected_ai_engine.strip() or selected_executor
        loop_step = _loop_step(step_request)
        ticket_status_before = str(ticket.status or "")
        validation_gate_before = self._validation_gate(ticket)
        request_id = f"ticket-loop-{ticket.id}-{uuid4().hex[:8]}"
        trace_ref = f".aiteamos/traces/{request_id}.jsonl"
        thread_id = str(step_request.runtime_config.get("loop_thread_id") or f"ticket-loop-{ticket.id}")
        context = self.context_service.build(
            message=task_message,
            employee=employee,
            employee_profiles=profiles,
            recent_messages=[],
            ticket_keys=[ticket.id],
            memory_refs=[],
            selected_ai_engine=selected_ai_engine,
        )
        execution_request = ExecutionRequest(
            request_id=request_id,
            workspace_id=str(_workspace_root()),
            employee_id=employee_id,
            ticket_id=ticket.id,
            ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
            action_plan=ChatActionPlan(
                action="append_report",
                arguments={
                    "ticket_id": ticket.id,
                    "content": task_message,
                    "report_type": "autonomous_loop_step",
                },
            ),
            task_context=context.model_dump(mode="json"),
            capability_grants=list(policy.allowed_capabilities),
            permission_policy={
                "selected_executor": selected_executor,
                "selected_ai_engine": selected_ai_engine,
                "runtime_config": step_request.runtime_config,
                "loop_policy": policy.model_dump(mode="json"),
            },
            budget={**step_request.budget, "max_steps": 1},
            approval_policy={"require_approval_for": list(policy.approval_requirements), "on_missing_approval": "return_needs_approval"},
            expected_outputs={"report": True, "evidence": True, "artifacts": True},
            trace_context={
                "run_id": request_id,
                "thread_id": thread_id,
                "trace_ref": trace_ref,
                "loop_kind": "ticket_native_step",
                "loop_step": loop_step,
                "stop_condition": step_request.stop_condition,
                "ticket_status_before": ticket_status_before,
                "validation_gate": validation_gate_before,
            },
        )
        result = await self.dispatch_service.dispatch(execution_request)
        ingested = False
        ingestion_blocker = ""
        if step_request.ingest_result:
            result = self.ingestion_service.ingest(execution_request, result)
            ingested = result.status in {"completed", "partial", "needs_approval"}
            if not ingested:
                ingestion_blocker = result.errors[-1]["detail"] if result.errors else result.report
        stop_reason = self._stop_reason(result)
        updated_ticket = get_ticket(ticket.id) or ticket
        ticket_status_after = str(getattr(updated_ticket, "status", "") or "")
        validation_gate_after = self._validation_gate(updated_ticket)
        return TicketLoopStepResponse(
            ticket_id=ticket.id,
            status=result.status,
            stop_reason=stop_reason,
            request=execution_request.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
            ingested=ingested,
            ingestion_blocker=ingestion_blocker,
            loop_state={
                "loop_kind": "ticket_native_step",
                "loop_step": loop_step,
                "step_count": 1,
                "max_steps": 1,
                "stop_condition": step_request.stop_condition,
                "employee_id": employee_id,
                "executor_id": result.executor_id,
                "ticket_id": ticket.id,
                "ticket_status_before": ticket_status_before,
                "ticket_status_after": ticket_status_after,
                "validation_gate": validation_gate_after,
                "next_stop_reason": stop_reason,
                "policy": policy.model_dump(mode="json"),
            },
        )

    def _default_message(self, ticket: Any) -> str:
        return (
            f"Advance Ticket {ticket.id}: {ticket.title}. "
            "Produce one governed progress report with evidence, blockers, validation needs, and reusable learning candidates when applicable."
        )

    def _stop_reason(self, result: ExecutionResult) -> str:
        if result.status == "needs_approval":
            return "approval_required"
        if result.status in {"blocked", "failed"}:
            return "blocked_or_failed"
        return "single_step_completed"

    def _validation_gate(self, ticket: Any) -> dict[str, Any]:
        status = str(getattr(ticket, "status", "") or "").strip().lower()
        validation_employee_id = str(getattr(ticket, "validation_employee_id", "") or "").strip()
        validation_role = str(getattr(ticket, "validation_role", "") or "").strip()
        reports = list(getattr(ticket, "reports", []) or [])
        has_validation_report = any(str(getattr(report, "report_type", "") or "").strip().lower() == "validation" for report in reports)
        satisfied = status in {"validated", "completed", "done", "closed"} or has_validation_report
        validation_statuses = {"reported", "review", "pending_validation", "validation", "waiting_validation"}
        requested = status in validation_statuses or bool(validation_employee_id or validation_role)
        required = requested or status in validation_statuses
        if satisfied:
            gate_status = "satisfied"
        elif required:
            gate_status = "required"
        else:
            gate_status = "not_required"
        return {
            "status": gate_status,
            "required": required,
            "requested": requested,
            "satisfied": satisfied,
            "has_validation_report": has_validation_report,
            "validator_employee_id": validation_employee_id,
            "validator_role": validation_role,
        }


def _workspace_root() -> Path:
    configured = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _workspace_dir() -> Path:
    root = _workspace_root()
    return root if root.name == ".aiteamos" else root / ".aiteamos"


def ticket_loop_policy(ticket_id: str, *, workspace_dir: Path | None = None) -> TicketLoopPolicy:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    workspace = workspace_dir or _workspace_dir()
    path = _policy_path(workspace)
    policy = TicketLoopPolicy(
        ticket_id=ticket.id,
        validation_required=bool(ticket.validation_employee_id or ticket.validation_role),
        saved_path=_relative(path),
    )
    metadata_policy = ticket.provider_metadata.get("loop_policy") if isinstance(ticket.provider_metadata, dict) else {}
    if isinstance(metadata_policy, dict):
        policy = _merge_policy(policy, metadata_policy, source="ticket_metadata")
    registry_policy = _load_policy_registry(path).get(ticket.id)
    if isinstance(registry_policy, dict):
        policy = _merge_policy(policy, registry_policy, source="policy_registry")
    return policy.model_copy(update={"saved_path": _relative(path)})


def update_ticket_loop_policy(
    ticket_id: str,
    request: TicketLoopPolicyUpdateRequest,
    *,
    workspace_dir: Path | None = None,
) -> TicketLoopPolicy:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    workspace = workspace_dir or _workspace_dir()
    path = _policy_path(workspace)
    registry = _load_policy_registry(path)
    current = ticket_loop_policy(ticket.id, workspace_dir=workspace)
    updates = request.model_dump(exclude={"actor_employee_id", "actor_role", "reason"}, exclude_none=True)
    updated_at = datetime.now(UTC).isoformat()
    updated = _merge_policy(
        current,
        {
            **updates,
            "ticket_id": ticket.id,
            "updated_by_employee_id": request.actor_employee_id.strip() or "clara",
            "updated_at": updated_at,
        },
        source="policy_registry",
    )
    registry[ticket.id] = updated.model_dump(mode="json")
    _write_policy_registry(path, registry)
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id=request.actor_employee_id.strip() or "clara",
            reporter_role=request.actor_role.strip() or "AI Team OS Manager",
            content=request.reason.strip() or "Ticket loop policy updated.",
            evidence=[_relative(path)],
            report_type="loop_policy_updated",
            source_run_id=f"ticket-loop-policy-{ticket.id}",
        ),
    )
    return updated.model_copy(update={"saved_path": _relative(path)})


def control_ticket_loop(
    ticket_id: str,
    request: TicketLoopControlRequest,
    *,
    workspace_dir: Path | None = None,
) -> TicketLoopControlResponse:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    workspace = workspace_dir or _workspace_dir()
    path = _control_path(workspace)
    registry = _load_control_registry(path)
    events = registry.get(ticket.id, {}).get("events", [])
    if not isinstance(events, list):
        events = []
    updated_at = datetime.now(UTC).isoformat()
    action = request.action.strip().lower()
    state = TicketLoopControlState(
        control_id=f"ticket-loop-control-{ticket.id}-{uuid4().hex[:8]}",
        ticket_id=ticket.id,
        action=action,
        status=_control_status(action),
        active=action in {"stop", "pause", "cancel"},
        actor_employee_id=request.actor_employee_id.strip() or "clara",
        actor_role=request.actor_role.strip() or "AI Team OS Manager",
        reason=request.reason.strip() or f"Ticket loop {action} requested.",
        session_key=request.session_key.strip(),
        updated_at=updated_at,
        saved_path=_relative(path),
    )
    updated_sessions = record_execution_session_control(
        workspace,
        ticket_id=ticket.id,
        action=state.action,
        actor_employee_id=state.actor_employee_id,
        reason=state.reason,
        updated_at=updated_at,
        session_key=state.session_key,
    )
    state = state.model_copy(update={"updated_session_count": len(updated_sessions)})
    registry[ticket.id] = {
        "state": state.model_dump(mode="json"),
        "events": [*events, state.model_dump(mode="json")],
    }
    _write_control_registry(path, registry)
    updated_ticket = add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id=state.actor_employee_id,
            reporter_role=state.actor_role,
            content=state.reason,
            evidence=[_relative(path)],
            report_type="loop_control",
            source_run_id=state.control_id,
        ),
    )
    report_id = updated_ticket.reports[-1].id if updated_ticket.reports else ""
    return TicketLoopControlResponse(
        ticket_id=ticket.id,
        state=state,
        report_id=report_id,
        updated_sessions=updated_sessions,
        saved_paths={"loop_controls": _relative(path)},
    )


def active_ticket_loop_control(ticket_id: str, *, workspace_dir: Path | None = None) -> TicketLoopControlState | None:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    workspace = workspace_dir or _workspace_dir()
    state = _latest_control_state(_control_path(workspace), ticket.id)
    return state if state is not None and state.active else None


def sync_ticket_loop_after_approval_review(
    approval_record: Any,
    *,
    workspace_dir: Path | None = None,
) -> TicketLoopApprovalSync:
    """Translate governed approval review outcomes into durable Ticket loop status."""

    ticket_id = str(getattr(approval_record, "ticket_id", "") or "").strip()
    approval_id = str(getattr(approval_record, "id", "") or "").strip()
    approval_status = str(getattr(approval_record, "status", "") or "").strip().lower()
    if not ticket_id:
        return TicketLoopApprovalSync(
            ticket_id="",
            approval_id=approval_id,
            approval_status=approval_status,
            reason="approval_has_no_ticket",
        )
    target_status = APPROVAL_REVIEW_TICKET_STATUSES.get(approval_status, "")
    if not target_status:
        return TicketLoopApprovalSync(
            ticket_id=ticket_id,
            approval_id=approval_id,
            approval_status=approval_status,
            reason="approval_status_has_no_ticket_loop_mapping",
        )
    ticket = get_ticket(ticket_id)
    if ticket is None:
        return TicketLoopApprovalSync(
            ticket_id=ticket_id,
            approval_id=approval_id,
            approval_status=approval_status,
            ticket_status=target_status,
            reason="ticket_not_found",
        )
    previous_status = str(getattr(ticket, "status", "") or "").strip().lower()
    if previous_status in TERMINAL_TICKET_STATUSES:
        return TicketLoopApprovalSync(
            ticket_id=ticket.id,
            approval_id=approval_id,
            approval_status=approval_status,
            ticket_status=previous_status,
            previous_ticket_status=previous_status,
            reason="terminal_ticket_status_not_changed",
        )
    if previous_status == target_status:
        return TicketLoopApprovalSync(
            ticket_id=ticket.id,
            approval_id=approval_id,
            approval_status=approval_status,
            ticket_status=target_status,
            previous_ticket_status=previous_status,
            reason="ticket_status_already_synced",
        )
    try:
        updated = transition_ticket_state(
            ticket.id,
            TicketStateTransitionRequest(
                status=target_status,
                actor_employee_id=str(getattr(approval_record, "reviewer_employee_id", "") or "clara"),
                actor_role="AI Team OS Manager",
                source_run_id=approval_id,
            ),
        )
    except Exception as exc:
        blocker_report_id = _record_approval_ticket_status_blocker(
            approval_record,
            target_status=target_status,
            detail=str(exc),
            workspace_dir=workspace_dir,
        )
        return TicketLoopApprovalSync(
            ticket_id=ticket.id,
            approval_id=approval_id,
            approval_status=approval_status,
            ticket_status=target_status,
            previous_ticket_status=previous_status,
            changed=False,
            reason=f"ticket_state_transition_blocked:{str(exc)[:240]}",
            blocker_report_id=blocker_report_id,
        )
    return TicketLoopApprovalSync(
        ticket_id=ticket.id,
        approval_id=approval_id,
        approval_status=approval_status,
        ticket_status=str(getattr(updated, "status", "") or target_status),
        previous_ticket_status=previous_status,
        changed=True,
        reason="ticket_status_synced",
    )


def sync_ticket_loop_after_approval_request(
    approval_record: Any,
    *,
    workspace_dir: Path | None = None,
) -> TicketLoopApprovalSync:
    ticket_id = str(getattr(approval_record, "ticket_id", "") or "").strip()
    approval_id = str(getattr(approval_record, "id", "") or "").strip()
    approval_status = str(getattr(approval_record, "status", "") or "").strip().lower()
    if approval_status and approval_status != "requested":
        return TicketLoopApprovalSync(
            ticket_id=ticket_id,
            approval_id=approval_id,
            approval_status=approval_status,
            reason="approval_request_already_reviewed",
        )
    if not ticket_id:
        return TicketLoopApprovalSync(
            ticket_id="",
            approval_id=approval_id,
            approval_status=approval_status or "requested",
            reason="approval_has_no_ticket",
        )
    ticket = get_ticket(ticket_id)
    if ticket is None:
        return TicketLoopApprovalSync(
            ticket_id=ticket_id,
            approval_id=approval_id,
            approval_status=approval_status or "requested",
            ticket_status=APPROVAL_REQUEST_TICKET_STATUS,
            reason="ticket_not_found",
        )
    previous_status = str(getattr(ticket, "status", "") or "").strip().lower()
    if previous_status in TERMINAL_TICKET_STATUSES:
        return TicketLoopApprovalSync(
            ticket_id=ticket.id,
            approval_id=approval_id,
            approval_status=approval_status or "requested",
            ticket_status=previous_status,
            previous_ticket_status=previous_status,
            reason="terminal_ticket_status_not_changed",
        )
    if previous_status == APPROVAL_REQUEST_TICKET_STATUS:
        return TicketLoopApprovalSync(
            ticket_id=ticket.id,
            approval_id=approval_id,
            approval_status=approval_status or "requested",
            ticket_status=APPROVAL_REQUEST_TICKET_STATUS,
            previous_ticket_status=previous_status,
            reason="ticket_status_already_synced",
        )
    try:
        updated = transition_ticket_state(
            ticket.id,
            TicketStateTransitionRequest(
                status=APPROVAL_REQUEST_TICKET_STATUS,
                actor_employee_id=str(getattr(approval_record, "employee_id", "") or "clara"),
                actor_role="AI Team OS Manager",
                source_run_id=approval_id,
            ),
        )
    except Exception as exc:
        blocker_report_id = _record_approval_ticket_status_blocker(
            approval_record,
            target_status=APPROVAL_REQUEST_TICKET_STATUS,
            detail=str(exc),
            workspace_dir=workspace_dir,
        )
        return TicketLoopApprovalSync(
            ticket_id=ticket.id,
            approval_id=approval_id,
            approval_status=approval_status or "requested",
            ticket_status=APPROVAL_REQUEST_TICKET_STATUS,
            previous_ticket_status=previous_status,
            changed=False,
            reason=f"ticket_state_transition_blocked:{str(exc)[:240]}",
            blocker_report_id=blocker_report_id,
        )
    return TicketLoopApprovalSync(
        ticket_id=ticket.id,
        approval_id=approval_id,
        approval_status=approval_status or "requested",
        ticket_status=str(getattr(updated, "status", "") or APPROVAL_REQUEST_TICKET_STATUS),
        previous_ticket_status=previous_status,
        changed=True,
        reason="ticket_status_synced",
    )


def list_ticket_loop_runs(ticket_id: str, *, workspace_dir: Path | None = None) -> list[TicketLoopRunRecord]:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    workspace = workspace_dir or _workspace_dir()
    path = _run_path(workspace)
    records = [
        _run_record_from_payload(payload, path)
        for payload in _load_run_registry(path).values()
        if str(payload.get("ticket_id") or "") == ticket.id
    ]
    return sorted(records, key=lambda record: record.updated_at or record.started_at or record.queued_at, reverse=True)


def get_ticket_loop_run(ticket_id: str, run_id: str, *, workspace_dir: Path | None = None) -> TicketLoopRunRecord | None:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    workspace = workspace_dir or _workspace_dir()
    path = _run_path(workspace)
    payload = _load_run_registry(path).get(run_id.strip())
    if not isinstance(payload, dict) or str(payload.get("ticket_id") or "") != ticket.id:
        return None
    return _run_record_from_payload(payload, path)


def ticket_loop_timeline(ticket_id: str, *, workspace_dir: Path | None = None) -> TicketLoopTimelineResponse:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    workspace = workspace_dir or _workspace_dir()
    root = _workspace_root_from_workspace(workspace)
    items: list[TicketLoopTimelineItem] = []

    for event in getattr(ticket, "events", []) or []:
        event_id = str(getattr(event, "event_id", "") or f"event-{len(items) + 1}")
        data = getattr(event, "data", {}) if isinstance(getattr(event, "data", {}), dict) else {}
        actor = getattr(event, "actor", {}) if isinstance(getattr(event, "actor", {}), dict) else {}
        items.append(
            TicketLoopTimelineItem(
                timeline_id=f"event:{event_id}",
                ticket_id=ticket.id,
                kind="ticket_event",
                status=str(data.get("to") or data.get("status") or getattr(ticket, "status", "") or ""),
                title=str(getattr(event, "type", "") or "ticket_event"),
                detail=_timeline_event_detail(str(getattr(event, "type", "") or ""), data),
                at=str(getattr(event, "at", "") or ""),
                actor_employee_id=str(actor.get("id") or ""),
                actor_role=str(actor.get("role") or ""),
                source_kind="ticket_event",
                source_ref=event_id,
                refs=_timeline_refs_from_event(data),
                data=getattr(event, "model_dump", lambda **_: {})(),
            )
        )

    for report in getattr(ticket, "reports", []) or []:
        report_id = str(getattr(report, "id", "") or f"report-{len(items) + 1}")
        evidence = [str(item) for item in getattr(report, "evidence", []) or [] if str(item)]
        items.append(
            TicketLoopTimelineItem(
                timeline_id=f"report:{report_id}",
                ticket_id=ticket.id,
                kind="ticket_report",
                status=str(getattr(report, "report_type", "") or "report"),
                title=f"Report: {str(getattr(report, 'report_type', '') or 'progress')}",
                detail=str(getattr(report, "content", "") or "")[:500],
                at=str(getattr(report, "created_at", "") or ""),
                actor_employee_id=str(getattr(report, "reporter_employee_id", "") or ""),
                actor_role=str(getattr(report, "reporter_role", "") or ""),
                source_kind="ticket_report",
                source_ref=report_id,
                target_route=_report_target_route(ticket.id, report_id),
                refs=[
                    _timeline_ref("evidence", ref, ticket_id=ticket.id, report_id=report_id, evidence_index=index)
                    for index, ref in enumerate(evidence)
                ],
                data=getattr(report, "model_dump", lambda **_: {})(),
            )
        )

    for approval in _timeline_approvals(root, ticket.id):
        approval_id = str(getattr(approval, "id", "") or "")
        refs = [
            _timeline_ref(kind, ref)
            for kind, ref in [
                ("checkpoint", str(getattr(approval, "checkpoint_ref", "") or "")),
                ("state", str(getattr(approval, "source_state_ref", "") or "")),
                ("state_snapshot", str(getattr(approval, "source_state_snapshot_ref", "") or "")),
            ]
            if ref
        ]
        executor_id = str(getattr(approval, "executor_id", "") or "")
        items.append(
            TicketLoopTimelineItem(
                timeline_id=f"approval:{approval_id}",
                ticket_id=ticket.id,
                kind="approval",
                status=str(getattr(approval, "status", "") or "requested"),
                title=f"Runtime approval {str(getattr(approval, 'status', '') or 'requested')}",
                detail=str(getattr(approval, "review_reason", "") or getattr(approval, "reason", "") or ""),
                at=str(getattr(approval, "reviewed_at", "") or getattr(approval, "updated_at", "") or getattr(approval, "created_at", "") or ""),
                actor_employee_id=str(getattr(approval, "reviewer_employee_id", "") or getattr(approval, "employee_id", "") or ""),
                actor_role="AI Team OS Manager" if getattr(approval, "reviewer_employee_id", "") else "",
                source_kind="execution_approval",
                source_ref=approval_id,
                target_route=f"assets/review/runtime-approval:{executor_id}:{approval_id}" if executor_id and approval_id else "",
                refs=refs,
                data=getattr(approval, "model_dump", lambda **_: {})(),
            )
        )

    for run in list_ticket_loop_runs(ticket.id, workspace_dir=workspace):
        items.append(
            TicketLoopTimelineItem(
                timeline_id=f"loop_run:{run.run_id}",
                ticket_id=ticket.id,
                kind="loop_run",
                status=run.status,
                title=f"Loop run {run.status}",
                detail=run.stop_reason or f"{run.step_count} steps",
                at=run.updated_at or run.finished_at or run.started_at or run.queued_at,
                actor_employee_id=str(run.request.get("employee_id") or ""),
                actor_role="",
                source_kind="ticket_loop_run",
                source_ref=run.run_id,
                refs=[
                    ref
                    for ref in [
                        _timeline_ref("runtime_session", str(run.response.get("session_key") or run.request.get("session_key") or "")),
                        _timeline_ref("saved_path", run.saved_path),
                    ]
                    if ref.ref
                ],
                data=run.model_dump(mode="json"),
            )
        )

    for queue_item in list_ticket_loop_queue(workspace_dir=workspace):
        if queue_item.ticket_id != ticket.id:
            continue
        items.append(
            TicketLoopTimelineItem(
                timeline_id=f"loop_queue:{queue_item.queue_id}",
                ticket_id=ticket.id,
                kind="loop_queue",
                status=queue_item.status,
                title=f"Queue item {queue_item.status}",
                detail=queue_item.reason or queue_item.error,
                at=queue_item.updated_at or queue_item.finished_at or queue_item.started_at or queue_item.enqueued_at,
                actor_employee_id=queue_item.actor_employee_id,
                actor_role=queue_item.actor_role,
                source_kind="ticket_loop_queue",
                source_ref=queue_item.queue_id,
                refs=[_timeline_ref("loop_run", queue_item.run_id)],
                data=queue_item.model_dump(mode="json"),
            )
        )

    for session_key, session in _timeline_sessions(workspace, ticket.id).items():
        items.append(
            TicketLoopTimelineItem(
                timeline_id=f"runtime_session:{session_key}",
                ticket_id=ticket.id,
                kind="runtime_session",
                status=str(session.get("status") or ""),
                title=f"Runtime session {str(session.get('status') or 'recorded')}",
                detail=str(session.get("last_request_id") or session.get("executor_id") or ""),
                at=str(session.get("updated_at") or ""),
                actor_employee_id=str(session.get("employee_id") or ""),
                actor_role="",
                source_kind="execution_session",
                source_ref=session_key,
                target_route=f"runtime/{session_key}",
                refs=[
                    ref
                    for ref in [
                        _timeline_ref("checkpoint", str(session.get("checkpoint_ref") or "")),
                        _timeline_ref("executor_session", str(session.get("executor_session_ref") or "")),
                        _timeline_ref("trace", str(session.get("trace_ref") or "")),
                    ]
                    if ref.ref
                ],
                data=session,
            )
        )

    for asset in ticket_assets_for_ticket(ticket.id):
        asset_id = str(getattr(asset, "id", "") or "")
        items.append(
            TicketLoopTimelineItem(
                timeline_id=f"asset:{asset_id}",
                ticket_id=ticket.id,
                kind="asset",
                status=str(getattr(asset, "status", "") or ""),
                title=str(getattr(asset, "title", "") or asset_id),
                detail=str(getattr(asset, "kind", "") or "asset"),
                at=str(getattr(asset, "updated_at", "") or getattr(asset, "created_at", "") or ""),
                actor_employee_id=str(getattr(asset, "source_employee_id", "") or ""),
                actor_role="",
                source_kind="asset",
                source_ref=asset_id,
                target_route=f"assets/asset/{asset_id}" if asset_id else "",
                refs=[_timeline_ref("asset", asset_id)],
                data=getattr(asset, "model_dump", lambda **_: {})(),
            )
        )

    items = sorted(items, key=lambda item: item.at or "", reverse=True)
    summary = _timeline_summary(ticket, items, workspace)
    return TicketLoopTimelineResponse(
        ticket_id=ticket.id,
        summary=summary,
        items=items,
        saved_paths={
            "loop_runs": _relative(_run_path(workspace)),
            "loop_queue": _relative(_queue_path(workspace)),
            "loop_controls": _relative(_control_path(workspace)),
        },
    )


def resume_ticket_loop(
    ticket_id: str,
    request: TicketLoopResumeRequest,
    *,
    workspace_dir: Path | None = None,
) -> TicketLoopResumeResponse:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    current_status = str(getattr(ticket, "status", "") or "").strip().lower()
    if current_status in {"waiting_approval"}:
        raise ValueError("Ticket is waiting for approval review before the loop can resume.")
    if current_status in TERMINAL_TICKET_STATUSES:
        raise ValueError(f"Ticket is already terminal: {current_status}.")
    allowed_statuses = {"ready_to_resume", "waiting_changes", "waiting_evidence", "assigned", "in_progress", "reported", "blocked", "failed"}
    if current_status and current_status not in allowed_statuses:
        raise ValueError(f"Ticket status is not resumable: {current_status}.")
    workspace = workspace_dir or _workspace_dir()
    _ensure_retry_prerequisites(ticket, request, current_status, workspace)
    resume_id = f"ticket-loop-resume-{ticket.id}-{uuid4().hex[:8]}"
    target_status = "in_progress"
    if current_status != target_status:
        try:
            transition_ticket_state(
                ticket.id,
                TicketStateTransitionRequest(
                    status=target_status,
                    actor_employee_id=request.actor_employee_id.strip() or "clara",
                    actor_role=request.actor_role.strip() or "AI Team OS Manager",
                    source_run_id=resume_id,
                ),
            )
        except Exception as exc:
            add_ticket_report(
                ticket.id,
                TicketReportRequest(
                    reporter_employee_id=request.actor_employee_id.strip() or "clara",
                    reporter_role=request.actor_role.strip() or "AI Team OS Manager",
                    content=(
                        "Ticket loop resume was blocked before queueing.\n"
                        f"Previous status: {current_status or '-'}.\n"
                        f"Target status: {target_status}.\n"
                        f"Provider blocker: {exc}"
                    ),
                    evidence=[],
                    report_type="loop_resume_blocked",
                    source_run_id=resume_id,
                ),
            )
            raise ValueError(f"Ticket loop resume blocked: {exc}") from exc
    item = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id=request.employee_id.strip() or ticket.assigned_employee_id or "clara",
            message=request.message.strip() or f"Resume Ticket {ticket.id}: {ticket.title}",
            selected_executor=request.selected_executor,
            selected_ai_engine=request.selected_ai_engine,
            max_steps=request.max_steps,
            max_runtime_seconds=request.max_runtime_seconds,
            priority=request.priority,
            actor_employee_id=request.actor_employee_id.strip() or "clara",
            actor_role=request.actor_role.strip() or "AI Team OS Manager",
            reason=request.reason.strip() or f"Ticket loop {request.action} queued.",
            runtime_config={
                **request.runtime_config,
                "loop_resume_id": resume_id,
                "loop_resume_action": request.action,
                "previous_ticket_status": current_status,
            },
            ingest_result=request.ingest_result,
        ),
        workspace_dir=workspace,
    )
    return TicketLoopResumeResponse(
        ticket_id=ticket.id,
        status=target_status,
        previous_status=current_status,
        detail=f"Ticket loop {request.action} queued from {current_status or 'unknown'} status.",
        queue_item=item,
        saved_paths={"loop_queue": _relative(_queue_path(workspace)), "loop_runs": _relative(_run_path(workspace))},
    )


def enqueue_ticket_loop(
    ticket_id: str,
    request: TicketLoopEnqueueRequest,
    *,
    workspace_dir: Path | None = None,
) -> TicketLoopQueueItem:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    workspace = workspace_dir or _workspace_dir()
    path = _queue_path(workspace)
    now = datetime.now(UTC).isoformat()
    run_id = str(request.runtime_config.get("loop_run_id") or f"ticket-loop-run-{ticket.id}-{uuid4().hex[:8]}")
    queue_id = f"ticket-loop-queue-{ticket.id}-{uuid4().hex[:8]}"
    run_request = TicketLoopRunRequest(
        employee_id=request.employee_id,
        message=request.message,
        selected_executor=request.selected_executor,
        selected_ai_engine=request.selected_ai_engine,
        max_steps=request.max_steps,
        max_runtime_seconds=request.max_runtime_seconds,
        stop_statuses=request.stop_statuses,
        stop_condition=request.stop_condition,
        budget=request.budget,
        runtime_config={**request.runtime_config, "loop_run_id": run_id, "loop_queue_id": queue_id},
        ingest_result=request.ingest_result,
    )
    report = add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id=request.actor_employee_id.strip() or "clara",
            reporter_role=request.actor_role.strip() or "AI Team OS Manager",
            content=request.reason.strip() or "Ticket loop queued.",
            evidence=[_relative(path)],
            report_type="loop_queued",
            source_run_id=queue_id,
        ),
    )
    item = TicketLoopQueueItem(
        queue_id=queue_id,
        run_id=run_id,
        ticket_id=ticket.id,
        status="queued",
        priority=request.priority,
        request=run_request.model_dump(mode="json"),
        actor_employee_id=request.actor_employee_id.strip() or "clara",
        actor_role=request.actor_role.strip() or "AI Team OS Manager",
        reason=request.reason.strip() or "Ticket loop queued.",
        report_id=report.reports[-1].id if report.reports else "",
        enqueued_at=now,
        updated_at=now,
        saved_path=_relative(path),
    )
    registry = _load_queue_registry(path)
    registry[item.queue_id] = item.model_dump(mode="json")
    _write_queue_registry(path, registry)
    _upsert_loop_run_record(
        workspace,
        TicketLoopRunRecord(
            run_id=run_id,
            ticket_id=ticket.id,
            status="queued",
            active=True,
            request=run_request.model_dump(mode="json"),
            step_count=0,
            queued_at=now,
            updated_at=now,
            saved_path=_relative(_run_path(workspace)),
        ),
    )
    return item


def list_ticket_loop_queue(*, workspace_dir: Path | None = None, status: str = "") -> list[TicketLoopQueueItem]:
    workspace = workspace_dir or _workspace_dir()
    path = _queue_path(workspace)
    normalized_status = status.strip().lower()
    items = [_queue_item_from_payload(payload, path) for payload in _load_queue_registry(path).values()]
    if normalized_status:
        items = [item for item in items if item.status == normalized_status]
    return sorted(items, key=lambda item: (item.priority, item.enqueued_at or item.updated_at))


def ticket_loop_queue_status(*, workspace_dir: Path | None = None) -> TicketLoopQueueStatus:
    workspace = workspace_dir or _workspace_dir()
    path = _queue_path(workspace)
    items = list_ticket_loop_queue(workspace_dir=workspace)
    queued = [item for item in items if item.status == "queued"]
    running = [item for item in items if item.status == "running"]
    completed = [item for item in items if item.status in {"completed", "partial", "needs_approval"}]
    failed = [item for item in items if item.status in {"failed", "blocked"}]
    active = [*queued, *running]
    latest_activity = max(
        [item.updated_at or item.finished_at or item.started_at or item.enqueued_at for item in items if item.updated_at or item.finished_at or item.started_at or item.enqueued_at],
        default="",
    )
    next_item = queued[0] if queued else None
    if running:
        status = "running"
    elif queued:
        status = "queued"
    elif failed:
        status = "needs_attention"
    elif completed:
        status = "idle"
    else:
        status = "empty"
    return TicketLoopQueueStatus(
        status=status,
        queued_count=len(queued),
        running_count=len(running),
        completed_count=len(completed),
        failed_count=len(failed),
        active_count=len(active),
        total_count=len(items),
        oldest_queued_at=queued[0].enqueued_at if queued else "",
        latest_activity_at=latest_activity,
        next_queue_id=next_item.queue_id if next_item else "",
        next_ticket_id=next_item.ticket_id if next_item else "",
        next_run_id=next_item.run_id if next_item else "",
        saved_paths={"loop_queue": _relative(path), "loop_runs": _relative(_run_path(workspace))},
    )


async def pump_ticket_loop_queue(
    request: TicketLoopQueuePumpRequest | None = None,
    *,
    workspace_dir: Path | None = None,
    service: TicketAutonomousLoopService | None = None,
) -> TicketLoopQueuePumpResponse:
    pump_request = request or TicketLoopQueuePumpRequest()
    workspace = workspace_dir or _workspace_dir()
    path = _queue_path(workspace)
    registry = _load_queue_registry(path)
    service = service or TicketAutonomousLoopService(workspace_dir=workspace)
    policy_actions = run_ticket_loop_policy_preflight(workspace_dir=workspace)
    registry = _load_queue_registry(path)
    queued = [
        _queue_item_from_payload(payload, path)
        for payload in registry.values()
        if str(payload.get("status") or "") == "queued"
    ]
    queued = sorted(queued, key=lambda item: (item.priority, item.enqueued_at or item.updated_at))
    processed: list[TicketLoopQueueItem] = []
    for item in queued[:pump_request.max_items]:
        started_at = datetime.now(UTC).isoformat()
        running = item.model_copy(update={"status": "running", "started_at": started_at, "updated_at": started_at})
        registry[item.queue_id] = running.model_dump(mode="json")
        _write_queue_registry(path, registry)
        try:
            response = await service.run_loop(item.ticket_id, TicketLoopRunRequest.model_validate(item.request))
            finished_at = datetime.now(UTC).isoformat()
            completed = running.model_copy(
                update={
                    "status": response.status,
                    "response": response.model_dump(mode="json"),
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive path covered by route behavior.
            finished_at = datetime.now(UTC).isoformat()
            completed = running.model_copy(
                update={
                    "status": "failed",
                    "error": str(exc),
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                }
            )
            _upsert_loop_run_record(
                workspace,
                TicketLoopRunRecord(
                    run_id=item.run_id,
                    ticket_id=item.ticket_id,
                    status="failed",
                    stop_reason="queue_worker_failed",
                    active=False,
                    request=item.request,
                    step_count=0,
                    queued_at=item.enqueued_at,
                    started_at=started_at,
                    finished_at=finished_at,
                    updated_at=finished_at,
                    saved_path=_relative(_run_path(workspace)),
                ),
            )
        registry[item.queue_id] = completed.model_dump(mode="json")
        _write_queue_registry(path, registry)
        processed.append(completed)
        action = _auto_propose_failure_retrospective_if_ready(completed, workspace)
        if action is not None:
            policy_actions.append(action)
    remaining = len([item for item in registry.values() if str(item.get("status") or "") == "queued"])
    return TicketLoopQueuePumpResponse(
        status="completed" if processed or policy_actions else "idle",
        processed=processed,
        policy_actions=policy_actions,
        remaining_queued=remaining,
        saved_paths={"loop_queue": _relative(path)},
    )


def run_ticket_loop_policy_preflight(*, workspace_dir: Path | None = None) -> list[TicketLoopPolicyAction]:
    """Record due Ticket-loop policy signals without owning a separate scheduler."""

    workspace = workspace_dir or _workspace_dir()
    now = datetime.now(UTC)
    actions: list[TicketLoopPolicyAction] = []
    for ticket_id in _policy_preflight_ticket_ids(workspace):
        ticket = get_ticket(ticket_id)
        if ticket is None:
            continue
        policy = ticket_loop_policy(ticket.id, workspace_dir=workspace)
        action = _record_sla_breach_if_due(ticket, policy, workspace, now)
        if action is not None:
            actions.append(action)
            ticket = get_ticket(ticket_id) or ticket
            policy = ticket_loop_policy(ticket.id, workspace_dir=workspace)
        action = _record_recurrence_due_if_due(ticket, policy, workspace, now)
        if action is not None:
            actions.append(action)
    return actions


def _policy_preflight_ticket_ids(workspace: Path) -> list[str]:
    policy_ticket_ids = set(_load_policy_registry(_policy_path(workspace)).keys())
    queue_ticket_ids = {
        item.ticket_id
        for item in list_ticket_loop_queue(workspace_dir=workspace)
        if item.status.strip().lower() in {"queued", "running"}
    }
    return sorted(policy_ticket_ids | queue_ticket_ids)


def _record_sla_breach_if_due(
    ticket: Any,
    policy: TicketLoopPolicy,
    workspace: Path,
    now: datetime,
) -> TicketLoopPolicyAction | None:
    due_seconds = policy.sla.response_due_seconds
    if not due_seconds or _ticket_is_terminal(ticket):
        return None
    created_at = _parse_datetime(str(getattr(ticket, "created_at", "") or ""))
    if created_at is None:
        return None
    due_at = created_at + timedelta(seconds=due_seconds)
    if now < due_at:
        return None
    source_run_id = f"ticket-loop-sla-{ticket.id}-response"
    existing_queue_item = _sla_escalation_queue_item_for_source(ticket.id, source_run_id, workspace)
    if _ticket_has_source_run_id(ticket, source_run_id):
        return None
    queued = existing_queue_item or _enqueue_sla_escalation_loop_if_configured(
        ticket=ticket,
        policy=policy,
        source_run_id=source_run_id,
        due_at=due_at,
        workspace=workspace,
    )
    escalation = _sla_escalation_detail(policy)
    content = "\n".join(
        line
        for line in [
            "Ticket loop SLA response deadline was breached.",
            f"Response due after: {due_seconds} seconds.",
            f"Ticket created at: {created_at.isoformat()}.",
            f"Due at: {due_at.isoformat()}.",
            f"Queued escalation run: {queued.run_id}." if queued is not None else "",
            f"Escalation queue item: {queued.queue_id}." if queued is not None else "",
            escalation,
        ]
        if line
    )
    updated = add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id=policy.updated_by_employee_id or "clara",
            reporter_role=policy.sla.escalation_role or "AI Team OS Manager",
            content=content,
            evidence=[ref for ref in [policy.saved_path, _relative(_queue_path(workspace))] if ref],
            report_type="ticket_loop_sla_breach",
            source_run_id=source_run_id,
        ),
    )
    report_id = updated.reports[-1].id if updated.reports else ""
    handoff_refs = _record_sla_escalation_handoff(ticket, policy, source_run_id)
    status = "escalated" if handoff_refs else "recorded"
    return TicketLoopPolicyAction(
        kind="sla_escalation_handoff" if handoff_refs else "sla_breach_report",
        ticket_id=ticket.id,
        status=status,
        detail=f"Ticket loop SLA response deadline breached at {due_at.isoformat()}.",
        queue_ids=[queued.queue_id] if queued is not None else [],
        run_ids=[queued.run_id] if queued is not None else [],
        handoff_refs=handoff_refs,
        report_id=report_id,
    )


def _record_recurrence_due_if_due(
    ticket: Any,
    policy: TicketLoopPolicy,
    workspace: Path,
    now: datetime,
) -> TicketLoopPolicyAction | None:
    recurrence = policy.recurrence
    if not recurrence.enabled or _ticket_is_terminal(ticket):
        return None
    next_run_at = _parse_datetime(recurrence.next_run_at)
    if next_run_at is None or now < next_run_at:
        return None
    if recurrence.max_occurrences is not None and _recurrence_due_report_count(ticket) >= recurrence.max_occurrences:
        return None
    source_run_id = f"ticket-loop-recurrence-{ticket.id}-{_source_ref_fragment(recurrence.next_run_at)}"
    if _ticket_has_source_run_id(ticket, source_run_id):
        return None
    existing_queue_item = _recurrence_queue_item_for_source(ticket.id, source_run_id, workspace)
    if existing_queue_item is not None:
        return None
    occurrence_count = _recurrence_due_report_count(ticket) + 1
    next_policy_run_at = _next_recurrence_policy_run_at(recurrence, next_run_at, now, occurrence_count)
    queued = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id=str(getattr(ticket, "assigned_employee_id", "") or "clara"),
            message=f"Run recurring governed loop for Ticket {ticket.id}: {getattr(ticket, 'title', ticket.id)}",
            max_steps=policy.max_steps,
            max_runtime_seconds=policy.max_runtime_seconds,
            stop_statuses=policy.stop_statuses,
            runtime_config={
                "loop_run_id": f"ticket-loop-recurrence-{ticket.id}-{uuid4().hex[:8]}",
                "recurrence_source_run_id": source_run_id,
                "recurrence_due_at": next_run_at.isoformat(),
                "recurrence_occurrence": occurrence_count,
                "recurrence_next_run_at": next_policy_run_at,
            },
            actor_employee_id=policy.updated_by_employee_id or "clara",
            actor_role="AI Team OS Manager",
            reason=f"Queue recurring governed Ticket loop due at {next_run_at.isoformat()}.",
            priority=80,
        ),
        workspace_dir=workspace,
    )
    content = "\n".join(
        line
        for line in [
            "Ticket loop recurrence policy is due.",
            f"Next run was scheduled for: {next_run_at.isoformat()}.",
            f"Queued governed loop run: {queued.run_id}.",
            f"Queue item: {queued.queue_id}.",
            f"Next policy run at: {next_policy_run_at or '-'}",
        ]
        if line
    )
    updated = add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id=policy.updated_by_employee_id or "clara",
            reporter_role="AI Team OS Manager",
            content=content,
            evidence=[ref for ref in [policy.saved_path, _relative(_queue_path(workspace))] if ref],
            report_type="ticket_loop_recurrence_due",
            source_run_id=source_run_id,
        ),
    )
    if next_policy_run_at or _recurrence_max_occurrences_reached(recurrence, occurrence_count):
        _persist_recurrence_after_enqueue(policy, workspace, next_policy_run_at, now, occurrence_count)
    report_id = updated.reports[-1].id if updated.reports else ""
    return TicketLoopPolicyAction(
        kind="recurrence_auto_enqueued",
        ticket_id=ticket.id,
        status="queued",
        detail=f"Ticket loop recurrence due at {next_run_at.isoformat()} was queued through the existing loop queue.",
        queue_ids=[queued.queue_id],
        run_ids=[queued.run_id],
        report_id=report_id,
    )


def _sla_escalation_detail(policy: TicketLoopPolicy) -> str:
    escalation_employee_id = policy.sla.escalation_employee_id.strip()
    escalation_role = policy.sla.escalation_role.strip()
    if not (escalation_employee_id or escalation_role):
        return ""
    return f"Escalation target: {escalation_employee_id or '-'} / {escalation_role or '-'}."


def _record_sla_escalation_handoff(ticket: Any, policy: TicketLoopPolicy, source_run_id: str) -> list[dict[str, str]]:
    to_employee_id = policy.sla.escalation_employee_id.strip()
    to_role = policy.sla.escalation_role.strip()
    if not (to_employee_id or to_role):
        return []
    current_employee_id = str(getattr(ticket, "assigned_employee_id", "") or "").strip()
    current_role = str(getattr(ticket, "assigned_role", "") or "").strip()
    if to_employee_id == current_employee_id and to_role == current_role:
        return []
    updated = record_ticket_handoff(
        str(getattr(ticket, "id", "") or ""),
        TicketHandoffRequest(
            to_employee_id=to_employee_id,
            to_role=to_role,
            from_employee_id=current_employee_id,
            from_role=current_role,
            content="Ticket loop SLA breach escalated this Ticket to the configured escalation Employee.",
            actor_employee_id=policy.updated_by_employee_id or "clara",
            actor_role="AI Team OS Manager",
            source_run_id=source_run_id,
        ),
    )
    refs: list[dict[str, str]] = []
    for event in getattr(updated, "events", []) or []:
        data = getattr(event, "data", {}) if isinstance(getattr(event, "data", {}), dict) else {}
        if str(data.get("source_run_id") or "") != source_run_id:
            continue
        event_type = str(getattr(event, "type", "") or "")
        if event_type not in {"handoff_requested", "assigned"}:
            continue
        refs.append(
            {
                "kind": event_type,
                "event_id": str(getattr(event, "event_id", "") or ""),
                "ticket_id": str(getattr(updated, "id", "") or ""),
                "from_employee_id": str(data.get("from_employee_id") or ""),
                "to_employee_id": str(data.get("to_employee_id") or data.get("assigned_employee_id") or ""),
                "to_role": str(data.get("to_role") or data.get("assigned_role") or ""),
            }
        )
    return refs


def _enqueue_sla_escalation_loop_if_configured(
    *,
    ticket: Any,
    policy: TicketLoopPolicy,
    source_run_id: str,
    due_at: datetime,
    workspace: Path,
) -> TicketLoopQueueItem | None:
    to_employee_id = policy.sla.escalation_employee_id.strip()
    to_role = policy.sla.escalation_role.strip()
    if not (to_employee_id or to_role):
        return None
    ticket_id = str(getattr(ticket, "id", "") or "")
    if not ticket_id:
        return None
    existing = _sla_escalation_queue_item_for_source(ticket_id, source_run_id, workspace)
    if existing is not None:
        return existing
    assigned_employee_id = str(getattr(ticket, "assigned_employee_id", "") or "").strip()
    assigned_role = str(getattr(ticket, "assigned_role", "") or "").strip()
    title = str(getattr(ticket, "title", "") or ticket_id)
    return enqueue_ticket_loop(
        ticket_id,
        TicketLoopEnqueueRequest(
            employee_id=to_employee_id or assigned_employee_id or "clara",
            message=f"Run SLA escalation governed loop for Ticket {ticket_id}: {title}",
            max_steps=policy.max_steps,
            max_runtime_seconds=policy.max_runtime_seconds,
            stop_statuses=policy.stop_statuses,
            runtime_config={
                "loop_run_id": f"ticket-loop-sla-escalation-{ticket_id}-{uuid4().hex[:8]}",
                "sla_escalation_source_run_id": source_run_id,
                "sla_due_at": due_at.isoformat(),
                "sla_response_due_seconds": policy.sla.response_due_seconds,
                "sla_escalation_employee_id": to_employee_id,
                "sla_escalation_role": to_role or assigned_role,
            },
            actor_employee_id=policy.updated_by_employee_id or "clara",
            actor_role="AI Team OS Manager",
            reason=f"Queue SLA escalation governed Ticket loop due at {due_at.isoformat()}.",
            priority=40,
        ),
        workspace_dir=workspace,
    )


def _ticket_is_terminal(ticket: Any) -> bool:
    return str(getattr(ticket, "status", "") or "").strip().lower() in TERMINAL_TICKET_STATUSES


def _ticket_has_source_run_id(ticket: Any, source_run_id: str) -> bool:
    for event in getattr(ticket, "events", []) or []:
        data = getattr(event, "data", {}) if isinstance(getattr(event, "data", {}), dict) else {}
        if str(data.get("source_run_id") or "") == source_run_id:
            return True
    return False


def _recurrence_due_report_count(ticket: Any) -> int:
    return sum(
        1
        for report in getattr(ticket, "reports", []) or []
        if str(getattr(report, "report_type", "") or "") == "ticket_loop_recurrence_due"
    )


def _recurrence_queue_item_for_source(ticket_id: str, source_run_id: str, workspace: Path) -> TicketLoopQueueItem | None:
    return _queue_item_for_runtime_source(ticket_id, "recurrence_source_run_id", source_run_id, workspace)


def _sla_escalation_queue_item_for_source(ticket_id: str, source_run_id: str, workspace: Path) -> TicketLoopQueueItem | None:
    return _queue_item_for_runtime_source(ticket_id, "sla_escalation_source_run_id", source_run_id, workspace)


def _queue_item_for_runtime_source(ticket_id: str, runtime_key: str, source_run_id: str, workspace: Path) -> TicketLoopQueueItem | None:
    for item in list_ticket_loop_queue(workspace_dir=workspace):
        if item.ticket_id != ticket_id:
            continue
        runtime_config = item.request.get("runtime_config") if isinstance(item.request, dict) else {}
        if isinstance(runtime_config, dict) and str(runtime_config.get(runtime_key) or "") == source_run_id:
            return item
    return None


def _next_recurrence_policy_run_at(
    recurrence: TicketLoopRecurrencePolicy,
    due_at: datetime,
    now: datetime,
    occurrence_count: int,
) -> str:
    if _recurrence_max_occurrences_reached(recurrence, occurrence_count):
        return ""
    if not recurrence.interval_seconds:
        return ""
    next_run_at = due_at + timedelta(seconds=recurrence.interval_seconds)
    while next_run_at <= now:
        next_run_at += timedelta(seconds=recurrence.interval_seconds)
    return next_run_at.isoformat()


def _recurrence_max_occurrences_reached(recurrence: TicketLoopRecurrencePolicy, occurrence_count: int) -> bool:
    return recurrence.max_occurrences is not None and occurrence_count >= recurrence.max_occurrences


def _persist_recurrence_after_enqueue(
    policy: TicketLoopPolicy,
    workspace: Path,
    next_run_at: str,
    now: datetime,
    occurrence_count: int,
) -> None:
    path = _policy_path(workspace)
    registry = _load_policy_registry(path)
    data = registry.get(policy.ticket_id) or policy.model_dump(mode="json")
    recurrence = data.get("recurrence") if isinstance(data.get("recurrence"), dict) else policy.recurrence.model_dump(mode="json")
    recurrence["next_run_at"] = next_run_at
    if _recurrence_max_occurrences_reached(policy.recurrence, occurrence_count):
        recurrence["enabled"] = False
    data.update(
        {
            "ticket_id": policy.ticket_id,
            "recurrence": recurrence,
            "updated_by_employee_id": policy.updated_by_employee_id or "clara",
            "updated_at": now.isoformat(),
        }
    )
    registry[policy.ticket_id] = data
    _write_policy_registry(path, registry)


def _source_ref_fragment(value: str) -> str:
    fragment = "".join(char if char.isalnum() else "-" for char in value.strip())
    return fragment.strip("-")[:80] or "due"


def _auto_propose_failure_retrospective_if_ready(item: TicketLoopQueueItem, workspace: Path) -> TicketLoopPolicyAction | None:
    if item.status.strip().lower() not in {"failed", "blocked"}:
        return None
    failed_items = [
        queue_item
        for queue_item in list_ticket_loop_queue(workspace_dir=workspace)
        if queue_item.ticket_id == item.ticket_id and queue_item.status.strip().lower() in {"failed", "blocked"}
    ]
    if len(failed_items) < QUEUE_FAILURE_RETROSPECTIVE_MIN_FAILED_ITEMS:
        return None
    try:
        from .asset_candidate_service import (
            TicketFailureRetrospectiveAssetCandidateRequest,
            propose_ticket_failure_retrospective_asset_candidates,
        )

        response = propose_ticket_failure_retrospective_asset_candidates(
            item.ticket_id,
            TicketFailureRetrospectiveAssetCandidateRequest(
                actor_employee_id=item.actor_employee_id or "clara",
                actor_role=item.actor_role or "AI Team OS Manager",
                reason="Ticket loop policy detected repeated failed or blocked queue work.",
                min_failed_items=QUEUE_FAILURE_RETROSPECTIVE_MIN_FAILED_ITEMS,
            ),
            workspace_dir=workspace,
        )
        return TicketLoopPolicyAction(
            kind="failure_retrospective_candidate",
            ticket_id=item.ticket_id,
            status=response.status,
            detail=response.detail,
            candidate_ids=[candidate.id for candidate in response.candidates],
            report_id=response.report_id,
        )
    except Exception as exc:  # pragma: no cover - pump should surface policy failures without losing queue state.
        return TicketLoopPolicyAction(
            kind="failure_retrospective_candidate",
            ticket_id=item.ticket_id,
            status="error",
            detail=str(exc),
        )


_QUEUE_WORKERS: dict[str, TicketLoopQueueWorker] = {}


def ticket_loop_queue_worker(*, workspace_dir: Path | None = None) -> TicketLoopQueueWorker:
    workspace = (workspace_dir or _workspace_dir()).resolve()
    key = str(workspace)
    worker = _QUEUE_WORKERS.get(key)
    if worker is None:
        worker = TicketLoopQueueWorker(workspace_dir=workspace)
        _QUEUE_WORKERS[key] = worker
    return worker


def ticket_loop_queue_worker_status(*, workspace_dir: Path | None = None) -> TicketLoopQueueWorkerStatus:
    return ticket_loop_queue_worker(workspace_dir=workspace_dir).status()


async def start_ticket_loop_queue_worker(
    request: TicketLoopQueueWorkerControlRequest | None = None,
    *,
    workspace_dir: Path | None = None,
) -> TicketLoopQueueWorkerStatus:
    return await ticket_loop_queue_worker(workspace_dir=workspace_dir).start(request)


async def stop_ticket_loop_queue_worker(
    *,
    workspace_dir: Path | None = None,
    reason: str = "Ticket loop queue worker stopped.",
) -> TicketLoopQueueWorkerStatus:
    return await ticket_loop_queue_worker(workspace_dir=workspace_dir).stop(reason)


async def tick_ticket_loop_queue_worker(
    request: TicketLoopQueueWorkerControlRequest | None = None,
    *,
    workspace_dir: Path | None = None,
) -> TicketLoopQueueWorkerTickResponse:
    return await ticket_loop_queue_worker(workspace_dir=workspace_dir).tick(request)


def _policy_path(workspace_dir: Path) -> Path:
    workspace = workspace_dir.resolve()
    return workspace / "ticket_loop_policies.json"


def _control_path(workspace_dir: Path) -> Path:
    workspace = workspace_dir.resolve()
    return workspace / "ticket_loop_controls.json"


def _run_path(workspace_dir: Path) -> Path:
    workspace = workspace_dir.resolve()
    return workspace / "ticket_loop_runs.json"


def _queue_path(workspace_dir: Path) -> Path:
    workspace = workspace_dir.resolve()
    return workspace / "ticket_loop_queue.json"


def _worker_path(workspace_dir: Path) -> Path:
    workspace = workspace_dir.resolve()
    return workspace / "ticket_loop_queue_worker.json"


def _load_policy_registry(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    tickets = payload.get("tickets") if isinstance(payload, dict) else {}
    if not isinstance(tickets, dict):
        return {}
    return {str(key): value for key, value in tickets.items() if isinstance(value, dict)}


def _write_policy_registry(path: Path, registry: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"tickets": registry}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_control_registry(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    tickets = payload.get("tickets") if isinstance(payload, dict) else {}
    if not isinstance(tickets, dict):
        return {}
    return {str(key): value for key, value in tickets.items() if isinstance(value, dict)}


def _write_control_registry(path: Path, registry: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"tickets": registry}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _latest_control_state(path: Path, ticket_id: str) -> TicketLoopControlState | None:
    state = _load_control_registry(path).get(ticket_id, {}).get("state")
    if not isinstance(state, dict):
        return None
    try:
        return TicketLoopControlState.model_validate(state)
    except ValueError:
        return None


def _load_run_registry(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    runs = payload.get("runs") if isinstance(payload, dict) else {}
    if not isinstance(runs, dict):
        return {}
    return {str(key): value for key, value in runs.items() if isinstance(value, dict)}


def _write_run_registry(path: Path, registry: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"runs": registry}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _upsert_loop_run_record(workspace_dir: Path, record: TicketLoopRunRecord) -> None:
    path = _run_path(workspace_dir)
    registry = _load_run_registry(path)
    registry[record.run_id] = record.model_copy(update={"saved_path": _relative(path)}).model_dump(mode="json")
    _write_run_registry(path, registry)


def _run_record_from_payload(payload: dict[str, Any], path: Path) -> TicketLoopRunRecord:
    return TicketLoopRunRecord.model_validate({**payload, "saved_path": _relative(path)})


def _load_queue_registry(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    items = payload.get("items") if isinstance(payload, dict) else {}
    if not isinstance(items, dict):
        return {}
    return {str(key): value for key, value in items.items() if isinstance(value, dict)}


def _write_queue_registry(path: Path, registry: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"items": registry}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _queue_item_from_payload(payload: dict[str, Any], path: Path) -> TicketLoopQueueItem:
    return TicketLoopQueueItem.model_validate({**payload, "saved_path": _relative(path)})


def _load_worker_state(path: Path) -> TicketLoopQueueWorkerStatus | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    worker = payload.get("worker") if isinstance(payload, dict) else {}
    if not isinstance(worker, dict):
        return None
    try:
        return TicketLoopQueueWorkerStatus.model_validate({**worker, "saved_path": _relative(path)})
    except ValueError:
        return None


def _write_worker_state(path: Path, state: TicketLoopQueueWorkerStatus) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"worker": state.model_dump(mode="json")}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _control_status(action: str) -> str:
    return {
        "stop": "stopped",
        "pause": "paused",
        "cancel": "cancelled",
        "continue": "ready_to_continue",
    }.get(action, action)


def _workspace_root_from_workspace(workspace_dir: Path) -> Path:
    workspace = workspace_dir.resolve()
    return workspace.parent if workspace.name == ".aiteamos" else workspace


def _timeline_approvals(root: Path, ticket_id: str) -> list[Any]:
    try:
        from .execution_approval_service import list_execution_approvals

        return [approval for approval in list_execution_approvals(workspace_dir=root) if approval.ticket_id == ticket_id]
    except Exception:
        return []


def _timeline_sessions(workspace: Path, ticket_id: str) -> dict[str, dict[str, Any]]:
    try:
        from .execution_session_store import load_execution_sessions

        sessions = load_execution_sessions(workspace)
    except Exception:
        return {}
    return {
        key: session
        for key, session in sessions.items()
        if isinstance(session, dict) and str(session.get("ticket_id") or "") == ticket_id
    }


def _timeline_ref(
    kind: str,
    ref: str,
    *,
    ticket_id: str = "",
    report_id: str = "",
    evidence_index: int | None = None,
) -> TicketLoopTimelineRef:
    normalized_kind = str(kind or "").strip()
    normalized_ref = str(ref or "").strip()
    return TicketLoopTimelineRef(
        kind=normalized_kind,
        ref=normalized_ref,
        target_route=_timeline_target_route(
            normalized_kind,
            normalized_ref,
            ticket_id=ticket_id,
            report_id=report_id,
            evidence_index=evidence_index,
        ),
    )


def _timeline_target_route(
    kind: str,
    ref: str,
    *,
    ticket_id: str = "",
    report_id: str = "",
    evidence_index: int | None = None,
) -> str:
    if not ref:
        return ""
    if kind == "runtime_session":
        return f"runtime/{ref}"
    if kind == "asset":
        return f"assets/asset/{ref}"
    if kind == "approval":
        return f"assets/review/approval:{ref}"
    if kind == "report" and ticket_id and report_id:
        return _report_target_route(ticket_id, report_id)
    if kind == "evidence" and ticket_id and report_id and evidence_index is not None:
        return _evidence_target_route(ticket_id, report_id, evidence_index)
    return ""


def _report_target_route(ticket_id: str, report_id: str) -> str:
    if not ticket_id or not report_id:
        return ""
    return f"tickets/reports/{ticket_id}::report::{report_id}"


def _evidence_target_route(ticket_id: str, report_id: str, evidence_index: int) -> str:
    if not ticket_id or not report_id:
        return ""
    return f"tickets/reports/{ticket_id}::evidence::{report_id}::{evidence_index}"


def _timeline_event_detail(event_type: str, data: dict[str, Any]) -> str:
    if event_type == "status_changed":
        return f"{str(data.get('from') or '-')} -> {str(data.get('to') or data.get('status') or '-')}"
    if event_type == "assigned":
        return f"Assigned to {str(data.get('assigned_employee_id') or data.get('assigned_role') or '-')}"
    if event_type == "handoff_requested":
        return (
            f"{str(data.get('from_employee_id') or data.get('from_role') or '-')} -> "
            f"{str(data.get('to_employee_id') or data.get('to_role') or '-')}"
        )
    if event_type == "validation_requested":
        return f"Validation requested from {str(data.get('validation_employee_id') or data.get('validation_role') or '-')}"
    if event_type in {"reported", "validated", "blocked"}:
        report = data.get("report") if isinstance(data.get("report"), dict) else {}
        return str(report.get("content") or event_type)
    return str(data.get("detail") or data.get("title") or event_type)


def _timeline_refs_from_event(data: dict[str, Any]) -> list[TicketLoopTimelineRef]:
    refs: list[TicketLoopTimelineRef] = []
    for key, kind in (
        ("source_run_id", "run"),
        ("target_ref", "asset"),
        ("assigned_employee_id", "employee"),
        ("to_employee_id", "employee"),
        ("validation_employee_id", "employee"),
    ):
        value = str(data.get(key) or "").strip()
        if value:
            refs.append(_timeline_ref(kind, value))
    return refs


def _ensure_retry_prerequisites(ticket: Any, request: TicketLoopResumeRequest, current_status: str, workspace: Path) -> None:
    if current_status not in {"waiting_changes", "waiting_evidence"}:
        return
    expected_action = "retry_after_changes" if current_status == "waiting_changes" else "retry_after_evidence"
    if request.action != expected_action:
        raise ValueError(f"Ticket status {current_status} requires action {expected_action}.")
    approval_status = "changes_requested" if current_status == "waiting_changes" else "evidence_requested"
    approval = _latest_approval_with_status(_workspace_root_from_workspace(workspace), str(getattr(ticket, "id", "") or ""), approval_status)
    if approval is None:
        raise ValueError(f"Ticket retry requires a prior approval review with status {approval_status}.")
    reviewed_at = str(getattr(approval, "reviewed_at", "") or getattr(approval, "updated_at", "") or getattr(approval, "created_at", "") or "")
    approval_id = str(getattr(approval, "id", "") or "")
    reports = list(getattr(ticket, "reports", []) or [])
    if current_status == "waiting_changes":
        if not _has_new_report_after_review(reports, reviewed_at, approval_id):
            raise ValueError("Ticket retry_after_changes requires a new Ticket report after the change request review.")
        return
    if not _has_new_evidence_after_review(reports, reviewed_at, approval_id):
        raise ValueError("Ticket retry_after_evidence requires new Ticket evidence after the evidence request review.")


def _latest_approval_with_status(root: Path, ticket_id: str, status: str) -> Any | None:
    approvals = [
        approval
        for approval in _timeline_approvals(root, ticket_id)
        if str(getattr(approval, "status", "") or "").strip().lower() == status
    ]
    if not approvals:
        return None
    return sorted(
        approvals,
        key=lambda item: str(getattr(item, "reviewed_at", "") or getattr(item, "updated_at", "") or getattr(item, "created_at", "") or ""),
        reverse=True,
    )[0]


def _report_after_review(report: Any, reviewed_at: str, approval_id: str) -> bool:
    report_type = str(getattr(report, "report_type", "") or "").strip().lower()
    if report_type.startswith("approval_"):
        return False
    source_run_id = str(getattr(report, "source_run_id", "") or "")
    if approval_id and source_run_id == approval_id:
        return False
    created_at = str(getattr(report, "created_at", "") or "")
    return not reviewed_at or not created_at or created_at > reviewed_at


def _new_reports_after_review(reports: list[Any], reviewed_at: str, approval_id: str) -> list[Any]:
    return [report for report in reports if _report_after_review(report, reviewed_at, approval_id)]


def _new_evidence_reports_after_review(reports: list[Any], reviewed_at: str, approval_id: str) -> list[Any]:
    return [
        report
        for report in reports
        if _report_after_review(report, reviewed_at, approval_id) and bool(getattr(report, "evidence", []) or [])
    ]


def _has_new_report_after_review(reports: list[Any], reviewed_at: str, approval_id: str) -> bool:
    return bool(_new_reports_after_review(reports, reviewed_at, approval_id))


def _has_new_evidence_after_review(reports: list[Any], reviewed_at: str, approval_id: str) -> bool:
    return bool(_new_evidence_reports_after_review(reports, reviewed_at, approval_id))


def _retry_requirements(ticket: Any, status: str, workspace: Path) -> list[TicketLoopRetryRequirement]:
    if status not in {"waiting_changes", "waiting_evidence"}:
        return []
    ticket_id = str(getattr(ticket, "id", "") or "")
    approval_status = "changes_requested" if status == "waiting_changes" else "evidence_requested"
    approval = _latest_approval_with_status(_workspace_root_from_workspace(workspace), ticket_id, approval_status)
    approval_id = str(getattr(approval, "id", "") or "") if approval is not None else ""
    executor_id = str(getattr(approval, "executor_id", "") or "") if approval is not None else ""
    reviewed_at = str(getattr(approval, "reviewed_at", "") or getattr(approval, "updated_at", "") or getattr(approval, "created_at", "") or "") if approval is not None else ""
    reports = list(getattr(ticket, "reports", []) or [])
    new_reports = _new_reports_after_review(reports, reviewed_at, approval_id) if approval is not None else []
    new_evidence_reports = _new_evidence_reports_after_review(reports, reviewed_at, approval_id) if approval is not None else []
    approval_route = f"assets/review/runtime-approval:{executor_id}:{approval_id}" if executor_id and approval_id else ""
    requirements = [
        TicketLoopRetryRequirement(
            id=f"latest_{approval_status}_review",
            label="Review recorded",
            satisfied=approval is not None,
            detail=f"Latest runtime approval review status: {approval_status}." if approval is not None else f"Missing runtime approval review status: {approval_status}.",
            target_route=approval_route,
        )
    ]
    if status == "waiting_changes":
        latest_report = sorted(new_reports, key=lambda item: str(getattr(item, "created_at", "") or ""), reverse=True)[0] if new_reports else None
        latest_report_id = str(getattr(latest_report, "id", "") or "") if latest_report is not None else ""
        requirements.append(
            TicketLoopRetryRequirement(
                id="new_report_after_changes_review",
                label="New report after review",
                satisfied=bool(new_reports),
                detail="A non-approval Ticket report was attached after the reviewer requested changes.",
                target_route=_report_target_route(ticket_id, latest_report_id) if latest_report_id else f"tickets/reports/{ticket_id}",
            )
        )
    else:
        latest_evidence_report = sorted(new_evidence_reports, key=lambda item: str(getattr(item, "created_at", "") or ""), reverse=True)[0] if new_evidence_reports else None
        latest_report_id = str(getattr(latest_evidence_report, "id", "") or "") if latest_evidence_report is not None else ""
        requirements.append(
            TicketLoopRetryRequirement(
                id="new_evidence_after_review",
                label="New evidence after review",
                satisfied=bool(new_evidence_reports),
                detail="A non-approval Ticket evidence ref was attached after the reviewer requested more evidence.",
                target_route=_report_target_route(ticket_id, latest_report_id) if latest_report_id else f"tickets/reports/{ticket_id}",
            )
        )
    return requirements


def _approval_resume_states(ticket: Any, workspace: Path) -> list[TicketLoopApprovalResumeState]:
    ticket_id = str(getattr(ticket, "id", "") or "")
    states: list[TicketLoopApprovalResumeState] = []
    for approval in _timeline_approvals(_workspace_root_from_workspace(workspace), ticket_id):
        approval_id = str(getattr(approval, "id", "") or "")
        executor_id = str(getattr(approval, "executor_id", "") or "")
        status = str(getattr(approval, "status", "") or "")
        last_run_status = str(getattr(approval, "last_run_status", "") or "")
        last_ingestion_blocker = str(getattr(approval, "last_ingestion_blocker", "") or "")
        run_history = getattr(approval, "run_history", []) or []
        ready_to_run = status == "approved" and not last_run_status
        needs_review = status == "requested"
        blocked = bool(last_ingestion_blocker) or last_run_status in {"blocked", "failed"}
        detail = "Runtime approval is ready to run from the approval review surface."
        if needs_review:
            detail = "Runtime approval needs review before LangGraph can resume the approved runtime path."
        elif status in {"changes_requested", "evidence_requested", "rejected"}:
            detail = f"Runtime approval review status is {status}; follow the Ticket next action before runtime resume."
        elif blocked:
            detail = last_ingestion_blocker or f"Last approved runtime run ended with status {last_run_status}."
        elif last_run_status:
            detail = f"Last approved runtime run ended with status {last_run_status}."
        states.append(
            TicketLoopApprovalResumeState(
                approval_id=approval_id,
                executor_id=executor_id,
                status=status,
                required_capability=str(getattr(approval, "required_capability", "") or ""),
                ready_to_run=ready_to_run,
                needs_review=needs_review,
                blocked=blocked,
                reviewed_at=str(getattr(approval, "reviewed_at", "") or ""),
                last_run_request_id=str(getattr(approval, "last_run_request_id", "") or ""),
                last_run_status=last_run_status,
                last_ingestion_blocker=last_ingestion_blocker,
                attempt_count=len(run_history) if isinstance(run_history, list) else 0,
                target_route=f"assets/review/runtime-approval:{executor_id}:{approval_id}" if executor_id and approval_id else "",
                detail=detail,
            )
        )
    return sorted(states, key=lambda item: item.reviewed_at or item.approval_id, reverse=True)


def _queue_reliability(ticket: Any, workspace: Path) -> TicketLoopQueueReliability:
    ticket_id = str(getattr(ticket, "id", "") or "")
    items = [item for item in list_ticket_loop_queue(workspace_dir=workspace) if item.ticket_id == ticket_id]
    counts = {
        "queued": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "active": 0,
    }
    latest_activity_at = ""
    stale_running_count = 0
    now = datetime.now(UTC)
    for item in items:
        normalized = item.status.strip().lower()
        if normalized == "queued":
            counts["queued"] += 1
        elif normalized == "running":
            counts["running"] += 1
            started_at = _parse_datetime(item.started_at or item.updated_at or item.enqueued_at)
            if started_at is not None and (now - started_at).total_seconds() >= QUEUE_STALE_RUNNING_SECONDS:
                stale_running_count += 1
        elif normalized in {"completed", "partial", "needs_approval"}:
            counts["completed"] += 1
        elif normalized in {"failed", "blocked"}:
            counts["failed"] += 1
        if normalized in {"queued", "running"}:
            counts["active"] += 1
        activity_at = item.updated_at or item.finished_at or item.started_at or item.enqueued_at
        if activity_at and (not latest_activity_at or activity_at > latest_activity_at):
            latest_activity_at = activity_at
    worker_status = ticket_loop_queue_worker_status(workspace_dir=workspace)
    duplicate_queued_count = max(counts["queued"] - 1, 0)
    status = "idle"
    detail = "No queued loop work is currently attached to this Ticket."
    if counts["failed"] or worker_status.last_error:
        status = "error"
        detail = worker_status.last_error or "At least one queued loop item failed."
    elif stale_running_count:
        status = "stale_running"
        detail = "At least one running loop item has exceeded the stale-running threshold."
    elif duplicate_queued_count:
        status = "duplicate_queued"
        detail = "This Ticket has multiple queued loop items; review duplicates before starting the worker."
    elif counts["queued"] and not worker_status.running:
        status = "waiting_worker"
        detail = "This Ticket has queued loop work but the queue worker is not running."
    elif counts["queued"] or counts["running"]:
        status = "active"
        detail = "This Ticket has active governed loop queue work."
    elif counts["completed"]:
        status = "ready"
        detail = "Recent governed loop queue work completed for this Ticket."
    return TicketLoopQueueReliability(
        ticket_id=ticket_id,
        status=status,
        detail=detail,
        queued_count=counts["queued"],
        duplicate_queued_count=duplicate_queued_count,
        running_count=counts["running"],
        stale_running_count=stale_running_count,
        stale_running_after_seconds=QUEUE_STALE_RUNNING_SECONDS,
        completed_count=counts["completed"],
        failed_count=counts["failed"],
        active_count=counts["active"],
        total_count=len(items),
        latest_activity_at=latest_activity_at,
        worker_status=worker_status.status,
        worker_running=worker_status.running,
        worker_last_error=worker_status.last_error,
    )


def _policy_status(ticket: Any, workspace: Path) -> TicketLoopPolicyStatus:
    ticket_id = str(getattr(ticket, "id", "") or "")
    policy = ticket_loop_policy(ticket_id, workspace_dir=workspace)
    sla_configured = bool(policy.sla.response_due_seconds or policy.sla.review_due_seconds)
    recurrence_configured = bool(policy.recurrence.enabled or policy.recurrence.next_run_at)
    closeout_configured = bool(
        policy.closeout.auto_propose_assets
        or policy.closeout.auto_settle_assets
        or policy.closeout.auto_approve_candidates
        or policy.closeout.project_graphiti
        or policy.closeout.project_relationships
        or policy.closeout.asset_types
    )
    return TicketLoopPolicyStatus(
        ticket_id=ticket_id,
        source=policy.source,
        validation_required=policy.validation_required,
        sla=policy.sla,
        recurrence=policy.recurrence,
        closeout=policy.closeout,
        configured={
            "sla": sla_configured,
            "recurrence": recurrence_configured,
            "closeout": closeout_configured,
        },
        saved_path=policy.saved_path,
    )


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _timeline_summary(ticket: Any, items: list[TicketLoopTimelineItem], workspace: Path) -> TicketLoopTimelineSummary:
    status = str(getattr(ticket, "status", "") or "").strip().lower()
    counts: dict[str, int] = {}
    provider_blockers: list[dict[str, Any]] = []
    latest_at = ""
    for item in items:
        counts[item.kind] = counts.get(item.kind, 0) + 1
        if item.at and (not latest_at or item.at > latest_at):
            latest_at = item.at
        if item.kind == "ticket_report" and item.status in {"loop_state_transition_blocked", "loop_resume_blocked"}:
            provider_blockers.append(
                {
                    "source_ref": item.source_ref,
                    "status": item.status,
                    "detail": item.detail[:500],
                    "at": item.at,
                }
            )
    waiting_reason = {
        "waiting_approval": "Approval review is required before the Ticket loop can continue.",
        "ready_to_resume": "Approval was granted; the Ticket loop can be resumed through the governed queue.",
        "waiting_changes": "A reviewer requested changes before this Ticket loop can retry.",
        "waiting_evidence": "A reviewer requested more evidence before this Ticket loop can retry.",
        "waiting_validation": "PV validation is required before closeout.",
        "blocked": "The Ticket is blocked and needs Clara or human intervention.",
        "failed": "The latest Ticket loop attempt failed and needs inspection.",
    }.get(status, "")
    next_action = {
        "waiting_approval": "Review the pending approval request.",
        "ready_to_resume": "Resume the governed Ticket loop.",
        "waiting_changes": "Attach requested changes, then retry the governed loop.",
        "waiting_evidence": "Attach evidence, then retry the governed loop.",
        "waiting_validation": "Ask the validator to record a validation result.",
        "blocked": "Unblock the Ticket or request a safer plan.",
        "failed": "Inspect runtime replay, then retry or hand off.",
    }.get(status, "Continue normal Ticket execution.")
    can_resume = status in {"ready_to_resume", "waiting_changes", "waiting_evidence"}
    can_retry = status in {"waiting_changes", "waiting_evidence", "blocked", "failed"}
    can_run = status not in {*TERMINAL_TICKET_STATUSES, "waiting_approval", "waiting_validation"}
    return TicketLoopTimelineSummary(
        ticket_id=str(getattr(ticket, "id", "") or ""),
        status=status,
        waiting_reason=waiting_reason,
        next_action=next_action,
        can_run=can_run,
        can_resume=can_resume,
        can_retry=can_retry,
        latest_at=latest_at,
        counts=counts,
        provider_blockers=provider_blockers,
        retry_requirements=_retry_requirements(ticket, status, workspace),
        approval_resume=_approval_resume_states(ticket, workspace),
        queue_reliability=_queue_reliability(ticket, workspace),
        policy=_policy_status(ticket, workspace),
    )


def _record_approval_ticket_status_blocker(
    approval_record: Any,
    *,
    target_status: str,
    detail: str,
    workspace_dir: Path | None = None,
) -> str:
    del workspace_dir
    ticket_id = str(getattr(approval_record, "ticket_id", "") or "").strip()
    if not ticket_id:
        return ""
    approval_id = str(getattr(approval_record, "id", "") or "").strip()
    content = "\n".join(
        line
        for line in [
            "Ticket loop state transition was blocked after runtime approval review.",
            f"Approval: {approval_id or '-'}; review status: {str(getattr(approval_record, 'status', '') or '-')}.",
            f"Target Ticket status: {target_status}.",
            f"Provider blocker: {detail or 'Unknown provider error.'}",
        ]
        if line
    )
    evidence = [
        ref
        for ref in [
            str(getattr(approval_record, "checkpoint_ref", "") or ""),
            str(getattr(approval_record, "source_state_ref", "") or ""),
        ]
        if ref
    ]
    try:
        updated = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=str(getattr(approval_record, "reviewer_employee_id", "") or "clara"),
                reporter_role="AI Team OS Manager",
                content=content,
                evidence=evidence,
                report_type="loop_state_transition_blocked",
                source_run_id=approval_id,
            ),
        )
    except Exception:
        return ""
    return updated.reports[-1].id if updated.reports else ""


def _merge_policy(policy: TicketLoopPolicy, payload: dict[str, Any], *, source: str) -> TicketLoopPolicy:
    data = policy.model_dump(mode="json")
    for key in (
        "max_steps",
        "max_runtime_seconds",
        "stop_statuses",
        "allowed_capabilities",
        "approval_requirements",
        "validation_required",
        "sla",
        "recurrence",
        "closeout",
        "updated_by_employee_id",
        "updated_at",
    ):
        if key in payload:
            data[key] = payload[key]
    data["source"] = source
    return TicketLoopPolicy.model_validate(data)


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_workspace_root()))
    except ValueError:
        return str(path)


def _employee_profiles() -> list[dict[str, Any]]:
    return load_employee_profiles(workspace_root=_workspace_root())


def _select_employee_profile(profiles: list[dict[str, Any]], employee_id: str) -> dict[str, Any]:
    normalized = employee_id.strip().lower()
    return next((profile for profile in profiles if str(profile.get("id") or "").strip().lower() == normalized), {"id": employee_id, "display_name": employee_id, "role": "AI Employee"})


def _loop_step(step_request: TicketLoopStepRequest) -> int:
    raw_value = step_request.runtime_config.get("loop_step", step_request.budget.get("loop_step", 1))
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return 1
