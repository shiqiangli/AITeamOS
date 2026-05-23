from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .loader import WorkspaceIndex, load_workspace, manifest_to_record
from .model_policy import resolve_run_model_profile
from .mutations import create_permission_request
from .permission_outcomes import denied_permission_decisions, permission_outcome_state, select_permission_decision, permission_action_canonical
from .permissions import bash_action, edit_action, explain_effective_permissions


PROTECTED_BRANCHES = {"main", "master", "develop", "development", "release", "production"}
UNSAFE_BRANCH_RE = re.compile(r"(^-|\\|\s|//|@\{|\.lock$)")
MANAGED_WORKER_MODES = {"managed_llm"}


def expected_worktree_path(index: WorkspaceIndex, run_id: str) -> Path:
    return (index.workspace_root / "artifacts" / "worktrees" / run_id).resolve()


def validate_branch_name(branch: str | None) -> list[str]:
    if not branch:
        return ["branch name is missing"]
    if branch in PROTECTED_BRANCHES:
        return [f"branch {branch} is protected"]
    if branch.startswith("/") or ".." in Path(branch).parts or UNSAFE_BRANCH_RE.search(branch):
        return [f"branch {branch} is unsafe"]
    return []


def validate_managed_worktree(index: WorkspaceIndex, run_id: str, worktree: str | Path | None) -> list[str]:
    if not worktree:
        return []
    expected = expected_worktree_path(index, run_id)
    resolved = Path(worktree).expanduser().resolve()
    if resolved != expected:
        return [f"worktree {resolved} is outside the managed run worktree {expected}"]
    return []


def evaluate_worker_authorization(workspace_or_index: str | Path | WorkspaceIndex, run_id: str) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    checks: list[dict[str, str]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    permission_decisions: list[dict[str, Any]] = []

    def check(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})
        if status == "fail":
            blockers.append(message)
        elif status == "warn":
            warnings.append(message)

    task = index.tasks.get(run.spec.task)
    member = index.members.get(run.spec.member)
    assignment = index.assignments.get(run.spec.assignment or "")

    if run.spec.mode in MANAGED_WORKER_MODES:
        check("worker-auth-mode", "pass", f"Run mode {run.spec.mode} is worker-managed.")
    else:
        check("worker-auth-mode", "fail", f"Run mode {run.spec.mode} is not a managed worker mode; use assisted/manual ingest instead.")

    if task is None:
        check("worker-auth-task", "fail", f"Run references missing task {run.spec.task}.")
    elif task.spec.assignedMember and task.spec.assignedMember != run.spec.member:
        check("worker-auth-task", "fail", f"Run member {run.spec.member} does not match task assignee {task.spec.assignedMember}.")
    else:
        check("worker-auth-task", "pass", f"Task {run.spec.task} is bound to member {run.spec.member}.")

    if member is None:
        check("worker-auth-member", "fail", f"Run references missing TeamMember {run.spec.member}.")
    else:
        check("worker-auth-member", "pass", f"TeamMember {run.spec.member} exists with kind {member.spec.kind}.")
        if run.spec.memberKind and run.spec.memberKind != member.spec.kind:
            check("worker-auth-member-kind", "fail", f"Run declares member kind {run.spec.memberKind}, but member is {member.spec.kind}.")
        else:
            check("worker-auth-member-kind", "pass", "Run member kind matches the TeamMember identity.")
        if run.spec.mode == "managed_llm" and member.spec.kind != "digital":
            check("worker-auth-mode-member-kind", "fail", f"managed_llm worker runs require a digital member, but {run.spec.member} is {member.spec.kind}.")
        elif run.spec.mode == "service" and member.spec.kind != "service":
            check("worker-auth-mode-member-kind", "fail", f"service worker runs require a service member, but {run.spec.member} is {member.spec.kind}.")
        elif run.spec.mode in MANAGED_WORKER_MODES:
            check("worker-auth-mode-member-kind", "pass", f"Run mode {run.spec.mode} matches member kind {member.spec.kind}.")

    if assignment is None:
        check("worker-auth-assignment", "fail", "Run has no valid assignment for project/module/feature scope.")
    else:
        if assignment.spec.member != run.spec.member:
            check("worker-auth-assignment", "fail", f"Assignment {assignment.object_id} belongs to {assignment.spec.member}, not {run.spec.member}.")
        elif assignment.spec.project != run.spec.project:
            check("worker-auth-assignment", "fail", f"Assignment {assignment.object_id} belongs to project {assignment.spec.project}, not {run.spec.project}.")
        elif assignment.spec.status != "active":
            check("worker-auth-assignment", "fail", f"Assignment {assignment.object_id} is {assignment.spec.status}, not active.")
        else:
            check("worker-auth-assignment", "pass", f"Assignment {assignment.object_id} scopes this run.")

        if not assignment.spec.scope.write:
            check("worker-auth-write-scope", "fail", "Managed workers require an explicit assignment write scope.")
        else:
            check("worker-auth-write-scope", "pass", "Assignment has an explicit managed worker write scope.")

    profile = _execution_profile(index, run.spec.member, member.spec.kind if member else None)
    selected_model, selected_model_source = resolve_run_model_profile(index, run)
    allowed_models = set(getattr(profile.spec, "allowedModelProfiles", []) or []) if profile is not None else set()
    if selected_model and allowed_models and selected_model not in allowed_models:
        check("worker-auth-model", "fail", f"Model profile {selected_model} is not allowed for member {run.spec.member}.")
    elif selected_model:
        check("worker-auth-model", "pass", f"Model profile {selected_model} is allowed for member {run.spec.member} from {selected_model_source}.")
    elif run.spec.mode == "managed_llm":
        check("worker-auth-model", "fail", "Managed LLM worker run has no model profile from run/member/assignment defaults.")
    else:
        check("worker-auth-model", "warn", "No model profile is selected; this is acceptable only for non-LLM service actions.")

    policy_ids = _permission_policy_ids(member, assignment, profile)
    missing_policies = [policy_id for policy_id in policy_ids if policy_id not in index.permission_policies]
    if missing_policies:
        check("worker-auth-permissions", "fail", f"Missing permission policies: {', '.join(sorted(missing_policies))}.")
    elif policy_ids:
        check("worker-auth-permissions", "pass", f"Permission policies apply: {', '.join(policy_ids)}.")
    elif member and member.spec.kind in {"digital", "service"}:
        check("worker-auth-permissions", "fail", f"{member.spec.kind} members require explicit permission policies before worker execution.")
    else:
        check("worker-auth-permissions", "warn", "No explicit permission policy is attached to this run.")

    run_data = run.model_dump(mode="json").get("spec", {})
    worker = run_data.get("worker") if isinstance(run_data.get("worker"), dict) else {}
    verification_commands = _verification_commands(worker)
    for command in verification_commands:
        permission = _explain_run_permission(index, run, command_action(command))
        permission_decisions.append(_permission_decision_summary(permission))
        if permission["decision"] != "allow" or permission["blockers"]:
            check(
                "worker-auth-action-bash",
                "fail",
                f"Verification command denied by effective permissions: {permission['normalizedAction']['canonical']} ({permission['reason']}).",
            )
        else:
            check("worker-auth-action-bash", "pass", f"Verification command allowed: {permission['normalizedAction']['canonical']}.")

    branch = run.spec.branch.name if run.spec.branch else f"aiteamos/{run.spec.task}/{run.spec.member}/{run_id}"
    branch_violations = validate_branch_name(branch)
    if branch_violations:
        check("worker-auth-branch", "fail", "; ".join(branch_violations))
    else:
        check("worker-auth-branch", "pass", f"Worker branch {branch} is safe to create.")

    worktree_value = run_data.get("worktree") or worker.get("worktree")
    worktree_violations = validate_managed_worktree(index, run_id, worktree_value)
    if worktree_violations:
        check("worker-auth-worktree", "fail", "; ".join(worktree_violations))
    elif worktree_value:
        check("worker-auth-worktree", "pass", "Recorded worktree is the managed run worktree.")
    else:
        check("worker-auth-worktree", "pass", "No existing worktree is recorded; worker will use the managed run worktree.")

    denied_decisions = denied_permission_decisions(permission_decisions)
    permission_state = permission_outcome_state(
        index,
        member=run.spec.member,
        project=run.spec.project,
        assignment=run.spec.assignment,
        task=run.spec.task,
        run=run_id,
        permission_decisions=denied_decisions,
        still_blocked_when_active=bool(denied_decisions),
    )
    return {
        "run": run_id,
        "member": run.spec.member,
        "assignment": run.spec.assignment,
        "ready": not blockers,
        "status": "READY" if not blockers else "BLOCKED",
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "permissionDecisions": permission_decisions,
        "permissionApprovalRequired": bool(denied_decisions),
        "permissionRequests": permission_state["requests"],
        "pendingPermissionRequests": permission_state["pendingRequests"],
        "pendingPermissionRequestIds": [item["id"] for item in permission_state["pendingRequests"]],
        "approvedPermissionRequestIds": [item["id"] for item in permission_state["approvedRequests"]],
        "rejectedPermissionRequestIds": [item["id"] for item in permission_state["rejectedRequests"]],
        "activePermissionGrantIds": [item["id"] for item in permission_state["activeGrants"]],
        "expiredPermissionGrantIds": [item["id"] for item in permission_state["expiredGrants"]],
        "revokedPermissionGrantIds": [item["id"] for item in permission_state["revokedGrants"]],
        "permissionApprovalOutcome": permission_state["outcome"],
        "permissionOutcomeExplanation": permission_state["explanation"],
    }


def request_run_worker_permission(
    workspace_path: str | Path,
    run_id: str,
    *,
    actor_member: str,
    action_canonical: str | None = None,
    action_index: int | None = None,
    reason: str | None = None,
    expires_at: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    actor = index.members.get(actor_member)
    if actor is None:
        raise KeyError(f"unknown actor member {actor_member}")
    if actor.spec.kind not in {"human", "service"}:
        raise ValueError("run worker permission requests require a human or governed service actor member")
    run = index.runs.get(run_id)
    if run is None:
        raise KeyError(f"unknown run {run_id}")
    authorization = evaluate_worker_authorization(index, run_id)
    denied_decisions = denied_permission_decisions(authorization.get("permissionDecisions", []))
    if not denied_decisions:
        return {
            "dryRun": dry_run,
            "written": False,
            "canRequest": False,
            "authorization": authorization,
            "blockers": ["run worker authorization has no denied permission actions"],
            "warnings": [],
        }
    selected_decision = select_permission_decision(
        denied_decisions,
        action_canonical=action_canonical,
        action_index=action_index,
    )
    action = selected_decision.get("action") if isinstance(selected_decision.get("action"), dict) else {}
    if not action:
        raise ValueError("selected permission decision has no action")
    current_decision = _explain_run_permission(index, run, action)
    canonical = permission_action_canonical(current_decision.get("normalizedAction") or action)
    if current_decision.get("decision") == "allow" and not current_decision.get("blockers"):
        return {
            "dryRun": dry_run,
            "written": False,
            "canRequest": False,
            "authorization": authorization,
            "action": current_decision.get("normalizedAction") or action,
            "selectedPermissionDecision": selected_decision,
            "currentDecision": current_decision,
            "permissionApprovalOutcome": "not-required",
            "blockers": [f"current effective permissions already allow {canonical}"],
            "warnings": [],
        }
    state = permission_outcome_state(
        index,
        member=run.spec.member,
        project=run.spec.project,
        assignment=run.spec.assignment,
        task=run.spec.task,
        run=run.object_id,
        permission_decisions=[selected_decision],
        still_blocked_when_active=True,
    )
    if state["pendingRequests"]:
        return {
            "dryRun": dry_run,
            "written": False,
            "canRequest": False,
            "authorization": authorization,
            "action": current_decision.get("normalizedAction") or action,
            "selectedPermissionDecision": selected_decision,
            "currentDecision": current_decision,
            "existingRequest": state["pendingRequests"][0],
            "blockers": [f"pending PermissionRequest {state['pendingRequests'][0]['id']} already covers {canonical}"],
            "warnings": [],
        }
    if state["activeGrants"]:
        return {
            "dryRun": dry_run,
            "written": False,
            "canRequest": False,
            "authorization": authorization,
            "action": current_decision.get("normalizedAction") or action,
            "selectedPermissionDecision": selected_decision,
            "currentDecision": current_decision,
            "activePermissionGrants": state["activeGrants"],
            "permissionApprovalOutcome": "approved-but-still-blocked",
            "blockers": [f"active PermissionGrant already covers {canonical}, but effective deny-first policy still blocks this run action"],
            "warnings": [],
        }
    request_preview = {
        "member": run.spec.member,
        "project": run.spec.project,
        "assignment": run.spec.assignment,
        "task": run.spec.task,
        "run": run.object_id,
        "requesterMember": actor_member,
        "action": current_decision.get("normalizedAction") or action,
        "reason": reason or f"Run {run.object_id} needs approval for {canonical}.",
        "expiresAt": expires_at,
        "source": "run-worker-authorization-permission-request",
    }
    if dry_run:
        return {
            "dryRun": True,
            "written": False,
            "canRequest": True,
            "authorization": authorization,
            "requestPreview": request_preview,
            "selectedPermissionDecision": selected_decision,
            "currentDecision": current_decision,
            "blockers": [],
            "warnings": [],
        }
    request = create_permission_request(
        workspace_path,
        member=run.spec.member,
        action=current_decision.get("normalizedAction") or action,
        project=run.spec.project,
        assignment=run.spec.assignment,
        task=run.spec.task,
        run=run.object_id,
        requester_member=actor_member,
        reason=reason or f"Run {run.object_id} needs approval for {canonical}.",
        expires_at=expires_at,
        current_decision=current_decision,
        source="run-worker-authorization-permission-request",
    )
    refreshed = load_workspace(workspace_path)
    return {
        "dryRun": False,
        "written": True,
        "canRequest": True,
        "authorization": evaluate_worker_authorization(refreshed, run_id),
        "permissionRequest": manifest_to_record(request),
        "selectedPermissionDecision": selected_decision,
        "currentDecision": current_decision,
        "blockers": [],
        "warnings": [],
    }


def command_action(command: str) -> dict[str, Any]:
    return bash_action(command)


def _explain_run_permission(index: WorkspaceIndex, run: Any, action: dict[str, Any]) -> dict[str, Any]:
    return explain_effective_permissions(
        index,
        member=run.spec.member,
        project=run.spec.project,
        assignment=run.spec.assignment,
        action=action,
        non_interactive=True,
    )


def _verification_commands(worker: dict[str, Any]) -> list[str]:
    value = worker.get("verificationCommands") or worker.get("testCommands") or []
    if isinstance(value, str):
        value = [line.strip() for line in value.splitlines() if line.strip()]
    return [str(command).strip() for command in value if str(command).strip()]


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


def _execution_profile(index: WorkspaceIndex, member_id: str | None, member_kind: str | None) -> Any | None:
    if not member_id or not member_kind:
        return None
    stores = {
        "digital": index.digital_execution_profiles,
        "human": index.human_collaboration_profiles,
        "hybrid": index.hybrid_execution_profiles,
        "service": index.service_account_profiles,
    }
    return stores.get(member_kind, {}).get(member_id)


def _permission_policy_ids(member: Any | None, assignment: Any | None, profile: Any | None) -> list[str]:
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
    tool_policy = getattr(getattr(profile, "spec", None), "toolPolicy", None)
    if isinstance(tool_policy, dict):
        add(tool_policy.get("permissionPolicy"))
    return policy_ids
