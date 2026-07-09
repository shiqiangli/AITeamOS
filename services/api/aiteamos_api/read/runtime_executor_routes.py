"""Runtime executor diagnostics routes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .execution_dispatch_service import ExecutionDispatchService
from .execution_replay_service import ExecutionReplayService
from .execution_session_store import load_execution_sessions
from .live_provider_dogfood_service import (
    LiveProviderDogfoodRequest,
    LiveProviderDogfoodService,
    live_provider_readiness_projection,
)
from .runtime_executor_config_service import (
    RuntimeExecutorConfigListResponse,
    RuntimeExecutorConfigRecord,
    RuntimeExecutorConfigUpdateRequest,
    get_runtime_executor_config,
    list_runtime_executor_configs,
    update_runtime_executor_config,
)
from .execution_approval_service import (
    ExecutionApprovalRecord,
    ExecutionApprovalReviewRequest,
    ExecutionApprovalRunRequest,
    ExecutionApprovalRunResponse,
    ExecutionApprovalRunService,
    list_execution_approvals,
    review_execution_approval,
)
from .runtime_executor_smoke_service import (
    RuntimeExecutorDogfoodRequest,
    RuntimeExecutorDogfoodResponse,
    RuntimeExecutorSmokeBatchRequest,
    RuntimeExecutorSmokeBatchResponse,
    RuntimeExecutorSmokeRequest,
    RuntimeExecutorSmokeResponse,
    RuntimeExecutorSmokeService,
)

router = APIRouter(prefix="/api/v1/runtime-executors", tags=["runtime-executors"])


class RuntimeExecutorRegistryItem(BaseModel):
    executor_id: str
    display_name: str
    status: str
    detail: str = ""
    capabilities: list[str] = Field(default_factory=list)
    setup_required: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    health: dict[str, Any] = Field(default_factory=dict)


class RuntimeExecutorRegistryResponse(BaseModel):
    executors: list[RuntimeExecutorRegistryItem] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    live_provider_readiness: dict[str, Any] = Field(default_factory=dict)


class RuntimeExecutionSessionRecord(BaseModel):
    session_key: str
    employee_id: str = ""
    thread_id: str = ""
    ticket_id: str = ""
    executor_id: str = ""
    executor_session_ref: str = ""
    checkpoint_ref: str = ""
    last_request_id: str = ""
    status: str = ""
    trace_ref: str = ""
    current_graph_node: str = ""
    source_state_ref: str = ""
    tool_event_count: int = 0
    tool_events: list[dict[str, Any]] = Field(default_factory=list)
    ticket_refs: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    context_refs: list[dict[str, Any]] = Field(default_factory=list)
    approval_refs: list[str] = Field(default_factory=list)
    updated_at: str = ""


class RuntimeExecutionReplayResponse(BaseModel):
    session: dict[str, Any] = Field(default_factory=dict)
    execution_artifacts: dict[str, Any] = Field(default_factory=dict)
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    state_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    native_checkpoint_history: list[dict[str, Any]] = Field(default_factory=list)
    state_transitions: list[dict[str, Any]] = Field(default_factory=list)
    trace_events: list[dict[str, Any]] = Field(default_factory=list)
    handoff_summary: dict[str, Any] = Field(default_factory=dict)
    coverage_summary: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeExecutionTimelineResponse(BaseModel):
    session: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)


def _runtime_setup_required(executor_status: dict[str, Any]) -> list[str]:
    missing_env = executor_status.get("missing_env")
    if isinstance(missing_env, list) and missing_env:
        return [str(item).strip() for item in missing_env if str(item).strip()]
    configured = executor_status.get("configured")
    if not isinstance(configured, dict):
        return []
    return [
        str(key).replace("_", " ")
        for key, value in configured.items()
        if value is False
    ][:8]


def _runtime_diagnostics(executor_status: dict[str, Any]) -> dict[str, Any]:
    executor_id = str(executor_status.get("executor_id") or "runtime_executor").strip()
    capabilities = executor_status.get("capabilities")
    capability_list = capabilities if isinstance(capabilities, list) else []
    diagnostics: dict[str, Any] = {
        "smoke": {
            "endpoint": f"/api/v1/runtime-executors/{executor_id}/smoke",
            "method": "POST",
            "mode": "non_destructive_inspect_and_report",
            "ingest_requires_ticket": True,
            "dispatch_boundary": "RuntimeExecutor",
        }
    }
    if "repo:write" in capability_list:
        diagnostics["mutation_guard"] = {
            "required": ["ticket_bound", "approval_bound", "evidence_bound"],
            "approval_endpoint": f"/api/v1/runtime-executors/{executor_id}/approvals",
            "run_endpoint": f"/api/v1/runtime-executors/{executor_id}/approvals/{{approval_id}}/run",
        }
    return diagnostics


@router.get("", response_model=RuntimeExecutorRegistryResponse)
async def list_runtime_executors() -> RuntimeExecutorRegistryResponse:
    """List RuntimeExecutor adapters, capabilities, health, and setup blockers."""

    items: list[RuntimeExecutorRegistryItem] = []
    blockers: list[dict[str, Any]] = []
    ready_count = 0
    service = ExecutionDispatchService()
    try:
        live_readiness = live_provider_readiness_projection(
            await LiveProviderDogfoodService().readiness(LiveProviderDogfoodRequest(execute=True))
        )
        for executor in service.executors.values():
            health = await executor.health()
            status = str(health.get("status") or "unknown")
            setup_required = _runtime_setup_required(health)
            item = RuntimeExecutorRegistryItem(
                executor_id=str(health.get("executor_id") or executor.id),
                display_name=str(health.get("display_name") or executor.display_name),
                status=status,
                detail=str(health.get("detail") or ""),
                capabilities=[str(item) for item in health.get("capabilities", sorted(executor.capabilities))],
                setup_required=setup_required,
                diagnostics=_runtime_diagnostics(health),
                health=health,
            )
            items.append(item)
            if status == "ready":
                ready_count += 1
            elif status != "unknown":
                blockers.append(
                    {
                        "executor_id": item.executor_id,
                        "status": status,
                        "detail": item.detail or "Runtime executor setup is incomplete.",
                        "setup_required": setup_required,
                    }
                )
    finally:
        await service.aclose()

    return RuntimeExecutorRegistryResponse(
        executors=items,
        blockers=blockers,
        summary={
            "executor_count": len(items),
            "ready_count": ready_count,
            "blocked_count": len(blockers),
            "runtime_boundary": "RuntimeExecutor",
            "live_provider_status": live_readiness.get("status"),
            "live_provider_blocker_count": live_readiness.get("summary", {}).get("blocker_count")
            if isinstance(live_readiness.get("summary"), dict)
            else None,
        },
        live_provider_readiness=live_readiness,
    )


@router.get("/config", response_model=RuntimeExecutorConfigListResponse)
async def list_runtime_executor_config_records() -> RuntimeExecutorConfigListResponse:
    """List saved non-sensitive RuntimeExecutor adapter configuration."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    return list_runtime_executor_configs(workspace_dir=workspace_dir)


@router.get("/approvals", response_model=list[ExecutionApprovalRecord])
async def list_runtime_approval_queue(status: str = "") -> list[ExecutionApprovalRecord]:
    """List governed runtime approval records across executors."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    return list_execution_approvals(workspace_dir=workspace_dir, status=status)


@router.get("/sessions", response_model=list[RuntimeExecutionSessionRecord])
async def list_runtime_execution_sessions(executor_id: str = "", status: str = "") -> list[RuntimeExecutionSessionRecord]:
    """List execution sessions with checkpoint and replay references."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    normalized_executor_id = executor_id.strip().replace("-", "_")
    normalized_status = status.strip().lower()
    records: list[RuntimeExecutionSessionRecord] = []
    for key, item in load_execution_sessions(workspace_dir).items():
        if normalized_executor_id and item.get("executor_id") != normalized_executor_id:
            continue
        if normalized_status and str(item.get("status") or "").lower() != normalized_status:
            continue
        records.append(RuntimeExecutionSessionRecord.model_validate({"session_key": key, **item}))
    return sorted(records, key=lambda item: item.updated_at, reverse=True)


@router.get("/sessions/{session_key}", response_model=RuntimeExecutionReplayResponse)
async def get_runtime_execution_session_replay(session_key: str) -> RuntimeExecutionReplayResponse:
    """Return a redacted replay view for one execution session."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    try:
        replay = ExecutionReplayService(workspace_dir=workspace_dir).session_replay(session_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Execution session was not found: {session_key}") from exc
    return RuntimeExecutionReplayResponse.model_validate(replay)


@router.get("/sessions/{session_key}/timeline", response_model=RuntimeExecutionTimelineResponse)
async def get_runtime_execution_session_timeline(session_key: str) -> RuntimeExecutionTimelineResponse:
    """Return the compact replay timeline for one execution session."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    try:
        timeline = ExecutionReplayService(workspace_dir=workspace_dir).session_timeline(session_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Execution session was not found: {session_key}") from exc
    return RuntimeExecutionTimelineResponse.model_validate(timeline)


@router.get("/{executor_id}/config", response_model=RuntimeExecutorConfigRecord)
async def get_runtime_executor_config_record(executor_id: str) -> RuntimeExecutorConfigRecord:
    """Get saved non-sensitive RuntimeExecutor adapter configuration."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    normalized = executor_id.strip().replace("-", "_")
    if normalized not in ExecutionDispatchService().executors:
        raise HTTPException(status_code=404, detail=f"Runtime executor is not registered: {normalized}")
    return get_runtime_executor_config(normalized, workspace_dir=workspace_dir)


@router.put("/{executor_id}/config", response_model=RuntimeExecutorConfigRecord)
async def update_runtime_executor_config_record(
    executor_id: str,
    request: RuntimeExecutorConfigUpdateRequest,
) -> RuntimeExecutorConfigRecord:
    """Save non-sensitive RuntimeExecutor adapter configuration."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    normalized = executor_id.strip().replace("-", "_")
    if normalized not in ExecutionDispatchService().executors:
        raise HTTPException(status_code=404, detail=f"Runtime executor is not registered: {normalized}")
    return update_runtime_executor_config(normalized, request, workspace_dir=workspace_dir)


@router.post("/smoke-batch", response_model=RuntimeExecutorSmokeBatchResponse)
async def smoke_runtime_executor_batch(request: RuntimeExecutorSmokeBatchRequest) -> RuntimeExecutorSmokeBatchResponse:
    """Run a governed non-destructive smoke batch across RuntimeExecutors."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    return await RuntimeExecutorSmokeService(workspace_dir=workspace_dir).smoke_batch(request)


@router.post("/dogfood", response_model=RuntimeExecutorDogfoodResponse)
async def dogfood_runtime_executor(request: RuntimeExecutorDogfoodRequest) -> RuntimeExecutorDogfoodResponse:
    """Run a Ticket-bound RuntimeExecutor dogfood harness through governance services."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    return await RuntimeExecutorSmokeService(workspace_dir=workspace_dir).dogfood(request)


@router.post("/{executor_id}/smoke", response_model=RuntimeExecutorSmokeResponse)
async def smoke_runtime_executor(executor_id: str, request: RuntimeExecutorSmokeRequest) -> RuntimeExecutorSmokeResponse:
    """Run a non-destructive inspect-and-report smoke diagnostic for one executor."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    return await RuntimeExecutorSmokeService(workspace_dir=workspace_dir).smoke(executor_id, request)


@router.get("/{executor_id}/approvals", response_model=list[ExecutionApprovalRecord])
async def list_runtime_executor_approvals(executor_id: str, status: str = "") -> list[ExecutionApprovalRecord]:
    """List governed approval records for one runtime executor."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    normalized = executor_id.strip().replace("-", "_")
    return [
        approval
        for approval in list_execution_approvals(workspace_dir=workspace_dir, status=status)
        if approval.executor_id == normalized
    ]


@router.post("/{executor_id}/approvals/{approval_id}/review", response_model=ExecutionApprovalRecord)
async def review_runtime_executor_approval(
    executor_id: str,
    approval_id: str,
    request: ExecutionApprovalReviewRequest,
) -> ExecutionApprovalRecord:
    """Approve or reject a runtime executor approval request."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    try:
        approval = review_execution_approval(workspace_dir=workspace_dir, approval_id=approval_id, review=request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Execution approval was not found: {approval_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized = executor_id.strip().replace("-", "_")
    if approval.executor_id != normalized:
        raise HTTPException(status_code=409, detail=f"Approval {approval_id} belongs to executor {approval.executor_id}, not {normalized}.")
    return approval


@router.post("/{executor_id}/approvals/{approval_id}/run", response_model=ExecutionApprovalRunResponse)
async def run_approved_runtime_executor(
    executor_id: str,
    approval_id: str,
    request: ExecutionApprovalRunRequest,
) -> ExecutionApprovalRunResponse:
    """Run an approved external runtime request through RuntimeExecutor dispatch."""

    workspace_dir = Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".aiteamos")).resolve()
    return await ExecutionApprovalRunService(workspace_dir=workspace_dir).run(executor_id, approval_id, request)
