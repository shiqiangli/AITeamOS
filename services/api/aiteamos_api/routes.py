from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
import hashlib
import hmac
import inspect
import json
import os
from pathlib import Path
import secrets
import time
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aiteamos_schema import (
    AutomationCreateInput,
    AutomationRunActionInput,
    CostAlertRouteInput,
    KnowledgeHealthRemediationInput,
    ManagerInputBundle,
    MemoryEntryCreateInput,
    MemoryStoreCreateInput,
    ProductUserArchiveInput,
    ProductUserCreateInput,
    ProductUserUpdateInput,
    RunAssistanceBundleRecord,
    RunAssistancePackageRecord,
    RunAssistedIngestInput,
    RunCloseoutInput,
    RunReviewGateRecord,
    RunReviewInput,
    RunReviewTargetCheckRecord,
    RunProviderSourceIntegrationExecuteInput,
    RunProviderSourceIntegrationInput,
    RunSourceIntegrationInput,
    RunSourceIntegrationRemediationInput,
    MemberGrowthRecordInput,
    MemberDeleteRequestInput,
    SessionLoginInput,
    SessionLoginRecord,
    SessionProjectionRecord,
    SkillArchiveInput,
    SkillAttachMemberInput,
    SkillCreateInput,
    SkillUpdateInput,
    WorkspaceCatalogRecord,
)
from aiteamos_workspace import (
    archive_member,
    archive_product_user,
    archive_skill,
    ask_for_help,
    attach_skill_to_member,
    close_run_after_review,
    collaboration_overview,
    create_assignment,
    create_member,
    create_product_user,
    create_review,
    create_skill,
    create_task_plan_retrospective,
    create_team_retrospective,
    cost_alert_candidates,
    evaluate_model_execution_readiness,
    evaluate_model_policy,
    evaluate_model_profile_readiness,
    evaluate_run_closeout_gate,
    evaluate_run_review_gate,
    evaluate_run_source_integration_gate,
    evaluate_worker_authorization,
    evaluate_worker_readiness,
    execute_run_provider_source_integration,
    execute_run_with_model,
    execute_worker_run,
    ingest_run_outputs,
    integrate_run_source_after_closeout,
    load_workspace,
    manifest_to_record,
    manager_evaluation_signal,
    member_growth_projection,
    new_trace_context,
    rebuild_workspace_indexes,
    record_member_growth,
    refresh_run_checks,
    remediate_memory_health_issue,
    render_prometheus_metrics,
    request_member_delete,
    request_review,
    request_run_provider_source_integration,
    request_run_source_integration_remediation,
    resolve_member_message,
    resolve_workspace_root,
    retrospective_suggestions,
    route_cost_alerts,
    run_trace_context,
    skill_projection_records,
    skill_record,
    skill_records,
    summarize_model_costs,
    task_execution_queue,
    task_plan_execution_view,
    task_plan_execution_view_records,
    trace_response_headers,
    update_assignment,
    update_member,
    update_product_user,
    update_skill,
    workspace_action_board,
    workspace_health_v2,
)
from aiteamos_workspace.knowledge_health import evaluate_knowledge_health
from .automation import (
    admit_external_automation_event,
    approve_automation_run,
    automation_approval_records,
    automation_provider_delivery_records,
    automation_run_records,
    automation_scheduler_lease_records,
    automation_trigger_event_records,
    cleanup_automation_provider_deliveries,
    create_automation,
    dry_run_automation,
    emit_scheduler_tick,
    execute_automation_run,
    ingest_automation_event,
    recover_scheduler_lease,
    reject_automation_run,
    request_automation_run_permission,
    retry_provider_delivery,
    scan_cron_scheduler,
    trigger_automation,
)
from .connector import (
    accept_connector_remediation_task_plan,
    check_connector_health,
    cleanup_connector_health_checks,
    connector_failure_escalation_candidates,
    connector_failure_reminder_candidates,
    connector_health_records,
    connector_operations_overview,
    connector_remediation_materialized_task_records,
    connector_remediation_run_records,
    connector_remediation_suggestions,
    connector_remediation_task_plan_records,
    launch_connector_remediation_task_run,
    request_connector_remediation_run_permission,
    resolve_connector_failure_escalation,
    route_connector_failure_escalations,
    route_connector_failure_reminders,
    submit_connector_remediation_task_plan,
)
from .context import (
    build_context_capsule,
    build_run_assistance_bundle,
    build_run_assistance_bundle_archive,
    build_run_assistance_package,
    build_run_launch_plan,
    get_context_capsule_for_tool,
)
from .git_activity import (
    admit_local_git_activity_import,
    admit_provider_git_activity_import,
    explain_git_activity_import_policy,
    git_activity_correlation_preview,
    git_activity_correlation_promotion_candidates,
    git_activity_retention_candidates,
    promote_git_activity_correlation_review,
    promote_git_activity_import_receipt,
    review_git_activity_correlation,
    sweep_git_activity_retention,
    update_git_activity_evidence_lifecycle,
)
from .manager import manager_input_bundle
from .memory import (
    approve_memory_proposal,
    archive_memory_binding,
    create_memory_binding,
    create_memory_entry,
    create_memory_grant,
    create_memory_store,
    grant_memory_for_tool,
    mark_memory_entry_stale,
    memory_proposal_review_queue,
    propose_memory_for_tool,
    reject_memory_proposal,
    repair_memory_proposal,
    search_memory_for_tool,
    share_memory,
    share_memory_for_tool,
    update_memory_entry,
    update_memory_proposal,
    verify_memory_entry,
)
from .permission import (
    approve_permission_request,
    create_permission_request,
    explain_effective_permissions,
    expire_permission_grants,
    permission_governance_overview,
    permission_grant_records,
    permission_policy_records,
    permission_request_records,
    reject_permission_request,
    request_run_worker_permission,
    revoke_permission_grant,
)


REDACTED_VALUE = "[redacted]"
SENSITIVE_MEMORY_LEVELS = {"confidential", "secret"}
PRIVATE_MEMORY_VISIBILITIES = {"private"}
REPO_ROOT = Path(__file__).resolve().parents[3]


def _workspace_health_summary(issues: list[dict[str, str]]) -> dict[str, int]:
    summary = {"errors": 0, "warnings": 0, "info": 0}
    for issue in issues:
        severity = issue.get("severity", "info")
        key = "errors" if severity == "error" else "warnings" if severity == "warning" else "info"
        summary[key] += 1
    return summary


def _workspace_health_response(current: Any) -> dict[str, Any]:
    return workspace_health_v2(current).model_dump(mode="json")


def _relative_repo_path(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return None


def _workspace_catalog_option(
    current: Any,
    *,
    option_id: str,
    option_type: str,
    workspace_ref: str,
    served_by_current_api: bool,
    safe_for_public_demo: bool,
    relative_path: str | None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    project_title = current.project.metadata.title or current.project.object_id
    launch_command = f"./aiteamos serve --workspace {relative_path}" if safe_for_public_demo and relative_path else None
    validate_command = f"./aiteamos workspace validate --workspace {relative_path}" if safe_for_public_demo and relative_path else None
    dashboard_command = "cd apps/dashboard && npm run dev" if safe_for_public_demo else None
    counts = current.to_summary().get("counts", {})
    return {
        "id": option_id,
        "label": project_title,
        "optionType": option_type,
        "workspaceRef": workspace_ref,
        "workspaceName": current.workspace.object_id,
        "workspaceMode": current.workspace.spec.mode,
        "protocolVersion": current.workspace.spec.protocolVersion,
        "project": current.project.object_id,
        "projectTitle": project_title,
        "relativePath": relative_path,
        "servedByCurrentApi": served_by_current_api,
        "safeForPublicDemo": safe_for_public_demo,
        "launchCommand": launch_command,
        "validateCommand": validate_command,
        "dashboardCommand": dashboard_command,
        "counts": {key: int(value) for key, value in counts.items() if isinstance(value, int)},
        "healthSummary": _workspace_health_summary(current.health),
        "warnings": warnings or [],
    }


def _workspace_catalog(current: Any, current_workspace_path: Path) -> dict[str, Any]:
    current_root = current_workspace_path.resolve()
    options: list[dict[str, Any]] = [
        _workspace_catalog_option(
            current,
            option_id="current",
            option_type="current",
            workspace_ref="current-api-workspace",
            served_by_current_api=True,
            safe_for_public_demo=False,
            relative_path=None,
            warnings=["Current API workspace details are intentionally path-redacted."],
        )
    ]
    examples_root = REPO_ROOT / "examples"
    for candidate in sorted(examples_root.glob("*/.aiteamos")):
        try:
            example = load_workspace(candidate)
        except Exception as exc:  # pragma: no cover - only exercised by broken local demo folders
            options.append(
                {
                    "id": f"example:{candidate.parent.name}",
                    "label": candidate.parent.name,
                    "optionType": "example",
                    "workspaceRef": f"examples/{candidate.parent.name}",
                    "relativePath": _relative_repo_path(candidate),
                    "servedByCurrentApi": candidate.resolve() == current_root,
                    "safeForPublicDemo": True,
                    "counts": {},
                    "healthSummary": {"errors": 1, "warnings": 0, "info": 0},
                    "warnings": [f"Example workspace failed to load: {exc}"],
                }
            )
            continue
        if _is_protocol_fixture_workspace(example):
            continue
        relative_path = _relative_repo_path(candidate)
        warnings: list[str] = []
        if not example.workspace.spec.governance.get("publicDemoDataOnly") and not example.project.spec.publicDataPolicy.get("publicDemoWorkspace"):
            warnings.append("Example workspace is not marked as public demo data.")
        options.append(
            _workspace_catalog_option(
                example,
                option_id=f"example:{candidate.parent.name}",
                option_type="example",
                workspace_ref=f"examples/{candidate.parent.name}",
                served_by_current_api=candidate.resolve() == current_root,
                safe_for_public_demo=True,
                relative_path=relative_path,
                warnings=warnings,
            )
        )
    record = WorkspaceCatalogRecord(
        spec={
            "currentWorkspace": "current",
            "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "options": options,
        }
    )
    return record.model_dump(mode="json")


def _is_protocol_fixture_workspace(index: Any) -> bool:
    governance = getattr(index.workspace.spec, "governance", {}) or {}
    public_policy = getattr(index.project.spec, "publicDataPolicy", {}) or {}
    visibility = str(governance.get("catalogVisibility") or public_policy.get("catalogVisibility") or "").lower()
    return bool(
        governance.get("protocolTestFixtureOnly")
        or public_policy.get("protocolTestFixtureOnly")
        or visibility in {"fixture-only", "protocol-fixture", "test-fixture"}
    )


def governed_memory_store_records(current: Any, *, viewer_member: str | None = None) -> list[dict[str, Any]]:
    return [
        _governed_memory_store_record(current, store, viewer_member=viewer_member)
        for store in current.memory_stores.values()
    ]


def governed_memory_entry_records(current: Any, *, viewer_member: str | None = None) -> list[dict[str, Any]]:
    return [
        _governed_memory_entry_record(current, entry_id, entry, viewer_member=viewer_member)
        for entry_id, entry in current.memory_entries.items()
    ]


def governed_memory_binding_records(current: Any, *, viewer_member: str | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for binding in current.memory_bindings.values():
        should_redact = False
        if binding.spec.entry:
            entry = current.memory_entries.get(binding.spec.entry)
            should_redact = bool(entry and _memory_entry_requires_redaction(current, binding.spec.entry, entry, viewer_member=viewer_member))
        elif binding.spec.store:
            store = current.memory_stores.get(binding.spec.store)
            should_redact = bool(store and _memory_store_requires_redaction(current, store, viewer_member=viewer_member))
        record = manifest_to_record(binding)
        if should_redact:
            spec = record["spec"]
            spec["entry"] = REDACTED_VALUE if spec.get("entry") else None
            spec["collectionPath"] = REDACTED_VALUE if spec.get("collectionPath") else None
            spec["targetId"] = REDACTED_VALUE
            spec["access"] = []
            spec["reason"] = REDACTED_VALUE if spec.get("reason") else None
            spec["redacted"] = True
            spec["redactionReason"] = "memory target is private, sensitive, or not readable by viewer"
        records.append(record)
    return records


def governed_memory_grant_records(current: Any, *, viewer_member: str | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for grant in current.memory_grants.values():
        viewer_is_party = bool(viewer_member and viewer_member in {grant.spec.granteeMember, grant.spec.grantorMember})
        linked_entries_readable = all(
            _viewer_can_read_memory_entry(current, entry_id, current.memory_entries[entry_id], viewer_member=viewer_member)
            for entry_id in grant.spec.entries
            if entry_id in current.memory_entries
        )
        linked_stores_readable = all(
            _viewer_can_read_memory_store(current, current.memory_stores[store_id], viewer_member=viewer_member)
            for store_id in grant.spec.stores
            if store_id in current.memory_stores
        )
        should_redact = not (viewer_is_party or (linked_entries_readable and linked_stores_readable and viewer_member))
        record = manifest_to_record(grant)
        if should_redact:
            spec = record["spec"]
            spec["granteeMember"] = REDACTED_VALUE
            spec["grantorMember"] = REDACTED_VALUE if spec.get("grantorMember") else None
            spec["task"] = REDACTED_VALUE if spec.get("task") else None
            spec["run"] = REDACTED_VALUE if spec.get("run") else None
            spec["stores"] = []
            spec["entries"] = []
            spec["access"] = []
            spec["reason"] = REDACTED_VALUE if spec.get("reason") else None
            spec["redacted"] = True
            spec["redactionReason"] = "memory grant is not readable by viewer"
        records.append(record)
    return records


def governed_memory_proposal_records(current: Any, *, viewer_member: str | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for proposal in current.memory_proposals.values():
        record = manifest_to_record(proposal)
        if not _viewer_can_read_memory_proposal(current, proposal, viewer_member=viewer_member):
            spec = record["spec"]
            spec["member"] = REDACTED_VALUE if spec.get("member") else None
            spec["assignment"] = REDACTED_VALUE if spec.get("assignment") else None
            spec["store"] = REDACTED_VALUE if spec.get("store") else None
            spec["entryPath"] = REDACTED_VALUE if spec.get("entryPath") else None
            spec["approvedMemory"] = REDACTED_VALUE if spec.get("approvedMemory") else None
            spec["title"] = REDACTED_VALUE
            spec["content"] = REDACTED_VALUE
            spec["evidence"] = []
            spec["reviewGuidance"] = REDACTED_VALUE if spec.get("reviewGuidance") else None
            spec["reviewedByMember"] = REDACTED_VALUE if spec.get("reviewedByMember") else None
            spec["reviewReason"] = REDACTED_VALUE if spec.get("reviewReason") else None
            spec["decisionAudit"] = []
            spec["redacted"] = True
            spec["redactionReason"] = "memory proposal is not readable by viewer"
        records.append(record)
    return records


def _governed_memory_store_record(current: Any, store: Any, *, viewer_member: str | None = None) -> dict[str, Any]:
    record = manifest_to_record(store)
    if _memory_store_requires_redaction(current, store, viewer_member=viewer_member):
        spec = record["spec"]
        spec["description"] = REDACTED_VALUE if spec.get("description") else None
        spec["acl"] = {}
        spec["retention"] = {}
        spec["redacted"] = True
        spec["redactionReason"] = "memory store is private or not readable by viewer"
    return record


def _governed_memory_entry_record(current: Any, entry_id: str, entry: Any, *, viewer_member: str | None = None) -> dict[str, Any]:
    record = manifest_to_record(entry)
    if _memory_entry_requires_redaction(current, entry_id, entry, viewer_member=viewer_member):
        spec = record["spec"]
        spec["path"] = REDACTED_VALUE
        spec["title"] = REDACTED_VALUE
        spec["content"] = REDACTED_VALUE
        spec["source"] = REDACTED_VALUE if spec.get("source") else None
        spec["evidence"] = []
        spec["acl"] = {}
        spec["tags"] = []
        spec["relatedProjects"] = []
        spec["relatedMembers"] = []
        spec["relatedAssignments"] = []
        spec["lineage"] = {}
        spec["embedding"] = {}
        spec["redacted"] = True
        spec["redactionReason"] = "memory entry is private, sensitive, redacted, or not readable by viewer"
    return record


def _memory_store_requires_redaction(current: Any, store: Any, *, viewer_member: str | None = None) -> bool:
    return not _viewer_can_read_memory_store(current, store, viewer_member=viewer_member) and store.spec.visibility in PRIVATE_MEMORY_VISIBILITIES


def _memory_entry_requires_redaction(current: Any, entry_id: str, entry: Any, *, viewer_member: str | None = None) -> bool:
    if entry.spec.lifecycle == "redacted":
        return True
    if _viewer_can_read_memory_entry(current, entry_id, entry, viewer_member=viewer_member):
        return False
    return entry.spec.visibility in PRIVATE_MEMORY_VISIBILITIES or entry.spec.sensitivity in SENSITIVE_MEMORY_LEVELS


def _viewer_can_read_memory_store(current: Any, store: Any, *, viewer_member: str | None = None) -> bool:
    if store is None:
        return False
    visibility = store.spec.visibility
    if visibility == "public":
        return True
    principals = _memory_viewer_principals(current, viewer_member)
    if store.spec.acl.read:
        return bool(principals.intersection(store.spec.acl.read))
    if not viewer_member:
        return False
    if visibility == "organization":
        return True
    if visibility == "project" and store.spec.ownerProject and f"project:{store.spec.ownerProject}" in principals:
        return True
    if visibility == "private" and store.spec.ownerMember == viewer_member:
        return True
    return False


def _viewer_can_read_memory_entry(current: Any, entry_id: str, entry: Any, *, viewer_member: str | None = None) -> bool:
    if entry.spec.lifecycle in {"redacted", "archived"}:
        return False
    if entry.spec.visibility == "public" and entry.spec.sensitivity != "secret":
        return True
    principals = _memory_viewer_principals(current, viewer_member)
    if entry.spec.acl.read:
        return bool(principals.intersection(entry.spec.acl.read))
    if entry.spec.sensitivity == "secret":
        return False
    if not viewer_member:
        return False
    if entry.spec.visibility == "organization":
        return True
    if viewer_member in set(entry.spec.relatedMembers):
        return True
    if _viewer_can_read_memory_store(current, current.memory_stores.get(entry.spec.store), viewer_member=viewer_member):
        return True
    if any(f"project:{project}" in principals for project in _entry_project_ids(current, entry_id, entry)):
        return entry.spec.visibility == "project"
    return False


def _viewer_can_read_memory_proposal(current: Any, proposal: Any, *, viewer_member: str | None = None) -> bool:
    if proposal.spec.store:
        store = current.memory_stores.get(proposal.spec.store)
        if store and not _viewer_can_read_memory_store(current, store, viewer_member=viewer_member):
            return False
    if not viewer_member:
        return True
    if proposal.spec.member == viewer_member:
        return True
    if proposal.spec.assignment:
        assignment = current.assignments.get(proposal.spec.assignment)
        if assignment and assignment.spec.member == viewer_member:
            return True
    return f"project:{proposal.spec.project}" in _memory_viewer_principals(current, viewer_member)


def _entry_project_ids(current: Any, entry_id: str, entry: Any) -> set[str]:
    project_ids = set(entry.spec.relatedProjects)
    store = current.memory_stores.get(entry.spec.store)
    if store and store.spec.ownerProject:
        project_ids.add(store.spec.ownerProject)
    for binding in current.memory_bindings.values():
        if binding.spec.entry == entry_id and binding.spec.targetType == "project":
            project_ids.add(binding.spec.targetId)
    return project_ids


def _memory_viewer_principals(current: Any, viewer_member: str | None) -> set[str]:
    if not viewer_member or viewer_member not in current.members:
        return {"public"}
    principals = {"public", "organization", f"member:{viewer_member}"}
    for assignment in current.assignments.values():
        if assignment.spec.member == viewer_member:
            principals.add(f"assignment:{assignment.object_id}")
            principals.add(f"project:{assignment.spec.project}")
    return principals
from aiteamos_workspace.queries import (
    get_task_for_tool,
    search_docs_for_tool,
)
from aiteamos_workspace.tool_mutations import (
    ask_member_for_tool,
    create_patch_for_tool,
    record_event_for_tool,
    record_handoff_for_tool,
    record_journal_for_tool,
    record_member_message_for_tool,
    request_review_for_tool,
)

from .auth import (
    api_auth_configured,
    api_token_from_authorization,
    authorize_mcp_tool,
    authorize_request,
    ProductUserTokenBinding,
    product_user_from_authorization,
    viewer_member_from_authorization,
)


SESSION_COOKIE_NAME = "aiteamos_session"
SESSION_COOKIE_MAX_AGE_SECONDS = 8 * 60 * 60
SESSION_COOKIE_VERSION = 1
SESSION_CSRF_HEADER = "x-aiteamos-csrf"
SESSION_COOKIE_SECURE_ENV = "AITEAMOS_SESSION_COOKIE_SECURE"
SESSION_COOKIE_SAMESITE_ENV = "AITEAMOS_SESSION_COOKIE_SAMESITE"
SESSION_COOKIE_DEPLOYMENT_ENV = "AITEAMOS_ENV"
SESSION_COOKIE_PUBLIC_URL_ENV = "AITEAMOS_PUBLIC_URL"


def session_cookie_policy() -> dict[str, bool | str]:
    same_site = _session_cookie_samesite()
    production_like = _session_cookie_production_like()
    secure = _session_cookie_secure_override(default=production_like)
    if same_site == "none":
        secure = True
    return {"secure": secure, "samesite": same_site}


def _session_cookie_samesite() -> str:
    value = os.environ.get(SESSION_COOKIE_SAMESITE_ENV, "").strip().lower()
    return value if value in {"lax", "strict", "none"} else "lax"


def _session_cookie_production_like() -> bool:
    environment = os.environ.get(SESSION_COOKIE_DEPLOYMENT_ENV, "").strip().lower()
    if environment in {"prod", "production"}:
        return True
    public_url = os.environ.get(SESSION_COOKIE_PUBLIC_URL_ENV, "").strip().lower()
    return public_url.startswith("https://")


def _session_cookie_secure_override(*, default: bool) -> bool:
    value = os.environ.get(SESSION_COOKIE_SECURE_ENV, "").strip().lower()
    if value in {"1", "true", "yes", "on", "secure"}:
        return True
    if value in {"0", "false", "no", "off", "insecure"}:
        return default if _session_cookie_production_like() else False
    return default


class SearchDocsToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = ""
    project: str | None = None
    member: str | None = None
    assignment: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class SearchMemoryToolInput(SearchDocsToolInput):
    store: str | None = None
    viewerMember: str | None = None
    viewer_member: str | None = None


class GetMemberToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memberId: str | None = None
    member_id: str | None = None


class GetProjectToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projectId: str | None = None
    project_id: str | None = None


class ListProjectMembersToolInput(GetProjectToolInput):
    pass


class ListMemberProjectsToolInput(GetMemberToolInput):
    pass


class GetMemberMemoryToolInput(GetMemberToolInput):
    query: str = ""
    project: str | None = None
    assignment: str | None = None
    store: str | None = None
    viewerMember: str | None = None
    viewer_member: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class GetProjectMemoryToolInput(GetProjectToolInput):
    query: str = ""
    member: str | None = None
    assignment: str | None = None
    store: str | None = None
    viewerMember: str | None = None
    viewer_member: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class ListAssignmentsToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member: str | None = None
    project: str | None = None


class ExplainPermissionsToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member: str | None = None
    project: str | None = None
    assignment: str | None = None
    action: dict[str, Any] | None = None
    nonInteractive: bool | None = None
    non_interactive: bool | None = None


class PermissionExplainInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member: str | None = None
    project: str | None = None
    assignment: str | None = None
    action: dict[str, Any] | None = None
    nonInteractive: bool | None = None
    non_interactive: bool | None = None


class PermissionRequestCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member: str
    action: dict[str, Any]
    project: str | None = None
    assignment: str | None = None
    task: str | None = None
    run: str | None = None
    automation: str | None = None
    automationRun: str | None = None
    automation_run: str | None = None
    requesterMember: str | None = None
    requester_member: str | None = None
    reason: str | None = None
    expiresAt: str | None = None
    expires_at: str | None = None
    source: str | None = None
    name: str | None = None


class PermissionRequestReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewerMember: str | None = None
    reviewer_member: str | None = None
    reason: str | None = None
    expiresAt: str | None = None
    expires_at: str | None = None


class PermissionGrantRevokeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    reason: str | None = None


class GetTaskToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    taskId: str | None = None
    task_id: str | None = None


class GetContextCapsuleToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runId: str | None = None
    run_id: str | None = None


class RecordJournalToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runId: str | None = None
    run_id: str | None = None
    actorMember: str | None = None
    actor_member: str | None = None
    entry: str


class RecordEventToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runId: str | None = None
    run_id: str | None = None
    actorMember: str | None = None
    actor_member: str | None = None
    event: dict[str, Any] = Field(default_factory=dict)


class ProposeMemoryToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runId: str | None = None
    run_id: str | None = None
    actorMember: str | None = None
    actor_member: str | None = None
    title: str | None = None
    content: str
    kind: str = "procedural"
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] | None = None
    reviewGuidance: str | None = None
    review_guidance: str | None = None


class HandoffToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    taskId: str | None = None
    task_id: str | None = None
    fromMember: str | None = None
    from_member: str | None = None
    toMember: str | None = None
    to_member: str | None = None
    problem: str
    runId: str | None = None
    run_id: str | None = None
    knownContext: list[str] | None = None
    known_context: list[str] | None = None
    recommendedNextStep: str | None = None
    recommended_next_step: str | None = None
    sharedMemoryPack: list[str] | None = None
    shared_memory_pack: list[str] | None = None
    ownership: str = "transfer"


class RecordMemberMessageToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fromMember: str | None = None
    from_member: str | None = None
    body: str
    toMembers: list[str] | None = None
    to_members: list[str] | None = None
    channel: str | None = None
    messageType: str | None = None
    message_type: str | None = None
    project: str | None = None
    task: str | None = None
    runId: str | None = None
    run_id: str | None = None
    attachments: list[str] | None = None


class CreatePatchToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runId: str | None = None
    run_id: str | None = None
    actorMember: str | None = None
    actor_member: str | None = None
    diffPatch: str | None = None
    diff_patch: str | None = None


class GrantMemoryToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member: str | None = None
    granteeMember: str | None = None
    grantee_member: str | None = None
    grantorMember: str | None = None
    grantor_member: str | None = None
    task: str | None = None
    runId: str | None = None
    run_id: str | None = None
    stores: list[str] | None = None
    entries: list[str] | None = None
    reason: str | None = None
    expiresAt: str | None = None
    expires_at: str | None = None


class ShareMemoryToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fromMember: str | None = None
    from_member: str | None = None
    toMember: str | None = None
    to_member: str | None = None
    stores: list[str] | None = None
    entries: list[str] | None = None
    task: str | None = None
    runId: str | None = None
    run_id: str | None = None
    reason: str | None = None
    expiresAt: str | None = None
    expires_at: str | None = None


class AskMemberToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fromMember: str | None = None
    from_member: str | None = None
    toMember: str | None = None
    to_member: str | None = None
    question: str
    project: str | None = None
    task: str | None = None
    runId: str | None = None
    run_id: str | None = None
    priority: str = "normal"
    requestedResponseBy: str | None = None
    requested_response_by: str | None = None
    attachments: list[str] | None = None


class ReviewRequestToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fromMember: str | None = None
    from_member: str | None = None
    toMember: str | None = None
    to_member: str | None = None
    body: str
    reviewKind: str | None = None
    review_kind: str | None = None
    project: str | None = None
    task: str | None = None
    runId: str | None = None
    run_id: str | None = None
    priority: str = "normal"
    requestedResponseBy: str | None = None
    requested_response_by: str | None = None
    attachments: list[str] | None = None


class AskForHelpInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fromMember: str | None = None
    from_member: str | None = None
    toMembers: list[str] | None = None
    to_members: list[str] | None = None
    toMember: str | None = None
    to_member: str | None = None
    question: str | None = None
    body: str | None = None
    project: str | None = None
    task: str | None = None
    runId: str | None = None
    run_id: str | None = None
    priority: str = "normal"
    requestedResponseBy: str | None = None
    requested_response_by: str | None = None
    attachments: list[str] | None = None


class ReviewRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fromMember: str | None = None
    from_member: str | None = None
    toMembers: list[str] | None = None
    to_members: list[str] | None = None
    toMember: str | None = None
    to_member: str | None = None
    body: str
    reviewKind: str | None = None
    review_kind: str | None = None
    project: str | None = None
    task: str | None = None
    runId: str | None = None
    run_id: str | None = None
    priority: str = "normal"
    requestedResponseBy: str | None = None
    requested_response_by: str | None = None
    attachments: list[str] | None = None


class MemberMessageResolveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    resolution: str
    status: str = "resolved"


class TeamRetrospectiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facilitatorMember: str | None = None
    facilitator_member: str | None = None
    participants: list[str] | None = None
    project: str | None = None
    sourceTaskPlan: str | None = None
    source_task_plan: str | None = None
    sourceRuns: list[str] | None = None
    source_runs: list[str] | None = None
    sourceTasks: list[str] | None = None
    source_tasks: list[str] | None = None
    sourceMessages: list[str] | None = None
    source_messages: list[str] | None = None
    sourceHandoffs: list[str] | None = None
    source_handoffs: list[str] | None = None
    summary: str
    lessons: list[str] | None = None
    actionItems: list[str] | None = None
    action_items: list[str] | None = None
    memoryKind: str | None = None
    memory_kind: str | None = None
    confidence: float | None = Field(default=0.8, ge=0, le=1)
    reviewGuidance: str | None = None
    review_guidance: str | None = None


class CreateRetrospectiveToolInput(TeamRetrospectiveInput):
    pass


class TaskPlanRetrospectiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facilitatorMember: str | None = None
    facilitator_member: str | None = None
    participants: list[str] | None = None
    summary: str
    lessons: list[str] | None = None
    actionItems: list[str] | None = None
    action_items: list[str] | None = None
    memoryKind: str | None = None
    memory_kind: str | None = None
    confidence: float | None = Field(default=0.8, ge=0, le=1)
    reviewGuidance: str | None = None
    review_guidance: str | None = None


class SuggestRetrospectivesToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member: str | None = None
    project: str | None = None
    task: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class MemberCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str
    profile: dict[str, Any] | None = None
    aboutMe: dict[str, Any] | None = None
    about_me: dict[str, Any] | None = None
    capabilities: list[dict[str, Any]] | None = None
    workStyle: dict[str, Any] | None = None
    work_style: dict[str, Any] | None = None
    workMethod: dict[str, Any] | None = None
    work_method: dict[str, Any] | None = None
    skills: list[str] | None = None
    connectors: list[str] | None = None
    permissionPolicies: list[str] | None = None
    permission_policies: list[str] | None = None
    memoryStores: list[str] | None = None
    memory_stores: list[str] | None = None
    defaultAssignments: list[str] | None = None
    default_assignments: list[str] | None = None


class MemberUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: dict[str, Any] | None = None
    aboutMe: dict[str, Any] | None = None
    about_me: dict[str, Any] | None = None
    capabilities: list[dict[str, Any]] | None = None
    workStyle: dict[str, Any] | None = None
    work_style: dict[str, Any] | None = None
    workMethod: dict[str, Any] | None = None
    work_method: dict[str, Any] | None = None
    projects: list[dict[str, Any]] | None = None
    defaultAssignments: list[str] | None = None
    default_assignments: list[str] | None = None
    skills: list[str] | None = None
    connectors: list[str] | None = None
    permissionPolicies: list[str] | None = None
    permission_policies: list[str] | None = None
    memoryStores: list[str] | None = None
    memory_stores: list[str] | None = None
    growthRecords: list[dict[str, Any]] | None = None
    growth_records: list[dict[str, Any]] | None = None
    performanceMetrics: list[dict[str, Any]] | None = None
    performance_metrics: list[dict[str, Any]] | None = None


class AssignmentCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    member: str
    project: str | None = None
    roleTemplate: str | None = None
    role_template: str | None = None
    roleContext: str | None = None
    role_context: str | None = None
    title: str | None = None
    status: str = "active"
    repositories: list[str] | None = None
    modules: list[str] | None = None
    features: list[str] | None = None
    responsibilities: list[str] | None = None
    scope: dict[str, Any] | None = None
    permissionPolicies: list[str] | None = None
    permission_policies: list[str] | None = None
    memoryBindings: list[str] | None = None
    memory_bindings: list[str] | None = None
    activeFrom: str | None = None
    active_from: str | None = None
    activeTo: str | None = None
    active_to: str | None = None


class AssignmentUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roleTemplate: str | None = None
    role_template: str | None = None
    roleContext: str | None = None
    role_context: str | None = None
    title: str | None = None
    status: str | None = None
    repositories: list[str] | None = None
    modules: list[str] | None = None
    features: list[str] | None = None
    responsibilities: list[str] | None = None
    scope: dict[str, Any] | None = None
    permissionPolicies: list[str] | None = None
    permission_policies: list[str] | None = None
    memoryBindings: list[str] | None = None
    memory_bindings: list[str] | None = None
    activeFrom: str | None = None
    active_from: str | None = None
    activeTo: str | None = None
    active_to: str | None = None


class MemoryBindingCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    targetType: str | None = None
    target_type: str | None = None
    targetId: str | None = None
    target_id: str | None = None
    store: str | None = None
    entry: str | None = None
    collectionPath: str | None = None
    collection_path: str | None = None
    access: list[str] | None = None
    reason: str | None = None
    createdByMember: str | None = None
    created_by_member: str | None = None


class MemoryGrantCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    granteeMember: str | None = None
    grantee_member: str | None = None
    member: str | None = None
    grantorMember: str | None = None
    grantor_member: str | None = None
    task: str | None = None
    runId: str | None = None
    run_id: str | None = None
    stores: list[str] | None = None
    entries: list[str] | None = None
    access: list[str] | None = None
    reason: str | None = None
    expiresAt: str | None = None
    expires_at: str | None = None


class MemoryShareInput(ShareMemoryToolInput):
    pass


class MemoryProposalUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    content: str | None = None
    kind: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] | None = None
    reviewGuidance: str | None = None
    review_guidance: str | None = None


class MemoryProposalReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None
    reviewerMember: str | None = None
    reviewer_member: str | None = None


class MemoryEntryUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    content: str | None = None
    kind: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] | None = None
    editReason: str | None = None
    edit_reason: str | None = None


class MemoryEntryLifecycleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None


class AutomationApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewerMember: str | None = None
    reviewer_member: str | None = None
    reason: str | None = None
    expiresAt: str | None = None
    expires_at: str | None = None


class AutomationTriggerEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    triggerType: str | None = None
    trigger_type: str | None = None
    source: str | None = None
    actorMember: str | None = None
    actor_member: str | None = None
    payload: dict[str, Any] | None = None
    sourceEvent: dict[str, Any] | None = None
    source_event: dict[str, Any] | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None
    dedupeKey: str | None = None
    dedupe_key: str | None = None


class AutomationSchedulerTickInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedulerId: str | None = None
    scheduler_id: str | None = None
    tickKey: str | None = None
    tick_key: str | None = None
    dueAt: str | None = None
    due_at: str | None = None
    leaseSeconds: int | None = None
    lease_seconds: int | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None
    payload: dict[str, Any] | None = None


class AutomationSchedulerLeaseRecoverInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    leaseSeconds: int | None = None
    lease_seconds: int | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None
    reason: str | None = None


class AutomationProviderDeliveryRetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    reason: str | None = None
    headers: dict[str, str] | None = None
    payload: dict[str, Any] | None = None
    rawBody: str | None = None
    raw_body: str | None = None
    receivedAt: str | None = None
    received_at: str | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None


class AutomationWebhookAdmissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str | None = None
    eventType: str | None = None
    event_type: str | None = None
    connector: str | None = None
    headers: dict[str, str] | None = None
    payload: dict[str, Any] | None = None
    rawBody: str | None = None
    raw_body: str | None = None
    actorMember: str | None = None
    actor_member: str | None = None
    receivedAt: str | None = None
    received_at: str | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None


class GitActivityLocalScanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str | None = None
    ref: str | None = None
    actorMember: str | None = None
    actor_member: str | None = None
    receivedAt: str | None = None
    received_at: str | None = None


class GitActivityProviderAdmissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    repository: str | None = None
    sourceType: str | None = None
    source_type: str | None = None
    payload: dict[str, Any] | None = None
    actorMember: str | None = None
    actor_member: str | None = None
    connector: str | None = None
    receivedAt: str | None = None
    received_at: str | None = None


class GitActivityImportPolicyExplainInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    repository: str | None = None
    sourceType: str | None = None
    source_type: str | None = None
    payload: dict[str, Any] | None = None
    connector: str | None = None


class GitActivityImportPromotionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewerMember: str | None = None
    reviewer_member: str | None = None
    member: str | None = None
    assignment: str | None = None
    activityType: str | None = None
    activity_type: str | None = None
    summary: str | None = None
    occurredAt: str | None = None
    occurred_at: str | None = None
    visibility: str = "project"
    refs: list[str] | None = None


class GitActivityCorrelationReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlationKey: str | None = None
    correlation_key: str | None = None
    receipts: list[str] = Field(default_factory=list)
    reviewerMember: str | None = None
    reviewer_member: str | None = None
    decision: str = "approved"
    summary: str | None = None
    recommendedMember: str | None = None
    recommended_member: str | None = None
    recommendedAssignment: str | None = None
    recommended_assignment: str | None = None
    recommendedActivityType: str | None = None
    recommended_activity_type: str | None = None
    reviewedAt: str | None = None
    reviewed_at: str | None = None


class GitActivityCorrelationPromotionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewerMember: str | None = None
    reviewer_member: str | None = None
    member: str | None = None
    assignment: str | None = None
    activityType: str | None = None
    activity_type: str | None = None
    summary: str | None = None
    occurredAt: str | None = None
    occurred_at: str | None = None
    visibility: str = "project"
    refs: list[str] | None = None


class GitActivityEvidenceLifecycleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    lifecycle: str
    reason: str | None = None
    redactionPolicy: str | None = None
    redaction_policy: str | None = None
    exportPolicy: str | None = None
    export_policy: str | None = None
    retainedUntil: str | None = None
    retained_until: str | None = None


class GitActivityRetentionSweepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    targetLifecycle: str | None = None
    target_lifecycle: str | None = None
    project: str | None = None
    member: str | None = None
    assignment: str | None = None
    now: str | None = None
    dryRun: bool | None = True
    dry_run: bool | None = None
    limit: int | None = None


class ConnectorHealthCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    observedRepositories: list[str] | None = None
    observed_repositories: list[str] | None = None
    observedInstallationIds: list[str] | None = None
    observed_installation_ids: list[str] | None = None
    providerNetworkCalled: bool | None = None
    provider_network_called: bool | None = None
    requiredProviderScopes: list[str] | None = None
    required_provider_scopes: list[str] | None = None
    observedProviderScopes: list[str] | None = None
    observed_provider_scopes: list[str] | None = None
    providerDiagnostics: dict[str, Any] | None = None
    provider_diagnostics: dict[str, Any] | None = None


class ConnectorFailureReminderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    connector: str | None = None
    project: str | None = None
    member: str | None = None
    assignment: str | None = None
    lifecycle: str | None = "active"
    maxMessagesPerRun: int | None = None
    max_messages_per_run: int | None = None
    throttleMinutes: int | None = None
    throttle_minutes: int | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None


class ConnectorFailureEscalationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    connector: str | None = None
    project: str | None = None
    member: str | None = None
    assignment: str | None = None
    lifecycle: str | None = "active"
    minEvidence: int | None = None
    min_evidence: int | None = None
    maxReviewRequestsPerRun: int | None = None
    max_review_requests_per_run: int | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None


class ConnectorFailureEscalationResolutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    resolution: str
    evidenceReviewed: list[str] | None = None
    evidence_reviewed: list[str] | None = None
    reminderMessagesReviewed: list[str] | None = None
    reminder_messages_reviewed: list[str] | None = None
    followUpReviewed: dict[str, Any] | None = None
    follow_up_reviewed: dict[str, Any] | None = None


class ConnectorRemediationTaskPlanSubmitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    taskPlan: dict[str, Any] | None = None
    task_plan: dict[str, Any] | None = None
    sourceActionableEvidenceIds: list[str] | None = None
    source_actionable_evidence_ids: list[str] | None = None
    lifecycle: str | None = "active"
    minEvidence: int | None = None
    min_evidence: int | None = None


class ConnectorRemediationTaskPlanAcceptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    reviewedEvidenceIds: list[str] | None = None
    reviewed_evidence_ids: list[str] | None = None
    reviewedReviewRequests: list[str] | None = None
    reviewed_review_requests: list[str] | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None


class ConnectorRemediationTaskRunLaunchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    member: str | None = None
    assignment: str | None = None
    modelProfile: str | None = None
    model_profile: str | None = None
    mode: str | None = None
    branchBase: str | None = None
    branch_base: str | None = None
    reviewedEvidenceIds: list[str] | None = None
    reviewed_evidence_ids: list[str] | None = None
    reviewedReviewRequests: list[str] | None = None
    reviewed_review_requests: list[str] | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None


class ConnectorRemediationRunPermissionRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    actionCanonical: str | None = None
    action_canonical: str | None = None
    actionIndex: int | None = None
    action_index: int | None = None
    reason: str | None = None
    expiresAt: str | None = None
    expires_at: str | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None


class ControlPlanePermissionRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    actionCanonical: str | None = None
    action_canonical: str | None = None
    actionIndex: int | None = None
    action_index: int | None = None
    reason: str | None = None
    expiresAt: str | None = None
    expires_at: str | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None


class RunWorkerStartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    createPr: bool | None = None
    create_pr: bool | None = None


class RetentionCleanupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorMember: str | None = None
    actor_member: str | None = None
    maxAgeDays: int | None = None
    max_age_days: int | None = None
    keepLatestPerConnector: bool | None = None
    keep_latest_per_connector: bool | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None


MCP_TOOL_MODELS: dict[str, type[BaseModel]] = {
    "search_docs": SearchDocsToolInput,
    "search_memory": SearchMemoryToolInput,
    "get_member": GetMemberToolInput,
    "get_project": GetProjectToolInput,
    "list_project_members": ListProjectMembersToolInput,
    "list_member_projects": ListMemberProjectsToolInput,
    "get_member_memory": GetMemberMemoryToolInput,
    "get_project_memory": GetProjectMemoryToolInput,
    "list_assignments": ListAssignmentsToolInput,
    "explain_permissions": ExplainPermissionsToolInput,
    "get_task": GetTaskToolInput,
    "get_context_capsule": GetContextCapsuleToolInput,
    "record_journal": RecordJournalToolInput,
    "record_event": RecordEventToolInput,
    "propose_memory": ProposeMemoryToolInput,
    "grant_memory": GrantMemoryToolInput,
    "share_memory": ShareMemoryToolInput,
    "ask_member": AskMemberToolInput,
    "request_review": ReviewRequestToolInput,
    "suggest_retrospectives": SuggestRetrospectivesToolInput,
    "create_retrospective": CreateRetrospectiveToolInput,
    "handoff": HandoffToolInput,
    "record_member_message": RecordMemberMessageToolInput,
    "create_patch": CreatePatchToolInput,
}


def create_app(workspace_path: str | Path = ".aiteamos") -> FastAPI:
    app = FastAPI(title="AITEAMOS API", version="team-member-greenfield")
    app.state.workspace_path = resolve_workspace_root(workspace_path)

    def index():
        return load_workspace(app.state.workspace_path)

    def records(values) -> list[dict[str, Any]]:
        return [manifest_to_record(value) for value in values]

    def product_user_management_record(result: dict[str, Any]) -> dict[str, Any]:
        return {
            **result,
            "productUser": manifest_to_record(result["productUser"]),
        }

    def product_user_token_envs(current) -> tuple[str, ...]:
        names: list[str] = []
        for product_user in current.product_users.values():
            token_env = product_user.spec.sessionTokenEnv
            if product_user.spec.status == "active" and token_env:
                names.append(token_env)
        return tuple(dict.fromkeys(names))

    def authorized_product_user(current, authorization_header: str | None):
        bindings = tuple(
            ProductUserTokenBinding(
                product_user=product_user.object_id,
                member=product_user.spec.member,
                token_env=product_user.spec.sessionTokenEnv,
            )
            for product_user in current.product_users.values()
            if product_user.spec.status == "active" and product_user.spec.sessionTokenEnv
        )
        matched = product_user_from_authorization(authorization_header, bindings)
        return current.product_users.get(matched) if matched else None

    def session_timestamp_to_iso(timestamp: int) -> str:
        return datetime.fromtimestamp(timestamp, tz=UTC).isoformat().replace("+00:00", "Z")

    def session_cookie_payload_bytes(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def session_cookie_token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def session_cookie_signature(payload: dict[str, Any], token: str) -> str:
        return hmac.new(token.encode("utf-8"), session_cookie_payload_bytes(payload), hashlib.sha256).hexdigest()

    def encode_session_cookie(payload: dict[str, Any]) -> str:
        encoded = base64.urlsafe_b64encode(session_cookie_payload_bytes(payload)).decode("ascii")
        return encoded.rstrip("=")

    def decode_session_cookie(value: str) -> dict[str, Any] | None:
        try:
            padded = value + "=" * (-len(value) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
            payload = json.loads(decoded)
        except (binascii.Error, UnicodeError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def current_product_user_token(product_user) -> str | None:
        token_env = product_user.spec.sessionTokenEnv
        if not token_env:
            return None
        token = os.environ.get(token_env)
        return token if token else None

    def create_session_cookie(product_user, token: str, expires_in_seconds: int = SESSION_COOKIE_MAX_AGE_SECONDS) -> tuple[str, dict[str, Any]]:
        issued_at = int(time.time())
        expires_at = issued_at + expires_in_seconds
        payload: dict[str, Any] = {
            "v": SESSION_COOKIE_VERSION,
            "productUser": product_user.object_id,
            "tokenDigest": session_cookie_token_digest(token),
            "issuedAt": issued_at,
            "expiresAt": expires_at,
            "nonce": secrets.token_urlsafe(16),
            "csrfToken": secrets.token_urlsafe(32),
        }
        signed_payload = {**payload, "signature": session_cookie_signature(payload, token)}
        return encode_session_cookie(signed_payload), signed_payload

    def product_session_from_cookie(current, cookie_value: str | None) -> dict[str, Any] | None:
        if not cookie_value:
            return None
        signed_payload = decode_session_cookie(cookie_value)
        if not signed_payload:
            return None
        signature = signed_payload.get("signature")
        payload = {key: value for key, value in signed_payload.items() if key != "signature"}
        if (
            payload.get("v") != SESSION_COOKIE_VERSION
            or not isinstance(payload.get("productUser"), str)
            or not isinstance(payload.get("tokenDigest"), str)
            or not isinstance(payload.get("issuedAt"), int)
            or not isinstance(payload.get("expiresAt"), int)
            or not isinstance(payload.get("nonce"), str)
            or not isinstance(payload.get("csrfToken"), str)
            or not isinstance(signature, str)
        ):
            return None
        if payload["expiresAt"] <= int(time.time()):
            return None
        product_user = current.product_users.get(payload["productUser"])
        if not product_user or product_user.spec.status != "active":
            return None
        token = current_product_user_token(product_user)
        if not token:
            return None
        if not hmac.compare_digest(payload["tokenDigest"], session_cookie_token_digest(token)):
            return None
        expected_signature = session_cookie_signature(payload, token)
        if not hmac.compare_digest(signature, expected_signature):
            return None
        return {
            "authorizationHeader": f"Bearer {token}",
            "productUser": product_user,
            "session": payload,
        }

    def auth_context_for_request(current, request: Request) -> tuple[str | None, dict[str, Any] | None]:
        authorization_header = request.headers.get("authorization")
        if authorization_header:
            return authorization_header, None
        product_session = product_session_from_cookie(current, request.cookies.get(SESSION_COOKIE_NAME))
        if not product_session:
            return None, None
        return product_session["authorizationHeader"], product_session

    def authorization_header_for_request(current, request: Request) -> str | None:
        authorization_header, _product_session = auth_context_for_request(current, request)
        return authorization_header

    def product_session_login_record(product_user, session: dict[str, Any]) -> dict[str, Any]:
        issued_at = int(session["issuedAt"])
        expires_at = int(session["expiresAt"])
        return SessionLoginRecord(
            productUser=product_user.object_id,
            viewerMember=product_user.spec.member,
            admin="admin" in product_user.spec.roles,
            canSelectViewer="admin" in product_user.spec.roles,
            expiresInSeconds=max(1, expires_at - issued_at),
            issuedAt=session_timestamp_to_iso(issued_at),
            expiresAt=session_timestamp_to_iso(expires_at),
            sessionVersion=SESSION_COOKIE_VERSION,
            sessionId=session["nonce"],
            csrfToken=session["csrfToken"],
        ).model_dump(mode="json")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def authorize_http_request(request: Request, call_next):
        trace_context = new_trace_context(request.headers.get("traceparent"), component="api")
        request.state.trace_context = trace_context
        current = index()
        extra_api_token_envs = product_user_token_envs(current)
        authorization_header, product_session = auth_context_for_request(current, request)
        decision = authorize_request(request.method, request.url.path, authorization_header, extra_api_token_envs=extra_api_token_envs)
        if not decision.allowed:
            response = JSONResponse(
                status_code=decision.status_code,
                content={
                    "detail": decision.detail,
                    "scope": decision.scope,
                    "acceptedTokenEnvNames": list(decision.accepted_token_envs),
                },
            )
            for header, value in trace_response_headers(trace_context).items():
                response.headers[header] = value
            return response
        normalized_path = request.url.path.rstrip("/") or "/"
        if (
            product_session
            and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
            and normalized_path != "/session/logout"
        ):
            provided_csrf = request.headers.get(SESSION_CSRF_HEADER)
            expected_csrf = product_session["session"]["csrfToken"]
            if not provided_csrf or not hmac.compare_digest(provided_csrf, expected_csrf):
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "missing or invalid csrf token for cookie session"},
                )
                for header, value in trace_response_headers(trace_context).items():
                    response.headers[header] = value
                return response
        request.state.viewer_member = viewer_member_from_authorization(authorization_header)
        product_user = authorized_product_user(current, authorization_header)
        request.state.product_user_id = product_user.object_id if product_user else None
        request.state.product_user_member = product_user.spec.member if product_user else None
        request.state.product_user_admin = bool(product_user and "admin" in product_user.spec.roles)
        request.state.product_session_id = product_session["session"]["nonce"] if product_session else None
        response = await call_next(request)
        for header, value in trace_response_headers(trace_context).items():
            response.headers[header] = value
        return response

    def require_product_user_management_authority(request: Request) -> None:
        current = index()
        authorization_header = authorization_header_for_request(current, request)
        if not api_auth_configured(extra_api_token_envs=product_user_token_envs(current)):
            return
        if api_token_from_authorization(authorization_header):
            return
        if bool(getattr(request.state, "product_user_admin", False)):
            return
        raise HTTPException(status_code=403, detail="ProductUser management requires ProductUser admin or API token")

    def governed_viewer_member(request: Request, explicit_viewer: str | None = None) -> str | None:
        authenticated_viewer = getattr(request.state, "viewer_member", None)
        if authenticated_viewer and explicit_viewer and explicit_viewer != authenticated_viewer:
            raise HTTPException(status_code=403, detail="viewerMember does not match authenticated TeamMember")
        product_user_id = getattr(request.state, "product_user_id", None)
        product_member = getattr(request.state, "product_user_member", None)
        product_admin = bool(getattr(request.state, "product_user_admin", False))
        if product_user_id and not product_admin:
            if explicit_viewer and explicit_viewer != product_member:
                raise HTTPException(status_code=403, detail="viewerMember does not match authenticated ProductUser")
            return product_member
        return authenticated_viewer or explicit_viewer

    def session_projection(
        request: Request,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> dict[str, Any]:
        current = index()
        requested_viewer = viewerMember or viewer_member
        authenticated_viewer = getattr(request.state, "viewer_member", None)
        if authenticated_viewer and requested_viewer and requested_viewer != authenticated_viewer:
            raise HTTPException(status_code=403, detail="viewerMember does not match authenticated TeamMember")
        product_user_id = getattr(request.state, "product_user_id", None)
        product_member = getattr(request.state, "product_user_member", None)
        product_admin = bool(getattr(request.state, "product_user_admin", False))
        product_user = current.product_users.get(product_user_id) if product_user_id else None
        if product_user and not product_admin and requested_viewer and requested_viewer != product_member:
            raise HTTPException(status_code=403, detail="viewerMember does not match authenticated ProductUser")

        bearer_is_api_token = api_token_from_authorization(request.headers.get("authorization"))
        extra_api_token_envs = product_user_token_envs(current)
        protection_configured = api_auth_configured(extra_api_token_envs=extra_api_token_envs)
        effective_viewer = authenticated_viewer or requested_viewer or (product_member if product_user else None)
        if effective_viewer and effective_viewer not in current.members:
            raise HTTPException(status_code=404, detail=f"unknown viewer member {effective_viewer}")

        member = current.members.get(effective_viewer) if effective_viewer else None
        warnings: list[str] = []
        if authenticated_viewer:
            auth_mode = "viewer-token"
            authenticated = True
            token_bound = True
            admin = False
            can_select_viewer = False
            projection_mode = "token-bound-viewer"
        elif product_user:
            auth_mode = "product-user-token"
            authenticated = True
            token_bound = True
            admin = product_admin
            can_select_viewer = product_admin
            projection_mode = (
                "admin-selected-viewer"
                if product_admin and requested_viewer
                else "token-bound-viewer"
                if effective_viewer
                else "public-redacted"
            )
        elif bearer_is_api_token:
            auth_mode = "api-token"
            authenticated = True
            token_bound = False
            admin = True
            can_select_viewer = True
            projection_mode = "admin-selected-viewer" if effective_viewer else "public-redacted"
        elif protection_configured:
            auth_mode = "anonymous"
            authenticated = False
            token_bound = False
            admin = False
            can_select_viewer = False
            projection_mode = "public-redacted"
            warnings.append("API auth is configured; use an authenticated session for governed projections.")
        else:
            auth_mode = "open-local"
            authenticated = False
            token_bound = False
            admin = False
            can_select_viewer = True
            projection_mode = "selected-viewer" if effective_viewer else "public-redacted"
            warnings.append("API auth is not configured; Projection Viewer is a local demo selector.")

        record = SessionProjectionRecord(
            spec={
                "authenticated": authenticated,
                "authMode": auth_mode,
                "tokenBound": token_bound,
                "admin": admin,
                "productUser": product_user.object_id if product_user else None,
                "productUserStatus": product_user.spec.status if product_user else None,
                "productUserMember": product_member,
                "productUserRoles": product_user.spec.roles if product_user else [],
                "canApproveGovernance": bool(admin or (product_user and "governance_reviewer" in product_user.spec.roles)),
                "viewerMember": effective_viewer,
                "viewerMemberKind": member.spec.kind if member else None,
                "viewerMemberStatus": member.spec.profile.status if member else None,
                "requestedViewerMember": requested_viewer,
                "canSelectViewer": can_select_viewer,
                "projectionMode": projection_mode,
                "governedScopes": ["memory", "skills", "permissions", "project", "employee", "assignment"],
                "warnings": warnings,
            }
        )
        return record.model_dump(mode="json")

    def set_product_session_cookie(response: Response, cookie_value: str) -> None:
        policy = session_cookie_policy()
        response.set_cookie(
            SESSION_COOKIE_NAME,
            cookie_value,
            max_age=SESSION_COOKIE_MAX_AGE_SECONDS,
            httponly=True,
            samesite=policy["samesite"],
            secure=bool(policy["secure"]),
            path="/",
        )

    def post_session_login(payload: SessionLoginInput, response: Response) -> dict[str, Any]:
        token = payload.token.strip()
        if not token:
            raise HTTPException(status_code=401, detail="invalid product user session token")
        current = index()
        product_user = authorized_product_user(current, f"Bearer {token}")
        if not product_user:
            raise HTTPException(status_code=401, detail="invalid product user session token")
        cookie_value, session = create_session_cookie(product_user, token)
        set_product_session_cookie(response, cookie_value)
        return product_session_login_record(product_user, session)

    def post_session_renew(request: Request, response: Response) -> dict[str, Any]:
        current = index()
        product_session = product_session_from_cookie(current, request.cookies.get(SESSION_COOKIE_NAME))
        if not product_session:
            raise HTTPException(status_code=401, detail="invalid or expired product user session")
        product_user = product_session["productUser"]
        token = current_product_user_token(product_user)
        if not token:
            raise HTTPException(status_code=401, detail="invalid or expired product user session")
        cookie_value, session = create_session_cookie(product_user, token)
        set_product_session_cookie(response, cookie_value)
        return product_session_login_record(product_user, session)

    def post_session_logout(response: Response) -> dict[str, str]:
        policy = session_cookie_policy()
        response.delete_cookie(
            SESSION_COOKIE_NAME,
            path="/",
            secure=bool(policy["secure"]),
            httponly=True,
            samesite=policy["samesite"],
        )
        return {"status": "logged-out"}

    def run_record(run_id: str) -> dict[str, Any]:
        current = index()
        if run_id not in current.runs:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
        record = manifest_to_record(current.runs[run_id])
        record["events"] = current.run_events.get(run_id, [])
        record["journal"] = current.run_journals.get(run_id)
        record["contextManifest"] = current.run_context_manifests.get(run_id)
        return record

    def get_run_trace_context(run_id: str, request: Request) -> dict[str, Any]:
        current = index()
        if run_id not in current.runs:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
        return run_trace_context(
            current,
            run_id,
            api_context=getattr(request.state, "trace_context", None),
            parent_traceparent=request.headers.get("traceparent"),
        )

    def project_member_view() -> list[dict[str, Any]]:
        current = index()
        rows: list[dict[str, Any]] = []
        for member_id in sorted(current.members):
            assignments = [assignment for assignment in current.assignments.values() if assignment.spec.member == member_id]
            tasks = [task for task in current.tasks.values() if task.spec.assignedMember == member_id]
            runs = [run for run in current.runs.values() if run.spec.member == member_id]
            rows.append(
                {
                    "project": current.project.object_id,
                    "member": member_id,
                    "memberKind": current.members[member_id].spec.kind,
                    "assignmentCount": len(assignments),
                    "taskCount": len(tasks),
                    "runCount": len(runs),
                    "assignments": [assignment.object_id for assignment in assignments],
                }
            )
        return rows

    def health_summary(issues: list[dict[str, str]]) -> dict[str, int]:
        return {
            "issues": len(issues),
            "errors": sum(1 for issue in issues if issue.get("severity") == "error"),
            "warnings": sum(1 for issue in issues if issue.get("severity") == "warning"),
        }

    def get_prometheus_metrics() -> Response:
        return Response(
            render_prometheus_metrics(index()),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    def get_model_cost_alerts(
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        task: str | None = None,
    ) -> dict[str, Any]:
        try:
            return cost_alert_candidates(index(), project=project, member=member, assignment=assignment, task=task)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def post_model_cost_alerts(payload: CostAlertRouteInput | None = None) -> dict[str, Any]:
        body = payload or CostAlertRouteInput()
        actor_member = body.actorMember or body.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            return route_cost_alerts(
                app.state.workspace_path,
                actor_member=actor_member,
                project=body.project,
                member=body.member,
                assignment=body.assignment,
                task=body.task,
                max_messages=body.maxMessagesPerRun if body.maxMessagesPerRun is not None else body.max_messages_per_run,
                dry_run=bool(body.dry_run if body.dry_run is not None else body.dryRun),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def inline_endpoint(handler: Callable[..., Any]) -> Callable[..., Any]:
        async def endpoint(*args: Any, **kwargs: Any) -> Any:
            result = handler(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        endpoint.__name__ = getattr(handler, "__name__", "endpoint")
        endpoint.__doc__ = getattr(handler, "__doc__", None)
        endpoint.__signature__ = inspect.signature(handler)  # type: ignore[attr-defined]
        return endpoint

    def ensure_workspace_scope(wsId: str) -> None:
        workspace_id = index().workspace.object_id
        if wsId != workspace_id:
            raise HTTPException(status_code=404, detail=f"unknown workspace {wsId}")

    def workspace_scoped_endpoint(handler: Callable[..., Any]) -> Callable[..., Any]:
        async def endpoint(*args: Any, **kwargs: Any) -> Any:
            ws_id = str(kwargs.pop("wsId"))
            ensure_workspace_scope(ws_id)
            result = handler(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        endpoint.__name__ = f"workspace_scoped_{getattr(handler, '__name__', 'endpoint')}"
        endpoint.__doc__ = getattr(handler, "__doc__", None)
        signature = inspect.signature(handler)
        parameters = [
            inspect.Parameter("wsId", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
            *signature.parameters.values(),
        ]
        endpoint.__signature__ = signature.replace(parameters=parameters)  # type: ignore[attr-defined]
        return endpoint

    def add_workspace_get(path: str, handler: Callable[..., Any]) -> None:
        endpoint = workspace_scoped_endpoint(handler)
        app.get(f"/workspaces/{{wsId}}{path}")(endpoint)

    def add_workspace_post(path: str, handler: Callable[..., Any]) -> None:
        endpoint = workspace_scoped_endpoint(handler)
        app.post(f"/workspaces/{{wsId}}{path}")(endpoint)

    def add_workspace_patch(path: str, handler: Callable[..., Any]) -> None:
        endpoint = workspace_scoped_endpoint(handler)
        app.patch(f"/workspaces/{{wsId}}{path}")(endpoint)

    def add_workspace_delete(path: str, handler: Callable[..., Any]) -> None:
        endpoint = workspace_scoped_endpoint(handler)
        app.delete(f"/workspaces/{{wsId}}{path}")(endpoint)

    def add_get(path: str, handler: Callable[..., Any]) -> None:
        add_workspace_get(path, handler)

    def add_post(path: str, handler: Callable[..., Any]) -> None:
        add_workspace_post(path, handler)

    def add_patch(path: str, handler: Callable[..., Any]) -> None:
        add_workspace_patch(path, handler)

    def add_delete(path: str, handler: Callable[..., Any]) -> None:
        add_workspace_delete(path, handler)

    def add_global_get(path: str, handler: Callable[..., Any]) -> None:
        app.get(path)(inline_endpoint(handler))

    def add_global_post(path: str, handler: Callable[..., Any]) -> None:
        app.post(path)(inline_endpoint(handler))

    def get_project(project_id: str) -> dict[str, Any]:
        current = index()
        if project_id != current.project.object_id:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id}")
        return manifest_to_record(current.project)

    def project_members(project_id: str) -> list[dict[str, Any]]:
        current = index()
        if project_id != current.project.object_id:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id}")
        member_ids = {assignment.spec.member for assignment in current.assignments.values() if assignment.spec.project == project_id}
        return [manifest_to_record(current.members[member_id]) for member_id in sorted(member_ids) if member_id in current.members]

    def get_member(member_id: str) -> dict[str, Any]:
        current = index()
        if member_id not in current.members:
            raise HTTPException(status_code=404, detail=f"unknown member {member_id}")
        return manifest_to_record(current.members[member_id])

    def post_member(payload: MemberCreateInput) -> dict[str, Any]:
        try:
            member = create_member(
                app.state.workspace_path,
                name=payload.name,
                kind=payload.kind,
                profile=payload.profile,
                about_me=payload.aboutMe or payload.about_me,
                capabilities=payload.capabilities,
                work_style=payload.workStyle or payload.work_style,
                work_method=payload.workMethod or payload.work_method,
                skills=payload.skills,
                connectors=payload.connectors,
                permission_policies=payload.permissionPolicies or payload.permission_policies,
                memory_stores=payload.memoryStores or payload.memory_stores,
                default_assignments=payload.defaultAssignments or payload.default_assignments,
            )
            return manifest_to_record(member)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def patch_member(member_id: str, payload: MemberUpdateInput) -> dict[str, Any]:
        updates = _camel_updates(payload)
        try:
            return manifest_to_record(update_member(app.state.workspace_path, member_id, updates))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_archive_member(member_id: str) -> dict[str, Any]:
        try:
            return manifest_to_record(archive_member(app.state.workspace_path, member_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def post_member_delete_request(member_id: str, payload: MemberDeleteRequestInput) -> dict[str, Any]:
        try:
            return request_member_delete(
                app.state.workspace_path,
                member_id,
                actor_member=payload.actorMember,
                reason=payload.reason,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_product_users(request: Request) -> list[dict[str, Any]]:
        require_product_user_management_authority(request)
        return records(index().product_users.values())

    def get_product_user(request: Request, user_id: str) -> dict[str, Any]:
        require_product_user_management_authority(request)
        current = index()
        if user_id not in current.product_users:
            raise HTTPException(status_code=404, detail=f"unknown product user {user_id}")
        return manifest_to_record(current.product_users[user_id])

    def post_product_user(request: Request, payload: ProductUserCreateInput) -> dict[str, Any]:
        require_product_user_management_authority(request)
        try:
            return product_user_management_record(
                create_product_user(
                    app.state.workspace_path,
                    name=payload.name,
                    actor_member=payload.actorMember,
                    display_name=payload.displayName,
                    member=payload.member,
                    identity_provider=payload.identityProvider,
                    identity_subject_hash=payload.identitySubjectHash,
                    status=payload.status,
                    roles=payload.roles,
                    session_token_env=payload.sessionTokenEnv,
                    governance_scopes=payload.governanceScopes,
                    reason=payload.reason,
                )
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def patch_product_user(request: Request, user_id: str, payload: ProductUserUpdateInput) -> dict[str, Any]:
        require_product_user_management_authority(request)
        try:
            return product_user_management_record(
                update_product_user(
                    app.state.workspace_path,
                    user_id,
                    actor_member=payload.actorMember,
                    display_name=payload.displayName,
                    member=payload.member,
                    identity_provider=payload.identityProvider,
                    identity_subject_hash=payload.identitySubjectHash,
                    status=payload.status,
                    roles=payload.roles,
                    session_token_env=payload.sessionTokenEnv,
                    governance_scopes=payload.governanceScopes,
                    reason=payload.reason,
                )
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_archive_product_user(
        request: Request,
        user_id: str,
        payload: ProductUserArchiveInput,
    ) -> dict[str, Any]:
        require_product_user_management_authority(request)
        try:
            return product_user_management_record(
                archive_product_user(
                    app.state.workspace_path,
                    user_id,
                    actor_member=payload.actorMember,
                    reason=payload.reason,
                )
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_skills(
        request: Request,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return skill_records(index(), viewer_member=governed_viewer_member(request, viewerMember or viewer_member))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def get_skill(
        request: Request,
        skill_id: str,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> dict[str, Any]:
        try:
            return skill_record(index(), skill_id, viewer_member=governed_viewer_member(request, viewerMember or viewer_member))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def get_project_skills(
        request: Request,
        project_id: str,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return skill_projection_records(
                index(),
                project=project_id,
                viewer_member=governed_viewer_member(request, viewerMember or viewer_member),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def get_member_skills(
        request: Request,
        member_id: str,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return skill_projection_records(
                index(),
                member=member_id,
                viewer_member=governed_viewer_member(request, viewerMember or viewer_member),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def get_assignment_skills(
        request: Request,
        assignment_id: str,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return skill_projection_records(
                index(),
                assignment=assignment_id,
                viewer_member=governed_viewer_member(request, viewerMember or viewer_member),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_skill(payload: SkillCreateInput) -> dict[str, Any]:
        try:
            result = create_skill(
                app.state.workspace_path,
                name=payload.name,
                actor_member=payload.actorMember,
                description=payload.description,
                owner_member=payload.ownerMember,
                projects=payload.projects,
                capabilities=payload.capabilities,
                required_permissions=payload.requiredPermissions,
                entrypoint=payload.entrypoint,
                lifecycle=payload.lifecycle,
                reason=payload.reason,
            )
            return {
                "skill": manifest_to_record(result["skill"]),
                "permissionDecision": result["permissionDecision"],
                "decisionAudit": result["decisionAudit"],
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def patch_skill(skill_id: str, payload: SkillUpdateInput) -> dict[str, Any]:
        try:
            result = update_skill(app.state.workspace_path, skill_id, _camel_updates(payload))
            return {
                "skill": manifest_to_record(result["skill"]),
                "permissionDecision": result["permissionDecision"],
                "decisionAudit": result["decisionAudit"],
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_archive_skill(skill_id: str, payload: SkillArchiveInput) -> dict[str, Any]:
        try:
            result = archive_skill(
                app.state.workspace_path,
                skill_id,
                actor_member=payload.actorMember,
                reason=payload.reason,
            )
            return {
                "skill": manifest_to_record(result["skill"]),
                "permissionDecision": result["permissionDecision"],
                "decisionAudit": result["decisionAudit"],
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_skill_member(skill_id: str, member_id: str, payload: SkillAttachMemberInput) -> dict[str, Any]:
        try:
            result = attach_skill_to_member(
                app.state.workspace_path,
                skill_id,
                actor_member=payload.actorMember,
                member=payload.member or member_id,
                growth_summary=payload.growthSummary,
                reason=payload.reason,
            )
            return {
                "skill": manifest_to_record(result["skill"]),
                "member": manifest_to_record(result["member"]),
                "permissionDecisions": result["permissionDecisions"],
                "decisionAudit": result["decisionAudit"],
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def member_projects(member_id: str) -> list[dict[str, Any]]:
        current = index()
        if member_id not in current.members:
            raise HTTPException(status_code=404, detail=f"unknown member {member_id}")
        projects = {assignment.spec.project for assignment in current.assignments.values() if assignment.spec.member == member_id}
        return [manifest_to_record(current.project)] if current.project.object_id in projects else []

    def member_activity(member_id: str) -> list[dict[str, Any]]:
        current = index()
        if member_id not in current.members:
            raise HTTPException(status_code=404, detail=f"unknown member {member_id}")
        return records(activity for activity in current.member_activities.values() if activity.spec.member == member_id)

    def all_member_activity(
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
    ) -> list[dict[str, Any]]:
        current = index()
        return records(
            activity
            for activity in current.member_activities.values()
            if (not project or activity.spec.project == project)
            and (not member or activity.spec.member == member)
            and (not assignment or activity.spec.assignment == assignment)
        )

    def project_member_activity(project_id: str, assignment: str | None = None) -> list[dict[str, Any]]:
        current = index()
        if project_id != current.project.object_id:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id}")
        return records(
            activity
            for activity in current.member_activities.values()
            if activity.spec.project == project_id and (not assignment or activity.spec.assignment == assignment)
        )

    def git_activity(
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
    ) -> list[dict[str, Any]]:
        current = index()
        return records(
            activity
            for activity in current.git_activities.values()
            if (not project or activity.spec.project == project)
            and (not member or activity.spec.member == member)
            and (not assignment or activity.spec.assignment == assignment)
        )

    def project_git_activity(project_id: str, assignment: str | None = None) -> list[dict[str, Any]]:
        current = index()
        if project_id != current.project.object_id:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id}")
        return records(
            activity
            for activity in current.git_activities.values()
            if activity.spec.project == project_id and (not assignment or activity.spec.assignment == assignment)
        )

    def member_git_activity(member_id: str, project: str | None = None, assignment: str | None = None) -> list[dict[str, Any]]:
        current = index()
        if member_id not in current.members:
            raise HTTPException(status_code=404, detail=f"unknown member {member_id}")
        return records(
            activity
            for activity in current.git_activities.values()
            if activity.spec.member == member_id
            and (not project or activity.spec.project == project)
            and (not assignment or activity.spec.assignment == assignment)
        )

    def post_git_activity_evidence_lifecycle(activity_id: str, payload: GitActivityEvidenceLifecycleInput) -> dict[str, Any]:
        actor_member = payload.actorMember or payload.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            result = update_git_activity_evidence_lifecycle(
                app.state.workspace_path,
                activity_id,
                actor_member=actor_member,
                lifecycle=payload.lifecycle,
                reason=payload.reason,
                redaction_policy=payload.redactionPolicy or payload.redaction_policy,
                export_policy=payload.exportPolicy or payload.export_policy,
                retained_until=payload.retainedUntil or payload.retained_until,
            )
            return {"activity": manifest_to_record(result["activity"]), "updated": bool(result.get("updated"))}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def git_activity_retention_candidate_view(
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        now: str | None = None,
    ) -> dict[str, Any]:
        return git_activity_retention_candidates(index(), project=project, member=member, assignment=assignment, now=now)

    def post_git_activity_retention_sweep(payload: GitActivityRetentionSweepInput) -> dict[str, Any]:
        actor_member = payload.actorMember or payload.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        dry_run = payload.dry_run if payload.dry_run is not None else (True if payload.dryRun is None else payload.dryRun)
        try:
            result = sweep_git_activity_retention(
                app.state.workspace_path,
                actor_member=actor_member,
                target_lifecycle=payload.targetLifecycle or payload.target_lifecycle,
                project=payload.project,
                member=payload.member,
                assignment=payload.assignment,
                now=payload.now,
                dry_run=dry_run,
                limit=payload.limit,
            )
            return result
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def git_activity_import_receipts(
        project: str | None = None,
        repository: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        current = index()
        return records(
            receipt
            for receipt in current.git_activity_import_receipts.values()
            if (not project or receipt.spec.project == project)
            and (not repository or receipt.spec.repository == repository)
            and (not status or receipt.spec.status == status)
        )

    def project_git_activity_import_receipts(
        project_id: str,
        repository: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        current = index()
        if project_id != current.project.object_id:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id}")
        return records(
            receipt
            for receipt in current.git_activity_import_receipts.values()
            if receipt.spec.project == project_id
            and (not repository or receipt.spec.repository == repository)
            and (not status or receipt.spec.status == status)
        )

    def git_activity_import_correlation_preview(
        project: str | None = None,
        repository: str | None = None,
        provider: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        try:
            return git_activity_correlation_preview(
                index(),
                project=project,
                repository=repository,
                provider=provider,
                member=member,
                assignment=assignment,
                status=status,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def project_git_activity_import_correlation_preview(
        project_id: str,
        repository: str | None = None,
        provider: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        current = index()
        if project_id != current.project.object_id:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id}")
        return git_activity_correlation_preview(
            current,
            project=project_id,
            repository=repository,
            provider=provider,
            member=member,
            assignment=assignment,
            status=status,
        )

    def git_activity_correlation_reviews(
        project: str | None = None,
        repository: str | None = None,
        provider: str | None = None,
        decision: str | None = None,
        reviewerMember: str | None = None,
    ) -> list[dict[str, Any]]:
        current = index()
        return records(
            review
            for review in current.git_activity_correlation_reviews.values()
            if (not project or review.spec.project == project)
            and (not repository or review.spec.repository == repository)
            and (not provider or review.spec.provider == provider)
            and (not decision or review.spec.decision == decision)
            and (not reviewerMember or review.spec.reviewerMember == reviewerMember)
        )

    def git_activity_correlation_promotion_candidate_view(
        project: str | None = None,
        automation: str | None = None,
        serviceMember: str | None = None,
        includeBlocked: bool = True,
    ) -> dict[str, Any]:
        try:
            return git_activity_correlation_promotion_candidates(
                index(),
                project=project,
                automation=automation,
                service_member=serviceMember,
                include_blocked=includeBlocked,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def project_git_activity_correlation_reviews(
        project_id: str,
        repository: str | None = None,
        provider: str | None = None,
        decision: str | None = None,
        reviewerMember: str | None = None,
    ) -> list[dict[str, Any]]:
        current = index()
        if project_id != current.project.object_id:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id}")
        return records(
            review
            for review in current.git_activity_correlation_reviews.values()
            if review.spec.project == project_id
            and (not repository or review.spec.repository == repository)
            and (not provider or review.spec.provider == provider)
            and (not decision or review.spec.decision == decision)
            and (not reviewerMember or review.spec.reviewerMember == reviewerMember)
        )

    def project_git_activity_correlation_promotion_candidate_view(
        project_id: str,
        automation: str | None = None,
        serviceMember: str | None = None,
        includeBlocked: bool = True,
    ) -> dict[str, Any]:
        current = index()
        if project_id != current.project.object_id:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id}")
        try:
            return git_activity_correlation_promotion_candidates(
                current,
                project=project_id,
                automation=automation,
                service_member=serviceMember,
                include_blocked=includeBlocked,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_git_activity_correlation_review(payload: GitActivityCorrelationReviewInput) -> dict[str, Any]:
        correlation_key = payload.correlationKey or payload.correlation_key
        reviewer_member = payload.reviewerMember or payload.reviewer_member
        if not correlation_key:
            raise HTTPException(status_code=400, detail="correlationKey is required")
        if not reviewer_member:
            raise HTTPException(status_code=400, detail="reviewerMember is required")
        try:
            result = review_git_activity_correlation(
                app.state.workspace_path,
                correlation_key=correlation_key,
                receipts=payload.receipts,
                reviewer_member=reviewer_member,
                decision=payload.decision,
                summary=payload.summary,
                recommended_member=payload.recommendedMember or payload.recommended_member,
                recommended_assignment=payload.recommendedAssignment or payload.recommended_assignment,
                recommended_activity_type=payload.recommendedActivityType or payload.recommended_activity_type,
                reviewed_at=payload.reviewedAt or payload.reviewed_at,
            )
            return {
                "review": manifest_to_record(result["review"]),
                "created": bool(result.get("created")),
                "duplicateOf": result.get("duplicateOf"),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_git_activity_correlation_promotion(review_id: str, payload: GitActivityCorrelationPromotionInput) -> dict[str, Any]:
        reviewer_member = payload.reviewerMember or payload.reviewer_member
        if not reviewer_member:
            raise HTTPException(status_code=400, detail="reviewerMember is required")
        try:
            result = promote_git_activity_correlation_review(
                app.state.workspace_path,
                review_id,
                reviewer_member=reviewer_member,
                member=payload.member,
                assignment=payload.assignment,
                activity_type=payload.activityType or payload.activity_type,
                summary=payload.summary,
                occurred_at=payload.occurredAt or payload.occurred_at,
                visibility=payload.visibility,
                refs=payload.refs,
            )
            return {
                "review": manifest_to_record(result["review"]),
                "receipts": records(result["receipts"]),
                "activities": records(result["activities"]),
                "created": bool(result.get("created")),
                "alreadyPromoted": bool(result.get("alreadyPromoted")),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_git_activity_local_scan(payload: GitActivityLocalScanInput | None = None) -> dict[str, Any]:
        body = payload or GitActivityLocalScanInput()
        try:
            result = admit_local_git_activity_import(
                app.state.workspace_path,
                repository=body.repository,
                ref=body.ref,
                actor_member=body.actorMember or body.actor_member,
                received_at=body.receivedAt or body.received_at,
            )
            return {
                "receipt": manifest_to_record(result["receipt"]),
                "created": bool(result.get("created")),
                "duplicateOf": result.get("duplicateOf"),
                "dedupeKey": result.get("dedupeKey"),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_git_activity_provider_admission(payload: GitActivityProviderAdmissionInput) -> dict[str, Any]:
        try:
            result = admit_provider_git_activity_import(
                app.state.workspace_path,
                provider=payload.provider,
                repository=payload.repository,
                source_type=payload.sourceType or payload.source_type or "webhook",
                payload=payload.payload or {},
                actor_member=payload.actorMember or payload.actor_member,
                connector=payload.connector,
                received_at=payload.receivedAt or payload.received_at,
            )
            return {
                "receipt": manifest_to_record(result["receipt"]),
                "created": bool(result.get("created")),
                "duplicateOf": result.get("duplicateOf"),
                "dedupeKey": result.get("dedupeKey"),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_git_activity_import_policy_explain(payload: GitActivityImportPolicyExplainInput) -> dict[str, Any]:
        try:
            return explain_git_activity_import_policy(
                index(),
                provider=payload.provider,
                repository=payload.repository,
                source_type=payload.sourceType or payload.source_type or "webhook",
                payload=payload.payload or {},
                connector=payload.connector,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_git_activity_import_promotion(receipt_id: str, payload: GitActivityImportPromotionInput) -> dict[str, Any]:
        reviewer_member = payload.reviewerMember or payload.reviewer_member
        if not reviewer_member:
            raise HTTPException(status_code=400, detail="reviewerMember is required")
        try:
            result = promote_git_activity_import_receipt(
                app.state.workspace_path,
                receipt_id,
                reviewer_member=reviewer_member,
                member=payload.member,
                assignment=payload.assignment,
                activity_type=payload.activityType or payload.activity_type,
                summary=payload.summary,
                occurred_at=payload.occurredAt or payload.occurred_at,
                visibility=payload.visibility,
                refs=payload.refs,
            )
            return {
                "receipt": manifest_to_record(result["receipt"]),
                "activities": records(result["activities"]),
                "created": bool(result.get("created")),
                "alreadyImported": bool(result.get("alreadyImported")),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def member_growth(project: str | None = None, member: str | None = None, assignment: str | None = None) -> dict[str, Any]:
        try:
            return member_growth_projection(index(), member=member, project=project, assignment=assignment)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_manager_inbox(project: str | None = None, assignment: str | None = None) -> ManagerInputBundle:
        try:
            return ManagerInputBundle.model_validate(
                manager_input_bundle(
                    index(),
                    project=project,
                    assignment=assignment,
                )
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_manager_evaluation(project: str | None = None, assignment: str | None = None, manager: str = "aiteamos-manager", limit: int = 5) -> dict[str, Any]:
        try:
            return manager_evaluation_signal(index(), manager=manager, project=project, assignment=assignment, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def project_member_growth(project_id: str, assignment: str | None = None) -> dict[str, Any]:
        try:
            return member_growth_projection(index(), project=project_id, assignment=assignment)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def selected_member_growth(member_id: str, project: str | None = None, assignment: str | None = None) -> dict[str, Any]:
        try:
            return member_growth_projection(index(), member=member_id, project=project, assignment=assignment)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_member_growth_record(member_id: str, payload: MemberGrowthRecordInput) -> dict[str, Any]:
        try:
            result = record_member_growth(
                app.state.workspace_path,
                member_id,
                actor_member=payload.actorMember,
                summary=payload.summary,
                project=payload.project,
                source_action=payload.sourceAction,
                source_task=payload.sourceTask,
                source_run=payload.sourceRun,
                source_review=payload.sourceReview,
                source_memory_proposal=payload.sourceMemoryProposal,
                source_skill=payload.sourceSkill,
                evidence=payload.evidence,
                reason=payload.reason,
            )
            return {
                "member": manifest_to_record(result["member"]),
                "growthRecord": result["growthRecord"],
                "decisionAudit": result["decisionAudit"],
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_assignment(assignment_id: str) -> dict[str, Any]:
        current = index()
        if assignment_id not in current.assignments:
            raise HTTPException(status_code=404, detail=f"unknown assignment {assignment_id}")
        return manifest_to_record(current.assignments[assignment_id])

    def post_assignment(payload: AssignmentCreateInput) -> dict[str, Any]:
        try:
            assignment = create_assignment(
                app.state.workspace_path,
                name=payload.name,
                member=payload.member,
                project=payload.project,
                role_template=payload.roleTemplate or payload.role_template,
                role_context=payload.roleContext or payload.role_context,
                title=payload.title,
                status=payload.status,
                repositories=payload.repositories,
                modules=payload.modules,
                features=payload.features,
                responsibilities=payload.responsibilities,
                scope=payload.scope,
                permission_policies=payload.permissionPolicies or payload.permission_policies,
                memory_bindings=payload.memoryBindings or payload.memory_bindings,
                active_from=payload.activeFrom or payload.active_from,
                active_to=payload.activeTo or payload.active_to,
            )
            return manifest_to_record(assignment)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def patch_assignment(assignment_id: str, payload: AssignmentUpdateInput) -> dict[str, Any]:
        updates = _camel_updates(payload)
        try:
            return manifest_to_record(update_assignment(app.state.workspace_path, assignment_id, updates))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_task(task_id: str) -> dict[str, Any]:
        current = index()
        if task_id not in current.tasks:
            raise HTTPException(status_code=404, detail=f"unknown task {task_id}")
        return manifest_to_record(current.tasks[task_id])

    def get_task_plan(task_plan_id: str) -> dict[str, Any]:
        current = index()
        if task_plan_id not in current.task_plans:
            raise HTTPException(status_code=404, detail=f"unknown task plan {task_plan_id}")
        return manifest_to_record(current.task_plans[task_plan_id])

    def get_task_plan_execution_views() -> dict[str, Any]:
        return task_plan_execution_view_records(index())

    def get_task_plan_execution_view(task_plan_id: str) -> dict[str, Any]:
        try:
            return task_plan_execution_view(index(), task_plan_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def post_task_plan_retrospective(task_plan_id: str, payload: TaskPlanRetrospectiveInput) -> dict[str, Any]:
        try:
            result = create_task_plan_retrospective(
                app.state.workspace_path,
                task_plan_id,
                facilitator_member=payload.facilitatorMember or payload.facilitator_member or "",
                participants=payload.participants,
                summary=payload.summary,
                lessons=payload.lessons,
                action_items=payload.actionItems or payload.action_items,
                memory_kind=payload.memoryKind or payload.memory_kind or "procedural",
                confidence=payload.confidence,
                review_guidance=payload.reviewGuidance or payload.review_guidance,
                source="api",
            )
            return {key: manifest_to_record(value) for key, value in result.items()}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_run_events(run_id: str) -> list[dict[str, Any]]:
        current = index()
        if run_id not in current.runs:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
        return current.run_events.get(run_id, [])

    def get_run_context_manifest(run_id: str) -> dict[str, Any]:
        current = index()
        if run_id not in current.runs:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
        return current.run_context_manifests.get(run_id, {})

    def get_run_context_preview(run_id: str) -> dict[str, Any]:
        current = index()
        if run_id not in current.runs:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
        run = current.runs[run_id]
        result = build_context_capsule(
            current,
            run_id=run_id,
            task_id=run.spec.task,
            member_id=run.spec.member,
            assignment_id=run.spec.assignment,
            model_profile=run.spec.modelProfile,
            branch_name=run.spec.branch.name if run.spec.branch else None,
        )
        return {"run": run_id, "capsule": result.capsule, "manifest": result.manifest}

    def get_run_assistance_package(run_id: str) -> RunAssistancePackageRecord:
        try:
            return build_run_assistance_package(index(), run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_run_assistance_bundle(run_id: str) -> RunAssistanceBundleRecord:
        try:
            return build_run_assistance_bundle(index(), run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_run_assistance_bundle_archive(run_id: str) -> Response:
        try:
            filename, archive = build_run_assistance_bundle_archive(index(), run_id)
            return Response(
                content=archive,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def tool_get_task(task_id: str) -> dict[str, Any]:
        return _tool_response(lambda: get_task_for_tool(index(), task_id))

    def tool_get_context_capsule(run_id: str) -> dict[str, Any]:
        return _tool_response(lambda: get_context_capsule_for_tool(index(), run_id))

    def tool_search_docs(
        query: str = "",
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        return _tool_response(
            lambda: search_docs_for_tool(
                index(),
                query,
                project=project,
                member=member,
                assignment=assignment,
                limit=limit,
            )
        )

    def tool_search_memory(
        request: Request,
        query: str = "",
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        store: str | None = None,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        viewer = governed_viewer_member(request, viewerMember or viewer_member)
        return _tool_response(
            lambda: search_memory_for_tool(
                index(),
                query,
                project=project,
                member=member,
                assignment=assignment,
                store=store,
                limit=limit,
                viewer_member=viewer,
                apply_governance=True,
            )
        )

    def tool_get_member(member_id: str) -> dict[str, Any]:
        return {"tool": "get_member", "member": get_member(member_id)}

    def tool_get_project(project_id: str) -> dict[str, Any]:
        return {"tool": "get_project", "project": get_project(project_id)}

    def tool_list_project_members(project_id: str) -> dict[str, Any]:
        return {"tool": "list_project_members", "project": project_id, "members": project_members(project_id)}

    def tool_list_member_projects(member_id: str) -> dict[str, Any]:
        return {"tool": "list_member_projects", "member": member_id, "projects": member_projects(member_id)}

    def list_assignments(member: str | None = None, project: str | None = None) -> list[dict[str, Any]]:
        current = index()
        selected_project = project or current.project.object_id
        if selected_project != current.project.object_id:
            raise HTTPException(status_code=404, detail=f"unknown project {selected_project}")
        if member and member not in current.members:
            raise HTTPException(status_code=404, detail=f"unknown member {member}")
        return records(
            assignment
            for assignment in current.assignments.values()
            if assignment.spec.project == selected_project and (member is None or assignment.spec.member == member)
        )

    def tool_list_assignments(member: str | None = None, project: str | None = None) -> dict[str, Any]:
        return {"tool": "list_assignments", "member": member, "project": project or index().project.object_id, "assignments": list_assignments(member=member, project=project)}

    def tool_explain_permissions(
        member: str | None = None,
        project: str | None = None,
        assignment: str | None = None,
        action: dict[str, Any] | None = None,
        nonInteractive: bool | None = None,
        non_interactive: bool | None = None,
    ) -> dict[str, Any]:
        return {
            "tool": "explain_permissions",
            **effective_permissions(
                member=member,
                project=project,
                assignment=assignment,
                action=action,
                nonInteractive=nonInteractive,
                non_interactive=non_interactive,
            ),
        }

    def member_memory(
        request: Request,
        member_id: str,
        query: str = "",
        project: str | None = None,
        assignment: str | None = None,
        store: str | None = None,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        return tool_search_memory(
            request,
            query=query,
            project=project,
            member=member_id,
            assignment=assignment,
            store=store,
            viewerMember=viewerMember,
            viewer_member=viewer_member,
            limit=limit,
        )

    def project_memory(
        request: Request,
        project_id: str,
        query: str = "",
        member: str | None = None,
        assignment: str | None = None,
        store: str | None = None,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        return tool_search_memory(
            request,
            query=query,
            project=project_id,
            member=member,
            assignment=assignment,
            store=store,
            viewerMember=viewerMember,
            viewer_member=viewer_member,
            limit=limit,
        )

    def tool_get_member_memory(
        request: Request,
        member_id: str = "",
        memberId: str | None = None,
        query: str = "",
        project: str | None = None,
        assignment: str | None = None,
        store: str | None = None,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        selected_member = memberId or member_id
        result = member_memory(
            request,
            selected_member,
            query=query,
            project=project,
            assignment=assignment,
            store=store,
            viewerMember=viewerMember,
            viewer_member=viewer_member,
            limit=limit,
        )
        result["tool"] = "get_member_memory"
        return result

    def tool_get_project_memory(
        request: Request,
        project_id: str = "",
        projectId: str | None = None,
        query: str = "",
        member: str | None = None,
        assignment: str | None = None,
        store: str | None = None,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        selected_project = projectId or project_id
        result = project_memory(
            request,
            selected_project,
            query=query,
            member=member,
            assignment=assignment,
            store=store,
            viewerMember=viewerMember,
            viewer_member=viewer_member,
            limit=limit,
        )
        result["tool"] = "get_project_memory"
        return result

    def post_automation(payload: AutomationCreateInput) -> dict[str, Any]:
        try:
            triggers = [trigger.model_dump(mode="json", exclude_none=True) for trigger in payload.triggers] if payload.triggers else None
            automation = create_automation(
                app.state.workspace_path,
                name=payload.name,
                target_type=payload.targetType or payload.target_type or "",
                target=payload.target,
                owner_member=payload.ownerMember or payload.owner_member,
                service_member=payload.serviceMember or payload.service_member,
                project=payload.project,
                triggers=triggers,
                dry_run=bool(payload.dryRun if payload.dryRun is not None else (payload.dry_run if payload.dry_run is not None else True)),
                status=payload.status,
                permission_policies=payload.permissionPolicies or payload.permission_policies,
                approval_gates=payload.approvalGates or payload.approval_gates,
            )
            return manifest_to_record(automation)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=exc.errors()) from exc

    def post_memory_store(payload: MemoryStoreCreateInput) -> dict[str, Any]:
        try:
            result = create_memory_store(
                app.state.workspace_path,
                name=payload.name,
                actor_member=payload.actorMember,
                store_type=payload.storeType,
                owner_project=payload.ownerProject,
                owner_member=payload.ownerMember,
                owner_team=payload.ownerTeam,
                domain=payload.domain,
                description=payload.description,
                visibility=payload.visibility,
                lifecycle=payload.lifecycle,
                acl=payload.acl.model_dump(mode="json", exclude_none=True),
                retention=payload.retention,
                reason=payload.reason,
            )
            return {
                "store": manifest_to_record(result["store"]),
                "decisionAudit": result["decisionAudit"],
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_memory_entry(payload: MemoryEntryCreateInput) -> dict[str, Any]:
        try:
            result = create_memory_entry(
                app.state.workspace_path,
                title=payload.title,
                content=payload.content,
                actor_member=payload.actorMember,
                store=payload.store,
                path=payload.path,
                kind=payload.kind,
                scope=payload.scope,
                source=payload.source,
                evidence=payload.evidence,
                confidence=payload.confidence,
                freshness=payload.freshness,
                sensitivity=payload.sensitivity,
                visibility=payload.visibility,
                acl=payload.acl.model_dump(mode="json", exclude_none=True),
                tags=payload.tags,
                related_projects=payload.relatedProjects,
                related_members=payload.relatedMembers,
                related_assignments=payload.relatedAssignments,
                lifecycle=payload.lifecycle,
                reason=payload.reason,
                bind_target_type=payload.bindTargetType,
                bind_target_id=payload.bindTargetId,
                bind_access=payload.bindAccess,
                bind_reason=payload.bindReason,
            )
            binding = result.get("binding")
            return {
                "memory": manifest_to_record(result["memory"]),
                "versions": [manifest_to_record(result["version"])],
                "bindings": [manifest_to_record(binding)] if binding else [],
                "decisionAudit": result["decisionAudit"],
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_memory_binding(payload: MemoryBindingCreateInput) -> dict[str, Any]:
        try:
            binding = create_memory_binding(
                app.state.workspace_path,
                name=payload.name,
                target_type=payload.targetType or payload.target_type or "",
                target_id=payload.targetId or payload.target_id or "",
                store=payload.store,
                entry=payload.entry,
                collection_path=payload.collectionPath or payload.collection_path,
                access=payload.access,
                reason=payload.reason,
                created_by_member=payload.createdByMember or payload.created_by_member,
            )
            return manifest_to_record(binding)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def delete_memory_binding(binding_id: str) -> dict[str, Any]:
        try:
            return manifest_to_record(archive_memory_binding(app.state.workspace_path, binding_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def post_memory_grant(payload: MemoryGrantCreateInput) -> dict[str, Any]:
        try:
            grant = create_memory_grant(
                app.state.workspace_path,
                name=payload.name,
                grantee_member=payload.granteeMember or payload.grantee_member or payload.member or "",
                grantor_member=payload.grantorMember or payload.grantor_member,
                task=payload.task,
                run=payload.runId or payload.run_id,
                stores=payload.stores,
                entries=payload.entries,
                access=payload.access,
                reason=payload.reason,
                expires_at=payload.expiresAt or payload.expires_at,
            )
            return manifest_to_record(grant)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_memory_share(payload: MemoryShareInput) -> dict[str, Any]:
        try:
            result = share_memory(
                app.state.workspace_path,
                from_member=payload.fromMember or payload.from_member or "",
                to_member=payload.toMember or payload.to_member or "",
                stores=payload.stores,
                entries=payload.entries,
                task=payload.task,
                run=payload.runId or payload.run_id,
                reason=payload.reason,
                expires_at=payload.expiresAt or payload.expires_at,
            )
            return {
                "grant": manifest_to_record(result["grant"]),
                "message": manifest_to_record(result["message"]),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def patch_memory_proposal(proposal_id: str, payload: MemoryProposalUpdateInput) -> dict[str, Any]:
        try:
            return update_memory_proposal(app.state.workspace_path, proposal_id, _camel_updates(payload))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_memory_proposal_repair(proposal_id: str, payload: MemoryProposalReviewInput | None = None) -> dict[str, Any]:
        _ = payload
        try:
            return repair_memory_proposal(app.state.workspace_path, proposal_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_memory_proposal_approve(proposal_id: str, payload: MemoryProposalReviewInput | None = None) -> dict[str, Any]:
        body = payload or MemoryProposalReviewInput()
        try:
            proposal = approve_memory_proposal(
                app.state.workspace_path,
                proposal_id,
                reviewer_member=body.reviewerMember or body.reviewer_member,
                reason=body.reason,
            )
            current = index()
            memory_id = str(proposal.get("spec", {}).get("approvedMemory") or "")
            memory = current.memory_entries.get(memory_id)
            return {
                "proposal": proposal,
                "memory": manifest_to_record(memory) if memory else None,
                "versions": records(
                    version
                    for version in current.memory_versions.values()
                    if version.spec.entry == memory_id
                ),
                "bindings": records(
                    binding
                    for binding in current.memory_bindings.values()
                    if binding.spec.entry == memory_id
                ),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_memory_proposal_reject(proposal_id: str, payload: MemoryProposalReviewInput | None = None) -> dict[str, Any]:
        body = payload or MemoryProposalReviewInput()
        try:
            return reject_memory_proposal(
                app.state.workspace_path,
                proposal_id,
                reviewer_member=body.reviewerMember or body.reviewer_member,
                reason=body.reason,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def patch_memory_entry(memory_id: str, payload: MemoryEntryUpdateInput) -> dict[str, Any]:
        try:
            return update_memory_entry(app.state.workspace_path, memory_id, _camel_updates(payload))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_memory_entry_stale(memory_id: str, payload: MemoryEntryLifecycleInput | None = None) -> dict[str, Any]:
        body = payload or MemoryEntryLifecycleInput()
        try:
            return mark_memory_entry_stale(app.state.workspace_path, memory_id, body.reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_memory_entry_verify(memory_id: str, payload: MemoryEntryLifecycleInput | None = None) -> dict[str, Any]:
        body = payload or MemoryEntryLifecycleInput()
        try:
            return verify_memory_entry(app.state.workspace_path, memory_id, body.reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_knowledge_health_remediation(payload: KnowledgeHealthRemediationInput) -> dict[str, Any]:
        try:
            return remediate_memory_health_issue(
                app.state.workspace_path,
                issue_kind=payload.issueKind,
                ref=payload.ref,
                action=payload.action,
                actor_member=payload.actorMember,
                reason=payload.reason,
                dry_run=payload.dryRun,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _recipients(to_members: list[str] | None = None, to_member: str | None = None) -> list[str]:
        values = list(to_members or [])
        if to_member:
            values.append(to_member)
        return sorted(set(item for item in values if item))

    def get_collaboration_overview(
        member: str | None = None,
        project: str | None = None,
        task: str | None = None,
        messageType: str | None = None,
        message_type: str | None = None,
    ) -> dict[str, Any]:
        try:
            return collaboration_overview(
                index(),
                member=member,
                project=project,
                task=task,
                message_type=messageType or message_type,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_retrospective_suggestions(
        member: str | None = None,
        project: str | None = None,
        task: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        try:
            return retrospective_suggestions(index(), member=member, project=project, task=task, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_ask_for_help(payload: AskForHelpInput) -> dict[str, Any]:
        try:
            message = ask_for_help(
                app.state.workspace_path,
                from_member=payload.fromMember or payload.from_member or "",
                to_members=_recipients(payload.toMembers or payload.to_members, payload.toMember or payload.to_member),
                question=payload.question or payload.body or "",
                project=payload.project,
                task=payload.task,
                run=payload.runId or payload.run_id,
                priority=payload.priority,
                requested_response_by=payload.requestedResponseBy or payload.requested_response_by,
                attachments=payload.attachments,
                source="api",
            )
            return manifest_to_record(message)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_review_request(payload: ReviewRequestInput) -> dict[str, Any]:
        try:
            message = request_review(
                app.state.workspace_path,
                from_member=payload.fromMember or payload.from_member or "",
                to_members=_recipients(payload.toMembers or payload.to_members, payload.toMember or payload.to_member),
                body=payload.body,
                review_kind=payload.reviewKind or payload.review_kind or "code",
                project=payload.project,
                task=payload.task,
                run=payload.runId or payload.run_id,
                priority=payload.priority,
                requested_response_by=payload.requestedResponseBy or payload.requested_response_by,
                attachments=payload.attachments,
                source="api",
            )
            return manifest_to_record(message)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_member_message_resolve(message_id: str, payload: MemberMessageResolveInput) -> dict[str, Any]:
        actor = payload.actorMember or payload.actor_member
        if not actor:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            message = resolve_member_message(
                app.state.workspace_path,
                message_id,
                actor_member=actor,
                resolution=payload.resolution,
                status=payload.status,
            )
            return manifest_to_record(message)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _create_retrospective_from_payload(payload: TeamRetrospectiveInput, *, source: str) -> dict[str, Any]:
        result = create_team_retrospective(
            app.state.workspace_path,
            facilitator_member=payload.facilitatorMember or payload.facilitator_member or "",
            participants=payload.participants,
            project=payload.project,
            source_task_plan=payload.sourceTaskPlan or payload.source_task_plan,
            source_runs=payload.sourceRuns or payload.source_runs,
            source_tasks=payload.sourceTasks or payload.source_tasks,
            source_messages=payload.sourceMessages or payload.source_messages,
            source_handoffs=payload.sourceHandoffs or payload.source_handoffs,
            summary=payload.summary,
            lessons=payload.lessons,
            action_items=payload.actionItems or payload.action_items,
            memory_kind=payload.memoryKind or payload.memory_kind or "procedural",
            confidence=payload.confidence,
            review_guidance=payload.reviewGuidance or payload.review_guidance,
            source=source,
        )
        return {key: manifest_to_record(value) for key, value in result.items()}

    def post_team_retrospective(payload: TeamRetrospectiveInput) -> dict[str, Any]:
        try:
            return _create_retrospective_from_payload(payload, source="api")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_run_model_readiness(run_id: str) -> dict[str, Any]:
        current = index()
        if run_id not in current.runs:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
        return evaluate_model_execution_readiness(current, run_id)

    def get_run_model_policy(run_id: str) -> dict[str, Any]:
        current = index()
        if run_id not in current.runs:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
        return evaluate_model_policy(current, run_id)

    def get_run_worker_readiness(run_id: str) -> dict[str, Any]:
        current = index()
        if run_id not in current.runs:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
        return evaluate_worker_readiness(current, run_id)

    def get_run_worker_authorization(run_id: str) -> dict[str, Any]:
        current = index()
        if run_id not in current.runs:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
        return evaluate_worker_authorization(current, run_id)

    def post_run_model_execute(run_id: str) -> dict[str, Any]:
        try:
            execute_run_with_model(app.state.workspace_path, run_id)
            return run_record(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_run_worker_start(run_id: str, payload: RunWorkerStartInput | None = None) -> dict[str, Any]:
        body = payload or RunWorkerStartInput()
        try:
            execute_worker_run(
                app.state.workspace_path,
                run_id,
                create_pr=bool(body.createPr if body.createPr is not None else body.create_pr),
            )
            return run_record(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (RuntimeError, ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_run_assisted_ingest(run_id: str, payload: RunAssistedIngestInput) -> dict[str, Any]:
        try:
            ingest_run_outputs(
                app.state.workspace_path,
                run_id,
                journal=payload.journal,
                diff_patch=payload.diffPatch,
                test_log=payload.testLog,
                review_target=payload.reviewTarget.model_dump(mode="json", exclude_none=True) if payload.reviewTarget else None,
                memory_proposal=payload.memoryProposal.model_dump(mode="json", exclude_none=True) if payload.memoryProposal else None,
            )
            return run_record(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_run_review(run_id: str, payload: RunReviewInput) -> dict[str, Any]:
        reviewer_member = payload.reviewerMember or payload.reviewer_member
        reviewer = payload.reviewer or reviewer_member
        if not reviewer:
            raise HTTPException(status_code=400, detail="reviewerMember or reviewer is required")
        findings: list[dict[str, Any]] = []
        if payload.summary and payload.summary.strip():
            findings.append({"id": "summary", "severity": "info", "summary": payload.summary.strip()})
        for index, finding in enumerate(payload.findings, start=1):
            summary = finding.summary.strip()
            if not summary:
                continue
            findings.append(
                {
                    "id": f"finding-{index}",
                    "severity": finding.severity or "medium",
                    "summary": summary,
                    **({"action": finding.action} if finding.action else {}),
                }
            )
        try:
            review = create_review(
                app.state.workspace_path,
                run_id=run_id,
                reviewer=reviewer,
                reviewer_member=reviewer_member,
                verdict=payload.verdict,
                source=payload.source,
                findings=findings,
                target=payload.target.model_dump(mode="json", exclude_none=True) if payload.target else None,
            )
            return manifest_to_record(review)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_run_review_gate(run_id: str) -> RunReviewGateRecord:
        try:
            return RunReviewGateRecord.model_validate(evaluate_run_review_gate(index(), run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def post_run_review_checks_refresh(run_id: str) -> RunReviewTargetCheckRecord:
        try:
            return RunReviewTargetCheckRecord.model_validate(refresh_run_checks(app.state.workspace_path, run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (RuntimeError, ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_run_closeout_gate(run_id: str, actorMember: str | None = None, actor_member: str | None = None) -> dict[str, Any]:
        try:
            return evaluate_run_closeout_gate(index(), run_id, actor_member=actorMember or actor_member)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_run_closeout(run_id: str, payload: RunCloseoutInput) -> dict[str, Any]:
        actor_member = payload.actorMember or payload.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            close_run_after_review(
                app.state.workspace_path,
                run_id,
                actor=actor_member,
                reason=payload.reason,
            )
            return run_record(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PermissionError, ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_run_source_integration_gate(run_id: str, actorMember: str | None = None, actor_member: str | None = None) -> dict[str, Any]:
        try:
            return evaluate_run_source_integration_gate(index(), run_id, actor_member=actorMember or actor_member)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_run_source_integration(run_id: str, payload: RunSourceIntegrationInput) -> dict[str, Any]:
        actor_member = payload.actorMember or payload.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            integrate_run_source_after_closeout(
                app.state.workspace_path,
                run_id,
                actor=actor_member,
                reason=payload.reason,
            )
            return run_record(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PermissionError, ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_run_source_integration_remediation(run_id: str, payload: RunSourceIntegrationRemediationInput) -> dict[str, Any]:
        actor_member = payload.actorMember or payload.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            request_run_source_integration_remediation(
                app.state.workspace_path,
                run_id,
                actor=actor_member,
                reason=payload.reason,
            )
            return run_record(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PermissionError, ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_run_provider_source_integration(run_id: str, payload: RunProviderSourceIntegrationInput) -> dict[str, Any]:
        actor_member = payload.actorMember or payload.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            request_run_provider_source_integration(
                app.state.workspace_path,
                run_id,
                actor=actor_member,
                reason=payload.reason,
            )
            return run_record(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PermissionError, ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_run_provider_source_integration_execute(run_id: str, payload: RunProviderSourceIntegrationExecuteInput) -> dict[str, Any]:
        actor_member = payload.actorMember or payload.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        dry_run = payload.dryRun if payload.dry_run is None else payload.dry_run
        try:
            execute_run_provider_source_integration(
                app.state.workspace_path,
                run_id,
                actor=actor_member,
                reason=payload.reason,
                dry_run=dry_run,
            )
            return run_record(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PermissionError, ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_run_worker_permission_request(run_id: str, payload: ControlPlanePermissionRequestInput | None = None) -> dict[str, Any]:
        body = payload or ControlPlanePermissionRequestInput()
        actor = body.actorMember or body.actor_member
        if not actor:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            return request_run_worker_permission(
                app.state.workspace_path,
                run_id,
                actor_member=actor,
                action_canonical=body.actionCanonical or body.action_canonical,
                action_index=body.actionIndex if body.actionIndex is not None else body.action_index,
                reason=body.reason,
                expires_at=body.expiresAt or body.expires_at,
                dry_run=True if body.dryRun is None and body.dry_run is None else bool(body.dryRun if body.dryRun is not None else body.dry_run),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_model_profile_readiness(profile_id: str) -> dict[str, Any]:
        current = index()
        if profile_id not in current.model_profiles:
            raise HTTPException(status_code=404, detail=f"unknown model profile {profile_id}")
        return evaluate_model_profile_readiness(current, profile_id)

    def get_review(review_id: str) -> dict[str, Any]:
        current = index()
        if review_id not in current.reviews:
            raise HTTPException(status_code=404, detail=f"unknown review {review_id}")
        return manifest_to_record(current.reviews[review_id])

    def get_memory_stores(
        request: Request,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        return governed_memory_store_records(index(), viewer_member=governed_viewer_member(request, viewerMember or viewer_member))

    def get_memory_entries(
        request: Request,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        return governed_memory_entry_records(index(), viewer_member=governed_viewer_member(request, viewerMember or viewer_member))

    def get_memory_bindings(
        request: Request,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        return governed_memory_binding_records(index(), viewer_member=governed_viewer_member(request, viewerMember or viewer_member))

    def get_memory_grants(
        request: Request,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        return governed_memory_grant_records(index(), viewer_member=governed_viewer_member(request, viewerMember or viewer_member))

    def get_memory_proposals(
        request: Request,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        return governed_memory_proposal_records(index(), viewer_member=governed_viewer_member(request, viewerMember or viewer_member))

    def effective_permissions(
        member: str | None = None,
        project: str | None = None,
        assignment: str | None = None,
        tool: str | None = None,
        value: str | None = None,
        path: str | None = None,
        command: str | None = None,
        url: str | None = None,
        domain: str | None = None,
        port: int | None = None,
        protocol: str | None = None,
        envVar: str | None = None,
        env_var: str | None = None,
        connector: str | None = None,
        connectorType: str | None = None,
        connector_type: str | None = None,
        connectorScope: str | None = None,
        connector_scope: str | None = None,
        artifactStore: str | None = None,
        artifact_store: str | None = None,
        artifactKind: str | None = None,
        artifact_kind: str | None = None,
        operation: str | None = None,
        retentionPolicy: str | None = None,
        retention_policy: str | None = None,
        exportPolicy: str | None = None,
        export_policy: str | None = None,
        redactionMode: str | None = None,
        redaction_mode: str | None = None,
        sensitivity: str | None = None,
        mcpTool: str | None = None,
        action: dict[str, Any] | None = None,
        nonInteractive: bool | None = None,
        non_interactive: bool | None = None,
    ) -> dict[str, Any]:
        current = index()
        selected_action = action
        action_inputs = {
            "tool": tool,
            "value": value,
            "path": path,
            "command": command,
            "url": url,
            "domain": domain,
            "port": port,
            "protocol": protocol,
            "envVar": envVar or env_var,
            "connector": connector,
            "connectorType": connectorType or connector_type,
            "connectorScope": connectorScope or connector_scope,
            "artifactStore": artifactStore or artifact_store,
            "artifactKind": artifactKind or artifact_kind,
            "operation": operation,
            "retentionPolicy": retentionPolicy or retention_policy,
            "exportPolicy": exportPolicy or export_policy,
            "redactionMode": redactionMode or redaction_mode,
            "sensitivity": sensitivity,
            "mcpTool": mcpTool,
        }
        if selected_action is None and any(item is not None for item in action_inputs.values()):
            selected_action = {
                key: item
                for key, item in action_inputs.items()
                if item is not None
            }
        try:
            return explain_effective_permissions(
                current,
                member=member,
                project=project,
                assignment=assignment,
                action=selected_action,
                non_interactive=bool(nonInteractive if nonInteractive is not None else non_interactive),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_permissions_explain(payload: PermissionExplainInput) -> dict[str, Any]:
        return effective_permissions(
            member=payload.member,
            project=payload.project,
            assignment=payload.assignment,
            action=payload.action,
            nonInteractive=payload.nonInteractive,
            non_interactive=payload.non_interactive,
        )

    def post_permission_request(payload: PermissionRequestCreateInput) -> dict[str, Any]:
        try:
            current_decision = explain_effective_permissions(
                index(),
                member=payload.member,
                project=payload.project,
                assignment=payload.assignment,
                action=payload.action,
                non_interactive=True,
            )
            request = create_permission_request(
                app.state.workspace_path,
                member=payload.member,
                action=payload.action,
                project=payload.project,
                assignment=payload.assignment,
                task=payload.task,
                run=payload.run,
                automation=payload.automation,
                automation_run=payload.automationRun or payload.automation_run,
                requester_member=payload.requesterMember or payload.requester_member,
                reason=payload.reason,
                expires_at=payload.expiresAt or payload.expires_at,
                current_decision=current_decision,
                source=payload.source or "api",
                name=payload.name,
            )
            return manifest_to_record(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_permission_request_approve(request_id: str, payload: PermissionRequestReviewInput) -> dict[str, Any]:
        reviewer = payload.reviewerMember or payload.reviewer_member
        if not reviewer:
            raise HTTPException(status_code=400, detail="reviewerMember is required")
        try:
            result = approve_permission_request(
                app.state.workspace_path,
                request_id,
                reviewer_member=reviewer,
                reason=payload.reason,
                expires_at=payload.expiresAt or payload.expires_at,
            )
            return {key: manifest_to_record(value) for key, value in result.items()}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_permission_request_reject(request_id: str, payload: PermissionRequestReviewInput) -> dict[str, Any]:
        reviewer = payload.reviewerMember or payload.reviewer_member
        if not reviewer:
            raise HTTPException(status_code=400, detail="reviewerMember is required")
        try:
            request = reject_permission_request(
                app.state.workspace_path,
                request_id,
                reviewer_member=reviewer,
                reason=payload.reason,
            )
            return manifest_to_record(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_permission_grant_revoke(grant_id: str, payload: PermissionGrantRevokeInput) -> dict[str, Any]:
        try:
            grant = revoke_permission_grant(
                app.state.workspace_path,
                grant_id,
                actor_member=payload.actorMember or payload.actor_member,
                reason=payload.reason,
            )
            return manifest_to_record(grant)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_permission_grants_expire() -> dict[str, Any]:
        return expire_permission_grants(app.state.workspace_path)

    def get_permissions(
        request: Request,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return permission_policy_records(index(), viewer_member=governed_viewer_member(request, viewerMember or viewer_member))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def get_permission_requests(
        request: Request,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return permission_request_records(index(), viewer_member=governed_viewer_member(request, viewerMember or viewer_member))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def get_permission_grants(
        request: Request,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return permission_grant_records(index(), viewer_member=governed_viewer_member(request, viewerMember or viewer_member))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def get_permissions_overview(
        request: Request,
        member: str | None = None,
        project: str | None = None,
        assignment: str | None = None,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> dict[str, Any]:
        try:
            return permission_governance_overview(
                index(),
                member=member,
                project=project,
                assignment=assignment,
                viewer_member=governed_viewer_member(request, viewerMember or viewer_member),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_project_permissions(
        request: Request,
        project_id: str,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> dict[str, Any]:
        try:
            return permission_governance_overview(
                index(),
                project=project_id,
                viewer_member=governed_viewer_member(request, viewerMember or viewer_member),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_member_permissions(
        request: Request,
        member_id: str,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> dict[str, Any]:
        try:
            return permission_governance_overview(
                index(),
                member=member_id,
                viewer_member=governed_viewer_member(request, viewerMember or viewer_member),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_assignment_permissions(
        request: Request,
        assignment_id: str,
        viewerMember: str | None = None,
        viewer_member: str | None = None,
    ) -> dict[str, Any]:
        try:
            return permission_governance_overview(
                index(),
                assignment=assignment_id,
                viewer_member=governed_viewer_member(request, viewerMember or viewer_member),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_automation_runs(automation_id: str | None = None) -> list[dict[str, Any]]:
        current = index()
        if automation_id is not None and automation_id not in current.automations:
            raise HTTPException(status_code=404, detail=f"unknown automation {automation_id}")
        return automation_run_records(current, automation_id=automation_id)

    def get_automation_approvals(run_id: str | None = None) -> list[dict[str, Any]]:
        current = index()
        if run_id is not None and run_id not in current.automation_runs:
            raise HTTPException(status_code=404, detail=f"unknown automation run {run_id}")
        return automation_approval_records(current, automation_run_id=run_id)

    def get_automation_events(automation_id: str | None = None) -> list[dict[str, Any]]:
        current = index()
        if automation_id is not None and automation_id not in current.automations:
            raise HTTPException(status_code=404, detail=f"unknown automation {automation_id}")
        return automation_trigger_event_records(current, automation_id=automation_id)

    def get_automation_provider_deliveries(automation_id: str | None = None) -> list[dict[str, Any]]:
        current = index()
        if automation_id is not None and automation_id not in current.automations:
            raise HTTPException(status_code=404, detail=f"unknown automation {automation_id}")
        return automation_provider_delivery_records(current, automation_id=automation_id)

    def post_automation_provider_deliveries_cleanup(payload: RetentionCleanupInput | None = None) -> dict[str, Any]:
        body = payload or RetentionCleanupInput()
        try:
            return cleanup_automation_provider_deliveries(
                app.state.workspace_path,
                actor_member=body.actorMember or body.actor_member,
                max_age_days=body.maxAgeDays if body.maxAgeDays is not None else (body.max_age_days if body.max_age_days is not None else 30),
                dry_run=bool(body.dryRun if body.dryRun is not None else body.dry_run),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_automation_provider_delivery_retry(
        delivery_id: str,
        payload: AutomationProviderDeliveryRetryInput | None = None,
    ) -> dict[str, Any]:
        body = payload or AutomationProviderDeliveryRetryInput()
        actor_member = body.actorMember or body.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            result = retry_provider_delivery(
                app.state.workspace_path,
                delivery_id,
                actor_member=actor_member,
                reason=body.reason,
                headers=body.headers,
                payload=body.payload,
                raw_body=body.rawBody or body.raw_body,
                received_at=body.receivedAt or body.received_at,
                dry_run=bool(body.dryRun if body.dryRun is not None else body.dry_run),
            )
            return {
                "delivery": manifest_to_record(result["delivery"]) if result.get("delivery") is not None else None,
                "retryDelivery": manifest_to_record(result["retryDelivery"]) if result.get("retryDelivery") is not None else None,
                "event": manifest_to_record(result["event"]) if result.get("event") is not None else None,
                "run": manifest_to_record(result["run"]) if result.get("run") is not None else None,
                "admitted": bool(result.get("admitted")),
                "requested": bool(result.get("requested")),
                "blockers": result.get("blockers") or [],
                "warnings": result.get("warnings") or [],
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_automation_scheduler_leases(automation_id: str | None = None) -> list[dict[str, Any]]:
        current = index()
        if automation_id is not None and automation_id not in current.automations:
            raise HTTPException(status_code=404, detail=f"unknown automation {automation_id}")
        return automation_scheduler_lease_records(current, automation_id=automation_id)

    def post_automation_scheduler_lease_recover(
        lease_id: str,
        payload: AutomationSchedulerLeaseRecoverInput | None = None,
    ) -> dict[str, Any]:
        body = payload or AutomationSchedulerLeaseRecoverInput()
        actor_member = body.actorMember or body.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            result = recover_scheduler_lease(
                app.state.workspace_path,
                lease_id,
                actor_member=actor_member,
                lease_seconds=body.leaseSeconds or body.lease_seconds or 60,
                dry_run=bool(body.dryRun if body.dryRun is not None else body.dry_run),
                reason=body.reason,
            )
            return _scheduler_result_record(result)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_connector_health(connector_id: str | None = None) -> list[dict[str, Any]]:
        current = index()
        if connector_id is not None and connector_id not in current.connectors:
            raise HTTPException(status_code=404, detail=f"unknown connector {connector_id}")
        return connector_health_records(current, connector=connector_id)

    def get_connector_operations(
        connector: str | None = None,
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        lifecycle: str | None = None,
    ) -> dict[str, Any]:
        try:
            return connector_operations_overview(index(), connector=connector, project=project, member=member, assignment=assignment, lifecycle=lifecycle)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_connector_failure_reminders(
        connector: str | None = None,
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        lifecycle: str | None = "active",
    ) -> dict[str, Any]:
        try:
            return connector_failure_reminder_candidates(
                index(),
                connector=connector,
                project=project,
                member=member,
                assignment=assignment,
                lifecycle=lifecycle,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_connector_failure_escalations(
        connector: str | None = None,
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        lifecycle: str | None = "active",
        minEvidence: int = 2,
    ) -> dict[str, Any]:
        try:
            return connector_failure_escalation_candidates(
                index(),
                connector=connector,
                project=project,
                member=member,
                assignment=assignment,
                lifecycle=lifecycle,
                min_evidence=minEvidence,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_connector_remediation_suggestions(
        connector: str | None = None,
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        lifecycle: str | None = "active",
        minEvidence: int = 2,
    ) -> dict[str, Any]:
        try:
            return connector_remediation_suggestions(
                index(),
                connector=connector,
                project=project,
                member=member,
                assignment=assignment,
                lifecycle=lifecycle,
                min_evidence=minEvidence,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_connector_remediation_task_plans(
        connector: str | None = None,
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        try:
            return connector_remediation_task_plan_records(
                index(),
                connector=connector,
                project=project,
                member=member,
                assignment=assignment,
                status=status,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_connector_remediation_tasks(
        connector: str | None = None,
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        status: str | None = None,
        taskPlan: str | None = None,
    ) -> dict[str, Any]:
        try:
            return connector_remediation_materialized_task_records(
                index(),
                connector=connector,
                project=project,
                member=member,
                assignment=assignment,
                status=status,
                task_plan=taskPlan,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def get_connector_remediation_runs(
        connector: str | None = None,
        project: str | None = None,
        member: str | None = None,
        assignment: str | None = None,
        status: str | None = None,
        taskPlan: str | None = None,
        task: str | None = None,
    ) -> dict[str, Any]:
        try:
            return connector_remediation_run_records(
                index(),
                connector=connector,
                project=project,
                member=member,
                assignment=assignment,
                status=status,
                task_plan=taskPlan,
                task=task,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_connector_remediation_run_permission_request(run_id: str, payload: ConnectorRemediationRunPermissionRequestInput | None = None) -> dict[str, Any]:
        body = payload or ConnectorRemediationRunPermissionRequestInput()
        actor_member = body.actorMember or body.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            return request_connector_remediation_run_permission(
                app.state.workspace_path,
                run_id,
                actor_member=actor_member,
                action_canonical=body.actionCanonical or body.action_canonical,
                action_index=body.actionIndex if body.actionIndex is not None else body.action_index,
                reason=body.reason,
                expires_at=body.expiresAt or body.expires_at,
                dry_run=bool(body.dryRun if body.dryRun is not None else (body.dry_run if body.dry_run is not None else True)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_connector_failure_escalations(payload: ConnectorFailureEscalationInput | None = None) -> dict[str, Any]:
        body = payload or ConnectorFailureEscalationInput()
        actor_member = body.actorMember or body.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            return route_connector_failure_escalations(
                app.state.workspace_path,
                actor_member=actor_member,
                connector=body.connector,
                project=body.project,
                member=body.member,
                assignment=body.assignment,
                lifecycle=body.lifecycle,
                min_evidence=body.minEvidence if body.minEvidence is not None else (body.min_evidence if body.min_evidence is not None else 2),
                max_messages=body.maxReviewRequestsPerRun if body.maxReviewRequestsPerRun is not None else body.max_review_requests_per_run,
                dry_run=bool(body.dryRun if body.dryRun is not None else (body.dry_run if body.dry_run is not None else True)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_connector_failure_escalation_resolve(message_id: str, payload: ConnectorFailureEscalationResolutionInput) -> dict[str, Any]:
        actor_member = payload.actorMember or payload.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            return manifest_to_record(
                resolve_connector_failure_escalation(
                    app.state.workspace_path,
                    message_id,
                    actor_member=actor_member,
                    resolution=payload.resolution,
                    evidence_reviewed=payload.evidenceReviewed or payload.evidence_reviewed,
                    reminder_messages_reviewed=payload.reminderMessagesReviewed or payload.reminder_messages_reviewed,
                    follow_up_reviewed=payload.followUpReviewed or payload.follow_up_reviewed,
                )
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_connector_remediation_task_plan(suggestion_id: str, payload: ConnectorRemediationTaskPlanSubmitInput) -> dict[str, Any]:
        actor_member = payload.actorMember or payload.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        task_plan = payload.taskPlan or payload.task_plan
        if task_plan is None:
            raise HTTPException(status_code=400, detail="taskPlan is required")
        try:
            return submit_connector_remediation_task_plan(
                app.state.workspace_path,
                suggestion_id,
                actor_member=actor_member,
                task_plan=task_plan,
                source_actionable_evidence_ids=payload.sourceActionableEvidenceIds or payload.source_actionable_evidence_ids,
                lifecycle=payload.lifecycle,
                min_evidence=payload.minEvidence if payload.minEvidence is not None else (payload.min_evidence if payload.min_evidence is not None else 2),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_connector_remediation_task_plan_accept(task_plan_id: str, payload: ConnectorRemediationTaskPlanAcceptInput | None = None) -> dict[str, Any]:
        body = payload or ConnectorRemediationTaskPlanAcceptInput()
        actor_member = body.actorMember or body.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            return accept_connector_remediation_task_plan(
                app.state.workspace_path,
                task_plan_id,
                actor_member=actor_member,
                reviewed_evidence_ids=body.reviewedEvidenceIds or body.reviewed_evidence_ids,
                reviewed_review_requests=body.reviewedReviewRequests or body.reviewed_review_requests,
                dry_run=bool(body.dryRun if body.dryRun is not None else (body.dry_run if body.dry_run is not None else True)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_connector_remediation_task_run(task_id: str, payload: ConnectorRemediationTaskRunLaunchInput | None = None) -> dict[str, Any]:
        body = payload or ConnectorRemediationTaskRunLaunchInput()
        actor_member = body.actorMember or body.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            return launch_connector_remediation_task_run(
                app.state.workspace_path,
                task_id,
                actor_member=actor_member,
                member=body.member,
                assignment=body.assignment,
                model_profile=body.modelProfile or body.model_profile,
                mode=body.mode,
                branch_base=body.branchBase or body.branch_base,
                reviewed_evidence_ids=body.reviewedEvidenceIds or body.reviewed_evidence_ids,
                reviewed_review_requests=body.reviewedReviewRequests or body.reviewed_review_requests,
                dry_run=bool(body.dryRun if body.dryRun is not None else (body.dry_run if body.dry_run is not None else True)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_connector_failure_reminders(payload: ConnectorFailureReminderInput | None = None) -> dict[str, Any]:
        body = payload or ConnectorFailureReminderInput()
        actor_member = body.actorMember or body.actor_member
        if not actor_member:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            return route_connector_failure_reminders(
                app.state.workspace_path,
                actor_member=actor_member,
                connector=body.connector,
                project=body.project,
                member=body.member,
                assignment=body.assignment,
                lifecycle=body.lifecycle,
                max_messages=body.maxMessagesPerRun if body.maxMessagesPerRun is not None else body.max_messages_per_run,
                throttle_minutes=body.throttleMinutes if body.throttleMinutes is not None else body.throttle_minutes,
                dry_run=bool(body.dryRun if body.dryRun is not None else (body.dry_run if body.dry_run is not None else True)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_connector_health_check(connector_id: str, payload: ConnectorHealthCheckInput | None = None) -> dict[str, Any]:
        body = payload or ConnectorHealthCheckInput()
        try:
            check = check_connector_health(
                app.state.workspace_path,
                connector_id,
                actor_member=body.actorMember or body.actor_member,
                observed_repositories=body.observedRepositories or body.observed_repositories,
                observed_installation_ids=body.observedInstallationIds or body.observed_installation_ids,
                provider_network_called=body.providerNetworkCalled
                if body.providerNetworkCalled is not None
                else body.provider_network_called,
                required_provider_scopes=body.requiredProviderScopes or body.required_provider_scopes,
                observed_provider_scopes=body.observedProviderScopes or body.observed_provider_scopes,
                provider_diagnostics=body.providerDiagnostics or body.provider_diagnostics,
            )
            return manifest_to_record(check)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_connector_health_cleanup(payload: RetentionCleanupInput | None = None) -> dict[str, Any]:
        body = payload or RetentionCleanupInput()
        try:
            return cleanup_connector_health_checks(
                app.state.workspace_path,
                actor_member=body.actorMember or body.actor_member,
                max_age_days=body.maxAgeDays if body.maxAgeDays is not None else (body.max_age_days if body.max_age_days is not None else 30),
                keep_latest_per_connector=bool(
                    body.keepLatestPerConnector
                    if body.keepLatestPerConnector is not None
                    else (body.keep_latest_per_connector if body.keep_latest_per_connector is not None else True)
                ),
                dry_run=bool(body.dryRun if body.dryRun is not None else body.dry_run),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _scheduler_result_record(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "lease": manifest_to_record(result["lease"]) if result.get("lease") is not None else None,
            "event": manifest_to_record(result["event"]) if result.get("event") is not None else None,
            "run": manifest_to_record(result["run"]) if result.get("run") is not None else None,
            "acquired": bool(result.get("acquired")),
        }

    def post_automation_scheduler_tick(automation_id: str, payload: AutomationSchedulerTickInput | None = None) -> dict[str, Any]:
        body = payload or AutomationSchedulerTickInput()
        scheduler_id = body.schedulerId or body.scheduler_id
        tick_key = body.tickKey or body.tick_key
        if not scheduler_id:
            raise HTTPException(status_code=400, detail="schedulerId is required")
        if not tick_key:
            raise HTTPException(status_code=400, detail="tickKey is required")
        try:
            result = emit_scheduler_tick(
                app.state.workspace_path,
                automation_id,
                scheduler_id=scheduler_id,
                tick_key=tick_key,
                due_at=body.dueAt or body.due_at,
                lease_seconds=body.leaseSeconds or body.lease_seconds or 60,
                dry_run=bool(body.dryRun if body.dryRun is not None else body.dry_run),
                payload=body.payload,
            )
            return _scheduler_result_record(result)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_automation_scheduler_scan(payload: AutomationSchedulerTickInput | None = None) -> list[dict[str, Any]]:
        body = payload or AutomationSchedulerTickInput()
        scheduler_id = body.schedulerId or body.scheduler_id
        if not scheduler_id:
            raise HTTPException(status_code=400, detail="schedulerId is required")
        try:
            results = scan_cron_scheduler(
                app.state.workspace_path,
                scheduler_id=scheduler_id,
                tick_key=body.tickKey or body.tick_key,
                due_at=body.dueAt or body.due_at,
                lease_seconds=body.leaseSeconds or body.lease_seconds or 60,
                dry_run=bool(body.dryRun if body.dryRun is not None else body.dry_run),
            )
            return [_scheduler_result_record(result) for result in results]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_automation_event(automation_id: str, payload: AutomationTriggerEventInput | None = None) -> dict[str, Any]:
        body = payload or AutomationTriggerEventInput()
        event_payload = body.payload if body.payload is not None else body.sourceEvent or body.source_event or {}
        try:
            result = ingest_automation_event(
                app.state.workspace_path,
                automation_id,
                trigger_type=body.triggerType or body.trigger_type or "manual",
                source=body.source or "manual",
                actor_member=body.actorMember or body.actor_member,
                payload=event_payload,
                dry_run=bool(body.dryRun if body.dryRun is not None else body.dry_run),
                dedupe_key=body.dedupeKey or body.dedupe_key,
            )
            return {
                "event": manifest_to_record(result["event"]),
                "run": manifest_to_record(result["run"]) if result["run"] is not None else None,
                "delivery": manifest_to_record(result["delivery"]) if result.get("delivery") is not None else None,
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_automation_webhook_admission(automation_id: str, payload: AutomationWebhookAdmissionInput | None = None) -> dict[str, Any]:
        body = payload or AutomationWebhookAdmissionInput()
        try:
            result = admit_external_automation_event(
                app.state.workspace_path,
                automation_id,
                provider=body.provider or "generic",
                event_type=body.eventType or body.event_type,
                connector=body.connector,
                headers=body.headers or {},
                payload=body.payload or {},
                raw_body=body.rawBody or body.raw_body,
                actor_member=body.actorMember or body.actor_member,
                received_at=body.receivedAt or body.received_at,
                dry_run=bool(body.dryRun if body.dryRun is not None else body.dry_run),
            )
            return {
                "event": manifest_to_record(result["event"]),
                "run": manifest_to_record(result["run"]) if result["run"] is not None else None,
                "delivery": manifest_to_record(result["delivery"]) if result.get("delivery") is not None else None,
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_automation_dry_run(automation_id: str, payload: AutomationRunActionInput | None = None) -> dict[str, Any]:
        body = payload or AutomationRunActionInput()
        try:
            run = dry_run_automation(
                app.state.workspace_path,
                automation_id,
                actor_member=body.actorMember or body.actor_member,
                source_event=body.sourceEvent or body.source_event,
            )
            return manifest_to_record(run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_automation_trigger(automation_id: str, payload: AutomationRunActionInput | None = None) -> dict[str, Any]:
        body = payload or AutomationRunActionInput()
        try:
            run = trigger_automation(
                app.state.workspace_path,
                automation_id,
                actor_member=body.actorMember or body.actor_member,
                source_event=body.sourceEvent or body.source_event,
            )
            return manifest_to_record(run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_automation_run_approve(run_id: str, payload: AutomationApprovalInput | None = None) -> dict[str, Any]:
        body = payload or AutomationApprovalInput()
        reviewer_member = body.reviewerMember or body.reviewer_member
        if not reviewer_member:
            raise HTTPException(status_code=400, detail="reviewerMember is required")
        try:
            run = approve_automation_run(
                app.state.workspace_path,
                run_id,
                reviewer_member=reviewer_member,
                reason=body.reason,
                expires_at=body.expiresAt or body.expires_at,
            )
            return manifest_to_record(run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_automation_run_reject(run_id: str, payload: AutomationApprovalInput | None = None) -> dict[str, Any]:
        body = payload or AutomationApprovalInput()
        reviewer_member = body.reviewerMember or body.reviewer_member
        if not reviewer_member:
            raise HTTPException(status_code=400, detail="reviewerMember is required")
        try:
            run = reject_automation_run(
                app.state.workspace_path,
                run_id,
                reviewer_member=reviewer_member,
                reason=body.reason,
            )
            return manifest_to_record(run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_automation_run_execute(run_id: str, payload: AutomationRunActionInput | None = None) -> dict[str, Any]:
        body = payload or AutomationRunActionInput()
        try:
            run = execute_automation_run(
                app.state.workspace_path,
                run_id,
                actor_member=body.actorMember or body.actor_member,
            )
            return manifest_to_record(run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def post_automation_run_permission_request(run_id: str, payload: ControlPlanePermissionRequestInput | None = None) -> dict[str, Any]:
        body = payload or ControlPlanePermissionRequestInput()
        actor = body.actorMember or body.actor_member
        if not actor:
            raise HTTPException(status_code=400, detail="actorMember is required")
        try:
            return request_automation_run_permission(
                app.state.workspace_path,
                run_id,
                actor_member=actor,
                action_canonical=body.actionCanonical or body.action_canonical,
                action_index=body.actionIndex if body.actionIndex is not None else body.action_index,
                reason=body.reason,
                expires_at=body.expiresAt or body.expires_at,
                dry_run=True if body.dryRun is None and body.dry_run is None else bool(body.dryRun if body.dryRun is not None else body.dry_run),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def task_launch_plan(
        task_id: str,
        member: str | None = None,
        assignment: str | None = None,
        modelProfile: str | None = None,
        mode: str | None = None,
        branchBase: str | None = None,
    ) -> dict[str, Any]:
        try:
            return build_run_launch_plan(
                index(),
                task_id,
                member=member,
                assignment=assignment,
                model_profile=modelProfile,
                mode=mode,
                branch_base=branchBase,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def _tool_response(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return call()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _permission_decision_summary(decision: dict[str, Any]) -> dict[str, Any]:
        return {
            "member": decision.get("member"),
            "memberKind": decision.get("memberKind"),
            "project": decision.get("project"),
            "assignment": decision.get("assignment"),
            "action": decision.get("normalizedAction"),
            "decision": decision.get("decision"),
            "reason": decision.get("reason"),
            "selectedPolicyIds": decision.get("selectedPolicyIds", []),
            "matchedRules": decision.get("matchedRules", []),
            "blockers": decision.get("blockers", []),
            "warnings": decision.get("warnings", []),
        }

    def _run_context(run_id: str) -> tuple[str | None, str | None, str]:
        if not run_id:
            raise HTTPException(status_code=400, detail="runId is required for this MCP write tool")
        current = index()
        if run_id not in current.runs:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
        run = current.runs[run_id]
        return run.spec.project, run.spec.assignment, run_id

    def _task_context(task_id: str | None) -> tuple[str | None, str | None, str | None]:
        if not task_id:
            return None, None, None
        current = index()
        if task_id not in current.tasks:
            raise HTTPException(status_code=404, detail=f"unknown task {task_id}")
        task = current.tasks[task_id]
        return task.spec.project, task.spec.assignment, task_id

    def _context_from_payload(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        run_id = str(payload.get("runId") or payload.get("run_id") or "")
        if run_id:
            return _run_context(run_id)
        return _task_context(payload.get("task") or payload.get("taskId") or payload.get("task_id"))

    def _enforce_mcp_write_permission(tool_name: str, payload: dict[str, Any], actor_member: str) -> dict[str, Any]:
        if not actor_member:
            raise HTTPException(status_code=400, detail=f"{tool_name} requires an actor member for permission enforcement")
        project, assignment, target = _context_from_payload(payload)
        project = project or payload.get("project") or index().project.object_id
        current = index()
        assignment_record = current.assignments.get(assignment or "")
        if assignment_record is not None and assignment_record.spec.member != actor_member:
            assignment = None
        try:
            decision = explain_effective_permissions(
                current,
                member=actor_member,
                project=project,
                assignment=assignment,
                action={"tool": f"mcp__aiteamos__{tool_name}", "target": target or project or tool_name},
                non_interactive=True,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if decision["decision"] != "allow" or decision["blockers"]:
            raise HTTPException(status_code=403, detail={"permission": _permission_decision_summary(decision)})
        return _permission_decision_summary(decision)

    def post_record_journal(payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("actorMember") or payload.get("actor_member") or "")
        permission = _enforce_mcp_write_permission("record_journal", payload, actor)
        result = _tool_response(
            lambda: record_journal_for_tool(
                app.state.workspace_path,
                str(payload.get("runId") or payload.get("run_id") or ""),
                actor,
                str(payload.get("entry") or ""),
            )
        )
        result["permissionDecision"] = permission
        return result

    def post_record_event(payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("actorMember") or payload.get("actor_member") or "")
        permission = _enforce_mcp_write_permission("record_event", payload, actor)
        result = _tool_response(
            lambda: record_event_for_tool(
                app.state.workspace_path,
                str(payload.get("runId") or payload.get("run_id") or ""),
                actor,
                payload.get("event") or {},
            )
        )
        result["permissionDecision"] = permission
        return result

    def post_propose_memory(payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("actorMember") or payload.get("actor_member") or "")
        permission = _enforce_mcp_write_permission("propose_memory", payload, actor)
        result = _tool_response(
            lambda: propose_memory_for_tool(
                app.state.workspace_path,
                str(payload.get("runId") or payload.get("run_id") or ""),
                actor,
                title=payload.get("title"),
                content=str(payload.get("content") or ""),
                kind=str(payload.get("kind") or "procedural"),
                confidence=payload.get("confidence"),
                evidence=payload.get("evidence"),
                review_guidance=payload.get("reviewGuidance") or payload.get("review_guidance"),
            )
        )
        result["permissionDecision"] = permission
        return result

    def post_handoff(payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("fromMember") or payload.get("from_member") or "")
        permission = _enforce_mcp_write_permission("handoff", payload, actor)
        result = _tool_response(
            lambda: record_handoff_for_tool(
                app.state.workspace_path,
                str(payload.get("taskId") or payload.get("task_id") or ""),
                actor,
                str(payload.get("toMember") or payload.get("to_member") or ""),
                str(payload.get("problem") or payload.get("reason") or ""),
                run_id=payload.get("runId") or payload.get("run_id"),
                known_context=payload.get("knownContext") or payload.get("known_context"),
                recommended_next_step=payload.get("recommendedNextStep") or payload.get("recommended_next_step"),
                shared_memory_pack=payload.get("sharedMemoryPack") or payload.get("shared_memory_pack"),
                ownership=str(payload.get("ownership") or "transfer"),
            )
        )
        result["permissionDecision"] = permission
        return result

    def post_member_message(payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("fromMember") or payload.get("from_member") or "")
        permission = _enforce_mcp_write_permission("record_member_message", payload, actor)
        result = _tool_response(
            lambda: record_member_message_for_tool(
                app.state.workspace_path,
                actor,
                str(payload.get("body") or ""),
                to_members=payload.get("toMembers") or payload.get("to_members"),
                channel=payload.get("channel"),
                message_type=str(payload.get("messageType") or payload.get("message_type") or "message"),
                project=payload.get("project"),
                task=payload.get("task"),
                run_id=payload.get("runId") or payload.get("run_id"),
                priority=str(payload.get("priority") or "normal"),
                requested_response_by=payload.get("requestedResponseBy") or payload.get("requested_response_by"),
                attachments=payload.get("attachments"),
            )
        )
        result["permissionDecision"] = permission
        return result

    def post_create_patch(payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("actorMember") or payload.get("actor_member") or "")
        permission = _enforce_mcp_write_permission("create_patch", payload, actor)
        result = _tool_response(
            lambda: create_patch_for_tool(
                app.state.workspace_path,
                str(payload.get("runId") or payload.get("run_id") or ""),
                actor,
                diff_patch=payload.get("diffPatch") or payload.get("diff_patch"),
            )
        )
        result["permissionDecision"] = permission
        return result

    def post_grant_memory(payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("grantorMember") or payload.get("grantor_member") or payload.get("actorMember") or payload.get("actor_member") or "")
        permission = _enforce_mcp_write_permission("grant_memory", payload, actor)
        result = _tool_response(
            lambda: grant_memory_for_tool(
                app.state.workspace_path,
                str(payload.get("granteeMember") or payload.get("grantee_member") or payload.get("member") or ""),
                grantor_member=actor,
                task=payload.get("task"),
                run_id=payload.get("runId") or payload.get("run_id"),
                stores=payload.get("stores"),
                entries=payload.get("entries"),
                reason=payload.get("reason"),
                expires_at=payload.get("expiresAt") or payload.get("expires_at"),
            )
        )
        result["permissionDecision"] = permission
        return result

    def post_share_memory_tool(payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("fromMember") or payload.get("from_member") or "")
        permission = _enforce_mcp_write_permission("share_memory", payload, actor)
        result = _tool_response(
            lambda: share_memory_for_tool(
                app.state.workspace_path,
                actor,
                str(payload.get("toMember") or payload.get("to_member") or ""),
                stores=payload.get("stores"),
                entries=payload.get("entries"),
                task=payload.get("task"),
                run_id=payload.get("runId") or payload.get("run_id"),
                reason=payload.get("reason"),
                expires_at=payload.get("expiresAt") or payload.get("expires_at"),
            )
        )
        result["permissionDecision"] = permission
        return result

    def post_ask_member(payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("fromMember") or payload.get("from_member") or "")
        permission = _enforce_mcp_write_permission("ask_member", payload, actor)
        result = _tool_response(
            lambda: ask_member_for_tool(
                app.state.workspace_path,
                actor,
                str(payload.get("toMember") or payload.get("to_member") or ""),
                str(payload.get("question") or ""),
                project=payload.get("project"),
                task=payload.get("task"),
                run_id=payload.get("runId") or payload.get("run_id"),
                priority=str(payload.get("priority") or "normal"),
                requested_response_by=payload.get("requestedResponseBy") or payload.get("requested_response_by"),
                attachments=payload.get("attachments"),
            )
        )
        result["permissionDecision"] = permission
        return result

    def post_request_review_tool(payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("fromMember") or payload.get("from_member") or "")
        permission = _enforce_mcp_write_permission("request_review", payload, actor)
        result = _tool_response(
            lambda: request_review_for_tool(
                app.state.workspace_path,
                actor,
                str(payload.get("toMember") or payload.get("to_member") or ""),
                str(payload.get("body") or ""),
                review_kind=str(payload.get("reviewKind") or payload.get("review_kind") or "code"),
                project=payload.get("project"),
                task=payload.get("task"),
                run_id=payload.get("runId") or payload.get("run_id"),
                priority=str(payload.get("priority") or "normal"),
                requested_response_by=payload.get("requestedResponseBy") or payload.get("requested_response_by"),
                attachments=payload.get("attachments"),
            )
        )
        result["permissionDecision"] = permission
        return result

    def post_create_retrospective_tool(payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("facilitatorMember") or payload.get("facilitator_member") or "")
        permission = _enforce_mcp_write_permission("create_retrospective", payload, actor)
        result = _tool_response(
            lambda: _create_retrospective_from_payload(CreateRetrospectiveToolInput.model_validate(payload), source="mcp-tool")
        )
        result["tool"] = "create_retrospective"
        result["permissionDecision"] = permission
        return result

    def mcp_endpoint(payload: dict[str, Any], request: Request) -> JSONResponse:
        request_id = payload.get("id")
        method = payload.get("method")
        if method == "tools/list":
            tools = [
                {
                    "name": name,
                    "description": _tool_description(name),
                    "inputSchema": model.model_json_schema(),
                }
                for name, model in sorted(MCP_TOOL_MODELS.items())
            ]
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}})
        if method != "tools/call":
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"unknown method {method}"}})

        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if name not in MCP_TOOL_MODELS:
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": f"unknown tool {name}"}})

        decision = authorize_mcp_tool(name, request.headers.get("authorization"))
        if not decision.allowed:
            return JSONResponse(
                status_code=decision.status_code,
                content={
                    "detail": decision.detail,
                    "scope": decision.scope,
                    "acceptedTokenEnvNames": list(decision.accepted_token_envs),
                },
            )

        try:
            validated = MCP_TOOL_MODELS[name].model_validate(arguments).model_dump(mode="json", exclude_none=True)
            result = _call_mcp_tool(name, validated, request)
        except ValidationError as exc:
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(exc)}})
        except HTTPException as exc:
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": exc.status_code, "message": str(exc.detail)}})

        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": str(result)}],
                    "structuredContent": result,
                    "isError": False,
                },
            }
        )

    def _call_mcp_tool(name: str, arguments: dict[str, Any], request: Request) -> dict[str, Any]:
        if name == "search_docs":
            return tool_search_docs(**arguments)
        if name == "search_memory":
            return tool_search_memory(request, **arguments)
        if name == "get_member":
            member_id = arguments.get("memberId") or arguments.get("member_id") or ""
            return tool_get_member(member_id)
        if name == "get_project":
            project_id = arguments.get("projectId") or arguments.get("project_id") or index().project.object_id
            return tool_get_project(project_id)
        if name == "list_project_members":
            project_id = arguments.get("projectId") or arguments.get("project_id") or index().project.object_id
            return tool_list_project_members(project_id)
        if name == "list_member_projects":
            member_id = arguments.get("memberId") or arguments.get("member_id") or ""
            return tool_list_member_projects(member_id)
        if name == "get_member_memory":
            member_id = arguments.get("memberId") or arguments.get("member_id") or ""
            return tool_get_member_memory(
                request,
                member_id,
                query=arguments.get("query") or "",
                project=arguments.get("project"),
                assignment=arguments.get("assignment"),
                store=arguments.get("store"),
                viewerMember=arguments.get("viewerMember"),
                viewer_member=arguments.get("viewer_member"),
                limit=arguments.get("limit") or 10,
            )
        if name == "get_project_memory":
            project_id = arguments.get("projectId") or arguments.get("project_id") or index().project.object_id
            return tool_get_project_memory(
                request,
                project_id,
                query=arguments.get("query") or "",
                member=arguments.get("member"),
                assignment=arguments.get("assignment"),
                store=arguments.get("store"),
                viewerMember=arguments.get("viewerMember"),
                viewer_member=arguments.get("viewer_member"),
                limit=arguments.get("limit") or 10,
            )
        if name == "list_assignments":
            return tool_list_assignments(member=arguments.get("member"), project=arguments.get("project"))
        if name == "explain_permissions":
            return tool_explain_permissions(
                member=arguments.get("member"),
                project=arguments.get("project"),
                assignment=arguments.get("assignment"),
                action=arguments.get("action"),
                nonInteractive=arguments.get("nonInteractive"),
                non_interactive=arguments.get("non_interactive"),
            )
        if name == "get_task":
            task_id = arguments.get("taskId") or arguments.get("task_id") or ""
            return tool_get_task(task_id)
        if name == "get_context_capsule":
            run_id = arguments.get("runId") or arguments.get("run_id") or ""
            return tool_get_context_capsule(run_id)
        if name == "record_journal":
            return post_record_journal(arguments)
        if name == "record_event":
            return post_record_event(arguments)
        if name == "propose_memory":
            return post_propose_memory(arguments)
        if name == "grant_memory":
            return post_grant_memory(arguments)
        if name == "share_memory":
            return post_share_memory_tool(arguments)
        if name == "ask_member":
            return post_ask_member(arguments)
        if name == "request_review":
            return post_request_review_tool(arguments)
        if name == "suggest_retrospectives":
            return get_retrospective_suggestions(
                member=arguments.get("member"),
                project=arguments.get("project"),
                task=arguments.get("task"),
                limit=arguments.get("limit") or 5,
            )
        if name == "create_retrospective":
            return post_create_retrospective_tool(arguments)
        if name == "handoff":
            return post_handoff(arguments)
        if name == "record_member_message":
            return post_member_message(arguments)
        if name == "create_patch":
            return post_create_patch(arguments)
        raise HTTPException(status_code=404, detail=f"unknown tool {name}")

    add_global_get("/session", session_projection)
    add_global_post("/session/login", post_session_login)
    add_global_post("/session/renew", post_session_renew)
    add_global_post("/session/logout", post_session_logout)
    add_global_get("/workspaces", lambda: [manifest_to_record(index().workspace)])
    add_get("/catalog", lambda: _workspace_catalog(index(), app.state.workspace_path))
    add_get("/health", lambda: _workspace_health_response(index()))
    add_post("/validate", lambda: {"issues": index().health, "summary": health_summary(index().health)})
    add_post("/index", lambda: rebuild_workspace_indexes(app.state.workspace_path))
    add_get("/summary", lambda: index().to_summary())
    add_get("/actions", lambda: workspace_action_board(index()))
    add_workspace_get("/catalog", lambda: _workspace_catalog(index(), app.state.workspace_path))
    add_workspace_get("/health", lambda: _workspace_health_response(index()))
    add_workspace_post("/validate", lambda: {"issues": index().health, "summary": health_summary(index().health)})
    add_workspace_post("/index", lambda: rebuild_workspace_indexes(app.state.workspace_path))
    add_workspace_get("/summary", lambda: index().to_summary())
    add_workspace_get("/actions", lambda: workspace_action_board(index()))
    add_get("/manager/inbox", get_manager_inbox)
    add_get("/manager/evaluation", get_manager_evaluation)
    add_get("/metrics", get_prometheus_metrics)

    add_get("/projects", lambda: [manifest_to_record(index().project)])
    add_get("/projects/{project_id}", get_project)
    add_get("/projects/{project_id}/members", project_members)
    add_get("/projects/{project_id}/contributors", lambda project_id: project_member_view() if project_id == index().project.object_id else [])
    add_get("/projects/{project_id}/activity", project_member_activity)
    add_get("/projects/{project_id}/git-activity", project_git_activity)
    add_get("/projects/{project_id}/git-activity/imports", project_git_activity_import_receipts)
    add_get("/projects/{project_id}/git-activity/imports/correlation-preview", project_git_activity_import_correlation_preview)
    add_get("/projects/{project_id}/git-activity/imports/correlations", project_git_activity_correlation_reviews)
    add_get("/projects/{project_id}/git-activity/imports/correlations/promotion-candidates", project_git_activity_correlation_promotion_candidate_view)
    add_get("/projects/{project_id}/member-growth", project_member_growth)
    add_get("/projects/{project_id}/memory", project_memory)
    add_get("/projects/{project_id}/skills", get_project_skills)
    add_get("/projects/{project_id}/permissions", get_project_permissions)
    add_get("/project-member-view", project_member_view)
    add_get("/member-activity", all_member_activity)
    add_get("/git-activity", git_activity)
    add_get("/git-activity/imports", git_activity_import_receipts)
    add_get("/git-activity/imports/correlation-preview", git_activity_import_correlation_preview)
    add_get("/git-activity/imports/correlations", git_activity_correlation_reviews)
    add_get("/git-activity/imports/correlations/promotion-candidates", git_activity_correlation_promotion_candidate_view)
    add_get("/git-activity/retention-candidates", git_activity_retention_candidate_view)
    add_post("/git-activity/retention-sweep", post_git_activity_retention_sweep)
    add_post("/git-activity/imports/correlations/review", post_git_activity_correlation_review)
    add_post("/git-activity/imports/correlations/{review_id}/promote", post_git_activity_correlation_promotion)
    add_post("/git-activity/imports/admit-local-scan", post_git_activity_local_scan)
    add_post("/git-activity/imports/admit-provider-event", post_git_activity_provider_admission)
    add_post("/git-activity/imports/policy/explain", post_git_activity_import_policy_explain)
    add_post("/git-activity/imports/{receipt_id}/promote", post_git_activity_import_promotion)
    add_post("/git-activity/{activity_id}/lifecycle", post_git_activity_evidence_lifecycle)
    add_get("/member-growth", member_growth)

    add_get("/members", lambda: records(index().members.values()))
    add_post("/members", post_member)
    add_get("/members/{member_id}", get_member)
    add_patch("/members/{member_id}", patch_member)
    add_post("/members/{member_id}/archive", post_archive_member)
    add_post("/members/{member_id}/delete-request", post_member_delete_request)
    add_get("/members/{member_id}/projects", member_projects)
    add_get("/members/{member_id}/activity", member_activity)
    add_get("/members/{member_id}/git-activity", member_git_activity)
    add_get("/members/{member_id}/growth", selected_member_growth)
    add_post("/members/{member_id}/growth-records", post_member_growth_record)
    add_get("/members/{member_id}/memory", member_memory)
    add_get("/members/{member_id}/skills", get_member_skills)
    add_get("/members/{member_id}/permissions", get_member_permissions)

    add_get("/product-users", get_product_users)
    add_post("/product-users", post_product_user)
    add_get("/product-users/{user_id}", get_product_user)
    add_patch("/product-users/{user_id}", patch_product_user)
    add_post("/product-users/{user_id}/archive", post_archive_product_user)

    add_get("/assignments", list_assignments)
    add_post("/assignments", post_assignment)
    add_get("/assignments/{assignment_id}", get_assignment)
    add_patch("/assignments/{assignment_id}", patch_assignment)
    add_get("/assignments/{assignment_id}/skills", get_assignment_skills)
    add_get("/assignments/{assignment_id}/permissions", get_assignment_permissions)
    add_get("/role-templates", lambda: records(index().role_templates.values()))
    add_get("/tasks/queue", lambda: task_execution_queue(index()))
    add_get("/task-plans", lambda: records(index().task_plans.values()))
    add_get("/task-plans/execution-views", get_task_plan_execution_views)
    add_get("/task-plans/{task_plan_id}", get_task_plan)
    add_get("/task-plans/{task_plan_id}/execution-view", get_task_plan_execution_view)
    add_post("/task-plans/{task_plan_id}/retrospective", post_task_plan_retrospective)
    add_get("/tasks", lambda: records(index().tasks.values()))
    add_get("/tasks/{task_id}", get_task)
    add_get("/tasks/{task_id}/launch-plan", task_launch_plan)
    add_get("/runs", lambda: [run_record(run_id) for run_id in sorted(index().runs)])
    add_get("/runs/{run_id}", run_record)
    add_get("/runs/{run_id}/trace-context", get_run_trace_context)
    add_get("/runs/{run_id}/events", get_run_events)
    add_get("/runs/{run_id}/context-manifest", get_run_context_manifest)
    add_get("/runs/{run_id}/context-preview", get_run_context_preview)
    add_get("/runs/{run_id}/assistance-package", get_run_assistance_package)
    add_get("/runs/{run_id}/assistance-bundle", get_run_assistance_bundle)
    add_get("/runs/{run_id}/assistance-bundle/archive", get_run_assistance_bundle_archive)
    add_get("/runs/{run_id}/model/readiness", get_run_model_readiness)
    add_get("/runs/{run_id}/model/policy", get_run_model_policy)
    add_get("/runs/{run_id}/worker/readiness", get_run_worker_readiness)
    add_get("/runs/{run_id}/worker/authorization", get_run_worker_authorization)
    add_post("/runs/{run_id}/model/execute", post_run_model_execute)
    add_post("/runs/{run_id}/worker/start", post_run_worker_start)
    add_post("/runs/{run_id}/assisted-ingest", post_run_assisted_ingest)
    add_post("/runs/{run_id}/reviews", post_run_review)
    add_get("/runs/{run_id}/review-gate", get_run_review_gate)
    add_post("/runs/{run_id}/review-checks/refresh", post_run_review_checks_refresh)
    add_get("/runs/{run_id}/closeout-gate", get_run_closeout_gate)
    add_post("/runs/{run_id}/closeout", post_run_closeout)
    add_get("/runs/{run_id}/source-integration-gate", get_run_source_integration_gate)
    add_post("/runs/{run_id}/source-integration", post_run_source_integration)
    add_post("/runs/{run_id}/source-integration-remediation", post_run_source_integration_remediation)
    add_post("/runs/{run_id}/provider-source-integration", post_run_provider_source_integration)
    add_post("/runs/{run_id}/provider-source-integration/execute", post_run_provider_source_integration_execute)
    add_post("/runs/{run_id}/permission-request", post_run_worker_permission_request)
    add_get("/reviews", lambda: records(index().reviews.values()))
    add_get("/reviews/{review_id}", get_review)

    add_get("/memory/stores", get_memory_stores)
    add_post("/memory/stores", post_memory_store)
    add_get("/memory/entries", get_memory_entries)
    add_post("/memory/entries", post_memory_entry)
    add_get("/memory/bindings", get_memory_bindings)
    add_post("/memory/bindings", post_memory_binding)
    add_delete("/memory/bindings/{binding_id}", delete_memory_binding)
    add_get("/memory/grants", get_memory_grants)
    add_post("/memory/grants", post_memory_grant)
    add_post("/memory/share", post_memory_share)
    add_get("/memory/proposals", get_memory_proposals)
    add_get("/memory/proposals/queue", lambda: memory_proposal_review_queue(index()))
    add_patch("/memory/proposals/{proposal_id}", patch_memory_proposal)
    add_post("/memory/proposals/{proposal_id}/repair", post_memory_proposal_repair)
    add_post("/memory/proposals/{proposal_id}/approve", post_memory_proposal_approve)
    add_post("/memory/proposals/{proposal_id}/reject", post_memory_proposal_reject)
    add_patch("/memory/entries/{memory_id}", patch_memory_entry)
    add_post("/memory/entries/{memory_id}/stale", post_memory_entry_stale)
    add_post("/memory/entries/{memory_id}/verify", post_memory_entry_verify)
    add_get("/memory/search", tool_search_memory)
    add_get("/eval-suites", lambda: records(index().eval_suites.values()))
    add_get("/eval-results", lambda: records(index().eval_results.values()))
    add_get("/member-messages", lambda: records(index().member_messages.values()))
    add_get("/collaboration/overview", get_collaboration_overview)
    add_post("/member-messages/ask-for-help", post_ask_for_help)
    add_post("/member-messages/review-request", post_review_request)
    add_post("/member-messages/{message_id}/resolve", post_member_message_resolve)
    add_get("/retrospectives", lambda: records(index().team_retrospectives.values()))
    add_get("/retrospectives/suggestions", get_retrospective_suggestions)
    add_post("/retrospectives", post_team_retrospective)
    add_get("/handoffs", lambda: records(index().handoffs.values()))

    add_get("/automations", lambda: records(index().automations.values()))
    add_post("/automations", post_automation)
    add_get("/automations/approvals", get_automation_approvals)
    add_get("/automations/events", get_automation_events)
    add_get("/automations/provider-deliveries", get_automation_provider_deliveries)
    add_post("/automations/provider-deliveries/cleanup", post_automation_provider_deliveries_cleanup)
    add_post("/automations/provider-deliveries/{delivery_id}/retry", post_automation_provider_delivery_retry)
    add_get("/automations/runs", get_automation_runs)
    add_get("/automations/scheduler/leases", get_automation_scheduler_leases)
    add_post("/automations/scheduler/scan", post_automation_scheduler_scan)
    add_post("/automations/scheduler/leases/{lease_id}/recover", post_automation_scheduler_lease_recover)
    add_get("/automations/{automation_id}/events", get_automation_events)
    add_get("/automations/{automation_id}/provider-deliveries", get_automation_provider_deliveries)
    add_get("/automations/{automation_id}/scheduler/leases", get_automation_scheduler_leases)
    add_get("/automations/{automation_id}/runs", get_automation_runs)
    add_get("/automations/runs/{run_id}/approvals", get_automation_approvals)
    add_post("/automations/runs/{run_id}/approve", post_automation_run_approve)
    add_post("/automations/runs/{run_id}/reject", post_automation_run_reject)
    add_post("/automations/runs/{run_id}/execute", post_automation_run_execute)
    add_post("/automations/runs/{run_id}/permission-request", post_automation_run_permission_request)
    add_post("/automations/{automation_id}/admit-webhook", post_automation_webhook_admission)
    add_post("/automations/{automation_id}/events", post_automation_event)
    add_post("/automations/{automation_id}/scheduler/ticks", post_automation_scheduler_tick)
    add_post("/automations/{automation_id}/dry-run", post_automation_dry_run)
    add_post("/automations/{automation_id}/trigger", post_automation_trigger)
    add_get("/skills", get_skills)
    add_post("/skills", post_skill)
    add_get("/skills/{skill_id}", get_skill)
    add_patch("/skills/{skill_id}", patch_skill)
    add_post("/skills/{skill_id}/archive", post_archive_skill)
    add_post("/skills/{skill_id}/members/{member_id}", post_skill_member)
    add_get("/permissions", get_permissions)
    add_get("/permission-requests", get_permission_requests)
    add_post("/permission-requests", post_permission_request)
    add_post("/permission-requests/{request_id}/approve", post_permission_request_approve)
    add_post("/permission-requests/{request_id}/reject", post_permission_request_reject)
    add_get("/permission-grants", get_permission_grants)
    add_post("/permission-grants/expire", post_permission_grants_expire)
    add_post("/permission-grants/{grant_id}/revoke", post_permission_grant_revoke)
    add_get("/permissions/overview", get_permissions_overview)
    add_get("/permissions/effective", effective_permissions)
    add_post("/permissions/explain", post_permissions_explain)
    add_get("/connectors", lambda: records(index().connectors.values()))
    add_get("/connectors/operations/remediation-suggestions", get_connector_remediation_suggestions)
    add_get("/connectors/operations/remediation-task-plans", get_connector_remediation_task_plans)
    add_get("/connectors/operations/remediation-tasks", get_connector_remediation_tasks)
    add_get("/connectors/operations/remediation-runs", get_connector_remediation_runs)
    add_post("/connectors/operations/remediation-runs/{run_id}/permission-request", post_connector_remediation_run_permission_request)
    add_post("/connectors/operations/remediation-tasks/{task_id}/run", post_connector_remediation_task_run)
    add_post("/connectors/operations/remediation-task-plans/{task_plan_id}/accept", post_connector_remediation_task_plan_accept)
    add_post("/connectors/operations/remediation-suggestions/{suggestion_id}/task-plan", post_connector_remediation_task_plan)
    add_get("/connectors/operations/escalations", get_connector_failure_escalations)
    add_post("/connectors/operations/escalations", post_connector_failure_escalations)
    add_post("/connectors/operations/escalations/{message_id}/resolve", post_connector_failure_escalation_resolve)
    add_get("/connectors/operations/reminders", get_connector_failure_reminders)
    add_post("/connectors/operations/reminders", post_connector_failure_reminders)
    add_get("/connectors/operations", get_connector_operations)
    add_get("/connectors/health", get_connector_health)
    add_post("/connectors/health/cleanup", post_connector_health_cleanup)
    add_get("/connectors/{connector_id}/health", get_connector_health)
    add_post("/connectors/{connector_id}/health/check", post_connector_health_check)
    add_get("/model-profiles", lambda: records(index().model_profiles.values()))
    add_get("/model-profiles/{profile_id}/readiness", get_model_profile_readiness)
    add_get("/budget-policies", lambda: records(index().budget_policies.values()))
    add_get("/artifacts", lambda: records(index().artifacts.values()))
    add_get("/artifact-stores", lambda: records(index().artifact_stores.values()))
    add_get("/knowledge/health", lambda: evaluate_knowledge_health(index()))
    add_post("/knowledge/health/remediation", post_knowledge_health_remediation)
    add_get("/models/costs", lambda: summarize_model_costs(index()))
    add_get("/models/cost-alerts", get_model_cost_alerts)
    add_post("/models/cost-alerts", post_model_cost_alerts)

    add_get("/mcp/tools/get_task/{task_id}", tool_get_task)
    add_get("/mcp/tools/get_context_capsule/{run_id}", tool_get_context_capsule)
    add_get("/mcp/tools/get_member/{member_id}", tool_get_member)
    add_get("/mcp/tools/get_project/{project_id}", tool_get_project)
    add_get("/mcp/tools/list_project_members/{project_id}", tool_list_project_members)
    add_get("/mcp/tools/list_member_projects/{member_id}", tool_list_member_projects)
    add_get("/mcp/tools/get_member_memory", tool_get_member_memory)
    add_get("/mcp/tools/get_project_memory", tool_get_project_memory)
    add_get("/mcp/tools/list_assignments", tool_list_assignments)
    add_get("/mcp/tools/explain_permissions", tool_explain_permissions)
    add_get("/mcp/tools/search_docs", tool_search_docs)
    add_get("/mcp/tools/search_memory", tool_search_memory)
    add_get("/mcp/tools/suggest_retrospectives", get_retrospective_suggestions)
    add_post("/mcp", mcp_endpoint)

    add_post("/mcp/tools/record_journal", post_record_journal)
    add_post("/mcp/tools/record_event", post_record_event)
    add_post("/mcp/tools/propose_memory", post_propose_memory)
    add_post("/mcp/tools/grant_memory", post_grant_memory)
    add_post("/mcp/tools/share_memory", post_share_memory_tool)
    add_post("/mcp/tools/ask_member", post_ask_member)
    add_post("/mcp/tools/request_review", post_request_review_tool)
    add_post("/mcp/tools/create_retrospective", post_create_retrospective_tool)
    add_post("/mcp/tools/handoff", post_handoff)
    add_post("/mcp/tools/record_member_message", post_member_message)
    add_post("/mcp/tools/create_patch", post_create_patch)

    dashboard_dist = Path(__file__).resolve().parents[3] / "apps" / "dashboard" / "dist"
    if dashboard_dist.exists():
        app.mount("/", StaticFiles(directory=dashboard_dist, html=True), name="dashboard")

    return app


def _tool_description(name: str) -> str:
    descriptions = {
        "search_docs": "Search project docs through project/member/assignment scope.",
        "search_memory": "Search neutral memory entries and proposals through project/member/assignment/store scope.",
        "get_member": "Fetch a TeamMember manifest by durable member id.",
        "get_project": "Fetch a project manifest.",
        "list_project_members": "List TeamMembers participating in a project through assignments.",
        "list_member_projects": "List projects where a TeamMember has assignments.",
        "get_member_memory": "Search memory through an employee/member projection.",
        "get_project_memory": "Search memory through a project projection.",
        "list_assignments": "List assignments by project and optional member.",
        "explain_permissions": "Explain effective permission composition for a member/project/assignment/action.",
        "get_task": "Fetch a task manifest, markdown, runs, and reviews.",
        "get_context_capsule": "Fetch a run context capsule and manifest.",
        "record_journal": "Record an audited journal entry for a run.",
        "record_event": "Record a constrained run event.",
        "propose_memory": "Create a pending memory proposal from a run.",
        "grant_memory": "Create a temporary MemoryGrant for a member/task/run without binding memory durably.",
        "share_memory": "Share memory member-to-member by creating a temporary grant and an audit message.",
        "ask_member": "Record an ask-for-help member message.",
        "request_review": "Record a structured member-to-member review request.",
        "suggest_retrospectives": "Suggest read-only team retrospective candidates from runs, messages, and handoffs.",
        "create_retrospective": "Create a team retrospective and pending team-level memory proposal.",
        "handoff": "Record a member-to-member handoff.",
        "record_member_message": "Record an audited member message.",
        "create_patch": "Create or reference a review patch artifact.",
    }
    return descriptions.get(name, name)


def _camel_updates(payload: BaseModel) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for key, value in payload.model_dump(mode="json", exclude_none=True).items():
        parts = key.split("_")
        canonical = parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])
        updates[canonical] = value
    return updates
