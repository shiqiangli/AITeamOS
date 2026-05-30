"""
Capability Context — Command Handlers (CQRS write side)。

每个 Handler 负责:
1. 从仓储加载聚合
2. 执行不变量校验
3. 修改聚合状态
4. 发出领域事件（通过 Outbox 同事务写入）
5. 保存聚合
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from aiteamos_shared.types import SkillId

from ..domain.events import SkillRegistered
from ..domain.invariants import (
    InvariantViolationError,
    assert_backward_compatible,
)
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
from .commands import (
    DeprecateSkillCommand,
    PublishSkillCommand,
    RegisterSkillCommand,
    UpdateSkillManifestCommand,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class SkillRepoLike(Protocol):
    async def get_by_id(self, id: Any, *, tx: Any = None) -> Skill | None: ...
    async def save(self, aggregate: Skill, *, tx: Any = None) -> None: ...
    async def lock_for_update(self, id: Any, *, tx: Any) -> Skill | None: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_side_effects(raw: list[dict[str, str]]) -> list[SideEffect]:
    return [
        SideEffect(
            resource_kind=se.get("resource_kind", ""),
            resource_pattern=se.get("resource_pattern", ""),
            mutation_kind=MutationKind(se.get("mutation_kind", "read")),
        )
        for se in raw
    ]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


class RegisterSkillHandler:
    """处理 RegisterSkillCommand。"""

    def __init__(
        self,
        *,
        skill_repo: SkillRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = skill_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: RegisterSkillCommand) -> Skill:
        manifest = SkillManifest(
            name=cmd.name,
            version=cmd.version,
            description=cmd.description,
            domain=cmd.domain,
            inputs=cmd.inputs,
            outputs=cmd.outputs,
            preconditions=cmd.preconditions,
            input_schema=cmd.input_schema,
            output_schema=cmd.output_schema,
            side_effects=_parse_side_effects(cmd.side_effects),
            required_permissions=cmd.required_permissions,
            capability_tags=cmd.capability_tags,
            examples=cmd.examples,
            references=cmd.references,
            quality_signals=cmd.quality_signals,
            cost_estimate=CostEstimate(
                token_estimate=cmd.token_estimate,
                time_estimate_seconds=cmd.time_estimate_seconds,
            ),
        )

        skill = Skill(
            name=cmd.name,
            version=cmd.version,
            manifest=manifest,
            status=SkillStatus.DRAFT,
        )

        registered_event = SkillRegistered(
            event_type="capability.skill.registered",
            skill_id=skill.id,
            name=skill.name,
            version=str(skill.version),
        )

        async with self._tx.transaction() as tx:
            await self._repo.save(skill, tx=tx)
            all_events = [registered_event] + skill.pending_events
            skill.clear_pending_events()
            await self._publisher.publish_events(
                all_events, partition_key=str(skill.id), tx=tx
            )

        logger.info("Registered Skill %s (name=%s, v=%s)", skill.id, skill.name, skill.version)
        return skill


class PublishSkillHandler:
    """处理 PublishSkillCommand。"""

    def __init__(
        self,
        *,
        skill_repo: SkillRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = skill_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: PublishSkillCommand) -> Skill:
        async with self._tx.transaction() as tx:
            skill = await self._repo.lock_for_update(cmd.skill_id, tx=tx)
            if skill is None:
                raise ValueError(f"Skill {cmd.skill_id} not found")

            skill.publish()

            await self._repo.save(skill, tx=tx)
            events = skill.pending_events
            skill.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(skill.id), tx=tx
            )

        return skill


class DeprecateSkillHandler:
    """处理 DeprecateSkillCommand。"""

    def __init__(
        self,
        *,
        skill_repo: SkillRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = skill_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: DeprecateSkillCommand) -> Skill:
        async with self._tx.transaction() as tx:
            skill = await self._repo.lock_for_update(cmd.skill_id, tx=tx)
            if skill is None:
                raise ValueError(f"Skill {cmd.skill_id} not found")

            skill.deprecate(reason=cmd.reason)

            await self._repo.save(skill, tx=tx)
            events = skill.pending_events
            skill.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(skill.id), tx=tx
            )

        return skill


class UpdateSkillManifestHandler:
    """处理 UpdateSkillManifestCommand。

    I-C-1: published 后 schema 只能向后兼容变更。
    """

    def __init__(
        self,
        *,
        skill_repo: SkillRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = skill_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: UpdateSkillManifestCommand) -> Skill:
        async with self._tx.transaction() as tx:
            skill = await self._repo.lock_for_update(cmd.skill_id, tx=tx)
            if skill is None:
                raise ValueError(f"Skill {cmd.skill_id} not found")

            new_manifest = SkillManifest(
                name=skill.manifest.name,
                version=skill.manifest.version,
                description=cmd.description or skill.manifest.description,
                domain=cmd.domain or skill.manifest.domain,
                inputs=cmd.inputs,
                outputs=cmd.outputs,
                preconditions=cmd.preconditions,
                input_schema=cmd.input_schema,
                output_schema=cmd.output_schema,
                side_effects=_parse_side_effects(cmd.side_effects),
                required_permissions=cmd.required_permissions,
                capability_tags=cmd.capability_tags,
                examples=cmd.examples,
                references=cmd.references,
                quality_signals=cmd.quality_signals,
                cost_estimate=skill.manifest.cost_estimate,
            )

            # I-C-1: published Skill 必须向后兼容
            if skill.status == SkillStatus.PUBLISHED:
                assert_backward_compatible(skill.manifest, new_manifest)

            skill.update_manifest(new_manifest)

            await self._repo.save(skill, tx=tx)
            events = skill.pending_events
            skill.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(skill.id), tx=tx
            )

        return skill
