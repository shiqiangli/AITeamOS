"""Ticket service with AITeamOS Ticket projections over configured backends."""

from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlparse
from uuid import uuid4

import httpx
import yaml
from pydantic import BaseModel, Field

from .repository_service import code_repository_plane_scope_summary, list_code_repositories

CLARA_SYSTEM_EMPLOYEE_ID = "clara"
CLARA_SYSTEM_ROLE = "AI Team OS Manager"
LOCAL_TICKET_ID_RE = re.compile(r"^(?:ticket-[A-Za-z0-9_.:-]+|(?:rd|pv|arch|rel|mem|doc|ops|trace)-\d{4,})$", re.IGNORECASE)
_SAFE_NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9_-]{1,24}$")

_ROLE_NAMESPACE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rd", ("rd", "implementer", "developer", "engineer", "研发", "开发")),
    ("pv", ("pv", "qa", "verification", "validation", "harness", "验证", "测试")),
    ("arch", ("architect", "architecture", "架构")),
    ("rel", ("release", "发布")),
    ("mem", ("memory curator", "memory", "记忆")),
    ("doc", ("docs", "documentation", "knowledge", "writer", "文档", "知识")),
    ("trace", ("trace reporter", "trace", "reporter", "观测")),
)
_MANAGER_ROLES = {CLARA_SYSTEM_ROLE.lower(), "manager", "system manager", "ai team os manager"}
_KNOWN_NAMESPACES = {"rd", "pv", "arch", "rel", "mem", "doc", "ops", "trace"}


class TicketEvent(BaseModel):
    event_id: str
    ticket_id: str
    type: str
    at: str
    actor: dict[str, str] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)


class TicketReport(BaseModel):
    id: str
    reporter_employee_id: str
    reporter_role: str = ""
    content: str
    evidence: list[str] = Field(default_factory=list)
    report_type: str = "progress"
    created_at: str
    source_event_id: str = ""


class ProviderTicketRef(BaseModel):
    provider: str = "plane"
    provider_record_id: str
    provider_project_id: str = ""
    provider_url: str = ""
    synced_at: str


class Ticket(BaseModel):
    id: str
    title: str
    description: str
    status: str = "assigned"
    ticket_type: str = "ops"
    assigned_employee_id: str = ""
    assigned_role: str = ""
    validation_employee_id: str = ""
    validation_role: str = ""
    knowledge_refs: list[str] = Field(default_factory=list)
    code_repository_ids: list[str] = Field(default_factory=list)
    source_thread_id: str = ""
    source_run_id: str = ""
    reports: list[TicketReport] = Field(default_factory=list)
    events: list[TicketEvent] = Field(default_factory=list)
    provider_ref: ProviderTicketRef | None = None
    external_url: str = ""
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    saved_path: str = ""


class TicketCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    ticket_type: str = ""
    assigned_employee_id: str = ""
    assigned_role: str = ""
    validation_employee_id: str = ""
    validation_role: str = ""
    knowledge_refs: list[str] = Field(default_factory=list)
    code_repository_ids: list[str] = Field(default_factory=list)
    source_thread_id: str = ""
    source_run_id: str = ""
    actor_employee_id: str = CLARA_SYSTEM_EMPLOYEE_ID
    actor_role: str = ""


class TicketReportRequest(BaseModel):
    reporter_employee_id: str
    reporter_role: str = ""
    content: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    report_type: str = "progress"
    source_run_id: str = ""


class TicketValidationRequest(BaseModel):
    validation_employee_id: str = ""
    validation_role: str = ""
    content: str = ""
    actor_employee_id: str = CLARA_SYSTEM_EMPLOYEE_ID
    actor_role: str = ""
    source_run_id: str = ""


class TicketHandoffRequest(BaseModel):
    to_employee_id: str = ""
    to_role: str = ""
    from_employee_id: str = ""
    from_role: str = ""
    content: str = ""
    actor_employee_id: str = CLARA_SYSTEM_EMPLOYEE_ID
    actor_role: str = ""
    source_run_id: str = ""


class TicketStateTransitionRequest(BaseModel):
    status: str = Field(min_length=1)
    actor_employee_id: str = CLARA_SYSTEM_EMPLOYEE_ID
    actor_role: str = ""
    source_run_id: str = ""


class TicketBackendMode(BaseModel):
    id: str
    label: str
    status: str
    description: str


class TicketBackendSettings(BaseModel):
    mode: str = "plane"
    local_file_path: str = ".aiteamos/tickets/index.json"
    plane_api_base_url: str = "https://api.plane.so"
    plane_web_base_url: str = "https://app.plane.so"
    plane_workspace_slug: str = ""
    plane_project_id: str = ""
    plane_api_key_env: str = "PLANE_API_KEY"
    plane_namespace_strategy: str = "label"
    plane_namespace_label_ids: dict[str, str] = Field(default_factory=dict)
    plane_state_ids: dict[str, str] = Field(default_factory=dict)
    plane_employee_assignee_ids: dict[str, str] = Field(default_factory=dict)
    saved_paths: dict[str, str] = Field(default_factory=dict)
    supported_modes: list[TicketBackendMode] = Field(default_factory=list)


class TicketBackendSettingsUpdateRequest(BaseModel):
    mode: str = "plane"
    local_file_path: str = ".aiteamos/tickets/index.json"
    plane_api_base_url: str = "https://api.plane.so"
    plane_web_base_url: str = "https://app.plane.so"
    plane_workspace_slug: str = ""
    plane_project_id: str = ""
    plane_api_key_env: str = "PLANE_API_KEY"
    plane_namespace_strategy: str = "label"
    plane_namespace_label_ids: dict[str, str] = Field(default_factory=dict)
    plane_state_ids: dict[str, str] = Field(default_factory=dict)
    plane_employee_assignee_ids: dict[str, str] = Field(default_factory=dict)


class TicketBackendStatus(BaseModel):
    mode: str
    status: str
    detail: str
    ticket_count: int = 0
    local_file_path: str = ""
    provider: str = ""
    provider_ref_count: int = 0
    setup_required: list[str] = Field(default_factory=list)
    plane_setup: dict[str, Any] = Field(default_factory=dict)
    release_target: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    mapping: dict[str, str] = Field(default_factory=dict)
    saved_paths: dict[str, str] = Field(default_factory=dict)
    supported_modes: list[TicketBackendMode] = Field(default_factory=list)


class TicketBackendPlaneScopeDiscovery(BaseModel):
    status: str
    detail: str
    api_key_env: str = "PLANE_API_KEY"
    api_key_configured: bool = False
    external_calls: bool = False
    checks: list[str] = Field(default_factory=list)
    setup_required: list[str] = Field(default_factory=list)
    suggestions: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class TicketProviderActionSmokeRequest(BaseModel):
    execute: bool = False
    confirm_env_var: str = "AITEAMOS_LIVE_PROVIDER_DOGFOOD"
    ticket_id: str = ""
    create_ticket_if_missing: bool = True
    from_employee_id: str = CLARA_SYSTEM_EMPLOYEE_ID
    from_role: str = CLARA_SYSTEM_ROLE
    to_employee_id: str = "alex"
    to_role: str = "AI RD / Implementer"
    source_run_id: str = "plane-ticket-action-smoke"
    report_content: str = "AITeamOS Plane action smoke for Ticket handoff/report writes."


class TicketProviderActionSmokeResponse(BaseModel):
    status: str
    provider: str = ""
    checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    external_calls: bool = False
    mutating: bool = False


class TicketWorkItem(BaseModel):
    ticket_id: str
    title: str
    status: str
    role: str
    updated_at: str
    next_action: str = ""


class EmployeeTicketReportRecord(BaseModel):
    ticket_id: str
    ticket_title: str
    report_id: str
    report_type: str
    content: str
    evidence: list[str] = Field(default_factory=list)
    created_at: str


class EmployeeAssetWorkRecord(BaseModel):
    asset_id: str = ""
    candidate_id: str = ""
    asset_type: str = ""
    title: str = ""
    status: str = ""
    review_state: str = ""
    scope_kind: str = ""
    scope_ref: str = ""
    source_ticket_id: str = ""
    source_run_id: str = ""
    source_ref: str = ""
    application_status: str = ""
    application_report_id: str = ""
    application_employee_id: str = ""
    created_at: str = ""
    updated_at: str = ""


class EmployeeAssetReviewRecord(BaseModel):
    review_id: str
    candidate_id: str = ""
    asset_id: str = ""
    status: str = ""
    reviewer_employee_id: str = ""
    reason: str = ""
    relation_to_employee: str = ""
    created_at: str = ""
    updated_at: str = ""


class EmployeeRuntimeRunRecord(BaseModel):
    request_id: str
    run_id: str = ""
    session_key: str = ""
    ticket_id: str = ""
    action: str = ""
    executor_id: str = ""
    status: str = ""
    trace_ref: str = ""
    artifact_count: int = 0
    evidence_count: int = 0
    tool_event_count: int = 0
    memory_candidate_count: int = 0
    latency_ms: int = 0
    total_cost: float = 0.0
    started_at: str = ""
    finished_at: str = ""


class EmployeeQualityFeedbackRecord(BaseModel):
    id: str
    kind: str = ""
    status: str = ""
    summary: str = ""
    source_ref: str = ""
    reviewer_employee_id: str = ""
    ticket_id: str = ""
    created_at: str = ""


class EmployeeImprovementCandidateRequest(BaseModel):
    actor_employee_id: str = CLARA_SYSTEM_EMPLOYEE_ID
    reason: str = ""
    title: str = ""
    content: str = ""
    proposed_skill_refs: list[str] = Field(default_factory=list)
    proposed_memory_scopes: list[str] = Field(default_factory=list)
    proposed_capability_tags: list[str] = Field(default_factory=list)
    proposed_personality_tags: list[str] = Field(default_factory=list)


class EmployeeImprovementCandidateResponse(BaseModel):
    employee_id: str
    feedback: EmployeeQualityFeedbackRecord
    candidate: dict[str, Any]
    saved_paths: dict[str, str] = Field(default_factory=dict)


class EmployeeWorkLedger(BaseModel):
    employee_id: str
    current_tickets: list[TicketWorkItem] = Field(default_factory=list)
    historical_tickets: list[TicketWorkItem] = Field(default_factory=list)
    reports: list[EmployeeTicketReportRecord] = Field(default_factory=list)
    validations: list[EmployeeTicketReportRecord] = Field(default_factory=list)
    blocked_records: list[EmployeeTicketReportRecord] = Field(default_factory=list)
    handoffs: list[dict[str, Any]] = Field(default_factory=list)
    asset_candidates: list[EmployeeAssetWorkRecord] = Field(default_factory=list)
    approved_assets: list[EmployeeAssetWorkRecord] = Field(default_factory=list)
    asset_reviews: list[EmployeeAssetReviewRecord] = Field(default_factory=list)
    runtime_runs: list[EmployeeRuntimeRunRecord] = Field(default_factory=list)
    quality_feedback: list[EmployeeQualityFeedbackRecord] = Field(default_factory=list)
    contribution: dict[str, int] = Field(default_factory=dict)


class TicketAssetRecord(BaseModel):
    id: str
    kind: str
    title: str
    status: str = "active"
    source_ticket_id: str = ""
    source_employee_id: str = ""
    assigned_employees: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TicketGraphNode(BaseModel):
    id: str
    kind: str
    label: str
    status: str = ""
    ref: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TicketGraphEdge(BaseModel):
    id: str
    type: str
    source_id: str
    target_id: str
    label: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TicketGraphProjection(BaseModel):
    ticket_id: str
    nodes: list[TicketGraphNode] = Field(default_factory=list)
    edges: list[TicketGraphEdge] = Field(default_factory=list)
    grouped_edges: dict[str, list[TicketGraphEdge]] = Field(default_factory=dict)
    source_counts: dict[str, int] = Field(default_factory=dict)


class EmployeeGraphProjection(BaseModel):
    employee_id: str
    nodes: list[TicketGraphNode] = Field(default_factory=list)
    edges: list[TicketGraphEdge] = Field(default_factory=list)
    grouped_edges: dict[str, list[TicketGraphEdge]] = Field(default_factory=dict)
    source_counts: dict[str, int] = Field(default_factory=dict)
    provider_projection: dict[str, Any] = Field(default_factory=dict)


class AssetGraphProjection(BaseModel):
    asset_id: str
    nodes: list[TicketGraphNode] = Field(default_factory=list)
    edges: list[TicketGraphEdge] = Field(default_factory=list)
    grouped_edges: dict[str, list[TicketGraphEdge]] = Field(default_factory=dict)
    source_counts: dict[str, int] = Field(default_factory=dict)


class AssetGraphStatus(BaseModel):
    status: str
    detail: str
    ticket_count: int = 0
    asset_record_count: int = 0
    graph_asset_count: int = 0
    employee_count: int = 0
    capabilities: list[str] = Field(default_factory=list)


class EmployeeAnalytics(BaseModel):
    employee_id: str
    assigned_ticket_count: int = 0
    completed_ticket_count: int = 0
    validation_pass_rate: float = 0.0
    candidates_produced: int = 0
    recalled_asset_count: int = 0
    blocker_count: int = 0
    validation_failure_count: int = 0
    stale_asset_count: int = 0
    useful_recall_count: int = 0
    execution_run_count: int = 0
    total_cost: float = 0.0
    average_latency_ms: int = 0
    source_counts: dict[str, int] = Field(default_factory=dict)


class EmployeeAnalyticsSummary(BaseModel):
    employees: list[EmployeeAnalytics] = Field(default_factory=list)
    source_counts: dict[str, int] = Field(default_factory=dict)


class TicketEmployeeContribution(BaseModel):
    employee_id: str
    role: str = ""
    assigned: bool = False
    validator: bool = False
    reporter: bool = False
    event_actor: bool = False
    asset_source: bool = False
    asset_assigned: bool = False
    report_count: int = 0
    validation_report_count: int = 0
    blocked_report_count: int = 0
    evidence_count: int = 0
    event_count: int = 0
    candidate_count: int = 0
    recalled_asset_count: int = 0
    linked_asset_count: int = 0


class TicketPerformance(BaseModel):
    ticket_id: str
    status: str = ""
    contribution: list[TicketEmployeeContribution] = Field(default_factory=list)
    quality_signals: dict[str, Any] = Field(default_factory=dict)
    source_counts: dict[str, int] = Field(default_factory=dict)


class TicketRuntimeProviderEvidence(BaseModel):
    mode: str = ""
    status: str = ""
    provider: str = ""
    provider_ref_recorded: bool = False
    provider_record_id: str = ""
    provider_project_id: str = ""
    provider_url: str = ""
    external_url: str = ""
    synced_at: str = ""
    detail: str = ""
    setup_required: list[str] = Field(default_factory=list)


class TicketRuntimeLoopRunEvidence(BaseModel):
    run_id: str
    status: str = ""
    stop_reason: str = ""
    active: bool = False
    session_key: str = ""
    step_count: int = 0
    queued_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    updated_at: str = ""
    saved_path: str = ""


class TicketRuntimeEvidence(BaseModel):
    ticket_id: str
    status: str = ""
    source_counts: dict[str, int] = Field(default_factory=dict)
    provider_state: TicketRuntimeProviderEvidence = Field(default_factory=TicketRuntimeProviderEvidence)
    governance_state: dict[str, Any] = Field(default_factory=dict)
    latest_loop_run: TicketRuntimeLoopRunEvidence | None = None
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)


class TicketEvidenceRequirement(BaseModel):
    id: str
    label: str
    required: bool = True
    satisfied: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)
    detail: str = ""


class TicketEvidenceRequirements(BaseModel):
    ticket_id: str
    ticket_type: str = ""
    profile: str = "general"
    satisfied: bool = True
    missing_required: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    requirements: list[TicketEvidenceRequirement] = Field(default_factory=list)


class SelfBootstrapTicketLearningRecord(BaseModel):
    ticket_id: str
    title: str
    status: str = ""
    assigned_employee_id: str = ""
    validation_employee_id: str = ""
    evidence_count: int = 0
    missing_required_evidence: int = 0
    validation_passed: bool = False
    blocked_or_failed: bool = False
    memory_candidates: int = 0
    approved_memory_candidates: int = 0
    approved_memories_recalled: int = 0
    graphiti_memories_recalled: int = 0
    useful_memory_recalls: int = 0
    provider_ref_recorded: bool = False
    next_learning_action: str = ""


class SelfBootstrapLearningSummary(BaseModel):
    ticket_count: int = 0
    validated_ticket_count: int = 0
    blocked_ticket_count: int = 0
    tickets_with_evidence: int = 0
    tickets_missing_required_evidence: int = 0
    memory_candidates_produced: int = 0
    approved_memory_candidates: int = 0
    approved_memories_recalled: int = 0
    graphiti_memories_recalled: int = 0
    useful_memory_recalls: int = 0
    stale_or_superseded_assets: int = 0
    summary: str = ""
    learning_delta: dict[str, Any] = Field(default_factory=dict)
    tickets: list[SelfBootstrapTicketLearningRecord] = Field(default_factory=list)
    source_counts: dict[str, int] = Field(default_factory=dict)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_root() -> Path:
    configured = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _workspace_dir() -> Path:
    return _workspace_root() / ".aiteamos"


def _tickets_dir() -> Path:
    path = _workspace_dir() / "tickets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _employees_dir() -> Path:
    return _workspace_dir() / "employees"


def _backend_settings_path() -> Path:
    return _tickets_dir() / "backend.json"


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(_workspace_root()))
    except ValueError:
        return str(path)


SUPPORTED_BACKENDS = [
    TicketBackendMode(
        id="local_file",
        label="Local file",
        status="legacy",
        description="Legacy append-only projection only for explicit migration checks; not the target Ticket Backend.",
    ),
    TicketBackendMode(
        id="plane",
        label="Plane",
        status="ready",
        description="Plane-backed Ticket fact source through the AITeamOS TicketAdapter.",
    ),
    TicketBackendMode(
        id="jira",
        label="Jira",
        status="planned",
        description="Future Jira-backed source of truth for enterprise Ticket integration after the Plane path is stable.",
    ),
]

PLANE_TICKET_MAPPING = {
    "Ticket": "provider record",
    "namespace": "Plane label",
    "Employee": "Plane member mapping or AITeamOS employee_id in comment metadata",
    "assignee": "Plane assignee when mapped, otherwise AITeamOS event projection",
    "report": "Plane comment with AITeamOS metadata",
    "validation": "Plane comment plus AITeamOS validation event projection",
    "state": "Plane state mapping table",
    "evidence": "tagged Plane comment link",
    "asset_link": "AITeamOS asset graph edge plus optional Plane comment backlink",
}


def _default_backend_settings() -> TicketBackendSettings:
    return TicketBackendSettings(
        mode="plane",
        saved_paths={
            "settings": _relative(_backend_settings_path()),
            "plane_projection": ".aiteamos/tickets/plane",
        },
        supported_modes=SUPPORTED_BACKENDS,
    )


def _plane_backend_setup_summary(settings: TicketBackendSettings) -> dict[str, Any]:
    api_key_env = settings.plane_api_key_env.strip() or "PLANE_API_KEY"
    selected = settings.mode == "plane"
    workspace_configured = bool(settings.plane_workspace_slug.strip())
    project_configured = bool(settings.plane_project_id.strip())
    api_key_configured = bool(os.environ.get(api_key_env))
    setup_required: list[str] = []
    if not selected:
        setup_required.extend(["PUT /api/v1/tickets/backend mode=plane", ".aiteamos/tickets/backend.json mode=plane"])
    if not workspace_configured:
        setup_required.append("plane_workspace_slug")
    if not project_configured:
        setup_required.append("plane_project_id")
    if not api_key_configured:
        setup_required.append(api_key_env)
    scope_summary = _plane_repository_scope_summary()
    configured = workspace_configured and project_configured and api_key_configured
    detail = "Plane Ticket Backend is selected and configured."
    if not selected and not configured:
        detail = "Plane Ticket Backend is not selected and Plane workspace/project setup is incomplete."
    elif not selected:
        detail = "Plane Ticket Backend setup is configured, but the active Ticket backend mode is not Plane."
    elif not configured:
        detail = "Plane Ticket Backend is selected, but Plane workspace/project setup is incomplete."
    return {
        "status": "ready" if selected and configured else "setup_blocked",
        "detail": detail,
        "selected": selected,
        "configured": configured,
        "active_mode": settings.mode,
        "active_provider": "plane" if selected else "",
        "required_mode": "plane",
        "workspace_configured": workspace_configured,
        "project_configured": project_configured,
        "api_key_env": api_key_env,
        "api_key_configured": api_key_configured,
        "setup_required": setup_required,
        "settings_path": _relative(_backend_settings_path()),
        "setup_endpoint": "/api/v1/tickets/backend",
        **scope_summary,
    }


def _plane_release_target_summary(
    settings: TicketBackendSettings,
    plane_setup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    setup = plane_setup or _plane_backend_setup_summary(settings)
    scope_status = str(setup.get("code_repository_scope_status") or "")
    blockers: list[str] = []
    setup_required = [str(item) for item in setup.get("setup_required", []) if str(item)]
    if not setup.get("selected"):
        blockers.append("plane_ticket_backend_not_selected")
    if not setup.get("workspace_configured"):
        blockers.append("plane_workspace_slug_missing")
    if not setup.get("project_configured"):
        blockers.append("plane_project_id_missing")
    if not setup.get("api_key_configured"):
        blockers.append("plane_api_key_missing")
    if scope_status != "available":
        blockers.append("code_repository_plane_scope_incomplete")
    ready = not blockers
    setup_action = "none"
    if blockers:
        setup_action = "configure_plane_ticket_backend"
    if "code_repository_plane_scope_incomplete" in blockers:
        setup_action = "configure_code_repository_plane_scope"
    if "plane_ticket_backend_not_selected" in blockers:
        setup_action = "select_plane_ticket_backend"
    detail = (
        "Plan v8 release target is ready: Plane is active, configured, and backed by an available Code Repository Plane scope."
        if ready
        else "Plan v8 release requires Plane as the active Ticket Backend, complete Plane workspace/project/API setup, and an available Code Repository Plane scope."
    )
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "detail": detail,
        "active_mode": settings.mode,
        "required_mode": "plane",
        "required_scope_status": "available",
        "code_repository_scope_status": scope_status,
        "blockers": blockers,
        "setup_required": list(dict.fromkeys(setup_required)),
        "setup_action": setup_action,
    }


def _plane_repository_scope_summary() -> dict[str, Any]:
    return code_repository_plane_scope_summary()


def _write_backend_settings(settings: TicketBackendSettings) -> TicketBackendSettings:
    path = _backend_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "mode": settings.mode,
                "local_file_path": settings.local_file_path,
                "plane_api_base_url": settings.plane_api_base_url,
                "plane_web_base_url": settings.plane_web_base_url,
                "plane_workspace_slug": settings.plane_workspace_slug,
                "plane_project_id": settings.plane_project_id,
                "plane_api_key_env": settings.plane_api_key_env,
                "plane_namespace_strategy": settings.plane_namespace_strategy,
                "plane_namespace_label_ids": settings.plane_namespace_label_ids,
                "plane_state_ids": settings.plane_state_ids,
                "plane_employee_assignee_ids": settings.plane_employee_assignee_ids,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    settings.saved_paths = {
        "settings": _relative(path),
        "plane_projection": ".aiteamos/tickets/plane",
    }
    settings.supported_modes = SUPPORTED_BACKENDS
    return settings


def ticket_backend_settings() -> TicketBackendSettings:
    path = _backend_settings_path()
    defaults = _default_backend_settings()
    if not path.exists():
        return defaults
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        settings = TicketBackendSettings.model_validate({**defaults.model_dump(), **payload})
    except (OSError, json.JSONDecodeError, ValueError):
        settings = defaults
    settings.supported_modes = SUPPORTED_BACKENDS
    settings.saved_paths = {
        "settings": _relative(path),
        "plane_projection": ".aiteamos/tickets/plane",
    }
    return settings


def update_ticket_backend_settings(request: TicketBackendSettingsUpdateRequest) -> TicketBackendSettings:
    supported = {entry.id for entry in SUPPORTED_BACKENDS}
    mode = request.mode.strip() or "plane"
    if mode not in supported:
        raise ValueError(f"Unsupported Ticket backend: {mode}")
    local_file_path = request.local_file_path.strip() or ".aiteamos/tickets/index.json"
    settings = TicketBackendSettings(
        mode=mode,
        local_file_path=local_file_path,
        plane_api_base_url=(request.plane_api_base_url.strip() or "https://api.plane.so").rstrip("/"),
        plane_web_base_url=(request.plane_web_base_url.strip() or "https://app.plane.so").rstrip("/"),
        plane_workspace_slug=request.plane_workspace_slug.strip(),
        plane_project_id=request.plane_project_id.strip(),
        plane_api_key_env=request.plane_api_key_env.strip() or "PLANE_API_KEY",
        plane_namespace_strategy=request.plane_namespace_strategy.strip() or "label",
        plane_namespace_label_ids={key.strip().lower(): value.strip() for key, value in request.plane_namespace_label_ids.items() if key.strip() and value.strip()},
        plane_state_ids={key.strip().lower(): value.strip() for key, value in request.plane_state_ids.items() if key.strip() and value.strip()},
        plane_employee_assignee_ids={key.strip().lower(): value.strip() for key, value in request.plane_employee_assignee_ids.items() if key.strip() and value.strip()},
    )
    return _write_backend_settings(settings)


def discover_ticket_backend_plane_scope() -> TicketBackendPlaneScopeDiscovery:
    return PlaneTicketAdapter(ticket_backend_settings()).discover_plane_scope()


def _resolve_local_file_path(settings: TicketBackendSettings) -> Path:
    configured = Path(settings.local_file_path)
    if configured.is_absolute():
        return configured.resolve()
    return (_workspace_root() / configured).resolve()


def _normalize_namespace(value: str | None) -> str:
    namespace = (value or "").strip().lower()
    aliases = {
        "release": "rel",
        "memory": "mem",
        "docs": "doc",
        "knowledge": "doc",
        "report": "trace",
    }
    namespace = aliases.get(namespace, namespace)
    if not namespace:
        return ""
    if namespace not in _KNOWN_NAMESPACES or not _SAFE_NAMESPACE_RE.fullmatch(namespace):
        raise ValueError(f"Unsupported Ticket type: {value}")
    return namespace


def _namespace_for_role(role: str) -> str:
    normalized = role.strip().lower()
    for namespace, tokens in _ROLE_NAMESPACE_RULES:
        if any(token in normalized for token in tokens):
            return namespace
    return "ops" if any(token in normalized for token in _MANAGER_ROLES) else ""


def _role_can_manage_all(role: str) -> bool:
    normalized = role.strip().lower()
    return any(token in normalized for token in _MANAGER_ROLES)


def _employee_role(employee_id: str) -> str:
    normalized = employee_id.strip().lower()
    if not normalized:
        return ""
    if normalized == CLARA_SYSTEM_EMPLOYEE_ID:
        return CLARA_SYSTEM_ROLE
    path = _employees_dir() / f"{normalized}.yaml"
    if not path.exists():
        return ""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("role") or "")


def _validation_employee_from_text(content: str) -> str:
    arrow_match = re.search(r"->\s*([A-Za-z][A-Za-z0-9_-]{1,63})", content)
    if arrow_match:
        return arrow_match.group(1).strip().lower()
    named_match = re.search(r"\b(Peter|Alex|Clara|Maya)\b", content, re.IGNORECASE)
    return named_match.group(1).strip().lower() if named_match else ""


def _resolve_actor_role(actor_employee_id: str, actor_role: str) -> str:
    explicit = actor_role.strip()
    if explicit:
        return explicit
    return _employee_role(actor_employee_id) or (CLARA_SYSTEM_ROLE if actor_employee_id.strip().lower() == CLARA_SYSTEM_EMPLOYEE_ID else "")


def _infer_ticket_namespace(request: TicketCreateRequest, actor_role: str) -> str:
    requested = _normalize_namespace(request.ticket_type)
    if requested:
        return requested
    assigned_namespace = _namespace_for_role(request.assigned_role)
    if assigned_namespace:
        return assigned_namespace
    actor_namespace = _namespace_for_role(actor_role)
    if actor_namespace:
        return actor_namespace
    return "ops"


def _ensure_namespace_authority(namespace: str, *, actor_employee_id: str, actor_role: str) -> None:
    if _role_can_manage_all(actor_role):
        return
    allowed_namespace = _namespace_for_role(actor_role)
    if allowed_namespace == namespace:
        return
    actor_label = actor_employee_id or "unknown actor"
    role_label = actor_role or "unknown role"
    raise ValueError(f"{actor_label} ({role_label}) cannot create {namespace} Tickets.")


def _terminal_status(status: str) -> bool:
    return status.lower() in {"validated", "completed", "done", "closed", "cancelled"}


_VALIDATION_PASS_REPORT_TYPES = {"validation", "validation_passed", "validation_pass", "passed"}
_VALIDATION_FAILURE_REPORT_TYPES = {
    "validation_failed",
    "validation_rejected",
    "failed",
    "failure",
    "blocked",
    "human_review",
    "human_review_requested",
    "request_human_review",
}


def _is_validation_pass_report_type(report_type: str) -> bool:
    return report_type.strip().lower() in _VALIDATION_PASS_REPORT_TYPES


def _is_validation_failure_report_type(report_type: str) -> bool:
    return report_type.strip().lower() in _VALIDATION_FAILURE_REPORT_TYPES


def _next_action(ticket: Ticket) -> str:
    normalized = ticket.status.lower()
    if normalized in {"validated", "completed", "done", "closed"}:
        return "Ready for Clara summary"
    if normalized in {"blocked", "failed"}:
        return "Needs Clara or human unblock"
    if normalized in {"reported", "review", "pending_validation", "validation", "waiting_validation"}:
        return f"PV review by {ticket.validation_employee_id or ticket.validation_role or 'PV'}"
    return f"{ticket.assigned_employee_id or ticket.assigned_role or 'Assignee'} investigates and reports"


def _ticket_evidence_refs(ticket: Ticket, pending_evidence: list[str] | None = None) -> list[str]:
    evidence_refs: list[str] = []
    for report in ticket.reports:
        evidence_refs.extend(entry.strip() for entry in report.evidence if entry.strip())
    evidence_refs.extend(entry.strip() for entry in (pending_evidence or []) if entry.strip())
    return sorted(set(evidence_refs))


def _ticket_evidence_profile(ticket: Ticket) -> str:
    text = " ".join(
        [
            ticket.ticket_type,
            ticket.title,
            ticket.description,
            " ".join(ticket.code_repository_ids),
            " ".join(ticket.knowledge_refs),
        ]
    ).lower()
    if ticket.ticket_type == "doc":
        return "docs_change"
    if any(token in text for token in ("frontend", "dashboard", "react", "vite", "tsx", "css")) or re.search(r"\bui\b", text):
        return "frontend_change"
    if any(token in text for token in ("plane", "graphiti", "adapter", "integration", "connector", "api smoke")):
        return "integration_change"
    if any(token in text for token in ("prompt", "model", "llm", "ai engine", "deepseek", "openai")):
        return "model_prompt_change"
    if any(token in text for token in ("docs", "doc ", "guide", "prd", "architecture")):
        return "docs_change"
    if ticket.code_repository_ids or ticket.ticket_type in {"rd", "rel"} or any(token in text for token in ("backend", "api", "service", "pytest", "python")):
        return "backend_change"
    return "general"


def _recommended_evidence_commands(profile: str) -> list[str]:
    return {
        "docs_change": ["focused doc/product review evidence"],
        "frontend_change": ["cd apps/dashboard && npm test", "cd apps/dashboard && npm run build"],
        "backend_change": ["pytest"],
        "integration_change": ["pytest focused integration smoke", "pytest"],
        "model_prompt_change": ["focused Chat / AI Engine smoke"],
    }.get(profile, [])


def _ticket_evidence_requirements_from_ticket(ticket: Ticket, pending_evidence: list[str] | None = None) -> TicketEvidenceRequirements:
    profile = _ticket_evidence_profile(ticket)
    evidence_refs = _ticket_evidence_refs(ticket, pending_evidence)
    requires_validation_evidence = profile != "general"
    requirement = TicketEvidenceRequirement(
        id=f"{profile}:validation_evidence",
        label="Validation evidence recorded",
        required=requires_validation_evidence,
        satisfied=(not requires_validation_evidence) or bool(evidence_refs),
        evidence_refs=evidence_refs,
        recommended_commands=_recommended_evidence_commands(profile),
        detail=(
            "This Ticket profile requires at least one evidence ref before it can be marked validated."
            if requires_validation_evidence
            else "No mandatory validation evidence profile was inferred for this Ticket."
        ),
    )
    missing_required = [requirement.id] if requirement.required and not requirement.satisfied else []
    return TicketEvidenceRequirements(
        ticket_id=ticket.id,
        ticket_type=ticket.ticket_type,
        profile=profile,
        satisfied=not missing_required,
        missing_required=missing_required,
        evidence_refs=evidence_refs,
        requirements=[requirement],
    )


def _ensure_validation_evidence(ticket: Ticket, pending_evidence: list[str]) -> None:
    requirements = _ticket_evidence_requirements_from_ticket(ticket, pending_evidence)
    if requirements.satisfied:
        return
    commands = [
        command
        for requirement in requirements.requirements
        for command in requirement.recommended_commands
    ]
    command_hint = f" Recommended evidence: {', '.join(commands)}." if commands else ""
    raise ValueError(
        "Validation evidence blocker: "
        f"{requirements.profile} Ticket requires evidence before it can be marked validated."
        f" Missing: {', '.join(requirements.missing_required)}."
        + command_hint
    )


def _event(ticket_id: str, event_type: str, *, actor_id: str, actor_role: str, data: dict[str, Any], at: str | None = None) -> TicketEvent:
    return TicketEvent(
        event_id=f"evt-{uuid4().hex[:12]}",
        ticket_id=ticket_id,
        type=event_type,
        at=at or _now(),
        actor={"kind": "employee" if actor_id else "system", "id": actor_id, "role": actor_role},
        data=data,
    )


class TicketAdapter(Protocol):
    def list_tickets(self, status: str | None = None) -> list[Ticket]: ...

    def create_ticket(self, request: TicketCreateRequest) -> Ticket: ...

    def get_ticket(self, ticket_id: str) -> Ticket | None: ...

    def get_ticket_events(self, ticket_id: str) -> list[TicketEvent]: ...

    def add_ticket_report(self, ticket_id: str, request: TicketReportRequest) -> Ticket: ...

    def request_ticket_validation(self, ticket_id: str, request: TicketValidationRequest) -> Ticket: ...

    def record_ticket_handoff(self, ticket_id: str, request: TicketHandoffRequest) -> Ticket: ...

    def transition_ticket_state(self, ticket_id: str, request: TicketStateTransitionRequest) -> Ticket: ...

    def employee_work_ledger(self, employee_id: str) -> EmployeeWorkLedger: ...

    def ticket_asset_records(self) -> list[TicketAssetRecord]: ...

    def status(self) -> TicketBackendStatus: ...

    def external_smoke(self) -> dict[str, Any]: ...

    def action_smoke(self, request: TicketProviderActionSmokeRequest) -> TicketProviderActionSmokeResponse: ...


class LocalFileTicketAdapter:
    def __init__(self, settings: TicketBackendSettings):
        self.settings = settings
        self.index_path = _resolve_local_file_path(settings)
        self.root = self.index_path.parent
        self.counters_path = self.root / "counters.json"

    def _event_files(self) -> list[Path]:
        return sorted(self.root.glob("*/*.ticket.jsonl"))

    def external_smoke(self) -> dict[str, Any]:
        status = self.status()
        return {
            "status": "passed" if status.status == "ready" else status.status,
            "checks": ["local_file_ticket_index_read"],
            "warnings": [],
            "failures": [],
            "blockers": [],
            "evidence": {
                "mode": status.mode,
                "ticket_count": status.ticket_count,
                "local_file_path": status.local_file_path,
            },
            "external_calls": False,
        }

    def action_smoke(self, request: TicketProviderActionSmokeRequest) -> TicketProviderActionSmokeResponse:
        status = self.status()
        return TicketProviderActionSmokeResponse(
            status="skipped",
            provider="local_file",
            checks=["local_file_ticket_backend_active", "plane_action_smoke_skipped"],
            warnings=["plane_action_smoke_requires_plane_backend"],
            evidence={"ticket_backend_status": status.model_dump(mode="json")},
            summary={
                "ticket_backend_status": status.status,
                "reason": "Local file Ticket backend has no external Plane action path.",
            },
        )

    def _ticket_file(self, namespace: str, ticket_id: str) -> Path:
        return self.root / namespace / f"{ticket_id}.ticket.jsonl"

    def _ticket_file_by_id(self, ticket_id: str) -> Path | None:
        if not LOCAL_TICKET_ID_RE.fullmatch(ticket_id):
            return None
        namespace = ticket_id.split("-", maxsplit=1)[0].lower()
        path = self._ticket_file(namespace, ticket_id.lower())
        if path.exists():
            return path
        return next((candidate for candidate in self._event_files() if candidate.stem.removesuffix(".ticket") == ticket_id), None)

    def _read_events_from_file(self, path: Path) -> list[TicketEvent]:
        events: list[TicketEvent] = []
        if not path.exists():
            return events
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(TicketEvent.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValueError):
                continue
        return events

    def _append_events(self, path: Path, events: list[TicketEvent]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n")
        self._write_index(self._load_items())

    def _read_counters(self) -> dict[str, int]:
        if not self.counters_path.exists():
            return {}
        try:
            payload = json.loads(self.counters_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(key): int(value) for key, value in payload.items() if isinstance(value, int)}

    def _write_counters(self, counters: dict[str, int]) -> None:
        self.counters_path.parent.mkdir(parents=True, exist_ok=True)
        self.counters_path.write_text(json.dumps(counters, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _max_existing_number(self, namespace: str) -> int:
        max_value = 0
        pattern = re.compile(rf"^{re.escape(namespace)}-(\d+)$")
        for path in self.root.glob(f"{namespace}/{namespace}-*.ticket.jsonl"):
            match = pattern.fullmatch(path.stem.removesuffix(".ticket"))
            if match:
                max_value = max(max_value, int(match.group(1)))
        return max_value

    def _next_ticket_id(self, namespace: str) -> str:
        counters = self._read_counters()
        next_number = max(counters.get(namespace, 0), self._max_existing_number(namespace)) + 1
        counters[namespace] = next_number
        self._write_counters(counters)
        return f"{namespace}-{next_number:04d}"

    def _write_index(self, items: list[Ticket]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _project_ticket(self, events: list[TicketEvent], path: Path) -> Ticket | None:
        if not events:
            return None
        ticket_id = events[0].ticket_id
        namespace = ticket_id.split("-", maxsplit=1)[0].lower()
        state: dict[str, Any] = {
            "id": ticket_id,
            "title": ticket_id,
            "description": "",
            "status": "open",
            "ticket_type": namespace,
            "assigned_employee_id": "",
            "assigned_role": "",
            "validation_employee_id": "",
            "validation_role": "",
            "knowledge_refs": [],
            "code_repository_ids": [],
            "source_thread_id": "",
            "source_run_id": "",
            "reports": [],
            "created_at": events[0].at,
            "updated_at": events[-1].at,
            "saved_path": _relative(path),
            "events": events,
        }
        for event in events:
            data = event.data
            state["updated_at"] = event.at
            if event.type == "created":
                state.update(
                    {
                        "title": str(data.get("title") or state["title"]),
                        "description": str(data.get("description") or data.get("title") or state["description"]),
                        "status": str(data.get("status") or state["status"]),
                        "ticket_type": str(data.get("ticket_type") or namespace),
                        "knowledge_refs": [str(item) for item in data.get("knowledge_refs", []) if str(item).strip()],
                        "code_repository_ids": [str(item) for item in data.get("code_repository_ids", []) if str(item).strip()],
                        "source_thread_id": str(data.get("source_thread_id") or ""),
                        "source_run_id": str(data.get("source_run_id") or ""),
                    }
                )
                state["created_at"] = event.at
            elif event.type == "assigned":
                state["assigned_employee_id"] = str(data.get("assigned_employee_id") or data.get("to_employee_id") or "")
                state["assigned_role"] = str(data.get("assigned_role") or data.get("to_role") or "")
            elif event.type == "validation_requested":
                state["validation_employee_id"] = str(data.get("validation_employee_id") or data.get("to_employee_id") or "")
                state["validation_role"] = str(data.get("validation_role") or data.get("to_role") or "")
            elif event.type in {"reported", "validated", "blocked"}:
                report_payload = data.get("report")
                if isinstance(report_payload, dict):
                    report = TicketReport.model_validate({**report_payload, "source_event_id": event.event_id})
                    state["reports"].append(report)
            elif event.type == "status_changed":
                state["status"] = str(data.get("to") or data.get("status") or state["status"])
            elif event.type == "asset_linked":
                target_kind = str(data.get("target_kind") or "")
                target_ref = str(data.get("target_ref") or "")
                if target_kind == "knowledge" and target_ref and target_ref not in state["knowledge_refs"]:
                    state["knowledge_refs"].append(target_ref)
                if target_kind == "repository" and target_ref and target_ref not in state["code_repository_ids"]:
                    state["code_repository_ids"].append(target_ref)
        return Ticket.model_validate(state)

    def _load_items(self) -> list[Ticket]:
        items = [
            ticket
            for ticket in (self._project_ticket(self._read_events_from_file(path), path) for path in self._event_files())
            if ticket is not None
        ]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def list_tickets(self, status: str | None = None) -> list[Ticket]:
        items = self._load_items()
        if status:
            items = [item for item in items if item.status == status]
        self._write_index(items)
        return items

    def create_ticket(self, request: TicketCreateRequest) -> Ticket:
        actor_id = request.actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID
        actor_role = _resolve_actor_role(actor_id, request.actor_role)
        namespace = _infer_ticket_namespace(request, actor_role)
        _ensure_namespace_authority(namespace, actor_employee_id=actor_id, actor_role=actor_role)
        assigned_employee_id = request.assigned_employee_id.strip()
        assigned_role = request.assigned_role.strip()
        if not (assigned_employee_id or assigned_role):
            raise ValueError("Ticket requires an assignee Employee or assigned role.")

        timestamp = _now()
        item_id = self._next_ticket_id(namespace)
        initial_status = "assigned"
        events = [
            _event(
                item_id,
                "created",
                actor_id=actor_id,
                actor_role=actor_role,
                at=timestamp,
                data={
                    "title": request.title.strip(),
                    "description": request.description.strip() or request.title.strip(),
                    "status": initial_status,
                    "ticket_type": namespace,
                    "knowledge_refs": sorted({item.strip() for item in request.knowledge_refs if item.strip()}),
                    "code_repository_ids": sorted({item.strip() for item in request.code_repository_ids if item.strip()}),
                    "source_thread_id": request.source_thread_id.strip(),
                    "source_run_id": request.source_run_id.strip(),
                },
            )
        ]
        events.append(
            _event(
                item_id,
                "assigned",
                actor_id=actor_id,
                actor_role=actor_role,
                at=timestamp,
                data={
                    "assigned_employee_id": assigned_employee_id,
                    "assigned_role": assigned_role,
                },
            )
        )
        if request.validation_employee_id.strip() or request.validation_role.strip():
            events.append(
                _event(
                    item_id,
                    "validation_requested",
                    actor_id=actor_id,
                    actor_role=actor_role,
                    at=timestamp,
                    data={
                        "validation_employee_id": request.validation_employee_id.strip(),
                        "validation_role": request.validation_role.strip(),
                    },
                )
            )
        for ref in sorted({item.strip() for item in request.knowledge_refs if item.strip()}):
            events.append(_event(item_id, "asset_linked", actor_id=actor_id, actor_role=actor_role, at=timestamp, data={"target_kind": "knowledge", "target_ref": ref}))
        for ref in sorted({item.strip() for item in request.code_repository_ids if item.strip()}):
            events.append(_event(item_id, "asset_linked", actor_id=actor_id, actor_role=actor_role, at=timestamp, data={"target_kind": "repository", "target_ref": ref}))

        path = self._ticket_file(namespace, item_id)
        self._append_events(path, events)
        item = self.get_ticket(item_id)
        if item is None:  # Defensive; append just succeeded.
            raise ValueError(f"Ticket was not persisted: {item_id}")
        return item

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        path = self._ticket_file_by_id(ticket_id.strip())
        if path is None:
            return None
        return self._project_ticket(self._read_events_from_file(path), path)

    def get_ticket_events(self, ticket_id: str) -> list[TicketEvent]:
        path = self._ticket_file_by_id(ticket_id.strip())
        return self._read_events_from_file(path) if path is not None else []

    def add_ticket_report(self, ticket_id: str, request: TicketReportRequest) -> Ticket:
        item = self.get_ticket(ticket_id)
        path = self._ticket_file_by_id(ticket_id.strip())
        if item is None or path is None:
            raise KeyError(ticket_id)

        timestamp = _now()
        reporter_id = request.reporter_employee_id.strip()
        reporter_role = request.reporter_role.strip() or _employee_role(reporter_id)
        report_type = request.report_type.strip() or "progress"
        evidence = [entry.strip() for entry in request.evidence if entry.strip()]
        if _is_validation_pass_report_type(report_type):
            _ensure_validation_evidence(item, evidence)
        report = TicketReport(
            id=f"report-{uuid4().hex[:10]}",
            reporter_employee_id=reporter_id,
            reporter_role=reporter_role,
            content=request.content.strip(),
            evidence=evidence,
            report_type=report_type,
            created_at=timestamp,
        )
        if _is_validation_pass_report_type(report_type):
            event_type = "validated"
            next_status = "validated"
        elif _is_validation_failure_report_type(report_type):
            event_type = "blocked"
            next_status = "blocked"
        elif report_type in {"result", "done", "completed"}:
            event_type = "reported"
            next_status = "reported"
        else:
            event_type = "reported"
            next_status = item.status

        events = [
            _event(
                item.id,
                event_type,
                actor_id=reporter_id,
                actor_role=reporter_role,
                at=timestamp,
                data={
                    "report": report.model_dump(mode="json"),
                    "source_run_id": request.source_run_id.strip(),
                },
            )
        ]
        if next_status != item.status:
            events.append(
                _event(
                    item.id,
                    "status_changed",
                    actor_id=reporter_id,
                    actor_role=reporter_role,
                    at=timestamp,
                    data={"from": item.status, "to": next_status, "reason": f"report:{report.id}"},
                )
            )
        for evidence in report.evidence:
            events.append(
                _event(
                    item.id,
                    "asset_linked",
                    actor_id=reporter_id,
                    actor_role=reporter_role,
                    at=timestamp,
                    data={"target_kind": "evidence", "target_ref": evidence, "source_report_id": report.id},
                )
            )
        self._append_events(path, events)
        updated = self.get_ticket(item.id)
        if updated is None:
            raise KeyError(ticket_id)
        return updated

    def request_ticket_validation(self, ticket_id: str, request: TicketValidationRequest) -> Ticket:
        item = self.get_ticket(ticket_id)
        path = self._ticket_file_by_id(ticket_id.strip())
        if item is None or path is None:
            raise KeyError(ticket_id)
        validation_employee_id = request.validation_employee_id.strip()
        validation_role = request.validation_role.strip()
        if not (validation_employee_id or validation_role):
            raise ValueError("Ticket validation request requires a validation Employee or role.")

        actor_id = request.actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID
        actor_role = _resolve_actor_role(actor_id, request.actor_role)
        event = _event(
            item.id,
            "validation_requested",
            actor_id=actor_id,
            actor_role=actor_role,
            data={
                "validation_employee_id": validation_employee_id,
                "validation_role": validation_role,
                "content": request.content.strip(),
                "source_run_id": request.source_run_id.strip(),
            },
        )
        self._append_events(path, [event])
        updated = self.get_ticket(item.id)
        if updated is None:
            raise KeyError(ticket_id)
        return updated

    def record_ticket_handoff(self, ticket_id: str, request: TicketHandoffRequest) -> Ticket:
        item = self.get_ticket(ticket_id)
        path = self._ticket_file_by_id(ticket_id.strip())
        if item is None or path is None:
            raise KeyError(ticket_id)
        to_employee_id = request.to_employee_id.strip()
        to_role = request.to_role.strip()
        if not (to_employee_id or to_role):
            raise ValueError("Ticket handoff requires a target Employee or role.")

        actor_id = request.actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID
        actor_role = _resolve_actor_role(actor_id, request.actor_role)
        timestamp = _now()
        events = [
            _event(
                item.id,
                "handoff_requested",
                actor_id=actor_id,
                actor_role=actor_role,
                at=timestamp,
                data={
                    "from_employee_id": request.from_employee_id.strip() or item.assigned_employee_id,
                    "from_role": request.from_role.strip() or item.assigned_role,
                    "to_employee_id": to_employee_id,
                    "to_role": to_role,
                    "content": request.content.strip(),
                    "source_run_id": request.source_run_id.strip(),
                },
            ),
            _event(
                item.id,
                "assigned",
                actor_id=actor_id,
                actor_role=actor_role,
                at=timestamp,
                data={
                    "assigned_employee_id": to_employee_id,
                    "assigned_role": to_role,
                    "source_run_id": request.source_run_id.strip(),
                },
            ),
        ]
        self._append_events(path, events)
        updated = self.get_ticket(item.id)
        if updated is None:
            raise KeyError(ticket_id)
        return updated

    def transition_ticket_state(self, ticket_id: str, request: TicketStateTransitionRequest) -> Ticket:
        item = self.get_ticket(ticket_id)
        path = self._ticket_file_by_id(ticket_id.strip())
        if item is None or path is None:
            raise KeyError(ticket_id)
        next_status = request.status.strip().lower()
        if not next_status:
            raise ValueError("Ticket state transition requires a status.")
        actor_id = request.actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID
        actor_role = _resolve_actor_role(actor_id, request.actor_role)
        event = _event(
            item.id,
            "status_changed",
            actor_id=actor_id,
            actor_role=actor_role,
            data={
                "from": item.status,
                "to": next_status,
                "source_run_id": request.source_run_id.strip(),
            },
        )
        self._append_events(path, [event])
        updated = self.get_ticket(item.id)
        if updated is None:
            raise KeyError(ticket_id)
        return updated

    def employee_work_ledger(self, employee_id: str) -> EmployeeWorkLedger:
        normalized = employee_id.strip()
        current: dict[str, TicketWorkItem] = {}
        historical: dict[str, TicketWorkItem] = {}
        reports: list[EmployeeTicketReportRecord] = []
        validations: list[EmployeeTicketReportRecord] = []
        blocked_records: list[EmployeeTicketReportRecord] = []
        handoffs: list[dict[str, Any]] = []

        for ticket in self._load_items():
            roles: set[str] = set()
            if ticket.assigned_employee_id == normalized:
                roles.add("owner")
            if ticket.validation_employee_id == normalized:
                roles.add("validator")
            for event in ticket.events:
                actor_id = event.actor.get("id", "")
                event_data = event.data if isinstance(event.data, dict) else {}
                handoff_employee_ids = {
                    actor_id,
                    str(event_data.get("from_employee_id") or ""),
                    str(event_data.get("to_employee_id") or ""),
                }
                if normalized in handoff_employee_ids and event.type.startswith("handoff"):
                    roles.add("handoff")
                    handoffs.append(
                        {
                            "ticket_id": ticket.id,
                            "title": ticket.title,
                            "relation": (
                                "target"
                                if str(event_data.get("to_employee_id") or "") == normalized
                                else ("source" if str(event_data.get("from_employee_id") or "") == normalized else "actor")
                            ),
                            "event": event.model_dump(mode="json"),
                        }
                    )
            for report in ticket.reports:
                if report.reporter_employee_id != normalized:
                    continue
                roles.add("reporter")
                record = EmployeeTicketReportRecord(
                    ticket_id=ticket.id,
                    ticket_title=ticket.title,
                    report_id=report.id,
                    report_type=report.report_type,
                    content=report.content,
                    evidence=report.evidence,
                    created_at=report.created_at,
                )
                reports.append(record)
                if _is_validation_pass_report_type(report.report_type):
                    validations.append(record)
                if _is_validation_failure_report_type(report.report_type):
                    blocked_records.append(record)
            if not roles:
                continue
            item = TicketWorkItem(
                ticket_id=ticket.id,
                title=ticket.title,
                status=ticket.status,
                role=", ".join(sorted(roles)),
                updated_at=ticket.updated_at,
                next_action=_next_action(ticket),
            )
            historical[ticket.id] = item
            if not _terminal_status(ticket.status):
                current[ticket.id] = item

        return _augment_employee_work_ledger(EmployeeWorkLedger(
            employee_id=normalized,
            current_tickets=sorted(current.values(), key=lambda item: item.updated_at, reverse=True),
            historical_tickets=sorted(historical.values(), key=lambda item: item.updated_at, reverse=True),
            reports=sorted(reports, key=lambda item: item.created_at, reverse=True),
            validations=sorted(validations, key=lambda item: item.created_at, reverse=True),
            blocked_records=sorted(blocked_records, key=lambda item: item.created_at, reverse=True),
            handoffs=handoffs,
            contribution={
                "ticket_count": len(historical),
                "current_ticket_count": len(current),
                "report_count": len(reports),
                "validation_count": len(validations),
                "blocked_count": len(blocked_records),
                "handoff_count": len(handoffs),
            },
        ))

    def ticket_asset_records(self) -> list[TicketAssetRecord]:
        records: list[TicketAssetRecord] = []
        for ticket in self._load_items():
            scopes = [ticket.ticket_type, *ticket.knowledge_refs]
            assigned = [value for value in [ticket.assigned_employee_id, ticket.validation_employee_id] if value]
            for report in ticket.reports:
                status = "approved" if _is_validation_pass_report_type(report.report_type) else "candidate"
                records.append(
                    TicketAssetRecord(
                        id=report.id,
                        kind="report",
                        title=f"{report.report_type} report for {ticket.id}",
                        status=status,
                        source_ticket_id=ticket.id,
                        source_employee_id=report.reporter_employee_id,
                        assigned_employees=assigned,
                        scopes=scopes,
                        created_at=report.created_at,
                        updated_at=report.created_at,
                        metadata={"ticket_title": ticket.title, "report": report.model_dump(mode="json")},
                    )
                )
                for index, evidence in enumerate(report.evidence):
                    records.append(
                        TicketAssetRecord(
                            id=f"{report.id}:evidence:{index}",
                            kind="evidence",
                            title=evidence,
                            status=status,
                            source_ticket_id=ticket.id,
                            source_employee_id=report.reporter_employee_id,
                            assigned_employees=assigned,
                            scopes=scopes,
                            created_at=report.created_at,
                            updated_at=report.created_at,
                            metadata={"ticket_title": ticket.title, "report_id": report.id, "evidence": evidence},
                        )
                    )
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def status(self) -> TicketBackendStatus:
        items = self._load_items()
        self._write_index(items)
        plane_setup = _plane_backend_setup_summary(self.settings)
        return TicketBackendStatus(
            mode=self.settings.mode,
            status="ready",
            detail="Local append-only Ticket backend is active.",
            ticket_count=len(items),
            local_file_path=_relative(self.index_path),
            plane_setup=plane_setup,
            release_target=_plane_release_target_summary(self.settings, plane_setup),
            saved_paths={
                "settings": _relative(_backend_settings_path()),
                "local_file": _relative(self.index_path),
                "counters": _relative(self.counters_path),
                "tickets": _relative(self.root),
            },
            supported_modes=SUPPORTED_BACKENDS,
        )


def _should_trust_proxy_env(url: str) -> bool:
    host = (urlparse(url).hostname or "").strip().lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    if host.endswith(".localhost"):
        return False
    return True


class PlaneTicketAdapter:
    def __init__(self, settings: TicketBackendSettings):
        self.settings = settings
        self.root = _tickets_dir() / "plane"
        self.index_path = self.root / "index.json"
        self.counters_path = self.root / "counters.json"

    def _setup_required(self) -> list[str]:
        missing: list[str] = []
        if not self.settings.plane_workspace_slug.strip():
            missing.append("plane_workspace_slug")
        if not self.settings.plane_project_id.strip():
            missing.append("plane_project_id")
        env_name = self.settings.plane_api_key_env.strip() or "PLANE_API_KEY"
        if missing or not os.environ.get(env_name):
            missing.append(env_name)
        return missing

    def _ensure_ready(self) -> None:
        missing = self._setup_required()
        if missing:
            raise ValueError(
                "Plane Ticket Backend setup blocker: configure "
                + ", ".join(missing)
                + " before running Ticket actions."
            )

    def _headers(self) -> dict[str, str]:
        env_name = self.settings.plane_api_key_env.strip() or "PLANE_API_KEY"
        token = os.environ.get(env_name, "")
        return {"X-API-Key": token, "Content-Type": "application/json"}

    def _api_url(self, path: str) -> str:
        base = (self.settings.plane_api_base_url.strip() or "https://api.plane.so").rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    def _project_api_path(self) -> str:
        workspace = quote(self.settings.plane_workspace_slug.strip(), safe="")
        project = quote(self.settings.plane_project_id.strip(), safe="")
        return f"/api/v1/workspaces/{workspace}/projects/{project}"

    def _work_items_path(self) -> str:
        return f"{self._project_api_path()}/work-items/"

    def _work_item_path(self, provider_record_id: str) -> str:
        return f"{self._work_items_path()}{quote(provider_record_id, safe='')}/"

    def _comments_path(self, provider_record_id: str) -> str:
        return f"{self._work_item_path(provider_record_id)}comments/"

    def _external_url(self, provider_record_id: str) -> str:
        web_base = (self.settings.plane_web_base_url.strip() or "https://app.plane.so").rstrip("/")
        workspace = quote(self.settings.plane_workspace_slug.strip(), safe="")
        project = quote(self.settings.plane_project_id.strip(), safe="")
        record = quote(provider_record_id, safe="")
        return f"{web_base}/{workspace}/projects/{project}/work-items/{record}"

    def _request(self, method: str, path: str, *, json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_ready()
        url = self._api_url(path)
        max_attempts = 3
        response: httpx.Response | None = None
        for attempt in range(1, max_attempts + 1):
            with httpx.Client(timeout=30, trust_env=_should_trust_proxy_env(url)) as client:
                response = client.request(method, url, headers=self._headers(), json=json_payload)
            if response.status_code not in {429, 502, 503, 504} or attempt == max_attempts:
                break
            time.sleep(0.25 * attempt)
        if response is None:
            raise ValueError("Plane Ticket Backend action blocker: no response")
        if response.status_code >= 400:
            raise ValueError(f"Plane Ticket Backend action blocker: {response.status_code} {response.text[:300]}")
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def _read_only_request(self, path: str) -> Any:
        url = self._api_url(path)
        with httpx.Client(timeout=30, trust_env=_should_trust_proxy_env(url)) as client:
            response = client.request("GET", url, headers=self._headers(), json=None)
        if response.status_code >= 400:
            raise ValueError(f"Plane read-only discovery blocker: {response.status_code} {response.text[:300]}")
        try:
            return response.json()
        except ValueError:
            return {}

    @staticmethod
    def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("results", "data", "workspaces", "projects"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def discover_plane_scope(self) -> TicketBackendPlaneScopeDiscovery:
        api_key_env = self.settings.plane_api_key_env.strip() or "PLANE_API_KEY"
        if not os.environ.get(api_key_env):
            return TicketBackendPlaneScopeDiscovery(
                status="blocked",
                detail=f"Plane scope discovery requires {api_key_env}.",
                api_key_env=api_key_env,
                api_key_configured=False,
                external_calls=False,
                checks=["plane_api_key_missing"],
                setup_required=[api_key_env],
            )

        checks = ["plane_workspace_list_requested"]
        suggestions: list[dict[str, Any]] = []
        workspace_count = 0
        project_count = 0
        try:
            configured_workspaces = self._configured_discovery_workspace_slugs()
            if configured_workspaces:
                checks = ["plane_workspace_slug_configured"]
                workspace_count = len(configured_workspaces)
                for workspace_slug in configured_workspaces[:5]:
                    project_count += self._collect_plane_project_suggestions(
                        workspace_slug=workspace_slug,
                        workspace_name=workspace_slug,
                        suggestions=suggestions,
                        checks=checks,
                    )
                    if len(suggestions) >= 10:
                        break
            else:
                checks = ["plane_workspace_list_requested"]
                workspaces_payload = self._read_only_request("/api/v1/workspaces/")
                workspaces = self._records_from_payload(workspaces_payload)
                workspace_count = len(workspaces)
                for workspace in workspaces[:5]:
                    workspace_slug = str(
                        workspace.get("slug")
                        or workspace.get("workspace_slug")
                        or workspace.get("id")
                        or workspace.get("name")
                        or ""
                    ).strip()
                    if not workspace_slug:
                        continue
                    project_count += self._collect_plane_project_suggestions(
                        workspace_slug=workspace_slug,
                        workspace_name=str(workspace.get("name") or workspace_slug),
                        suggestions=suggestions,
                        checks=checks,
                    )
                    if len(suggestions) >= 10:
                        break
        except Exception as exc:
            return TicketBackendPlaneScopeDiscovery(
                status="failed",
                detail=str(exc),
                api_key_env=api_key_env,
                api_key_configured=True,
                external_calls=True,
                checks=checks,
                setup_required=[],
                suggestions=[],
                evidence={"workspace_count": workspace_count, "project_count": project_count},
            )

        status = "ready" if suggestions else "no_candidates"
        detail = (
            "Plane scope discovery found workspace/project candidates."
            if suggestions
            else "Plane scope discovery completed but found no workspace/project candidates."
        )
        return TicketBackendPlaneScopeDiscovery(
            status=status,
            detail=detail,
            api_key_env=api_key_env,
            api_key_configured=True,
            external_calls=True,
            checks=checks,
            setup_required=[],
            suggestions=suggestions[:10],
            evidence={"workspace_count": workspace_count, "project_count": project_count},
        )

    def _configured_discovery_workspace_slugs(self) -> list[str]:
        values = [
            self.settings.plane_workspace_slug,
            os.environ.get("AITEAMOS_PLANE_WORKSPACE_SLUG", ""),
            os.environ.get("PLANE_WORKSPACE_SLUG", ""),
        ]
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            workspace_slug = str(value or "").strip()
            if not workspace_slug or workspace_slug in seen:
                continue
            seen.add(workspace_slug)
            result.append(workspace_slug)
        return result

    def _collect_plane_project_suggestions(
        self,
        *,
        workspace_slug: str,
        workspace_name: str,
        suggestions: list[dict[str, Any]],
        checks: list[str],
    ) -> int:
        projects_payload = self._read_only_request(f"/api/v1/workspaces/{quote(workspace_slug, safe='')}/projects/")
        projects = self._records_from_payload(projects_payload)
        if "plane_project_list_requested" not in checks:
            checks.append("plane_project_list_requested")
        for project in projects[:10]:
            project_id = str(
                project.get("id")
                or project.get("project_id")
                or project.get("identifier")
                or project.get("slug")
                or ""
            ).strip()
            if not project_id:
                continue
            suggestions.append(
                {
                    "source": "plane_discovery",
                    "plane_workspace_slug": workspace_slug,
                    "plane_project_id": project_id,
                    "workspace_name": workspace_name,
                    "project_name": str(project.get("name") or project_id),
                    "project_identifier": str(project.get("identifier") or ""),
                    "status": "available",
                    "deep_link": "#/settings/code-repositories",
                }
            )
        return len(projects)

    def external_smoke(self) -> dict[str, Any]:
        status = self.status()
        if status.status != "ready":
            return {
                "status": status.status,
                "checks": ["plane_setup_blocker_reported"],
                "warnings": [],
                "failures": [],
                "blockers": [
                    {
                        "id": "ticket:plane:setup",
                        "status": status.status,
                        "detail": status.detail,
                        "setup_required": status.setup_required,
                    }
                ],
                "evidence": {"ticket_backend_status": status.model_dump(mode="json")},
                "external_calls": False,
            }
        try:
            payload = self._request("GET", self._work_items_path())
        except Exception as exc:
            return {
                "status": "failed",
                "checks": ["plane_project_work_items_read"],
                "warnings": [],
                "failures": ["plane_external_smoke_failed"],
                "blockers": [
                    {
                        "id": "ticket:plane:external_smoke",
                        "status": "failed",
                        "detail": str(exc),
                        "setup_required": [],
                    }
                ],
                "evidence": {
                    "endpoint": self._work_items_path(),
                    "provider": "plane",
                },
                "external_calls": True,
            }
        return {
            "status": "passed",
            "checks": ["plane_project_work_items_read", "plane_external_call_completed"],
            "warnings": [],
            "failures": [],
            "blockers": [],
            "evidence": {
                "endpoint": self._work_items_path(),
                "response_keys": sorted(payload.keys())[:12],
                "provider": "plane",
            },
            "external_calls": True,
        }

    def action_smoke(self, request: TicketProviderActionSmokeRequest) -> TicketProviderActionSmokeResponse:
        status = self.status()
        checks: list[str] = ["plane_action_smoke_requested"]
        evidence: dict[str, Any] = {
            "ticket_backend_status": status.model_dump(mode="json"),
            "confirm_env_var": request.confirm_env_var,
            "confirm_env_configured": os.environ.get(request.confirm_env_var, "") == "1",
        }
        if status.status != "ready":
            return TicketProviderActionSmokeResponse(
                status="blocked",
                provider="plane",
                checks=[*checks, "plane_setup_blocker_reported"],
                blockers=[
                    {
                        "id": "ticket:plane:setup",
                        "reason": "ticket_provider_not_ready",
                        "status": status.status,
                        "detail": status.detail,
                        "setup_required": status.setup_required,
                    }
                ],
                evidence=evidence,
                summary={"ticket_backend_status": status.status, "blocker_stage": "setup"},
            )
        if not request.execute or os.environ.get(request.confirm_env_var, "") != "1":
            return TicketProviderActionSmokeResponse(
                status="dry_run",
                provider="plane",
                checks=[*checks, "plane_action_smoke_mutation_gate_checked"],
                blockers=[
                    {
                        "id": "ticket:plane:action_smoke:confirmation",
                        "reason": "plane_action_smoke_not_confirmed",
                        "status": "confirmation_required",
                        "detail": (
                            f"Pass --execute and set {request.confirm_env_var}=1 to run a mutating "
                            "Plane Ticket handoff/report action smoke."
                        ),
                        "setup_required": ["--execute", f"{request.confirm_env_var}=1"],
                    }
                ],
                evidence=evidence,
                summary={"ticket_backend_status": status.status, "mutation_gate_open": False},
            )

        stage = "load_or_create_ticket"
        ticket: Ticket | None = None
        ticket_source = ""
        try:
            if request.ticket_id.strip():
                ticket = self.get_ticket(request.ticket_id.strip())
                ticket_source = "existing"
                if ticket is None:
                    raise KeyError(request.ticket_id.strip())
            elif request.create_ticket_if_missing:
                ticket_source = "created"
                ticket = self.create_ticket(
                    TicketCreateRequest(
                        title="AITeamOS Plane Ticket action smoke",
                        description=(
                            "Opt-in Plan v7 provider action smoke. This Ticket verifies the "
                            "Plane-backed Ticket handoff/report write path before live dogfood."
                        ),
                        ticket_type="ops",
                        assigned_employee_id=request.from_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID,
                        assigned_role=request.from_role.strip() or CLARA_SYSTEM_ROLE,
                        validation_employee_id="peter",
                        validation_role="AI PV",
                        source_thread_id="plane-ticket-action-smoke",
                        source_run_id=request.source_run_id.strip() or "plane-ticket-action-smoke",
                        actor_employee_id=CLARA_SYSTEM_EMPLOYEE_ID,
                        actor_role=CLARA_SYSTEM_ROLE,
                    )
                )
            else:
                raise ValueError("ticket_id is required when create_ticket_if_missing=false.")

            checks.append(f"plane_ticket_{ticket_source}_loaded")
            evidence["ticket_id"] = ticket.id
            evidence["provider_ref"] = ticket.provider_ref.model_dump(mode="json") if ticket.provider_ref else {}

            stage = "record_ticket_handoff"
            handoff = self.record_ticket_handoff(
                ticket.id,
                TicketHandoffRequest(
                    from_employee_id=request.from_employee_id.strip() or ticket.assigned_employee_id,
                    from_role=request.from_role.strip() or ticket.assigned_role,
                    to_employee_id=request.to_employee_id.strip(),
                    to_role=request.to_role.strip(),
                    content=request.report_content.strip()
                    or "AITeamOS Plane action smoke for Ticket handoff/report writes.",
                    actor_employee_id=CLARA_SYSTEM_EMPLOYEE_ID,
                    actor_role=CLARA_SYSTEM_ROLE,
                    source_run_id=request.source_run_id.strip() or "plane-ticket-action-smoke",
                ),
            )
            checks.append("ticket_handoff_projection_recorded")

            stage = "append_handoff_report"
            report = self.add_ticket_report(
                ticket.id,
                TicketReportRequest(
                    reporter_employee_id=CLARA_SYSTEM_EMPLOYEE_ID,
                    reporter_role=CLARA_SYSTEM_ROLE,
                    content=(
                        "Plane Ticket action smoke recorded a Ticket handoff and is verifying "
                        "the Plane comment/report write path.\n\n"
                        + (
                            request.report_content.strip()
                            or "AITeamOS Plane action smoke for Ticket handoff/report writes."
                        )
                    ),
                    evidence=[f"plane_action_smoke:{request.source_run_id.strip() or 'plane-ticket-action-smoke'}"],
                    report_type="employee_handoff",
                    source_run_id=request.source_run_id.strip() or "plane-ticket-action-smoke",
                ),
            )
            checks.append("plane_handoff_report_comment_appended")
            latest_report = report.reports[-1] if report.reports else None
            return TicketProviderActionSmokeResponse(
                status="passed",
                provider="plane",
                checks=checks,
                evidence={
                    **evidence,
                    "handoff_ticket": handoff.model_dump(mode="json"),
                    "reported_ticket": report.model_dump(mode="json"),
                    "report_id": latest_report.id if latest_report else "",
                },
                summary={
                    "ticket_backend_status": status.status,
                    "ticket_id": ticket.id,
                    "ticket_source": ticket_source,
                    "provider_record_id": ticket.provider_ref.provider_record_id if ticket.provider_ref else "",
                    "handoff_recorded": True,
                    "handoff_report_recorded": True,
                    "report_id": latest_report.id if latest_report else "",
                    "to_employee_id": request.to_employee_id.strip(),
                    "mutation_gate_open": True,
                },
                external_calls=True,
                mutating=True,
            )
        except Exception as exc:
            reason = {
                "load_or_create_ticket": "plane_ticket_load_or_create_failed",
                "record_ticket_handoff": "plane_ticket_handoff_projection_failed",
                "append_handoff_report": "plane_handoff_report_action_failed",
            }.get(stage, "plane_action_smoke_failed")
            return TicketProviderActionSmokeResponse(
                status="blocked",
                provider="plane",
                checks=checks,
                failures=[reason],
                blockers=[
                    {
                        "id": f"ticket:plane:action_smoke:{stage}",
                        "reason": reason,
                        "status": "blocked",
                        "detail": str(exc),
                        "stage": stage,
                        "setup_required": [],
                    }
                ],
                evidence=evidence,
                summary={
                    "ticket_backend_status": status.status,
                    "ticket_id": ticket.id if ticket is not None else "",
                    "blocker_stage": stage,
                    "blocker_reason": reason,
                    "mutation_gate_open": True,
                },
                external_calls=True,
                mutating=True,
            )

    def _event_files(self) -> list[Path]:
        return sorted(self.root.glob("*/*.ticket.jsonl"))

    def _ticket_file(self, namespace: str, ticket_id: str) -> Path:
        return self.root / namespace / f"{ticket_id}.ticket.jsonl"

    def _ticket_file_by_id(self, ticket_id: str) -> Path | None:
        if not LOCAL_TICKET_ID_RE.fullmatch(ticket_id):
            return None
        namespace = ticket_id.split("-", maxsplit=1)[0].lower()
        path = self._ticket_file(namespace, ticket_id.lower())
        if path.exists():
            return path
        return next((candidate for candidate in self._event_files() if candidate.stem.removesuffix(".ticket") == ticket_id), None)

    def _read_events_from_file(self, path: Path) -> list[TicketEvent]:
        events: list[TicketEvent] = []
        if not path.exists():
            return events
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(TicketEvent.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValueError):
                continue
        return events

    def _append_events(self, path: Path, events: list[TicketEvent]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n")
        self._write_index(self._load_items())

    def _read_counters(self) -> dict[str, int]:
        if not self.counters_path.exists():
            return {}
        try:
            payload = json.loads(self.counters_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(key): int(value) for key, value in payload.items() if isinstance(value, int)}

    def _write_counters(self, counters: dict[str, int]) -> None:
        self.counters_path.parent.mkdir(parents=True, exist_ok=True)
        self.counters_path.write_text(json.dumps(counters, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _max_existing_number(self, namespace: str) -> int:
        max_value = 0
        pattern = re.compile(rf"^{re.escape(namespace)}-(\d+)$")
        for path in self.root.glob(f"{namespace}/{namespace}-*.ticket.jsonl"):
            match = pattern.fullmatch(path.stem.removesuffix(".ticket"))
            if match:
                max_value = max(max_value, int(match.group(1)))
        return max_value

    def _next_ticket_id(self, namespace: str) -> str:
        counters = self._read_counters()
        next_number = max(counters.get(namespace, 0), self._max_existing_number(namespace)) + 1
        counters[namespace] = next_number
        self._write_counters(counters)
        return f"{namespace}-{next_number:04d}"

    def _write_index(self, items: list[Ticket]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _provider_ref(self, provider_payload: dict[str, Any]) -> ProviderTicketRef:
        provider_record_id = str(provider_payload.get("id") or provider_payload.get("uuid") or "")
        if not provider_record_id:
            raise ValueError("Plane Ticket Backend returned no provider record id.")
        return ProviderTicketRef(
            provider="plane",
            provider_record_id=provider_record_id,
            provider_project_id=str(provider_payload.get("project") or self.settings.plane_project_id),
            provider_url=str(provider_payload.get("url") or provider_payload.get("html_url") or self._external_url(provider_record_id)),
            synced_at=_now(),
        )

    def _provider_state_snapshot(self, provider_payload: dict[str, Any]) -> dict[str, str]:
        state_payload = provider_payload.get("state")
        if state_payload is None:
            state_payload = provider_payload.get("state_detail") or provider_payload.get("state_data")
        state_id = ""
        state_name = ""
        if isinstance(state_payload, dict):
            state_id = str(
                state_payload.get("id")
                or state_payload.get("uuid")
                or state_payload.get("value")
                or state_payload.get("key")
                or ""
            )
            state_name = str(
                state_payload.get("name")
                or state_payload.get("display_name")
                or state_payload.get("label")
                or ""
            )
        elif state_payload is not None:
            state_id = str(state_payload)
        return {
            "provider_state_id": state_id,
            "provider_state_name": state_name,
        }

    def _status_from_provider_state(self, state_snapshot: dict[str, str], fallback: str) -> str:
        state_id = state_snapshot.get("provider_state_id", "").strip()
        reverse_mapping = {
            value.strip(): key.strip().lower()
            for key, value in self.settings.plane_state_ids.items()
            if key.strip() and value.strip()
        }
        if state_id in reverse_mapping:
            return reverse_mapping[state_id]
        label = state_snapshot.get("provider_state_name", "").strip() or state_id
        normalized = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        if normalized in {"open", "assigned", "in_review", "validated", "blocked", "closed", "done"}:
            return normalized
        return fallback

    def _project_ticket(self, events: list[TicketEvent], path: Path) -> Ticket | None:
        if not events:
            return None
        ticket_id = events[0].ticket_id
        namespace = ticket_id.split("-", maxsplit=1)[0].lower()
        state: dict[str, Any] = {
            "id": ticket_id,
            "title": ticket_id,
            "description": "",
            "status": "open",
            "ticket_type": namespace,
            "assigned_employee_id": "",
            "assigned_role": "",
            "validation_employee_id": "",
            "validation_role": "",
            "knowledge_refs": [],
            "code_repository_ids": [],
            "source_thread_id": "",
            "source_run_id": "",
            "reports": [],
            "provider_ref": None,
            "external_url": "",
            "provider_metadata": {},
            "created_at": events[0].at,
            "updated_at": events[-1].at,
            "saved_path": _relative(path),
            "events": events,
        }
        for event in events:
            data = event.data
            state["updated_at"] = event.at
            provider_ref_payload = data.get("provider_ref")
            if isinstance(provider_ref_payload, dict):
                provider_ref = ProviderTicketRef.model_validate(provider_ref_payload)
                state["provider_ref"] = provider_ref
                state["external_url"] = provider_ref.provider_url
            provider_metadata = data.get("provider_metadata")
            if isinstance(provider_metadata, dict):
                state["provider_metadata"] = {**dict(state["provider_metadata"]), **provider_metadata}
            if event.type == "created":
                state.update(
                    {
                        "title": str(data.get("title") or state["title"]),
                        "description": str(data.get("description") or data.get("title") or state["description"]),
                        "status": str(data.get("status") or state["status"]),
                        "ticket_type": str(data.get("ticket_type") or namespace),
                        "knowledge_refs": [str(item) for item in data.get("knowledge_refs", []) if str(item).strip()],
                        "code_repository_ids": [str(item) for item in data.get("code_repository_ids", []) if str(item).strip()],
                        "source_thread_id": str(data.get("source_thread_id") or ""),
                        "source_run_id": str(data.get("source_run_id") or ""),
                    }
                )
                state["created_at"] = event.at
            elif event.type == "assigned":
                state["assigned_employee_id"] = str(data.get("assigned_employee_id") or data.get("to_employee_id") or "")
                state["assigned_role"] = str(data.get("assigned_role") or data.get("to_role") or "")
            elif event.type == "validation_requested":
                state["validation_employee_id"] = str(data.get("validation_employee_id") or data.get("to_employee_id") or "")
                state["validation_role"] = str(data.get("validation_role") or data.get("to_role") or "")
            elif event.type in {"reported", "validated", "blocked"}:
                report_payload = data.get("report")
                if isinstance(report_payload, dict):
                    report = TicketReport.model_validate({**report_payload, "source_event_id": event.event_id})
                    state["reports"].append(report)
            elif event.type == "status_changed":
                state["status"] = str(data.get("to") or data.get("status") or state["status"])
            elif event.type == "asset_linked":
                target_kind = str(data.get("target_kind") or "")
                target_ref = str(data.get("target_ref") or "")
                if target_kind == "knowledge" and target_ref and target_ref not in state["knowledge_refs"]:
                    state["knowledge_refs"].append(target_ref)
                if target_kind == "repository" and target_ref and target_ref not in state["code_repository_ids"]:
                    state["code_repository_ids"].append(target_ref)
        return Ticket.model_validate(state)

    def _load_items(self) -> list[Ticket]:
        items = [
            ticket
            for ticket in (self._project_ticket(self._read_events_from_file(path), path) for path in self._event_files())
            if ticket is not None
        ]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def _get_projected_ticket(self, ticket_id: str) -> tuple[Ticket | None, Path | None]:
        path = self._ticket_file_by_id(ticket_id.strip())
        if path is None:
            return None, None
        return self._project_ticket(self._read_events_from_file(path), path), path

    def _refresh_ticket_from_provider(self, item: Ticket, path: Path) -> Ticket:
        if item.provider_ref is None:
            return item
        provider_payload = self._request("GET", self._work_item_path(item.provider_ref.provider_record_id))
        provider_ref = self._provider_ref(
            {
                **provider_payload,
                "id": provider_payload.get("id") or item.provider_ref.provider_record_id,
                "project": provider_payload.get("project") or item.provider_ref.provider_project_id,
                "url": provider_payload.get("url") or provider_payload.get("html_url") or item.provider_ref.provider_url,
            }
        )
        current_state = self._provider_state_snapshot(provider_payload)
        provider_metadata = {
            "provider_record_id": provider_ref.provider_record_id,
            "current_state": current_state,
        }
        next_status = self._status_from_provider_state(current_state, item.status)
        if next_status != item.status:
            self._append_events(
                path,
                [
                    _event(
                        item.id,
                        "status_changed",
                        actor_id="system",
                        actor_role="Ticket Backend",
                        data={
                            "from": item.status,
                            "to": next_status,
                            "reason": "provider_refresh",
                            "provider_ref": provider_ref.model_dump(mode="json"),
                            "provider_metadata": provider_metadata,
                        },
                    )
                ],
            )
            refreshed, _ = self._get_projected_ticket(item.id)
            if refreshed is not None:
                item = refreshed
        item.provider_ref = provider_ref
        item.external_url = provider_ref.provider_url
        item.provider_metadata = {**item.provider_metadata, **provider_metadata}
        return item

    def _plane_create_payload(self, *, ticket_id: str, namespace: str, request: TicketCreateRequest) -> dict[str, Any]:
        assigned_employee_id = request.assigned_employee_id.strip()
        metadata = {
            "ticket_id": ticket_id,
            "namespace": namespace,
            "assigned_employee_id": assigned_employee_id,
            "assigned_role": request.assigned_role.strip(),
            "validation_employee_id": request.validation_employee_id.strip(),
            "validation_role": request.validation_role.strip(),
            "source_thread_id": request.source_thread_id.strip(),
            "source_run_id": request.source_run_id.strip(),
        }
        payload: dict[str, Any] = {
            "name": request.title.strip(),
            "description_stripped": (
                (request.description.strip() or request.title.strip())
                + "\n\nAITeamOS metadata:\n"
                + json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            ),
            "external_source": "aiteamos",
            "external_id": ticket_id,
            "priority": "medium",
        }
        state_id = self.settings.plane_state_ids.get("assigned")
        if state_id:
            payload["state"] = state_id
        label_id = self.settings.plane_namespace_label_ids.get(namespace)
        if label_id:
            payload["labels"] = [label_id]
        assignee_id = self.settings.plane_employee_assignee_ids.get(assigned_employee_id.lower())
        if assignee_id:
            payload["assignees"] = [assignee_id]
        return payload

    def list_tickets(self, status: str | None = None) -> list[Ticket]:
        self._ensure_ready()
        items = self._load_items()
        if status:
            items = [item for item in items if item.status == status]
        self._write_index(items)
        return items

    def create_ticket(self, request: TicketCreateRequest) -> Ticket:
        self._ensure_ready()
        actor_id = request.actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID
        actor_role = _resolve_actor_role(actor_id, request.actor_role)
        namespace = _infer_ticket_namespace(request, actor_role)
        _ensure_namespace_authority(namespace, actor_employee_id=actor_id, actor_role=actor_role)
        assigned_employee_id = request.assigned_employee_id.strip()
        assigned_role = request.assigned_role.strip()
        if not (assigned_employee_id or assigned_role):
            raise ValueError("Ticket requires an assignee Employee or assigned role.")

        timestamp = _now()
        item_id = self._next_ticket_id(namespace)
        provider_payload = self._request("POST", self._work_items_path(), json_payload=self._plane_create_payload(ticket_id=item_id, namespace=namespace, request=request))
        provider_ref = self._provider_ref(provider_payload)
        provider_ref_payload = provider_ref.model_dump(mode="json")
        initial_status = "assigned"
        events = [
            _event(
                item_id,
                "created",
                actor_id=actor_id,
                actor_role=actor_role,
                at=timestamp,
                data={
                    "title": request.title.strip(),
                    "description": request.description.strip() or request.title.strip(),
                    "status": initial_status,
                    "ticket_type": namespace,
                    "knowledge_refs": sorted({item.strip() for item in request.knowledge_refs if item.strip()}),
                    "code_repository_ids": sorted({item.strip() for item in request.code_repository_ids if item.strip()}),
                    "source_thread_id": request.source_thread_id.strip(),
                    "source_run_id": request.source_run_id.strip(),
                    "provider_ref": provider_ref_payload,
                    "provider_metadata": {
                        "provider_record_id": provider_ref.provider_record_id,
                        "sequence_id": provider_payload.get("sequence_id"),
                        "current_state": self._provider_state_snapshot(provider_payload),
                        "namespace_strategy": self.settings.plane_namespace_strategy,
                        "mapping": PLANE_TICKET_MAPPING,
                    },
                },
            ),
            _event(
                item_id,
                "assigned",
                actor_id=actor_id,
                actor_role=actor_role,
                at=timestamp,
                data={
                    "assigned_employee_id": assigned_employee_id,
                    "assigned_role": assigned_role,
                    "provider_ref": provider_ref_payload,
                },
            ),
        ]
        if request.validation_employee_id.strip() or request.validation_role.strip():
            events.append(
                _event(
                    item_id,
                    "validation_requested",
                    actor_id=actor_id,
                    actor_role=actor_role,
                    at=timestamp,
                    data={
                        "validation_employee_id": request.validation_employee_id.strip(),
                        "validation_role": request.validation_role.strip(),
                        "provider_ref": provider_ref_payload,
                    },
                )
            )
        for ref in sorted({item.strip() for item in request.knowledge_refs if item.strip()}):
            events.append(_event(item_id, "asset_linked", actor_id=actor_id, actor_role=actor_role, at=timestamp, data={"target_kind": "knowledge", "target_ref": ref, "provider_ref": provider_ref_payload}))
        for ref in sorted({item.strip() for item in request.code_repository_ids if item.strip()}):
            events.append(_event(item_id, "asset_linked", actor_id=actor_id, actor_role=actor_role, at=timestamp, data={"target_kind": "repository", "target_ref": ref, "provider_ref": provider_ref_payload}))

        path = self._ticket_file(namespace, item_id)
        self._append_events(path, events)
        item, _ = self._get_projected_ticket(item_id)
        if item is None:
            raise ValueError(f"Ticket was not projected after Plane create: {item_id}")
        return item

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        self._ensure_ready()
        item, path = self._get_projected_ticket(ticket_id)
        if item is None or path is None:
            return None
        return self._refresh_ticket_from_provider(item, path)

    def get_ticket_events(self, ticket_id: str) -> list[TicketEvent]:
        self._ensure_ready()
        path = self._ticket_file_by_id(ticket_id.strip())
        return self._read_events_from_file(path) if path is not None else []

    def add_ticket_report(self, ticket_id: str, request: TicketReportRequest) -> Ticket:
        self._ensure_ready()
        item, path = self._get_projected_ticket(ticket_id)
        if item is None or path is None:
            raise KeyError(ticket_id)
        if item.provider_ref is None:
            raise ValueError(f"Ticket {ticket_id} has no Plane provider ref.")

        timestamp = _now()
        reporter_id = request.reporter_employee_id.strip()
        reporter_role = request.reporter_role.strip() or _employee_role(reporter_id)
        report_type = request.report_type.strip() or "progress"
        evidence = [entry.strip() for entry in request.evidence if entry.strip()]
        if _is_validation_pass_report_type(report_type):
            _ensure_validation_evidence(item, evidence)
        report = TicketReport(
            id=f"report-{uuid4().hex[:10]}",
            reporter_employee_id=reporter_id,
            reporter_role=reporter_role,
            content=request.content.strip(),
            evidence=evidence,
            report_type=report_type,
            created_at=timestamp,
        )
        aiteamos_comment = {
            "ticket_id": item.id,
            "report_id": report.id,
            "report_type": report.report_type,
            "reporter_employee_id": reporter_id,
            "source_run_id": request.source_run_id.strip(),
            "evidence": report.evidence,
        }
        validation_request_like = (
            report_type in {"validation_request", "validation_requested"}
            or "validation" in report.content.lower()
            or "验证" in report.content
        )
        inferred_validation_employee = item.validation_employee_id or _validation_employee_from_text(report.content)
        if validation_request_like:
            aiteamos_comment.update(
                {
                    "request_type": "validation_request",
                    "validation_employee_id": inferred_validation_employee,
                    "validation_role": item.validation_role,
                }
            )
        comment_payload = {
            "comment_html": f"<p>{html.escape(report.content)}</p>",
            "comment_json": {"aiteamos": aiteamos_comment},
            "access": "INTERNAL",
            "external_source": "aiteamos",
            "external_id": report.id,
        }
        provider_comment = self._request("POST", self._comments_path(item.provider_ref.provider_record_id), json_payload=comment_payload)
        event_type = "validated" if _is_validation_pass_report_type(report_type) else "blocked" if _is_validation_failure_report_type(report_type) else "reported"
        next_status = "validated" if _is_validation_pass_report_type(report_type) else "blocked" if _is_validation_failure_report_type(report_type) else item.status
        provider_ref_payload = item.provider_ref.model_dump(mode="json")
        events = [
            _event(
                item.id,
                event_type,
                actor_id=reporter_id,
                actor_role=reporter_role,
                at=timestamp,
                data={
                    "report": report.model_dump(mode="json"),
                    "source_run_id": request.source_run_id.strip(),
                    "provider_ref": provider_ref_payload,
                    "provider_metadata": {"provider_comment_id": provider_comment.get("id")},
                },
            )
        ]
        if next_status != item.status:
            events.append(
                _event(
                    item.id,
                    "status_changed",
                    actor_id=reporter_id,
                    actor_role=reporter_role,
                    at=timestamp,
                    data={"from": item.status, "to": next_status, "reason": f"report:{report.id}", "provider_ref": provider_ref_payload},
                )
            )
        for evidence in report.evidence:
            events.append(
                _event(
                    item.id,
                    "asset_linked",
                    actor_id=reporter_id,
                    actor_role=reporter_role,
                    at=timestamp,
                    data={"target_kind": "evidence", "target_ref": evidence, "source_report_id": report.id, "provider_ref": provider_ref_payload},
                )
            )
        self._append_events(path, events)
        updated, _ = self._get_projected_ticket(item.id)
        if updated is None:
            raise KeyError(ticket_id)
        return updated

    def request_ticket_validation(self, ticket_id: str, request: TicketValidationRequest) -> Ticket:
        self._ensure_ready()
        item, path = self._get_projected_ticket(ticket_id)
        if item is None or path is None:
            raise KeyError(ticket_id)
        if item.provider_ref is None:
            raise ValueError(f"Ticket {ticket_id} has no Plane provider ref.")
        validation_employee_id = request.validation_employee_id.strip()
        validation_role = request.validation_role.strip()
        if not (validation_employee_id or validation_role):
            raise ValueError("Ticket validation request requires a validation Employee or role.")

        timestamp = _now()
        actor_id = request.actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID
        actor_role = _resolve_actor_role(actor_id, request.actor_role)
        request_id = f"validation-{uuid4().hex[:10]}"
        content = request.content.strip() or f"Validation requested for Ticket {item.id}."
        comment_payload = {
            "comment_html": f"<p>{html.escape(content)}</p>",
            "comment_json": {
                "aiteamos": {
                    "ticket_id": item.id,
                    "validation_request_id": request_id,
                    "validation_employee_id": validation_employee_id,
                    "validation_role": validation_role,
                    "source_run_id": request.source_run_id.strip(),
                    "request_type": "validation_request",
                }
            },
            "access": "INTERNAL",
            "external_source": "aiteamos",
            "external_id": request_id,
        }
        provider_comment = self._request("POST", self._comments_path(item.provider_ref.provider_record_id), json_payload=comment_payload)
        provider_ref_payload = item.provider_ref.model_dump(mode="json")
        event = _event(
            item.id,
            "validation_requested",
            actor_id=actor_id,
            actor_role=actor_role,
            at=timestamp,
            data={
                "validation_employee_id": validation_employee_id,
                "validation_role": validation_role,
                "content": content,
                "source_run_id": request.source_run_id.strip(),
                "provider_ref": provider_ref_payload,
                "provider_metadata": {
                    "provider_comment_id": provider_comment.get("id"),
                    "validation_request_id": request_id,
                },
            },
        )
        self._append_events(path, [event])
        updated, _ = self._get_projected_ticket(item.id)
        if updated is None:
            raise KeyError(ticket_id)
        return updated

    def record_ticket_handoff(self, ticket_id: str, request: TicketHandoffRequest) -> Ticket:
        self._ensure_ready()
        item, path = self._get_projected_ticket(ticket_id)
        if item is None or path is None:
            raise KeyError(ticket_id)
        to_employee_id = request.to_employee_id.strip()
        to_role = request.to_role.strip()
        if not (to_employee_id or to_role):
            raise ValueError("Ticket handoff requires a target Employee or role.")

        actor_id = request.actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID
        actor_role = _resolve_actor_role(actor_id, request.actor_role)
        timestamp = _now()
        events = [
            _event(
                item.id,
                "handoff_requested",
                actor_id=actor_id,
                actor_role=actor_role,
                at=timestamp,
                data={
                    "from_employee_id": request.from_employee_id.strip() or item.assigned_employee_id,
                    "from_role": request.from_role.strip() or item.assigned_role,
                    "to_employee_id": to_employee_id,
                    "to_role": to_role,
                    "content": request.content.strip(),
                    "source_run_id": request.source_run_id.strip(),
                },
            ),
            _event(
                item.id,
                "assigned",
                actor_id=actor_id,
                actor_role=actor_role,
                at=timestamp,
                data={
                    "assigned_employee_id": to_employee_id,
                    "assigned_role": to_role,
                    "source_run_id": request.source_run_id.strip(),
                },
            ),
        ]
        self._append_events(path, events)
        updated, _ = self._get_projected_ticket(item.id)
        if updated is None:
            raise KeyError(ticket_id)
        return updated

    def transition_ticket_state(self, ticket_id: str, request: TicketStateTransitionRequest) -> Ticket:
        self._ensure_ready()
        item, path = self._get_projected_ticket(ticket_id)
        if item is None or path is None:
            raise KeyError(ticket_id)
        if item.provider_ref is None:
            raise ValueError(f"Ticket {ticket_id} has no Plane provider ref.")
        next_status = request.status.strip().lower()
        state_id = self.settings.plane_state_ids.get(next_status) or request.status.strip()
        if not state_id:
            raise ValueError("Ticket state transition requires a Plane state id or mapped status.")
        provider_payload = self._request("PATCH", self._work_item_path(item.provider_ref.provider_record_id), json_payload={"state": state_id})
        provider_ref = self._provider_ref({**provider_payload, "id": provider_payload.get("id") or item.provider_ref.provider_record_id})
        actor_id = request.actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID
        actor_role = _resolve_actor_role(actor_id, request.actor_role)
        event = _event(
            item.id,
            "status_changed",
            actor_id=actor_id,
            actor_role=actor_role,
            data={
                "from": item.status,
                "to": next_status,
                "provider_ref": provider_ref.model_dump(mode="json"),
                "provider_metadata": {"state_id": state_id, "current_state": self._provider_state_snapshot(provider_payload)},
                "source_run_id": request.source_run_id.strip(),
            },
        )
        self._append_events(path, [event])
        updated, _ = self._get_projected_ticket(item.id)
        if updated is None:
            raise KeyError(ticket_id)
        return updated

    def employee_work_ledger(self, employee_id: str) -> EmployeeWorkLedger:
        self._ensure_ready()
        normalized = employee_id.strip()
        current: dict[str, TicketWorkItem] = {}
        historical: dict[str, TicketWorkItem] = {}
        reports: list[EmployeeTicketReportRecord] = []
        validations: list[EmployeeTicketReportRecord] = []
        blocked_records: list[EmployeeTicketReportRecord] = []
        handoffs: list[dict[str, Any]] = []

        for ticket in self._load_items():
            roles: set[str] = set()
            if ticket.assigned_employee_id == normalized:
                roles.add("owner")
            if ticket.validation_employee_id == normalized:
                roles.add("validator")
            for event in ticket.events:
                actor_id = event.actor.get("id", "")
                event_data = event.data if isinstance(event.data, dict) else {}
                handoff_employee_ids = {
                    actor_id,
                    str(event_data.get("from_employee_id") or ""),
                    str(event_data.get("to_employee_id") or ""),
                }
                if normalized in handoff_employee_ids and event.type.startswith("handoff"):
                    roles.add("handoff")
                    handoffs.append(
                        {
                            "ticket_id": ticket.id,
                            "title": ticket.title,
                            "relation": (
                                "target"
                                if str(event_data.get("to_employee_id") or "") == normalized
                                else ("source" if str(event_data.get("from_employee_id") or "") == normalized else "actor")
                            ),
                            "event": event.model_dump(mode="json"),
                        }
                    )
            for report in ticket.reports:
                if report.reporter_employee_id != normalized:
                    continue
                roles.add("reporter")
                record = EmployeeTicketReportRecord(
                    ticket_id=ticket.id,
                    ticket_title=ticket.title,
                    report_id=report.id,
                    report_type=report.report_type,
                    content=report.content,
                    evidence=report.evidence,
                    created_at=report.created_at,
                )
                reports.append(record)
                if _is_validation_pass_report_type(report.report_type):
                    validations.append(record)
                if _is_validation_failure_report_type(report.report_type):
                    blocked_records.append(record)
            if not roles:
                continue
            item = TicketWorkItem(
                ticket_id=ticket.id,
                title=ticket.title,
                status=ticket.status,
                role=", ".join(sorted(roles)),
                updated_at=ticket.updated_at,
                next_action=_next_action(ticket),
            )
            historical[ticket.id] = item
            if not _terminal_status(ticket.status):
                current[ticket.id] = item

        return _augment_employee_work_ledger(EmployeeWorkLedger(
            employee_id=normalized,
            current_tickets=sorted(current.values(), key=lambda item: item.updated_at, reverse=True),
            historical_tickets=sorted(historical.values(), key=lambda item: item.updated_at, reverse=True),
            reports=sorted(reports, key=lambda item: item.created_at, reverse=True),
            validations=sorted(validations, key=lambda item: item.created_at, reverse=True),
            blocked_records=sorted(blocked_records, key=lambda item: item.created_at, reverse=True),
            handoffs=handoffs,
            contribution={
                "ticket_count": len(historical),
                "current_ticket_count": len(current),
                "report_count": len(reports),
                "validation_count": len(validations),
                "blocked_count": len(blocked_records),
                "handoff_count": len(handoffs),
            },
        ))

    def ticket_asset_records(self) -> list[TicketAssetRecord]:
        self._ensure_ready()
        records: list[TicketAssetRecord] = []
        for ticket in self._load_items():
            scopes = [ticket.ticket_type, *ticket.knowledge_refs]
            assigned = [value for value in [ticket.assigned_employee_id, ticket.validation_employee_id] if value]
            for report in ticket.reports:
                status = "approved" if _is_validation_pass_report_type(report.report_type) else "candidate"
                records.append(
                    TicketAssetRecord(
                        id=report.id,
                        kind="report",
                        title=f"{report.report_type} report for {ticket.id}",
                        status=status,
                        source_ticket_id=ticket.id,
                        source_employee_id=report.reporter_employee_id,
                        assigned_employees=assigned,
                        scopes=scopes,
                        created_at=report.created_at,
                        updated_at=report.created_at,
                        metadata={
                            "ticket_title": ticket.title,
                            "report": report.model_dump(mode="json"),
                            "provider_ref": ticket.provider_ref.model_dump(mode="json") if ticket.provider_ref else None,
                        },
                    )
                )
                for index, evidence in enumerate(report.evidence):
                    records.append(
                        TicketAssetRecord(
                            id=f"{report.id}:evidence:{index}",
                            kind="evidence",
                            title=evidence,
                            status=status,
                            source_ticket_id=ticket.id,
                            source_employee_id=report.reporter_employee_id,
                            assigned_employees=assigned,
                            scopes=scopes,
                            created_at=report.created_at,
                            updated_at=report.created_at,
                            metadata={"ticket_title": ticket.title, "report_id": report.id, "evidence": evidence},
                        )
                    )
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def status(self) -> TicketBackendStatus:
        missing = self._setup_required()
        items = self._load_items()
        plane_setup = _plane_backend_setup_summary(self.settings)
        if missing:
            return TicketBackendStatus(
                mode=self.settings.mode,
                status="setup_blocked",
                detail="Plane Ticket Backend is selected but setup is incomplete.",
                ticket_count=len(items),
                provider="plane",
                provider_ref_count=len([item for item in items if item.provider_ref is not None]),
                setup_required=missing,
                plane_setup=plane_setup,
                release_target=_plane_release_target_summary(self.settings, plane_setup),
                capabilities=["setup_blocker"],
                mapping=PLANE_TICKET_MAPPING,
                saved_paths={"settings": _relative(_backend_settings_path()), "plane_projection": _relative(self.root)},
                supported_modes=SUPPORTED_BACKENDS,
            )
        self._write_index(items)
        return TicketBackendStatus(
            mode=self.settings.mode,
            status="ready",
            detail="Plane Ticket Backend is active; AITeamOS stores only Ticket event projection and audit mirror.",
            ticket_count=len(items),
            provider="plane",
            provider_ref_count=len([item for item in items if item.provider_ref is not None]),
            plane_setup=plane_setup,
            release_target=_plane_release_target_summary(self.settings, plane_setup),
            capabilities=[
                "create_ticket",
                "read_provider_ref",
                "read_provider_current_state",
                "append_report_comment",
                "request_validation",
                "request_human_review",
                "record_handoff",
                "transition_state",
                "external_deep_link",
            ],
            mapping=PLANE_TICKET_MAPPING,
            saved_paths={"settings": _relative(_backend_settings_path()), "plane_projection": _relative(self.root), "index": _relative(self.index_path)},
            supported_modes=SUPPORTED_BACKENDS,
        )


class PlannedTicketAdapter:
    def __init__(self, settings: TicketBackendSettings):
        self.settings = settings

    def _raise(self) -> None:
        raise ValueError(f"Ticket backend '{self.settings.mode}' is planned but not implemented yet.")

    def list_tickets(self, status: str | None = None) -> list[Ticket]:
        self._raise()

    def create_ticket(self, request: TicketCreateRequest) -> Ticket:
        self._raise()

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        self._raise()

    def get_ticket_events(self, ticket_id: str) -> list[TicketEvent]:
        self._raise()

    def add_ticket_report(self, ticket_id: str, request: TicketReportRequest) -> Ticket:
        self._raise()

    def request_ticket_validation(self, ticket_id: str, request: TicketValidationRequest) -> Ticket:
        self._raise()

    def record_ticket_handoff(self, ticket_id: str, request: TicketHandoffRequest) -> Ticket:
        self._raise()

    def transition_ticket_state(self, ticket_id: str, request: TicketStateTransitionRequest) -> Ticket:
        self._raise()

    def employee_work_ledger(self, employee_id: str) -> EmployeeWorkLedger:
        self._raise()

    def ticket_asset_records(self) -> list[TicketAssetRecord]:
        self._raise()

    def status(self) -> TicketBackendStatus:
        plane_setup = _plane_backend_setup_summary(self.settings)
        return TicketBackendStatus(
            mode=self.settings.mode,
            status="planned",
            detail=f"Ticket backend '{self.settings.mode}' is configured, but Plane is the only external executable Ticket Backend in this version.",
            ticket_count=0,
            local_file_path=self.settings.local_file_path,
            plane_setup=plane_setup,
            release_target=_plane_release_target_summary(self.settings, plane_setup),
            mapping=PLANE_TICKET_MAPPING,
            saved_paths={
                "settings": _relative(_backend_settings_path()),
                "local_file": self.settings.local_file_path,
                "plane_projection": ".aiteamos/tickets/plane",
            },
            supported_modes=SUPPORTED_BACKENDS,
        )

    def external_smoke(self) -> dict[str, Any]:
        status = self.status()
        return {
            "status": status.status,
            "checks": ["planned_ticket_provider_reported"],
            "warnings": [],
            "failures": [],
            "blockers": [
                {
                    "id": f"ticket:{self.settings.mode}:planned",
                    "status": status.status,
                    "detail": status.detail,
                    "setup_required": [],
                }
            ],
            "evidence": {"ticket_backend_status": status.model_dump(mode="json")},
            "external_calls": False,
        }

    def action_smoke(self, request: TicketProviderActionSmokeRequest) -> TicketProviderActionSmokeResponse:
        status = self.status()
        return TicketProviderActionSmokeResponse(
            status=status.status,
            provider=self.settings.mode,
            checks=["planned_ticket_provider_reported", "plane_action_smoke_unavailable"],
            blockers=[
                {
                    "id": f"ticket:{self.settings.mode}:planned",
                    "reason": "ticket_provider_not_implemented",
                    "status": status.status,
                    "detail": status.detail,
                    "setup_required": [],
                }
            ],
            evidence={"ticket_backend_status": status.model_dump(mode="json")},
            summary={"ticket_backend_status": status.status, "blocker_stage": "planned_backend"},
        )


def ticket_adapter() -> TicketAdapter:
    settings = ticket_backend_settings()
    if settings.mode == "local_file":
        return LocalFileTicketAdapter(settings)
    if settings.mode == "plane":
        return PlaneTicketAdapter(settings)
    return PlannedTicketAdapter(settings)


def ticket_backend_status() -> TicketBackendStatus:
    return ticket_adapter().status()


def ticket_provider_external_smoke() -> dict[str, Any]:
    return ticket_adapter().external_smoke()


def ticket_provider_action_smoke(
    request: TicketProviderActionSmokeRequest | None = None,
) -> TicketProviderActionSmokeResponse:
    return ticket_adapter().action_smoke(request or TicketProviderActionSmokeRequest())


def list_tickets(status: str | None = None) -> list[Ticket]:
    return ticket_adapter().list_tickets(status=status)


def create_ticket(request: TicketCreateRequest) -> Ticket:
    return ticket_adapter().create_ticket(request)


def get_ticket(ticket_id: str) -> Ticket | None:
    return ticket_adapter().get_ticket(ticket_id)


def get_ticket_events(ticket_id: str) -> list[TicketEvent]:
    return ticket_adapter().get_ticket_events(ticket_id)


def add_ticket_report(ticket_id: str, request: TicketReportRequest) -> Ticket:
    updated = ticket_adapter().add_ticket_report(ticket_id, request)
    if _is_validation_pass_report_type(request.report_type):
        return _maybe_auto_propose_ticket_closeout_candidates(
            updated,
            actor_employee_id=request.reporter_employee_id,
            actor_role=request.reporter_role,
            source_run_id=request.source_run_id,
            trigger="validation_report",
            reason=f"Auto-proposed after validation report {request.report_type.strip() or 'validation'}.",
        )
    return updated


def request_ticket_validation(ticket_id: str, request: TicketValidationRequest) -> Ticket:
    return ticket_adapter().request_ticket_validation(ticket_id, request)


def record_ticket_handoff(ticket_id: str, request: TicketHandoffRequest) -> Ticket:
    return ticket_adapter().record_ticket_handoff(ticket_id, request)


def transition_ticket_state(ticket_id: str, request: TicketStateTransitionRequest) -> Ticket:
    updated = ticket_adapter().transition_ticket_state(ticket_id, request)
    if _closeout_status(request.status):
        return _maybe_auto_propose_ticket_closeout_candidates(
            updated,
            actor_employee_id=request.actor_employee_id,
            actor_role=request.actor_role,
            source_run_id=request.source_run_id,
            trigger="state_transition",
            reason=f"Auto-proposed after Ticket state transition to {request.status.strip().lower()}.",
        )
    return updated


def employee_work_ledger(employee_id: str) -> EmployeeWorkLedger:
    return ticket_adapter().employee_work_ledger(employee_id)


def propose_employee_quality_improvement_candidate(
    employee_id: str,
    feedback_id: str,
    request: EmployeeImprovementCandidateRequest,
) -> EmployeeImprovementCandidateResponse:
    normalized_employee_id = employee_id.strip()
    normalized_feedback_id = feedback_id.strip()
    if not normalized_employee_id:
        raise ValueError("Employee id is required.")
    if not normalized_feedback_id:
        raise ValueError("Quality feedback id is required.")
    ledger = employee_work_ledger(normalized_employee_id)
    feedback = next((item for item in ledger.quality_feedback if item.id == normalized_feedback_id), None)
    if feedback is None:
        raise KeyError(normalized_feedback_id)

    from .asset_candidate_service import AssetCandidateRecord, asset_candidates_path, list_asset_candidates, upsert_asset_candidate

    timestamp = _now()
    candidate_id = f"employee-improvement-{_safe_asset_ref(normalized_employee_id)}-{_safe_asset_ref(normalized_feedback_id)}"
    existing_candidate = next((item for item in list_asset_candidates(asset_type="employee_improvement") if item.id == candidate_id), None)
    actor_employee_id = request.actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID
    title = request.title.strip() or f"Improve {normalized_employee_id} from {feedback.kind or 'quality'} feedback"
    content = request.content.strip() or _employee_improvement_content(normalized_employee_id, feedback, request.reason)
    relationships = _employee_improvement_relationships(normalized_employee_id, feedback)
    profile_updates = _employee_improvement_profile_updates(request)
    if not any(profile_updates.values()) and existing_candidate is not None:
        existing_updates = existing_candidate.provenance.get("proposed_profile_updates")
        if isinstance(existing_updates, dict):
            profile_updates = {
                "skill_refs": _unique_profile_update_values(existing_updates.get("skill_refs") if isinstance(existing_updates.get("skill_refs"), list) else []),
                "memory_scopes": _unique_profile_update_values(existing_updates.get("memory_scopes") if isinstance(existing_updates.get("memory_scopes"), list) else []),
                "capability_tags": _unique_profile_update_values(existing_updates.get("capability_tags") if isinstance(existing_updates.get("capability_tags"), list) else []),
                "personality_tags": _unique_profile_update_values(existing_updates.get("personality_tags") if isinstance(existing_updates.get("personality_tags"), list) else []),
            }
    candidate = upsert_asset_candidate(
        AssetCandidateRecord(
            id=candidate_id,
            source_candidate_id=normalized_feedback_id,
            asset_id=existing_candidate.asset_id if existing_candidate is not None and existing_candidate.asset_id else f"asset-{candidate_id}",
            asset_type="employee_improvement",
            title=title,
            content=content,
            status="proposed",
            scope_kind="employee",
            scope_ref=normalized_employee_id,
            owner_employee_id=normalized_employee_id,
            source_kind="employee_quality_feedback",
            source_ref=feedback.source_ref or feedback.id,
            provenance={
                "source_employee_id": normalized_employee_id,
                "source_feedback_id": feedback.id,
                "source_feedback_kind": feedback.kind,
                "source_feedback_status": feedback.status,
                "source_feedback_summary": feedback.summary,
                "source_ticket_id": feedback.ticket_id,
                "source_ref": feedback.source_ref,
                "reviewer_employee_id": feedback.reviewer_employee_id,
                "proposed_by_employee_id": actor_employee_id,
                "proposal_reason": request.reason.strip(),
                "proposed_profile_updates": profile_updates,
                "improvement_loop": "employee_quality_feedback_to_asset_candidate.v1",
                "relationships": relationships,
            },
            relationships=relationships,
            review_state="proposed",
            created_at=existing_candidate.created_at if existing_candidate is not None and existing_candidate.created_at else timestamp,
            updated_at=timestamp,
        )
    )
    return EmployeeImprovementCandidateResponse(
        employee_id=normalized_employee_id,
        feedback=feedback,
        candidate=candidate.model_dump(mode="json"),
        saved_paths={"asset_candidates": _relative(asset_candidates_path())},
    )


def _employee_improvement_content(employee_id: str, feedback: EmployeeQualityFeedbackRecord, reason: str) -> str:
    lines = [
        f"Employee improvement proposal for {employee_id}.",
        "",
        f"Feedback kind: {feedback.kind or 'quality_feedback'}",
        f"Feedback status: {feedback.status or '-'}",
        f"Feedback summary: {feedback.summary or '-'}",
    ]
    if feedback.ticket_id:
        lines.append(f"Ticket: {feedback.ticket_id}")
    if feedback.source_ref:
        lines.append(f"Source: {feedback.source_ref}")
    if feedback.reviewer_employee_id:
        lines.append(f"Reviewer: {feedback.reviewer_employee_id}")
    normalized_reason = reason.strip()
    if normalized_reason:
        lines.extend(["", f"Reviewer proposal reason: {normalized_reason}"])
    lines.extend(
        [
            "",
            "Suggested follow-up:",
            "- Review the source Ticket, runtime run, or Asset review evidence.",
            "- Decide whether this should become a Skill, Memory, permission change, runtime setting, or handoff policy update.",
            "- Approve, link, or merge this candidate through the Asset Review Queue before changing durable Employee behavior.",
        ]
    )
    return "\n".join(lines)


def _employee_improvement_relationships(employee_id: str, feedback: EmployeeQualityFeedbackRecord) -> list[dict[str, Any]]:
    relationships: list[dict[str, Any]] = [
        {
            "type": "improves_employee",
            "target_kind": "employee",
            "target_ref": employee_id,
            "reason": "Quality feedback proposed an Employee improvement candidate.",
        }
    ]
    if feedback.ticket_id:
        relationships.append(
            {
                "type": "derived_from_ticket",
                "target_kind": "ticket",
                "target_ref": feedback.ticket_id,
                "reason": "Quality feedback was observed in this Ticket flow.",
            }
        )
    if feedback.source_ref:
        relationships.append(
            {
                "type": "derived_from_feedback",
                "target_kind": feedback.kind or "quality_feedback",
                "target_ref": feedback.source_ref,
                "reason": "Quality feedback source evidence for this proposed improvement.",
            }
        )
    return relationships


def _employee_improvement_profile_updates(request: EmployeeImprovementCandidateRequest) -> dict[str, list[str]]:
    return {
        "skill_refs": _unique_profile_update_values(request.proposed_skill_refs),
        "memory_scopes": _unique_profile_update_values(request.proposed_memory_scopes),
        "capability_tags": _unique_profile_update_values(request.proposed_capability_tags),
        "personality_tags": _unique_profile_update_values(request.proposed_personality_tags),
    }


def _unique_profile_update_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _safe_asset_ref(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip())
    return normalized.strip("-")[:160] or "feedback"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _metadata_string(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    return value.strip() if isinstance(value, str) else ""


def _is_positive_memory_usefulness_status(value: Any) -> bool:
    return str(value or "").strip().lower() in {"used", "promoted", "useful"}


def _closeout_status(status: str) -> bool:
    return status.strip().lower() in {"validated", "completed", "done", "closed"}


def _maybe_auto_propose_ticket_closeout_candidates(
    ticket: Ticket,
    *,
    actor_employee_id: str,
    actor_role: str,
    source_run_id: str,
    trigger: str,
    reason: str,
) -> Ticket:
    if not (_closeout_status(ticket.status) or any(_is_validation_pass_report_type(report.report_type) for report in ticket.reports)):
        return ticket
    if trigger == "state_transition":
        requirements = _ticket_evidence_requirements_from_ticket(ticket)
        if not requirements.satisfied:
            _record_auto_closeout_blocker(
                ticket,
                actor_employee_id=actor_employee_id,
                actor_role=actor_role,
                source_run_id=source_run_id,
                trigger=trigger,
                detail=(
                    "Auto closeout Asset candidates were not proposed because validation evidence is incomplete. "
                    f"Missing: {', '.join(requirements.missing_required)}."
                ),
            )
            return get_ticket(ticket.id) or ticket
    try:
        from .asset_candidate_service import TicketCloseoutAssetCandidateRequest, propose_ticket_closeout_asset_candidates

        propose_ticket_closeout_asset_candidates(
            ticket.id,
            TicketCloseoutAssetCandidateRequest(
                actor_employee_id=actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID,
                actor_role=_resolve_actor_role(actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID, actor_role),
                reason=reason,
            ),
        )
    except ValueError as exc:
        _record_auto_closeout_blocker(
            ticket,
            actor_employee_id=actor_employee_id,
            actor_role=actor_role,
            source_run_id=source_run_id,
            trigger=trigger,
            detail=str(exc),
        )
    except Exception:
        return ticket
    return get_ticket(ticket.id) or ticket


def _record_auto_closeout_blocker(
    ticket: Ticket,
    *,
    actor_employee_id: str,
    actor_role: str,
    source_run_id: str,
    trigger: str,
    detail: str,
) -> None:
    marker = f"Auto closeout blocked ({trigger})"
    if any(report.report_type == "ticket_closeout_blocked" and marker in report.content for report in ticket.reports):
        return
    try:
        ticket_adapter().add_ticket_report(
            ticket.id,
            TicketReportRequest(
                reporter_employee_id=actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID,
                reporter_role=_resolve_actor_role(actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID, actor_role),
                content=f"{marker}: {detail}",
                report_type="ticket_closeout_blocked",
                evidence=[],
                source_run_id=source_run_id.strip() or f"ticket-closeout-auto-blocked:{ticket.id}:{trigger}",
            ),
        )
    except Exception:
        return


def _asset_canonical_id(asset: TicketAssetRecord) -> str:
    return _metadata_string(asset.metadata, "asset_id") or _metadata_string(asset.metadata, "memory_id") or asset.id


def _execution_artifact_mirror_records() -> list[dict[str, Any]]:
    path = _workspace_dir() / "execution_artifacts.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    records: list[dict[str, Any]] = []
    for item in payload.values():
        if isinstance(item, dict):
            records.append(item)
    return records


def _execution_artifact_records_for_ticket(ticket_id: str) -> list[dict[str, Any]]:
    normalized = ticket_id.strip()
    return [
        record
        for record in _execution_artifact_mirror_records()
        if str(record.get("ticket_id") or "").strip() == normalized
    ]


def _execution_artifact_records_for_employee(employee_id: str) -> list[dict[str, Any]]:
    normalized = employee_id.strip()
    return [
        record
        for record in _execution_artifact_mirror_records()
        if str(record.get("employee_id") or "").strip() == normalized
    ]


def _numeric(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def _usage_cost(usage: dict[str, Any]) -> float:
    for key in ("cost_usd", "total_cost_usd", "estimated_cost_usd", "cost"):
        cost = _numeric(usage.get(key))
        if cost:
            return cost
    return 0.0


def _execution_latency_ms(record: dict[str, Any]) -> int:
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
    explicit = _numeric(usage.get("latency_ms") or usage.get("duration_ms"))
    if explicit:
        return int(round(explicit))
    started_at = str(record.get("started_at") or "").strip()
    finished_at = str(record.get("finished_at") or "").strip()
    if not (started_at and finished_at):
        return 0
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    latency = (finished - started).total_seconds() * 1000
    return int(round(latency)) if latency > 0 else 0


def _augment_employee_work_ledger(ledger: EmployeeWorkLedger) -> EmployeeWorkLedger:
    normalized = ledger.employee_id.strip()
    asset_candidates, approved_assets, asset_reviews, asset_feedback = _employee_asset_work_records(normalized)
    runtime_runs = _employee_runtime_run_records(normalized)
    runtime_feedback = _employee_runtime_quality_feedback(runtime_runs)
    contribution = {
        **ledger.contribution,
        "asset_candidate_count": len(asset_candidates),
        "approved_asset_count": len(approved_assets),
        "asset_review_count": len(asset_reviews),
        "runtime_run_count": len(runtime_runs),
        "quality_feedback_count": len(asset_feedback) + len(runtime_feedback),
        "tool_event_count": sum(run.tool_event_count for run in runtime_runs),
    }
    return ledger.model_copy(
        update={
            "asset_candidates": asset_candidates,
            "approved_assets": approved_assets,
            "asset_reviews": asset_reviews,
            "runtime_runs": runtime_runs,
            "quality_feedback": [*asset_feedback, *runtime_feedback],
            "contribution": contribution,
        }
    )


def _employee_asset_work_records(
    employee_id: str,
) -> tuple[
    list[EmployeeAssetWorkRecord],
    list[EmployeeAssetWorkRecord],
    list[EmployeeAssetReviewRecord],
    list[EmployeeQualityFeedbackRecord],
]:
    try:
        from .asset_candidate_service import list_asset_candidates, list_asset_records, list_asset_reviews
    except Exception:
        return [], [], [], []

    try:
        candidates = list_asset_candidates()
        assets = list_asset_records()
        reviews = list_asset_reviews()
    except Exception:
        return [], [], [], []

    matched_candidates = [
        candidate for candidate in candidates if _asset_candidate_matches_employee(candidate, employee_id)
    ]
    matched_candidate_ids = {candidate.id for candidate in matched_candidates}
    matched_asset_ids = {candidate.asset_id for candidate in matched_candidates if candidate.asset_id}
    matched_assets = [
        asset
        for asset in assets
        if _asset_record_matches_employee(asset, employee_id)
        or (asset.id and asset.id in matched_asset_ids)
        or (_asset_candidate_ref(asset) and _asset_candidate_ref(asset) in matched_candidate_ids)
    ]
    matched_asset_ids.update(asset.id for asset in matched_assets if asset.id)

    review_records: list[EmployeeAssetReviewRecord] = []
    quality_feedback: list[EmployeeQualityFeedbackRecord] = []
    for review in reviews:
        reviewer_match = _normalize_match_id(review.reviewer_employee_id) == _normalize_match_id(employee_id)
        candidate_match = review.candidate_id in matched_candidate_ids
        asset_match = review.asset_id in matched_asset_ids
        if not (reviewer_match or candidate_match or asset_match):
            continue
        relation = "reviewer" if reviewer_match else "asset_owner"
        review_records.append(
            EmployeeAssetReviewRecord(
                review_id=review.id,
                candidate_id=review.candidate_id,
                asset_id=review.asset_id,
                status=review.status,
                reviewer_employee_id=review.reviewer_employee_id,
                reason=review.reason,
                relation_to_employee=relation,
                created_at=review.created_at,
                updated_at=review.updated_at,
            )
        )
        if candidate_match or asset_match:
            quality_feedback.append(
                EmployeeQualityFeedbackRecord(
                    id=review.id,
                    kind="asset_review",
                    status=review.status,
                    summary=review.reason or f"Asset review status: {review.status}",
                    source_ref=review.candidate_id or review.asset_id,
                    reviewer_employee_id=review.reviewer_employee_id,
                    created_at=review.created_at,
                )
            )

    return (
        sorted([_asset_work_from_candidate(candidate) for candidate in matched_candidates], key=lambda item: item.updated_at or item.created_at, reverse=True),
        sorted([_asset_work_from_asset(asset) for asset in matched_assets], key=lambda item: item.updated_at or item.created_at, reverse=True),
        sorted(review_records, key=lambda item: item.updated_at or item.created_at, reverse=True),
        sorted(quality_feedback, key=lambda item: item.created_at, reverse=True),
    )


def _employee_runtime_run_records(employee_id: str) -> list[EmployeeRuntimeRunRecord]:
    records = []
    for record in _execution_artifact_records_for_employee(employee_id):
        usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
        records.append(
            EmployeeRuntimeRunRecord(
                request_id=str(record.get("request_id") or ""),
                run_id=str(record.get("run_id") or record.get("request_id") or ""),
                session_key=str(record.get("session_key") or _execution_session_key(record, employee_id)),
                ticket_id=str(record.get("ticket_id") or ""),
                action=str(record.get("action") or ""),
                executor_id=str(record.get("executor_id") or ""),
                status=str(record.get("status") or ""),
                trace_ref=str(record.get("trace_ref") or ""),
                artifact_count=len(record.get("artifacts") if isinstance(record.get("artifacts"), list) else []),
                evidence_count=len(record.get("evidence") if isinstance(record.get("evidence"), list) else []),
                tool_event_count=len(record.get("tool_events") if isinstance(record.get("tool_events"), list) else []),
                memory_candidate_count=len(record.get("memory_candidates") if isinstance(record.get("memory_candidates"), list) else []),
                latency_ms=_execution_latency_ms(record),
                total_cost=round(_usage_cost(usage), 6),
                started_at=str(record.get("started_at") or ""),
                finished_at=str(record.get("finished_at") or ""),
            )
    )
    return sorted(records, key=lambda item: item.finished_at or item.started_at or item.request_id, reverse=True)


def _execution_session_key(record: dict[str, Any], employee_id: str) -> str:
    employee = str(record.get("employee_id") or employee_id).strip()
    thread = str(record.get("thread_id") or record.get("run_id") or record.get("request_id") or "runtime").strip()
    ticket = str(record.get("ticket_id") or "none").strip() or "none"
    return f"{employee}::{thread}::{ticket}" if employee and thread else ""


def _employee_runtime_quality_feedback(runtime_runs: list[EmployeeRuntimeRunRecord]) -> list[EmployeeQualityFeedbackRecord]:
    feedback: list[EmployeeQualityFeedbackRecord] = []
    for run in runtime_runs:
        if run.status.strip().lower() not in {"blocked", "failed"}:
            continue
        feedback.append(
            EmployeeQualityFeedbackRecord(
                id=f"runtime-feedback:{run.request_id}",
                kind="runtime_result",
                status=run.status,
                summary=f"Runtime run {run.request_id} ended with status={run.status}.",
                source_ref=run.request_id,
                ticket_id=run.ticket_id,
                created_at=run.finished_at or run.started_at,
            )
        )
    return feedback


def _asset_work_from_candidate(candidate: Any) -> EmployeeAssetWorkRecord:
    provenance = candidate.provenance if isinstance(candidate.provenance, dict) else {}
    source_ticket_id = str(provenance.get("source_ticket_id") or "").strip()
    if not source_ticket_id and candidate.scope_kind == "ticket":
        source_ticket_id = candidate.scope_ref
    return EmployeeAssetWorkRecord(
        asset_id=candidate.asset_id,
        candidate_id=candidate.id,
        asset_type=candidate.asset_type,
        title=candidate.title,
        status=candidate.status,
        review_state=candidate.review_state,
        scope_kind=candidate.scope_kind,
        scope_ref=candidate.scope_ref,
        source_ticket_id=source_ticket_id,
        source_run_id=str(provenance.get("source_run_id") or provenance.get("run_id") or "").strip(),
        source_ref=candidate.source_ref,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def _asset_work_from_asset(asset: Any) -> EmployeeAssetWorkRecord:
    provenance = asset.provenance if isinstance(asset.provenance, dict) else {}
    application = provenance.get("employee_improvement_application")
    application_record = application if isinstance(application, dict) else {}
    source_ticket_id = str(provenance.get("source_ticket_id") or "").strip()
    if not source_ticket_id and asset.scope_kind == "ticket":
        source_ticket_id = asset.scope_ref
    return EmployeeAssetWorkRecord(
        asset_id=asset.id,
        candidate_id=_asset_candidate_ref(asset),
        asset_type=asset.asset_type,
        title=asset.title,
        status=asset.status,
        review_state=asset.review_state,
        scope_kind=asset.scope_kind,
        scope_ref=asset.scope_ref,
        source_ticket_id=source_ticket_id,
        source_run_id=str(provenance.get("source_run_id") or provenance.get("run_id") or "").strip(),
        source_ref=asset.source_ref,
        application_status=str(application_record.get("status") or "").strip(),
        application_report_id=str(application_record.get("ticket_report_id") or "").strip(),
        application_employee_id=str(application_record.get("employee_id") or "").strip(),
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _asset_candidate_matches_employee(candidate: Any, employee_id: str) -> bool:
    provenance = candidate.provenance if isinstance(candidate.provenance, dict) else {}
    return _normalize_match_id(employee_id) in {
        _normalize_match_id(candidate.owner_employee_id),
        _normalize_match_id(str(provenance.get("source_employee_id") or "")),
        _normalize_match_id(str(provenance.get("derived_from_employee_id") or "")),
    }


def _asset_record_matches_employee(asset: Any, employee_id: str) -> bool:
    provenance = asset.provenance if isinstance(asset.provenance, dict) else {}
    return _normalize_match_id(employee_id) in {
        _normalize_match_id(asset.owner_employee_id),
        _normalize_match_id(str(provenance.get("source_employee_id") or "")),
        _normalize_match_id(str(provenance.get("derived_from_employee_id") or "")),
    }


def _asset_candidate_ref(asset: Any) -> str:
    provenance = asset.provenance if isinstance(asset.provenance, dict) else {}
    return str(
        provenance.get("source_asset_candidate_id")
        or provenance.get("source_candidate_id")
        or provenance.get("source_memory_candidate_id")
        or ""
    ).strip()


def _normalize_match_id(value: str) -> str:
    return value.strip().lower()


def _graph_employee_key(employee_id: str, role: str) -> str:
    employee_id = employee_id.strip()
    if employee_id:
        return employee_id
    role = role.strip()
    return f"role:{role}" if role else "unassigned"


def ticket_graph_projection(ticket_id: str) -> TicketGraphProjection | None:
    adapter = ticket_adapter()
    target_ticket_id = ticket_id.strip()
    if not target_ticket_id:
        return None
    ticket = next((item for item in adapter.list_tickets() if item.id == target_ticket_id), None)
    if ticket is None:
        ticket = adapter.get_ticket(target_ticket_id)
    if ticket is None:
        return None
    events = adapter.get_ticket_events(ticket.id) or ticket.events
    linked_assets = [
        asset
        for asset in ticket_asset_records()
        if asset.source_ticket_id == ticket.id or _metadata_string(asset.metadata, "derived_from_ticket_id") == ticket.id
    ]

    nodes: dict[str, TicketGraphNode] = {}
    edges: dict[str, TicketGraphEdge] = {}

    def add_node(kind: str, key: str, label: str, *, status: str = "", ref: str = "", metadata: dict[str, Any] | None = None) -> str:
        node_id = f"{kind}:{key}"
        if node_id not in nodes:
            nodes[node_id] = TicketGraphNode(
                id=node_id,
                kind=kind,
                label=label or key,
                status=status,
                ref=ref or key,
                metadata=metadata or {},
            )
        return node_id

    def add_employee(employee_id: str, role: str = "") -> str:
        key = _graph_employee_key(employee_id, role)
        label = employee_id.strip() or role.strip() or "Unassigned"
        return add_node("employee", key, label, status=role.strip(), ref=employee_id.strip(), metadata={"role": role.strip()} if role.strip() else {})

    def add_edge(
        edge_type: str,
        source_id: str,
        target_id: str,
        *,
        label: str = "",
        evidence_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        edge_id = f"{edge_type}:{source_id}->{target_id}"
        existing = edges.get(edge_id)
        if existing is not None:
            existing.evidence_refs = sorted({*existing.evidence_refs, *(evidence_refs or [])})
            existing.metadata = {**existing.metadata, **(metadata or {})}
            if label and not existing.label:
                existing.label = label
            return
        edges[edge_id] = TicketGraphEdge(
            id=edge_id,
            type=edge_type,
            source_id=source_id,
            target_id=target_id,
            label=label,
            evidence_refs=evidence_refs or [],
            metadata=metadata or {},
        )

    ticket_node = add_node(
        "ticket",
        ticket.id,
        ticket.title,
        status=ticket.status,
        ref=ticket.id,
        metadata={
            "ticket_type": ticket.ticket_type,
            "provider_ref": ticket.provider_ref.model_dump(mode="json") if ticket.provider_ref else None,
            "external_url": ticket.external_url,
        },
    )

    if ticket.assigned_employee_id or ticket.assigned_role:
        assigned_employee = add_employee(ticket.assigned_employee_id, ticket.assigned_role)
        add_edge("ticket.assigned_to.employee", ticket_node, assigned_employee, label="assigned to")
    if ticket.validation_employee_id or ticket.validation_role:
        validation_employee = add_employee(ticket.validation_employee_id, ticket.validation_role)
        add_edge("ticket.validated_by.employee", ticket_node, validation_employee, label="validated by")

    run_node = ""
    if ticket.source_run_id:
        run_node = add_node("run", ticket.source_run_id, ticket.source_run_id, ref=ticket.source_run_id)

    for repo_id in ticket.code_repository_ids:
        repo_node = add_node("repository", repo_id, repo_id, ref=repo_id)
        add_edge("ticket.references_repository", ticket_node, repo_node, label="references")

    for knowledge_ref in ticket.knowledge_refs:
        if run_node:
            doc_node = add_node("doc", knowledge_ref, knowledge_ref, ref=knowledge_ref)
            add_edge("run.reads_doc", run_node, doc_node, label="reads")

    for report in ticket.reports:
        report_node = add_node(
            "report",
            report.id,
            f"{report.report_type} report",
            status=report.report_type,
            ref=report.id,
            metadata={"ticket_id": ticket.id, "source_event_id": report.source_event_id},
        )
        reporter_node = add_employee(report.reporter_employee_id, report.reporter_role)
        add_edge("employee.produced.report", reporter_node, report_node, label="produced")
        add_edge("report.belongs_to.ticket", report_node, ticket_node, label="belongs to")
        if _is_validation_pass_report_type(report.report_type):
            add_edge(
                "ticket.validated_by.employee",
                ticket_node,
                reporter_node,
                label="validated by",
                evidence_refs=report.evidence,
                metadata={"report_id": report.id},
            )
        source_event = next((event for event in events if event.event_id == report.source_event_id), None)
        source_run_id = str(source_event.data.get("source_run_id") or "").strip() if source_event else ""
        if source_run_id:
            source_run_node = add_node("run", source_run_id, source_run_id, ref=source_run_id)
            add_edge("run.produces.report", source_run_node, report_node, label="produces")
        for index, evidence in enumerate(report.evidence):
            evidence_id = f"{report.id}:{index}"
            evidence_node = add_node("evidence", evidence_id, evidence, ref=evidence, metadata={"report_id": report.id})
            add_edge("report.has_evidence", report_node, evidence_node, label="has evidence", evidence_refs=[evidence])

    for asset in linked_assets:
        asset_node = add_node(
            "asset",
            asset.id,
            asset.title,
            status=asset.status,
            ref=asset.id,
            metadata={"kind": asset.kind, **asset.metadata},
        )
        if asset.kind == "memory_candidate":
            add_edge("memory.derived_from.ticket", asset_node, ticket_node, label="derived from")
            source_run_id = _metadata_string(asset.metadata, "source_run_id")
            if source_run_id:
                source_run_node = add_node("run", source_run_id, source_run_id, ref=source_run_id)
                add_edge("run.proposes_memory_candidate", source_run_node, asset_node, label="proposes")
        elif asset.kind == "memory":
            usage_ticket_node = add_node("ticket", asset.source_ticket_id, asset.source_ticket_id, ref=asset.source_ticket_id)
            source_run_id = _metadata_string(asset.metadata, "source_run_id")
            if source_run_id:
                source_run_node = add_node("run", source_run_id, source_run_id, ref=source_run_id)
                add_edge("run.recalls_memory", source_run_node, asset_node, label="recalls", metadata={"usage_id": _metadata_string(asset.metadata, "usage_id")})
            derived_ticket_id = _metadata_string(asset.metadata, "derived_from_ticket_id")
            if derived_ticket_id:
                derived_ticket_node = add_node("ticket", derived_ticket_id, derived_ticket_id, ref=derived_ticket_id)
                add_edge("memory.derived_from.ticket", asset_node, derived_ticket_node, label="derived from")
            add_edge("asset.used_by.ticket", asset_node, usage_ticket_node, label="used by")
        else:
            add_edge("asset.linked_to.ticket", asset_node, ticket_node, label="linked to")

    execution_records = _execution_artifact_records_for_ticket(ticket.id)
    for record in execution_records:
        run_id = str(record.get("run_id") or record.get("request_id") or "").strip()
        if not run_id:
            continue
        run_metadata = {
            "request_id": str(record.get("request_id") or "").strip(),
            "executor_id": str(record.get("executor_id") or "").strip(),
            "executor_session_ref": str(record.get("executor_session_ref") or "").strip(),
            "checkpoint_ref": str(record.get("checkpoint_ref") or "").strip(),
            "trace_ref": str(record.get("trace_ref") or "").strip(),
            "action": str(record.get("action") or "").strip(),
            "usage": record.get("usage") if isinstance(record.get("usage"), dict) else {},
        }
        execution_run_node = add_node(
            "run",
            run_id,
            run_id,
            status=str(record.get("status") or ""),
            ref=run_id,
            metadata=run_metadata,
        )
        add_edge("run.executed_for.ticket", execution_run_node, ticket_node, label="executed for", metadata=run_metadata)
        employee_id = str(record.get("employee_id") or "").strip()
        if employee_id:
            employee_node = add_employee(employee_id)
            add_edge("employee.started.run", employee_node, execution_run_node, label="started", metadata={"request_id": run_metadata["request_id"]})

        tool_events = record.get("tool_events") if isinstance(record.get("tool_events"), list) else []
        for index, event in enumerate(tool_events):
            if not isinstance(event, dict):
                continue
            command = event.get("data", {}).get("command") if isinstance(event.get("data"), dict) else {}
            command_id = str((command.get("id") if isinstance(command, dict) else "") or event.get("event") or f"tool-{index}").strip()
            tool_key = f"{run_id}:{index}:{command_id or 'tool'}"
            tool_node = add_node(
                "tool_call",
                tool_key,
                command_id or str(event.get("event") or "tool"),
                status=str(event.get("event") or ""),
                ref=command_id,
                metadata={"event": event.get("event"), "detail": event.get("detail"), "data": event.get("data") if isinstance(event.get("data"), dict) else {}},
            )
            add_edge("run.calls.tool", execution_run_node, tool_node, label="calls", metadata={"request_id": run_metadata["request_id"]})

        artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), list) else []
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                continue
            artifact_kind = str(artifact.get("kind") or "artifact").strip()
            artifact_ref = str(artifact.get("id") or artifact.get("asset_id") or artifact.get("title") or f"{run_id}:artifact:{index}").strip()
            artifact_node = add_node(
                "artifact",
                f"{run_id}:{index}:{artifact_ref}",
                artifact_kind,
                status=str(record.get("status") or ""),
                ref=artifact_ref,
                metadata={"kind": artifact_kind, "artifact": artifact, "request_id": run_metadata["request_id"]},
            )
            add_edge("run.produces.artifact", execution_run_node, artifact_node, label="produces", metadata={"artifact_kind": artifact_kind})

        execution_evidence = record.get("evidence") if isinstance(record.get("evidence"), list) else []
        for index, evidence in enumerate(execution_evidence):
            if not isinstance(evidence, dict):
                continue
            evidence_ref = str(evidence.get("ref") or evidence.get("evidence_ref") or evidence.get("summary") or evidence.get("kind") or f"{run_id}:evidence:{index}").strip()
            evidence_node = add_node(
                "evidence",
                f"{run_id}:execution-evidence:{index}",
                evidence_ref,
                ref=evidence_ref,
                metadata={"evidence": evidence, "request_id": run_metadata["request_id"]},
            )
            add_edge("run.produces.evidence", execution_run_node, evidence_node, label="produces", evidence_refs=[evidence_ref])

    grouped_edges: dict[str, list[TicketGraphEdge]] = {}
    for edge in sorted(edges.values(), key=lambda item: (item.type, item.id)):
        grouped_edges.setdefault(edge.type, []).append(edge)
    return TicketGraphProjection(
        ticket_id=ticket.id,
        nodes=sorted(nodes.values(), key=lambda item: (item.kind, item.id)),
        edges=sorted(edges.values(), key=lambda item: (item.type, item.id)),
        grouped_edges=grouped_edges,
        source_counts={
            "events": len(events),
            "reports": len(ticket.reports),
            "assets": len(linked_assets),
            "evidence": sum(len(report.evidence) for report in ticket.reports),
            "runs": len(execution_records),
            "tool_events": sum(len(record.get("tool_events") if isinstance(record.get("tool_events"), list) else []) for record in execution_records),
            "artifacts": sum(len(record.get("artifacts") if isinstance(record.get("artifacts"), list) else []) for record in execution_records),
        },
    )


def employee_graph_projection(employee_id: str) -> EmployeeGraphProjection | None:
    normalized = employee_id.strip()
    if not normalized:
        return None
    role = _employee_role(normalized)
    employee_key = _graph_employee_key(normalized, role)
    employee_node_id = f"employee:{employee_key}"

    nodes: dict[str, TicketGraphNode] = {
        employee_node_id: TicketGraphNode(
            id=employee_node_id,
            kind="employee",
            label=normalized,
            status=role,
            ref=normalized,
            metadata={"role": role} if role else {},
        )
    }
    edges: dict[str, TicketGraphEdge] = {}
    touched_tickets: set[str] = set()
    touched_reports: set[str] = set()
    touched_assets: set[str] = set()

    def add_node(kind: str, key: str, label: str, *, status: str = "", ref: str = "", metadata: dict[str, Any] | None = None) -> str:
        node_id = f"{kind}:{key}"
        if node_id not in nodes:
            nodes[node_id] = TicketGraphNode(
                id=node_id,
                kind=kind,
                label=label or key,
                status=status,
                ref=ref or key,
                metadata=metadata or {},
            )
        return node_id

    def add_edge(
        edge_type: str,
        source_id: str,
        target_id: str,
        *,
        label: str = "",
        evidence_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        edge_id = f"{edge_type}:{source_id}->{target_id}"
        existing = edges.get(edge_id)
        if existing is not None:
            existing.evidence_refs = sorted({*existing.evidence_refs, *(evidence_refs or [])})
            existing.metadata = {**existing.metadata, **(metadata or {})}
            if label and not existing.label:
                existing.label = label
            return
        edges[edge_id] = TicketGraphEdge(
            id=edge_id,
            type=edge_type,
            source_id=source_id,
            target_id=target_id,
            label=label,
            evidence_refs=evidence_refs or [],
            metadata=metadata or {},
        )

    adapter = ticket_adapter()
    tickets = adapter.list_tickets()
    events_by_ticket = {ticket.id: (adapter.get_ticket_events(ticket.id) or ticket.events) for ticket in tickets}
    for ticket in tickets:
        ticket_node = add_node("ticket", ticket.id, ticket.title, status=ticket.status, ref=ticket.id)
        if ticket.assigned_employee_id == normalized:
            touched_tickets.add(ticket.id)
            add_edge("ticket.assigned_to.employee", ticket_node, employee_node_id, label="assigned to")
        if ticket.validation_employee_id == normalized:
            touched_tickets.add(ticket.id)
            add_edge("ticket.validated_by.employee", ticket_node, employee_node_id, label="validated by")

        for event in events_by_ticket.get(ticket.id, []):
            if event.actor.get("id", "") == normalized:
                touched_tickets.add(ticket.id)
                add_edge(
                    "employee.acted_on.ticket",
                    employee_node_id,
                    ticket_node,
                    label=event.type,
                    metadata={"event_id": event.event_id, "event_type": event.type, "at": event.at},
                )

        for report in ticket.reports:
            if report.reporter_employee_id != normalized:
                continue
            touched_tickets.add(ticket.id)
            touched_reports.add(report.id)
            report_node = add_node(
                "report",
                report.id,
                f"{report.report_type} report",
                status=report.report_type,
                ref=report.id,
                metadata={"ticket_id": ticket.id, "source_event_id": report.source_event_id},
            )
            add_edge("employee.produced.report", employee_node_id, report_node, label="produced")
            add_edge("report.belongs_to.ticket", report_node, ticket_node, label="belongs to")
            if _is_validation_pass_report_type(report.report_type):
                add_edge("ticket.validated_by.employee", ticket_node, employee_node_id, label="validated by", evidence_refs=report.evidence, metadata={"report_id": report.id})
            source_event = next((event for event in events_by_ticket.get(ticket.id, []) if event.event_id == report.source_event_id), None)
            source_run_id = str(source_event.data.get("source_run_id") or "").strip() if source_event else ""
            if source_run_id:
                run_node = add_node("run", source_run_id, source_run_id, ref=source_run_id)
                add_edge("run.produces.report", run_node, report_node, label="produces")
            for index, evidence in enumerate(report.evidence):
                evidence_id = f"{report.id}:{index}"
                evidence_node = add_node("evidence", evidence_id, evidence, ref=evidence, metadata={"report_id": report.id})
                add_edge("report.has_evidence", report_node, evidence_node, label="has evidence", evidence_refs=[evidence])

    for asset in ticket_asset_records():
        source_employee_match = asset.source_employee_id == normalized
        assigned_employee_match = normalized in asset.assigned_employees
        if not (source_employee_match or assigned_employee_match):
            continue
        touched_assets.add(asset.id)
        asset_node = add_node(
            "asset",
            asset.id,
            asset.title,
            status=asset.status,
            ref=asset.id,
            metadata={"kind": asset.kind, **asset.metadata},
        )
        if source_employee_match:
            add_edge("employee.produced.asset", employee_node_id, asset_node, label="produced")
        if assigned_employee_match:
            add_edge("asset.assigned_to.employee", asset_node, employee_node_id, label="assigned to")
        if asset.source_ticket_id:
            touched_tickets.add(asset.source_ticket_id)
            source_ticket_node = add_node("ticket", asset.source_ticket_id, asset.source_ticket_id, ref=asset.source_ticket_id)
            add_edge("asset.linked_to.ticket", asset_node, source_ticket_node, label="linked to")
        if asset.kind == "memory":
            derived_ticket_id = _metadata_string(asset.metadata, "derived_from_ticket_id")
            if derived_ticket_id:
                derived_ticket_node = add_node("ticket", derived_ticket_id, derived_ticket_id, ref=derived_ticket_id)
                add_edge("memory.derived_from.ticket", asset_node, derived_ticket_node, label="derived from")
            source_run_id = _metadata_string(asset.metadata, "source_run_id")
            if source_run_id:
                run_node = add_node("run", source_run_id, source_run_id, ref=source_run_id)
                add_edge("run.recalls_memory", run_node, asset_node, label="recalls", metadata={"usage_id": _metadata_string(asset.metadata, "usage_id")})
        elif asset.kind == "memory_candidate":
            source_run_id = _metadata_string(asset.metadata, "source_run_id")
            if source_run_id:
                run_node = add_node("run", source_run_id, source_run_id, ref=source_run_id)
                add_edge("run.proposes_memory_candidate", run_node, asset_node, label="proposes")

    grouped_edges: dict[str, list[TicketGraphEdge]] = {}
    for edge in sorted(edges.values(), key=lambda item: (item.type, item.id)):
        grouped_edges.setdefault(edge.type, []).append(edge)
    return EmployeeGraphProjection(
        employee_id=normalized,
        nodes=sorted(nodes.values(), key=lambda item: (item.kind, item.id)),
        edges=sorted(edges.values(), key=lambda item: (item.type, item.id)),
        grouped_edges=grouped_edges,
        source_counts={
            "tickets": len(touched_tickets),
            "reports": len(touched_reports),
            "assets": len(touched_assets),
            "events": len([edge for edge in edges.values() if edge.type == "employee.acted_on.ticket"]),
        },
        provider_projection=_employee_provider_projection(normalized),
    )


def _employee_provider_projection(employee_id: str) -> dict[str, Any]:
    try:
        from .memory_service import employee_profile_projection_status

        return {"employee_profile": employee_profile_projection_status(employee_id)}
    except Exception as exc:
        return {
            "employee_profile": {
                "provider": "graphiti",
                "status": "unavailable",
                "detail": str(exc),
            }
        }


def asset_graph_projection(asset_id: str) -> AssetGraphProjection | None:
    normalized = asset_id.strip()
    if not normalized:
        return None

    records = ticket_asset_records()
    target_canonical_id = ""
    for record in records:
        canonical_id = _asset_canonical_id(record)
        if record.id == normalized or canonical_id == normalized:
            target_canonical_id = canonical_id
            break
    if not target_canonical_id:
        return None

    related_records = [
        record
        for record in records
        if record.id == normalized or _asset_canonical_id(record) == target_canonical_id
    ]
    if not related_records:
        return None

    nodes: dict[str, TicketGraphNode] = {}
    edges: dict[str, TicketGraphEdge] = {}
    touched_tickets: set[str] = set()
    touched_employees: set[str] = set()
    touched_reports: set[str] = set()
    touched_evidence: set[str] = set()
    touched_runs: set[str] = set()

    def add_node(kind: str, key: str, label: str, *, status: str = "", ref: str = "", metadata: dict[str, Any] | None = None) -> str:
        node_id = f"{kind}:{key}"
        if node_id not in nodes:
            nodes[node_id] = TicketGraphNode(
                id=node_id,
                kind=kind,
                label=label or key,
                status=status,
                ref=ref or key,
                metadata=metadata or {},
            )
            return node_id
        existing = nodes[node_id]
        existing.metadata = {**existing.metadata, **(metadata or {})}
        if status and not existing.status:
            existing.status = status
        if label and existing.label == key:
            existing.label = label
        return node_id

    def add_employee(employee_id: str, role: str = "") -> str:
        key = _graph_employee_key(employee_id, role)
        label = employee_id.strip() or role.strip() or "Unassigned"
        if employee_id.strip():
            touched_employees.add(employee_id.strip())
        return add_node("employee", key, label, status=role.strip(), ref=employee_id.strip(), metadata={"role": role.strip()} if role.strip() else {})

    def add_edge(
        edge_type: str,
        source_id: str,
        target_id: str,
        *,
        label: str = "",
        evidence_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        edge_id = f"{edge_type}:{source_id}->{target_id}"
        existing = edges.get(edge_id)
        if existing is not None:
            existing.evidence_refs = sorted({*existing.evidence_refs, *(evidence_refs or [])})
            existing.metadata = {**existing.metadata, **(metadata or {})}
            if label and not existing.label:
                existing.label = label
            return
        edges[edge_id] = TicketGraphEdge(
            id=edge_id,
            type=edge_type,
            source_id=source_id,
            target_id=target_id,
            label=label,
            evidence_refs=evidence_refs or [],
            metadata=metadata or {},
        )

    asset_node = ""
    for record in related_records:
        metadata = {"kind": record.kind, "record_id": record.id, **record.metadata}
        asset_node = add_node(
            "asset",
            target_canonical_id,
            record.title,
            status=record.status,
            ref=target_canonical_id,
            metadata=metadata,
        )
        if record.source_employee_id:
            producer_node = add_employee(record.source_employee_id)
            add_edge("employee.produced.asset", producer_node, asset_node, label="produced", metadata={"record_id": record.id})
        derived_employee_id = _metadata_string(record.metadata, "derived_from_employee_id")
        if derived_employee_id and derived_employee_id != record.source_employee_id:
            producer_node = add_employee(derived_employee_id)
            add_edge("employee.produced.asset", producer_node, asset_node, label="produced", metadata={"record_id": record.id})
        for employee_id in record.assigned_employees:
            assigned_node = add_employee(employee_id)
            add_edge("asset.assigned_to.employee", asset_node, assigned_node, label="assigned to", metadata={"record_id": record.id})

        source_ticket_id = record.source_ticket_id.strip()
        if source_ticket_id:
            touched_tickets.add(source_ticket_id)
            ticket_node = add_node("ticket", source_ticket_id, source_ticket_id, ref=source_ticket_id)
            if record.kind == "memory_candidate":
                add_edge("memory.derived_from.ticket", asset_node, ticket_node, label="derived from", metadata={"record_id": record.id})
            elif record.kind == "memory":
                add_edge("asset.used_by.ticket", asset_node, ticket_node, label="used by", metadata={"record_id": record.id, "usage_id": _metadata_string(record.metadata, "usage_id")})
            else:
                add_edge("asset.linked_to.ticket", asset_node, ticket_node, label="linked to", metadata={"record_id": record.id})

        derived_ticket_id = _metadata_string(record.metadata, "derived_from_ticket_id")
        if derived_ticket_id:
            touched_tickets.add(derived_ticket_id)
            derived_ticket_node = add_node("ticket", derived_ticket_id, derived_ticket_id, ref=derived_ticket_id)
            add_edge("memory.derived_from.ticket", asset_node, derived_ticket_node, label="derived from", metadata={"record_id": record.id})

        source_run_id = _metadata_string(record.metadata, "source_run_id")
        if source_run_id:
            touched_runs.add(source_run_id)
            run_node = add_node("run", source_run_id, source_run_id, ref=source_run_id)
            if record.kind == "memory_candidate":
                add_edge("run.proposes_memory_candidate", run_node, asset_node, label="proposes", metadata={"record_id": record.id})
            elif record.kind == "memory":
                add_edge("run.recalls_memory", run_node, asset_node, label="recalls", metadata={"record_id": record.id, "usage_id": _metadata_string(record.metadata, "usage_id")})

        source_report_id = _metadata_string(record.metadata, "source_report_id")
        if source_report_id:
            touched_reports.add(source_report_id)
            report_node = add_node("report", source_report_id, source_report_id, ref=source_report_id)
            add_edge("report.supports.asset", report_node, asset_node, label="supports", metadata={"record_id": record.id})
            evidence_id = _metadata_string(record.metadata, "evidence_id")
            if evidence_id:
                touched_evidence.add(evidence_id)
                evidence_node = add_node("evidence", evidence_id, evidence_id, ref=evidence_id)
                add_edge("report.has_evidence", report_node, evidence_node, label="has evidence", evidence_refs=[evidence_id])
                add_edge("evidence.supports.asset", evidence_node, asset_node, label="supports", evidence_refs=[evidence_id], metadata={"record_id": record.id})

    grouped_edges: dict[str, list[TicketGraphEdge]] = {}
    for edge in sorted(edges.values(), key=lambda item: (item.type, item.id)):
        grouped_edges.setdefault(edge.type, []).append(edge)
    return AssetGraphProjection(
        asset_id=target_canonical_id,
        nodes=sorted(nodes.values(), key=lambda item: (item.kind, item.id)),
        edges=sorted(edges.values(), key=lambda item: (item.type, item.id)),
        grouped_edges=grouped_edges,
        source_counts={
            "records": len(related_records),
            "tickets": len(touched_tickets),
            "employees": len(touched_employees),
            "reports": len(touched_reports),
            "evidence": len(touched_evidence),
            "runs": len(touched_runs),
        },
    )


def ticket_assets_for_ticket(ticket_id: str) -> list[TicketAssetRecord]:
    target_ticket_id = ticket_id.strip()
    if not target_ticket_id:
        return []
    return [
        asset
        for asset in ticket_asset_records()
        if asset.source_ticket_id == target_ticket_id or _metadata_string(asset.metadata, "derived_from_ticket_id") == target_ticket_id
    ]


def asset_graph_status() -> AssetGraphStatus:
    adapter = ticket_adapter()
    tickets = adapter.list_tickets()
    assets = ticket_asset_records()
    employee_ids: set[str] = set()
    for ticket in tickets:
        if ticket.assigned_employee_id:
            employee_ids.add(ticket.assigned_employee_id)
        if ticket.validation_employee_id:
            employee_ids.add(ticket.validation_employee_id)
        for report in ticket.reports:
            if report.reporter_employee_id:
                employee_ids.add(report.reporter_employee_id)
    for asset in assets:
        if asset.source_employee_id:
            employee_ids.add(asset.source_employee_id)
        for employee_id in asset.assigned_employees:
            if employee_id:
                employee_ids.add(employee_id)
    return AssetGraphStatus(
        status="ready",
        detail="Asset graph read model is rebuildable from AITeamOS Ticket, Employee, report, evidence, and durable asset provenance.",
        ticket_count=len(tickets),
        asset_record_count=len(assets),
        graph_asset_count=len({_asset_canonical_id(asset) for asset in assets}),
        employee_count=len(employee_ids),
        capabilities=[
            "ticket_graph_projection",
            "employee_graph_projection",
            "asset_graph_projection",
            "ticket_assets_for_ticket",
        ],
    )


def _employee_ids_from_work_facts(tickets: list[Ticket], assets: list[TicketAssetRecord]) -> list[str]:
    employee_ids: set[str] = set()
    for ticket in tickets:
        if ticket.assigned_employee_id:
            employee_ids.add(ticket.assigned_employee_id)
        if ticket.validation_employee_id:
            employee_ids.add(ticket.validation_employee_id)
        for report in ticket.reports:
            if report.reporter_employee_id:
                employee_ids.add(report.reporter_employee_id)
        for event in ticket.events:
            actor_id = event.actor.get("id", "")
            if actor_id:
                employee_ids.add(actor_id)
    for asset in assets:
        if asset.source_employee_id:
            employee_ids.add(asset.source_employee_id)
        derived_employee_id = _metadata_string(asset.metadata, "derived_from_employee_id")
        if derived_employee_id:
            employee_ids.add(derived_employee_id)
        for employee_id in asset.assigned_employees:
            if employee_id:
                employee_ids.add(employee_id)
    for record in _execution_artifact_mirror_records():
        employee_id = str(record.get("employee_id") or "").strip()
        if employee_id:
            employee_ids.add(employee_id)
    return sorted(employee_ids)


def _employee_analytics_from_facts(employee_id: str, tickets: list[Ticket], assets: list[TicketAssetRecord]) -> EmployeeAnalytics:
    normalized = employee_id.strip()
    assigned_ticket_ids: set[str] = set()
    completed_ticket_ids: set[str] = set()
    validation_reports = 0
    validation_passes = 0
    validation_failure_count = 0
    report_count = 0
    event_count = 0

    for ticket in tickets:
        participates = False
        if ticket.assigned_employee_id == normalized:
            assigned_ticket_ids.add(ticket.id)
            participates = True
            if _terminal_status(ticket.status):
                completed_ticket_ids.add(ticket.id)
        if ticket.validation_employee_id == normalized:
            participates = True
        for report in ticket.reports:
            if report.reporter_employee_id != normalized:
                continue
            participates = True
            report_count += 1
            if _is_validation_pass_report_type(report.report_type):
                validation_reports += 1
                if ticket.status.lower() in {"validated", "completed", "done", "closed"}:
                    validation_passes += 1
            if _is_validation_failure_report_type(report.report_type):
                validation_failure_count += 1
        for event in ticket.events:
            if event.actor.get("id", "") == normalized:
                participates = True
                event_count += 1
        if participates and _terminal_status(ticket.status) and ticket.id in assigned_ticket_ids:
            completed_ticket_ids.add(ticket.id)

    candidates_produced = sum(
        1
        for asset in assets
        if asset.kind == "memory_candidate"
        and (asset.source_employee_id == normalized or _metadata_string(asset.metadata, "derived_from_employee_id") == normalized)
    )
    recalled_asset_count = sum(1 for asset in assets if asset.kind == "memory" and asset.source_employee_id == normalized)
    stale_asset_count = sum(
        1
        for asset in assets
        if asset.status in {"stale", "superseded"}
        and (
            asset.source_employee_id == normalized
            or _metadata_string(asset.metadata, "derived_from_employee_id") == normalized
            or normalized in asset.assigned_employees
        )
    )
    useful_recall_count = sum(
        1
        for asset in assets
        if asset.kind == "memory"
        and asset.source_employee_id == normalized
        and _is_positive_memory_usefulness_status(asset.metadata.get("usefulness_status"))
    )
    execution_records = _execution_artifact_records_for_employee(normalized)
    execution_latencies = [_execution_latency_ms(record) for record in execution_records]
    execution_latencies = [latency for latency in execution_latencies if latency > 0]
    execution_blockers = len([
        record
        for record in execution_records
        if str(record.get("status") or "").strip().lower() in {"blocked", "failed"}
    ])
    total_cost = round(
        sum(
            _usage_cost(record.get("usage") if isinstance(record.get("usage"), dict) else {})
            for record in execution_records
        ),
        6,
    )
    validation_pass_rate = round(validation_passes / validation_reports, 3) if validation_reports else 0.0
    return EmployeeAnalytics(
        employee_id=normalized,
        assigned_ticket_count=len(assigned_ticket_ids),
        completed_ticket_count=len(completed_ticket_ids),
        validation_pass_rate=validation_pass_rate,
        candidates_produced=candidates_produced,
        recalled_asset_count=recalled_asset_count,
        blocker_count=validation_failure_count + execution_blockers,
        validation_failure_count=validation_failure_count,
        stale_asset_count=stale_asset_count,
        useful_recall_count=useful_recall_count,
        execution_run_count=len(execution_records),
        total_cost=total_cost,
        average_latency_ms=int(round(sum(execution_latencies) / len(execution_latencies))) if execution_latencies else 0,
        source_counts={
            "tickets": len([ticket for ticket in tickets if ticket.assigned_employee_id == normalized or ticket.validation_employee_id == normalized]),
            "reports": report_count,
            "events": event_count,
            "assets": len([
                asset
                for asset in assets
                if asset.source_employee_id == normalized
                or _metadata_string(asset.metadata, "derived_from_employee_id") == normalized
                or normalized in asset.assigned_employees
            ]),
            "execution_runs": len(execution_records),
        },
    )


def _ticket_contribution_key(employee_id: str, role: str) -> str:
    normalized_employee = employee_id.strip()
    if normalized_employee:
        return normalized_employee
    normalized_role = role.strip()
    return f"role:{normalized_role}" if normalized_role else "system"


def _touch_ticket_contribution(
    records: dict[str, TicketEmployeeContribution],
    *,
    employee_id: str = "",
    role: str = "",
) -> TicketEmployeeContribution:
    key = _ticket_contribution_key(employee_id, role)
    record = records.get(key)
    if record is None:
        record = TicketEmployeeContribution(employee_id=key, role=role.strip())
        records[key] = record
    if role.strip():
        roles = [entry for entry in record.role.split(" / ") if entry]
        if role.strip() not in roles:
            record.role = " / ".join([*roles, role.strip()]) if roles else role.strip()
    return record


def ticket_evidence_requirements(ticket_id: str) -> TicketEvidenceRequirements | None:
    adapter = ticket_adapter()
    target_ticket_id = ticket_id.strip()
    if not target_ticket_id:
        return None
    ticket = next((item for item in adapter.list_tickets() if item.id == target_ticket_id), None)
    if ticket is None:
        ticket = adapter.get_ticket(target_ticket_id)
    if ticket is None:
        return None
    return _ticket_evidence_requirements_from_ticket(ticket)


def ticket_performance(ticket_id: str) -> TicketPerformance | None:
    adapter = ticket_adapter()
    target_ticket_id = ticket_id.strip()
    if not target_ticket_id:
        return None
    ticket = next((item for item in adapter.list_tickets() if item.id == target_ticket_id), None)
    if ticket is None:
        ticket = adapter.get_ticket(target_ticket_id)
    if ticket is None:
        return None

    events = adapter.get_ticket_events(ticket.id) or ticket.events
    linked_assets = ticket_assets_for_ticket(ticket.id)
    graph = ticket_graph_projection(ticket.id)
    contribution: dict[str, TicketEmployeeContribution] = {}

    if ticket.assigned_employee_id or ticket.assigned_role:
        record = _touch_ticket_contribution(
            contribution,
            employee_id=ticket.assigned_employee_id,
            role=ticket.assigned_role,
        )
        record.assigned = True
    if ticket.validation_employee_id or ticket.validation_role:
        record = _touch_ticket_contribution(
            contribution,
            employee_id=ticket.validation_employee_id,
            role=ticket.validation_role,
        )
        record.validator = True

    for report in ticket.reports:
        record = _touch_ticket_contribution(
            contribution,
            employee_id=report.reporter_employee_id,
            role=report.reporter_role,
        )
        record.reporter = True
        record.report_count += 1
        record.evidence_count += len(report.evidence)
        if _is_validation_pass_report_type(report.report_type):
            record.validation_report_count += 1
            record.validator = True
        if _is_validation_failure_report_type(report.report_type):
            record.blocked_report_count += 1

    for event in events:
        actor_id = event.actor.get("id", "").strip()
        if not actor_id or actor_id == "system":
            continue
        record = _touch_ticket_contribution(
            contribution,
            employee_id=actor_id,
            role=event.actor.get("role", ""),
        )
        record.event_actor = True
        record.event_count += 1

    for asset in linked_assets:
        source_employee_id = asset.source_employee_id.strip()
        derived_employee_id = _metadata_string(asset.metadata, "derived_from_employee_id")
        source_record = None
        if source_employee_id:
            source_record = _touch_ticket_contribution(contribution, employee_id=source_employee_id)
        elif derived_employee_id:
            source_record = _touch_ticket_contribution(contribution, employee_id=derived_employee_id)
        if source_record is not None:
            source_record.asset_source = True
            source_record.linked_asset_count += 1
            if asset.kind == "memory_candidate":
                source_record.candidate_count += 1
            if asset.kind == "memory":
                source_record.recalled_asset_count += 1
        if derived_employee_id and derived_employee_id != source_employee_id:
            derived_record = _touch_ticket_contribution(contribution, employee_id=derived_employee_id)
            derived_record.asset_source = True
            if asset.kind == "memory_candidate":
                derived_record.candidate_count += 1
        for assigned_employee_id in asset.assigned_employees:
            assigned_record = _touch_ticket_contribution(contribution, employee_id=assigned_employee_id)
            assigned_record.asset_assigned = True

    report_count = len(ticket.reports)
    evidence_count = sum(len(report.evidence) for report in ticket.reports)
    validation_report_count = len([report for report in ticket.reports if _is_validation_pass_report_type(report.report_type)])
    blocked_report_count = len([report for report in ticket.reports if _is_validation_failure_report_type(report.report_type)])
    memory_candidate_count = len([asset for asset in linked_assets if asset.kind == "memory_candidate"])
    recalled_asset_count = len([asset for asset in linked_assets if asset.kind == "memory"])
    graphiti_recalled_count = len([
        asset
        for asset in linked_assets
        if asset.kind == "memory" and bool(asset.metadata.get("graphiti_recalled"))
    ])
    evidence_requirements = _ticket_evidence_requirements_from_ticket(ticket)
    validation_requested = bool(ticket.validation_employee_id or ticket.validation_role) or any(
        event.type == "validation_requested" for event in events
    )
    waiting_for_validation = validation_requested and validation_report_count == 0 and ticket.status.lower() in {
        "reported",
        "review",
        "pending",
        "pending_validation",
        "validation",
        "in_review",
    }
    status_normalized = ticket.status.lower()
    quality_signals = {
        "has_assignee": bool(ticket.assigned_employee_id or ticket.assigned_role),
        "has_report": report_count > 0,
        "has_evidence": evidence_count > 0,
        "validation_requested": validation_requested,
        "has_validation_report": validation_report_count > 0,
        "has_blocker": blocked_report_count > 0 or status_normalized in {"blocked", "failed"},
        "candidate_produced": memory_candidate_count > 0,
        "used_recalled_asset": recalled_asset_count > 0,
        "graphiti_recall_recorded": graphiti_recalled_count > 0,
        "provider_ref_recorded": ticket.provider_ref is not None,
        "missing_evidence": report_count > 0 and evidence_count == 0,
        "evidence_requirements_satisfied": evidence_requirements.satisfied,
        "missing_required_evidence": len(evidence_requirements.missing_required),
        "waiting_report": report_count == 0 and not _terminal_status(ticket.status),
        "waiting_validation": waiting_for_validation,
        "blocked_or_failed": status_normalized in {"blocked", "failed"} or blocked_report_count > 0,
    }

    def contribution_sort_key(record: TicketEmployeeContribution) -> tuple[int, str]:
        score = (
            int(record.assigned) * 100
            + int(record.validator) * 80
            + record.report_count * 20
            + record.evidence_count * 10
            + record.candidate_count * 8
            + record.recalled_asset_count * 8
            + record.event_count
        )
        return (-score, record.employee_id)

    return TicketPerformance(
        ticket_id=ticket.id,
        status=ticket.status,
        contribution=sorted(contribution.values(), key=contribution_sort_key),
        quality_signals=quality_signals,
        source_counts={
            "events": len(events),
            "reports": report_count,
            "evidence": evidence_count,
            "assets": len(linked_assets),
            "memory_candidates": memory_candidate_count,
            "recalled_assets": recalled_asset_count,
            "graphiti_recalled_assets": graphiti_recalled_count,
            "graph_nodes": len(graph.nodes) if graph else 0,
            "graph_edges": len(graph.edges) if graph else 0,
        },
    )


def ticket_runtime_evidence(ticket_id: str) -> TicketRuntimeEvidence | None:
    adapter = ticket_adapter()
    target_ticket_id = ticket_id.strip()
    if not target_ticket_id:
        return None
    ticket = next((item for item in adapter.list_tickets() if item.id == target_ticket_id), None)
    if ticket is None:
        ticket = adapter.get_ticket(target_ticket_id)
    if ticket is None:
        return None

    events = adapter.get_ticket_events(ticket.id) or ticket.events
    linked_assets = ticket_assets_for_ticket(ticket.id)
    graph = ticket_graph_projection(ticket.id)
    performance = ticket_performance(ticket.id)
    evidence_requirements = _ticket_evidence_requirements_from_ticket(ticket)
    backend = ticket_backend_status()
    execution_records = _execution_artifact_records_for_ticket(ticket.id)

    loop_runs: list[Any] = []
    timeline: Any | None = None
    try:
        from .ticket_loop_service import list_ticket_loop_runs, ticket_loop_timeline

        loop_runs = list_ticket_loop_runs(ticket.id)
        timeline = ticket_loop_timeline(ticket.id)
    except (KeyError, ValueError):
        loop_runs = []
        timeline = None

    provider_ref = ticket.provider_ref
    provider_state = TicketRuntimeProviderEvidence(
        mode=backend.mode,
        status=backend.status,
        provider=backend.provider or (provider_ref.provider if provider_ref else ""),
        provider_ref_recorded=provider_ref is not None,
        provider_record_id=provider_ref.provider_record_id if provider_ref else "",
        provider_project_id=provider_ref.provider_project_id if provider_ref else "",
        provider_url=provider_ref.provider_url if provider_ref else "",
        external_url=ticket.external_url,
        synced_at=provider_ref.synced_at if provider_ref else "",
        detail=backend.detail,
        setup_required=list(backend.setup_required),
    )

    provider_blockers = []
    queue_reliability = None
    timeline_summary = getattr(timeline, "summary", None)
    if timeline_summary is not None:
        provider_blockers = [
            dict(item) if isinstance(item, dict) else item.model_dump(mode="json")
            for item in getattr(timeline_summary, "provider_blockers", [])
        ]
        queue_reliability = getattr(timeline_summary, "queue_reliability", None)

    timeline_session_keys = [
        str(getattr(item, "source_ref", "") or "").strip()
        for item in getattr(timeline, "items", []) or []
        if getattr(item, "kind", "") == "runtime_session" and str(getattr(item, "source_ref", "") or "").strip()
    ]

    def run_session_key(run: Any) -> str:
        for payload in (getattr(run, "response", {}), getattr(run, "request", {}), getattr(run, "control", {})):
            if not isinstance(payload, dict):
                continue
            direct = str(payload.get("session_key") or "").strip()
            if direct:
                return direct
            loop_state = payload.get("loop_state")
            if isinstance(loop_state, dict):
                loop_state_session = str(loop_state.get("session_key") or "").strip()
                if loop_state_session:
                    return loop_state_session
        return timeline_session_keys[0] if timeline_session_keys else ""

    latest_run = loop_runs[0] if loop_runs else None
    latest_loop_run = (
        TicketRuntimeLoopRunEvidence(
            run_id=getattr(latest_run, "run_id", ""),
            status=getattr(latest_run, "status", ""),
            stop_reason=getattr(latest_run, "stop_reason", ""),
            active=bool(getattr(latest_run, "active", False)),
            session_key=run_session_key(latest_run),
            step_count=int(getattr(latest_run, "step_count", 0) or 0),
            queued_at=getattr(latest_run, "queued_at", ""),
            started_at=getattr(latest_run, "started_at", ""),
            finished_at=getattr(latest_run, "finished_at", ""),
            updated_at=getattr(latest_run, "updated_at", ""),
            saved_path=getattr(latest_run, "saved_path", ""),
        )
        if latest_run is not None
        else None
    )

    report_count = len(ticket.reports)
    evidence_count = sum(len(report.evidence) for report in ticket.reports)
    memory_candidate_count = len([asset for asset in linked_assets if asset.kind == "memory_candidate"])
    approved_memory_count = len([asset for asset in linked_assets if asset.kind == "memory" and asset.status == "approved"])
    handoff_count = len([event for event in events if event.type.startswith("handoff")])
    approval_resume_count = len(getattr(timeline_summary, "approval_resume", []) or []) if timeline_summary is not None else 0
    retry_requirement_count = len(getattr(timeline_summary, "retry_requirements", []) or []) if timeline_summary is not None else 0
    provider_blocker_count = len(provider_blockers)
    queue_reliability_payload = queue_reliability.model_dump(mode="json") if queue_reliability is not None else None
    queue_reliability_status = str((queue_reliability_payload or {}).get("status") or "")

    governance_state = {
        "timeline_status": str(getattr(timeline_summary, "status", "") or ""),
        "next_action": str(getattr(timeline_summary, "next_action", "") or ""),
        "waiting_reason": str(getattr(timeline_summary, "waiting_reason", "") or ""),
        "can_run": bool(getattr(timeline_summary, "can_run", False)),
        "can_resume": bool(getattr(timeline_summary, "can_resume", False)),
        "can_retry": bool(getattr(timeline_summary, "can_retry", False)),
        "approval_resume_count": approval_resume_count,
        "retry_requirement_count": retry_requirement_count,
        "provider_blocker_count": provider_blocker_count,
        "queue_reliability_status": queue_reliability_status,
        "queue_reliability": queue_reliability_payload,
    }

    blockers: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    def append_issue(target: list[dict[str, Any]], reason: str, detail: str, *, scope: str = "", status: str = "", setup_required: list[str] | None = None) -> None:
        issue = {
            "reason": reason,
            "detail": detail,
        }
        if scope:
            issue["scope"] = scope
        if status:
            issue["status"] = status
        if setup_required:
            issue["setup_required"] = setup_required
        target.append(issue)

    normalized_status = ticket.status.lower()
    if normalized_status in {"blocked", "failed"}:
        append_issue(blockers, "ticket_blocked_or_failed", f"Ticket status is {ticket.status}.", scope="ticket", status=ticket.status)
    if backend.setup_required or backend.status not in {"ready", "active"}:
        append_issue(
            blockers,
            "ticket_provider_not_ready",
            backend.detail,
            scope="ticket_backend",
            status=backend.status,
            setup_required=list(backend.setup_required),
        )
    for provider_blocker in provider_blockers:
        blockers.append(provider_blocker)
    if latest_loop_run is not None and latest_loop_run.status.lower() in {"blocked", "failed"}:
        append_issue(
            blockers,
            "latest_loop_run_blocked",
            latest_loop_run.stop_reason or f"Latest loop run status is {latest_loop_run.status}.",
            scope="loop_run",
            status=latest_loop_run.status,
        )

    if report_count == 0:
        append_issue(gaps, "report_not_recorded", "No Ticket report is recorded yet.", scope="reports")
    if evidence_count == 0:
        append_issue(gaps, "evidence_not_recorded", "No report evidence is recorded yet.", scope="evidence")
    if evidence_requirements.missing_required:
        append_issue(
            gaps,
            "required_evidence_missing",
            "Ticket evidence requirements are not fully satisfied.",
            scope="evidence_requirements",
            setup_required=list(evidence_requirements.missing_required),
        )
    if graph is None or not graph.edges:
        append_issue(gaps, "graph_edges_not_projected", "Ticket Asset Graph has no projected edges yet.", scope="asset_graph")
    if not loop_runs:
        append_issue(gaps, "loop_run_not_recorded", "No governed Ticket loop run is recorded yet.", scope="loop_runs")
    if backend.mode == "plane" and provider_ref is None:
        append_issue(gaps, "provider_ref_missing", "Plane mode is active but this Ticket has no provider reference.", scope="provider_ref")
    if queue_reliability_status and queue_reliability_status not in {"healthy", "idle", "completed"}:
        append_issue(
            gaps,
            "queue_reliability_attention",
            str((queue_reliability_payload or {}).get("detail") or "Ticket loop queue reliability needs attention."),
            scope="loop_queue",
            status=queue_reliability_status,
        )

    links = {
        "ticket": f"tickets/overview/{ticket.id}",
        "asset_graph": f"tickets/overview/{ticket.id}",
    }
    if latest_loop_run is not None and latest_loop_run.session_key:
        links["runtime"] = f"runtime/{latest_loop_run.session_key}"
    if ticket.external_url:
        links["provider"] = ticket.external_url

    return TicketRuntimeEvidence(
        ticket_id=ticket.id,
        status=ticket.status,
        source_counts={
            "events": len(events),
            "reports": report_count,
            "evidence": evidence_count,
            "assets": len(linked_assets),
            "memory_candidates": memory_candidate_count,
            "approved_memories": approved_memory_count,
            "graph_nodes": len(graph.nodes) if graph else 0,
            "graph_edges": len(graph.edges) if graph else 0,
            "loop_runs": len(loop_runs),
            "runtime_artifact_runs": len(execution_records),
            "handoffs": handoff_count,
            "approval_resume": approval_resume_count,
            "retry_requirements": retry_requirement_count,
            "provider_blockers": provider_blocker_count,
            **(performance.source_counts if performance else {}),
        },
        provider_state=provider_state,
        governance_state=governance_state,
        latest_loop_run=latest_loop_run,
        blockers=blockers,
        gaps=gaps,
        links=links,
    )


def _self_bootstrap_next_learning_action(
    *,
    missing_required_evidence: int,
    blocked_or_failed: bool,
    memory_candidates: int,
    approved_memory_candidates: int,
    pending_memory_candidates: int,
    approved_memories_recalled: int,
    useful_memory_recalls: int,
    validation_passed: bool,
) -> str:
    if blocked_or_failed:
        return "Resolve blocker or record rework evidence before continuing the self-bootstrap batch."
    if missing_required_evidence:
        return "Attach validation evidence before marking this Ticket validated."
    if pending_memory_candidates:
        return "Review generated Memory candidates before relying on them in later Tickets."
    if approved_memories_recalled and not useful_memory_recalls:
        return "PV should mark whether recalled approved assets were useful for this Ticket."
    if validation_passed:
        return "Post Clara learning summary and use this Ticket as prior evidence for the next batch."
    return "Continue Ticket flow until report, evidence, validation, and Clara summary are available."


def self_bootstrap_learning_summary() -> SelfBootstrapLearningSummary:
    adapter = ticket_adapter()
    tickets = adapter.list_tickets()
    assets = ticket_asset_records()
    assets_by_ticket: dict[str, list[TicketAssetRecord]] = {}
    for asset in assets:
        if asset.source_ticket_id:
            assets_by_ticket.setdefault(asset.source_ticket_id, []).append(asset)

    ticket_records: list[SelfBootstrapTicketLearningRecord] = []
    validated_ticket_count = 0
    blocked_ticket_count = 0
    tickets_with_evidence = 0
    tickets_missing_required_evidence = 0
    report_count = 0
    evidence_count_total = 0

    for ticket in tickets:
        ticket_assets = assets_by_ticket.get(ticket.id, [])
        requirements = _ticket_evidence_requirements_from_ticket(ticket)
        evidence_count = sum(len(report.evidence) for report in ticket.reports)
        report_count += len(ticket.reports)
        evidence_count_total += evidence_count

        validation_passed = (
            ticket.status.lower() in {"validated", "completed", "done", "closed"}
            or any(_is_validation_pass_report_type(report.report_type) for report in ticket.reports)
        )
        blocked_or_failed = (
            ticket.status.lower() in {"blocked", "failed"}
            or any(_is_validation_failure_report_type(report.report_type) for report in ticket.reports)
        )
        memory_candidates = len([asset for asset in ticket_assets if asset.kind == "memory_candidate"])
        approved_memory_candidates = len([
            asset
            for asset in ticket_assets
            if asset.kind == "memory_candidate" and asset.status == "approved"
        ])
        pending_memory_candidates = len([
            asset
            for asset in ticket_assets
            if asset.kind == "memory_candidate" and asset.status in {"candidate", "pending", "proposed", "unreviewed"}
        ])
        approved_memories_recalled = len([asset for asset in ticket_assets if asset.kind == "memory" and asset.status == "approved"])
        graphiti_memories_recalled = len([
            asset
            for asset in ticket_assets
            if asset.kind == "memory" and bool(asset.metadata.get("graphiti_recalled"))
        ])
        useful_memory_recalls = len([
            asset
            for asset in ticket_assets
            if asset.kind == "memory" and _is_positive_memory_usefulness_status(asset.metadata.get("usefulness_status"))
        ])
        missing_required_evidence = len(requirements.missing_required)

        if validation_passed:
            validated_ticket_count += 1
        if blocked_or_failed:
            blocked_ticket_count += 1
        if evidence_count:
            tickets_with_evidence += 1
        if missing_required_evidence:
            tickets_missing_required_evidence += 1

        ticket_records.append(
            SelfBootstrapTicketLearningRecord(
                ticket_id=ticket.id,
                title=ticket.title,
                status=ticket.status,
                assigned_employee_id=ticket.assigned_employee_id,
                validation_employee_id=ticket.validation_employee_id,
                evidence_count=evidence_count,
                missing_required_evidence=missing_required_evidence,
                validation_passed=validation_passed,
                blocked_or_failed=blocked_or_failed,
                memory_candidates=memory_candidates,
                approved_memory_candidates=approved_memory_candidates,
                approved_memories_recalled=approved_memories_recalled,
                graphiti_memories_recalled=graphiti_memories_recalled,
                useful_memory_recalls=useful_memory_recalls,
                provider_ref_recorded=ticket.provider_ref is not None,
                next_learning_action=_self_bootstrap_next_learning_action(
                    missing_required_evidence=missing_required_evidence,
                    blocked_or_failed=blocked_or_failed,
                    memory_candidates=memory_candidates,
                    approved_memory_candidates=approved_memory_candidates,
                    pending_memory_candidates=pending_memory_candidates,
                    approved_memories_recalled=approved_memories_recalled,
                    useful_memory_recalls=useful_memory_recalls,
                    validation_passed=validation_passed,
                ),
            )
        )

    memory_candidate_assets = [asset for asset in assets if asset.kind == "memory_candidate"]
    memory_usage_assets = [asset for asset in assets if asset.kind == "memory"]
    approved_memory_candidates = len([asset for asset in memory_candidate_assets if asset.status == "approved"])
    approved_memories_recalled = len([asset for asset in memory_usage_assets if asset.status == "approved"])
    graphiti_memories_recalled = len([
        asset
        for asset in memory_usage_assets
        if bool(asset.metadata.get("graphiti_recalled"))
    ])
    useful_memory_recalls = len([
        asset
        for asset in memory_usage_assets
        if _is_positive_memory_usefulness_status(asset.metadata.get("usefulness_status"))
    ])
    stale_or_superseded_assets = len([asset for asset in assets if asset.status in {"stale", "superseded"}])
    summary = (
        f"{len(tickets)} self-bootstrap Tickets, {validated_ticket_count} validated, "
        f"{len(memory_candidate_assets)} candidates produced, {approved_memories_recalled} approved assets recalled."
    )
    return SelfBootstrapLearningSummary(
        ticket_count=len(tickets),
        validated_ticket_count=validated_ticket_count,
        blocked_ticket_count=blocked_ticket_count,
        tickets_with_evidence=tickets_with_evidence,
        tickets_missing_required_evidence=tickets_missing_required_evidence,
        memory_candidates_produced=len(memory_candidate_assets),
        approved_memory_candidates=approved_memory_candidates,
        approved_memories_recalled=approved_memories_recalled,
        graphiti_memories_recalled=graphiti_memories_recalled,
        useful_memory_recalls=useful_memory_recalls,
        stale_or_superseded_assets=stale_or_superseded_assets,
        summary=summary,
        learning_delta={
            "new_candidates": len(memory_candidate_assets),
            "approved_candidates": approved_memory_candidates,
            "reused_prior_assets": approved_memories_recalled,
            "graphiti_reused_assets": graphiti_memories_recalled,
            "useful_recalls": useful_memory_recalls,
            "needs_validation_evidence": tickets_missing_required_evidence,
            "blocked_or_failed_tickets": blocked_ticket_count,
            "stale_or_superseded_assets": stale_or_superseded_assets,
        },
        tickets=sorted(ticket_records, key=lambda item: item.ticket_id),
        source_counts={
            "tickets": len(tickets),
            "assets": len(assets),
            "reports": report_count,
            "evidence": evidence_count_total,
            "memory_candidates": len(memory_candidate_assets),
            "memory_recall_usages": len(memory_usage_assets),
        },
    )


def employee_analytics(employee_id: str) -> EmployeeAnalytics | None:
    normalized = employee_id.strip()
    if not normalized:
        return None
    adapter = ticket_adapter()
    tickets = adapter.list_tickets()
    assets = ticket_asset_records()
    known_employee_ids = set(_employee_ids_from_work_facts(tickets, assets))
    if normalized not in known_employee_ids and not _employee_role(normalized):
        return None
    return _employee_analytics_from_facts(normalized, tickets, assets)


def employee_analytics_summary() -> EmployeeAnalyticsSummary:
    adapter = ticket_adapter()
    tickets = adapter.list_tickets()
    assets = ticket_asset_records()
    employee_ids = _employee_ids_from_work_facts(tickets, assets)
    return EmployeeAnalyticsSummary(
        employees=[_employee_analytics_from_facts(employee_id, tickets, assets) for employee_id in employee_ids],
        source_counts={
            "tickets": len(tickets),
            "assets": len(assets),
            "employees": len(employee_ids),
        },
    )


def _memory_candidate_ticket_asset_records() -> list[TicketAssetRecord]:
    from .memory_service import list_memory_candidates

    records: list[TicketAssetRecord] = []
    for candidate in list_memory_candidates():
        provenance = candidate.provenance if isinstance(candidate.provenance, dict) else {}
        source_ticket_id = str(provenance.get("source_ticket_id") or "").strip()
        if not source_ticket_id and candidate.scope_kind == "ticket":
            source_ticket_id = candidate.scope_ref.strip()
        if not source_ticket_id:
            ticket_keys = _string_list(provenance.get("ticket_keys"))
            source_ticket_id = ticket_keys[0] if ticket_keys else ""
        if not source_ticket_id:
            continue
        source_employee_id = str(provenance.get("source_employee_id") or "").strip()
        source_report_id = str(provenance.get("source_report_id") or "").strip()
        evidence_id = str(provenance.get("evidence_id") or "").strip()
        records.append(
            TicketAssetRecord(
                id=f"{candidate.id}:candidate",
                kind="memory_candidate",
                title=f"Memory candidate from {source_ticket_id}",
                status=candidate.status,
                source_ticket_id=source_ticket_id,
                source_employee_id=source_employee_id or (candidate.employee_ids[0] if candidate.employee_ids else ""),
                assigned_employees=candidate.employee_ids,
                scopes=sorted({f"{candidate.scope_kind}:{candidate.scope_ref}", *candidate.tags}),
                created_at=candidate.created_at,
                updated_at=candidate.updated_at,
                metadata={
                    "asset_id": candidate.id,
                    "memory_id": candidate.id,
                    "memory_type": candidate.memory_type,
                    "content": candidate.content,
                    "confidence": candidate.confidence,
                    "source_kind": candidate.source_kind,
                    "source_ref": candidate.source_ref,
                    "source_run_id": str(provenance.get("source_run_id") or provenance.get("run_id") or "").strip(),
                    "source_trace_path": str(provenance.get("source_trace_path") or provenance.get("trace") or "").strip(),
                    "source_report_id": source_report_id,
                    "evidence_id": evidence_id,
                    "why_should_be_remembered": str(provenance.get("why_should_be_remembered") or "").strip(),
                    "future_recall_query_hints": _string_list(provenance.get("future_recall_query_hints")),
                    "recalled_memory_refs": provenance.get("recalled_memory_refs") if isinstance(provenance.get("recalled_memory_refs"), list) else [],
                    "graphiti_episode_id": candidate.graphiti_episode_id or "",
                    "graphiti_status": candidate.graphiti_status,
                },
            )
        )
    return records


def _memory_usage_ticket_asset_records() -> list[TicketAssetRecord]:
    from .memory_service import list_approved_memories

    records: list[TicketAssetRecord] = []
    for memory in list_approved_memories():
        provenance = memory.provenance if isinstance(memory.provenance, dict) else {}
        usage_history = provenance.get("usage_history")
        if not isinstance(usage_history, list):
            continue
        memory_source_ticket_id = str(provenance.get("source_ticket_id") or "").strip()
        memory_source_employee_id = str(provenance.get("source_employee_id") or "").strip()
        source_report_id = str(provenance.get("source_report_id") or "").strip()
        evidence_id = str(provenance.get("evidence_id") or "").strip()
        provider_refs = provenance.get("provider_refs") if isinstance(provenance.get("provider_refs"), list) else []
        scopes = sorted({f"{memory.scope_kind}:{memory.scope_ref}", *memory.tags})
        for index, usage in enumerate(usage_history):
            if not isinstance(usage, dict):
                continue
            source_ticket_ids = _string_list(usage.get("source_ticket_ids"))
            if not source_ticket_ids:
                continue
            usage_id = str(usage.get("usage_id") or f"usage-{index}").strip()
            source_employee_id = str(usage.get("source_employee_id") or memory_source_employee_id).strip()
            recalled_at = str(usage.get("reviewed_at") or usage.get("at") or memory.updated_at or memory.created_at).strip()
            graphiti_episode_id = str(usage.get("graphiti_episode_id") or memory.graphiti_episode_id or "").strip()
            for ticket_id in source_ticket_ids:
                records.append(
                    TicketAssetRecord(
                        id=f"{memory.id}:{usage_id}:{ticket_id}",
                        kind="memory",
                        title=f"Approved Memory reused by {ticket_id}",
                        status=memory.status,
                        source_ticket_id=ticket_id,
                        source_employee_id=source_employee_id,
                        assigned_employees=memory.employee_ids,
                        scopes=scopes,
                        created_at=str(usage.get("at") or memory.created_at).strip(),
                        updated_at=recalled_at,
                        metadata={
                            "asset_id": memory.id,
                            "memory_id": memory.id,
                            "memory_type": memory.memory_type,
                            "content": memory.content,
                            "scope_kind": memory.scope_kind,
                            "scope_ref": memory.scope_ref,
                            "tags": memory.tags,
                            "usage_id": usage_id,
                            "query": str(usage.get("query") or "").strip(),
                            "source_run_id": str(usage.get("source_run_id") or "").strip(),
                            "source_trace_path": str(usage.get("source_trace_path") or "").strip(),
                            "graphiti_recalled": bool(usage.get("graphiti_recalled")),
                            "graphiti_episode_id": graphiti_episode_id,
                            "graphiti_result_id": str(usage.get("graphiti_result_id") or "").strip(),
                            "usefulness_status": str(usage.get("usefulness_status") or "unreviewed").strip(),
                            "usefulness_reason": str(usage.get("usefulness_reason") or "").strip(),
                            "reviewer_employee_id": str(usage.get("reviewer_employee_id") or "").strip(),
                            "reviewed_at": str(usage.get("reviewed_at") or "").strip(),
                            "derived_from_ticket_id": memory_source_ticket_id,
                            "derived_from_employee_id": memory_source_employee_id,
                            "source_report_id": source_report_id,
                            "evidence_id": evidence_id,
                            "provider_refs": provider_refs,
                        },
                    )
                )
    return records


def ticket_asset_records() -> list[TicketAssetRecord]:
    records = [
        *ticket_adapter().ticket_asset_records(),
        *_memory_candidate_ticket_asset_records(),
        *_memory_usage_ticket_asset_records(),
    ]
    return sorted(records, key=lambda item: item.updated_at or item.created_at, reverse=True)
