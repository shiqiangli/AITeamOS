"""
Validation Context — PostgreSQL Repository 实现。

PostgresHarnessAdapterRepository: HarnessAdapter 配置型聚合根仓储
PostgresHarnessInvocationRepository: HarnessInvocation 运行时聚合根仓储
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from aiteamos_shared.repository import BaseRepository, DatabasePool
from aiteamos_shared.types import new_id

from ..domain.models import (
    AdapterHealth,
    HarnessAdapterAggregate,
    HarnessInvocation,
    HarnessTier,
    InvocationState,
    ProtocolKind,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HarnessAdapter Repository
# ---------------------------------------------------------------------------


class PostgresHarnessAdapterRepository(BaseRepository[HarnessAdapterAggregate]):
    """HarnessAdapter 配置型聚合根的 PostgreSQL 仓储实现。"""

    UPSERT_ADAPTER = """
        INSERT INTO harness_adapter (
            id, tier, protocol, endpoint, auth_secret_ref,
            callback_secret_ref, health, project_bindings, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
        ON CONFLICT (id) DO UPDATE SET
            tier = EXCLUDED.tier,
            protocol = EXCLUDED.protocol,
            endpoint = EXCLUDED.endpoint,
            auth_secret_ref = EXCLUDED.auth_secret_ref,
            callback_secret_ref = EXCLUDED.callback_secret_ref,
            health = EXCLUDED.health,
            project_bindings = EXCLUDED.project_bindings
    """

    SELECT_ADAPTER = """
        SELECT * FROM harness_adapter WHERE id = $1
    """

    SELECT_ALL_ADAPTERS = """
        SELECT * FROM harness_adapter ORDER BY id
    """

    SELECT_ADAPTERS_BY_PROJECT_AND_TIER = """
        SELECT * FROM harness_adapter
        WHERE tier = $1
          AND (
              $2 = ANY(project_bindings)
              OR array_length(project_bindings, 1) IS NULL
              OR project_bindings = '{}'
          )
        ORDER BY array_length(project_bindings, 1) DESC NULLS LAST
    """

    DELETE_ADAPTER = """
        DELETE FROM harness_adapter WHERE id = $1
    """

    async def get_by_id(self, id: Any, *, tx: Any = None) -> HarnessAdapterAggregate | None:
        executor = tx if tx else self._db
        row = await executor.fetchrow(self.SELECT_ADAPTER, id)
        if row is None:
            return None
        return self._row_to_adapter(row)

    async def save(self, aggregate: HarnessAdapterAggregate, *, tx: Any = None) -> None:
        executor = tx if tx else self._db
        await executor.execute(
            self.UPSERT_ADAPTER,
            aggregate.id,
            aggregate.tier.value,
            aggregate.protocol.value,
            aggregate.endpoint,
            aggregate.auth_secret_ref,
            aggregate.callback_secret_ref,
            json.dumps({
                "ready": aggregate.health.ready,
                "success_rate_24h": aggregate.health.success_rate_24h,
                "diagnostics": aggregate.health.diagnostics,
            }),
            aggregate.project_bindings,
            aggregate.created_at,
        )

    async def delete(self, adapter_id: str, *, tx: Any = None) -> None:
        executor = tx if tx else self._db
        await executor.execute(self.DELETE_ADAPTER, adapter_id)

    async def find_by_project_and_tier(
        self, project_id: UUID, tier: HarnessTier, *, tx: Any = None
    ) -> list[HarnessAdapterAggregate]:
        executor = tx if tx else self._db
        rows = await executor.fetch(
            self.SELECT_ADAPTERS_BY_PROJECT_AND_TIER,
            tier.value,
            project_id,
        )
        return [self._row_to_adapter(r) for r in rows]

    async def list_all(self, *, tx: Any = None) -> list[HarnessAdapterAggregate]:
        executor = tx if tx else self._db
        rows = await executor.fetch(self.SELECT_ALL_ADAPTERS)
        return [self._row_to_adapter(r) for r in rows]

    @staticmethod
    def _row_to_adapter(row: Any) -> HarnessAdapterAggregate:
        health_data = row.get("health", {}) if hasattr(row, "get") else {}
        if isinstance(health_data, str):
            health_data = json.loads(health_data)

        return HarnessAdapterAggregate(
            id=row["id"],
            tier=HarnessTier(row["tier"]),
            protocol=ProtocolKind(row["protocol"]),
            endpoint=row["endpoint"],
            auth_secret_ref=row["auth_secret_ref"],
            callback_secret_ref=row.get("callback_secret_ref", "") or "",
            health=AdapterHealth(
                ready=health_data.get("ready", True),
                success_rate_24h=health_data.get("success_rate_24h", 1.0),
                diagnostics=health_data.get("diagnostics", {}),
            ),
            project_bindings=list(row.get("project_bindings", []) or []),
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# HarnessInvocation Repository
# ---------------------------------------------------------------------------


class PostgresHarnessInvocationRepository(BaseRepository[HarnessInvocation]):
    """HarnessInvocation 运行时聚合根的 PostgreSQL 仓储实现。"""

    UPSERT_INVOCATION = """
        INSERT INTO harness_invocation (
            id, adapter_id, run_id, deliverable_ref, callback_token,
            state, triggered_at, completed_at, expire_at,
            result, flaky_signal, archived_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::jsonb, $12)
        ON CONFLICT (id) DO UPDATE SET
            state = EXCLUDED.state,
            completed_at = EXCLUDED.completed_at,
            result = EXCLUDED.result,
            flaky_signal = EXCLUDED.flaky_signal,
            archived_at = EXCLUDED.archived_at
    """

    SELECT_INVOCATION = """
        SELECT * FROM harness_invocation WHERE id = $1
    """

    SELECT_INVOCATION_FOR_UPDATE = """
        SELECT * FROM harness_invocation WHERE id = $1 FOR UPDATE
    """

    SELECT_BY_CALLBACK_TOKEN = """
        SELECT * FROM harness_invocation WHERE callback_token = $1
    """

    SELECT_PENDING_EXPIRED = """
        SELECT * FROM harness_invocation
        WHERE state = 'pending' AND expire_at < now()
        ORDER BY expire_at
        LIMIT 500
    """

    SELECT_BY_RUN_ID = """
        SELECT * FROM harness_invocation WHERE run_id = $1 ORDER BY triggered_at
    """

    async def get_by_id(self, id: Any, *, tx: Any = None) -> HarnessInvocation | None:
        executor = tx if tx else self._db
        row = await executor.fetchrow(self.SELECT_INVOCATION, id)
        if row is None:
            return None
        return self._row_to_invocation(row)

    async def lock_for_update(self, invocation_id: UUID, *, tx: Any = None) -> HarnessInvocation | None:
        executor = tx if tx else self._db
        row = await executor.fetchrow(self.SELECT_INVOCATION_FOR_UPDATE, invocation_id)
        if row is None:
            return None
        return self._row_to_invocation(row)

    async def save(self, aggregate: HarnessInvocation, *, tx: Any = None) -> None:
        executor = tx if tx else self._db
        import json as _json
        await executor.execute(
            self.UPSERT_INVOCATION,
            aggregate.id,
            aggregate.adapter_id,
            aggregate.run_id,
            aggregate.deliverable_ref,
            aggregate.callback_token,
            aggregate.state.value,
            aggregate.triggered_at,
            aggregate.completed_at,
            aggregate.expire_at,
            _json.dumps(aggregate.result) if aggregate.result else None,
            _json.dumps(aggregate.flaky_signal) if aggregate.flaky_signal else None,
            aggregate.archived_at,
        )

    async def get_by_callback_token(
        self, token: str, *, tx: Any = None
    ) -> HarnessInvocation | None:
        executor = tx if tx else self._db
        row = await executor.fetchrow(self.SELECT_BY_CALLBACK_TOKEN, token)
        if row is None:
            return None
        return self._row_to_invocation(row)

    async def find_pending_expired(self, *, tx: Any = None) -> list[HarnessInvocation]:
        executor = tx if tx else self._db
        rows = await executor.fetch(self.SELECT_PENDING_EXPIRED)
        return [self._row_to_invocation(r) for r in rows]

    async def get_by_run_id(
        self, run_id: UUID, *, tx: Any = None
    ) -> list[HarnessInvocation]:
        executor = tx if tx else self._db
        rows = await executor.fetch(self.SELECT_BY_RUN_ID, run_id)
        return [self._row_to_invocation(r) for r in rows]

    @staticmethod
    def _row_to_invocation(row: Any) -> HarnessInvocation:
        return HarnessInvocation(
            id=row["id"],
            adapter_id=row["adapter_id"],
            run_id=row["run_id"],
            deliverable_ref=row["deliverable_ref"],
            callback_token=row["callback_token"],
            state=InvocationState(row["state"]),
            triggered_at=row["triggered_at"],
            completed_at=row.get("completed_at"),
            expire_at=row["expire_at"],
            result=row.get("result"),
            flaky_signal=row.get("flaky_signal"),
            archived_at=row.get("archived_at"),
        )
