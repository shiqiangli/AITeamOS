"""
Governance Context - PostgreSQL Repository Implementations.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4
from aiteamos_governance.domain.models import (
    ConflictCase,
    ConflictKind,
    DetectorKind,
    ResolutionKind,
    ReviewCase,
    ReviewTargetKind,
    Verdict,
)

logger = logging.getLogger(__name__)


class PostgresReviewCaseRepository:
    def __init__(self, *, db: Any):
        self._db = db

    async def save(self, case: ReviewCase, *, tx: Any = None) -> None:
        conn = tx or self._db
        await conn.execute(
            """INSERT INTO review_case (id, target_kind, target_id, reviewer_member_id,
               verdict, reason, correction, decision_at, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
               ON CONFLICT (id) DO UPDATE SET
               verdict=EXCLUDED.verdict,
               reason=EXCLUDED.reason, correction=EXCLUDED.correction,
               decision_at=EXCLUDED.decision_at""",
            case.id,
            case.target_kind.value if isinstance(case.target_kind, ReviewTargetKind) else str(case.target_kind),
            case.target_id,
            case.reviewer_member_id,
            case.verdict.value if case.verdict else None,
            case.reason or "",
            case.correction or "",
            case.decision_at,
            case.created_at,
        )

    async def get_by_id(self, case_id: UUID) -> ReviewCase | None:
        row = await self._db.fetchrow("SELECT * FROM review_case WHERE id=$1", case_id)
        if not row:
            return None
        return self._from_row(row)

    async def find_pending(self, *, limit: int = 50, offset: int = 0) -> list[ReviewCase]:
        rows = await self._db.fetch(
            "SELECT * FROM review_case WHERE verdict IS NULL ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
        return [self._from_row(r) for r in rows]

    async def find_by_target(self, target_kind: str, target_id: UUID) -> list[ReviewCase]:
        rows = await self._db.fetch(
            "SELECT * FROM review_case WHERE target_kind=$1 AND target_id=$2 ORDER BY created_at DESC",
            target_kind, target_id,
        )
        return [self._from_row(r) for r in rows]

    async def count_pending(self) -> int:
        row = await self._db.fetchrow("SELECT count(*) FROM review_case WHERE verdict IS NULL")
        return row["count"] if row else 0

    @staticmethod
    def _from_row(row: Any) -> ReviewCase:
        return ReviewCase(
            id=row["id"],
            target_kind=ReviewTargetKind(row["target_kind"]),
            target_id=row["target_id"],
            reviewer_member_id=row["reviewer_member_id"],
            verdict=Verdict(row["verdict"]) if row.get("verdict") else None,
            reason=row.get("reason"),
            correction=row.get("correction"),
            decision_at=row.get("decision_at"),
            created_at=row["created_at"],
        )


class PostgresConflictCaseRepository:
    def __init__(self, *, db: Any):
        self._db = db

    async def save(self, case: ConflictCase, *, tx: Any = None) -> None:
        conn = tx or self._db
        ck = case.conflict_kind.value if isinstance(case.conflict_kind, ConflictKind) else str(case.conflict_kind)
        db_val = case.detected_by.value if isinstance(case.detected_by, DetectorKind) else str(case.detected_by)
        rs = case.resolution.value if case.resolution else None
        await conn.execute(
            """INSERT INTO conflict_case (id, memory_a_id, memory_b_id,
               conflict_kind, detected_by, resolution, winner_id,
               resolved_by, detected_at, resolved_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               ON CONFLICT (id) DO UPDATE SET
               resolution=EXCLUDED.resolution,
               winner_id=EXCLUDED.winner_id,
               resolved_by=EXCLUDED.resolved_by,
               resolved_at=EXCLUDED.resolved_at""",
            case.id,
            case.memory_a_id,
            case.memory_b_id,
            ck,
            db_val,
            rs,
            case.winner_id,
            case.resolved_by,
            case.detected_at,
            case.resolved_at,
        )

    async def get_by_id(self, case_id: UUID) -> ConflictCase | None:
        row = await self._db.fetchrow(
            "SELECT * FROM conflict_case WHERE id=$1", case_id)
        if not row:
            return None
        return self._from_row(row)

    async def find_unresolved(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[ConflictCase]:
        rows = await self._db.fetch(
            "SELECT * FROM conflict_case WHERE resolved_at IS NULL"
            " ORDER BY detected_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
        return [self._from_row(r) for r in rows]

    async def find_by_memory(self, memory_id: UUID) -> list[ConflictCase]:
        rows = await self._db.fetch(
            "SELECT * FROM conflict_case"
            " WHERE memory_a_id=$1 OR memory_b_id=$1"
            " ORDER BY detected_at DESC",
            memory_id,
        )
        return [self._from_row(r) for r in rows]

    async def count_unresolved(self) -> int:
        row = await self._db.fetchrow(
            "SELECT count(*) FROM conflict_case WHERE resolved_at IS NULL")
        return row["count"] if row else 0

    @staticmethod
    def _from_row(row: Any) -> ConflictCase:
        return ConflictCase(
            id=row["id"],
            memory_a_id=row["memory_a_id"],
            memory_b_id=row["memory_b_id"],
            conflict_kind=ConflictKind(row["conflict_kind"]),
            detected_by=DetectorKind(row["detected_by"]),
            resolution=ResolutionKind(row["resolution"]) if row.get("resolution") else None,
            winner_id=row.get("winner_id"),
            resolved_by=row.get("resolved_by"),
            detected_at=row["detected_at"],
            resolved_at=row.get("resolved_at"),
        )
