from __future__ import annotations

from datetime import datetime
from typing import Any

from .loader import WorkspaceIndex, manifest_to_record


def permission_outcome_state(
    index: WorkspaceIndex,
    *,
    member: str | None,
    project: str | None = None,
    assignment: str | None = None,
    task: str | None = None,
    run: str | None = None,
    automation: str | None = None,
    automation_run: str | None = None,
    permission_decisions: list[dict[str, Any]] | None = None,
    action_canonicals: set[str] | None = None,
    still_blocked_when_active: bool = False,
) -> dict[str, Any]:
    canonicals = set(action_canonicals or set())
    for decision in permission_decisions or []:
        canonical = permission_decision_action_canonical(decision)
        if canonical:
            canonicals.add(canonical)
    requests = _permission_requests(
        index,
        member=member,
        project=project,
        assignment=assignment,
        task=task,
        run=run,
        automation=automation,
        automation_run=automation_run,
        action_canonicals=canonicals,
    )
    grants = _permission_grants(
        index,
        member=member,
        project=project,
        assignment=assignment,
        action_canonicals=canonicals,
        requests=requests,
    )
    pending_requests = [item for item in requests if item.get("status") == "pending"]
    approved_requests = [item for item in requests if item.get("status") == "approved"]
    rejected_requests = [item for item in requests if item.get("status") == "rejected"]
    active_grants = [item for item in grants if item.get("effectiveStatus") == "active"]
    expired_grants = [item for item in grants if item.get("effectiveStatus") == "expired"]
    revoked_grants = [item for item in grants if item.get("effectiveStatus") == "revoked"]
    outcome, explanation = _permission_outcome(
        action_canonicals=canonicals,
        pending_requests=pending_requests,
        approved_requests=approved_requests,
        rejected_requests=rejected_requests,
        active_grants=active_grants,
        expired_grants=expired_grants,
        revoked_grants=revoked_grants,
        still_blocked_when_active=still_blocked_when_active,
    )
    return {
        "actionCanonicals": sorted(canonicals),
        "requests": requests,
        "pendingRequests": pending_requests,
        "approvedRequests": approved_requests,
        "rejectedRequests": rejected_requests,
        "grants": grants,
        "activeGrants": active_grants,
        "expiredGrants": expired_grants,
        "revokedGrants": revoked_grants,
        "outcome": outcome,
        "explanation": explanation,
    }


def denied_permission_decisions(permission_decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        decision
        for decision in permission_decisions
        if decision.get("decision") != "allow" or decision.get("blockers")
    ]


def select_permission_decision(
    permission_decisions: list[dict[str, Any]],
    *,
    action_canonical: str | None = None,
    action_index: int | None = None,
) -> dict[str, Any]:
    if action_index is not None:
        if action_index < 0 or action_index >= len(permission_decisions):
            raise ValueError(f"actionIndex {action_index} is outside permission decisions")
        return permission_decisions[action_index]
    if action_canonical:
        for decision in permission_decisions:
            if permission_decision_action_canonical(decision) == action_canonical:
                return decision
        raise ValueError(f"permission action {action_canonical} was not found")
    if not permission_decisions:
        raise ValueError("no denied permission decisions are available")
    return permission_decisions[0]


def permission_decision_action_canonical(decision: dict[str, Any]) -> str | None:
    action = decision.get("action") if isinstance(decision.get("action"), dict) else {}
    return permission_action_canonical(action)


def permission_action_canonical(action: dict[str, Any] | Any) -> str | None:
    data = action if isinstance(action, dict) else {}
    canonical = data.get("canonical")
    if canonical:
        return str(canonical)
    tool = str(data.get("tool") or data.get("name") or data.get("type") or "").strip()
    value = str(
        data.get("value")
        or data.get("path")
        or data.get("command")
        or data.get("url")
        or data.get("domain")
        or data.get("operation")
        or data.get("target")
        or ""
    ).strip()
    if tool and value:
        return f"{tool}({value})"
    return tool or None


def _permission_requests(
    index: WorkspaceIndex,
    *,
    member: str | None,
    project: str | None,
    assignment: str | None,
    task: str | None,
    run: str | None,
    automation: str | None,
    automation_run: str | None,
    action_canonicals: set[str],
) -> list[dict[str, Any]]:
    if not member or not action_canonicals:
        return []
    rows: list[dict[str, Any]] = []
    for request in sorted(index.permission_requests.values(), key=lambda item: item.object_id):
        if request.spec.member != member:
            continue
        if project and request.spec.project != project:
            continue
        if assignment is not None and request.spec.assignment != assignment:
            continue
        if task is not None and request.spec.task != task:
            continue
        if run is not None and request.spec.run != run:
            continue
        if automation is not None and request.spec.automation != automation:
            continue
        if automation_run is not None and getattr(request.spec, "automationRun", None) != automation_run:
            continue
        request_action = request.spec.action.model_dump(mode="json", exclude_none=True)
        action_canonical = permission_action_canonical(request_action)
        if action_canonical not in action_canonicals:
            continue
        row = manifest_to_record(request)
        row["actionCanonical"] = action_canonical
        row["status"] = request.spec.status
        row["grant"] = request.spec.grant
        row["decidedAt"] = request.spec.decidedAt
        row["reviewerMember"] = request.spec.reviewerMember
        rows.append(row)
    return rows


def _permission_grants(
    index: WorkspaceIndex,
    *,
    member: str | None,
    project: str | None,
    assignment: str | None,
    action_canonicals: set[str],
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not action_canonicals:
        return []
    request_ids = {str(item["id"]) for item in requests if item.get("id")}
    rows: list[dict[str, Any]] = []
    for grant in sorted(index.permission_grants.values(), key=lambda item: item.object_id):
        grant_action = grant.spec.action.model_dump(mode="json", exclude_none=True)
        action_canonical = permission_action_canonical(grant_action)
        if action_canonical not in action_canonicals:
            continue
        source_request = grant.spec.sourceRequest
        if source_request not in request_ids and not _grant_scope_matches(grant.spec.scope, member=member, project=project, assignment=assignment):
            continue
        row = manifest_to_record(grant)
        row["actionCanonical"] = action_canonical
        row["sourceRequest"] = source_request
        row["effectiveStatus"] = _grant_effective_status(grant)
        rows.append(row)
    return rows


def _grant_scope_matches(scope: dict[str, str], *, member: str | None, project: str | None, assignment: str | None) -> bool:
    if scope.get("project") and scope["project"] != project:
        return False
    if scope.get("member") and scope["member"] != member:
        return False
    if scope.get("assignment") and scope["assignment"] != assignment:
        return False
    return True


def _grant_effective_status(grant: Any) -> str:
    if grant.spec.status != "active":
        return grant.spec.status
    if not grant.spec.expiresAt:
        return "active"
    try:
        expires_at = datetime.fromisoformat(grant.spec.expiresAt)
    except ValueError:
        return "expired"
    now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
    return "active" if expires_at > now else "expired"


def _permission_outcome(
    *,
    action_canonicals: set[str],
    pending_requests: list[dict[str, Any]],
    approved_requests: list[dict[str, Any]],
    rejected_requests: list[dict[str, Any]],
    active_grants: list[dict[str, Any]],
    expired_grants: list[dict[str, Any]],
    revoked_grants: list[dict[str, Any]],
    still_blocked_when_active: bool,
) -> tuple[str, str]:
    if not action_canonicals:
        return "not-required", "No denied permission action is attached to this control-plane object."
    if pending_requests:
        return "pending", "A PermissionRequest is pending in the normal Permissions review queue."
    if active_grants:
        if still_blocked_when_active:
            return (
                "approved-but-still-blocked",
                "An active PermissionGrant exists, but the effective evaluator still blocks this action; review deny-first policy or action scope.",
            )
        return "approved-active-grant", "An active PermissionGrant is available for retry or re-evaluation."
    if rejected_requests:
        return "rejected", "The latest matching PermissionRequest was rejected by a human reviewer."
    if expired_grants or revoked_grants:
        return "expired-or-revoked", "A matching PermissionGrant exists but is expired or revoked."
    if approved_requests:
        return "approved-without-active-grant", "A matching PermissionRequest was approved, but no active grant is available."
    return "request-required", "No matching PermissionRequest or active PermissionGrant exists for the denied action."
