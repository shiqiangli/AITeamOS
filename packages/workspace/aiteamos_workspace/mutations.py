from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import hashlib
import json

from aiteamos_schema import (
    Assignment,
    ContextManifest,
    GitActivity,
    Handoff,
    KnowledgeHealthRemediationRecord,
    MemoryBinding,
    MemoryEntry,
    MemoryGrant,
    MemoryProposal,
    MemoryStore,
    MemoryVersion,
    MemberDeleteRequestRecord,
    ModelProfile,
    MemberMessage,
    PermissionGrant,
    PermissionRequest,
    ProductUser,
    Review,
    Run,
    Skill,
    Task,
    TeamMember,
    TeamRetrospective,
    timestamp_memory_proposal_id,
    timestamp_review_id,
    timestamp_run_id,
    timestamp_task_id,
)

from .approval_workflows import approval_workflow_id, write_subject_approval_workflow
from .context import ContextCompilerResult, build_context_capsule
from .audit import decision_audit_record
from .io import read_text_if_exists, read_yaml, write_text, write_yaml
from .loader import load_workspace
from .memory_gate import (
    memory_eval_confidence_sources,
    memory_eval_evidence_records,
    memory_eval_evidence_refs,
    memory_proposal_repair_hints,
    evaluate_memory_promotion_gate,
)
from .permissions import edit_action, explain_effective_permissions
from .run_events import RUN_EVENT_RETENTION_DAYS, append_run_event_record, build_run_event_payload
from .task_plan_execution import task_plan_execution_view


RUN_RETENTION_DAYS = RUN_EVENT_RETENTION_DAYS


def create_member(
    workspace_path: str | Path,
    *,
    name: str,
    kind: str,
    profile: dict[str, Any] | None = None,
    about_me: dict[str, Any] | None = None,
    capabilities: list[dict[str, Any]] | None = None,
    work_style: dict[str, Any] | None = None,
    work_method: dict[str, Any] | None = None,
    skills: list[str] | None = None,
    connectors: list[str] | None = None,
    permission_policies: list[str] | None = None,
    memory_stores: list[str] | None = None,
    default_assignments: list[str] | None = None,
) -> TeamMember:
    index = load_workspace(workspace_path)
    member_id = _safe_id(name)
    if not member_id:
        raise ValueError("member name is required")
    if member_id in index.members:
        raise ValueError(f"member {member_id} already exists")
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "TeamMember",
        "metadata": {
            "name": member_id,
            "title": (profile or {}).get("displayName") or (profile or {}).get("title") or member_id,
            "createdAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        },
        "spec": {
            "kind": kind,
            "profile": profile or {},
            "aboutMe": about_me or {},
            "capabilities": capabilities or [],
            "workStyle": work_style or {},
            "workMethod": work_method or {},
            "defaultAssignments": default_assignments or [],
            "skills": skills or [],
            "connectors": connectors or [],
            "permissionPolicies": permission_policies or [],
            "memoryStores": memory_stores or [],
        },
    }
    member = TeamMember.model_validate(payload)
    write_yaml(index.workspace_root / "members" / f"{member_id}.yaml", member.model_dump(mode="json", exclude_none=True))
    return member


def update_member(workspace_path: str | Path, member_id: str, updates: dict[str, Any]) -> TeamMember:
    index = load_workspace(workspace_path)
    if member_id not in index.members:
        raise KeyError(f"unknown member {member_id}")
    path = index.workspace_root / "members" / f"{member_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    for key in [
        "profile",
        "userBinding",
        "aboutMe",
        "capabilities",
        "workStyle",
        "workMethod",
        "projects",
        "defaultAssignments",
        "skills",
        "connectors",
        "permissionPolicies",
        "memoryStores",
        "growthRecords",
        "performanceMetrics",
    ]:
        if key in updates and updates[key] is not None:
            value = updates[key]
            if key in {"profile", "aboutMe", "workStyle", "workMethod"} and isinstance(value, dict):
                current = spec.get(key) if isinstance(spec.get(key), dict) else {}
                spec[key] = {**current, **value}
            else:
                spec[key] = value
    member = TeamMember.model_validate(data)
    write_yaml(path, member.model_dump(mode="json", exclude_none=True))
    return member


def archive_member(workspace_path: str | Path, member_id: str) -> TeamMember:
    index = load_workspace(workspace_path)
    if member_id not in index.members:
        raise KeyError(f"unknown member {member_id}")
    path = index.workspace_root / "members" / f"{member_id}.yaml"
    data = read_yaml(path)
    data.setdefault("spec", {}).setdefault("profile", {})["status"] = "archived"
    archived = TeamMember.model_validate(data)
    write_yaml(path, archived.model_dump(mode="json", exclude_none=True))
    for assignment_id, assignment in index.assignments.items():
        if assignment.spec.member == member_id and assignment.spec.status == "active":
            update_assignment(workspace_path, assignment_id, {"status": "archived"})
    for binding_id, binding in index.memory_bindings.items():
        if binding.spec.targetType == "member" and binding.spec.targetId == member_id and binding.spec.status == "active":
            archive_memory_binding(workspace_path, binding_id)
    return archived


def request_member_delete(
    workspace_path: str | Path,
    member_id: str,
    *,
    actor_member: str,
    reason: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if member_id not in index.members:
        raise KeyError(f"unknown member {member_id}")
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    if actor_kind not in {"human", "hybrid", "service"}:
        raise ValueError("member delete requests require a human, hybrid, or governed service actor")

    requested_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
    references = _member_delete_references(index, member_id)
    evidence = [
        {"kind": kind, "ids": ids}
        for kind, ids in references.items()
        if ids
    ]
    audit = decision_audit_record(
        index,
        decision_kind="service_policy_decision" if actor_kind == "service" else "human_approval",
        decision="member-delete-request-redacted",
        actor_member=actor_member,
        authority="enforce" if actor_kind == "service" else "approve",
        reason=reason or "Member delete request archived and redacted linked workspace evidence.",
        source="member-delete-request",
        decided_at=requested_at,
        evidence=evidence,
        metadata={"targetMember": member_id},
    )
    redaction_queue: list[dict[str, str]] = []
    updated: dict[str, int] = {"members": 0, "runs": 0, "messages": 0, "handoffs": 0, "gitActivity": 0, "assignments": 0, "memoryBindings": 0}

    member_path = index.workspace_root / "members" / f"{member_id}.yaml"
    member_data = read_yaml(member_path)
    member_spec = member_data.setdefault("spec", {})
    member_data.setdefault("metadata", {})["title"] = f"Redacted TeamMember {member_id}"
    profile = member_spec.setdefault("profile", {})
    profile["displayName"] = f"Redacted TeamMember {member_id}"
    profile["title"] = "redacted"
    profile["avatarUrl"] = None
    profile["timezone"] = None
    profile["status"] = "archived"
    profile["summary"] = "Redacted by member delete request."
    member_spec["aboutMe"] = {}
    member_spec["capabilities"] = []
    member_spec["workStyle"] = {}
    member_spec["workMethod"] = {}
    member_spec["projects"] = []
    member_spec["defaultAssignments"] = []
    member_spec["skills"] = []
    member_spec["connectors"] = []
    member_spec["permissionPolicies"] = []
    member_spec["memoryStores"] = []
    member_spec["growthRecords"] = []
    member_spec["performanceMetrics"] = []
    _mark_lifecycle_redacted(member_spec, requested_at, audit, export_policy="sanitize")
    member = TeamMember.model_validate(member_data)
    write_yaml(member_path, member.model_dump(mode="json", exclude_none=True))
    updated["members"] = 1

    for assignment_id in references["assignments"]:
        path = index.workspace_root / "assignments" / f"{assignment_id}.yaml"
        data = read_yaml(path)
        spec = data.setdefault("spec", {})
        spec["status"] = "archived"
        spec["archivedAt"] = requested_at
        spec["archiveReason"] = "member-delete-request"
        spec.setdefault("decisionAudit", []).append(audit)
        assignment = Assignment.model_validate(data)
        write_yaml(path, assignment.model_dump(mode="json", exclude_none=True))
        updated["assignments"] += 1
        _queue_member_delete_reference(redaction_queue, index, "Assignment", assignment_id, path, "archive")

    for binding_id in references["memoryBindings"]:
        path = _memory_binding_manifest_path(index, binding_id)
        data = read_yaml(path)
        spec = data.setdefault("spec", {})
        spec["status"] = "archived"
        spec["archivedAt"] = requested_at
        spec["archiveReason"] = "member-delete-request"
        spec.setdefault("decisionAudit", []).append(audit)
        binding = MemoryBinding.model_validate(data)
        write_yaml(path, binding.model_dump(mode="json", exclude_none=True))
        updated["memoryBindings"] += 1
        _queue_member_delete_reference(redaction_queue, index, "MemoryBinding", binding_id, path, "archive")

    for run_id in references["runs"]:
        path = index.workspace_root / "runs" / run_id / "run.yaml"
        data = read_yaml(path)
        spec = data.setdefault("spec", {})
        spec["roleContext"] = "redacted"
        spec["outputs"] = []
        spec["ingest"] = {}
        spec["closeout"] = {}
        spec["sourceIntegration"] = {}
        _mark_lifecycle_redacted(spec, requested_at, audit, export_policy="manifest-only")
        run = Run.model_validate(data)
        write_yaml(path, run.model_dump(mode="json", exclude_none=True))
        _redact_run_payload_files(index, run, requested_at)
        updated["runs"] += 1
        _queue_member_delete_reference(redaction_queue, index, "Run", run_id, path, "redact")

    for message_id in references["messages"]:
        path = _member_message_manifest_path(index, message_id)
        data = read_yaml(path)
        spec = data.setdefault("spec", {})
        spec["status"] = "archived"
        spec["body"] = "Redacted by member delete request."
        spec["resolution"] = "Redacted by member delete request."
        spec.setdefault("audit", {})["memberDeleteRequest"] = {"member": member_id, "redactedAt": requested_at}
        _mark_lifecycle_redacted(spec, requested_at, audit, export_policy="sanitize")
        message = MemberMessage.model_validate(data)
        write_yaml(path, message.model_dump(mode="json", exclude_none=True))
        updated["messages"] += 1
        _queue_member_delete_reference(redaction_queue, index, "MemberMessage", message_id, path, "redact")

    for handoff_id in references["handoffs"]:
        path = _handoff_manifest_path(index, handoff_id)
        data = read_yaml(path)
        spec = data.setdefault("spec", {})
        spec["status"] = "cancelled"
        spec["sourceBranch"] = None
        spec["targetBranch"] = None
        spec["problem"] = "Redacted by member delete request."
        spec["knownContext"] = []
        spec["recommendedNextStep"] = "Redacted by member delete request."
        spec["sharedMemoryPack"] = []
        _mark_lifecycle_redacted(spec, requested_at, audit, export_policy="sanitize")
        handoff = Handoff.model_validate(data)
        write_yaml(path, handoff.model_dump(mode="json", exclude_none=True))
        updated["handoffs"] += 1
        _queue_member_delete_reference(redaction_queue, index, "Handoff", handoff_id, path, "redact")

    for activity_id in references["gitActivity"]:
        path = _git_activity_manifest_path(index, activity_id)
        data = read_yaml(path)
        spec = data.setdefault("spec", {})
        spec["summary"] = f"Redacted GitActivity evidence {activity_id}; lineage preserved for member delete request."
        spec["externalId"] = None
        spec["url"] = None
        spec["refs"] = []
        _mark_lifecycle_redacted(spec, requested_at, audit, export_policy="exclude")
        spec["redactionPolicy"] = "redacted-summary"
        activity = GitActivity.model_validate(data)
        write_yaml(path, activity.model_dump(mode="json", exclude_none=True))
        updated["gitActivity"] += 1
        _queue_member_delete_reference(redaction_queue, index, "GitActivity", activity_id, path, "redact")

    result = {
        "member": member_id,
        "actorMember": actor_member,
        "requestedAt": requested_at,
        "status": "redacted",
        "references": references,
        "redactionQueue": redaction_queue,
        "updated": updated,
        "decisionAudit": audit,
    }
    return MemberDeleteRequestRecord.model_validate(result).model_dump(mode="json", exclude_none=True)


def create_product_user(
    workspace_path: str | Path,
    *,
    name: str,
    actor_member: str,
    display_name: str | None = None,
    member: str | None = None,
    identity_provider: str = "local-token",
    identity_subject_hash: str | None = None,
    status: str = "active",
    roles: list[str] | None = None,
    session_token_env: str | None = None,
    governance_scopes: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    user_id = _safe_id(name)
    if not user_id:
        raise ValueError("product user name is required")
    if user_id in index.product_users:
        raise ValueError(f"product user {user_id} already exists")
    _validate_product_user_refs(index, actor_member=actor_member, member=member)
    permission = _product_user_permission_decision(
        index,
        actor_member=actor_member,
        path=f"/.aiteamos/product_users/{user_id}.yaml",
        reason=reason,
    )
    audit = _product_user_management_audit(
        index,
        actor_member=actor_member,
        action="create-product-user",
        target_user=user_id,
        reason=reason,
        permission_decision=permission,
    )
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "ProductUser",
        "metadata": {
            "name": user_id,
            "title": display_name or name,
            "createdAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        },
        "spec": {
            "displayName": display_name or name,
            "member": member,
            "identityProvider": identity_provider,
            "identitySubjectHash": identity_subject_hash,
            "status": status,
            "roles": roles or ["viewer"],
            "sessionTokenEnv": session_token_env,
            "governanceScopes": governance_scopes or [],
            "managementAudit": [audit],
        },
    }
    product_user = ProductUser.model_validate(payload)
    write_yaml(
        index.workspace_root / "product_users" / f"{user_id}.yaml",
        product_user.model_dump(mode="json", exclude_none=True),
    )
    _sync_product_user_member_binding(index.workspace_root, product_user, actor_member=actor_member)
    return {"productUser": product_user, "permissionDecision": permission, "managementAudit": audit}


def update_product_user(
    workspace_path: str | Path,
    user_id: str,
    *,
    actor_member: str,
    display_name: str | None = None,
    member: str | None = None,
    identity_provider: str | None = None,
    identity_subject_hash: str | None = None,
    status: str | None = None,
    roles: list[str] | None = None,
    session_token_env: str | None = None,
    governance_scopes: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if user_id not in index.product_users:
        raise KeyError(f"unknown product user {user_id}")
    _validate_product_user_refs(index, actor_member=actor_member, member=member)
    permission = _product_user_permission_decision(
        index,
        actor_member=actor_member,
        path=f"/.aiteamos/product_users/{user_id}.yaml",
        reason=reason,
    )
    path = index.workspace_root / "product_users" / f"{user_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    if display_name is not None:
        spec["displayName"] = display_name
        data.setdefault("metadata", {})["title"] = display_name
    if member is not None:
        spec["member"] = member
    if identity_provider is not None:
        spec["identityProvider"] = identity_provider
    if identity_subject_hash is not None:
        spec["identitySubjectHash"] = identity_subject_hash
    if status is not None:
        spec["status"] = status
    if roles is not None:
        spec["roles"] = roles
    if session_token_env is not None:
        spec["sessionTokenEnv"] = session_token_env
    if governance_scopes is not None:
        spec["governanceScopes"] = governance_scopes
    audit = _product_user_management_audit(
        index,
        actor_member=actor_member,
        action="update-product-user",
        target_user=user_id,
        reason=reason,
        permission_decision=permission,
    )
    spec.setdefault("managementAudit", []).append(audit)
    product_user = ProductUser.model_validate(data)
    write_yaml(path, product_user.model_dump(mode="json", exclude_none=True))
    _sync_product_user_member_binding(
        index.workspace_root,
        product_user,
        actor_member=actor_member,
        previous_member=index.product_users[user_id].spec.member,
    )
    return {"productUser": product_user, "permissionDecision": permission, "managementAudit": audit}


def archive_product_user(
    workspace_path: str | Path,
    user_id: str,
    *,
    actor_member: str,
    reason: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if user_id not in index.product_users:
        raise KeyError(f"unknown product user {user_id}")
    _validate_product_user_refs(index, actor_member=actor_member, member=None)
    permission = _product_user_permission_decision(
        index,
        actor_member=actor_member,
        path=f"/.aiteamos/product_users/{user_id}.yaml",
        reason=reason,
    )
    path = index.workspace_root / "product_users" / f"{user_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    spec["status"] = "archived"
    audit = _product_user_management_audit(
        index,
        actor_member=actor_member,
        action="archive-product-user",
        target_user=user_id,
        reason=reason,
        permission_decision=permission,
    )
    spec.setdefault("managementAudit", []).append(audit)
    product_user = ProductUser.model_validate(data)
    write_yaml(path, product_user.model_dump(mode="json", exclude_none=True))
    _sync_product_user_member_binding(index.workspace_root, product_user, actor_member=actor_member)
    return {"productUser": product_user, "permissionDecision": permission, "managementAudit": audit}


def create_skill(
    workspace_path: str | Path,
    *,
    name: str,
    actor_member: str,
    description: str | None = None,
    owner_member: str | None = None,
    projects: list[str] | None = None,
    capabilities: list[str] | None = None,
    required_permissions: list[str] | None = None,
    entrypoint: str | None = None,
    lifecycle: str = "active",
    reason: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    skill_id = _safe_id(name)
    if not skill_id:
        raise ValueError("skill name is required")
    if skill_id in index.skills:
        raise ValueError(f"skill {skill_id} already exists")
    owner = owner_member or actor_member
    project_refs = projects or [index.project.object_id]
    _validate_skill_refs(index, owner_member=owner, projects=project_refs, required_permissions=required_permissions or [])
    permission = _skill_permission_decision(
        index,
        actor_member=actor_member,
        path=f"/.aiteamos/skills/{skill_id}.yaml",
        reason=reason,
    )
    audit = _skill_decision_audit(
        index,
        actor_member=actor_member,
        decision="create-skill",
        reason=reason,
        permission_decision=permission,
        skill_id=skill_id,
    )
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "Skill",
        "metadata": {
            "name": skill_id,
            "title": name,
            "createdAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        },
        "spec": {
            "description": description,
            "ownerMember": owner,
            "projects": project_refs,
            "capabilities": capabilities or [],
            "requiredPermissions": required_permissions or [],
            "entrypoint": entrypoint,
            "lifecycle": lifecycle,
            "decisionAudit": [audit],
        },
    }
    skill = Skill.model_validate(payload)
    write_yaml(index.workspace_root / "skills" / f"{skill_id}.yaml", skill.model_dump(mode="json", exclude_none=True))
    _append_skill_event(
        index.workspace_root,
        {
            "event": "skill.created",
            "skill": skill_id,
            "actorMember": actor_member,
            "permissionDecision": permission.get("decision"),
        },
    )
    return {"skill": skill, "permissionDecision": permission, "decisionAudit": audit}


def update_skill(
    workspace_path: str | Path,
    skill_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if skill_id not in index.skills:
        raise KeyError(f"unknown skill {skill_id}")
    actor_member = updates.get("actorMember")
    if not actor_member:
        raise ValueError("actorMember is required")
    path = index.workspace_root / "skills" / f"{skill_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    owner = updates.get("ownerMember", spec.get("ownerMember"))
    projects = updates.get("projects", spec.get("projects") or [])
    required_permissions = updates.get("requiredPermissions", spec.get("requiredPermissions") or [])
    _validate_skill_refs(index, owner_member=owner, projects=projects, required_permissions=required_permissions)
    permission = _skill_permission_decision(
        index,
        actor_member=actor_member,
        path=f"/.aiteamos/skills/{skill_id}.yaml",
        reason=updates.get("reason"),
    )
    for key in ["description", "ownerMember", "projects", "capabilities", "requiredPermissions", "entrypoint", "lifecycle"]:
        if key in updates and updates[key] is not None:
            spec[key] = updates[key]
    audit = _skill_decision_audit(
        index,
        actor_member=actor_member,
        decision="update-skill",
        reason=updates.get("reason"),
        permission_decision=permission,
        skill_id=skill_id,
    )
    spec.setdefault("decisionAudit", []).append(audit)
    skill = Skill.model_validate(data)
    write_yaml(path, skill.model_dump(mode="json", exclude_none=True))
    _append_skill_event(
        index.workspace_root,
        {
            "event": "skill.updated",
            "skill": skill_id,
            "actorMember": actor_member,
            "permissionDecision": permission.get("decision"),
        },
    )
    return {"skill": skill, "permissionDecision": permission, "decisionAudit": audit}


def archive_skill(
    workspace_path: str | Path,
    skill_id: str,
    *,
    actor_member: str,
    reason: str | None = None,
) -> dict[str, Any]:
    return update_skill(
        workspace_path,
        skill_id,
        {
            "actorMember": actor_member,
            "lifecycle": "archived",
            "reason": reason or "Archive skill through reviewed lifecycle API.",
        },
    )


def attach_skill_to_member(
    workspace_path: str | Path,
    skill_id: str,
    *,
    actor_member: str,
    member: str,
    growth_summary: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if skill_id not in index.skills:
        raise KeyError(f"unknown skill {skill_id}")
    if member not in index.members:
        raise KeyError(f"unknown member {member}")
    skill = index.skills[skill_id]
    if skill.spec.lifecycle == "archived":
        raise ValueError(f"skill {skill_id} is archived")
    skill_permission = _skill_permission_decision(
        index,
        actor_member=actor_member,
        path=f"/.aiteamos/skills/{skill_id}.yaml",
        reason=reason,
    )
    member_permission = _skill_permission_decision(
        index,
        actor_member=actor_member,
        path=f"/.aiteamos/members/{member}.yaml",
        reason=reason,
    )

    member_path = index.workspace_root / "members" / f"{member}.yaml"
    member_data = read_yaml(member_path)
    member_spec = member_data.setdefault("spec", {})
    skills = list(member_spec.get("skills") or [])
    if skill_id not in skills:
        skills.append(skill_id)
    member_spec["skills"] = skills
    if growth_summary:
        member_spec.setdefault("growthRecords", []).append(
            {
                "recordedAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                "project": (skill.spec.projects or [index.project.object_id])[0],
                "summary": growth_summary,
                "evidence": [f"skill:{skill_id}", f"approvedBy:{actor_member}"],
            }
        )
    updated_member = TeamMember.model_validate(member_data)
    write_yaml(member_path, updated_member.model_dump(mode="json", exclude_none=True))

    skill_path = index.workspace_root / "skills" / f"{skill_id}.yaml"
    skill_data = read_yaml(skill_path)
    audit = _skill_decision_audit(
        index,
        actor_member=actor_member,
        decision="attach-skill-to-member",
        reason=reason,
        permission_decision=skill_permission,
        skill_id=skill_id,
        evidence=[{"kind": "member", "member": member, "growthRecordCreated": bool(growth_summary)}],
    )
    skill_data.setdefault("spec", {}).setdefault("decisionAudit", []).append(audit)
    updated_skill = Skill.model_validate(skill_data)
    write_yaml(skill_path, updated_skill.model_dump(mode="json", exclude_none=True))
    _append_skill_event(
        index.workspace_root,
        {
            "event": "skill.attached_to_member",
            "skill": skill_id,
            "member": member,
            "actorMember": actor_member,
            "permissionDecision": skill_permission.get("decision"),
        },
    )
    return {
        "skill": updated_skill,
        "member": updated_member,
        "permissionDecisions": [skill_permission, member_permission],
        "decisionAudit": audit,
    }


def record_member_growth(
    workspace_path: str | Path,
    member_id: str,
    *,
    actor_member: str,
    summary: str,
    project: str | None = None,
    source_action: str | None = None,
    source_task: str | None = None,
    source_run: str | None = None,
    source_review: str | None = None,
    source_memory_proposal: str | None = None,
    source_skill: str | None = None,
    evidence: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if member_id not in index.members:
        raise KeyError(f"unknown member {member_id}")
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    if actor_kind not in {"human", "hybrid"}:
        raise PermissionError("reviewed growth records require a human or hybrid reviewer")
    clean_summary = summary.strip()
    if not clean_summary:
        raise ValueError("growth summary is required")

    resolved_project = project or _project_for_growth_source(
        index,
        source_task=source_task,
        source_run=source_run,
        source_review=source_review,
        source_memory_proposal=source_memory_proposal,
        source_skill=source_skill,
    )
    if resolved_project != index.project.object_id:
        raise KeyError(f"unknown project {resolved_project}")
    _validate_growth_source_refs(
        index,
        member_id,
        project=resolved_project,
        source_action=source_action,
        source_task=source_task,
        source_run=source_run,
        source_review=source_review,
        source_memory_proposal=source_memory_proposal,
        source_skill=source_skill,
    )

    created_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
    evidence_refs = _unique_strings(
        list(evidence or [])
        + _optional_ref("task", source_task)
        + _optional_ref("run", source_run)
        + _optional_ref("review", source_review)
        + _optional_ref("memory-proposal", source_memory_proposal)
        + _optional_ref("skill", source_skill)
        + _optional_ref("growth-action", source_action)
    )
    audit = decision_audit_record(
        index,
        decision_kind="human_approval",
        decision="recorded-growth-note",
        actor_member=actor_member,
        authority="approve",
        reason=reason or "Reviewer recorded growth evidence from observed work.",
        source="member-growth-record",
        evidence=[_evidence_record(ref) for ref in evidence_refs],
        metadata={"member": member_id, "project": resolved_project},
    )
    record: dict[str, Any] = {
        "recordedAt": created_at,
        "project": resolved_project,
        "summary": clean_summary,
        "evidence": evidence_refs,
        "sourceAction": source_action,
        "sourceTask": source_task,
        "sourceRun": source_run,
        "sourceReview": source_review,
        "sourceMemoryProposal": source_memory_proposal,
        "sourceSkill": source_skill,
        "reviewedByMember": actor_member,
        "reviewedAt": created_at,
        "decisionAudit": [audit],
    }
    record = {key: value for key, value in record.items() if value is not None and value != []}

    member_path = index.workspace_root / "members" / f"{member_id}.yaml"
    member_data = read_yaml(member_path)
    member_data.setdefault("spec", {}).setdefault("growthRecords", []).append(record)
    updated_member = TeamMember.model_validate(member_data)
    write_yaml(member_path, updated_member.model_dump(mode="json", exclude_none=True))
    return {"member": updated_member, "growthRecord": record, "decisionAudit": audit}


def create_assignment(
    workspace_path: str | Path,
    *,
    name: str,
    member: str,
    project: str | None = None,
    role_template: str | None = None,
    role_context: str | None = None,
    title: str | None = None,
    status: str = "active",
    repositories: list[str] | None = None,
    modules: list[str] | None = None,
    features: list[str] | None = None,
    responsibilities: list[str] | None = None,
    scope: dict[str, Any] | None = None,
    permission_policies: list[str] | None = None,
    memory_bindings: list[str] | None = None,
    active_from: str | None = None,
    active_to: str | None = None,
) -> Assignment:
    index = load_workspace(workspace_path)
    assignment_id = _safe_id(name)
    if not assignment_id:
        raise ValueError("assignment name is required")
    if assignment_id in index.assignments:
        raise ValueError(f"assignment {assignment_id} already exists")
    project_id = project or index.project.object_id
    if project_id != index.project.object_id:
        raise KeyError(f"unknown project {project_id}")
    if member not in index.members:
        raise KeyError(f"unknown member {member}")
    if role_template and role_template not in index.role_templates:
        raise KeyError(f"unknown role template {role_template}")
    for repo in repositories or []:
        if repo not in index.repositories:
            raise KeyError(f"unknown repository {repo}")
    for binding in memory_bindings or []:
        if binding not in index.memory_bindings:
            raise KeyError(f"unknown memory binding {binding}")
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "Assignment",
        "metadata": {
            "name": assignment_id,
            "createdAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        },
        "spec": {
            "member": member,
            "project": project_id,
            "roleTemplate": role_template,
            "roleContext": role_context,
            "title": title,
            "status": status,
            "repositories": repositories or [],
            "modules": modules or [],
            "features": features or [],
            "responsibilities": responsibilities or [],
            "scope": scope or {},
            "permissionPolicies": permission_policies or [],
            "memoryBindings": memory_bindings or [],
            "activeFrom": active_from,
            "activeTo": active_to,
        },
    }
    assignment = Assignment.model_validate(payload)
    write_yaml(index.workspace_root / "assignments" / f"{assignment_id}.yaml", assignment.model_dump(mode="json", exclude_none=True))
    _link_assignment_to_member(index.workspace_root, member, project_id, assignment_id, responsibilities or [])
    return assignment


def update_assignment(workspace_path: str | Path, assignment_id: str, updates: dict[str, Any]) -> Assignment:
    index = load_workspace(workspace_path)
    if assignment_id not in index.assignments:
        raise KeyError(f"unknown assignment {assignment_id}")
    path = index.workspace_root / "assignments" / f"{assignment_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    for key in [
        "roleTemplate",
        "roleContext",
        "title",
        "status",
        "repositories",
        "modules",
        "features",
        "responsibilities",
        "scope",
        "permissionPolicies",
        "memoryBindings",
        "activeFrom",
        "activeTo",
    ]:
        if key in updates and updates[key] is not None:
            value = updates[key]
            if key == "scope" and isinstance(value, dict):
                current = spec.get("scope") if isinstance(spec.get("scope"), dict) else {}
                spec["scope"] = {**current, **value}
            else:
                spec[key] = value
    assignment = Assignment.model_validate(data)
    write_yaml(path, assignment.model_dump(mode="json", exclude_none=True))
    return assignment


def create_memory_binding(
    workspace_path: str | Path,
    *,
    name: str,
    target_type: str,
    target_id: str,
    store: str | None = None,
    entry: str | None = None,
    collection_path: str | None = None,
    access: list[str] | None = None,
    reason: str | None = None,
    created_by_member: str | None = None,
    status: str = "active",
) -> MemoryBinding:
    index = load_workspace(workspace_path)
    binding_id = _safe_id(name)
    if not binding_id:
        raise ValueError("memory binding name is required")
    if binding_id in index.memory_bindings:
        raise ValueError(f"memory binding {binding_id} already exists")
    if not (store or entry or collection_path):
        raise ValueError("memory binding requires store, entry, or collectionPath")
    if entry:
        if entry not in index.memory_entries:
            raise KeyError(f"unknown memory entry {entry}")
        entry_store = index.memory_entries[entry].spec.store
        if store and store != entry_store:
            raise ValueError(f"memory entry {entry} belongs to store {entry_store}, not {store}")
        store = store or entry_store
    if store and store not in index.memory_stores:
        raise KeyError(f"unknown memory store {store}")
    if collection_path and not store:
        raise ValueError("collectionPath binding requires a store")
    if created_by_member and created_by_member not in index.members:
        raise KeyError(f"unknown member {created_by_member}")
    _require_binding_target(index, target_type, target_id)
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "MemoryBinding",
        "metadata": {
            "id": binding_id,
            "createdAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        },
        "spec": {
            "store": store,
            "entry": entry,
            "collectionPath": collection_path,
            "targetType": target_type,
            "targetId": target_id,
            "access": access or ["read", "reference"],
            "reason": reason,
            "status": status,
            "createdByMember": created_by_member,
        },
    }
    binding = MemoryBinding.model_validate(payload)
    write_yaml(index.workspace_root / "memory" / "bindings" / f"{binding_id}.yaml", binding.model_dump(mode="json", exclude_none=True))
    _append_memory_event(
        index.workspace_root,
        {
            "type": "memory.binding.created",
            "memoryBinding": binding_id,
            "targetType": target_type,
            "targetId": target_id,
            "actorMember": created_by_member,
        },
    )
    return binding


def create_memory_store(
    workspace_path: str | Path,
    *,
    name: str,
    actor_member: str,
    store_type: str,
    owner_project: str | None = None,
    owner_member: str | None = None,
    owner_team: str | None = None,
    domain: str | None = None,
    description: str | None = None,
    visibility: str = "private",
    lifecycle: str = "active",
    acl: dict[str, Any] | None = None,
    retention: dict[str, Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    store_id = _safe_id(name)
    if not store_id:
        raise ValueError("memory store name is required")
    if store_id in index.memory_stores:
        raise ValueError(f"memory store {store_id} already exists")
    _require_reviewing_memory_actor(index, actor_member)
    if store_type == "project":
        owner_project = owner_project or index.project.object_id
    _validate_memory_store_owner(
        index,
        store_type=store_type,
        owner_project=owner_project,
        owner_member=owner_member,
        owner_team=owner_team,
        domain=domain,
    )
    created_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
    audit = decision_audit_record(
        index,
        decision_kind="human_approval",
        decision="created-memory-store",
        actor_member=actor_member,
        authority="approve",
        reason=reason or "reviewed memory store creation",
        source="memory-store-create",
        decided_at=created_at,
        evidence=[{"kind": "memory-store", "memoryStore": store_id, "storeType": store_type}],
    )
    store = MemoryStore.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryStore",
            "metadata": {
                "name": store_id,
                "title": name,
                "createdAt": created_at,
            },
            "spec": {
                "storeType": store_type,
                "ownerProject": owner_project,
                "ownerMember": owner_member,
                "ownerTeam": owner_team,
                "domain": domain,
                "description": description,
                "visibility": visibility,
                "lifecycle": lifecycle,
                "acl": acl or {},
                "retention": retention or {},
                "createdByMember": actor_member,
                "reviewReason": reason,
                "decisionAudit": [audit],
            },
        }
    )
    write_yaml(index.workspace_root / "memory" / "stores" / f"{store_id}.yaml", store.model_dump(mode="json", exclude_none=True))
    _append_memory_event(
        index.workspace_root,
        {
            "type": "memory.store.created",
            "memoryStore": store_id,
            "actorMember": actor_member,
            "storeType": store_type,
            "reason": reason,
        },
    )
    return {"store": store, "decisionAudit": audit}


def create_memory_entry(
    workspace_path: str | Path,
    *,
    title: str,
    content: str,
    actor_member: str,
    store: str,
    path: str | None = None,
    kind: str = "procedural",
    scope: str = "project",
    source: str | None = None,
    evidence: list[str] | None = None,
    confidence: float | None = None,
    freshness: str | None = None,
    sensitivity: str = "internal",
    visibility: str = "private",
    acl: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    related_projects: list[str] | None = None,
    related_members: list[str] | None = None,
    related_assignments: list[str] | None = None,
    lifecycle: str = "active",
    reason: str | None = None,
    bind_target_type: str | None = None,
    bind_target_id: str | None = None,
    bind_access: list[str] | None = None,
    bind_reason: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    _require_reviewing_memory_actor(index, actor_member)
    if store not in index.memory_stores:
        raise KeyError(f"unknown memory store {store}")
    if bool(bind_target_type) != bool(bind_target_id):
        raise ValueError("bindTargetType and bindTargetId must be provided together")
    if bind_target_type and bind_target_id:
        _require_binding_target(index, bind_target_type, bind_target_id)
    clean_title = title.strip()
    clean_content = content.strip()
    if not clean_title:
        raise ValueError("memory entry title is required")
    if not clean_content:
        raise ValueError("memory entry content is required")
    created_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
    memory_id = _unique_timestamped_id(index.workspace_root, "MEM", f"memory/entries/{store}")
    while memory_id in index.memory_entries:
        memory_id = _unique_timestamped_id(index.workspace_root, "MEM", f"memory/entries/{store}")
    entry_path = path.strip() if path and path.strip() else f"manual/{memory_id}.md"
    evidence_refs = _unique_ordered([str(item).strip() for item in evidence or [] if str(item).strip()])
    store_record = index.memory_stores[store]
    project_refs = _memory_related_projects(index, store_record, related_projects or [], bind_target_type, bind_target_id)
    member_refs = _memory_related_members(store_record, related_members or [], bind_target_type, bind_target_id)
    assignment_refs = _memory_related_assignments(related_assignments or [], bind_target_type, bind_target_id)
    content_sha = hashlib.sha256(clean_content.encode("utf-8")).hexdigest()
    audit = decision_audit_record(
        index,
        decision_kind="human_approval",
        decision="created-memory-entry",
        actor_member=actor_member,
        authority="approve",
        reason=reason or "reviewed memory entry creation",
        source="memory-entry-create",
        decided_at=created_at,
        evidence=[
            {
                "kind": "memory-entry",
                "memoryEntry": memory_id,
                "memoryStore": store,
                "contentSha256": content_sha,
                "evidence": evidence_refs,
            }
        ],
    )
    entry = MemoryEntry.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryEntry",
            "metadata": {"id": memory_id, "title": clean_title, "createdAt": created_at},
            "spec": {
                "store": store,
                "path": entry_path,
                "title": clean_title,
                "content": clean_content,
                "kind": kind,
                "scope": scope,
                "source": source,
                "evidence": evidence_refs,
                "confidence": confidence,
                "freshness": freshness,
                "lastVerifiedAt": created_at if lifecycle == "active" else None,
                "sensitivity": sensitivity,
                "visibility": visibility,
                "acl": acl or {},
                "tags": tags or [],
                "relatedProjects": project_refs,
                "relatedMembers": member_refs,
                "relatedAssignments": assignment_refs,
                "version": 1,
                "lineage": {
                    "authorMember": actor_member,
                    "reviewerMember": actor_member,
                    "evidence": evidence_refs,
                },
                "lifecycle": lifecycle,
                "embedding": {},
                "createdByMember": actor_member,
                "reviewReason": reason,
                "decisionAudit": [audit],
            },
        }
    )
    write_yaml(index.workspace_root / "memory" / "entries" / store / f"{memory_id}.yaml", entry.model_dump(mode="json", exclude_none=True))
    version = MemoryVersion.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryVersion",
            "metadata": {"id": f"{memory_id}-v1", "createdAt": created_at},
            "spec": {
                "entry": memory_id,
                "store": store,
                "version": 1,
                "operation": "create",
                "contentSha256": content_sha,
                "createdAt": created_at,
                "createdByMember": actor_member,
            },
        }
    )
    write_yaml(index.workspace_root / "memory" / "versions" / store / f"{memory_id}-v1.yaml", version.model_dump(mode="json", exclude_none=True))
    binding: MemoryBinding | None = None
    if bind_target_type and bind_target_id:
        binding = create_memory_binding(
            workspace_path,
            name=f"bind-{memory_id}-to-{bind_target_id}",
            target_type=bind_target_type,
            target_id=bind_target_id,
            store=store,
            entry=memory_id,
            access=bind_access or ["read", "reference", "inject"],
            reason=bind_reason or reason or f"Reviewed manual memory entry {memory_id}.",
            created_by_member=actor_member,
        )
    _append_memory_event(
        index.workspace_root,
        {
            "type": "memory.entry.created",
            "memoryEntry": memory_id,
            "memoryStore": store,
            "memoryVersion": version.object_id,
            "memoryBinding": binding.object_id if binding else None,
            "actorMember": actor_member,
            "reason": reason,
            "status": lifecycle,
        },
    )
    return {"memory": entry, "version": version, "binding": binding, "decisionAudit": audit}


def archive_memory_binding(workspace_path: str | Path, binding_id: str) -> MemoryBinding:
    index = load_workspace(workspace_path)
    if binding_id not in index.memory_bindings:
        raise KeyError(f"unknown memory binding {binding_id}")
    path = _memory_binding_manifest_path(index, binding_id)
    data = read_yaml(path)
    data.setdefault("spec", {})["status"] = "archived"
    binding = MemoryBinding.model_validate(data)
    write_yaml(path, binding.model_dump(mode="json", exclude_none=True))
    _append_memory_event(
        index.workspace_root,
        {
            "type": "memory.binding.archived",
            "memoryBinding": binding_id,
            "targetType": binding.spec.targetType,
            "targetId": binding.spec.targetId,
        },
    )
    return binding


def create_memory_grant(
    workspace_path: str | Path,
    *,
    grantee_member: str,
    grantor_member: str | None = None,
    task: str | None = None,
    run: str | None = None,
    stores: list[str] | None = None,
    entries: list[str] | None = None,
    access: list[str] | None = None,
    reason: str | None = None,
    expires_at: str | None = None,
    name: str | None = None,
) -> MemoryGrant:
    index = load_workspace(workspace_path)
    if grantee_member not in index.members:
        raise KeyError(f"unknown grantee member {grantee_member}")
    if grantor_member and grantor_member not in index.members:
        raise KeyError(f"unknown grantor member {grantor_member}")
    if task:
        if task not in index.tasks:
            raise KeyError(f"unknown task {task}")
        assigned = index.tasks[task].spec.assignedMember
        if assigned and assigned != grantee_member:
            raise ValueError(f"task {task} is assigned to {assigned}, not {grantee_member}")
    if run:
        if run not in index.runs:
            raise KeyError(f"unknown run {run}")
        if index.runs[run].spec.member != grantee_member:
            raise ValueError(f"run {run} belongs to member {index.runs[run].spec.member}, not {grantee_member}")
    if not (stores or entries):
        raise ValueError("memory grant requires at least one store or entry")
    for store_id in stores or []:
        if store_id not in index.memory_stores:
            raise KeyError(f"unknown memory store {store_id}")
    for entry_id in entries or []:
        if entry_id not in index.memory_entries:
            raise KeyError(f"unknown memory entry {entry_id}")
    grant_id = _safe_id(name) if name else _unique_timestamped_id(index.workspace_root, "GRANT", "memory/grants")
    if grant_id in index.memory_grants:
        raise ValueError(f"memory grant {grant_id} already exists")
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "MemoryGrant",
        "metadata": {
            "id": grant_id,
            "createdAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        },
        "spec": {
            "granteeMember": grantee_member,
            "grantorMember": grantor_member,
            "task": task,
            "run": run,
            "stores": stores or [],
            "entries": entries or [],
            "access": access or ["read", "reference", "inject"],
            "reason": reason,
            "expiresAt": expires_at,
            "status": "active",
        },
    }
    grant = MemoryGrant.model_validate(payload)
    write_yaml(index.workspace_root / "memory" / "grants" / f"{grant_id}.yaml", grant.model_dump(mode="json", exclude_none=True))
    _append_memory_event(
        index.workspace_root,
        {
            "type": "memory.grant.created",
            "memoryGrant": grant_id,
            "granteeMember": grantee_member,
            "grantorMember": grantor_member,
            "task": task,
            "run": run,
        },
    )
    return grant


def revoke_memory_grant(
    workspace_path: str | Path,
    grant_id: str,
    *,
    reason: str | None = None,
    revoked_by_member: str | None = None,
) -> MemoryGrant:
    index = load_workspace(workspace_path)
    if grant_id not in index.memory_grants:
        raise KeyError(f"unknown memory grant {grant_id}")
    if revoked_by_member and revoked_by_member not in index.members:
        raise KeyError(f"unknown member {revoked_by_member}")
    path = index.workspace_root / "memory" / "grants" / f"{grant_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    spec["status"] = "revoked"
    spec["revokedAt"] = now
    spec["revokedByMember"] = revoked_by_member
    spec["revokedReason"] = (reason or "memory grant revoked").strip()
    grant = MemoryGrant.model_validate(data)
    write_yaml(path, grant.model_dump(mode="json", exclude_none=True))
    _append_memory_event(
        index.workspace_root,
        {
            "type": "memory.grant.revoked",
            "memoryGrant": grant_id,
            "actorMember": revoked_by_member,
            "reason": spec["revokedReason"],
            "granteeMember": grant.spec.granteeMember,
        },
    )
    return grant


def share_memory(
    workspace_path: str | Path,
    *,
    from_member: str,
    to_member: str,
    stores: list[str] | None = None,
    entries: list[str] | None = None,
    task: str | None = None,
    run: str | None = None,
    reason: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    grant = create_memory_grant(
        workspace_path,
        grantee_member=to_member,
        grantor_member=from_member,
        task=task,
        run=run,
        stores=stores,
        entries=entries,
        access=["read", "reference", "inject"],
        reason=reason or "member-to-member memory share",
        expires_at=expires_at,
    )
    index = load_workspace(workspace_path)
    project = None
    if task and task in index.tasks:
        project = index.tasks[task].spec.project
    elif run and run in index.runs:
        project = index.runs[run].spec.project
    message_id = _unique_timestamped_id(index.workspace_root, "MSG", "im/messages")
    message = MemberMessage.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemberMessage",
            "metadata": {"id": message_id, "createdAt": datetime.now().astimezone().isoformat(timespec="milliseconds")},
            "spec": {
                "fromMember": from_member,
                "toMembers": [to_member],
                "messageType": "knowledge-share",
                "project": project,
                "task": task,
                "run": run,
                "body": reason or f"Shared memory grant {grant.object_id}.",
                "attachments": [grant.object_id],
                "audit": {"source": "memory-share-api", "memoryGrant": grant.object_id},
            },
        }
    )
    write_yaml(index.workspace_root / "im" / "messages" / f"{message_id}.yaml", message.model_dump(mode="json", exclude_none=True))
    return {"grant": grant, "message": message}


def record_member_message(
    workspace_path: str | Path,
    *,
    from_member: str,
    body: str,
    to_members: list[str] | None = None,
    channel: str | None = None,
    message_type: str = "message",
    project: str | None = None,
    task: str | None = None,
    run: str | None = None,
    attachments: list[str] | None = None,
    priority: str = "normal",
    requested_response_by: str | None = None,
    audit: dict[str, Any] | None = None,
    source: str = "api",
) -> MemberMessage:
    index = load_workspace(workspace_path)
    if from_member not in index.members:
        raise KeyError(f"unknown from member {from_member}")
    for member_id in to_members or []:
        if member_id not in index.members:
            raise KeyError(f"unknown to member {member_id}")
    project_id = project or index.project.object_id
    if project_id != index.project.object_id:
        raise KeyError(f"unknown project {project_id}")
    if task:
        if task not in index.tasks:
            raise KeyError(f"unknown task {task}")
        task_project = index.tasks[task].spec.project
        if task_project != project_id:
            raise ValueError(f"task {task} belongs to project {task_project}, not {project_id}")
    if run:
        if run not in index.runs:
            raise KeyError(f"unknown run {run}")
        run_record = index.runs[run]
        if task and run_record.spec.task != task:
            raise ValueError(f"run {run} belongs to task {run_record.spec.task}, not {task}")
        if run_record.spec.project != project_id:
            raise ValueError(f"run {run} belongs to project {run_record.spec.project}, not {project_id}")
    message_id = _unique_timestamped_id(index.workspace_root, "MSG", "im/messages")
    payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "MemberMessage",
        "metadata": {"id": message_id, "createdAt": datetime.now().astimezone().isoformat(timespec="milliseconds")},
        "spec": {
            "fromMember": from_member,
            "toMembers": to_members or [],
            "channel": channel,
            "messageType": message_type,
            "status": "open",
            "priority": priority,
            "project": project_id,
            "task": task,
            "run": run,
            "body": body,
            "attachments": attachments or [],
            "requestedResponseBy": requested_response_by,
            "audit": {"source": source, **(audit or {})},
        },
    }
    message = MemberMessage.model_validate(payload)
    write_yaml(index.workspace_root / "im" / "messages" / f"{message_id}.yaml", message.model_dump(mode="json", exclude_none=True))
    if run:
        _append_run_event(
            index.workspace_root,
            run,
            {
                "type": "member.message.recorded",
                "actorMember": from_member,
                "message": message_id,
                "messageType": message.spec.messageType,
                "source": source,
            },
        )
    return message


def ask_for_help(
    workspace_path: str | Path,
    *,
    from_member: str,
    to_members: list[str],
    question: str,
    project: str | None = None,
    task: str | None = None,
    run: str | None = None,
    priority: str = "normal",
    requested_response_by: str | None = None,
    attachments: list[str] | None = None,
    source: str = "api",
) -> MemberMessage:
    if not to_members:
        raise ValueError("ask-for-help requires at least one recipient")
    return record_member_message(
        workspace_path,
        from_member=from_member,
        to_members=to_members,
        message_type="ask-for-help",
        body=question,
        project=project,
        task=task,
        run=run,
        attachments=attachments,
        priority=priority,
        requested_response_by=requested_response_by,
        source=source,
        audit={"workflow": "ask-for-help"},
    )


def request_review(
    workspace_path: str | Path,
    *,
    from_member: str,
    to_members: list[str],
    body: str,
    review_kind: str = "code",
    project: str | None = None,
    task: str | None = None,
    run: str | None = None,
    priority: str = "normal",
    requested_response_by: str | None = None,
    attachments: list[str] | None = None,
    source: str = "api",
) -> MemberMessage:
    if not to_members:
        raise ValueError("review request requires at least one reviewer")
    return record_member_message(
        workspace_path,
        from_member=from_member,
        to_members=to_members,
        message_type="review-request",
        body=body,
        project=project,
        task=task,
        run=run,
        attachments=attachments,
        priority=priority,
        requested_response_by=requested_response_by,
        source=source,
        audit={"workflow": "review-request", "reviewKind": review_kind},
    )


def resolve_member_message(
    workspace_path: str | Path,
    message_id: str,
    *,
    actor_member: str,
    resolution: str,
    status: str = "resolved",
    allow_connector_escalation_resolution: bool = False,
) -> MemberMessage:
    index = load_workspace(workspace_path)
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    if message_id not in index.member_messages:
        raise KeyError(f"unknown member message {message_id}")
    if status not in {"acknowledged", "resolved", "archived"}:
        raise ValueError(f"unsupported member message status {status}")
    message = index.member_messages[message_id]
    if (
        message.spec.audit.get("source") == "connector-failure-escalation"
        and status in {"resolved", "archived"}
        and not allow_connector_escalation_resolution
    ):
        raise ValueError("connector failure escalation review requests must be closed through the connector escalation resolution workflow")
    participants = {message.spec.fromMember, *message.spec.toMembers}
    if actor_member not in participants:
        raise ValueError(f"actor member {actor_member} is not a participant in message {message_id}")
    path = _member_message_manifest_path(index, message_id)
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    spec["status"] = status
    spec["resolvedAt"] = datetime.now().astimezone().isoformat(timespec="milliseconds")
    spec["resolvedByMember"] = actor_member
    spec["resolution"] = resolution
    audit = spec.setdefault("audit", {})
    audit["lastResolution"] = {"actorMember": actor_member, "status": status}
    resolved = MemberMessage.model_validate(data)
    write_yaml(path, resolved.model_dump(mode="json", exclude_none=True))
    if resolved.spec.run:
        _append_run_event(
            index.workspace_root,
            resolved.spec.run,
            {
                "type": "member.message.resolved",
                "actorMember": actor_member,
                "message": message_id,
                "status": status,
            },
        )
    return resolved


def create_team_retrospective(
    workspace_path: str | Path,
    *,
    facilitator_member: str,
    summary: str,
    participants: list[str] | None = None,
    project: str | None = None,
    source_task_plan: str | None = None,
    source_runs: list[str] | None = None,
    source_tasks: list[str] | None = None,
    source_messages: list[str] | None = None,
    source_handoffs: list[str] | None = None,
    lessons: list[str] | None = None,
    action_items: list[str] | None = None,
    memory_kind: str = "procedural",
    confidence: float | None = 0.8,
    review_guidance: str | None = None,
    source: str = "api",
) -> dict[str, TeamRetrospective | MemoryProposal]:
    index = load_workspace(workspace_path)
    project_id = project or index.project.object_id
    if project_id != index.project.object_id:
        raise KeyError(f"unknown project {project_id}")
    if facilitator_member not in index.members:
        raise KeyError(f"unknown facilitator member {facilitator_member}")
    participants = _unique_ordered([facilitator_member, *(participants or [])])
    for member in participants:
        if member not in index.members:
            raise KeyError(f"unknown participant member {member}")
    source_runs = _unique_ordered(source_runs or [])
    source_tasks = _unique_ordered(source_tasks or [])
    source_messages = _unique_ordered(source_messages or [])
    source_handoffs = _unique_ordered(source_handoffs or [])
    if source_task_plan:
        if source_task_plan not in index.task_plans:
            raise KeyError(f"unknown source task plan {source_task_plan}")
        task_plan_project = index.task_plans[source_task_plan].spec.project or index.project.object_id
        if task_plan_project != project_id:
            raise ValueError(f"task plan {source_task_plan} belongs to project {task_plan_project}, not {project_id}")
    if not any([source_task_plan, source_runs, source_tasks, source_messages, source_handoffs]):
        raise ValueError("team retrospective requires at least one source task plan, run, task, message, or handoff")
    for run_id in source_runs:
        if run_id not in index.runs:
            raise KeyError(f"unknown source run {run_id}")
        if index.runs[run_id].spec.project != project_id:
            raise ValueError(f"run {run_id} belongs to project {index.runs[run_id].spec.project}, not {project_id}")
    for task_id in source_tasks:
        if task_id not in index.tasks:
            raise KeyError(f"unknown source task {task_id}")
        if index.tasks[task_id].spec.project != project_id:
            raise ValueError(f"task {task_id} belongs to project {index.tasks[task_id].spec.project}, not {project_id}")
    for message_id in source_messages:
        if message_id not in index.member_messages:
            raise KeyError(f"unknown source message {message_id}")
        message_project = index.member_messages[message_id].spec.project
        if message_project and message_project != project_id:
            raise ValueError(f"message {message_id} belongs to project {message_project}, not {project_id}")
    for handoff_id in source_handoffs:
        if handoff_id not in index.handoffs:
            raise KeyError(f"unknown source handoff {handoff_id}")
        handoff_project = index.handoffs[handoff_id].spec.project
        if handoff_project and handoff_project != project_id:
            raise ValueError(f"handoff {handoff_id} belongs to project {handoff_project}, not {project_id}")

    retrospective_id = _unique_timestamped_id(index.workspace_root, "RETRO", "im/retrospectives")
    evidence = [
        f"retrospective:{retrospective_id}",
        *([f"task-plan:{source_task_plan}"] if source_task_plan else []),
        *[f"run:{run_id}" for run_id in source_runs],
        *[f"task:{task_id}" for task_id in source_tasks],
        *[f"message:{message_id}" for message_id in source_messages],
        *[f"handoff:{handoff_id}" for handoff_id in source_handoffs],
    ]
    proposal = propose_memory(
        workspace_path,
        project=project_id,
        member=facilitator_member,
        source_run=source_runs[0] if source_runs else None,
        source_task=source_tasks[0] if source_tasks else (index.runs[source_runs[0]].spec.task if source_runs else None),
        source_extractor_id="team-retrospective",
        dedupe_key=_retrospective_dedupe_key(project_id, source_task_plan, source_runs, source_tasks, source_messages, source_handoffs, summary),
        title=f"Team retrospective: {summary[:72]}",
        content=_retrospective_memory_content(summary, lessons or [], action_items or []),
        kind=memory_kind,
        confidence=confidence,
        evidence=evidence,
        review_guidance=review_guidance or "Review this team retrospective before promoting it to project or team memory.",
    )
    payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "TeamRetrospective",
        "metadata": {"id": retrospective_id, "createdAt": datetime.now().astimezone().isoformat(timespec="milliseconds")},
        "spec": {
            "project": project_id,
            "facilitatorMember": facilitator_member,
            "participants": participants,
            "sourceTaskPlan": source_task_plan,
            "sourceRuns": source_runs,
            "sourceTasks": source_tasks,
            "sourceMessages": source_messages,
            "sourceHandoffs": source_handoffs,
            "summary": summary,
            "lessons": lessons or [],
            "actionItems": action_items or [],
            "proposedMemory": proposal.object_id,
            "status": "proposed",
            "audit": {"source": source},
        },
    }
    retrospective = TeamRetrospective.model_validate(payload)
    write_yaml(index.workspace_root / "im" / "retrospectives" / f"{retrospective_id}.yaml", retrospective.model_dump(mode="json", exclude_none=True))
    return {"retrospective": retrospective, "proposal": proposal}


def create_task_plan_retrospective(
    workspace_path: str | Path,
    task_plan_id: str,
    *,
    facilitator_member: str,
    summary: str,
    participants: list[str] | None = None,
    lessons: list[str] | None = None,
    action_items: list[str] | None = None,
    memory_kind: str = "procedural",
    confidence: float | None = 0.8,
    review_guidance: str | None = None,
    source: str = "api",
) -> dict[str, TeamRetrospective | MemoryProposal]:
    index = load_workspace(workspace_path)
    if task_plan_id not in index.task_plans:
        raise KeyError(f"unknown task plan {task_plan_id}")
    task_plan = index.task_plans[task_plan_id]
    project_id = task_plan.spec.project or index.project.object_id
    if project_id != index.project.object_id:
        raise KeyError(f"unknown project {project_id}")
    if task_plan.spec.status == "draft":
        raise ValueError(f"task plan {task_plan_id} is still draft")

    view = task_plan_execution_view(index, task_plan_id)
    subtask_rows = view["spec"]["subtasks"]
    incomplete = [row for row in subtask_rows if row["actualState"] != "completed"]
    terminal_without_execution = task_plan.spec.status in {"rejected", "superseded"}
    if incomplete and not terminal_without_execution:
        blockers = ", ".join(f"{row['index']}:{row['actualState']}" for row in incomplete[:5])
        raise ValueError(f"task plan {task_plan_id} is not complete; incomplete subtasks: {blockers}")

    source_runs = _unique_ordered([run_id for row in subtask_rows for run_id in row["runs"]])
    source_tasks = _unique_ordered([task_id for row in subtask_rows for task_id in row["tasks"]])
    if task_plan.spec.sourceTask and task_plan.spec.sourceTask in index.tasks:
        source_tasks = _unique_ordered([task_plan.spec.sourceTask, *source_tasks])

    planned_participants = [
        task_plan.spec.createdByMember,
        *[row.get("assignedMember") for row in subtask_rows],
        *(participants or []),
    ]
    known_participants = [member for member in planned_participants if isinstance(member, str) and member in index.members]
    return create_team_retrospective(
        workspace_path,
        facilitator_member=facilitator_member,
        participants=known_participants,
        project=project_id,
        source_task_plan=task_plan_id,
        source_runs=source_runs,
        source_tasks=source_tasks,
        summary=summary,
        lessons=lessons,
        action_items=action_items,
        memory_kind=memory_kind,
        confidence=confidence,
        review_guidance=review_guidance or "Review this task-plan retrospective before promoting it to project or team memory.",
        source=source,
    )


def create_permission_request(
    workspace_path: str | Path,
    *,
    member: str,
    action: dict[str, Any],
    project: str | None = None,
    assignment: str | None = None,
    task: str | None = None,
    run: str | None = None,
    automation: str | None = None,
    automation_run: str | None = None,
    requester_member: str | None = None,
    reason: str | None = None,
    expires_at: str | None = None,
    current_decision: dict[str, Any] | None = None,
    source: str | None = None,
    name: str | None = None,
) -> PermissionRequest:
    index = load_workspace(workspace_path)
    project_id = project or index.project.object_id
    if project_id != index.project.object_id:
        raise KeyError(f"unknown project {project_id}")
    if member not in index.members:
        raise KeyError(f"unknown member {member}")
    if assignment:
        if assignment not in index.assignments:
            raise KeyError(f"unknown assignment {assignment}")
        assignment_record = index.assignments[assignment]
        if assignment_record.spec.member != member:
            raise ValueError(f"assignment {assignment} belongs to member {assignment_record.spec.member}, not {member}")
        if assignment_record.spec.project != project_id:
            raise ValueError(f"assignment {assignment} belongs to project {assignment_record.spec.project}, not {project_id}")
    if task and task not in index.tasks:
        raise KeyError(f"unknown task {task}")
    if run and run not in index.runs:
        raise KeyError(f"unknown run {run}")
    if automation and automation not in index.automations:
        raise KeyError(f"unknown automation {automation}")
    if automation_run and automation_run not in index.automation_runs:
        raise KeyError(f"unknown automation run {automation_run}")
    if requester_member and requester_member not in index.members:
        raise KeyError(f"unknown requester member {requester_member}")
    if not action:
        raise ValueError("permission request requires an action")
    request_id = _safe_id(name) if name else _unique_timestamped_id(index.workspace_root, "PREQ", "permission_requests")
    if request_id in index.permission_requests:
        raise ValueError(f"permission request {request_id} already exists")
    decision_audit = []
    if current_decision:
        decision_audit.append(
            decision_audit_record(
                index,
                decision_kind="service_policy_decision",
                decision=str(current_decision.get("decision") or "pending"),
                actor_member=None,
                authority="enforce",
                reason=str(current_decision.get("reason") or reason or "permission evaluator recorded the current policy decision"),
                source="permission-evaluator",
                policy_refs=list(current_decision.get("selectedPolicyIds") or []),
                evidence=[
                    {
                        "kind": "permission-explain",
                        "matchedRules": current_decision.get("matchedRules", []),
                        "matchedGrants": current_decision.get("matchedGrants", []),
                        "blockers": current_decision.get("blockers", []),
                        "warnings": current_decision.get("warnings", []),
                    }
                ],
                requires_human_review=True,
                risk_assessment=current_decision.get("riskAssessment"),
            )
        )
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "PermissionRequest",
        "metadata": {
            "id": request_id,
            "createdAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        },
        "spec": {
            "project": project_id,
            "member": member,
            "assignment": assignment,
            "task": task,
            "run": run,
            "automation": automation,
            "automationRun": automation_run,
            "approvalWorkflow": approval_workflow_id("PermissionRequest", request_id),
            "requesterMember": requester_member,
            "action": action,
            "reason": reason,
            "status": "pending",
            "currentDecision": current_decision or {},
            "expiresAt": expires_at,
            "source": source,
            "decisionAudit": decision_audit,
        },
    }
    request = PermissionRequest.model_validate(payload)
    write_subject_approval_workflow(
        index,
        subject_kind="PermissionRequest",
        subject_ref=request.object_id,
        project=request.spec.project,
        requester_member=request.spec.requesterMember or request.spec.member,
        status=request.spec.status,
        stage_id="permission-review",
        stage_kind="any-of",
        decision_audit=[item.model_dump(mode="json", exclude_none=True) for item in request.spec.decisionAudit],
        subject_record=request.model_dump(mode="json", exclude_none=True),
        reason=reason,
    )
    _append_permission_event(
        index.workspace_root,
        {
            "type": "permission.request.created",
            "permissionRequest": request_id,
            "member": member,
            "assignment": assignment,
            "project": project_id,
            "requesterMember": requester_member,
        },
    )
    return request


def approve_permission_request(
    workspace_path: str | Path,
    request_id: str,
    *,
    reviewer_member: str,
    reason: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if request_id not in index.permission_requests:
        raise KeyError(f"unknown permission request {request_id}")
    if reviewer_member not in index.members:
        raise KeyError(f"unknown reviewer member {reviewer_member}")
    if index.members[reviewer_member].spec.kind != "human":
        raise ValueError("permission request approval requires a human reviewer member")
    request = index.permission_requests[request_id]
    request_data = request.model_dump(mode="json", exclude_none=True)
    if request.spec.status != "pending":
        raise ValueError(f"permission request {request_id} is {request.spec.status}, not pending")
    decided_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
    grant_expires_at = expires_at or request.spec.expiresAt or (datetime.now().astimezone() + timedelta(hours=24)).isoformat(timespec="milliseconds")
    grant_id = _unique_timestamped_id(index.workspace_root, "PGRANT", "permission_grants")
    approval_audit = decision_audit_record(
        index,
        decision_kind="human_approval",
        decision="approved",
        actor_member=reviewer_member,
        authority="approve",
        reason=reason or request.spec.reason or "permission request approved",
        source="permission-request-review",
        decided_at=decided_at,
        policy_refs=list(request.spec.currentDecision.get("selectedPolicyIds") or []),
        evidence=[
            {
                "kind": "permission-request",
                "permissionRequest": request_id,
                "currentDecision": request.spec.currentDecision,
            }
        ],
        risk_assessment=request.spec.currentDecision.get("riskAssessment"),
    )
    grant = PermissionGrant.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "PermissionGrant",
            "metadata": {
                "id": grant_id,
                "createdAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            },
            "spec": {
                "scope": {
                    key: value
                    for key, value in {
                        "project": request.spec.project,
                        "member": request.spec.member,
                        "assignment": request.spec.assignment,
                    }.items()
                    if value
                },
                "action": request.spec.action,
                "sourceRequest": request_id,
                "approvedByMember": reviewer_member,
                "reason": reason or request.spec.reason or "permission request approved",
                "status": "active",
                "expiresAt": grant_expires_at,
                "decisionAudit": [
                    {
                        **approval_audit,
                        "decision": "allowed",
                        "metadata": {
                            **approval_audit.get("metadata", {}),
                            "permissionRequest": request_id,
                        },
                    }
                ],
            },
        }
    )
    write_yaml(index.workspace_root / "permission_grants" / f"{grant_id}.yaml", grant.model_dump(mode="json", exclude_none=True))

    request_data.setdefault("spec", {})["status"] = "approved"
    request_data["spec"]["approvalWorkflow"] = approval_workflow_id("PermissionRequest", request_id)
    request_data["spec"]["reviewerMember"] = reviewer_member
    request_data["spec"]["decidedAt"] = decided_at
    request_data["spec"]["expiresAt"] = grant_expires_at
    request_data["spec"]["grant"] = grant_id
    request_data["spec"].setdefault("audit", {})["approvalReason"] = reason
    request_data["spec"].setdefault("decisionAudit", []).append(
        {
            **approval_audit,
            "metadata": {
                **approval_audit.get("metadata", {}),
                "permissionGrant": grant_id,
            },
        }
    )
    updated_request = PermissionRequest.model_validate(request_data)
    write_subject_approval_workflow(
        index,
        subject_kind="PermissionRequest",
        subject_ref=updated_request.object_id,
        project=updated_request.spec.project,
        requester_member=updated_request.spec.requesterMember or updated_request.spec.member,
        owner_member=reviewer_member,
        status=updated_request.spec.status,
        stage_id="permission-review",
        stage_kind="any-of",
        reviewer_members=[reviewer_member],
        approvals=[grant_id],
        decision_audit=[item.model_dump(mode="json", exclude_none=True) for item in updated_request.spec.decisionAudit],
        subject_record=updated_request.model_dump(mode="json", exclude_none=True),
        reason=reason or updated_request.spec.reason,
        decided_at=decided_at,
    )
    _append_permission_event(
        index.workspace_root,
        {
            "type": "permission.request.approved",
            "permissionRequest": request_id,
            "permissionGrant": grant_id,
            "member": request.spec.member,
            "reviewerMember": reviewer_member,
            "expiresAt": grant_expires_at,
        },
    )
    return {"request": updated_request, "grant": grant}


def reject_permission_request(
    workspace_path: str | Path,
    request_id: str,
    *,
    reviewer_member: str,
    reason: str | None = None,
) -> PermissionRequest:
    index = load_workspace(workspace_path)
    if request_id not in index.permission_requests:
        raise KeyError(f"unknown permission request {request_id}")
    if reviewer_member not in index.members:
        raise KeyError(f"unknown reviewer member {reviewer_member}")
    if index.members[reviewer_member].spec.kind != "human":
        raise ValueError("permission request rejection requires a human reviewer member")
    request = index.permission_requests[request_id]
    request_data = request.model_dump(mode="json", exclude_none=True)
    if request.spec.status != "pending":
        raise ValueError(f"permission request {request_id} is {request.spec.status}, not pending")
    decided_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
    request_data.setdefault("spec", {})["status"] = "rejected"
    request_data["spec"]["approvalWorkflow"] = approval_workflow_id("PermissionRequest", request_id)
    request_data["spec"]["reviewerMember"] = reviewer_member
    request_data["spec"]["decidedAt"] = decided_at
    request_data["spec"].setdefault("audit", {})["rejectionReason"] = reason
    request_data["spec"].setdefault("decisionAudit", []).append(
        decision_audit_record(
            index,
            decision_kind="human_approval",
            decision="rejected",
            actor_member=reviewer_member,
            authority="approve",
            reason=reason or "permission request rejected",
            source="permission-request-review",
            decided_at=decided_at,
            policy_refs=list(request.spec.currentDecision.get("selectedPolicyIds") or []),
            evidence=[
                {
                    "kind": "permission-request",
                    "permissionRequest": request_id,
                    "currentDecision": request.spec.currentDecision,
                }
            ],
            risk_assessment=request.spec.currentDecision.get("riskAssessment"),
        )
    )
    updated_request = PermissionRequest.model_validate(request_data)
    write_subject_approval_workflow(
        index,
        subject_kind="PermissionRequest",
        subject_ref=updated_request.object_id,
        project=updated_request.spec.project,
        requester_member=updated_request.spec.requesterMember or updated_request.spec.member,
        owner_member=reviewer_member,
        status=updated_request.spec.status,
        stage_id="permission-review",
        stage_kind="any-of",
        reviewer_members=[reviewer_member],
        decision_audit=[item.model_dump(mode="json", exclude_none=True) for item in updated_request.spec.decisionAudit],
        subject_record=updated_request.model_dump(mode="json", exclude_none=True),
        reason=reason or updated_request.spec.reason,
        decided_at=decided_at,
    )
    _append_permission_event(
        index.workspace_root,
        {
            "type": "permission.request.rejected",
            "permissionRequest": request_id,
            "member": request.spec.member,
            "reviewerMember": reviewer_member,
            "reason": reason,
        },
    )
    return updated_request


def revoke_permission_grant(
    workspace_path: str | Path,
    grant_id: str,
    *,
    actor_member: str | None = None,
    reason: str | None = None,
) -> PermissionGrant:
    index = load_workspace(workspace_path)
    if grant_id not in index.permission_grants:
        raise KeyError(f"unknown permission grant {grant_id}")
    if actor_member and actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    grant_path = index.workspace_root / "permission_grants" / f"{grant_id}.yaml"
    grant_data = read_yaml(grant_path)
    grant = PermissionGrant.model_validate(grant_data)
    if grant.spec.status == "revoked":
        return grant
    spec = grant_data.setdefault("spec", {})
    spec["status"] = "revoked"
    audit = spec.setdefault("audit", {})
    revoked_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
    audit["revokedAt"] = revoked_at
    audit["revokedByMember"] = actor_member
    audit["revocationReason"] = reason or "permission grant revoked"
    spec.setdefault("decisionAudit", []).append(
        decision_audit_record(
            index,
            decision_kind="human_approval" if actor_member and index.members.get(actor_member, None) and index.members[actor_member].spec.kind == "human" else "system_check",
            decision="revoked",
            actor_member=actor_member,
            authority="revoke",
            reason=reason or "permission grant revoked",
            source="permission-grant-lifecycle",
            decided_at=revoked_at,
            evidence=[{"kind": "permission-grant", "permissionGrant": grant_id}],
        )
    )
    updated = PermissionGrant.model_validate(grant_data)
    write_yaml(grant_path, updated.model_dump(mode="json", exclude_none=True))
    _append_permission_event(
        index.workspace_root,
        {
            "type": "permission.grant.revoked",
            "permissionGrant": grant_id,
            "actorMember": actor_member,
            "reason": reason,
        },
    )
    return updated


def expire_permission_grants(workspace_path: str | Path) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    now = datetime.now().astimezone()
    expired: list[str] = []
    for grant_id, grant in index.permission_grants.items():
        if grant.spec.status != "active" or not grant.spec.expiresAt:
            continue
        try:
            expires_at = datetime.fromisoformat(grant.spec.expiresAt)
        except ValueError:
            continue
        comparable_now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else now.replace(tzinfo=None)
        if expires_at > comparable_now:
            continue
        grant_path = index.workspace_root / "permission_grants" / f"{grant_id}.yaml"
        data = read_yaml(grant_path)
        spec = data.setdefault("spec", {})
        spec["status"] = "expired"
        expired_at = now.isoformat(timespec="milliseconds")
        spec.setdefault("audit", {})["expiredAt"] = expired_at
        spec.setdefault("decisionAudit", []).append(
            decision_audit_record(
                index,
                decision_kind="system_check",
                decision="expired",
                authority="expire",
                reason="permission grant expired",
                source="permission-grant-lifecycle",
                decided_at=expired_at,
                evidence=[{"kind": "permission-grant", "permissionGrant": grant_id}],
            )
        )
        updated = PermissionGrant.model_validate(data)
        write_yaml(grant_path, updated.model_dump(mode="json", exclude_none=True))
        expired.append(grant_id)
    if expired:
        _append_permission_event(
            index.workspace_root,
            {
                "type": "permission.grants.expired",
                "permissionGrants": expired,
            },
        )
    return {"expired": expired, "expiredCount": len(expired)}


def create_task(
    workspace_path: str | Path,
    *,
    title: str,
    project: str | None = None,
    assigned_member: str | None = None,
    assignment: str | None = None,
    priority: str = "normal",
    status: str = "TODO",
    risk_class: str | None = None,
    execution_mode: str | None = "assisted",
    acceptance: list[str] | None = None,
    markdown: str | None = None,
) -> Task:
    index = load_workspace(workspace_path)
    now = datetime.now().astimezone()
    task_id = timestamp_task_id(now)
    project_name = project or index.project.object_id
    if project_name != index.project.object_id:
        raise KeyError(f"unknown project {project_name}")
    if assigned_member and assigned_member not in index.members:
        raise KeyError(f"unknown member {assigned_member}")
    if assignment:
        if assignment not in index.assignments:
            raise KeyError(f"unknown assignment {assignment}")
        assignment_record = index.assignments[assignment]
        if assignment_record.spec.project != project_name:
            raise ValueError(f"assignment {assignment} belongs to project {assignment_record.spec.project}, not {project_name}")
        if assigned_member and assignment_record.spec.member != assigned_member:
            raise ValueError(f"assignment {assignment} belongs to {assignment_record.spec.member}, not {assigned_member}")
        assigned_member = assigned_member or assignment_record.spec.member
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "Task",
        "metadata": {
            "id": task_id,
            "createdAt": now.isoformat(timespec="milliseconds"),
        },
        "spec": {
            "title": title,
            "project": project_name,
            "assignedMember": assigned_member,
            "assignment": assignment,
            "status": status,
            "priority": priority,
            "riskClass": risk_class,
            "executionMode": execution_mode,
            "acceptance": acceptance or [],
            "relatedRuns": [],
            "relatedReviews": [],
        },
    }
    task = Task.model_validate(payload)
    root = index.workspace_root
    write_yaml(root / "tasks" / f"{task_id}.yaml", task.model_dump(mode="json", exclude_none=True))
    if markdown is not None:
        write_text(root / "tasks" / f"{task_id}.md", markdown)
    return task


def update_task(workspace_path: str | Path, task_id: str, updates: dict[str, Any]) -> Task:
    index = load_workspace(workspace_path)
    if task_id not in index.tasks:
        raise KeyError(f"unknown task {task_id}")
    path = index.workspace_root / "tasks" / f"{task_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    allowed = {"title", "status", "priority", "assignedMember", "assignment", "riskClass", "executionMode", "acceptance"}
    for key, value in updates.items():
        if key in allowed and value is not None:
            spec[key] = value
    task = Task.model_validate(data)
    write_yaml(path, task.model_dump(mode="json", exclude_none=True))
    return task


def assign_task(workspace_path: str | Path, task_id: str, member: str, assignment: str | None = None) -> Task:
    index = load_workspace(workspace_path)
    if member not in index.members:
        raise KeyError(f"unknown member {member}")
    if assignment:
        if assignment not in index.assignments:
            raise KeyError(f"unknown assignment {assignment}")
        assignment_record = index.assignments[assignment]
        if assignment_record.spec.member != member:
            raise ValueError(f"assignment {assignment} belongs to {assignment_record.spec.member}, not {member}")
    return update_task(workspace_path, task_id, {"assignedMember": member, "assignment": assignment})


def create_model_profile(
    workspace_path: str | Path,
    *,
    name: str,
    provider: str,
    model: str,
    display_name: str | None = None,
    gateway: str = "litellm",
    secret_env: str | None = None,
    invocation: dict[str, Any] | None = None,
    pricing: dict[str, Any] | None = None,
    capabilities: list[str] | None = None,
    default_for_members: list[str] | None = None,
    default_for_assignments: list[str] | None = None,
    notes: str | None = None,
) -> ModelProfile:
    index = load_workspace(workspace_path)
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "ModelProfile",
        "metadata": {"name": name},
        "spec": {
            "provider": provider,
            "model": model,
            "displayName": display_name,
            "gateway": gateway,
            "secretEnv": secret_env,
            "invocation": invocation or {},
            "pricing": pricing,
            "capabilities": capabilities or [],
            "defaultForMembers": default_for_members or [],
            "defaultForAssignments": default_for_assignments or [],
            "notes": notes,
        },
    }
    profile = ModelProfile.model_validate(payload)
    write_yaml(index.workspace_root / "model_profiles" / f"{name}.yaml", profile.model_dump(mode="json", exclude_none=True))
    return profile


def create_run(
    workspace_path: str | Path,
    *,
    task_id: str,
    member: str | None = None,
    assignment: str | None = None,
    model_profile: str | None = None,
    mode: str = "assisted",
    status: str = "READY",
    branch_base: str | None = None,
    extra_spec: dict[str, Any] | None = None,
) -> Run:
    index = load_workspace(workspace_path)
    if task_id not in index.tasks:
        raise KeyError(f"unknown task {task_id}")
    now = datetime.now().astimezone()
    run_id = timestamp_run_id(now)
    task = index.tasks[task_id]
    selected_member = member or task.spec.assignedMember
    if not selected_member:
        raise ValueError(f"task {task_id} has no assigned member")
    if selected_member not in index.members:
        raise KeyError(f"unknown member {selected_member}")
    selected_assignment = assignment or task.spec.assignment or _single_active_assignment(index, selected_member, task.spec.project)
    if selected_assignment:
        if selected_assignment not in index.assignments:
            raise KeyError(f"unknown assignment {selected_assignment}")
        assignment_record = index.assignments[selected_assignment]
        if assignment_record.spec.member != selected_member:
            raise ValueError(f"assignment {selected_assignment} belongs to {assignment_record.spec.member}, not {selected_member}")
        if assignment_record.spec.project != task.spec.project:
            raise ValueError(f"assignment {selected_assignment} belongs to project {assignment_record.spec.project}, not {task.spec.project}")
    else:
        assignment_record = None
    member_record = index.members[selected_member]
    selected_model = model_profile or _default_model_profile_for_member(index, selected_member)
    project = task.spec.project
    default_repo = next(iter(index.repositories.values()), None)
    base = branch_base or (default_repo.spec.defaultBranch if default_repo else "develop") or "develop"
    branch_name = f"aiteamos/{task_id}/{selected_member}/{run_id}"
    retained_until = (now + timedelta(days=RUN_RETENTION_DAYS)).isoformat(timespec="milliseconds")
    run_spec: dict[str, Any] = {
        "project": project,
        "task": task_id,
        "member": selected_member,
        "assignment": selected_assignment,
        "memberKind": member_record.spec.kind,
        "roleContext": assignment_record.spec.roleContext if assignment_record else None,
        "mode": mode,
        "status": status,
        "modelProfile": selected_model,
        "branch": {
            "name": branch_name,
            "base": base,
            "status": "planned",
        },
        "contextCapsule": "prompt_capsule.md",
        "contextManifest": "context_manifest.yaml",
        "eventLedger": "events.jsonl",
        "journal": "journal.md",
        "lifecycle": "active",
        "retainedUntil": retained_until,
        "exportPolicy": "manifest-only",
        "decisionAudit": [],
        "reviews": [],
        "outputs": [],
        "memoryProposals": [],
    }
    if extra_spec:
        run_spec.update(extra_spec)
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "Run",
        "metadata": {
            "id": run_id,
            "createdAt": now.isoformat(timespec="milliseconds"),
        },
        "spec": run_spec,
    }
    run = Run.model_validate(payload)
    run_dir = index.workspace_root / "runs" / run_id
    context = build_context_capsule(
        index,
        run_id=run_id,
        task_id=task_id,
        member_id=selected_member,
        assignment_id=selected_assignment,
        model_profile=selected_model,
        branch_name=branch_name,
    )
    write_yaml(run_dir / "run.yaml", run.model_dump(mode="json", exclude_none=True))
    _write_context_outputs(run_dir, run, context)
    write_text(
        run_dir / "journal.md",
        f"# {run_id} Journal\n\nAssisted run created from the dashboard. Execution must happen on branch `{branch_name}`, not on the base branch.\n",
    )
    _append_run_event(
        index.workspace_root,
        run_id,
        {
            "type": "run.created",
            "run": run_id,
            "task": task_id,
            "member": selected_member,
            "assignment": selected_assignment or "",
            "modelProfile": selected_model or "",
            "branch": branch_name,
        },
    )

    task_path = index.workspace_root / "tasks" / f"{task_id}.yaml"
    task_data = read_yaml(task_path)
    related_runs = task_data.setdefault("spec", {}).setdefault("relatedRuns", [])
    if run_id not in related_runs:
        related_runs.append(run_id)
    write_yaml(task_path, task_data)
    return run


def create_review(
    workspace_path: str | Path,
    *,
    run_id: str,
    reviewer: str,
    verdict: str,
    source: str = "dashboard-human-review",
    reviewer_member: str | None = None,
    findings: list[dict[str, Any]] | None = None,
    markdown: str | None = None,
    target: dict[str, Any] | None = None,
) -> Review:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    now = datetime.now().astimezone()
    review_id = timestamp_review_id(now)
    review_target = target
    if review_target is None and run.spec.reviewTarget is not None:
        review_target = run.spec.reviewTarget.model_dump(mode="json", exclude_none=True)
    resolved_reviewer_member = reviewer_member or (reviewer if reviewer in index.members else None)
    reviewer_kind = index.members[resolved_reviewer_member].spec.kind if resolved_reviewer_member else None
    decision_kind = "human_approval" if reviewer_kind == "human" else "digital_recommendation" if reviewer_kind in {"digital", "hybrid"} else "service_policy_decision" if reviewer_kind == "service" else "system_check"
    review_audit = decision_audit_record(
        index,
        decision_kind=decision_kind,
        decision=verdict,
        actor_member=resolved_reviewer_member,
        authority="approve" if reviewer_kind == "human" else "recommend" if reviewer_kind in {"digital", "hybrid"} else "record",
        reason=f"Review verdict recorded as {verdict}.",
        source=source,
        decided_at=now.isoformat(timespec="milliseconds"),
        evidence=[{"kind": "review", "run": run_id, "task": run.spec.task, "findings": findings or []}],
        requires_human_review=reviewer_kind != "human",
    )
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "Review",
        "metadata": {
            "id": review_id,
            "createdAt": now.isoformat(timespec="milliseconds"),
        },
        "spec": {
            "project": run.spec.project,
            "task": run.spec.task,
            "run": run_id,
            "reviewer": reviewer,
            "reviewerMember": resolved_reviewer_member,
            "reviewerKind": reviewer_kind,
            "source": source,
            "verdict": verdict,
            "target": review_target,
            "findings": findings or [],
            "decisionAudit": [review_audit],
        },
    }
    review = Review.model_validate(payload)
    root = index.workspace_root
    write_yaml(root / "reviews" / f"{review_id}.yaml", review.model_dump(mode="json", exclude_none=True))
    write_text(root / "reviews" / f"{review_id}.md", markdown or _default_review_markdown(review))
    _link_review_to_run(root, run_id, review_id)
    _link_review_to_task(root, run.spec.task, review_id)
    _append_run_event(root, run_id, {"type": "review.recorded", "review": review_id, "reviewer": reviewer, "verdict": verdict})
    if _is_changes_requested(verdict):
        update_run(workspace_path, run_id, {"status": "CHANGES_REQUESTED"})
        update_task(workspace_path, run.spec.task, {"status": "CHANGES_REQUESTED"})
    return review


def rebuild_run_context(workspace_path: str | Path, run_id: str) -> Run:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    branch_name = run.spec.branch.name if run.spec.branch else f"aiteamos/{run.spec.task}/{run.spec.member}/{run_id}"
    context = build_context_capsule(
        index,
        run_id=run_id,
        task_id=run.spec.task,
        member_id=run.spec.member,
        assignment_id=run.spec.assignment,
        model_profile=run.spec.modelProfile,
        branch_name=branch_name,
    )
    run_dir = index.workspace_root / "runs" / run_id
    run_path = run_dir / "run.yaml"
    data = read_yaml(run_path)
    spec = data.setdefault("spec", {})
    spec.setdefault("contextCapsule", "prompt_capsule.md")
    spec.setdefault("contextManifest", "context_manifest.yaml")
    run = Run.model_validate(data)
    write_yaml(run_path, run.model_dump(mode="json", exclude_none=True))
    _write_context_outputs(run_dir, run, context)
    _append_run_event(index.workspace_root, run_id, {"type": "context.rebuilt"})
    return load_workspace(workspace_path).runs[run_id]


def update_run(workspace_path: str | Path, run_id: str, updates: dict[str, Any]) -> Run:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    path = index.workspace_root / "runs" / run_id / "run.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    for key in [
        "status",
        "worktree",
        "lifecycle",
        "retainedUntil",
        "archivedAt",
        "redactedAt",
        "redactionPolicy",
        "exportPolicy",
    ]:
        if key in updates and updates[key] is not None:
            spec[key] = updates[key]
    if "decisionAudit" in updates and updates["decisionAudit"] is not None:
        spec["decisionAudit"] = updates["decisionAudit"]
    if "modelProfile" in updates:
        if updates["modelProfile"]:
            spec["modelProfile"] = updates["modelProfile"]
        else:
            spec.pop("modelProfile", None)
    if "reviewTarget" in updates:
        if updates["reviewTarget"]:
            spec["reviewTarget"] = updates["reviewTarget"]
        else:
            spec.pop("reviewTarget", None)
    if "worker" in updates and updates["worker"] is not None:
        current_worker = spec.get("worker") if isinstance(spec.get("worker"), dict) else {}
        next_worker = updates["worker"]
        spec["worker"] = {**current_worker, **next_worker} if isinstance(next_worker, dict) else next_worker
    for key in ["outputs", "memoryProposals", "closeout", "sourceIntegration"]:
        if key in updates and updates[key] is not None:
            spec[key] = updates[key]
    run = Run.model_validate(data)
    write_yaml(path, run.model_dump(mode="json", exclude_none=True))
    return run


def append_run_event(workspace_path: str | Path, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    return _append_run_event(index.workspace_root, run_id, event)


def append_run_journal(workspace_path: str | Path, run_id: str, *, title: str, body: str) -> str:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    run_dir = index.workspace_root / "runs" / run_id
    journal_name = run.spec.journal or "journal.md"
    journal_path = run_dir / journal_name
    previous = read_text_if_exists(journal_path) or f"# {run_id} Journal\n"
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    section = f"""

## {title} ({now})

{body.strip()}
"""
    write_text(journal_path, previous.rstrip() + section + "\n")
    return f"runs/{run_id}/{journal_name}"


def propose_memory(
    workspace_path: str | Path,
    *,
    project: str,
    title: str,
    content: str,
    kind: str = "procedural",
    member: str | None = None,
    assignment: str | None = None,
    store: str | None = None,
    entry_path: str | None = None,
    source_run: str | None = None,
    source_task: str | None = None,
    source_ingest_id: str | None = None,
    source_extractor_id: str | None = None,
    dedupe_key: str | None = None,
    confidence: float | None = None,
    evidence: list[str] | None = None,
    review_guidance: str | None = None,
) -> MemoryProposal:
    index = load_workspace(workspace_path)
    if source_run and source_run in index.runs:
        source = index.runs[source_run]
        member = member or source.spec.member
        assignment = assignment or source.spec.assignment
        source_task = source_task or source.spec.task
        project = project or source.spec.project
    if dedupe_key:
        for existing in index.memory_proposals.values():
            if existing.spec.sourceRun == source_run and existing.spec.dedupeKey == dedupe_key:
                if source_run and source_run in index.runs:
                    _link_memory_proposal_to_run(index.workspace_root, source_run, existing.object_id)
                return existing
    now = datetime.now().astimezone()
    proposal_id = timestamp_memory_proposal_id(now)
    payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "MemoryProposal",
        "metadata": {
            "id": proposal_id,
            "createdAt": now.isoformat(timespec="milliseconds"),
        },
        "spec": {
            "project": project,
            "member": member,
            "assignment": assignment,
            "store": store,
            "entryPath": entry_path,
            "sourceRun": source_run,
            "sourceTask": source_task,
            "sourceIngestId": source_ingest_id,
            "sourceExtractorId": source_extractor_id,
            "dedupeKey": dedupe_key,
            "status": "pending-review",
            "kind": kind,
            "title": title,
            "content": content,
            "evidence": evidence or [],
            "confidence": confidence,
            "reviewGuidance": review_guidance,
        },
    }
    proposal = MemoryProposal.model_validate(payload)
    write_yaml(index.workspace_root / "memory" / "proposals" / f"{proposal_id}.yaml", proposal.model_dump(mode="json", exclude_none=True))
    if source_run and source_run in index.runs:
        _link_memory_proposal_to_run(index.workspace_root, source_run, proposal_id)
    return proposal


def approve_memory_proposal(
    workspace_path: str | Path,
    proposal_id: str,
    *,
    reviewer_member: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if proposal_id not in index.memory_proposals:
        raise KeyError(f"unknown memory proposal {proposal_id}")
    if reviewer_member and reviewer_member not in index.members:
        raise KeyError(f"unknown reviewer member {reviewer_member}")
    gate = evaluate_memory_promotion_gate(index, proposal_id)
    if gate["blockers"]:
        raise ValueError("memory proposal is not ready for approval: " + "; ".join(gate["blockers"]))
    proposal = index.memory_proposals[proposal_id]
    now = datetime.now().astimezone()
    memory_id = proposal_id.replace("MP-", "MEM-", 1)
    approved_at = now.isoformat(timespec="milliseconds")
    reviewer = reviewer_member or "human"
    audit_actor = reviewer if reviewer in index.members else None
    store_id = proposal.spec.store or _default_memory_store_for_proposal(index, proposal)
    entry_path = proposal.spec.entryPath or f"approved/{memory_id}.md"
    scope = _memory_scope_for_store(index, store_id, proposal)
    eval_evidence_refs = memory_eval_evidence_refs(index, proposal_id)
    eval_evidence_records = memory_eval_evidence_records(index, proposal_id)
    eval_confidence_sources = memory_eval_confidence_sources(index, proposal_id)
    memory_evidence = _unique_ordered([*proposal.spec.evidence, *eval_evidence_refs])
    review_audit = decision_audit_record(
        index,
        decision_kind="human_approval",
        decision="approved",
        actor_member=audit_actor,
        authority="approve",
        reason=reason or "memory proposal approved",
        source="memory-proposal-review",
        decided_at=approved_at,
        evidence=[{"kind": "memory-proposal", "proposal": proposal_id}, *eval_evidence_records],
    )
    memory_payload: dict[str, Any] = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "MemoryEntry",
        "metadata": {
            "id": memory_id,
            "createdAt": approved_at,
        },
        "spec": {
            "store": store_id,
            "path": entry_path,
            "scope": scope,
            "source": proposal_id,
            "kind": proposal.spec.kind,
            "title": proposal.spec.title,
            "content": proposal.spec.content,
            "evidence": memory_evidence,
            "evalEvidence": eval_evidence_records,
            "confidence": gate.get("effectiveConfidence") if gate.get("effectiveConfidence") is not None else proposal.spec.confidence,
            "lastVerifiedAt": approved_at,
            "lifecycle": "active",
            "relatedProjects": [proposal.spec.project] if proposal.spec.project else [],
            "relatedMembers": [proposal.spec.member] if proposal.spec.member else [],
            "relatedAssignments": [proposal.spec.assignment] if proposal.spec.assignment else [],
            "lineage": {
                "sourceRun": proposal.spec.sourceRun,
                "sourceTask": proposal.spec.sourceTask,
                "authorMember": proposal.spec.member,
                "reviewerMember": reviewer,
                "evidence": memory_evidence,
                "relatedTests": [str(source["lastResultId"]) for source in eval_confidence_sources if source.get("meetsThreshold")],
            },
        },
    }
    memory = MemoryEntry.model_validate(memory_payload)
    write_yaml(index.workspace_root / "memory" / "entries" / store_id / f"{memory_id}.yaml", memory.model_dump(mode="json", exclude_none=True))

    version = MemoryVersion.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryVersion",
            "metadata": {"id": f"{memory_id}-v1", "createdAt": approved_at},
            "spec": {
                "entry": memory_id,
                "store": store_id,
                "version": 1,
                "operation": "create",
                "createdAt": approved_at,
                "createdByMember": reviewer,
            },
        }
    )
    write_yaml(index.workspace_root / "memory" / "versions" / store_id / f"{memory_id}-v1.yaml", version.model_dump(mode="json", exclude_none=True))

    binding = _memory_binding_for_approved_entry(index, proposal, memory_id, store_id, approved_at, reviewer)
    if binding:
        write_yaml(index.workspace_root / "memory" / "bindings" / f"{binding.object_id}.yaml", binding.model_dump(mode="json", exclude_none=True))

    data = _set_memory_status(
        workspace_path,
        proposal_id,
        "approved",
        reviewed_at=approved_at,
        reviewed_by_member=reviewer,
        review_reason=reason,
        decision_audit=review_audit,
    )
    spec = data.setdefault("spec", {})
    spec["approvedMemory"] = memory_id
    spec["store"] = store_id
    spec["entryPath"] = entry_path
    write_yaml(index.workspace_root / "memory" / "proposals" / f"{proposal_id}.yaml", data)
    _append_memory_event(
        index.workspace_root,
        {
            "type": "memory.approved",
            "memoryEntry": memory_id,
            "memoryStore": store_id,
            "proposal": proposal_id,
            "actorMember": reviewer,
            "reason": reason,
            "sourceRun": proposal.spec.sourceRun,
            "status": "active",
        },
    )
    return data


def update_memory_proposal(workspace_path: str | Path, proposal_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if proposal_id not in index.memory_proposals:
        raise KeyError(f"unknown memory proposal {proposal_id}")
    proposal = index.memory_proposals[proposal_id]
    if proposal.spec.status != "pending-review":
        raise ValueError(f"memory proposal {proposal_id} is {proposal.spec.status}; only pending-review proposals can be edited")
    path = index.workspace_root / "memory" / "proposals" / f"{proposal_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    for key in ["title", "content", "kind", "reviewGuidance"]:
        if key in updates and updates[key] is not None:
            value = str(updates[key]).strip()
            if value:
                spec[key] = value
    if "confidence" in updates:
        confidence = updates["confidence"]
        spec["confidence"] = None if confidence is None else float(confidence)
    if "evidence" in updates and updates["evidence"] is not None:
        spec["evidence"] = [str(item).strip() for item in updates["evidence"] if str(item).strip()]
    spec["editedAt"] = datetime.now().astimezone().isoformat(timespec="milliseconds")
    spec["editedBy"] = "human"
    updated = MemoryProposal.model_validate(data)
    payload = updated.model_dump(mode="json", exclude_none=True)
    write_yaml(path, payload)
    return payload


def repair_memory_proposal(workspace_path: str | Path, proposal_id: str) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if proposal_id not in index.memory_proposals:
        raise KeyError(f"unknown memory proposal {proposal_id}")
    proposal = index.memory_proposals[proposal_id]
    if proposal.spec.status != "pending-review":
        raise ValueError(f"memory proposal {proposal_id} is {proposal.spec.status}; only pending-review proposals can be repaired")
    hints = memory_proposal_repair_hints(index, proposal_id)
    updates: dict[str, Any] = {}
    if "evidence" in hints["failedChecks"] and hints["suggestedEvidence"]:
        updates["evidence"] = hints["suggestedEvidence"]
    if hints["suggestedConfidence"] is not None:
        updates["confidence"] = hints["suggestedConfidence"]
    if hints["suggestedReviewGuidance"]:
        updates["reviewGuidance"] = hints["suggestedReviewGuidance"]
    if not updates:
        raise ValueError(f"memory proposal {proposal_id} has no safe repair hints to apply")
    return update_memory_proposal(workspace_path, proposal_id, updates)


def update_memory_entry(workspace_path: str | Path, memory_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if memory_id not in index.memory_entries:
        raise KeyError(f"unknown memory entry {memory_id}")
    path = _memory_entry_manifest_path(index, memory_id)
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    changed_fields: list[str] = []
    for key in ["title", "content", "kind"]:
        if key in updates and updates[key] is not None:
            value = str(updates[key]).strip()
            if not value:
                raise ValueError(f"memory entry {key} cannot be empty")
            if spec.get(key) != value:
                spec[key] = value
                changed_fields.append(key)
    if "confidence" in updates:
        confidence = updates["confidence"]
        value = None if confidence is None else float(confidence)
        if spec.get("confidence") != value:
            spec["confidence"] = value
            changed_fields.append("confidence")
    if "evidence" in updates and updates["evidence"] is not None:
        evidence = [str(item).strip() for item in updates["evidence"] if str(item).strip()]
        if spec.get("evidence", []) != evidence:
            spec["evidence"] = evidence
            changed_fields.append("evidence")
    if not changed_fields:
        updated = MemoryEntry.model_validate(data)
        return updated.model_dump(mode="json", exclude_none=True)
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    reason = str(updates.get("editReason") or "manual approved memory entry edit").strip()
    spec["editedAt"] = now
    spec["editedBy"] = "human"
    spec["editReason"] = reason
    spec["lifecycle"] = "stale"
    spec["staleAt"] = now
    spec["staleReason"] = f"edited pending re-verification: {reason}"
    updated = MemoryEntry.model_validate(data)
    payload = updated.model_dump(mode="json", exclude_none=True)
    write_yaml(path, payload)
    _append_memory_event(
        index.workspace_root,
        {
            "type": "memory.edited",
            "memoryEntry": memory_id,
            "actorMember": "human",
            "fields": changed_fields,
            "reason": reason,
            "status": "stale",
        },
    )
    return payload


def verify_memory_entry(workspace_path: str | Path, memory_id: str, reason: str | None = None) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if memory_id not in index.memory_entries:
        raise KeyError(f"unknown memory entry {memory_id}")
    path = _memory_entry_manifest_path(index, memory_id)
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    spec["lifecycle"] = "active"
    spec["lastVerifiedAt"] = now
    spec["verifiedBy"] = "human"
    spec["verificationReason"] = (reason or "manual dashboard verification").strip()
    spec.pop("staleAt", None)
    spec.pop("staleReason", None)
    updated = MemoryEntry.model_validate(data)
    payload = updated.model_dump(mode="json", exclude_none=True)
    write_yaml(path, payload)
    _append_memory_event(
        index.workspace_root,
        {
            "type": "memory.verified",
            "memoryEntry": memory_id,
            "actorMember": "human",
            "reason": spec["verificationReason"],
            "status": "active",
        },
    )
    return payload


def mark_memory_entry_stale(workspace_path: str | Path, memory_id: str, reason: str | None = None) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if memory_id not in index.memory_entries:
        raise KeyError(f"unknown memory entry {memory_id}")
    path = _memory_entry_manifest_path(index, memory_id)
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    spec["lifecycle"] = "stale"
    spec["staleAt"] = now
    spec["staleReason"] = (reason or "manual dashboard stale mark").strip()
    spec["verifiedBy"] = "human"
    updated = MemoryEntry.model_validate(data)
    payload = updated.model_dump(mode="json", exclude_none=True)
    write_yaml(path, payload)
    _append_memory_event(
        index.workspace_root,
        {
            "type": "memory.marked_stale",
            "memoryEntry": memory_id,
            "actorMember": "human",
            "reason": spec["staleReason"],
            "status": "stale",
        },
    )
    return payload


def remediate_memory_health_issue(
    workspace_path: str | Path,
    *,
    issue_kind: str,
    ref: str,
    action: str,
    actor_member: str,
    reason: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    from .knowledge_health import evaluate_knowledge_health

    index = load_workspace(workspace_path)
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    issue = _find_memory_health_issue(index, issue_kind, ref)
    blockers: list[str] = []
    warnings: list[str] = []
    result: dict[str, Any] = {}

    actor = index.members.get(actor_member)
    if not actor:
        blockers.append(f"unknown actor member {actor_member}")
    elif actor.spec.kind not in {"human", "hybrid"} and not dry_run:
        blockers.append("applying memory health remediation requires a human or hybrid actor")

    if not reason.strip():
        blockers.append("remediation reason is required")
    if issue is None:
        blockers.append(f"health issue {issue_kind}:{ref} is not currently open")
    else:
        warnings.extend(_memory_health_action_warnings(issue_kind, action))
        blockers.extend(_memory_health_action_blockers(index, issue_kind, ref, action))

    audit = decision_audit_record(
        index,
        decision_kind=_remediation_decision_kind(actor.spec.kind if actor else None),
        decision="dry-run" if dry_run else ("blocked" if blockers else "approved"),
        actor_member=actor_member if actor else None,
        authority="record" if dry_run else "approve",
        reason=reason.strip() or None,
        source="knowledge-health-remediation",
        decided_at=now,
        evidence=[{"kind": "knowledge-health-issue", "issueKind": issue_kind, "ref": ref, "action": action}],
        requires_human_review=bool(actor and actor.spec.kind in {"digital", "service"}),
    )

    applied = False
    if not blockers and not dry_run:
        result = _apply_memory_health_remediation(workspace_path, ref, action, reason.strip(), actor_member)
        applied = True
        refreshed = evaluate_knowledge_health(workspace_path)
        still_open = _find_issue_in_health(refreshed, issue_kind, ref)
        if still_open:
            warnings.append("remediation was applied but the health issue is still open after refresh")
        _append_memory_event(
            index.workspace_root,
            {
                "type": "memory.health.remediated",
                "issueKind": issue_kind,
                "ref": ref,
                "action": action,
                "actorMember": actor_member,
                "reason": reason.strip(),
                "applied": True,
            },
        )
    elif not blockers:
        result = {"preview": _memory_health_remediation_preview(index, ref, action)}

    payload = {
        "generatedAt": now,
        "issueKind": issue_kind,
        "ref": ref,
        "action": action,
        "actorMember": actor_member,
        "dryRun": dry_run,
        "applied": applied,
        "blockers": blockers,
        "warnings": warnings,
        "issue": issue,
        "decisionAudit": [audit],
        "result": result,
    }
    return KnowledgeHealthRemediationRecord.model_validate(payload).model_dump(mode="json", exclude_none=True)


def _find_memory_health_issue(index: Any, issue_kind: str, ref: str) -> dict[str, Any] | None:
    from .knowledge_health import evaluate_knowledge_health

    return _find_issue_in_health(evaluate_knowledge_health(index), issue_kind, ref)


def _find_issue_in_health(health: dict[str, Any], issue_kind: str, ref: str) -> dict[str, Any] | None:
    for issue in health.get("issues", []):
        if issue.get("kind") == issue_kind and issue.get("ref") == ref:
            return dict(issue)
    return None


def _memory_health_action_blockers(index: Any, issue_kind: str, ref: str, action: str) -> list[str]:
    if action == "verify-entry":
        blockers = _entry_action_blockers(index, ref)
        if issue_kind not in {"memory-status", "memory-freshness"}:
            blockers.append(f"{action} is only supported for stale or freshness issues")
        return blockers
    if action == "mark-entry-stale":
        return _entry_action_blockers(index, ref)
    if action == "archive-binding":
        blockers = []
        if ref not in index.memory_bindings:
            blockers.append(f"unknown memory binding {ref}")
        if not issue_kind.startswith("memory-binding-"):
            blockers.append(f"{action} is only supported for memory binding issues")
        return blockers
    if action == "revoke-grant":
        blockers = []
        if ref not in index.memory_grants:
            blockers.append(f"unknown memory grant {ref}")
        if not issue_kind.startswith("memory-grant-"):
            blockers.append(f"{action} is only supported for memory grant issues")
        return blockers
    return [f"unsupported remediation action {action}"]


def _entry_action_blockers(index: Any, ref: str) -> list[str]:
    return [] if ref in index.memory_entries else [f"unknown memory entry {ref}"]


def _memory_health_action_warnings(issue_kind: str, action: str) -> list[str]:
    if action == "mark-entry-stale" and issue_kind in {"memory-conflict", "memory-conflict-link"}:
        return ["marking conflicted memory stale keeps the conflict audit visible but does not resolve the source conflict"]
    if action in {"archive-binding", "revoke-grant"} and issue_kind.endswith("sensitive"):
        return ["sensitive memory remediation should be followed by a scoped ACL review"]
    return []


def _remediation_decision_kind(actor_kind: str | None) -> str:
    if actor_kind in {"human", "hybrid"}:
        return "human_approval"
    if actor_kind == "digital":
        return "digital_recommendation"
    if actor_kind == "service":
        return "service_policy_decision"
    return "system_check"


def _memory_health_remediation_preview(index: Any, ref: str, action: str) -> dict[str, Any]:
    if action in {"verify-entry", "mark-entry-stale"}:
        entry = index.memory_entries.get(ref)
        return {"kind": "MemoryEntry", "id": ref, "currentLifecycle": entry.spec.lifecycle if entry else None}
    if action == "archive-binding":
        binding = index.memory_bindings.get(ref)
        return {"kind": "MemoryBinding", "id": ref, "currentStatus": binding.spec.status if binding else None}
    if action == "revoke-grant":
        grant = index.memory_grants.get(ref)
        return {"kind": "MemoryGrant", "id": ref, "currentStatus": grant.spec.status if grant else None}
    return {"id": ref}


def _apply_memory_health_remediation(
    workspace_path: str | Path,
    ref: str,
    action: str,
    reason: str,
    actor_member: str,
) -> dict[str, Any]:
    if action == "verify-entry":
        return {"memory": verify_memory_entry(workspace_path, ref, reason)}
    if action == "mark-entry-stale":
        return {"memory": mark_memory_entry_stale(workspace_path, ref, reason)}
    if action == "archive-binding":
        return {"binding": archive_memory_binding(workspace_path, ref).model_dump(mode="json", exclude_none=True)}
    if action == "revoke-grant":
        return {"grant": revoke_memory_grant(workspace_path, ref, reason=reason, revoked_by_member=actor_member).model_dump(mode="json", exclude_none=True)}
    raise ValueError(f"unsupported remediation action {action}")


def _link_memory_proposal_to_run(workspace_root: Path, run_id: str, proposal_id: str) -> None:
    run_path = workspace_root / "runs" / run_id / "run.yaml"
    run_data = read_yaml(run_path)
    proposals = run_data.setdefault("spec", {}).setdefault("memoryProposals", [])
    if proposal_id not in proposals:
        proposals.append(proposal_id)
    write_yaml(run_path, run_data)


def _link_review_to_run(workspace_root: Path, run_id: str, review_id: str) -> None:
    run_path = workspace_root / "runs" / run_id / "run.yaml"
    run_data = read_yaml(run_path)
    reviews = run_data.setdefault("spec", {}).setdefault("reviews", [])
    if review_id not in reviews:
        reviews.append(review_id)
    write_yaml(run_path, run_data)


def _link_review_to_task(workspace_root: Path, task_id: str, review_id: str) -> None:
    task_path = workspace_root / "tasks" / f"{task_id}.yaml"
    if not task_path.exists():
        return
    task_data = read_yaml(task_path)
    reviews = task_data.setdefault("spec", {}).setdefault("relatedReviews", [])
    if review_id not in reviews:
        reviews.append(review_id)
    write_yaml(task_path, task_data)


def _default_review_markdown(review: Review) -> str:
    lines = [
        f"# {review.object_id}",
        "",
        f"Reviewer: `{review.spec.reviewer}`",
        f"Verdict: `{review.spec.verdict}`",
        f"Run: `{review.spec.run or 'none'}`",
        "",
        "## Findings",
        "",
    ]
    if review.spec.findings:
        for finding in review.spec.findings:
            lines.append(f"- `{finding.id}` [{finding.severity}] {finding.summary}")
            if finding.action:
                lines.append(f"  Action: {finding.action}")
    else:
        lines.append("- No findings recorded.")
    lines.append("")
    return "\n".join(lines)


def _is_changes_requested(verdict: str) -> bool:
    return verdict.strip().lower() in {"changes-requested", "change-requested", "rejected", "blocked"}


def reject_memory_proposal(
    workspace_path: str | Path,
    proposal_id: str,
    *,
    reviewer_member: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if proposal_id not in index.memory_proposals:
        raise KeyError(f"unknown memory proposal {proposal_id}")
    if reviewer_member and reviewer_member not in index.members:
        raise KeyError(f"unknown reviewer member {reviewer_member}")
    proposal = index.memory_proposals[proposal_id]
    if proposal.spec.status != "pending-review":
        raise ValueError(f"memory proposal {proposal_id} is {proposal.spec.status}, not pending-review")
    reviewed_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
    reviewer = reviewer_member or "human"
    audit_actor = reviewer if reviewer in index.members else None
    review_audit = decision_audit_record(
        index,
        decision_kind="human_approval",
        decision="rejected",
        actor_member=audit_actor,
        authority="approve",
        reason=reason or "memory proposal rejected",
        source="memory-proposal-review",
        decided_at=reviewed_at,
        evidence=[{"kind": "memory-proposal", "proposal": proposal_id}],
    )
    data = _set_memory_status(
        workspace_path,
        proposal_id,
        "rejected",
        reviewed_at=reviewed_at,
        reviewed_by_member=reviewer,
        review_reason=reason,
        decision_audit=review_audit,
    )
    _append_memory_event(
        index.workspace_root,
        {
            "type": "memory.rejected",
            "proposal": proposal_id,
            "actorMember": reviewer,
            "reason": reason,
            "sourceRun": proposal.spec.sourceRun,
            "status": "rejected",
        },
    )
    return data


def _single_active_assignment(index: Any, member_id: str, project: str) -> str | None:
    matches = [
        assignment.object_id
        for assignment in index.assignments.values()
        if assignment.spec.member == member_id and assignment.spec.project == project and assignment.spec.status == "active"
    ]
    return sorted(matches)[0] if len(matches) == 1 else None


def _default_model_profile_for_member(index: Any, member_id: str) -> str | None:
    if member_id in index.digital_execution_profiles:
        return index.digital_execution_profiles[member_id].spec.defaultModelProfile
    for profile in index.digital_execution_profiles.values():
        if profile.spec.member == member_id and profile.spec.defaultModelProfile:
            return profile.spec.defaultModelProfile
    for profile_id, profile in index.model_profiles.items():
        if member_id in profile.spec.defaultForMembers:
            return profile_id
    return None


def _default_memory_store_for_proposal(index: Any, proposal: MemoryProposal) -> str:
    if proposal.spec.member:
        for store_id, store in sorted(index.memory_stores.items()):
            if store.spec.ownerMember == proposal.spec.member and store.spec.lifecycle == "active":
                return store_id
    for store_id, store in sorted(index.memory_stores.items()):
        if store.spec.ownerProject == proposal.spec.project and store.spec.lifecycle == "active":
            return store_id
    raise ValueError(f"memory proposal {proposal.object_id} has no explicit store and no active default store")


def _require_reviewing_memory_actor(index: Any, actor_member: str) -> None:
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    if actor_kind not in {"human", "hybrid"}:
        raise ValueError("reviewed memory creation requires a human or hybrid actor member")


def _validate_memory_store_owner(
    index: Any,
    *,
    store_type: str,
    owner_project: str | None,
    owner_member: str | None,
    owner_team: str | None,
    domain: str | None,
) -> None:
    if store_type not in {"project", "member", "team", "domain", "organization", "temporary", "imported"}:
        raise ValueError(f"unsupported memory store type {store_type}")
    if store_type == "project":
        if owner_project != index.project.object_id:
            raise KeyError(f"unknown project {owner_project}")
    if store_type == "member":
        if not owner_member:
            raise ValueError("member memory store requires ownerMember")
        if owner_member not in index.members:
            raise KeyError(f"unknown owner member {owner_member}")
    if store_type == "team":
        if not owner_team:
            raise ValueError("team memory store requires ownerTeam")
        if owner_team not in index.teams:
            raise KeyError(f"unknown owner team {owner_team}")
    if store_type == "domain" and not domain:
        raise ValueError("domain memory store requires domain")


def _memory_related_projects(
    index: Any,
    store: MemoryStore,
    values: list[str],
    bind_target_type: str | None,
    bind_target_id: str | None,
) -> list[str]:
    refs = list(values)
    if store.spec.ownerProject:
        refs.append(store.spec.ownerProject)
    if bind_target_type == "project" and bind_target_id:
        refs.append(bind_target_id)
    if bind_target_type == "assignment" and bind_target_id and bind_target_id in index.assignments:
        refs.append(index.assignments[bind_target_id].spec.project)
    return _unique_ordered(refs)


def _memory_related_members(
    store: MemoryStore,
    values: list[str],
    bind_target_type: str | None,
    bind_target_id: str | None,
) -> list[str]:
    refs = list(values)
    if store.spec.ownerMember:
        refs.append(store.spec.ownerMember)
    if bind_target_type == "member" and bind_target_id:
        refs.append(bind_target_id)
    return _unique_ordered(refs)


def _memory_related_assignments(
    values: list[str],
    bind_target_type: str | None,
    bind_target_id: str | None,
) -> list[str]:
    refs = list(values)
    if bind_target_type == "assignment" and bind_target_id:
        refs.append(bind_target_id)
    return _unique_ordered(refs)


def _memory_scope_for_store(index: Any, store_id: str, proposal: MemoryProposal) -> str:
    store = index.memory_stores.get(store_id)
    if store and store.spec.storeType in {"member", "project", "team", "domain", "organization"}:
        return "org" if store.spec.storeType == "organization" else store.spec.storeType
    if proposal.spec.sourceRun:
        return "run"
    if proposal.spec.sourceTask:
        return "task"
    if proposal.spec.member:
        return "member"
    return "project"


def _memory_binding_for_approved_entry(
    index: Any,
    proposal: MemoryProposal,
    memory_id: str,
    store_id: str,
    created_at: str,
    reviewer_member: str,
) -> MemoryBinding | None:
    target_type = "project"
    target_id = proposal.spec.project
    if proposal.spec.assignment:
        target_type = "assignment"
        target_id = proposal.spec.assignment
    elif proposal.spec.member:
        target_type = "member"
        target_id = proposal.spec.member
    if not target_id:
        return None
    binding_id = f"bind-{memory_id.lower()}-to-{_safe_id(target_id)}"
    return MemoryBinding.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryBinding",
            "metadata": {"id": binding_id, "createdAt": created_at},
            "spec": {
                "store": store_id,
                "entry": memory_id,
                "targetType": target_type,
                "targetId": target_id,
                "access": ["read", "reference", "inject"],
                "reason": f"Approved from memory proposal {proposal.object_id}.",
                "status": "active",
                "createdByMember": reviewer_member,
            },
        }
    )


def _memory_entry_manifest_path(index: Any, memory_id: str) -> Path:
    entry = index.memory_entries[memory_id]
    direct = index.workspace_root / "memory" / "entries" / entry.spec.store / f"{memory_id}.yaml"
    if direct.exists():
        return direct
    matches = sorted((index.workspace_root / "memory" / "entries").rglob(f"{memory_id}.yaml"))
    if not matches:
        raise FileNotFoundError(f"memory entry manifest not found for {memory_id}")
    return matches[0]


def _memory_binding_manifest_path(index: Any, binding_id: str) -> Path:
    direct = index.workspace_root / "memory" / "bindings" / f"{binding_id}.yaml"
    if direct.exists():
        return direct
    matches = sorted((index.workspace_root / "memory" / "bindings").rglob(f"{binding_id}.yaml"))
    if not matches:
        raise FileNotFoundError(f"memory binding manifest not found for {binding_id}")
    return matches[0]


def _handoff_manifest_path(index: Any, handoff_id: str) -> Path:
    direct = index.workspace_root / "im" / "handoffs" / f"{handoff_id}.yaml"
    if direct.exists():
        return direct
    matches = sorted((index.workspace_root / "im" / "handoffs").rglob(f"{handoff_id}.yaml"))
    if not matches:
        raise FileNotFoundError(f"handoff manifest not found for {handoff_id}")
    return matches[0]


def _git_activity_manifest_path(index: Any, activity_id: str) -> Path:
    direct = index.workspace_root / "git_activity" / f"{activity_id}.yaml"
    if direct.exists():
        return direct
    matches = sorted(path for path in (index.workspace_root / "git_activity").rglob(f"{activity_id}.yaml") if "imports" not in path.parts and "correlations" not in path.parts)
    if not matches:
        raise FileNotFoundError(f"git activity manifest not found for {activity_id}")
    return matches[0]


def _member_message_manifest_path(index: Any, message_id: str) -> Path:
    direct = index.workspace_root / "im" / "messages" / f"{message_id}.yaml"
    if direct.exists():
        return direct
    matches = sorted((index.workspace_root / "im" / "messages").rglob(f"{message_id}.yaml"))
    if not matches:
        raise FileNotFoundError(f"member message manifest not found for {message_id}")
    return matches[0]


def _member_delete_references(index: Any, member_id: str) -> dict[str, list[str]]:
    return {
        "runs": sorted(run_id for run_id, run in index.runs.items() if run.spec.member == member_id),
        "messages": sorted(
            message_id
            for message_id, message in index.member_messages.items()
            if message.spec.fromMember == member_id
            or member_id in message.spec.toMembers
            or message.spec.resolvedByMember == member_id
        ),
        "handoffs": sorted(
            handoff_id
            for handoff_id, handoff in index.handoffs.items()
            if handoff.spec.fromMember == member_id or handoff.spec.toMember == member_id
        ),
        "gitActivity": sorted(activity_id for activity_id, activity in index.git_activities.items() if activity.spec.member == member_id),
        "assignments": sorted(
            assignment_id
            for assignment_id, assignment in index.assignments.items()
            if assignment.spec.member == member_id and assignment.spec.status != "archived"
        ),
        "memoryBindings": sorted(
            binding_id
            for binding_id, binding in index.memory_bindings.items()
            if binding.spec.targetType == "member" and binding.spec.targetId == member_id and binding.spec.status != "archived"
        ),
    }


def _mark_lifecycle_redacted(spec: dict[str, Any], redacted_at: str, audit: dict[str, Any], *, export_policy: str) -> None:
    spec["lifecycle"] = "redacted"
    spec.setdefault("archivedAt", redacted_at)
    spec["redactedAt"] = redacted_at
    spec.setdefault("redactionPolicy", "member-delete-request")
    spec["exportPolicy"] = export_policy
    spec.setdefault("decisionAudit", []).append(audit)


def _queue_member_delete_reference(
    queue: list[dict[str, str]],
    index: Any,
    kind: str,
    object_id: str,
    path: Path,
    action: str,
) -> None:
    queue.append(
        {
            "kind": kind,
            "id": object_id,
            "path": f".aiteamos/{path.relative_to(index.workspace_root).as_posix()}",
            "action": action,
        }
    )


def _redact_run_payload_files(index: Any, run: Run, redacted_at: str) -> None:
    run_dir = index.workspace_root / "runs" / run.object_id
    if run.spec.contextCapsule:
        path = run_dir / run.spec.contextCapsule
        if path.exists():
            write_text(path, f"Redacted context capsule for {run.object_id} at {redacted_at}.\n")
    if run.spec.journal:
        path = run_dir / run.spec.journal
        if path.exists():
            write_text(path, f"Redacted run journal for {run.object_id} at {redacted_at}.\n")
    if run.spec.eventLedger:
        path = run_dir / run.spec.eventLedger
        if path.exists():
            event = build_run_event_payload(
                {"spec": run.model_dump(mode="json").get("spec", {})},
                {
                    "ts": redacted_at,
                    "type": "run.redacted",
                    "run": run.object_id,
                    "lifecycle": "redacted",
                    "redactedAt": redacted_at,
                    "redactionPolicy": "member-delete-request",
                    "exportPolicy": "manifest-only",
                    "source": "member-delete-request",
                    "decisionAudit": run.spec.decisionAudit,
                },
                sequence=1,
            )
            write_text(path, json.dumps(event, sort_keys=True) + "\n")
    if run.spec.contextManifest:
        path = run_dir / run.spec.contextManifest
        if path.exists():
            payload = {
                "apiVersion": "aiteamos.dev/v1alpha1",
                "kind": "ContextManifest",
                "metadata": {"id": f"{run.object_id}-redacted-context"},
                "spec": {
                    "generatedAt": redacted_at,
                    "task": run.spec.task,
                    "member": run.spec.member,
                    "memberKind": run.spec.memberKind,
                    "assignment": run.spec.assignment,
                    "project": run.spec.project,
                    "sourcePriority": [],
                    "sources": {},
                    "sourceDecisions": [],
                    "sourceCounts": {},
                    "exclusions": ["member-delete-request-redaction"],
                    "freshnessSignals": {},
                    "budget": {},
                    "limits": {},
                },
            }
            write_yaml(path, payload)


def _require_binding_target(index: Any, target_type: str, target_id: str) -> None:
    targets = {
        "member": index.members,
        "project": {index.project.object_id: index.project},
        "assignment": index.assignments,
        "task": index.tasks,
        "run": index.runs,
        "team": index.teams,
        "context-capsule": index.runs,
    }
    if target_type not in targets:
        raise ValueError(f"unsupported memory binding target type {target_type}")
    if target_id not in targets[target_type]:
        raise KeyError(f"unknown {target_type} {target_id}")


def _link_assignment_to_member(
    workspace_root: Path,
    member_id: str,
    project_id: str,
    assignment_id: str,
    responsibilities: list[str],
) -> None:
    path = workspace_root / "members" / f"{member_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    default_assignments = spec.setdefault("defaultAssignments", [])
    if assignment_id not in default_assignments:
        default_assignments.append(assignment_id)
    projects = spec.setdefault("projects", [])
    for project in projects:
        if project.get("project") == project_id:
            assignments = project.setdefault("assignments", [])
            if assignment_id not in assignments:
                assignments.append(assignment_id)
            existing = project.setdefault("responsibilities", [])
            for responsibility in responsibilities:
                if responsibility not in existing:
                    existing.append(responsibility)
            break
    else:
        projects.append(
            {
                "project": project_id,
                "assignments": [assignment_id],
                "responsibilities": responsibilities,
                "status": "active",
            }
        )
    updated = TeamMember.model_validate(data)
    write_yaml(path, updated.model_dump(mode="json", exclude_none=True))


def _unique_timestamped_id(workspace_root: Path, prefix: str, relative_dir: str) -> str:
    now = datetime.now().astimezone()
    stem = f"{prefix}-{now.strftime('%Y%m%dT%H%M%S')}{now.microsecond // 1000:03d}"
    directory = workspace_root / relative_dir
    candidate = stem
    suffix = 1
    while (directory / f"{candidate}.yaml").exists():
        suffix += 1
        candidate = f"{stem}-{suffix}"
    return candidate


def _unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _retrospective_dedupe_key(
    project: str,
    source_task_plan: str | None,
    source_runs: list[str],
    source_tasks: list[str],
    source_messages: list[str],
    source_handoffs: list[str],
    summary: str,
) -> str:
    payload = json.dumps(
        {
            "project": project,
            "sourceTaskPlan": source_task_plan,
            "sourceRuns": sorted(source_runs),
            "sourceTasks": sorted(source_tasks),
            "sourceMessages": sorted(source_messages),
            "sourceHandoffs": sorted(source_handoffs),
            "summary": summary.strip(),
        },
        sort_keys=True,
    )
    return "team-retrospective:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _retrospective_memory_content(summary: str, lessons: list[str], action_items: list[str]) -> str:
    lines = ["# Team Retrospective", "", "## Summary", summary.strip()]
    if lessons:
        lines.extend(["", "## Lessons", *[f"- {lesson}" for lesson in lessons]])
    if action_items:
        lines.extend(["", "## Action Items", *[f"- {item}" for item in action_items]])
    return "\n".join(lines).rstrip() + "\n"


def _validate_skill_refs(
    index: Any,
    *,
    owner_member: str | None,
    projects: list[str],
    required_permissions: list[str],
) -> None:
    if owner_member and owner_member not in index.members:
        raise KeyError(f"unknown owner member {owner_member}")
    for project in projects:
        if project != index.project.object_id:
            raise KeyError(f"unknown project {project}")
    for permission_id in required_permissions:
        if permission_id not in index.permission_policies:
            raise KeyError(f"unknown permission policy {permission_id}")


def _project_for_growth_source(
    index: Any,
    *,
    source_task: str | None,
    source_run: str | None,
    source_review: str | None,
    source_memory_proposal: str | None,
    source_skill: str | None,
) -> str:
    if source_task and source_task in index.tasks:
        return index.tasks[source_task].spec.project
    if source_run and source_run in index.runs:
        return index.runs[source_run].spec.project
    if source_review and source_review in index.reviews:
        return index.reviews[source_review].spec.project
    if source_memory_proposal and source_memory_proposal in index.memory_proposals:
        return index.memory_proposals[source_memory_proposal].spec.project
    if source_skill and source_skill in index.skills:
        projects = index.skills[source_skill].spec.projects
        if projects:
            return projects[0]
    return index.project.object_id


def _validate_growth_source_refs(
    index: Any,
    member_id: str,
    *,
    project: str,
    source_action: str | None,
    source_task: str | None,
    source_run: str | None,
    source_review: str | None,
    source_memory_proposal: str | None,
    source_skill: str | None,
) -> None:
    if source_action and not source_action.startswith(f"{member_id}:"):
        raise ValueError(f"growth action {source_action} does not belong to member {member_id}")
    if source_task:
        task = index.tasks.get(source_task)
        if not task:
            raise KeyError(f"unknown task {source_task}")
        if task.spec.project != project:
            raise ValueError(f"task {source_task} belongs to project {task.spec.project}, not {project}")
        if task.spec.assignedMember and task.spec.assignedMember != member_id:
            raise ValueError(f"task {source_task} is assigned to {task.spec.assignedMember}, not {member_id}")
    if source_run:
        run = index.runs.get(source_run)
        if not run:
            raise KeyError(f"unknown run {source_run}")
        if run.spec.project != project:
            raise ValueError(f"run {source_run} belongs to project {run.spec.project}, not {project}")
        if run.spec.member != member_id:
            raise ValueError(f"run {source_run} belongs to member {run.spec.member}, not {member_id}")
    if source_review:
        review = index.reviews.get(source_review)
        if not review:
            raise KeyError(f"unknown review {source_review}")
        if review.spec.project != project:
            raise ValueError(f"review {source_review} belongs to project {review.spec.project}, not {project}")
        if not _review_matches_growth_member(index, review, member_id):
            raise ValueError(f"review {source_review} is not linked to member {member_id}")
    if source_memory_proposal:
        proposal = index.memory_proposals.get(source_memory_proposal)
        if not proposal:
            raise KeyError(f"unknown memory proposal {source_memory_proposal}")
        if proposal.spec.project != project:
            raise ValueError(f"memory proposal {source_memory_proposal} belongs to project {proposal.spec.project}, not {project}")
        if proposal.spec.member and proposal.spec.member != member_id:
            raise ValueError(f"memory proposal {source_memory_proposal} belongs to member {proposal.spec.member}, not {member_id}")
    if source_skill:
        skill = index.skills.get(source_skill)
        if not skill:
            raise KeyError(f"unknown skill {source_skill}")
        member = index.members[member_id]
        if source_skill not in member.spec.skills and skill.spec.ownerMember != member_id:
            raise ValueError(f"skill {source_skill} is not attached to or owned by member {member_id}")
        if skill.spec.projects and project not in skill.spec.projects:
            raise ValueError(f"skill {source_skill} is not scoped to project {project}")


def _review_matches_growth_member(index: Any, review: Any, member_id: str) -> bool:
    if review.spec.reviewerMember == member_id or review.spec.reviewer == member_id:
        return True
    if review.spec.run:
        run = index.runs.get(review.spec.run)
        if run and run.spec.member == member_id:
            return True
    if review.spec.task:
        task = index.tasks.get(review.spec.task)
        if task and task.spec.assignedMember == member_id:
            return True
    return False


def _optional_ref(kind: str, value: str | None) -> list[str]:
    return [f"{kind}:{value}"] if value else []


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _evidence_record(ref: str) -> dict[str, str]:
    kind, _, value = ref.partition(":")
    return {"kind": kind or "evidence", "ref": value or ref}


def _validate_product_user_refs(index: Any, *, actor_member: str, member: str | None) -> None:
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    if member and member not in index.members:
        raise KeyError(f"unknown product user member {member}")


def _sync_product_user_member_binding(
    workspace_root: Path,
    product_user: ProductUser,
    *,
    actor_member: str,
    previous_member: str | None = None,
) -> None:
    if previous_member and previous_member != product_user.spec.member:
        _clear_member_user_binding(workspace_root, previous_member, product_user.object_id)
    if product_user.spec.member:
        _write_member_user_binding(workspace_root, product_user, actor_member=actor_member)


def _write_member_user_binding(workspace_root: Path, product_user: ProductUser, *, actor_member: str) -> None:
    member_id = product_user.spec.member
    if not member_id:
        return
    path = workspace_root / "members" / f"{member_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    existing = spec.get("userBinding") if isinstance(spec.get("userBinding"), dict) else {}
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    spec["userBinding"] = {
        "productUser": product_user.object_id,
        "source": "ProductUser",
        "identityProvider": product_user.spec.identityProvider,
        "identitySubjectHash": product_user.spec.identitySubjectHash,
        "sessionTokenEnv": product_user.spec.sessionTokenEnv,
        "status": product_user.spec.status,
        "roles": list(product_user.spec.roles),
        "boundAt": existing.get("boundAt") or product_user.metadata.createdAt or now,
        "boundByMember": existing.get("boundByMember") or actor_member,
        "updatedAt": now,
    }
    member = TeamMember.model_validate(data)
    write_yaml(path, member.model_dump(mode="json", exclude_none=True))


def _clear_member_user_binding(workspace_root: Path, member_id: str, product_user_id: str) -> None:
    path = workspace_root / "members" / f"{member_id}.yaml"
    if not path.exists():
        return
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    existing = spec.get("userBinding") if isinstance(spec.get("userBinding"), dict) else None
    if not existing or existing.get("productUser") != product_user_id:
        return
    spec.pop("userBinding", None)
    member = TeamMember.model_validate(data)
    write_yaml(path, member.model_dump(mode="json", exclude_none=True))


def _product_user_permission_decision(
    index: Any,
    *,
    actor_member: str,
    path: str,
    reason: str | None,
) -> dict[str, Any]:
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    decision = explain_effective_permissions(
        index,
        member=actor_member,
        project=index.project.object_id,
        action=edit_action(path),
        non_interactive=actor_kind in {"digital", "service"},
    )
    if decision.get("decision") == "deny" or decision.get("blockers"):
        raise PermissionError(reason or f"actor {actor_member} is not allowed to edit governed ProductUser state")
    if actor_kind == "service" and decision.get("decision") != "allow":
        raise PermissionError("service actors require an explicit allow decision for governed ProductUser state")
    return decision


def _product_user_management_audit(
    index: Any,
    *,
    actor_member: str,
    action: str,
    target_user: str,
    reason: str | None,
    permission_decision: dict[str, Any],
) -> dict[str, Any]:
    actor_kind = index.members[actor_member].spec.kind if actor_member in index.members else None
    if actor_kind == "service":
        decision_kind = "service_policy_decision"
        authority = "enforce"
    elif actor_kind == "digital":
        decision_kind = "digital_recommendation"
        authority = "recommend"
    else:
        decision_kind = "human_approval"
        authority = "approve"
    return {
        "action": action,
        "actorMember": actor_member,
        "actorMemberKind": actor_kind,
        "decisionKind": decision_kind,
        "authority": authority,
        "decidedAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "reason": reason,
        "permissionDecision": permission_decision.get("decision"),
        "policyRefs": list(permission_decision.get("selectedPolicyIds") or []),
        "targetUser": target_user,
    }


def _skill_permission_decision(
    index: Any,
    *,
    actor_member: str,
    path: str,
    reason: str | None,
) -> dict[str, Any]:
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    decision = explain_effective_permissions(
        index,
        member=actor_member,
        project=index.project.object_id,
        action=edit_action(path),
        non_interactive=actor_kind in {"digital", "service"},
    )
    if decision.get("decision") == "deny" or decision.get("blockers"):
        raise PermissionError(reason or f"actor {actor_member} is not allowed to edit governed skill state")
    if actor_kind == "service" and decision.get("decision") != "allow":
        raise PermissionError("service actors require an explicit allow decision for governed skill state")
    return decision


def _skill_decision_audit(
    index: Any,
    *,
    actor_member: str,
    decision: str,
    reason: str | None,
    permission_decision: dict[str, Any],
    skill_id: str,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    actor_kind = index.members[actor_member].spec.kind if actor_member in index.members else None
    decision_kind = "service_policy_decision" if actor_kind == "service" else "human_approval"
    authority = "enforce" if actor_kind == "service" else "approve"
    return decision_audit_record(
        index,
        decision_kind=decision_kind,
        decision=decision,
        actor_member=actor_member,
        authority=authority,
        reason=reason,
        source="skill-lifecycle",
        policy_refs=list(permission_decision.get("selectedPolicyIds") or []),
        evidence=[
            {
                "kind": "skill",
                "skill": skill_id,
                "permissionDecision": permission_decision.get("decision"),
                "permissionReason": permission_decision.get("reason"),
                "nonInteractive": permission_decision.get("nonInteractive"),
            },
            *(evidence or []),
        ],
        risk_assessment=permission_decision.get("riskAssessment"),
    )


def _safe_id(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def _set_memory_status(
    workspace_path: str | Path,
    proposal_id: str,
    status: str,
    *,
    reviewed_at: str | None = None,
    reviewed_by_member: str | None = None,
    review_reason: str | None = None,
    decision_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if proposal_id not in index.memory_proposals:
        raise KeyError(f"unknown memory proposal {proposal_id}")
    path = index.workspace_root / "memory" / "proposals" / f"{proposal_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    spec["status"] = status
    if reviewed_at:
        spec["reviewedAt"] = reviewed_at
    if reviewed_by_member:
        spec["reviewedByMember"] = reviewed_by_member
    if review_reason:
        spec["reviewReason"] = review_reason
    if decision_audit:
        spec.setdefault("decisionAudit", []).append(decision_audit)
    write_yaml(path, data)
    return data


def _write_context_outputs(run_dir: Path, run: Run, context: ContextCompilerResult) -> None:
    capsule_name = run.spec.contextCapsule or "prompt_capsule.md"
    manifest_name = run.spec.contextManifest or "context_manifest.yaml"
    write_text(run_dir / capsule_name, context.capsule)
    manifest = ContextManifest.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "ContextManifest",
            "metadata": {"id": f"{run.object_id}-context"},
            "spec": context.manifest,
        }
    )
    write_yaml(run_dir / manifest_name, manifest.model_dump(mode="json", exclude_none=True))


def _append_run_event(workspace_root: Path, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    return append_run_event_record(workspace_root, run_id, event)


def _append_memory_event(workspace_root: Path, event: dict[str, Any]) -> None:
    ledger_path = workspace_root / "memory" / "events.jsonl"
    events = []
    if ledger_path.exists():
        events = [line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = {
        "seq": len(events) + 1,
        "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        **event,
    }
    events.append(json.dumps(payload, sort_keys=True, ensure_ascii=True))
    write_text(ledger_path, "\n".join(events) + "\n")


def _append_permission_event(workspace_root: Path, event: dict[str, Any]) -> None:
    ledger_path = workspace_root / "permissions" / "events.jsonl"
    events = []
    if ledger_path.exists():
        events = [line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = {
        "seq": len(events) + 1,
        "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        **event,
    }
    events.append(json.dumps(payload, sort_keys=True, ensure_ascii=True))
    write_text(ledger_path, "\n".join(events) + "\n")


def _append_skill_event(workspace_root: Path, event: dict[str, Any]) -> None:
    ledger_path = workspace_root / "skills" / "events.jsonl"
    events = []
    if ledger_path.exists():
        events = [line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = {
        "seq": len(events) + 1,
        "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        **event,
    }
    events.append(json.dumps(payload, sort_keys=True, ensure_ascii=True))
    write_text(ledger_path, "\n".join(events) + "\n")
