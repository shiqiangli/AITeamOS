from __future__ import annotations

from typing import Any

from .loader import WorkspaceIndex, manifest_to_record


SKILL_REDACTION_REASON = "viewer is not authorized to inspect this skill record"
REDACTED_VALUE = "[redacted]"


def skill_records(index: WorkspaceIndex, *, viewer_member: str | None = None) -> list[dict[str, Any]]:
    if viewer_member is not None:
        _member(index, viewer_member)
    return [
        _redact_skill_record(index, manifest_to_record(skill), viewer_member)
        for skill in index.skills.values()
    ]


def skill_record(index: WorkspaceIndex, skill_id: str, *, viewer_member: str | None = None) -> dict[str, Any]:
    if viewer_member is not None:
        _member(index, viewer_member)
    if skill_id not in index.skills:
        raise KeyError(f"unknown skill {skill_id}")
    return _redact_skill_record(index, manifest_to_record(index.skills[skill_id]), viewer_member)


def skill_projection_records(
    index: WorkspaceIndex,
    *,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    viewer_member: str | None = None,
) -> list[dict[str, Any]]:
    project_id = _project_id(index, project) if project else None
    member_id = _member(index, member).object_id if member else None
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
    return [
        _skill_projection_record(index, skill, scope_member=member_id, viewer_member=viewer_member)
        for skill in index.skills.values()
        if _skill_matches_scope(index, skill, project=project_id, member=member_id, assignment=assignment_id)
    ]


def _redact_skill_record(
    index: WorkspaceIndex,
    record: dict[str, Any],
    viewer_member: str | None,
) -> dict[str, Any]:
    if _viewer_can_read_skill(index, record, viewer_member):
        return record
    spec = dict(record.get("spec", {}))
    redacted = {**record, "redacted": True, "redactionReason": SKILL_REDACTION_REASON}
    redacted["spec"] = {
        **spec,
        "description": REDACTED_VALUE if spec.get("description") else None,
        "ownerMember": REDACTED_VALUE if spec.get("ownerMember") else None,
        "projects": [],
        "capabilities": [],
        "requiredPermissions": [],
        "entrypoint": REDACTED_VALUE if spec.get("entrypoint") else None,
        "decisionAudit": [],
        "redacted": True,
        "redactionReason": SKILL_REDACTION_REASON,
    }
    return redacted


def _viewer_can_read_skill(index: WorkspaceIndex, record: dict[str, Any], viewer_member: str | None) -> bool:
    if viewer_member is None:
        return False
    if viewer_member not in index.members:
        return False
    spec = record.get("spec", {})
    if not isinstance(spec, dict):
        return False
    if spec.get("ownerMember") == viewer_member:
        return True
    skill_id = str(record.get("id") or "")
    member = index.members[viewer_member]
    if skill_id and skill_id in set(member.spec.skills):
        return True
    viewer_projects = {
        assignment.spec.project
        for assignment in index.assignments.values()
        if assignment.spec.member == viewer_member
    }
    skill_projects = {str(project) for project in spec.get("projects", []) if project}
    return bool(viewer_projects.intersection(skill_projects))


def _skill_projection_record(
    index: WorkspaceIndex,
    skill: Any,
    *,
    scope_member: str | None,
    viewer_member: str | None,
) -> dict[str, Any]:
    record = _redact_skill_record(index, manifest_to_record(skill), viewer_member)
    if record.get("redacted"):
        return {
            "id": skill.object_id,
            "kind": "SkillProjection",
            "redacted": True,
            "redactionReason": SKILL_REDACTION_REASON,
            "spec": {
                "skill": skill.object_id,
                "lifecycle": skill.spec.lifecycle,
                "projects": [],
                "projectCount": 0,
                "members": [],
                "memberCount": 0,
                "assignments": [],
                "assignmentCount": 0,
                "tasks": [],
                "taskCount": 0,
                "runs": [],
                "runCount": 0,
                "capabilities": [],
                "requiredPermissions": [],
                "memberFitReasons": [],
                "fitSignal": "redacted",
                "redacted": True,
                "redactionReason": SKILL_REDACTION_REASON,
            },
        }
    members = [
        member_id
        for member_id in index.members
        if _skill_matches_member(index, skill, member_id)
    ]
    assignments = [
        assignment_id
        for assignment_id in index.assignments
        if _skill_matches_assignment(index, skill, assignment_id)
    ]
    tasks = [
        task_id
        for task_id, task in index.tasks.items()
        if _skill_matches_task(index, skill, task)
    ]
    runs = [
        run_id
        for run_id, run in index.runs.items()
        if _skill_matches_run(index, skill, run)
    ]
    projects = [
        index.project.object_id
        for project in [index.project]
        if _skill_matches_project(index, skill, project.object_id)
    ]
    return {
        "id": skill.object_id,
        "kind": "SkillProjection",
        "spec": {
            "skill": skill.object_id,
            "ownerMember": skill.spec.ownerMember,
            "lifecycle": skill.spec.lifecycle,
            "projects": projects,
            "projectCount": len(projects),
            "members": members,
            "memberCount": len(members),
            "assignments": assignments,
            "assignmentCount": len(assignments),
            "tasks": tasks,
            "taskCount": len(tasks),
            "runs": runs,
            "runCount": len(runs),
            "capabilities": list(skill.spec.capabilities),
            "requiredPermissions": list(skill.spec.requiredPermissions),
            "memberFitReasons": _skill_fit_reasons_for_member(index, skill, scope_member) if scope_member else [],
            "fitSignal": _skill_fit_signal(skill, members, assignments, tasks, runs),
        },
    }


def _skill_matches_scope(
    index: WorkspaceIndex,
    skill: Any,
    *,
    project: str | None,
    member: str | None,
    assignment: str | None,
) -> bool:
    if project and not _skill_matches_project(index, skill, project):
        return False
    if member and not _skill_matches_member(index, skill, member):
        return False
    if assignment and not _skill_matches_assignment(index, skill, assignment):
        return False
    return True


def _skill_matches_project(index: WorkspaceIndex, skill: Any, project_id: str) -> bool:
    if project_id in set(skill.spec.projects):
        return True
    return any(
        assignment.spec.project == project_id and _skill_matches_assignment(index, skill, assignment_id)
        for assignment_id, assignment in index.assignments.items()
    )


def _skill_matches_member(index: WorkspaceIndex, skill: Any, member_id: str) -> bool:
    return bool(_skill_fit_reasons_for_member(index, skill, member_id))


def _skill_matches_assignment(index: WorkspaceIndex, skill: Any, assignment_id: str) -> bool:
    assignment = index.assignments.get(assignment_id)
    if assignment is None:
        return False
    if _skill_matches_member(index, skill, assignment.spec.member):
        return True
    return assignment.spec.project in set(skill.spec.projects) and _assignment_work_matches_skill(skill, assignment)


def _skill_matches_task(index: WorkspaceIndex, skill: Any, task: Any) -> bool:
    member = task.spec.assignedMember
    assignment = task.spec.assignment
    if (member and _skill_matches_member(index, skill, member)) or (assignment and _skill_matches_assignment(index, skill, assignment)):
        return True
    return task.spec.project in set(skill.spec.projects) and _task_work_matches_skill(skill, task)


def _skill_matches_run(index: WorkspaceIndex, skill: Any, run: Any) -> bool:
    if _skill_matches_member(index, skill, run.spec.member):
        return True
    if run.spec.assignment and _skill_matches_assignment(index, skill, run.spec.assignment):
        return True
    task = index.tasks.get(run.spec.task)
    return bool(task and _skill_matches_task(index, skill, task))


def _skill_fit_reasons_for_member(index: WorkspaceIndex, skill: Any, member_id: str | None) -> list[str]:
    if not member_id or member_id not in index.members:
        return []
    member = index.members[member_id]
    reasons: list[str] = []
    if skill.spec.ownerMember == member_id:
        reasons.append("owner")
    if skill.object_id in set(_member_skill_refs(member)):
        reasons.append("declared-skill")
    if _skill_capability_matches(skill, member):
        reasons.append("capability-match")
    return _unique_strings(reasons)


def _member_skill_refs(member: Any) -> list[str]:
    related = [
        related_skill
        for capability in member.spec.capabilities
        for related_skill in getattr(capability, "relatedSkills", [])
    ]
    return _unique_strings([*member.spec.skills, *related])


def _skill_capability_matches(skill: Any, member: Any) -> list[str]:
    skill_tokens = _skill_capability_tokens(skill)
    member_tokens = _member_capability_tokens(member)
    return [
        token
        for token in skill_tokens
        if any(_token_matches(member_token, token) for member_token in member_tokens)
    ]


def _skill_capability_tokens(skill: Any) -> list[str]:
    return _unique_strings(
        _normalize_skill_token(token)
        for token in [skill.object_id, *skill.spec.capabilities, *_words_from_value(skill.spec.description)]
    )


def _member_capability_tokens(member: Any) -> list[str]:
    capability_names = [
        token
        for capability in member.spec.capabilities
        for token in [getattr(capability, "name", ""), *getattr(capability, "relatedSkills", [])]
    ]
    values = [
        *_member_skill_refs(member),
        *member.spec.aboutMe.coreCapabilities,
        *member.spec.workMethod.methods,
        *capability_names,
    ]
    return _unique_strings(_normalize_skill_token(word) for value in values for word in _words_from_value(value))


def _assignment_work_matches_skill(skill: Any, assignment: Any) -> bool:
    return _skill_text_matches_fields(
        skill,
        [
            assignment.spec.title,
            assignment.spec.roleContext,
            assignment.spec.roleTemplate,
            assignment.spec.modules,
            assignment.spec.features,
            assignment.spec.responsibilities,
        ],
    )


def _task_work_matches_skill(skill: Any, task: Any) -> bool:
    return _skill_text_matches_fields(
        skill,
        [task.spec.title, task.spec.acceptance, task.spec.riskClass, task.spec.executionMode],
    )


def _skill_text_matches_fields(skill: Any, fields: list[Any]) -> bool:
    skill_tokens = [token for token in _skill_capability_tokens(skill) if len(token) >= 4]
    field_tokens = _unique_strings(_normalize_skill_token(word) for value in fields for word in _words_from_value(value))
    return any(
        _token_matches(field_token, skill_token)
        for skill_token in skill_tokens
        for field_token in field_tokens
    )


def _skill_fit_signal(skill: Any, members: list[str], assignments: list[str], tasks: list[str], runs: list[str]) -> str:
    if not skill.spec.ownerMember:
        return "unowned"
    if not members:
        return "no-member-fit"
    if not assignments:
        return "no-assignment-fit"
    if not tasks and not runs:
        return "no-work-linked"
    return "active-fit"


def _words_from_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [word for item in value for word in _words_from_value(item)]
    if isinstance(value, dict):
        return [word for item in value.values() for word in _words_from_value(item)]
    if value is None:
        return []
    return [part.strip() for part in str(value).replace("_", " ").replace("-", " ").split() if part.strip()]


def _normalize_skill_token(value: str) -> str:
    return value.strip().lower()


def _token_matches(left: str, right: str) -> bool:
    return bool(left and right and (left == right or left in right or right in left))


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in result:
            result.append(item)
    return result


def _project_id(index: WorkspaceIndex, project: str | None) -> str:
    project_id = project or index.project.object_id
    if project_id != index.project.object_id:
        raise KeyError(f"unknown project {project_id}")
    return project_id


def _assignment(index: WorkspaceIndex, assignment: str) -> Any:
    if assignment not in index.assignments:
        raise KeyError(f"unknown assignment {assignment}")
    return index.assignments[assignment]


def _member(index: WorkspaceIndex, member: str) -> Any:
    if member not in index.members:
        raise KeyError(f"unknown member {member}")
    return index.members[member]
