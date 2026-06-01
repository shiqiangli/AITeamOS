"""
API Gateway — Delete Routes with Forward-Reference Protection.

Forward-reference rules (positive references block deletion):
- Department: block if members or projects exist in it
- Project: block if tasks reference it via task_project
- Member: block if tasks assigned to it
- Skill: block if assigned to members
- Memory: block if assigned to members
- Task: always allowed (leaf entity)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..middleware.auth import AuthContext, get_current_user
from ..middleware.error_handler import ConflictError, NotFoundError

router = APIRouter(tags=["delete"])

_db: Any = None


def init_routes(*, db: Any) -> None:
    global _db
    _db = db


async def _count(query: str, *args: Any) -> int:
    """Execute a COUNT query and return the integer result."""
    row = await _db.fetchrow(query, *args)
    return row["count"] if row else 0


@router.delete("/api/v1/memories/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    user: AuthContext = Depends(get_current_user),
) -> None:
    if _db is None:
        raise RuntimeError("Service not initialized")
    ref = await _count(
        "SELECT count(*) AS count FROM member_memory_assignment WHERE memory_id = $1",
        memory_id,
    )
    if ref > 0:
        raise ConflictError(
            detail=f"Cannot delete: memory is assigned to {ref} member(s). Remove assignments first.",
        )
    await _db.execute(
        "DELETE FROM memory_edge WHERE source_id = $1 OR target_id = $1", memory_id,
    )
    await _db.execute("DELETE FROM memory_version WHERE memory_id = $1", memory_id)
    result = await _db.execute("DELETE FROM memory_node WHERE id = $1", memory_id)
    if result == "DELETE 0":
        raise NotFoundError(detail="Memory not found")


@router.delete("/api/v1/skills/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str,
    user: AuthContext = Depends(get_current_user),
) -> None:
    if _db is None:
        raise RuntimeError("Service not initialized")
    ref = await _count(
        "SELECT count(*) AS count FROM member_skill_assignment WHERE skill_id = $1",
        skill_id,
    )
    if ref > 0:
        raise ConflictError(
            detail=f"Cannot delete: skill is assigned to {ref} member(s). Remove assignments first.",
        )
    result = await _db.execute("DELETE FROM skill WHERE id = $1", skill_id)
    if result == "DELETE 0":
        raise NotFoundError(detail="Skill not found")


@router.delete("/api/v1/members/{member_id}", status_code=204)
async def delete_member(
    member_id: str,
    user: AuthContext = Depends(get_current_user),
) -> None:
    if _db is None:
        raise RuntimeError("Service not initialized")
    ref = await _count(
        "SELECT count(*) AS count FROM job WHERE member_id = $1",
        member_id,
    )
    if ref > 0:
        raise ConflictError(
            detail=f"Cannot delete: member has {ref} active job(s). Cancel jobs first.",
        )
    await _db.execute(
        "DELETE FROM member_skill_assignment WHERE member_id = $1", member_id,
    )
    await _db.execute(
        "DELETE FROM member_memory_assignment WHERE member_id = $1", member_id,
    )
    await _db.execute(
        "DELETE FROM project_member WHERE member_id = $1", member_id,
    )
    result = await _db.execute("DELETE FROM member WHERE id = $1", member_id)
    if result == "DELETE 0":
        raise NotFoundError(detail="Member not found")


@router.delete("/api/v1/departments/{department_id}", status_code=204)
async def delete_department(
    department_id: str,
    user: AuthContext = Depends(get_current_user),
) -> None:
    if _db is None:
        raise RuntimeError("Service not initialized")
    members = await _count(
        "SELECT count(*) AS count FROM member WHERE department_id = $1",
        department_id,
    )
    if members > 0:
        raise ConflictError(
            detail=f"Cannot delete: department has {members} member(s). Remove or reassign members first.",
        )
    projects = await _count(
        "SELECT count(*) AS count FROM project WHERE department_id = $1",
        department_id,
    )
    if projects > 0:
        raise ConflictError(
            detail=f"Cannot delete: department has {projects} project(s). Remove or reassign projects first.",
        )
    result = await _db.execute(
        "DELETE FROM department WHERE id = $1", department_id,
    )
    if result == "DELETE 0":
        raise NotFoundError(detail="Department not found")


@router.delete("/api/v1/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    user: AuthContext = Depends(get_current_user),
) -> None:
    if _db is None:
        raise RuntimeError("Service not initialized")
    await _db.execute(
        "DELETE FROM project_member WHERE project_id = $1", project_id,
    )
    result = await _db.execute("DELETE FROM project WHERE id = $1", project_id)
    if result == "DELETE 0":
        raise NotFoundError(detail="Project not found")


@router.delete("/api/v1/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    user: AuthContext = Depends(get_current_user),
) -> None:
    if _db is None:
        raise RuntimeError("Service not initialized")
    await _db.execute("DELETE FROM task_run WHERE task_id = $1", task_id)
    result = await _db.execute("DELETE FROM task WHERE id = $1", task_id)
    if result == "DELETE 0":
        raise NotFoundError(detail="Task not found")
