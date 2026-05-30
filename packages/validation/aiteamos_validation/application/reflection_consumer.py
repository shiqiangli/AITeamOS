"""
Validation Context — Reflection Projection Consumer (arch.md §2.2.5).

消费 Harness 调用事件，维护 harness_invocation 读侧投影，
驱动 Flaky 检测 → Reflection Quarantine 流水线。
"""

from __future__ import annotations

import logging
from typing import Any

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer

logger = logging.getLogger(__name__)


class ReflectionConsumer(IdempotentProjectionConsumer):
    """消费 Validation 上下文事件，维护 harness_invocation 投影。

    处理事件:
    - validation.harness_invocation.triggered  → INSERT row (state=pending)
    - validation.harness_invocation.completed  → UPDATE state + result
    - validation.harness_invocation.expired    → UPDATE state=expired
    - validation.harness_adapter.registered    → INSERT adapter row
    - validation.harness_adapter.health_changed → UPDATE adapter health
    """

    consumer_id = "reflection-v1"

    _UPSERT_INVOCATION = """
        INSERT INTO harness_invocation (
            id, adapter_id, run_id, state, callback_token, triggered_at
        ) VALUES ($1, $2, $3, 'pending', $4, now())
        ON CONFLICT (id) DO NOTHING
    """

    _COMPLETE_INVOCATION = """
        UPDATE harness_invocation
        SET state = $2, result = $3::jsonb, completed_at = now()
        WHERE id = $1
    """

    _EXPIRE_INVOCATION = """
        UPDATE harness_invocation
        SET state = 'expired', completed_at = now()
        WHERE id = $1
    """

    _UPSERT_ADAPTER = """
        INSERT INTO harness_adapter (id, tier, protocol, endpoint, created_at)
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (id) DO UPDATE SET
            tier = EXCLUDED.tier, protocol = EXCLUDED.protocol, endpoint = EXCLUDED.endpoint
    """

    _UPDATE_ADAPTER_HEALTH = """
        UPDATE harness_adapter
        SET health = jsonb_build_object('ready', $2::boolean, 'success_rate_24h', $3::float)
        WHERE id = $1
    """

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        data = event.model_dump()
        et = event.event_type

        if et == "validation.harness_invocation.triggered":
            await self._db.execute(
                self._UPSERT_INVOCATION,
                data["invocation_id"],
                data["adapter_id"],
                data["run_id"],
                data.get("callback_token", ""),
            )

        elif et == "validation.harness_invocation.completed":
            import json
            outcome = data.get("outcome", "pass")
            state = "flaky" if outcome == "flaky" else "done"
            result_json = json.dumps({"outcome": outcome})
            await self._db.execute(
                self._COMPLETE_INVOCATION,
                data["invocation_id"],
                state,
                result_json,
            )
            if outcome == "flaky":
                logger.info(
                    "Reflection: invocation %s flaky → quarantine candidate",
                    data["invocation_id"],
                )

        elif et == "validation.harness_invocation.expired":
            await self._db.execute(
                self._EXPIRE_INVOCATION,
                data["invocation_id"],
            )

        elif et == "validation.harness_adapter.registered":
            await self._db.execute(
                self._UPSERT_ADAPTER,
                data["adapter_id"],
                data["tier"],
                data["protocol"],
                data["endpoint"],
            )

        elif et == "validation.harness_adapter.health_changed":
            await self._db.execute(
                self._UPDATE_ADAPTER_HEALTH,
                data["adapter_id"],
                data.get("ready", False),
                data.get("success_rate_24h", 0.0),
            )

        else:
            logger.debug("ReflectionConsumer: ignoring %s", et)
