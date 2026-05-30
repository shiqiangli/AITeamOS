"""
Capability Context — PostgreSQL Repository 实现。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from aiteamos_shared.repository import BaseRepository, DatabasePool
from aiteamos_shared.types import SemVer

from ..domain.models import (
    CircuitState,
    CostEstimate,
    MutationKind,
    SideEffect,
    Skill,
    SkillHealth,
    SkillManifest,
    SkillStatus,
)
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
            id, name, version_major, version_minor, version_patch,
            manifest, status, circuit_state, description, domain, inputs,
            outputs, preconditions, side_effects, required_permissions,
            capability_tags, examples, reference_links, quality_signals, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11::jsonb,
            $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb,
            $17::jsonb, $18::jsonb, $19::jsonb, $20
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            version_major = EXCLUDED.version_major,
            version_minor = EXCLUDED.version_minor,
            version_patch = EXCLUDED.version_patch,
            manifest = EXCLUDED.manifest,
            status = EXCLUDED.status,
            circuit_state = EXCLUDED.circuit_state,
            description = EXCLUDED.description,
            domain = EXCLUDED.domain,
            inputs = EXCLUDED.inputs,
            outputs = EXCLUDED.outputs,
            preconditions = EXCLUDED.preconditions,
            side_effects = EXCLUDED.side_effects,
            required_permissions = EXCLUDED.required_permissions,
            capability_tags = EXCLUDED.capability_tags,
            examples = EXCLUDED.examples,
            reference_links = EXCLUDED.reference_links,
            quality_signals = EXCLUDED.quality_signals
    """

    SELECT_SKILL = """SELECT * FROM skill WHERE id = $1"""
    SELECT_SKILL_FOR_UPDATE = """SELECT * FROM skill WHERE id = $1 FOR UPDATE"""

    LIST_SKILLS = """
        SELECT id, name, version_major, version_minor, version_patch,
               description, domain, status, circuit_state, capability_tags, created_at
        FROM skill
        WHERE ($1::text IS NULL OR status = $1)
          AND ($2::text IS NULL OR name ILIKE '%' || $2 || '%')
        ORDER BY created_at DESC
        OFFSET $3 LIMIT $4
    """

    SEARCH_BY_TAG = """
        SELECT id, name, version_major, version_minor, version_patch,
               description, domain, status, circuit_state, capability_tags, created_at
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
        manifest_dict = aggregate.manifest.to_dict()

        await executor.execute(
            self.UPSERT_SKILL,
            aggregate.id,
            aggregate.name,
            aggregate.version.major,
            aggregate.version.minor,
            aggregate.version.patch,
            json.dumps(manifest_dict),
            aggregate.status.value,
            aggregate.health.circuit_state.value,
            aggregate.manifest.description,
            aggregate.manifest.domain,
            json.dumps(aggregate.manifest.inputs),
            json.dumps(aggregate.manifest.outputs),
            json.dumps(aggregate.manifest.preconditions),
            json.dumps(manifest_dict["side_effects"]),
            json.dumps(aggregate.manifest.required_permissions),
            json.dumps(aggregate.manifest.capability_tags),
            json.dumps(aggregate.manifest.examples),
            json.dumps(aggregate.manifest.references),
            json.dumps(aggregate.manifest.quality_signals),
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

        manifest_data = self._row_to_manifest_data(row)
        side_effects = _as_json_value(row.get("side_effects"), manifest_data.get("side_effects", []))

        return SkillDetail(
            id=row["id"],
            name=row["name"],
            version=f"{row['version_major']}.{row['version_minor']}.{row['version_patch']}",
            description=row.get("description", ""),
            domain=row.get("domain", ""),
            status=row["status"],
            circuit_state=row.get("circuit_state", "closed"),
            inputs=_as_json_value(row.get("inputs"), []),
            outputs=_as_json_value(row.get("outputs"), []),
            preconditions=_as_json_value(row.get("preconditions"), []),
            side_effects=side_effects,
            required_permissions=_as_json_value(row.get("required_permissions"), []),
            capability_tags=_as_json_value(row.get("capability_tags"), []),
            examples=_as_json_value(row.get("examples"), []),
            references=_as_json_value(row.get("reference_links"), []),
            quality_signals=_as_json_value(row.get("quality_signals"), {}),
            manifest=manifest_data,
            health={},
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
        manifest = SkillManifest.from_dict(PostgresSkillRepository._row_to_manifest_data(row))

        version = SemVer(
            major=row["version_major"],
            minor=row["version_minor"],
            patch=row["version_patch"],
        )

        health = SkillHealth(
            circuit_state=CircuitState(row.get("circuit_state", "closed")),
        )

        return Skill(
            id=row["id"],
            name=row["name"],
            version=version,
            manifest=manifest,
            status=SkillStatus(row["status"]),
            health=health,
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_summary(row: Any) -> SkillSummary:
        tags = _as_json_value(row.get("capability_tags"), [])

        return SkillSummary(
            id=row["id"],
            name=row["name"],
            version=f"{row['version_major']}.{row['version_minor']}.{row['version_patch']}",
            description=row.get("description", ""),
            domain=row.get("domain", ""),
            status=row["status"],
            circuit_state=row.get("circuit_state", "closed"),
            capability_tags=tags,
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_manifest_data(row: Any) -> dict[str, Any]:
        manifest_data = _as_json_value(row["manifest"], {})
        if not isinstance(manifest_data, dict):
            manifest_data = {}
        manifest_data.update({
            "name": row["name"],
            "version": f"{row['version_major']}.{row['version_minor']}.{row['version_patch']}",
            "description": row.get("description", manifest_data.get("description", "")),
            "domain": row.get("domain", manifest_data.get("domain", "")),
            "inputs": _as_json_value(row.get("inputs"), manifest_data.get("inputs", [])),
            "outputs": _as_json_value(row.get("outputs"), manifest_data.get("outputs", [])),
            "preconditions": _as_json_value(row.get("preconditions"), manifest_data.get("preconditions", [])),
            "side_effects": _as_json_value(row.get("side_effects"), manifest_data.get("side_effects", [])),
            "required_permissions": _as_json_value(row.get("required_permissions"), manifest_data.get("required_permissions", [])),
            "capability_tags": _as_json_value(row.get("capability_tags"), manifest_data.get("capability_tags", [])),
            "examples": _as_json_value(row.get("examples"), manifest_data.get("examples", [])),
            "references": _as_json_value(row.get("reference_links"), manifest_data.get("references", [])),
            "quality_signals": _as_json_value(row.get("quality_signals"), manifest_data.get("quality_signals", {})),
        })
        return manifest_data
