"""
Knowledge Context — Memory 健康度指标 (plan.md §4.4.1)。

MemoryHealthService: 计算 Memory 库健康度指标。

指标:
- 新鲜度: 30 天内新增/更新占比
- 活跃率: 被召回过的占总量比例
- 失效占比: deprecated/needs_verify 占比
- 冲突数: 未解决冲突对数
- 层级分布: Facts/Patterns/Principles 比例
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryHealthMetrics:
    """Memory 库健康度指标。"""

    total_count: int = 0
    freshness_rate: float = 0.0  # 30 天内新增/更新占比
    active_rate: float = 0.0  # 被召回过的占比
    stale_rate: float = 0.0  # deprecated/needs_verify 占比
    unresolved_conflicts: int = 0
    tier_distribution: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class BulkOperationResult:
    """批量操作结果。"""

    affected_count: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExportPayload:
    """导出数据包。"""

    version: str = "1.0"
    exported_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    memories: list[dict[str, Any]] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    members: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ImportResult:
    """导入结果。"""

    imported_count: int = 0
    skipped_duplicates: int = 0
    conflicts_detected: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class HealthDataRepoLike(Protocol):
    """健康度计算所需的仓储接口。"""

    async def count_total(self, *, tx: Any = None) -> int: ...

    async def count_updated_since(
        self, since: datetime, *, tx: Any = None
    ) -> int: ...

    async def count_by_lifecycle(
        self, state: str, *, tx: Any = None
    ) -> int: ...

    async def count_recalled(self, *, tx: Any = None) -> int:
        """统计被召回过的 Memory 数量。"""
        ...

    async def count_by_tier(self, *, tx: Any = None) -> dict[str, int]: ...


class ConflictCountProvider(Protocol):
    async def count_unresolved(self) -> int: ...


class BulkMemoryRepoLike(Protocol):
    """批量操作所需的仓储接口。"""

    async def find_ids_by_criteria(
        self,
        *,
        lifecycle_state: str | None = None,
        not_used_since: datetime | None = None,
        tier: str | None = None,
        tx: Any = None,
    ) -> list[UUID]: ...

    async def bulk_update_lifecycle(
        self,
        memory_ids: list[UUID],
        new_state: str,
        reason: str,
        *,
        tx: Any = None,
    ) -> int: ...


class ExportRepoLike(Protocol):
    async def export_all_memories(self, *, tx: Any = None) -> list[dict[str, Any]]: ...
    async def export_all_skills(self, *, tx: Any = None) -> list[dict[str, Any]]: ...
    async def export_all_members(self, *, tx: Any = None) -> list[dict[str, Any]]: ...


class ImportRepoLike(Protocol):
    async def memory_exists(self, title: str, *, tx: Any = None) -> bool: ...
    async def import_memory(self, data: dict[str, Any], *, tx: Any = None) -> None: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


# ---------------------------------------------------------------------------
# MemoryHealthService (plan.md §4.4.1)
# ---------------------------------------------------------------------------

FRESHNESS_WINDOW_DAYS = 30


class MemoryHealthService:
    """Memory 库健康度计算。"""

    def __init__(
        self,
        *,
        health_repo: HealthDataRepoLike,
        conflict_provider: ConflictCountProvider,
    ):
        self._repo = health_repo
        self._conflicts = conflict_provider

    async def compute_metrics(
        self, *, now: datetime | None = None
    ) -> MemoryHealthMetrics:
        """计算健康度指标。"""
        current_time = now or datetime.now(timezone.utc)
        since = current_time - timedelta(days=FRESHNESS_WINDOW_DAYS)

        total = await self._repo.count_total()

        if total == 0:
            return MemoryHealthMetrics()

        recent = await self._repo.count_updated_since(since)
        recalled = await self._repo.count_recalled()
        deprecated = await self._repo.count_by_lifecycle("deprecated")
        needs_verify = await self._repo.count_by_lifecycle("needs_verify")
        tier_dist = await self._repo.count_by_tier()
        conflicts = await self._conflicts.count_unresolved()

        stale_count = deprecated + needs_verify

        return MemoryHealthMetrics(
            total_count=total,
            freshness_rate=round(recent / total, 4) if total > 0 else 0.0,
            active_rate=round(recalled / total, 4) if total > 0 else 0.0,
            stale_rate=round(stale_count / total, 4) if total > 0 else 0.0,
            unresolved_conflicts=conflicts,
            tier_distribution=tier_dist,
        )


# ---------------------------------------------------------------------------
# BulkGovernanceService (plan.md §4.4.2)
# ---------------------------------------------------------------------------

# 默认 GC 阈值: 未使用超过 90 天
DEFAULT_GC_UNUSED_DAYS = 90


class BulkGovernanceService:
    """批量治理操作。"""

    def __init__(
        self,
        *,
        bulk_repo: BulkMemoryRepoLike,
        tx_manager: TransactionManagerLike,
    ):
        self._repo = bulk_repo
        self._tx = tx_manager

    async def bulk_deprecate(
        self,
        *,
        tier: str | None = None,
        lifecycle_state: str | None = None,
        reason: str = "bulk_deprecation",
    ) -> BulkOperationResult:
        """批量废弃匹配的 Memory。"""
        async with self._tx.transaction() as tx:
            ids = await self._repo.find_ids_by_criteria(
                lifecycle_state=lifecycle_state, tier=tier, tx=tx,
            )
            if not ids:
                return BulkOperationResult()

            affected = await self._repo.bulk_update_lifecycle(
                ids, "deprecated", reason, tx=tx,
            )

        return BulkOperationResult(affected_count=affected)

    async def bulk_verify(
        self,
        *,
        lifecycle_state: str = "needs_verify",
        reason: str = "bulk_verification",
    ) -> BulkOperationResult:
        """批量重新验证 (将 needs_verify 标记为 active)。"""
        async with self._tx.transaction() as tx:
            ids = await self._repo.find_ids_by_criteria(
                lifecycle_state=lifecycle_state, tx=tx,
            )
            if not ids:
                return BulkOperationResult()

            affected = await self._repo.bulk_update_lifecycle(
                ids, "active", reason, tx=tx,
            )

        return BulkOperationResult(affected_count=affected)

    async def gc_unused(
        self,
        *,
        unused_days: int = DEFAULT_GC_UNUSED_DAYS,
        now: datetime | None = None,
    ) -> BulkOperationResult:
        """定时 GC: 未使用超过配置天数的候选自动废弃。"""
        current_time = now or datetime.now(timezone.utc)
        cutoff = current_time - timedelta(days=unused_days)

        async with self._tx.transaction() as tx:
            ids = await self._repo.find_ids_by_criteria(
                not_used_since=cutoff, tx=tx,
            )
            if not ids:
                return BulkOperationResult()

            affected = await self._repo.bulk_update_lifecycle(
                ids, "deprecated", "gc_unused_threshold", tx=tx,
            )

        logger.info("GC: deprecated %d unused memories (> %d days)", affected, unused_days)
        return BulkOperationResult(affected_count=affected)


# ---------------------------------------------------------------------------
# ExportImportService (plan.md §4.4.3)
# ---------------------------------------------------------------------------


class ExportImportService:
    """数据导出/导入。"""

    def __init__(
        self,
        *,
        export_repo: ExportRepoLike,
        import_repo: ImportRepoLike,
        tx_manager: TransactionManagerLike,
    ):
        self._export_repo = export_repo
        self._import_repo = import_repo
        self._tx = tx_manager

    async def export_all(self) -> ExportPayload:
        """导出所有数据 (JSON 格式)。"""
        async with self._tx.transaction() as tx:
            memories = await self._export_repo.export_all_memories(tx=tx)
            skills = await self._export_repo.export_all_skills(tx=tx)
            members = await self._export_repo.export_all_members(tx=tx)

        return ExportPayload(
            memories=memories,
            skills=skills,
            members=members,
        )

    async def import_memories(
        self,
        memories: list[dict[str, Any]],
    ) -> ImportResult:
        """导入 Memory (自动去重)。"""
        imported = 0
        skipped = 0
        errors: list[str] = []

        async with self._tx.transaction() as tx:
            for mem_data in memories:
                title = mem_data.get("title", "")
                if not title:
                    errors.append("Memory without title skipped")
                    continue

                exists = await self._import_repo.memory_exists(title, tx=tx)
                if exists:
                    skipped += 1
                    continue

                try:
                    await self._import_repo.import_memory(mem_data, tx=tx)
                    imported += 1
                except Exception as e:
                    errors.append(f"Import error for '{title}': {e}")

        return ImportResult(
            imported_count=imported,
            skipped_duplicates=skipped,
            errors=errors,
        )
