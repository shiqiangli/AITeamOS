"""Execution and ingestion nodes for the AITeamOS Workbench graph."""

import asyncio
from typing import Any

from langchain_core.runnables.config import RunnableConfig

from aiteamos_api.agents.workbench.nodes.governance import inject_graph_context, state_action_plan
from aiteamos_api.agents.workbench.state import (
    AITeamOSWorkbenchState,
    configurable,
    latest_human_text,
    record,
    records,
    text,
)
from aiteamos_api.read.chat_governance_service import ChatGovernanceInput, ChatGovernanceService
from aiteamos_api.read.execution_approval_service import (
    ExecutionApprovalRunRequest,
    ExecutionApprovalRunService,
    get_execution_approval,
)
from aiteamos_api.read.execution_contract import ExecutionRequest, ExecutionResult
from aiteamos_api.read.workbench_runtime_context_service import (
    WorkbenchRuntimeContextService,
    WorkbenchRuntimeDispatchInput,
)


async def dispatch_runtime_executor(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Dispatch this Workbench turn through the governed ExecutionRequest boundary."""

    return await _dispatch_through_execution_contract(state, config)


async def _dispatch_through_execution_contract(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    cfg = configurable(config)
    message = latest_human_text(list(state.get("messages") or []))
    if not message:
        message = text(cfg.get("message")) or "Continue the AITeamOS Workbench thread."
    runtime_context = WorkbenchRuntimeContextService()
    prepared_run = await runtime_context.prepare(
        WorkbenchRuntimeDispatchInput(
            message=message,
            target_employee_id=text(state.get("employee_id")) or text(cfg.get("target_employee_id")),
            thread_id=text(state.get("thread_id")) or text(cfg.get("thread_id")),
            ticket_key=text(state.get("ticket_key")) or text(cfg.get("ticket_key")),
            approval_ref=text(state.get("approval_ref")) or text(cfg.get("approval_ref")),
            runtime_config={
                **record(cfg.get("runtime_config")),
                "source": "aiteamos_workbench_graph",
                "graph_node": "dispatch_runtime_executor",
                "dispatch_contract": "ExecutionRequest",
                "run_id": text(record(state.get("execution_request")).get("request_id")),
            },
        )
    )
    governance = prepared_run.governance
    governance_input = prepared_run.governance_input
    execution_request = _execution_request_from_state(state)
    if execution_request is None:
        execution_request = await asyncio.to_thread(
            governance.build_request,
            governance_input,
            action_plan=state_action_plan(state),
            planning_events=list(state.get("planning_events") or []),
        )
        execution_request = inject_graph_context(execution_request, state)
    execution_request, execution_result = await _run_execution_request(
        governance=governance,
        governance_input=governance_input,
        execution_request=execution_request,
        approval_ref=prepared_run.approval_ref,
    )
    response = await runtime_context.persist_execution_response(
        prepared_run.context,
        execution_request=execution_request,
        execution_result=execution_result,
    )
    request_payload = execution_request.model_dump(mode="json")
    result_payload = execution_result.model_dump(mode="json")
    response_payload = response.model_dump(mode="json")
    approval_records = records(record(execution_result.learning_delta).get("approval_records"))
    return {
        "execution_request": request_payload,
        "execution_result": result_payload,
        "aiteamos_chat_response": response_payload,
        "final_response": response.reply,
        "thread_id": response.thread_id,
        "employee_id": response.target_employee.id,
        "approval_requests": records(result_payload.get("approval_requests")),
        "approval_records": approval_records,
        "execution_summary": {
            **record(state.get("execution_summary")),
            "dispatch_node": "dispatch_runtime_executor",
            "execution_contract": "ExecutionRequest/ExecutionResult",
            "runtime_context_service": runtime_context.service_id,
            "executor_id": execution_result.executor_id,
            "request_id": execution_request.request_id,
            "run_id": response.run_id,
            "thread_id": response.thread_id,
            "employee_id": response.target_employee.id,
            "status": execution_result.status,
            "reply_available": bool(response.reply),
        },
        "runtime_status": {
            **record(state.get("runtime_status")),
            "current_node": "dispatch_runtime_executor",
            "status": execution_result.status,
            "run_id": response.run_id,
            "request_id": execution_request.request_id,
            "executor_id": execution_result.executor_id,
            "checkpoint_ref": execution_result.checkpoint_ref,
            "executor_session_ref": execution_result.executor_session_ref,
        },
    }


def _execution_request_from_state(state: AITeamOSWorkbenchState) -> ExecutionRequest | None:
    payload = record(state.get("execution_request"))
    if not payload:
        return None
    return ExecutionRequest.model_validate(payload)


async def _run_execution_request(
    *,
    governance: ChatGovernanceService,
    governance_input: ChatGovernanceInput,
    execution_request: ExecutionRequest,
    approval_ref: str,
) -> tuple[ExecutionRequest, ExecutionResult]:
    normalized_ref = approval_ref.strip()
    if normalized_ref:
        approval = await asyncio.to_thread(
            get_execution_approval,
            workspace_dir=governance.approval_workspace_dir,
            approval_id=normalized_ref,
        )
        executor_id = (
            approval.executor_id
            if approval is not None
            else str(
                execution_request.permission_policy.get("selected_executor")
                or execution_request.permission_policy.get("selected_ai_engine")
                or "runtime_approval"
            )
        )
        runner = ExecutionApprovalRunService(
            workspace_dir=governance.approval_workspace_dir,
            dispatch_service=governance.dispatch_service,
            ingestion_service=governance.ingestion_service,
        )
        response = await runner.run(
            executor_id,
            normalized_ref,
            ExecutionApprovalRunRequest(
                employee_id=governance_input.employee.get("id", ""),
                workspace_id=governance_input.workspace_id,
                message=governance_input.message,
                runtime_config=governance_input.runtime_config,
                ingest_result=True,
            ),
        )
        approved_request = ExecutionRequest.model_validate(response.request) if response.request else execution_request
        return approved_request, ExecutionResult.model_validate(response.result)

    result = await governance.dispatch_service.dispatch(execution_request)
    result = await asyncio.to_thread(governance.ingest_result, execution_request, result)
    return execution_request, result


async def ingest_ticket_report_evidence(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    """Expose execution ingestion outputs as graph state without owning ingestion itself."""

    return await asyncio.to_thread(_ingest_ticket_report_evidence_sync, state)


def _ingest_ticket_report_evidence_sync(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    response = record(state.get("aiteamos_chat_response"))
    metadata = record(response.get("run_metadata"))
    execution = record(metadata.get("execution"))
    result = record(execution.get("result"))
    trace = record(execution.get("trace"))
    tool_calls = records(result.get("tool_events"))
    if not tool_calls:
        dispatch_event = next(
            (
                record(event.get("data")).get("tool_events")
                for event in records(response.get("trace_events"))
                if event.get("event") == "execution.dispatch.completed"
            ),
            [],
        )
        tool_calls = records(dispatch_event)
    evidence_refs = records(result.get("evidence_refs"))
    ticket_report_refs = records(result.get("ticket_report_refs"))
    ticket_report_id = text(next((item.get("ref") for item in ticket_report_refs if text(item.get("ref"))), ""))
    evidence_id = text(next((item.get("ref") for item in evidence_refs if text(item.get("ref"))), ""))
    execution_status = text(execution.get("status")) or text(metadata.get("status")) or "completed"
    return {
        "tool_calls": tool_calls,
        "ticket_evidence_refs": evidence_refs,
        "ticket_report_refs": ticket_report_refs,
        "execution_summary": {
            **record(state.get("execution_summary")),
            "ingestion_node": "ingest_ticket_report_evidence",
            "executor_id": text(execution.get("executor_id")),
            "status": execution_status,
            "checkpoint_ref": text(trace.get("checkpoint_ref")),
            "executor_session_ref": text(trace.get("executor_session_ref")),
            "ticket_report_id": ticket_report_id,
            "evidence_id": evidence_id,
            "evidence_count": len(evidence_refs),
            "ticket_report_count": len(ticket_report_refs),
            "tool_event_count": len(tool_calls),
        },
        "runtime_status": {
            **record(state.get("runtime_status")),
            "current_node": "ingest_ticket_report_evidence",
            "executor_id": text(execution.get("executor_id")),
            "status": execution_status,
            "checkpoint_ref": text(trace.get("checkpoint_ref")),
            "executor_session_ref": text(trace.get("executor_session_ref")),
            "ticket_report_id": ticket_report_id,
            "evidence_id": evidence_id,
        },
    }
