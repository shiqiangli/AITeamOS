"""
Knowledge Context — Reflection Event Consumer (H4: Reflection Pipeline wiring).

Consumes ``execution.run.finished`` events and delegates to
:class:`ReflectionEngine` to extract Memory candidates from completed runs.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer

from .extraction import ExtractionInput, ReflectionEngine

logger = logging.getLogger(__name__)


class ReflectionConsumer(IdempotentProjectionConsumer):
    """Subscribe to RunFinished events → trigger Memory extraction.

    consumer_id is unique so that this consumer tracks its own offset
    in the ``projection_offsets`` table.
    """

    consumer_id = "reflection-extract-v1"

    def __init__(self, *, engine: ReflectionEngine, db: Any):
        super().__init__(db=db)
        self._engine = engine

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        if event.event_type != "execution.run.finished":
            return

        data = event.model_dump()
        run_id = data.get("run_id", "")
        task_id = data.get("task_id", "")
        outcome = data.get("outcome", "success")

        logger.info(
            "ReflectionConsumer: extracting from run=%s task=%s outcome=%s",
            run_id, task_id, outcome,
        )

        input_data = ExtractionInput(
            task_id=task_id,
            run_id=run_id,
            member_id=data.get("member_id", ""),
            department_id=UUID(data["department_id"]) if data.get("department_id") else UUID(int=0),
            project_ids=[UUID(p) for p in data.get("project_ids", [])],
            snapshot_content=data.get("snapshot", {}),
            run_trace=data.get("run_trace", {}),
            outcome=outcome,
            retry_count=data.get("retry_count", 0),
        )

        try:
            nodes = await self._engine.extract_from_run(input_data)
            logger.info(
                "ReflectionConsumer: extracted %d candidates from task=%s",
                len(nodes), task_id,
            )
        except Exception:
            logger.exception(
                "ReflectionConsumer: extraction failed for task=%s", task_id,
            )
