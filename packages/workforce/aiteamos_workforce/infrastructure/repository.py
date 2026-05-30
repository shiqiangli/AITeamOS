"""
Workforce Context — PostgreSQL Repository 实现。
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from aiteamos_shared.repository import BaseRepository, DatabasePool
from aiteamos_shared.types import MemberKind, new_id

from ..domain.models import (
    Department,
    Member,
    MemberHealthMetrics,
    MemberProfile,
    Project,
    ProjectStatus,
    TimeoutMode,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Department Repository
# ---------------------------------------------------------------------------


class PostgresDepartmentRepository(BaseRepository[Department]):
    UPSERT = """
        INSERT INTO department (id, name, leader_member_id, backup_leader_member_id, created_at)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            leader_member_id = EXCLUDED.leader_member_id,
            backup_leader_member_id = EXCLUDED.backup_leader_member_id
    """
    SELECT = "SELECT * FROM department WHERE id = $1"
    SELECT_FOR_UPDATE = "SELECT * FROM department WHERE id = $1 FOR UPDATE"
    LIST = """
        SELECT id, name, leader_member_id, created_at
        FROM department
        ORDER BY created_at DESC
        OFFSET $1 LIMIT $2
    """

    async def get_by_id(self, id: Any, *, tx: Any = None) -> Department | None:
        executor = tx if tx else self._db
        row = await executor.fetchrow(self.SELECT, id)
        return self._row_to_dept(row) if row else None

    async def lock_for_update(self, id: Any, *, tx: Any) -> Department | None:
        row = await tx.fetchrow(self.SELECT_FOR_UPDATE, id)
        return self._row_to_dept(row) if row else None

    async def save(self, aggregate: Department, *, tx: Any = None) -> None:
        executor = tx if tx else self._db
        await executor.execute(
            self.UPSERT, aggregate.id, aggregate.name,
            aggregate.leader_member_id, aggregate.backup_leader_member_id, aggregate.created_at,
        )

    async def list_departments(
        self, *, offset: int = 0, limit: int = 50,
    ) -> list:
        from ..application.queries import DepartmentSummary
        rows = await self._db.fetch(self.LIST, offset, limit)
        return [
            DepartmentSummary(
                id=row["id"], name=row["name"],
                leader_member_id=str(row["leader_member_id"]) if row.get("leader_member_id") else None,
                created_at=row["created_at"],
            )
            for row in rows
        ]

    @staticmethod
    def _row_to_dept(row: Any) -> Department:
        return Department(
            id=row["id"], name=row["name"],
            leader_member_id=row.get("leader_member_id"),
            backup_leader_member_id=row.get("backup_leader_member_id"),
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# Member Repository
# ---------------------------------------------------------------------------


class PostgresMemberRepository(BaseRepository[Member]):
    UPSERT = """
        INSERT INTO member (id, kind, department_id, profile, display_name, concurrency_limit, health, created_at, archived_at)
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7::jsonb, $8, $9)
        ON CONFLICT (id) DO UPDATE SET
            kind = EXCLUDED.kind, department_id = EXCLUDED.department_id,
            profile = EXCLUDED.profile, display_name = EXCLUDED.display_name,
            concurrency_limit = EXCLUDED.concurrency_limit,
            health = EXCLUDED.health, archived_at = EXCLUDED.archived_at
    """
    SELECT = "SELECT * FROM member WHERE id = $1"
    SELECT_FOR_UPDATE = "SELECT * FROM member WHERE id = $1 FOR UPDATE"
    LIST = """
        SELECT id, kind, department_id, profile, concurrency_limit, created_at, archived_at
        FROM member
        WHERE ($1::text IS NULL OR department_id::text = $1)
          AND ($2::text IS NULL OR kind = $2)
        ORDER BY created_at DESC
        OFFSET $3 LIMIT $4
    """
    SELECT_SKILLS = "SELECT skill_id FROM member_skill_assignment WHERE member_id = $1 ORDER BY assigned_at"
    SELECT_MEMORIES = "SELECT memory_id FROM member_memory_assignment WHERE member_id = $1 ORDER BY assigned_at"
    INSERT_SKILL = """
        INSERT INTO member_skill_assignment (member_id, skill_id, is_base)
        VALUES ($1, $2, TRUE)
        ON CONFLICT (member_id, skill_id) DO UPDATE SET is_base = TRUE
    """
    INSERT_MEMORY = """
        INSERT INTO member_memory_assignment (member_id, memory_id)
        VALUES ($1, $2)
        ON CONFLICT (member_id, memory_id) DO NOTHING
    """

    async def get_by_id(self, id: Any, *, tx: Any = None) -> Member | None:
        executor = tx if tx else self._db
        row = await executor.fetchrow(self.SELECT, id)
        if row is None:
            return None
        skill_rows = await executor.fetch(self.SELECT_SKILLS, id)
        memory_rows = await executor.fetch(self.SELECT_MEMORIES, id)
        return self._row_to_member(row, skill_rows=skill_rows, memory_rows=memory_rows)

    async def lock_for_update(self, id: Any, *, tx: Any) -> Member | None:
        row = await tx.fetchrow(self.SELECT_FOR_UPDATE, id)
        if row is None:
            return None
        skill_rows = await tx.fetch(self.SELECT_SKILLS, id)
        memory_rows = await tx.fetch(self.SELECT_MEMORIES, id)
        return self._row_to_member(row, skill_rows=skill_rows, memory_rows=memory_rows)

    async def save(self, aggregate: Member, *, tx: Any = None) -> None:
        executor = tx if tx else self._db
        await executor.execute(
            self.UPSERT, aggregate.id, aggregate.kind.value, aggregate.department_id,
            json.dumps(aggregate.profile.to_dict()), aggregate.profile.display_name,
            aggregate.concurrency_limit, json.dumps(aggregate.health.to_dict()),
            aggregate.created_at, aggregate.archived_at,
        )
        for skill_id in aggregate.base_skill_set:
            await executor.execute(self.INSERT_SKILL, aggregate.id, skill_id)
        for memory_id in aggregate.assigned_memories:
            await executor.execute(self.INSERT_MEMORY, aggregate.id, memory_id)

    async def list_members(
        self, *, department_id: str | None = None, kind: str | None = None,
        offset: int = 0, limit: int = 50,
    ) -> list:
        from ..application.queries import MemberSummary
        rows = await self._db.fetch(self.LIST, department_id, kind, offset, limit)
        results = []
        for row in rows:
            profile_data = row["profile"]
            if isinstance(profile_data, str):
                profile_data = json.loads(profile_data)
            display_name = (profile_data or {}).get("display_name", str(row["id"])[:8])
            results.append(MemberSummary(
                id=row["id"], kind=row["kind"], display_name=display_name,
                department_id=str(row["department_id"]),
                concurrency_limit=row["concurrency_limit"],
                is_archived=row.get("archived_at") is not None,
                created_at=row["created_at"],
            ))
        return results

    @staticmethod
    def _row_to_member(
        row: Any,
        *,
        skill_rows: list[Any] | None = None,
        memory_rows: list[Any] | None = None,
    ) -> Member:
        profile_data = row["profile"]
        if isinstance(profile_data, str):
            profile_data = json.loads(profile_data)
        health_data = row.get("health", {})
        if isinstance(health_data, str):
            health_data = json.loads(health_data)
        base_skill_set = [r["skill_id"] for r in (skill_rows or [])]
        assigned_memories = [r["memory_id"] for r in (memory_rows or [])]
        return Member(
            id=row["id"], kind=MemberKind(row["kind"]), department_id=row["department_id"],
            profile=MemberProfile.from_dict(profile_data or {}),
            base_skill_set=base_skill_set,
            assigned_memories=assigned_memories,
            health=MemberHealthMetrics.from_dict(health_data or {}),
            concurrency_limit=row["concurrency_limit"],
            created_at=row["created_at"], archived_at=row.get("archived_at"),
        )


# ---------------------------------------------------------------------------
# Project Repository
# ---------------------------------------------------------------------------


class PostgresProjectRepository(BaseRepository[Project]):
    UPSERT = """
        INSERT INTO project (id, name, description, department_id, repository_refs, harness_config, status, created_at, archived_at)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name, description = EXCLUDED.description,
            repository_refs = EXCLUDED.repository_refs, harness_config = EXCLUDED.harness_config,
            status = EXCLUDED.status, archived_at = EXCLUDED.archived_at
    """
    SELECT = "SELECT * FROM project WHERE id = $1"
    SELECT_FOR_UPDATE = "SELECT * FROM project WHERE id = $1 FOR UPDATE"
    LIST = """
        SELECT p.id, p.name, p.department_id, p.status, p.created_at,
               COUNT(pm.member_id) AS member_count
        FROM project p
        LEFT JOIN project_member pm ON pm.project_id = p.id
        WHERE ($1::text IS NULL OR p.department_id::text = $1)
          AND ($2::text IS NULL OR p.status = $2)
        GROUP BY p.id
        ORDER BY p.created_at DESC
        OFFSET $3 LIMIT $4
    """

    async def get_by_id(self, id: Any, *, tx: Any = None) -> Project | None:
        executor = tx if tx else self._db
        row = await executor.fetchrow(self.SELECT, id)
        return self._row_to_project(row) if row else None

    async def lock_for_update(self, id: Any, *, tx: Any) -> Project | None:
        row = await tx.fetchrow(self.SELECT_FOR_UPDATE, id)
        return self._row_to_project(row) if row else None

    async def save(self, aggregate: Project, *, tx: Any = None) -> None:
        executor = tx if tx else self._db
        await executor.execute(
            self.UPSERT, aggregate.id, aggregate.name, aggregate.description,
            aggregate.department_id, json.dumps(aggregate.repository_refs),
            json.dumps(aggregate.harness_config), aggregate.status.value,
            aggregate.created_at, aggregate.archived_at,
        )

    async def list_projects(
        self, *, department_id: str | None = None, status: str | None = None,
        offset: int = 0, limit: int = 50,
    ) -> list:
        from ..application.queries import ProjectSummary
        rows = await self._db.fetch(self.LIST, department_id, status, offset, limit)
        return [
            ProjectSummary(
                id=row["id"], name=row["name"],
                department_id=str(row["department_id"]),
                status=row["status"],
                member_count=row["member_count"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    @staticmethod
    def _row_to_project(row: Any) -> Project:
        repo_refs = row.get("repository_refs", [])
        if isinstance(repo_refs, str):
            repo_refs = json.loads(repo_refs)
        harness_cfg = row.get("harness_config", {})
        if isinstance(harness_cfg, str):
            harness_cfg = json.loads(harness_cfg)
        return Project(
            id=row["id"], name=row["name"], description=row.get("description", ""),
            department_id=row["department_id"], repository_refs=repo_refs or [],
            harness_config=harness_cfg or {}, status=ProjectStatus(row["status"]),
            created_at=row["created_at"], archived_at=row.get("archived_at"),
        )
