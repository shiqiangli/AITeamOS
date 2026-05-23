from __future__ import annotations

from typing import Any

from ..audit import latest_decision_audit
from ..loader import WorkspaceIndex, manifest_to_record
from .evaluator import _assignment, _member, _permission_grant_effective_status, _project_id


REDACTED_PERMISSION_ACTION = {"tool": "redacted", "redacted": True}
PERMISSION_REDACTION_REASON = "viewer is not authorized to inspect this permission record"


def permission_governance_overview(
    index: WorkspaceIndex,
    *,
    member: str | None = None,
    project: str | None = None,
    assignment: str | None = None,
    viewer_member: str | None = None,
) -> dict[str, Any]:
    member_id = _member(index, member).object_id if member else None
    project_id = _project_id(index, project) if project else None
    assignment_id = None
    if assignment:
        assignment_record = _assignment(index, assignment)
        assignment_id = assignment_record.object_id
        if member_id and assignment_record.spec.member != member_id:
            raise ValueError(f"assignment {assignment} belongs to member {assignment_record.spec.member}, not {member_id}")
        if project_id and assignment_record.spec.project != project_id:
            raise ValueError(f"assignment {assignment} belongs to project {assignment_record.spec.project}, not {project_id}")
    if viewer_member is not None:
        _member(index, viewer_member)
    redact_without_viewer = viewer_member is None
    raw_requests = [_permission_request_record(request) for request in index.permission_requests.values()]
    raw_grants = [_permission_grant_record(grant) for grant in index.permission_grants.values()]
    raw_requests = [request for request in raw_requests if _record_scope_matches(request, member=member_id, project=project_id, assignment=assignment_id)]
    raw_grants = [grant for grant in raw_grants if _record_scope_matches(grant, member=member_id, project=project_id, assignment=assignment_id)]
    policies = [
        policy
        for policy in permission_policy_records(index, viewer_member=viewer_member, redact_without_viewer=redact_without_viewer)
        if _policy_scope_matches_projection(index, policy, member=member_id, project=project_id, assignment=assignment_id)
    ]
    requests_by_member = _count_by(raw_requests, "member")
    grants_by_member = _count_by(raw_grants, "member")
    requests_by_project = _count_by(raw_requests, "project")
    grants_by_project = _count_by(raw_grants, "project")
    pending_requests = [request for request in raw_requests if request["status"] == "pending"]
    active_grants = [grant for grant in raw_grants if grant["effectiveStatus"] == "active"]
    expired_grants = [grant for grant in raw_grants if grant["effectiveStatus"] == "expired"]
    revoked_grants = [grant for grant in raw_grants if grant["effectiveStatus"] == "revoked"]
    denied_requests = [
        request
        for request in raw_requests
        if request.get("currentDecision", {}).get("decision") == "deny" or request["status"] == "rejected"
    ]
    requests = _redacted_permission_request_records(index, raw_requests, viewer_member, redact_without_viewer)
    grants = _redacted_permission_grant_records(index, raw_grants, viewer_member, redact_without_viewer)
    redacted_pending_requests = _redacted_permission_request_records(index, pending_requests, viewer_member, redact_without_viewer)
    redacted_active_grants = _redacted_permission_grant_records(index, active_grants, viewer_member, redact_without_viewer)
    redacted_expired_grants = _redacted_permission_grant_records(index, expired_grants, viewer_member, redact_without_viewer)
    redacted_revoked_grants = _redacted_permission_grant_records(index, revoked_grants, viewer_member, redact_without_viewer)
    redacted_denied_requests = _redacted_permission_request_records(index, denied_requests, viewer_member, redact_without_viewer)
    return {
        "scope": {
            "member": member_id,
            "project": project_id,
            "assignment": assignment_id,
        },
        "summary": {
            "policies": len(policies),
            "requests": len(requests),
            "pendingRequests": len(pending_requests),
            "approvedRequests": sum(1 for request in requests if request["status"] == "approved"),
            "rejectedRequests": sum(1 for request in requests if request["status"] == "rejected"),
            "grants": len(grants),
            "activeGrants": len(active_grants),
            "expiredGrants": len(expired_grants),
            "revokedGrants": len(revoked_grants),
            "deniedRequests": len(denied_requests),
        },
        "policies": policies,
        "requests": requests,
        "pendingRequests": redacted_pending_requests,
        "grants": grants,
        "activeGrants": redacted_active_grants,
        "expiredGrants": redacted_expired_grants,
        "revokedGrants": redacted_revoked_grants,
        "deniedRequests": redacted_denied_requests,
        "byMember": _projection_rows(
            {member_id: index.members[member_id]} if member_id else index.members,
            requests_by_member,
            grants_by_member,
            "member",
        ),
        "byProject": _projection_rows(
            {project_id: index.project} if project_id else {index.project.object_id: index.project},
            requests_by_project,
            grants_by_project,
            "project",
        ),
    }


def permission_policy_records(
    index: WorkspaceIndex,
    *,
    viewer_member: str | None = None,
    redact_without_viewer: bool = True,
) -> list[dict[str, Any]]:
    if viewer_member is not None:
        _member(index, viewer_member)
    return [
        _redact_permission_policy_record(index, manifest_to_record(policy), viewer_member, redact_without_viewer)
        for policy in index.permission_policies.values()
    ]


def permission_request_records(
    index: WorkspaceIndex,
    *,
    viewer_member: str | None = None,
    redact_without_viewer: bool = True,
) -> list[dict[str, Any]]:
    if viewer_member is not None:
        _member(index, viewer_member)
    return _redacted_permission_request_records(
        index,
        [_permission_request_record(request) for request in index.permission_requests.values()],
        viewer_member,
        redact_without_viewer,
    )


def permission_grant_records(
    index: WorkspaceIndex,
    *,
    viewer_member: str | None = None,
    redact_without_viewer: bool = True,
) -> list[dict[str, Any]]:
    if viewer_member is not None:
        _member(index, viewer_member)
    return _redacted_permission_grant_records(
        index,
        [_permission_grant_record(grant) for grant in index.permission_grants.values()],
        viewer_member,
        redact_without_viewer,
    )


def _redacted_permission_request_records(
    index: WorkspaceIndex,
    records: list[dict[str, Any]],
    viewer_member: str | None,
    redact_without_viewer: bool,
) -> list[dict[str, Any]]:
    return [
        _redact_permission_request_record(index, record, viewer_member, redact_without_viewer)
        for record in records
    ]


def _redacted_permission_grant_records(
    index: WorkspaceIndex,
    records: list[dict[str, Any]],
    viewer_member: str | None,
    redact_without_viewer: bool,
) -> list[dict[str, Any]]:
    return [
        _redact_permission_grant_record(index, record, viewer_member, redact_without_viewer)
        for record in records
    ]


def _redact_permission_policy_record(
    index: WorkspaceIndex,
    record: dict[str, Any],
    viewer_member: str | None,
    redact_without_viewer: bool,
) -> dict[str, Any]:
    spec = dict(record.get("spec", {}))
    if _permission_scope_allows_viewer(
        index,
        spec.get("scope", {}),
        viewer_member,
        redact_without_viewer=redact_without_viewer,
    ):
        return record
    redacted = {**record, "redacted": True, "redactionReason": PERMISSION_REDACTION_REASON}
    redacted["spec"] = {
        **spec,
        "allow": [],
        "ask": [],
        "deny": [],
        "sensitivePaths": [],
        "redacted": True,
        "redactionReason": PERMISSION_REDACTION_REASON,
    }
    return redacted


def _redact_permission_request_record(
    index: WorkspaceIndex,
    record: dict[str, Any],
    viewer_member: str | None,
    redact_without_viewer: bool,
) -> dict[str, Any]:
    scope = {
        key: value
        for key, value in {
            "member": record.get("member"),
            "project": record.get("project"),
            "assignment": record.get("assignment"),
        }.items()
        if value
    }
    related_members = {
        value
        for value in [
            record.get("member"),
            record.get("requesterMember"),
            record.get("reviewerMember"),
            record.get("latestDecisionActorMember"),
        ]
        if value
    }
    if _permission_scope_allows_viewer(
        index,
        scope,
        viewer_member,
        related_members=related_members,
        redact_without_viewer=redact_without_viewer,
    ):
        return record
    redacted = _base_redacted_permission_record(record)
    spec = dict(redacted.get("spec", {}))
    spec.update(
        {
            "action": dict(REDACTED_PERMISSION_ACTION),
            "reason": None,
            "currentDecision": {},
            "decisionAudit": [],
            "audit": {},
            "redacted": True,
            "redactionReason": PERMISSION_REDACTION_REASON,
        }
    )
    redacted["spec"] = spec
    redacted.update(
        {
            "action": dict(REDACTED_PERMISSION_ACTION),
            "currentDecision": {},
            "decisionAudit": [],
            "latestDecisionKind": None,
            "latestDecision": None,
            "latestDecisionActorMember": None,
            "latestDecisionActorKind": None,
            "latestRiskLevel": None,
            "latestRiskRecommendedDecision": None,
            "latestRiskRequiresHumanReview": None,
            "redacted": True,
            "redactionReason": PERMISSION_REDACTION_REASON,
        }
    )
    return redacted


def _redact_permission_grant_record(
    index: WorkspaceIndex,
    record: dict[str, Any],
    viewer_member: str | None,
    redact_without_viewer: bool,
) -> dict[str, Any]:
    scope = {
        key: value
        for key, value in {
            "member": record.get("member"),
            "project": record.get("project"),
            "assignment": record.get("assignment"),
            "memberKind": record.get("memberKind"),
        }.items()
        if value
    }
    related_members = {
        value
        for value in [
            record.get("member"),
            record.get("approvedByMember"),
            record.get("latestDecisionActorMember"),
        ]
        if value
    }
    if _permission_scope_allows_viewer(
        index,
        scope,
        viewer_member,
        related_members=related_members,
        redact_without_viewer=redact_without_viewer,
    ):
        return record
    redacted = _base_redacted_permission_record(record)
    spec = dict(redacted.get("spec", {}))
    spec.update(
        {
            "action": dict(REDACTED_PERMISSION_ACTION),
            "sourceRequest": None,
            "approvedByMember": None,
            "reason": None,
            "decisionAudit": [],
            "audit": {},
            "redacted": True,
            "redactionReason": PERMISSION_REDACTION_REASON,
        }
    )
    redacted["spec"] = spec
    redacted.update(
        {
            "action": dict(REDACTED_PERMISSION_ACTION),
            "sourceRequest": None,
            "approvedByMember": None,
            "decisionAudit": [],
            "latestDecisionKind": None,
            "latestDecision": None,
            "latestDecisionActorMember": None,
            "latestDecisionActorKind": None,
            "latestRiskLevel": None,
            "latestRiskRecommendedDecision": None,
            "latestRiskRequiresHumanReview": None,
            "redacted": True,
            "redactionReason": PERMISSION_REDACTION_REASON,
        }
    )
    return redacted


def _base_redacted_permission_record(record: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(record)
    redacted["spec"] = dict(record.get("spec", {}))
    return redacted


def _permission_scope_allows_viewer(
    index: WorkspaceIndex,
    scope: dict[str, Any],
    viewer_member: str | None,
    *,
    related_members: set[str] | None = None,
    redact_without_viewer: bool,
) -> bool:
    if viewer_member is None:
        return not redact_without_viewer
    if viewer_member not in index.members:
        return False
    if related_members and viewer_member in related_members:
        return True
    viewer = index.members[viewer_member]
    viewer_assignments = {
        assignment.object_id
        for assignment in index.assignments.values()
        if assignment.spec.member == viewer_member
    }
    viewer_projects = {
        assignment.spec.project
        for assignment in index.assignments.values()
        if assignment.spec.member == viewer_member
    }
    if scope.get("member"):
        return scope["member"] == viewer_member
    if scope.get("assignment"):
        return scope["assignment"] in viewer_assignments
    if scope.get("memberKind"):
        return scope["memberKind"] == viewer.spec.kind
    if scope.get("project"):
        return scope["project"] in viewer_projects
    return True


def _policy_scope_matches_projection(
    index: WorkspaceIndex,
    record: dict[str, Any],
    *,
    member: str | None,
    project: str | None,
    assignment: str | None,
) -> bool:
    if not any([member, project, assignment]):
        return True
    spec = record.get("spec", {})
    scope = spec.get("scope", {}) if isinstance(spec, dict) else {}
    if not scope:
        return True
    target_members, target_member_kinds, target_projects, target_assignments = _projection_scope_targets(
        index,
        member=member,
        project=project,
        assignment=assignment,
    )
    scope_member = scope.get("member")
    if scope_member:
        return scope_member in target_members
    scope_assignment = scope.get("assignment")
    if scope_assignment:
        return scope_assignment in target_assignments
    scope_project = scope.get("project")
    if scope_project:
        return scope_project in target_projects
    scope_member_kind = scope.get("memberKind")
    if scope_member_kind:
        return scope_member_kind in target_member_kinds
    return True


def _projection_scope_targets(
    index: WorkspaceIndex,
    *,
    member: str | None,
    project: str | None,
    assignment: str | None,
) -> tuple[set[str], set[str], set[str], set[str]]:
    members: set[str] = set()
    projects: set[str] = set()
    assignments: set[str] = set()

    if project:
        projects.add(project)
        for assignment_id, assignment_record in index.assignments.items():
            if assignment_record.spec.project == project:
                assignments.add(assignment_id)
                members.add(assignment_record.spec.member)
        for member_id, member_record in index.members.items():
            if _member_has_project(member_record, project):
                members.add(member_id)

    if member:
        members.add(member)
        for assignment_id, assignment_record in index.assignments.items():
            if assignment_record.spec.member == member:
                assignments.add(assignment_id)
                projects.add(assignment_record.spec.project)
        member_record = index.members.get(member)
        if member_record is not None:
            for engagement in getattr(member_record.spec, "projects", []):
                engagement_project = getattr(engagement, "project", None)
                if engagement_project:
                    projects.add(engagement_project)

    if assignment:
        assignments.add(assignment)
        assignment_record = index.assignments.get(assignment)
        if assignment_record is not None:
            members.add(assignment_record.spec.member)
            projects.add(assignment_record.spec.project)

    member_kinds = {
        index.members[member_id].spec.kind
        for member_id in members
        if member_id in index.members
    }
    return members, member_kinds, projects, assignments


def _member_has_project(member_record: Any, project: str) -> bool:
    return any(getattr(engagement, "project", None) == project for engagement in getattr(member_record.spec, "projects", []))


def _permission_request_record(request: Any) -> dict[str, Any]:
    record = manifest_to_record(request)
    spec = record.get("spec", {})
    latest_audit = latest_decision_audit(request.spec.decisionAudit)
    latest_risk = latest_audit.get("riskAssessment") or {}
    return {
        **record,
        "member": spec.get("member"),
        "project": spec.get("project"),
        "assignment": spec.get("assignment"),
        "task": spec.get("task"),
        "run": spec.get("run"),
        "automation": spec.get("automation"),
        "automationRun": spec.get("automationRun"),
        "requesterMember": spec.get("requesterMember"),
        "reviewerMember": spec.get("reviewerMember"),
        "status": spec.get("status"),
        "action": spec.get("action", {}),
        "currentDecision": spec.get("currentDecision", {}),
        "decisionAudit": spec.get("decisionAudit", []),
        "latestDecisionKind": latest_audit.get("decisionKind"),
        "latestDecision": latest_audit.get("decision"),
        "latestDecisionActorMember": latest_audit.get("actorMember"),
        "latestDecisionActorKind": latest_audit.get("actorMemberKind"),
        "latestRiskLevel": latest_risk.get("riskLevel"),
        "latestRiskRecommendedDecision": latest_risk.get("recommendedDecision"),
        "latestRiskRequiresHumanReview": latest_risk.get("requiresHumanReview"),
        "grant": spec.get("grant"),
        "expiresAt": spec.get("expiresAt"),
    }


def _permission_grant_record(grant: Any) -> dict[str, Any]:
    record = manifest_to_record(grant)
    spec = record.get("spec", {})
    scope = spec.get("scope", {})
    latest_audit = latest_decision_audit(grant.spec.decisionAudit)
    latest_risk = latest_audit.get("riskAssessment") or {}
    return {
        **record,
        "project": scope.get("project"),
        "member": scope.get("member"),
        "assignment": scope.get("assignment"),
        "memberKind": scope.get("memberKind"),
        "status": spec.get("status"),
        "effectiveStatus": _permission_grant_effective_status(grant),
        "action": spec.get("action", {}),
        "sourceRequest": spec.get("sourceRequest"),
        "approvedByMember": spec.get("approvedByMember"),
        "decisionAudit": spec.get("decisionAudit", []),
        "latestDecisionKind": latest_audit.get("decisionKind"),
        "latestDecision": latest_audit.get("decision"),
        "latestDecisionActorMember": latest_audit.get("actorMember"),
        "latestDecisionActorKind": latest_audit.get("actorMemberKind"),
        "latestRiskLevel": latest_risk.get("riskLevel"),
        "latestRiskRecommendedDecision": latest_risk.get("recommendedDecision"),
        "latestRiskRequiresHumanReview": latest_risk.get("requiresHumanReview"),
        "expiresAt": spec.get("expiresAt"),
    }


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "")
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _record_scope_matches(
    record: dict[str, Any],
    *,
    member: str | None = None,
    project: str | None = None,
    assignment: str | None = None,
) -> bool:
    return not (
        (member and record.get("member") != member)
        or (project and record.get("project") != project)
        or (assignment and record.get("assignment") != assignment)
    )


def _projection_rows(objects: dict[str, Any], requests_by_id: dict[str, int], grants_by_id: dict[str, int], id_key: str) -> list[dict[str, Any]]:
    rows = []
    for object_id in sorted(objects):
        rows.append(
            {
                "id": object_id,
                "kind": "PermissionProjection",
                id_key: object_id,
                "requestCount": requests_by_id.get(object_id, 0),
                "grantCount": grants_by_id.get(object_id, 0),
            }
        )
    return rows


__all__ = [
    "permission_governance_overview",
    "permission_grant_records",
    "permission_policy_records",
    "permission_request_records",
]
