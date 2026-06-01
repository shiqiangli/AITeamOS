"""
Capability Context — PostgreSQL Repository 实现。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from aiteamos_shared.repository import BaseRepository, DatabasePool
from aiteamos_shared.types import SemVer

from ..domain.models import Skill, SkillStatus
from ..application.queries import SkillDetail, SkillSummary

logger = logging.getLogger(__name__)


def _as_json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


class PostgresSkillRepository(BaseRepository[Skill]):
    """Skill 聚合根的 PostgreSQL 仓储实现。"""

    UPSERT_SKILL = """
        INSERT INTO skill (
            id, name, version, description, domain, status,
            capability_tags, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7::jsonb, $8
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            version = EXCLUDED.version,
            description = EXCLUDED.description,
            domain = EXCLUDED.domain,
            status = EXCLUDED.status,
            capability_tags = EXCLUDED.capability_tags
    """

    SELECT_SKILL = """SELECT * FROM skill WHERE id = $1"""
    SELECT_SKILL_FOR_UPDATE = """SELECT * FROM skill WHERE id = $1 FOR UPDATE"""

    LIST_SKILLS = """
        SELECT id, name, version, description, domain, status,
               capability_tags, created_at
        FROM skill
        WHERE ($1::text IS NULL OR status = $1)
          AND ($2::text IS NULL OR name ILIKE '%' || $2 || '%')
        ORDER BY created_at DESC
        OFFSET $3 LIMIT $4
    """

    SEARCH_BY_TAG = """
        SELECT id, name, version, description, domain, status,
               capability_tags, created_at
        FROM skill
        ORDER BY created_at DESC
        LIMIT $1
    """

    async def get_by_id(self, id: Any, *, tx: Any = None) -> Skill | None:
        executor = tx if tx else self._db
        row = await executor.fetchrow(self.SELECT_SKILL, id)
        if row is None:
            return None
        return self._row_to_skill(row)

    async def lock_for_update(self, id: Any, *, tx: Any) -> Skill | None:
        row = await tx.fetchrow(self.SELECT_SKILL_FOR_UPDATE, id)
        if row is None:
            return None
        return self._row_to_skill(row)

    async def save(self, aggregate: Skill, *, tx: Any = None) -> None:
        executor = tx if tx else self._db

        await executor.execute(
            self.UPSERT_SKILL,
            aggregate.id,
            aggregate.name,
            str(aggregate.version),
            aggregate.description,
            aggregate.domain,
            aggregate.status.value,
            json.dumps(aggregate.capability_tags),
            aggregate.created_at,
        )

    # -- Read-Side (CQRS) --

    async def list_skills(
        self,
        *,
        status: str | None = None,
        name_filter: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SkillSummary]:
        rows = await self._db.fetch(self.LIST_SKILLS, status, name_filter, offset, limit)
        return [self._row_to_summary(r) for r in rows]

    async def get_detail(self, skill_id: Any) -> SkillDetail | None:
        row = await self._db.fetchrow(self.SELECT_SKILL, skill_id)
        if row is None:
            return None

        return SkillDetail(
            id=row["id"],
            name=row["name"],
            version=row.get("version", "1.0.0"),
            description=row.get("description", ""),
            domain=row.get("domain", ""),
            status=row["status"],
            capability_tags=_as_json_value(row.get("capability_tags"), []),
            created_at=row["created_at"],
        )

    async def search_by_tag(
        self, *, tags: list[str], limit: int = 20
    ) -> list[SkillSummary]:
        rows = await self._db.fetch(self.SEARCH_BY_TAG, limit)
        summaries = [self._row_to_summary(r) for r in rows]

        if tags:
            tag_set = set(tags)
            summaries = [
                s for s in summaries if tag_set.intersection(set(s.capability_tags))
            ]
        return summaries

    # -- Row Mapping --

    @staticmethod
    def _row_to_skill(row: Any) -> Skill:
        version_str = row.get("version", "1.0.0")
        version = SemVer.parse(version_str)

        return Skill(
            id=row["id"],
            name=row["name"],
            version=version,
            description=row.get("description", ""),
            domain=row.get("domain", ""),
            status=SkillStatus(row["status"]),
            capability_tags=_as_json_value(row.get("capability_tags"), []),
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_summary(row: Any) -> SkillSummary:
        tags = _as_json_value(row.get("capability_tags"), [])

        return SkillSummary(
            id=row["id"],
            name=row["name"],
            version=row.get("version", "1.0.0"),
            description=row.get("description", ""),
            domain=row.get("domain", ""),
            status=row["status"],
            capability_tags=tags,
            created_at=row["created_at"],
        )
