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
from ..domain.models import Skill, SkillStatus
from .commands import (
    DeprecateSkillCommand,
    PublishSkillCommand,
    RegisterSkillCommand,
    UpdateSkillCommand,
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
        skill = Skill(
            name=cmd.name,
            version=cmd.version,
            description=cmd.description,
            domain=cmd.domain,
            capability_tags=cmd.capability_tags,
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


class UpdateSkillHandler:
    """处理 UpdateSkillCommand。"""

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

    async def handle(self, cmd: UpdateSkillCommand) -> Skill:
        async with self._tx.transaction() as tx:
            skill = await self._repo.lock_for_update(cmd.skill_id, tx=tx)
            if skill is None:
                raise ValueError(f"Skill {cmd.skill_id} not found")

            skill.update(
                description=cmd.description or skill.description,
                domain=cmd.domain or skill.domain,
                capability_tags=cmd.capability_tags or skill.capability_tags,
            )

            await self._repo.save(skill, tx=tx)
            events = skill.pending_events
            skill.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(skill.id), tx=tx
            )

        return skill
