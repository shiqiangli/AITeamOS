"""Governance orchestration for Chat-driven execution dispatch."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .chat_action_planning_service import ChatActionPlanningService
from .capability_service import capability_required_approval_for_command
from .chat_kernel_catalog import CHAT_ACTION_TO_COMMAND_ID
from .execution_approval_service import ExecutionApprovalRunRequest, ExecutionApprovalRunService, get_execution_approval
from .execution_context_service import ExecutionContextService
from .execution_contract import ExecutionRequest, ExecutionResult, TicketBinding
from .execution_dispatch_service import ExecutionDispatchService
from .execution_result_ingestion_service import ExecutionResultIngestionService
from .runtime_executors.base import blocked_result


class ChatGovernanceInput(BaseModel):
    message: str
    employee: dict[str, Any]
    selected_ai_engine: str
    thread_id: str
    run_id: str
    ticket_keys: list[str] = Field(default_factory=list)
    memory_refs: list[dict[str, Any]] = Field(default_factory=list)
    employee_profiles: list[dict[str, Any]] = Field(default_factory=list)
    recent_messages: list[dict[str, str]] = Field(default_factory=list)
    trace_ref: str = ""
    workspace_id: str = "local"
    approval_ref: str = ""
    runtime_config: dict[str, Any] = Field(default_factory=dict)


def build_chat_governance_input(
    context: Any,
    *,
    trace_path: Path,
    workspace_root: Path,
    employee_profiles: list[dict[str, Any]],
) -> ChatGovernanceInput:
    employee_payload = context.employee.model_dump(mode="json")
    employee_payload["skill_titles"] = context.skills
    employee_payload["permissions"] = [
        str(permission)
        for permission in context.selected_profile.get("permissions", [])
        if str(permission).strip()
    ]
    return ChatGovernanceInput(
        message=context.request.message,
        employee=employee_payload,
        employee_profiles=employee_profiles,
        selected_ai_engine=context.selected_ai_engine,
        thread_id=context.thread_id,
        run_id=context.run_id,
        ticket_keys=context.ticket_keys,
        memory_refs=context.memory_refs,
        trace_ref=str(trace_path.relative_to(workspace_root)),
        recent_messages=[
            {"role": message.role, "content": message.content}
            for message in context.recent_messages
            if message.role in {"user", "assistant"} and message.content.strip()
        ],
        workspace_id=str(workspace_root),
        approval_ref=(context.request.approval_ref or "").strip(),
        runtime_config=context.request.runtime_config,
    )


class ChatGovernanceService:
    def __init__(
        self,
        *,
        workspace_dir: Path,
        planner: ChatActionPlanningService | None = None,
        context_service: ExecutionContextService | None = None,
        dispatch_service: ExecutionDispatchService | None = None,
        ingestion_service: ExecutionResultIngestionService | None = None,
        approval_workspace_dir: Path | None = None,
    ) -> None:
        self.planner = planner or ChatActionPlanningService()
        self.context_service = context_service or ExecutionContextService()
        self.dispatch_service = dispatch_service or ExecutionDispatchService()
        self.ingestion_service = ingestion_service or ExecutionResultIngestionService(workspace_dir=workspace_dir)
        self.workspace_dir = workspace_dir
        self.approval_workspace_dir = approval_workspace_dir or (workspace_dir.parent if workspace_dir.name == ".aiteamos" else workspace_dir)

    def build_request(
        self,
        payload: ChatGovernanceInput,
        *,
        action_plan: Any | None = None,
        planning_events: list[dict[str, Any]] | None = None,
    ) -> ExecutionRequest:
        employee_id = str(payload.employee.get("id") or "clara")
        if action_plan is None:
            action_plan = self.planner.plan(
                message=payload.message,
                ticket_keys=payload.ticket_keys,
                employee_id=employee_id,
                employee_profiles=payload.employee_profiles,
            )
        ticket_id = str(action_plan.arguments.get("ticket_id") or (payload.ticket_keys[0] if payload.ticket_keys else ""))
        binding = self._ticket_binding(action_plan.action, ticket_id)
        scoped_context = self.context_service.build(
            message=payload.message,
            employee=payload.employee,
            employee_profiles=payload.employee_profiles,
            recent_messages=payload.recent_messages,
            ticket_keys=payload.ticket_keys,
            memory_refs=payload.memory_refs,
            selected_ai_engine=payload.selected_ai_engine,
        )
        permission_policy = {"source": "aiteamos_governance", "selected_ai_engine": payload.selected_ai_engine}
        if action_plan.action == "implement_ticket" and payload.selected_ai_engine.strip() in {
            "claude_agent_sdk",
            "claude-agent-sdk",
            "claude_code",
            "claude-code",
            "cursor",
            "openhands",
            "open-hands",
            "opencode",
            "open-code",
        }:
            permission_policy = {
                "source": "aiteamos_governance",
                "selected_ai_engine": "universal_employee_agent",
                "selected_executor": "universal_employee_agent",
                "requested_runtime_executor": self._runtime_executor_id(payload.selected_ai_engine),
            }
        request = ExecutionRequest(
            request_id=payload.run_id,
            workspace_id=payload.workspace_id,
            employee_id=employee_id,
            ticket_id=ticket_id,
            ticket_binding=binding,
            action_plan=action_plan,
            task_context=scoped_context.model_dump(mode="json"),
            capability_grants=self._capability_grants(action_plan.action),
            permission_policy=permission_policy,
            budget={"max_runtime_steps": 12, "max_tool_events": 50},
            approval_policy=self._approval_policy(action_plan.action),
            expected_outputs={"report": True, "evidence": action_plan.action in {"append_report", "request_validation", "implement_ticket"}},
            trace_context={
                "thread_id": payload.thread_id,
                "run_id": payload.run_id,
                "trace_ref": payload.trace_ref,
                "source_message": payload.message,
                "planning_events": planning_events or [],
            },
        )
        return request

    async def handle_message(self, payload: ChatGovernanceInput) -> tuple[ExecutionRequest, ExecutionResult]:
        employee_id = str(payload.employee.get("id") or "clara")
        action_plan, planning_events = await self.planner.plan_async(
            message=payload.message,
            ticket_keys=payload.ticket_keys,
            employee_id=employee_id,
            selected_ai_engine=payload.selected_ai_engine,
            workspace_id=payload.workspace_id,
            employee=payload.employee,
            employee_profiles=payload.employee_profiles,
            recent_messages=payload.recent_messages,
        )
        request = await asyncio.to_thread(
            self.build_request,
            payload,
            action_plan=action_plan,
            planning_events=planning_events,
        )
        approval_ref = payload.approval_ref.strip()
        if approval_ref:
            return await self._handle_approved_runtime_run(payload, request, approval_ref)
        result = await self.dispatch_service.dispatch(request)
        result = await asyncio.to_thread(self.ingestion_service.ingest, request, result)
        return request, result

    def ingest_result(self, request: ExecutionRequest, result: ExecutionResult) -> ExecutionResult:
        return self.ingestion_service.ingest(request, result)

    def _ticket_binding(self, action: str, ticket_id: str) -> TicketBinding:
        if action in {"create_ticket", "self_bootstrap_start"}:
            return TicketBinding(mode="create", ticket_id="", required=True)
        if action in {
            "append_report",
            "record_validation",
            "record_failure",
            "request_validation",
            "request_human_review",
            "inspect_code_repository",
            "implement_ticket",
            "self_bootstrap_close",
            "terminal_run",
        }:
            return TicketBinding(mode="existing", ticket_id=ticket_id, required=True)
        return TicketBinding(mode="none", ticket_id=ticket_id, required=False)

    def _capability_grants(self, action: str) -> list[str]:
        base = ["tickets:read", "assets:read", "memory:recall"]
        if action in {"create_ticket", "self_bootstrap_start"}:
            return [*base, "tickets:write"]
        if action == "list_employees":
            return [*base, "employees:read"]
        if action in {"create_employee", "edit_employee_profile"}:
            return [*base, "employees:write"]
        if action == "delete_employee":
            return [*base, "employees:delete"]
        if action == "list_skills":
            return [*base, "skills:read"]
        if action == "create_skill":
            return [*base, "skills:write"]
        if action == "assign_skill_to_employee":
            return [*base, "assets:assign", "employees:write", "skills:read"]
        if action == "delete_skill":
            return [*base, "skills:delete", "employees:write"]
        if action in {"append_report", "record_validation", "record_failure", "request_validation", "request_human_review"}:
            return [*base, "tickets:write", "ticket:evidence:write"]
        if action == "self_bootstrap_close":
            return [*base, "tickets:write", "ticket:evidence:write", "memory:review"]
        if action == "terminal_run":
            return [*base, "tickets:write", "ticket:evidence:write", "terminal:run"]
        if action == "inspect_code_repository":
            return [*base, "tickets:write", "ticket:evidence:write", "repositories:read", "repo:read"]
        if action == "implement_ticket":
            return [*base, "tickets:write", "ticket:evidence:write", "repositories:read", "repo:read", "repo:write"]
        return base

    def _approval_policy(self, action: str) -> dict[str, Any]:
        requirements = {"repo:write", "destructive_file_delete", "external_connector_write", "memory_approve"}
        command_id = CHAT_ACTION_TO_COMMAND_ID.get(action, "")
        if command_id and command_id != "none":
            requirements.update(capability_required_approval_for_command(command_id))
        return {
            "require_approval_for": sorted(requirements),
            "on_missing_approval": "return_needs_approval",
        }

    def _runtime_executor_id(self, value: str) -> str:
        normalized = value.strip()
        aliases = {
            "claude-code": "claude_code",
            "claude_agent": "claude_agent_sdk",
            "claude-agent-sdk": "claude_agent_sdk",
            "open-hands": "openhands",
            "open-code": "opencode",
        }
        return aliases.get(normalized, normalized)

    async def _handle_approved_runtime_run(
        self,
        payload: ChatGovernanceInput,
        request: ExecutionRequest,
        approval_ref: str,
    ) -> tuple[ExecutionRequest, ExecutionResult]:
        approval = await asyncio.to_thread(
            get_execution_approval,
            workspace_dir=self.approval_workspace_dir,
            approval_id=approval_ref,
        )
        if approval is None:
            return request, blocked_result(
                request,
                executor_id="runtime_approval",
                reason="runtime_approval_not_found",
                detail=f"Execution approval was not found: {approval_ref}",
            )
        if approval.status != "approved":
            return request, blocked_result(
                request,
                executor_id=approval.executor_id or "runtime_approval",
                reason="runtime_approval_not_approved",
                detail=f"Execution approval {approval_ref} must be approved before runtime dispatch.",
            )
        runner = ExecutionApprovalRunService(
            workspace_dir=self.approval_workspace_dir,
            dispatch_service=self.dispatch_service,
            ingestion_service=self.ingestion_service,
        )
        response = await runner.run(
            approval.executor_id,
            approval_ref,
            ExecutionApprovalRunRequest(
                employee_id=payload.employee.get("id", ""),
                workspace_id=payload.workspace_id,
                message=payload.message,
                runtime_config=payload.runtime_config,
                ingest_result=True,
            ),
        )
        approved_request = ExecutionRequest.model_validate(response.request) if response.request else request
        approved_result = ExecutionResult.model_validate(response.result)
        return approved_request, approved_result
