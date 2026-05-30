"""
Validation Context — 域模型 + 应用层测试。

验证标准 (plan.md §3.1):
- HarnessAdapter 聚合根: 配置、project 绑定、matches 逻辑
- HarnessInvocation 聚合根: 状态转换、mark_done/expired/adapter_error、幂等
- HarnessGateway: 路由、skip ticket、健康检查、trigger、complete_invocation
- WebhookInboundProcessor: 幂等回调
- HarnessInvocationDeadlineSweeper: 过期扫描
- DDL migration 文件存在
"""

import pytest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from aiteamos_validation.domain.models import (
    AdapterHealth,
    DeliverableRef,
    FlakySignal,
    HarnessAdapterAggregate,
    HarnessInvocation,
    HarnessManifest,
    HarnessMetrics,
    HarnessOutcome,
    HarnessResult,
    HarnessTicket,
    HarnessTier,
    InvocationState,
    ProtocolKind,
    TIMEOUT_RULES,
    ValidationContext,
    generate_callback_token,
)
from aiteamos_validation.domain.events import (
    HarnessAdapterRegistered,
    HarnessInvocationCompleted,
    HarnessInvocationExpired,
    HarnessInvocationTriggered,
)


# ---------------------------------------------------------------------------
# Mock Infrastructure
# ---------------------------------------------------------------------------


class MockTransactionManager:
    def __init__(self):
        self.tx = MagicMock()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        yield self.tx


class MockEventPublisher:
    def __init__(self):
        self.published: list[tuple[list, str]] = []

    async def publish_events(
        self, events: list, *, partition_key: str, tx: Any
    ) -> None:
        self.published.append((events, partition_key))


class InMemoryAdapterRepo:
    """In-memory 适配器仓储。"""

    def __init__(self):
        self._store: dict[str, HarnessAdapterAggregate] = {}

    async def get_by_id(self, adapter_id: str, *, tx: Any = None) -> HarnessAdapterAggregate | None:
        return self._store.get(adapter_id)

    async def save(self, aggregate: HarnessAdapterAggregate, *, tx: Any = None) -> None:
        self._store[aggregate.id] = aggregate

    async def find_by_project_and_tier(
        self, project_id: UUID, tier: HarnessTier, *, tx: Any = None
    ) -> list[HarnessAdapterAggregate]:
        result = []
        for a in self._store.values():
            if a.tier == tier:
                if not a.project_bindings or project_id in a.project_bindings:
                    result.append(a)
        return result

    async def list_all(self, *, tx: Any = None) -> list[HarnessAdapterAggregate]:
        return list(self._store.values())


class InMemoryInvocationRepo:
    """In-memory 调用仓储。"""

    def __init__(self):
        self._store: dict[UUID, HarnessInvocation] = {}

    async def save(self, aggregate: HarnessInvocation, *, tx: Any = None) -> None:
        self._store[aggregate.id] = aggregate

    async def get_by_id(self, invocation_id: UUID, *, tx: Any = None) -> HarnessInvocation | None:
        return self._store.get(invocation_id)

    async def get_by_callback_token(
        self, token: str, *, tx: Any = None
    ) -> HarnessInvocation | None:
        for inv in self._store.values():
            if inv.callback_token == token:
                return inv
        return None

    async def find_pending_expired(self, *, tx: Any = None) -> list[HarnessInvocation]:
        now = datetime.now(timezone.utc)
        return [
            inv for inv in self._store.values()
            if inv.state == InvocationState.PENDING and inv.expire_at < now
        ]

    async def lock_for_update(
        self, invocation_id: UUID, *, tx: Any = None
    ) -> HarnessInvocation | None:
        return self._store.get(invocation_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(
    *,
    adapter_id: str = "test-adapter",
    tier: HarnessTier = HarnessTier.SPEC,
    protocol: ProtocolKind = ProtocolKind.SYNC,
    project_bindings: list[UUID] | None = None,
    ready: bool = True,
) -> HarnessAdapterAggregate:
    return HarnessAdapterAggregate(
        id=adapter_id,
        tier=tier,
        protocol=protocol,
        endpoint="https://harness.example.com/api",
        auth_secret_ref="HARNESS_TOKEN",
        health=AdapterHealth(ready=ready),
        project_bindings=project_bindings or [],
    )


def _make_invocation(
    *,
    state: InvocationState = InvocationState.PENDING,
    expire_past: bool = False,
) -> HarnessInvocation:
    now = datetime.now(timezone.utc)
    expire = now - timedelta(hours=1) if expire_past else now + timedelta(hours=25)
    return HarnessInvocation(
        adapter_id="test-adapter",
        run_id=uuid4(),
        deliverable_ref="s3://deliverables/patch-001",
        state=state,
        expire_at=expire,
    )


def _make_result(
    *,
    invocation_id: UUID | None = None,
    outcome: HarnessOutcome = HarnessOutcome.PASS,
) -> HarnessResult:
    return HarnessResult(
        invocation_id=invocation_id or uuid4(),
        callback_token="cb_test_token",
        outcome=outcome,
        tier=HarnessTier.SPEC,
        metrics=HarnessMetrics(duration_seconds=12.5, tests_passed=42, tests_failed=0),
        cost_usd=Decimal("0.05"),
    )


# ===========================================================================
# 1. HarnessAdapter 聚合根测试
# ===========================================================================


class TestHarnessAdapter:
    """测试 HarnessAdapter 配置型聚合根。"""

    def test_create_adapter(self):
        adapter = _make_adapter()
        assert adapter.id == "test-adapter"
        assert adapter.tier == HarnessTier.SPEC
        assert adapter.protocol == ProtocolKind.SYNC
        assert adapter.health.ready is True

    def test_matches_global(self):
        """全局适配器 (无 project_bindings) 匹配任意 project。"""
        adapter = _make_adapter()
        assert adapter.matches(uuid4(), HarnessTier.SPEC) is True

    def test_matches_specific_project(self):
        """精确匹配 project_id。"""
        pid = uuid4()
        adapter = _make_adapter(project_bindings=[pid])
        assert adapter.matches(pid, HarnessTier.SPEC) is True
        assert adapter.matches(uuid4(), HarnessTier.SPEC) is False

    def test_matches_wrong_tier(self):
        """tier 不匹配 → False。"""
        adapter = _make_adapter(tier=HarnessTier.SPEC)
        assert adapter.matches(uuid4(), HarnessTier.FUNCTIONAL) is False

    def test_bind_unbind_project(self):
        adapter = _make_adapter()
        pid = uuid4()
        adapter.bind_project(pid)
        assert pid in adapter.project_bindings
        adapter.unbind_project(pid)
        assert pid not in adapter.project_bindings

    def test_bind_duplicate_is_idempotent(self):
        adapter = _make_adapter()
        pid = uuid4()
        adapter.bind_project(pid)
        adapter.bind_project(pid)
        assert adapter.project_bindings.count(pid) == 1

    def test_update_health(self):
        adapter = _make_adapter()
        new_health = AdapterHealth(ready=False, success_rate_24h=0.5)
        adapter.update_health(new_health)
        assert adapter.health.ready is False
        assert adapter.health.success_rate_24h == 0.5


# ===========================================================================
# 2. HarnessInvocation 聚合根测试
# ===========================================================================


class TestHarnessInvocation:
    """测试 HarnessInvocation 运行时聚合根。"""

    def test_create_pending(self):
        inv = _make_invocation()
        assert inv.state == InvocationState.PENDING
        assert inv.callback_token.startswith("cb_")
        assert inv.is_terminal() is False

    def test_mark_done(self):
        inv = _make_invocation()
        result = _make_result(invocation_id=inv.id)
        inv.mark_done(result)

        assert inv.state == InvocationState.DONE
        assert inv.completed_at is not None
        assert inv.is_terminal() is True
        # 2 events: triggered (from __init__) + completed
        assert len(inv.pending_events) == 2
        assert "triggered" in inv.pending_events[0].event_type
        assert "completed" in inv.pending_events[1].event_type

    def test_mark_done_non_pending_raises(self):
        inv = _make_invocation(state=InvocationState.DONE)
        with pytest.raises(ValueError, match="Cannot complete"):
            inv.mark_done(_make_result())

    def test_mark_expired(self):
        inv = _make_invocation()
        inv.mark_expired()

        assert inv.state == InvocationState.EXPIRED
        assert inv.is_terminal() is True
        # 2 events: triggered (from __init__) + expired
        assert len(inv.pending_events) == 2
        assert "triggered" in inv.pending_events[0].event_type
        assert "expired" in inv.pending_events[1].event_type

    def test_mark_expired_idempotent(self):
        """非 pending 状态 → 幂等忽略。"""
        inv = _make_invocation(state=InvocationState.DONE)
        inv.mark_expired()  # 不应抛出
        assert inv.state == InvocationState.DONE

    def test_mark_adapter_error(self):
        inv = _make_invocation()
        inv.mark_adapter_error(diagnostics={"error": "connection_refused"})

        assert inv.state == InvocationState.ADAPTER_ERROR
        assert inv.is_terminal() is True
        assert inv.result is not None
        assert inv.result["outcome"] == "adapter_error"

    def test_archive(self):
        inv = _make_invocation()
        inv.archive()
        assert inv.archived_at is not None

    def test_terminal_states(self):
        for state in [InvocationState.DONE, InvocationState.EXPIRED, InvocationState.ADAPTER_ERROR]:
            inv = _make_invocation(state=state)
            assert inv.is_terminal() is True

    def test_from_ticket(self):
        ticket = HarnessTicket(
            invocation_id=uuid4(),
            callback_token="cb_test",
            pending=True,
        )
        inv = HarnessInvocation.from_ticket(
            ticket,
            adapter_id="jenkins-prod",
            run_id=uuid4(),
            deliverable_ref="s3://patch",
            tier=HarnessTier.SYSTEM,
        )
        assert inv.id == ticket.invocation_id
        assert inv.adapter_id == "jenkins-prod"
        assert inv.state == InvocationState.PENDING

    def test_callback_token_generation(self):
        token = generate_callback_token()
        assert token.startswith("cb_")
        assert len(token) > 10

    def test_flaky_signal_in_result(self):
        """含 flaky signal 的 result 正确保存。"""
        inv = _make_invocation()
        result = HarnessResult(
            invocation_id=inv.id,
            callback_token=inv.callback_token,
            outcome=HarnessOutcome.FLAKY,
            tier=HarnessTier.FUNCTIONAL,
            flaky_signal=FlakySignal(
                test_name="test_login",
                pass_count=8,
                fail_count=2,
                flake_rate=0.2,
            ),
        )
        inv.mark_done(result)
        assert inv.flaky_signal is not None
        assert inv.flaky_signal["test_name"] == "test_login"


# ===========================================================================
# 3. Value Objects 测试
# ===========================================================================


class TestValueObjects:
    """测试值对象。"""

    def test_harness_ticket_skip(self):
        ticket = HarnessTicket.skip(reason="no_adapter_configured")
        assert ticket.skip_reason == "no_adapter_configured"
        assert ticket.pending is False

    def test_harness_result(self):
        result = _make_result()
        assert result.outcome == HarnessOutcome.PASS
        assert result.cost_usd == Decimal("0.05")

    def test_timeout_rules(self):
        assert TIMEOUT_RULES[HarnessTier.SPEC] == timedelta(minutes=5)
        assert TIMEOUT_RULES[HarnessTier.FUNCTIONAL] == timedelta(minutes=30)
        assert TIMEOUT_RULES[HarnessTier.SYSTEM] == timedelta(hours=24)

    def test_deliverable_ref(self):
        ref = DeliverableRef(task_id="TASK-001", run_id="run-001", uri="s3://test")
        assert ref.kind == "code_patch"

    def test_validation_context_from_run(self):
        ctx = ValidationContext.from_run(
            task_id="t1", run_id="r1", member_id="m1",
            department_id="d1", project_id="p1",
        )
        assert ctx.task_id == "t1"


# ===========================================================================
# 4. HarnessGateway 测试
# ===========================================================================


class TestHarnessGateway:
    """测试验证网关。"""

    def _make_gateway(self):
        from aiteamos_validation.application.gateway import (
            HarnessAdapterRegistry,
            HarnessGateway,
        )

        adapter_repo = InMemoryAdapterRepo()
        invocation_repo = InMemoryInvocationRepo()
        publisher = MockEventPublisher()

        registry = HarnessAdapterRegistry(adapter_repo)
        gateway = HarnessGateway(
            registry=registry,
            invocation_repo=invocation_repo,
            tx_manager=MockTransactionManager(),
            event_publisher=publisher,
        )
        return gateway, adapter_repo, invocation_repo, publisher

    @pytest.mark.asyncio
    async def test_trigger_no_adapter_returns_skip(self):
        """无适配器 → skip ticket。"""
        gateway, _, _, _ = self._make_gateway()
        deliverable = DeliverableRef(task_id="t1", run_id=str(uuid4()), uri="s3://test")

        ticket = await gateway.trigger(deliverable, HarnessTier.SPEC, uuid4())

        assert ticket.skip_reason == "no_adapter_configured"

    @pytest.mark.asyncio
    async def test_trigger_unhealthy_adapter_raises(self):
        """不健康的适配器 → HarnessUnavailableError。"""
        from aiteamos_validation.application.gateway import HarnessUnavailableError

        gateway, adapter_repo, _, _ = self._make_gateway()
        adapter = _make_adapter(ready=False)
        await adapter_repo.save(adapter)

        deliverable = DeliverableRef(task_id="t1", run_id=str(uuid4()), uri="s3://test")

        with pytest.raises(HarnessUnavailableError):
            await gateway.trigger(deliverable, HarnessTier.SPEC, uuid4())

    @pytest.mark.asyncio
    async def test_trigger_sync_adapter(self):
        """同步适配器 → 创建 invocation。"""
        gateway, adapter_repo, invocation_repo, _ = self._make_gateway()
        adapter = _make_adapter(protocol=ProtocolKind.SYNC)
        await adapter_repo.save(adapter)

        run_id = uuid4()
        deliverable = DeliverableRef(task_id="t1", run_id=str(run_id), uri="s3://test")

        ticket = await gateway.trigger(deliverable, HarnessTier.SPEC, uuid4())

        assert ticket.pending is False
        assert ticket.skip_reason == ""
        assert len(invocation_repo._store) == 1

    @pytest.mark.asyncio
    async def test_trigger_async_adapter(self):
        """异步适配器 → pending ticket。"""
        gateway, adapter_repo, invocation_repo, _ = self._make_gateway()
        adapter = _make_adapter(protocol=ProtocolKind.ASYNC)
        await adapter_repo.save(adapter)

        deliverable = DeliverableRef(task_id="t1", run_id=str(uuid4()), uri="s3://test")

        ticket = await gateway.trigger(deliverable, HarnessTier.SPEC, uuid4())

        assert ticket.pending is True

    @pytest.mark.asyncio
    async def test_complete_invocation(self):
        """完成验证调用。"""
        gateway, _, invocation_repo, publisher = self._make_gateway()
        inv = _make_invocation()
        await invocation_repo.save(inv)

        result = _make_result(invocation_id=inv.id)
        result = HarnessResult(
            invocation_id=inv.id,
            callback_token=inv.callback_token,
            outcome=HarnessOutcome.PASS,
            tier=HarnessTier.SPEC,
        )

        completed = await gateway.complete_invocation(inv.callback_token, result)

        assert completed.state == InvocationState.DONE
        assert len(publisher.published) > 0

    @pytest.mark.asyncio
    async def test_complete_invocation_idempotent(self):
        """重复回调 → 幂等跳过。"""
        gateway, _, invocation_repo, publisher = self._make_gateway()
        inv = _make_invocation(state=InvocationState.DONE)
        await invocation_repo.save(inv)

        result = _make_result()
        completed = await gateway.complete_invocation(inv.callback_token, result)

        assert completed.state == InvocationState.DONE
        # 幂等: 不发布新事件
        assert len(publisher.published) == 0

    @pytest.mark.asyncio
    async def test_complete_invocation_not_found(self):
        """不存在的 callback_token → ValueError。"""
        gateway, _, _, _ = self._make_gateway()

        with pytest.raises(ValueError, match="No invocation"):
            await gateway.complete_invocation("cb_nonexistent", _make_result())


# ===========================================================================
# 5. HarnessAdapterRegistry 测试
# ===========================================================================


class TestHarnessAdapterRegistry:
    """测试适配器注册表路由。"""

    @pytest.mark.asyncio
    async def test_resolve_exact_match(self):
        """精确 project 匹配优先。"""
        from aiteamos_validation.application.gateway import HarnessAdapterRegistry

        repo = InMemoryAdapterRepo()
        pid = uuid4()
        global_adapter = _make_adapter(adapter_id="global-spec")
        exact_adapter = _make_adapter(adapter_id="exact-spec", project_bindings=[pid])
        await repo.save(global_adapter)
        await repo.save(exact_adapter)

        registry = HarnessAdapterRegistry(repo)
        result = await registry.resolve(pid, HarnessTier.SPEC)

        assert result is not None
        assert result.id == "exact-spec"

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_global(self):
        """无精确匹配 → 全局适配器。"""
        from aiteamos_validation.application.gateway import HarnessAdapterRegistry

        repo = InMemoryAdapterRepo()
        global_adapter = _make_adapter(adapter_id="global-spec")
        await repo.save(global_adapter)

        registry = HarnessAdapterRegistry(repo)
        result = await registry.resolve(uuid4(), HarnessTier.SPEC)

        assert result is not None
        assert result.id == "global-spec"

    @pytest.mark.asyncio
    async def test_resolve_none_when_no_match(self):
        """无匹配 → None。"""
        from aiteamos_validation.application.gateway import HarnessAdapterRegistry

        repo = InMemoryAdapterRepo()
        registry = HarnessAdapterRegistry(repo)
        result = await registry.resolve(uuid4(), HarnessTier.SYSTEM)

        assert result is None


# ===========================================================================
# 6. WebhookInboundProcessor 测试
# ===========================================================================


class TestWebhookInboundProcessor:
    """测试 Webhook 入站处理器。"""

    @pytest.mark.asyncio
    async def test_process_callback(self):
        """Webhook 回调驱动完成。"""
        from aiteamos_validation.application.gateway import (
            HarnessAdapterRegistry,
            HarnessGateway,
            WebhookInboundProcessor,
        )

        adapter_repo = InMemoryAdapterRepo()
        invocation_repo = InMemoryInvocationRepo()
        registry = HarnessAdapterRegistry(adapter_repo)
        gateway = HarnessGateway(
            registry=registry,
            invocation_repo=invocation_repo,
            tx_manager=MockTransactionManager(),
            event_publisher=MockEventPublisher(),
        )
        processor = WebhookInboundProcessor(gateway=gateway)

        inv = _make_invocation()
        await invocation_repo.save(inv)

        result = HarnessResult(
            invocation_id=inv.id,
            callback_token=inv.callback_token,
            outcome=HarnessOutcome.PASS,
            tier=HarnessTier.SPEC,
        )

        completed = await processor.process(
            callback_token=inv.callback_token,
            payload={"raw": "data"},
            result=result,
        )

        assert completed.state == InvocationState.DONE


# ===========================================================================
# 7. HarnessInvocationDeadlineSweeper 测试
# ===========================================================================


class TestDeadlineSweeper:
    """测试过期扫描。"""

    @pytest.mark.asyncio
    async def test_sweep_expires_pending(self):
        """过期的 pending invocation 被标记为 expired。"""
        from aiteamos_validation.application.gateway import HarnessInvocationDeadlineSweeper

        invocation_repo = InMemoryInvocationRepo()
        publisher = MockEventPublisher()
        sweeper = HarnessInvocationDeadlineSweeper(
            invocation_repo=invocation_repo,
            tx_manager=MockTransactionManager(),
            event_publisher=publisher,
        )

        # 创建 2 个过期 + 1 个未过期
        inv1 = _make_invocation(expire_past=True)
        inv2 = _make_invocation(expire_past=True)
        inv3 = _make_invocation(expire_past=False)
        await invocation_repo.save(inv1)
        await invocation_repo.save(inv2)
        await invocation_repo.save(inv3)

        count = await sweeper.sweep()

        assert count == 2
        assert inv1.state == InvocationState.EXPIRED
        assert inv2.state == InvocationState.EXPIRED
        assert inv3.state == InvocationState.PENDING

    @pytest.mark.asyncio
    async def test_sweep_no_expired(self):
        """无过期 → 返回 0。"""
        from aiteamos_validation.application.gateway import HarnessInvocationDeadlineSweeper

        invocation_repo = InMemoryInvocationRepo()
        sweeper = HarnessInvocationDeadlineSweeper(
            invocation_repo=invocation_repo,
            tx_manager=MockTransactionManager(),
            event_publisher=MockEventPublisher(),
        )

        inv = _make_invocation(expire_past=False)
        await invocation_repo.save(inv)

        count = await sweeper.sweep()
        assert count == 0


# ===========================================================================
# 8. Domain Events 测试
# ===========================================================================


class TestValidationEvents:
    """测试领域事件。"""

    def test_invocation_completed_event(self):
        evt = HarnessInvocationCompleted(
            event_type="validation.harness_invocation.completed",
            invocation_id=uuid4(),
            run_id=uuid4(),
            outcome="pass",
            callback_token="cb_test",
        )
        assert evt.event_type == "validation.harness_invocation.completed"

    def test_invocation_expired_event(self):
        evt = HarnessInvocationExpired(
            event_type="validation.harness_invocation.expired",
            invocation_id=uuid4(),
            run_id=uuid4(),
            callback_token="cb_test",
        )
        assert evt.reason == "gc_deadline_exceeded"

    def test_adapter_registered_event(self):
        evt = HarnessAdapterRegistered(
            event_type="validation.harness_adapter.registered",
            adapter_id="jenkins-prod",
            tier="system",
            protocol="async",
            endpoint="https://jenkins.example.com",
        )
        assert evt.adapter_id == "jenkins-prod"


# ===========================================================================
# 9. Migration 文件存在性检查
# ===========================================================================


class TestMigrationExists:
    """检查 DDL migration 文件存在。"""

    def test_migration_006_exists(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "006_validation_context.sql"
        )
        assert os.path.exists(path), "Migration 006_validation_context.sql should exist"
