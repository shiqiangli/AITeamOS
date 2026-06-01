"""
API Gateway — Member / Department / Project Read Routes (plan.md §1.5.2).

GET /api/v1/members              — 列表
GET /api/v1/members/{id}         — 详情（含已分配 Skill/Memory）
GET /api/v1/departments          — 列表
GET /api/v1/projects             — 列表
GET /api/v1/projects/{id}        — 详情（含关联 Members/Repository）
"""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from aiteamos_workforce.application.queries import (
    ListDepartmentsExecutor,
    ListMembersExecutor,
    ListProjectsExecutor,
)

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(tags=["workforce-read"])

_members_executor: ListMembersExecutor | None = None
_departments_executor: ListDepartmentsExecutor | None = None
_projects_executor: ListProjectsExecutor | None = None

# Placeholder for detail repos (member detail with skill/memory assignments)
_member_detail_repo: Any = None
_project_detail_repo: Any = None
_db: Any = None


def init_routes(
    *,
    members_executor: ListMembersExecutor,
    departments_executor: ListDepartmentsExecutor,
    projects_executor: ListProjectsExecutor,
    member_detail_repo: Any = None,
    project_detail_repo: Any = None,
    db: Any = None,
) -> None:
    global _db
    global _members_executor, _departments_executor, _projects_executor
    global _member_detail_repo, _project_detail_repo
    _members_executor = members_executor
    _departments_executor = departments_executor
    _projects_executor = projects_executor
    _member_detail_repo = member_detail_repo
    _project_detail_repo = project_detail_repo
    _db = db


@router.get("/api/v1/members", response_model=list[dict[str, Any]])
async def list_members(
    department_id: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _members_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_workforce.application.commands import ListMembersQuery
    from aiteamos_shared.types import MemberKind

    query = ListMembersQuery(
        department_id=UUID(department_id) if department_id else None,  # type: ignore[arg-type]
        kind=MemberKind(kind) if kind else None,
        offset=offset,
        limit=limit,
    )
    results = await _members_executor.execute(query)
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "display_name": r.display_name,
            "role": r.role,
            "department_id": r.department_id,
            "concurrency_limit": r.concurrency_limit,
            "is_archived": r.is_archived,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in results
    ]


@router.get("/api/v1/members/{member_id}", response_model=dict[str, Any])
async def get_member_detail(
    member_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _member_detail_repo is not None:
        return await _get_member_base(member_id)
    from ..middleware.error_handler import ApiError
    raise ApiError(status_code=501, detail="Member detail not available", code="NOT_IMPLEMENTED")


@router.get("/api/v1/members/{member_id}/profile", response_model=dict[str, Any])
async def get_member_profile(
    member_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the dashboard read model for the member detail surface."""
    member = await _get_member_base(member_id)
    if _db is None:
        return _empty_member_profile(member)

    skills = await _fetch_member_skills(member_id)
    memories = await _fetch_member_memories(member_id)
    projects = await _fetch_member_projects(member_id)
    tasks = await _fetch_member_tasks(member_id)
    activities = await _fetch_member_activities(member_id)
    capability_changes = _capability_changes(skills=skills, memories=memories)
    stats = _member_profile_stats(
        skills=skills,
        memories=memories,
        projects=projects,
        tasks=tasks,
        activities=activities,
    )

    return {
        "member": member,
        "stats": stats,
        "skills": skills,
        "memories": memories,
        "projects": projects,
        "tasks": tasks,
        "activities": activities,
        "capability_changes": capability_changes,
    }


@router.get("/api/v1/members/{member_id}/prompt/preview", response_model=dict[str, Any])
async def get_member_prompt_preview(
    member_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the rendered prompt using current skills, memories, and context.

    This is a read-only preview. Template placeholders are filled with
    live data from the member's current assignments.
    """
    member_data = await _get_member_base(member_id)
    template = member_data.get("prompt_template", "")
    if not template:
        return {"template": "", "rendered": "", "variables_used": []}

    skills = await _fetch_member_skills(member_id)
    memories = await _fetch_member_memories(member_id)

    skill_descriptions = "\n".join(
        f"- {s['name']}: {s.get('description') or 'No description'}"
        for s in skills
    ) or "- No skills assigned"

    memory_summaries = "\n".join(
        f"- [{m.get('tier', 'unknown')}] {m['title']}"
        for m in memories
    ) or "- No memories assigned"

    replacements = {
        "{member_name}": member_data.get("display_name", ""),
        "{member_role}": member_data.get("role", ""),
        "{member_kind}": member_data.get("kind", ""),
        "{skill_descriptions}": skill_descriptions,
        "{memory_summaries}": memory_summaries,
    }

    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)

    variables_used = [
        k.strip("{}")
        for k, v in replacements.items()
        if k in template and v and not v.startswith("- No")
    ]

    return {
        "template": template,
        "rendered": rendered,
        "variables_used": variables_used,
        "token_estimate": len(rendered.split()) * 4 // 3,
    }


@router.get("/api/v1/departments", response_model=list[dict[str, Any]])
async def list_departments(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _departments_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_workforce.application.commands import ListDepartmentsQuery

    query = ListDepartmentsQuery(offset=offset, limit=limit)
    results = await _departments_executor.execute(query)
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "leader_member_id": r.leader_member_id,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in results
    ]


@router.get("/api/v1/projects", response_model=list[dict[str, Any]])
async def list_projects(
    department_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _projects_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_workforce.application.commands import ListProjectsQuery

    query = ListProjectsQuery(
        department_id=UUID(department_id) if department_id else None,  # type: ignore[arg-type]
        status=status,
        offset=offset,
        limit=limit,
    )
    results = await _projects_executor.execute(query)
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "department_id": r.department_id,
            "status": r.status,
            "member_count": r.member_count,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in results
    ]


@router.get("/api/v1/projects/{project_id}", response_model=dict[str, Any])
async def get_project_detail(
    project_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _project_detail_repo is not None:
        project = await _project_detail_repo.get_by_id(project_id)
        if project is None:
            from ..middleware.error_handler import NotFoundError
            raise NotFoundError(detail=f"Project {project_id} not found")
        return {
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "department_id": str(project.department_id),
            "repository_refs": project.repository_refs,
            "harness_config": project.harness_config,
            "status": project.status.value,
            "member_ids": [str(m) for m in project.member_ids],
            "created_at": str(project.created_at),
            "archived_at": str(project.archived_at) if project.archived_at else None,
        }
    from ..middleware.error_handler import ApiError
    raise ApiError(status_code=501, detail="Project detail not available", code="NOT_IMPLEMENTED")


async def _get_member_base(member_id: UUID) -> dict[str, Any]:
    if _member_detail_repo is None:
        from ..middleware.error_handler import ApiError
        raise ApiError(status_code=501, detail="Member detail not available", code="NOT_IMPLEMENTED")

    member = await _member_detail_repo.get_by_id(member_id)
    if member is None:
        from ..middleware.error_handler import NotFoundError
        raise NotFoundError(detail=f"Member {member_id} not found")
    return {
        "id": str(member.id),
        "kind": member.kind.value,
        "display_name": member.profile.display_name,
        "role": member.profile.role,
        "department_id": str(member.department_id),
        "concurrency_limit": member.concurrency_limit,
        "base_skill_set": [str(s) for s in member.base_skill_set],
        "assigned_memories": [str(m) for m in member.assigned_memories],
        "prompt_template": member.prompt_template,
        "is_archived": member.is_archived,
        "created_at": str(member.created_at),
    }


def _empty_member_profile(member: dict[str, Any]) -> dict[str, Any]:
    return {
        "member": member,
        "stats": {
            "skill_count": 0,
            "memory_count": 0,
            "project_count": 0,
            "task_count": 0,
            "active_task_count": 0,
            "done_task_count": 0,
            "failed_task_count": 0,
            "done_rate": None,
            "activity_count": 0,
            "last_activity_at": member.get("created_at"),
        },
        "skills": [],
        "memories": [],
        "projects": [],
        "tasks": [],
        "activities": [],
        "capability_changes": [],
    }


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _as_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def _fetch_member_skills(member_id: UUID) -> list[dict[str, Any]]:
    rows = await _db.fetch(
        """
        SELECT
            msa.skill_id,
            msa.is_base,
            msa.assigned_at,
            s.name,
            s.version,
            s.description,
            s.domain,
            s.status,
            s.capability_tags,
            s.created_at
        FROM member_skill_assignment msa
        LEFT JOIN skill s ON s.id = msa.skill_id
        WHERE msa.member_id = $1
        ORDER BY msa.assigned_at DESC
        """,
        member_id,
    )
    results: list[dict[str, Any]] = []
    for row in rows:
        version = _row_get(row, "version")
        skill_id = _row_get(row, "skill_id")
        results.append({
            "id": str(skill_id),
            "name": _row_get(row, "name") or str(skill_id),
            "version": version,
            "description": _row_get(row, "description"),
            "domain": _row_get(row, "domain"),
            "status": _row_get(row, "status"),
            "capability_tags": _row_get(row, "capability_tags", []),
            "is_base": bool(_row_get(row, "is_base", False)),
            "assigned_at": _iso(_row_get(row, "assigned_at")),
            "created_at": _iso(_row_get(row, "created_at")),
        })
    return results


async def _fetch_member_memories(member_id: UUID) -> list[dict[str, Any]]:
    rows = await _db.fetch(
        """
        SELECT
            mma.memory_id,
            mma.weight,
            mma.assigned_at,
            mn.title,
            mn.tier,
            mn.lifecycle_state,
            mn.confidence_value,
            mn.scope_kind,
            mn.current_version,
            mn.created_at
        FROM member_memory_assignment mma
        LEFT JOIN memory_node mn ON mn.id = mma.memory_id
        WHERE mma.member_id = $1
        ORDER BY mma.assigned_at DESC
        """,
        member_id,
    )
    return [
        {
            "id": str(_row_get(row, "memory_id")),
            "title": _row_get(row, "title") or str(_row_get(row, "memory_id")),
            "tier": _row_get(row, "tier"),
            "lifecycle_state": _row_get(row, "lifecycle_state"),
            "confidence_value": float(_row_get(row, "confidence_value")) if _row_get(row, "confidence_value") is not None else None,
            "scope_kind": _row_get(row, "scope_kind"),
            "current_version": _row_get(row, "current_version"),
            "weight": float(_row_get(row, "weight", 1.0)),
            "assigned_at": _iso(_row_get(row, "assigned_at")),
            "created_at": _iso(_row_get(row, "created_at")),
        }
        for row in rows
    ]


async def _fetch_member_projects(member_id: UUID) -> list[dict[str, Any]]:
    rows = await _db.fetch(
        """
        SELECT
            p.id,
            p.name,
            p.description,
            p.department_id,
            p.status,
            p.created_at,
            pm.role,
            pm.assigned_at
        FROM project_member pm
        JOIN project p ON p.id = pm.project_id
        WHERE pm.member_id = $1
        ORDER BY pm.assigned_at DESC
        """,
        member_id,
    )
    return [
        {
            "id": str(_row_get(row, "id")),
            "name": _row_get(row, "name"),
            "description": _row_get(row, "description"),
            "department_id": str(_row_get(row, "department_id")) if _row_get(row, "department_id") else None,
            "status": _row_get(row, "status"),
            "role": _row_get(row, "role"),
            "assigned_at": _iso(_row_get(row, "assigned_at")),
            "created_at": _iso(_row_get(row, "created_at")),
        }
        for row in rows
    ]


async def _fetch_member_tasks(member_id: UUID) -> list[dict[str, Any]]:
    rows = await _db.fetch(
        """
        SELECT
            j.job_id,
            j.task_id,
            t.title,
            t.state AS task_state,
            j.phase,
            j.state AS job_state,
            j.started_at,
            j.finished_at
        FROM job j
        JOIN task t ON j.task_id = t.id
        WHERE j.member_id = $1
        ORDER BY j.started_at DESC
        LIMIT 100
        """,
        member_id,
    )
    return [
        {
            "job_id": str(_row_get(row, "job_id")),
            "task_id": _row_get(row, "task_id"),
            "title": _row_get(row, "title"),
            "task_state": _row_get(row, "task_state"),
            "phase": _row_get(row, "phase"),
            "job_state": _row_get(row, "job_state"),
            "started_at": _iso(_row_get(row, "started_at")),
            "finished_at": _iso(_row_get(row, "finished_at")),
        }
        for row in rows
    ]


async def _fetch_member_activities(member_id: UUID) -> list[dict[str, Any]]:
    rows = await _db.fetch(
        """
        SELECT id, event_kind, event_payload, occurred_at
        FROM member_activity_event
        WHERE member_id = $1
        ORDER BY occurred_at DESC
        LIMIT 200
        """,
        member_id,
    )
    results: list[dict[str, Any]] = []
    for row in rows:
        payload = _as_json_dict(_row_get(row, "event_payload"))
        results.append({
            "id": str(_row_get(row, "id")),
            "kind": _row_get(row, "event_kind"),
            "label": payload.get("label") or payload.get("title") or _row_get(row, "event_kind"),
            "occurred_at": _iso(_row_get(row, "occurred_at")),
            "target_kind": payload.get("target_kind"),
            "target_id": payload.get("target_id"),
            "payload": payload,
        })
    return results


def _capability_changes(
    *,
    skills: list[dict[str, Any]],
    memories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for skill in skills:
        changes.append({
            "id": f"skill:{skill['id']}",
            "kind": "skill_assigned",
            "target_kind": "skill",
            "target_id": skill["id"],
            "label": skill.get("name") or skill["id"],
            "occurred_at": skill.get("assigned_at"),
        })
    for memory in memories:
        changes.append({
            "id": f"memory:{memory['id']}",
            "kind": "memory_assigned",
            "target_kind": "memory",
            "target_id": memory["id"],
            "label": memory.get("title") or memory["id"],
            "occurred_at": memory.get("assigned_at"),
        })
    return sorted(changes, key=lambda item: item.get("occurred_at") or "", reverse=True)


def _member_profile_stats(
    *,
    skills: list[dict[str, Any]],
    memories: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    activities: list[dict[str, Any]],
) -> dict[str, Any]:
    done_count = sum(1 for task in tasks if task.get("state") == "done")
    failed_count = sum(1 for task in tasks if task.get("state") == "failed")
    active_count = sum(
        1 for task in tasks
        if task.get("state") not in {"done", "failed", "cancelled"}
    )
    last_candidates = [
        value for value in (
            [activity.get("occurred_at") for activity in activities]
            + [task.get("updated_at") or task.get("created_at") for task in tasks]
        )
        if value
    ]
    return {
        "skill_count": len(skills),
        "memory_count": len(memories),
        "project_count": len(projects),
        "task_count": len(tasks),
        "active_task_count": active_count,
        "done_task_count": done_count,
        "failed_task_count": failed_count,
        "done_rate": round(done_count / len(tasks), 4) if tasks else None,
        "activity_count": len(activities),
        "last_activity_at": max(last_candidates) if last_candidates else None,
    }
