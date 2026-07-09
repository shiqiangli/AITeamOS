"""Runtime execution boundary contracts for AITeamOS governance dispatch."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .chat_action_plan import ChatActionPlan


class TicketBinding(BaseModel):
    mode: str = "existing"
    ticket_id: str = ""
    required: bool = True


class ScopedTaskContext(BaseModel):
    task_summary: str = ""
    ticket: dict[str, Any] = Field(default_factory=dict)
    employee: dict[str, Any] = Field(default_factory=dict)
    employee_profiles: list[dict[str, Any]] = Field(default_factory=list)
    recent_messages: list[dict[str, str]] = Field(default_factory=list)
    relevant_assets: list[dict[str, Any]] = Field(default_factory=list)
    recalled_memories: list[dict[str, Any]] = Field(default_factory=list)
    prior_evidence: list[dict[str, Any]] = Field(default_factory=list)
    repository_scope: dict[str, Any] = Field(default_factory=dict)
    validation_requirements: list[dict[str, Any]] = Field(default_factory=list)
    approval_policy_summary: dict[str, Any] = Field(default_factory=dict)
    exclusions: list[str] = Field(default_factory=list)
    recall_trace: list[dict[str, Any]] = Field(default_factory=list)
    setup_blockers: list[dict[str, Any]] = Field(default_factory=list)
    universal_context: dict[str, Any] = Field(default_factory=dict)


class ExecutionEvent(BaseModel):
    event: str
    request_id: str
    data: dict[str, Any] = Field(default_factory=dict)


class ExecutionRequest(BaseModel):
    request_id: str
    tenant_id: str = "local"
    workspace_id: str = "local"
    employee_id: str
    ticket_id: str = ""
    ticket_binding: TicketBinding = Field(default_factory=TicketBinding)
    action_plan: ChatActionPlan
    task_context: dict[str, Any] = Field(default_factory=dict)
    capability_grants: list[str] = Field(default_factory=list)
    permission_policy: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    approval_policy: dict[str, Any] = Field(default_factory=dict)
    expected_outputs: dict[str, Any] = Field(default_factory=dict)
    trace_context: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    request_id: str
    executor_id: str
    status: str
    report: str
    output_ticket_id: str = ""
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    trace_ref: str = ""
    executor_session_ref: str = ""
    checkpoint_ref: str = ""
    tool_events: list[dict[str, Any]] = Field(default_factory=list)
    approval_requests: list[dict[str, Any]] = Field(default_factory=list)
    memory_candidates: list[dict[str, Any]] = Field(default_factory=list)
    learning_delta: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""


class ExecutorHealth(BaseModel):
    executor_id: str
    status: str = "unknown"
    detail: str = ""
    capabilities: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
