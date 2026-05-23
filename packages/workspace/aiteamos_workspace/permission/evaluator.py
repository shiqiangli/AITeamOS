from __future__ import annotations

from datetime import datetime
from typing import Any

from ..loader import WorkspaceIndex, manifest_to_record
from ..risk import risk_assessment_from_permission_decision
from .actions import _normalize_action, _rule_matches, _sensitive_matches


DECISION_ORDER = ["deny", "ask", "allow"]
DEFAULT_BY_MEMBER_KIND = {
    "human": "ask",
    "hybrid": "ask",
    "digital": "deny",
    "service": "deny",
}


def explain_effective_permissions(
    index: WorkspaceIndex,
    *,
    member: str | None = None,
    project: str | None = None,
    assignment: str | None = None,
    action: dict[str, Any] | None = None,
    non_interactive: bool = False,
) -> dict[str, Any]:
    project_id = _project_id(index, project)
    member_record = _member(index, member) if member else None
    assignment_record = _assignment(index, assignment) if assignment else None
    if assignment_record is not None:
        if assignment_record.spec.project != project_id:
            raise ValueError(f"assignment {assignment} belongs to project {assignment_record.spec.project}, not {project_id}")
        if member_record is not None and assignment_record.spec.member != member_record.object_id:
            raise ValueError(f"assignment {assignment} belongs to member {assignment_record.spec.member}, not {member_record.object_id}")
        if member_record is None:
            member_record = _member(index, assignment_record.spec.member)
            member = member_record.object_id

    policy_ids, missing_policy_ids = _selected_policy_ids(index, member_record, assignment_record, project_id)
    policies = [index.permission_policies[policy_id] for policy_id in policy_ids if policy_id in index.permission_policies]
    normalized_action = _normalize_action(action or {})
    default_mode = _effective_default_mode(policies, member_record)
    matched: list[dict[str, Any]] = []
    matched_grants: list[dict[str, Any]] = []
    sensitive_matches: list[dict[str, Any]] = []
    decision = default_mode
    reason = "defaultMode"

    if normalized_action["tool"]:
        for policy in policies:
            for rule in policy.spec.deny:
                if _rule_matches(rule.match, normalized_action):
                    matched.append(_rule_match_record(policy.object_id, "deny", rule.match, rule.reason))
        if matched:
            decision = "deny"
            reason = "deny rule matched"
        else:
            matched_grants = _matched_permission_grants(index, member_record, assignment_record, project_id, normalized_action)
            if matched_grants:
                decision = "allow"
                reason = "active permission grant matched"
            else:
                sensitive_matches = _sensitive_matches(policies, normalized_action)
                if sensitive_matches:
                    decision = "ask"
                    reason = "sensitive action requires approval"
                else:
                    for policy in policies:
                        for rule in policy.spec.ask:
                            if _rule_matches(rule.match, normalized_action):
                                matched.append(_rule_match_record(policy.object_id, "ask", rule.match, rule.reason))
                    if matched:
                        decision = "ask"
                        reason = "ask rule matched"
                    else:
                        for policy in policies:
                            for rule in policy.spec.allow:
                                if _rule_matches(rule.match, normalized_action):
                                    matched.append(_rule_match_record(policy.object_id, "allow", rule.match, rule.reason))
                        if matched:
                            decision = "allow"
                            reason = "allow rule matched"

    if decision == "ask" and non_interactive:
        decision = "deny"
        reason = f"{reason}; ask converted to deny for non-interactive execution"

    blockers = []
    warnings = []
    if missing_policy_ids:
        blockers.append(f"missing permission policies: {', '.join(missing_policy_ids)}")
    if not policy_ids and member_record is not None and member_record.spec.kind in {"digital", "service"}:
        blockers.append(f"{member_record.spec.kind} member has no explicit permission policy")
    if not normalized_action["tool"]:
        warnings.append("no action supplied; decision reflects only effective defaultMode")

    result = {
        "member": member,
        "memberKind": member_record.spec.kind if member_record else None,
        "project": project_id,
        "assignment": assignment,
        "decisionOrder": DECISION_ORDER,
        "effectiveDefaultMode": default_mode,
        "nonInteractive": non_interactive,
        "action": action or {},
        "normalizedAction": normalized_action,
        "decision": decision,
        "reason": reason,
        "matchedRules": matched,
        "matchedGrants": matched_grants,
        "sensitiveMatches": sensitive_matches,
        "selectedPolicyIds": policy_ids,
        "missingPolicyIds": missing_policy_ids,
        "policies": [manifest_to_record(policy) for policy in policies],
        "blockers": blockers,
        "warnings": warnings,
    }
    result["riskAssessment"] = risk_assessment_from_permission_decision(result)
    return result


def _project_id(index: WorkspaceIndex, project: str | None) -> str:
    project_id = project or index.project.object_id
    if project_id != index.project.object_id:
        raise KeyError(f"unknown project {project_id}")
    return project_id


def _member(index: WorkspaceIndex, member: str) -> Any:
    if member not in index.members:
        raise KeyError(f"unknown member {member}")
    return index.members[member]


def _assignment(index: WorkspaceIndex, assignment: str) -> Any:
    if assignment not in index.assignments:
        raise KeyError(f"unknown assignment {assignment}")
    return index.assignments[assignment]


def _selected_policy_ids(index: WorkspaceIndex, member: Any | None, assignment: Any | None, project: str) -> tuple[list[str], list[str]]:
    seen: set[str] = set()
    policy_ids: list[str] = []

    def add(policy_id: str | None) -> None:
        if policy_id and policy_id not in seen:
            seen.add(policy_id)
            policy_ids.append(policy_id)

    if member is not None:
        for policy_id in member.spec.permissionPolicies:
            add(policy_id)
    if assignment is not None:
        for policy_id in assignment.spec.permissionPolicies:
            add(policy_id)
    for policy_id, policy in sorted(index.permission_policies.items()):
        scope = policy.spec.scope
        if not scope:
            add(policy_id)
            continue
        if member is not None and scope.get("member") == member.object_id:
            add(policy_id)
        if member is not None and scope.get("memberKind") == member.spec.kind:
            add(policy_id)
        if scope.get("project") == project:
            add(policy_id)
        if assignment is not None and scope.get("assignment") == assignment.object_id:
            add(policy_id)

    missing = [policy_id for policy_id in policy_ids if policy_id not in index.permission_policies]
    return policy_ids, missing


def _effective_default_mode(policies: list[Any], member: Any | None) -> str:
    if any(policy.spec.defaultMode == "deny" for policy in policies):
        return "deny"
    if any(policy.spec.defaultMode == "ask" for policy in policies):
        return "ask"
    if any(policy.spec.defaultMode == "allow" for policy in policies):
        return "allow"
    if member is not None:
        return DEFAULT_BY_MEMBER_KIND.get(member.spec.kind, "ask")
    return "ask"


def _matched_permission_grants(index: WorkspaceIndex, member: Any | None, assignment: Any | None, project: str, action: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for grant in index.permission_grants.values():
        if not _permission_grant_is_active(grant):
            continue
        if not _grant_scope_matches(grant.spec.scope, member, assignment, project):
            continue
        grant_action = _normalize_action(grant.spec.action)
        if _grant_action_matches(grant_action, action):
            records.append(
                {
                    "grant": grant.object_id,
                    "scope": grant.spec.scope,
                    "action": grant.spec.action,
                    "sourceRequest": grant.spec.sourceRequest,
                    "approvedByMember": grant.spec.approvedByMember,
                    "expiresAt": grant.spec.expiresAt,
                    "reason": grant.spec.reason,
                }
            )
    return sorted(records, key=lambda item: item["grant"])


def _permission_grant_is_active(grant: Any) -> bool:
    if grant.spec.status != "active":
        return False
    if not grant.spec.expiresAt:
        return True
    try:
        expires_at = datetime.fromisoformat(grant.spec.expiresAt)
    except ValueError:
        return False
    now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
    return expires_at > now


def _permission_grant_effective_status(grant: Any) -> str:
    if grant.spec.status != "active":
        return grant.spec.status
    if grant.spec.expiresAt and not _permission_grant_is_active(grant):
        return "expired"
    return "active"


def _grant_scope_matches(scope: dict[str, str], member: Any | None, assignment: Any | None, project: str) -> bool:
    if scope.get("project") and scope["project"] != project:
        return False
    if scope.get("member") and (member is None or scope["member"] != member.object_id):
        return False
    if scope.get("memberKind") and (member is None or scope["memberKind"] != member.spec.kind):
        return False
    if scope.get("assignment") and (assignment is None or scope["assignment"] != assignment.object_id):
        return False
    return True


def _grant_action_matches(grant_action: dict[str, Any], action: dict[str, Any]) -> bool:
    if not grant_action["tool"]:
        return False
    rule = grant_action["canonical"] or grant_action["tool"]
    return _rule_matches(rule, action)


def _rule_match_record(policy_id: str, decision: str, rule: str, reason: str | None) -> dict[str, Any]:
    return {"policy": policy_id, "decision": decision, "rule": rule, "reason": reason}


__all__ = [
    "DECISION_ORDER",
    "DEFAULT_BY_MEMBER_KIND",
    "explain_effective_permissions",
]
