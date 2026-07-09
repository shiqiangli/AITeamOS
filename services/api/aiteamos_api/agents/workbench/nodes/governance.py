"""Governance nodes for the AITeamOS Workbench graph."""

import asyncio
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from langchain_core.runnables.config import RunnableConfig

from aiteamos_api.agents.workbench.state import (
    AITeamOSWorkbenchState,
    configurable,
    latest_human_text,
    record,
    records,
    text,
)
from aiteamos_api.read.chat_action_plan import ChatActionPlan
from aiteamos_api.read.chat_action_planning_service import ChatActionPlanningService
from aiteamos_api.read.chat_governance_service import ChatGovernanceInput, ChatGovernanceService
from aiteamos_api.read.chat_run_preparation_service import ChatRunPreparationService
from aiteamos_api.read.execution_approval_service import get_execution_approval, record_execution_approval_requests
from aiteamos_api.read.execution_contract import ExecutionRequest, ExecutionResult
from aiteamos_api.read.execution_dispatch_service import ExecutionDispatchService
from aiteamos_api.read.runtime_executors.base import utc_now


async def governance_gate(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Create/load the governance envelope before runtime dispatch."""

    return await asyncio.to_thread(_governance_gate_sync, state, config)


def _governance_gate_sync(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    cfg = configurable(config)
    runtime_status = record(state.get("runtime_status"))
    provider_blockers = records(state.get("provider_blockers"))
    governance = _chat_governance_service()
    execution_request = _execution_request_from_state(state)
    if execution_request is None:
        governance_input = _governance_input_from_state(state, cfg)
        execution_request = governance.build_request(
            governance_input,
            action_plan=state_action_plan(state),
            planning_events=list(state.get("planning_events") or []),
        )
        execution_request = inject_graph_context(execution_request, state)

    approval_ref = text(state.get("approval_ref")) or text(cfg.get("approval_ref"))
    approval_resume = record(state.get("approval_resume"))
    approval_records = records(state.get("approval_records"))
    if approval_ref:
        approval = get_execution_approval(
            workspace_dir=governance.approval_workspace_dir,
            approval_id=approval_ref,
        )
        if approval is None:
            provider_blockers.append(
                {
                    "kind": "approval",
                    "reason": "runtime_approval_not_found",
                    "detail": f"Execution approval was not found: {approval_ref}",
                    "provider": "execution_approval_service",
                }
            )
            approval_resume = {
                **approval_resume,
                "approval_ref": approval_ref,
                "status": "not_found",
                "source": "governance_gate",
            }
        else:
            approval_payload = approval.model_dump(mode="json")
            approval_records = [approval_payload]
            approval_resume = {
                **approval_resume,
                "approval_ref": approval_ref,
                "approval_refs": [approval_ref],
                "approved_capabilities": (
                    [approval.required_capability]
                    if approval.status == "approved" and approval.required_capability
                    else []
                ),
                "status": approval.status,
                "checkpoint_ref": approval.checkpoint_ref,
                "executor_session_ref": approval.executor_session_ref,
                "source_state_ref": approval.source_state_ref,
                "source_state_snapshot_ref": approval.source_state_snapshot_ref,
                "current_graph_node": approval.current_graph_node,
                "source": "governance_gate",
            }
            if approval.status != "approved":
                provider_blockers.append(
                    {
                        "kind": "approval",
                        "reason": "runtime_approval_not_approved",
                        "detail": f"Execution approval {approval_ref} has status={approval.status}.",
                        "provider": "execution_approval_service",
                    }
                )

    request_payload = execution_request.model_dump(mode="json")
    approval_policy = record(request_payload.get("approval_policy"))
    base_payload: dict[str, Any] = {
        "execution_request": request_payload,
        "approval_resume": approval_resume,
        "approval_records": approval_records,
        "provider_blockers": provider_blockers,
        "capability_scope": {
            "grants": request_payload.get("capability_grants") if isinstance(request_payload.get("capability_grants"), list) else [],
            "approval_required": approval_policy.get("require_approval_for") if isinstance(approval_policy.get("require_approval_for"), list) else [],
        },
        "governance_summary": {
            "node": "governance_gate",
            "request_id": execution_request.request_id,
            "action": execution_request.action_plan.action,
            "ticket_binding": request_payload.get("ticket_binding"),
            "approval_policy": approval_policy,
            "approval_ref": approval_ref,
            "approval_resume_status": text(approval_resume.get("status")),
            "provider_blocker_count": len(provider_blockers),
        },
        "runtime_status": {
            **runtime_status,
            "current_node": "governance_gate",
            "request_id": execution_request.request_id,
            "approval_ref": approval_ref,
            "approval_resume_status": text(approval_resume.get("status")),
        },
    }
    preapproval = _pre_dispatch_approval_result(
        governance=governance,
        execution_request=execution_request,
        approval_ref=approval_ref,
    )
    if preapproval is None:
        return base_payload

    execution_result, approval_records = preapproval
    result_payload = execution_result.model_dump(mode="json")
    approval_requests = records(result_payload.get("approval_requests"))
    return {
        **base_payload,
        "execution_result": result_payload,
        "approval_requests": approval_requests,
        "approval_records": approval_records,
        "final_response": execution_result.report,
        "execution_summary": {
            "dispatch_node": "governance_gate",
            "execution_contract": "ExecutionRequest/ExecutionResult",
            "executor_id": execution_result.executor_id,
            "request_id": execution_request.request_id,
            "status": execution_result.status,
            "reply_available": bool(execution_result.report),
        },
        "workbench_panels": {
            **record(state.get("workbench_panels")),
            "approval": True,
            "provider_blockers": bool(provider_blockers),
        },
        "runtime_status": {
            **record(base_payload.get("runtime_status")),
            "current_node": "approval_interrupt",
            "status": execution_result.status,
            "executor_id": execution_result.executor_id,
            "checkpoint_ref": execution_result.checkpoint_ref,
            "executor_session_ref": execution_result.executor_session_ref,
            "approval_request_count": len(approval_requests),
        },
    }


def state_action_plan(state: AITeamOSWorkbenchState) -> ChatActionPlan:
    payload = record(state.get("action_plan"))
    if payload:
        return ChatActionPlan.model_validate(payload)
    return ChatActionPlan(action="answer_only", arguments={"message": latest_human_text(list(state.get("messages") or []))})


def inject_graph_context(
    execution_request: ExecutionRequest,
    state: AITeamOSWorkbenchState,
) -> ExecutionRequest:
    context_bundle = record(state.get("context_bundle"))
    graph_scoped_context = record(context_bundle.get("scoped_context"))
    if not graph_scoped_context:
        return execution_request

    task_context = {
        **record(execution_request.task_context),
        **graph_scoped_context,
    }
    if not text(task_context.get("task_summary")):
        task_context["task_summary"] = text(execution_request.task_context.get("task_summary"))
    task_context["universal_context"] = record(
        graph_scoped_context.get("universal_context")
        or context_bundle.get("universal_context")
        or execution_request.task_context.get("universal_context")
    )
    trace_context = {
        **record(execution_request.trace_context),
        "graph_context_source": text(context_bundle.get("source")) or "langgraph_context_node",
        "graph_governance_node": "governance_gate",
    }
    return execution_request.model_copy(update={"task_context": task_context, "trace_context": trace_context})


def _pre_dispatch_approval_result(
    *,
    governance: Any,
    execution_request: ExecutionRequest,
    approval_ref: str,
) -> tuple[ExecutionResult, list[dict[str, Any]]] | None:
    if approval_ref:
        return None
    if execution_request.action_plan.action != "implement_ticket":
        return None
    approval_policy = execution_request.approval_policy if isinstance(execution_request.approval_policy, dict) else {}
    required = _string_set(approval_policy.get("require_approval_for"))
    approved = _string_set(approval_policy.get("approved_capabilities"))
    if "repo:write" not in required or "repo:write" in approved:
        return None

    executor_id = _selected_executor_id(governance, execution_request)
    ticket_id = execution_request.ticket_id or execution_request.ticket_binding.ticket_id
    source_state_ref = f"state://aiteamos_workbench/{execution_request.request_id}/governance_gate"
    checkpoint_ref = f"langgraph:{execution_request.request_id}"
    executor_session_ref = f"lg-{execution_request.request_id}"
    approval_ref = f"approval-{execution_request.request_id}-1"
    timestamp = utc_now()
    result = ExecutionResult(
        request_id=execution_request.request_id,
        executor_id=executor_id,
        status="needs_approval",
        report="Approval is required before AITeamOS dispatches repo:write runtime work.",
        output_ticket_id=ticket_id,
        trace_ref=str(execution_request.trace_context.get("trace_ref") or ""),
        executor_session_ref=executor_session_ref,
        checkpoint_ref=checkpoint_ref,
        approval_requests=[
            {
                "approval_ref": approval_ref,
                "kind": "repo_mutation",
                "ticket_id": ticket_id,
                "executor_id": executor_id,
                "required_capability": "repo:write",
                "risk_level": "high",
                "reason": "repo:write requires human approval before runtime dispatch.",
                "proposed_action": {
                    "action": execution_request.action_plan.action,
                    "arguments": dict(execution_request.action_plan.arguments),
                    "ticket_id": ticket_id,
                    "executor_id": executor_id,
                },
                "checkpoint_ref": checkpoint_ref,
                "executor_session_ref": executor_session_ref,
                "source_state_ref": source_state_ref,
                "current_graph_node": "governance_gate",
            }
        ],
        learning_delta={
            "approval_interrupt": {
                "source": "aiteamos_workbench_graph",
                "approval_ref": approval_ref,
                "required_capability": "repo:write",
                "ticket_id": ticket_id,
                "current_graph_node": "governance_gate",
            }
        },
        errors=[
            {
                "reason": "repo_mutation_approval_required",
                "detail": "repo:write requires human approval before runtime dispatch.",
            }
        ],
        started_at=timestamp,
        finished_at=timestamp,
    )
    approval_records = record_execution_approval_requests(
        workspace_dir=governance.approval_workspace_dir,
        request=execution_request,
        result=result,
    )
    record_payloads = [item.model_dump(mode="json") for item in approval_records]
    if record_payloads:
        enriched_requests: list[dict[str, Any]] = []
        records_by_id = {text(item.get("id")): item for item in record_payloads}
        for request in result.approval_requests:
            request_ref = text(request.get("approval_ref"))
            approval_record = records_by_id.get(request_ref)
            enriched_requests.append(
                {
                    **request,
                    "approval_record_ref": request_ref,
                    "source_state_snapshot_ref": text(record(approval_record).get("source_state_snapshot_ref")),
                    "status": text(record(approval_record).get("status")) or "requested",
                }
            )
        result = result.model_copy(
            update={
                "approval_requests": enriched_requests,
                "learning_delta": {
                    **record(result.learning_delta),
                    "approval_records": record_payloads,
                },
            }
        )
    return result, record_payloads


def _selected_executor_id(governance: Any, execution_request: ExecutionRequest) -> str:
    selector = getattr(governance.dispatch_service, "_executor_id", None)
    if callable(selector):
        return str(selector(execution_request) or "universal_employee_agent")
    return str(
        execution_request.permission_policy.get("selected_executor")
        or execution_request.permission_policy.get("selected_ai_engine")
        or "universal_employee_agent"
    )


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {text(item) for item in value if text(item)}


def _execution_request_from_state(state: AITeamOSWorkbenchState) -> ExecutionRequest | None:
    payload = record(state.get("execution_request"))
    if not payload:
        return None
    return ExecutionRequest.model_validate(payload)


def _governance_input_from_state(
    state: AITeamOSWorkbenchState,
    cfg: dict[str, Any],
) -> ChatGovernanceInput:
    request_id = _request_id(state, cfg)
    employee = record(state.get("selected_employee")) or {"id": text(state.get("employee_id")) or "clara"}
    message = latest_human_text(list(state.get("messages") or [])) or text(cfg.get("message")) or "Continue the AITeamOS Workbench thread."
    thread_id = text(state.get("thread_id")) or text(cfg.get("thread_id")) or "employee-clara-default"
    return ChatGovernanceInput(
        message=message,
        employee=employee,
        selected_ai_engine=text(state.get("selected_ai_engine")) or "system",
        thread_id=thread_id,
        run_id=request_id,
        ticket_keys=list(state.get("ticket_keys") or []),
        memory_refs=records(state.get("recalled_memory_refs")),
        employee_profiles=list(state.get("employee_profiles") or []),
        recent_messages=[
            {"role": str(item.get("role") or ""), "content": str(item.get("content") or "")}
            for item in records(state.get("recent_messages"))
            if str(item.get("role") or "") in {"user", "assistant"} and str(item.get("content") or "").strip()
        ],
        trace_ref=f".aiteamos/traces/{request_id}.jsonl",
        workspace_id=str(_workspace_root()),
        approval_ref=text(state.get("approval_ref")) or text(cfg.get("approval_ref")),
        runtime_config={
            **record(cfg.get("runtime_config")),
            "source": "aiteamos_workbench_graph",
            "graph_node": "governance_gate",
            "run_id": request_id,
        },
    )


def _request_id(state: AITeamOSWorkbenchState, cfg: dict[str, Any]) -> str:
    existing = text(record(state.get("execution_request")).get("request_id"))
    if existing:
        return existing
    runtime_config = record(cfg.get("runtime_config"))
    configured = text(runtime_config.get("run_id") or runtime_config.get("request_id"))
    if configured:
        return ChatRunPreparationService.require_safe_id(configured, field="run_id")
    return f"run-{uuid4().hex[:12]}"


def _chat_governance_service() -> ChatGovernanceService:
    return ChatGovernanceService(
        workspace_dir=_workspace_dir(),
        planner=ChatActionPlanningService(async_client_factory=httpx.AsyncClient),
        dispatch_service=ExecutionDispatchService(async_client_factory=httpx.AsyncClient),
    )


def _workspace_dir() -> Path:
    return _workspace_root() / ".aiteamos"


def _workspace_root() -> Path:
    explicit = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[6]
