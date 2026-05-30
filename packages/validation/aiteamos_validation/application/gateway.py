"""
Validation Context — HarnessGateway + AdapterRegistry (arch.md §4.2.3)。

HarnessGateway: Saga 调用此 Gateway 触发验证。
HarnessAdapterRegistry: 根据 project + tier 路由到对应 Adapter。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import UUID

from aiteamos_shared.types import ProjectId, RunId, new_id

from ..domain.models import (
    DeliverableRef,
    HarnessAdapterAggregate,
    HarnessInvocation,
    HarnessOutcome,
    HarnessResult,
    HarnessTicket,
    HarnessTier,
    InvocationState,
    ProtocolKind,
    ValidationContext,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class AdapterRepoLike(Protocol):
    async def get_by_id(self, adapter_id: str, *, tx: Any = None) -> HarnessAdapterAggregate | None: ...
    async def save(self, aggregate: HarnessAdapterAggregate, *, tx: Any = None) -> None: ...
    async def find_by_project_and_tier(
        self, project_id: UUID, tier: HarnessTier, *, tx: Any = None
    ) -> list[HarnessAdapterAggregate]: ...
    async def list_all(self, *, tx: Any = None) -> list[HarnessAdapterAggregate]: ...


class InvocationRepoLike(Protocol):
    async def save(self, aggregate: HarnessInvocation, *, tx: Any = None) -> None: ...
    async def get_by_id(self, invocation_id: UUID, *, tx: Any = None) -> HarnessInvocation | None: ...
    async def get_by_callback_token(
        self, token: str, *, tx: Any = None
    ) -> HarnessInvocation | None: ...
    async def find_pending_expired(self, *, tx: Any = None) -> list[HarnessInvocation]: ...
    async def lock_for_update(
        self, invocation_id: UUID, *, tx: Any = None
    ) -> HarnessInvocation | None: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


# ---------------------------------------------------------------------------
# HarnessAdapterRegistry — 适配器注册与路由
# ---------------------------------------------------------------------------


class HarnessAdapterRegistry:
    """适配器注册表 — 根据 project + tier 选择 Adapter。

    路由规则:
    1. 精确匹配: project_bindings 包含 project_id 且 tier 匹配
    2. 全局匹配: project_bindings 为空且 tier 匹配
    3. 无匹配: 返回 None (Gateway 生成 skip ticket)
    """

    def __init__(self, adapter_repo: AdapterRepoLike):
        self._repo = adapter_repo

    async def resolve(
        self, project_id: UUID, tier: HarnessTier, *, tx: Any = None
    ) -> HarnessAdapterAggregate | None:
        """解析 project + tier 对应的适配器。

        优先精确匹配，其次全局匹配。
        """
        adapters = await self._repo.find_by_project_and_tier(project_id, tier, tx=tx)

        # 优先精确匹配 (project_bindings 包含 project_id)
        for adapter in adapters:
            if project_id in adapter.project_bindings:
                return adapter

        # 其次全局匹配 (project_bindings 为空)
        for adapter in adapters:
            if not adapter.project_bindings:
                return adapter

        return None


# ---------------------------------------------------------------------------
# HarnessGateway — 验证触发入口 (arch.md §4.2.3)
# ---------------------------------------------------------------------------


class HarnessGateway:
    """验证网关 — Saga 调用此 Gateway 触发验证。

    职责:
    1. 根据 project + tier 路由到对应 Adapter
    2. 无 Adapter 时返回 skip ticket
    3. 健康检查后触发验证
    4. 保存 HarnessInvocation 记录
    """

    def __init__(
        self,
        *,
        registry: HarnessAdapterRegistry,
        invocation_repo: InvocationRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._registry = registry
        self._invocation_repo = invocation_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def trigger(
        self,
        deliverable: DeliverableRef,
        tier: HarnessTier,
        project_id: UUID,
        *,
        validation_ctx: ValidationContext | None = None,
    ) -> HarnessTicket:
        """触发验证。

        Args:
            deliverable: 交付物引用
            tier: 验证层级
            project_id: 项目 ID
            validation_ctx: 验证上下文

        Returns:
            HarnessTicket (pending=True for async, outcome set for sync)
        """
        adapter = await self._registry.resolve(project_id, tier)
        if not adapter:
            logger.info(
                "No adapter for project=%s tier=%s, skipping",
                project_id, tier,
            )
            return HarnessTicket.skip(reason="no_adapter_configured")

        # 健康检查
        if not adapter.health.ready:
            logger.warning(
                "Adapter %s not ready: %s",
                adapter.id, adapter.health.diagnostics,
            )
            raise HarnessUnavailableError(
                adapter_id=adapter.id,
                diagnostics=adapter.health.diagnostics,
            )

        # 创建 Invocation 记录
        callback_token = _generate_callback_token()
        invocation = HarnessInvocation(
            adapter_id=adapter.id,
            run_id=UUID(deliverable.run_id) if isinstance(deliverable.run_id, str) else deliverable.run_id,
            deliverable_ref=deliverable.uri,
            callback_token=callback_token,
        )

        ticket = HarnessTicket(
            invocation_id=invocation.id,
            callback_token=callback_token,
            pending=(adapter.protocol == ProtocolKind.ASYNC),
        )

        async with self._tx.transaction() as tx:
            await self._invocation_repo.save(invocation, tx=tx)

            events = invocation.pending_events
            invocation.clear_pending_events()
            if events:
                await self._publisher.publish_events(
                    events, partition_key=str(invocation.run_id), tx=tx,
                )

        logger.info(
            "Triggered validation: invocation=%s adapter=%s tier=%s pending=%s",
            invocation.id, adapter.id, tier, ticket.pending,
        )
        return ticket

    async def complete_invocation(
        self,
        callback_token: str,
        result: HarnessResult,
    ) -> HarnessInvocation:
        """完成验证调用 (Webhook 回调或同步返回)。

        幂等: 非 pending 状态的 invocation 直接返回。

        Args:
            callback_token: 回调令牌
            result: 验证结果

        Returns:
            更新后的 HarnessInvocation

        Raises:
            ValueError: callback_token 不存在
        """
        async with self._tx.transaction() as tx:
            invocation = await self._invocation_repo.get_by_callback_token(
                callback_token, tx=tx
            )
            if invocation is None:
                raise ValueError(f"No invocation with callback_token={callback_token}")

            # 幂等: 已完成则跳过
            if invocation.is_terminal():
                logger.debug(
                    "Invocation %s already terminal (state=%s), skipping",
                    invocation.id, invocation.state,
                )
                return invocation

            invocation.mark_done(result)
            await self._invocation_repo.save(invocation, tx=tx)

            events = invocation.pending_events
            invocation.clear_pending_events()
            if events:
                await self._publisher.publish_events(
                    events, partition_key=str(invocation.run_id), tx=tx,
                )

        logger.info(
            "Invocation completed: id=%s outcome=%s",
            invocation.id, result.outcome,
        )
        return invocation


# ---------------------------------------------------------------------------
# WebhookInboundProcessor (arch.md §3.3.3)
# ---------------------------------------------------------------------------


class WebhookInboundProcessor:
    """Webhook 入站处理器。

    职责:
    1. HMAC 签名校验
    2. 结果归一化
    3. 驱动 Gateway.complete_invocation

    幂等: 重复回调不二次驱动 (通过 callback_token 唯一约束)。
    """

    def __init__(
        self,
        *,
        gateway: HarnessGateway,
    ):
        self._gateway = gateway

    async def process(
        self,
        *,
        callback_token: str,
        payload: dict[str, Any],
        result: HarnessResult,
    ) -> HarnessInvocation:
        """处理 Webhook 回调。

        Args:
            callback_token: 回调令牌
            payload: 原始 payload (用于审计)
            result: 归一化后的验证结果

        Returns:
            更新后的 HarnessInvocation
        """
        return await self._gateway.complete_invocation(callback_token, result)


# ---------------------------------------------------------------------------
# HarnessInvocationDeadlineSweeper (arch.md §3.3.6)
# ---------------------------------------------------------------------------


class HarnessInvocationDeadlineSweeper:
    """每分钟扫描过期的 pending invocation。

    不直接删除，而是标记 expired + 发领域事件。
    事件驱动 Saga 转终态 (Failed)。
    """

    def __init__(
        self,
        *,
        invocation_repo: InvocationRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = invocation_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def sweep(self) -> int:
        """扫描并标记过期的 pending invocation。

        Returns:
            标记为 expired 的数量
        """
        async with self._tx.transaction() as tx:
            expired_list = await self._repo.find_pending_expired(tx=tx)
            if not expired_list:
                return 0

            all_events: list[Any] = []
            for invocation in expired_list:
                invocation.mark_expired()
                await self._repo.save(invocation, tx=tx)
                all_events.extend(invocation.pending_events)
                invocation.clear_pending_events()

            if all_events:
                # 按 run_id 分区发布
                for event in all_events:
                    run_id = getattr(event, "run_id", "")
                    await self._publisher.publish_events(
                        [event], partition_key=str(run_id), tx=tx,
                    )

        logger.info("Sweep completed: %d invocations expired", len(expired_list))
        return len(expired_list)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class HarnessUnavailableError(Exception):
    """验证系统不可用。"""

    def __init__(self, *, adapter_id: str, diagnostics: dict[str, Any] | None = None):
        self.adapter_id = adapter_id
        self.diagnostics = diagnostics or {}
        super().__init__(f"Harness adapter {adapter_id!r} unavailable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_callback_token() -> str:
    from ..domain.models import generate_callback_token
    return generate_callback_token()
