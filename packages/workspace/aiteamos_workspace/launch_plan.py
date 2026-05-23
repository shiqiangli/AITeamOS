from __future__ import annotations

from pathlib import Path
from typing import Any

from .loader import WorkspaceIndex, load_workspace


SUPPORTED_RUN_MODES = {"manual", "assisted", "managed_llm", "service"}
MANAGED_RUN_MODES = {"managed_llm"}
BUILTIN_MODEL_PROFILES = {"builtin/openai-gpt-5.5-xhigh", "builtin/openai-gpt-5.4"}


def build_run_launch_plan(
    workspace_or_index: str | Path | WorkspaceIndex,
    task_id: str,
    *,
    member: str | None = None,
    assignment: str | None = None,
    model_profile: str | None = None,
    mode: str | None = None,
    branch_base: str | None = None,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if task_id not in index.tasks:
        raise KeyError(f"unknown task {task_id}")

    task = index.tasks[task_id]
    selected_member = member or task.spec.assignedMember
    selected_assignment = assignment or task.spec.assignment or _single_active_assignment(index, selected_member, task.spec.project)
    member_record = index.members.get(selected_member or "")
    assignment_record = index.assignments.get(selected_assignment or "")
    profile = _execution_profile(index, selected_member, member_record.spec.kind) if member_record else None
    selected_mode = mode or task.spec.executionMode or _default_execution_mode(profile) or index.project.spec.defaultExecutionMode or "assisted"
    selected_model = model_profile or _default_model_profile(index, selected_member, selected_assignment)

    blockers: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []

    if not selected_member:
        blockers.append("No TeamMember selected.")
        actions.append("Assign the task to a TeamMember.")
    elif selected_member not in index.members:
        blockers.append(f"Selected TeamMember {selected_member} does not exist.")
        actions.append("Choose an existing human, digital, hybrid, or service member.")

    if selected_member and task.spec.assignedMember and selected_member != task.spec.assignedMember:
        warnings.append(f"Run member {selected_member} differs from task member {task.spec.assignedMember}.")

    if selected_assignment:
        if selected_assignment not in index.assignments:
            blockers.append(f"Selected assignment {selected_assignment} does not exist.")
            actions.append("Choose an existing assignment for this project/member.")
        elif assignment_record and selected_member and assignment_record.spec.member != selected_member:
            blockers.append(f"Assignment {selected_assignment} belongs to {assignment_record.spec.member}, not {selected_member}.")
            actions.append("Choose an assignment owned by the selected member.")
        elif assignment_record and assignment_record.spec.project != task.spec.project:
            blockers.append(f"Assignment {selected_assignment} belongs to project {assignment_record.spec.project}, not {task.spec.project}.")
            actions.append("Choose an assignment in the task project.")
    else:
        blockers.append("No assignment selected.")
        actions.append("Select the project/module/feature assignment that scopes this run.")

    if member_record and member_record.spec.kind in {"digital", "hybrid", "service"} and profile is None:
        blockers.append(f"Member {selected_member} has no {member_record.spec.kind} execution profile.")
        actions.append("Create the matching execution/collaboration profile before launching.")

    if selected_mode not in SUPPORTED_RUN_MODES:
        blockers.append(f"Run mode {selected_mode} is not supported by the current launcher.")
        actions.append("Choose manual, assisted, managed_llm, or service mode.")

    if selected_model and not _model_profile_exists(index, selected_model):
        blockers.append(f"Model profile {selected_model} does not exist.")
        actions.append("Create the model profile or choose an existing one.")

    if profile is not None and selected_model:
        allowed = set(getattr(profile.spec, "allowedModelProfiles", []) or [])
        if allowed and selected_model not in allowed:
            blockers.append(f"Model profile {selected_model} is not allowed for member {selected_member}.")
            actions.append("Bind the model profile to the member execution profile or choose an allowed profile.")

    if selected_mode in MANAGED_RUN_MODES and not selected_model:
        blockers.append(f"Run mode {selected_mode} requires a model profile.")
        actions.append("Choose a model profile or set a member/assignment default.")
    elif selected_mode in {"manual", "assisted"} and not selected_model:
        warnings.append("Manual/assisted execution can create a context capsule without a model profile.")

    if not blockers:
        if selected_mode in {"manual", "assisted"}:
            actions.append("Create the run, inspect the context capsule, execute manually or in an IDE, then ingest journal/diff/test/review target.")
        elif selected_mode == "service":
            actions.append("Create the service run, check automation permission gates, then execute the service action.")
        else:
            actions.append("Create the run, inspect the context capsule, then start managed LLM execution from Run Detail.")

    base = branch_base or _default_branch(index)
    branch_preview = f"aiteamos/{task_id}/{selected_member or '<member>'}/RUN-YYYYMMDDTHHMMSSmmm"
    can_create_run = not blockers

    return {
        "task": task_id,
        "summary": _summary(can_create_run, blockers, warnings, selected_mode),
        "canCreateRun": can_create_run,
        "selectedMember": selected_member,
        "assignedMember": task.spec.assignedMember,
        "selectedAssignment": selected_assignment,
        "selectedMode": selected_mode,
        "selectedModelProfile": selected_model,
        "memberKind": member_record.spec.kind if member_record else None,
        "branchBase": base,
        "branchPreview": branch_preview,
        "blockers": blockers,
        "warnings": warnings,
        "actions": actions,
        "memberOptions": _member_options(index),
        "assignmentOptions": _assignment_options(index, selected_member, task.spec.project),
        "modelOptions": _model_options(index, selected_member),
    }


def _single_active_assignment(index: WorkspaceIndex, member_id: str | None, project: str) -> str | None:
    if not member_id:
        return None
    matches = [
        assignment.object_id
        for assignment in index.assignments.values()
        if assignment.spec.member == member_id and assignment.spec.project == project and assignment.spec.status == "active"
    ]
    return sorted(matches)[0] if len(matches) == 1 else None


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


def _default_execution_mode(profile: Any | None) -> str | None:
    if profile is None:
        return None
    runtime = getattr(profile.spec, "workerRuntime", None)
    if isinstance(runtime, dict):
        return runtime.get("defaultMode")
    ingest_policy = getattr(profile.spec, "ingestPolicy", None)
    if isinstance(ingest_policy, dict):
        return ingest_policy.get("defaultMode")
    return None


def _default_model_profile(index: WorkspaceIndex, member_id: str | None, assignment_id: str | None) -> str | None:
    if not member_id or member_id not in index.members:
        return None
    member = index.members[member_id]
    profile = _execution_profile(index, member_id, member.spec.kind)
    if profile is not None and getattr(profile.spec, "defaultModelProfile", None):
        return profile.spec.defaultModelProfile
    for profile_id, model in sorted(index.model_profiles.items()):
        if assignment_id and assignment_id in model.spec.defaultForAssignments:
            return profile_id
        if member_id in model.spec.defaultForMembers:
            return profile_id
    return None


def _model_profile_exists(index: WorkspaceIndex, model_profile: str) -> bool:
    return model_profile in index.model_profiles or model_profile in BUILTIN_MODEL_PROFILES


def _default_branch(index: WorkspaceIndex) -> str:
    default_repo = next(iter(index.repositories.values()), None)
    return (default_repo.spec.defaultBranch if default_repo else None) or "develop"


def _member_options(index: WorkspaceIndex) -> list[dict[str, Any]]:
    return [
        {
            "id": member_id,
            "kind": member.spec.kind,
            "displayName": member.spec.profile.displayName or member_id,
            "defaultAssignments": member.spec.defaultAssignments,
        }
        for member_id, member in sorted(index.members.items())
    ]


def _assignment_options(index: WorkspaceIndex, selected_member: str | None, project: str) -> list[dict[str, Any]]:
    options = []
    for assignment_id, assignment in sorted(index.assignments.items()):
        if assignment.spec.project != project:
            continue
        options.append(
            {
                "id": assignment_id,
                "member": assignment.spec.member,
                "title": assignment.spec.title,
                "status": assignment.spec.status,
                "roleTemplate": assignment.spec.roleTemplate,
                "selectedMemberMatch": not selected_member or assignment.spec.member == selected_member,
            }
        )
    return options


def _model_options(index: WorkspaceIndex, selected_member: str | None) -> list[dict[str, Any]]:
    allowed = set()
    if selected_member and selected_member in index.members:
        member = index.members[selected_member]
        profile = _execution_profile(index, selected_member, member.spec.kind)
        if profile is not None:
            allowed = set(getattr(profile.spec, "allowedModelProfiles", []) or [])
    options = []
    for profile_id in sorted(index.model_profiles):
        profile = index.model_profiles[profile_id]
        options.append(
            {
                "id": profile_id,
                "displayName": profile.spec.displayName or profile_id,
                "provider": profile.spec.provider,
                "model": profile.spec.model,
                "capabilities": profile.spec.capabilities,
                "allowedForSelectedMember": not allowed or profile_id in allowed,
            }
        )
    for profile_id in sorted(allowed - set(index.model_profiles)):
        if profile_id in BUILTIN_MODEL_PROFILES:
            options.append(
                {
                    "id": profile_id,
                    "displayName": profile_id,
                    "provider": "builtin",
                    "model": profile_id,
                    "capabilities": ["managed_llm", "assisted"],
                    "allowedForSelectedMember": True,
                }
            )
    return options


def _summary(can_create_run: bool, blockers: list[str], warnings: list[str], mode: str) -> str:
    if blockers:
        return f"Run launch is blocked: {blockers[0]}"
    if warnings:
        return f"Run can be created in {mode} mode with warnings."
    return f"Run can be created in {mode} mode."
