"""
Capability Context — 应用层测试。

验证标准 (plan.md §1.3):
- Skill 注册 → 发布 → 废弃全流程
- Outbox 事件正确写入
"""

import pytest
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from aiteamos_shared.types import SemVer, new_id
from aiteamos_capability.domain.models import (
    CircuitState,
    MutationKind,
    SideEffect,
    Skill,
    SkillHealth,
    SkillManifest,
    SkillStatus,
)
from aiteamos_capability.application.commands import (
    DeprecateSkillCommand,
    ListSkillsQuery,
    PublishSkillCommand,
    RegisterSkillCommand,
    SearchSkillsByTagQuery,
    UpdateSkillManifestCommand,
)
from aiteamos_capability.application.handlers import (
    DeprecateSkillHandler,
    PublishSkillHandler,
    RegisterSkillHandler,
    UpdateSkillManifestHandler,
)
from aiteamos_capability.application.queries import (
    ListSkillsExecutor,
    SearchSkillsByTagExecutor,
    SkillSummary,
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


def _make_skill(*, status: SkillStatus = SkillStatus.DRAFT) -> Skill:
    manifest = SkillManifest(
        name="test-skill",
        version=SemVer(major=1, minor=0, patch=0),
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
        capability_tags=["test"],
    )
    return Skill(
        name="test-skill",
        version=SemVer(major=1, minor=0, patch=0),
        manifest=manifest,
        status=status,
    )


# ===========================================================================
# Test RegisterSkillHandler
# ===========================================================================


class TestRegisterSkillHandler:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        handler = RegisterSkillHandler(
            skill_repo=repo, tx_manager=tx_mgr, event_publisher=publisher
        )
        return handler, repo, publisher

    @pytest.mark.asyncio
    async def test_registers_skill(self, setup):
        handler, repo, publisher = setup
        cmd = RegisterSkillCommand(
            name="code-review",
            version=SemVer(major=1, minor=0, patch=0),
            description="Reviews code for issues",
            domain="code-review",
            inputs=["source tree"],
            outputs=["review findings"],
            preconditions=[],
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            side_effects=[{"resource_kind": "filesystem", "resource_pattern": "*.py", "mutation_kind": "read"}],
            required_permissions=["read:code"],
            capability_tags=["review"],
            examples=["review a Python module"],
            references=[],
            quality_signals={"signals": ["findings are actionable"]},
        )
        skill = await handler.handle(cmd)
        assert skill.name == "code-review"
        assert skill.status == SkillStatus.DRAFT
        repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_publishes_registered_event(self, setup):
        handler, repo, publisher = setup
        cmd = RegisterSkillCommand(
            name="test",
            version=SemVer(major=0, minor=1, patch=0),
            description="",
            domain="test",
            inputs=[],
            outputs=[],
            preconditions=[],
            input_schema={},
            output_schema={},
            side_effects=[],
            required_permissions=[],
            capability_tags=[],
            examples=[],
            references=[],
            quality_signals={},
        )
        skill = await handler.handle(cmd)
        assert len(publisher.published) == 1
        events, pk = publisher.published[0]
        assert any(e.event_type == "capability.skill.registered" for e in events)
        assert pk == str(skill.id)


# ===========================================================================
# Test PublishSkillHandler
# ===========================================================================


class TestPublishSkillHandler:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        handler = PublishSkillHandler(
            skill_repo=repo, tx_manager=tx_mgr, event_publisher=publisher
        )
        return handler, repo, publisher

    @pytest.mark.asyncio
    async def test_publishes_skill(self, setup):
        handler, repo, publisher = setup
        skill = _make_skill()
        repo.lock_for_update.return_value = skill

        cmd = PublishSkillCommand(skill_id=skill.id)
        result = await handler.handle(cmd)
        assert result.status == SkillStatus.PUBLISHED

    @pytest.mark.asyncio
    async def test_not_found_raises(self, setup):
        handler, repo, publisher = setup
        repo.lock_for_update.return_value = None

        cmd = PublishSkillCommand(skill_id=new_id())
        with pytest.raises(ValueError, match="not found"):
            await handler.handle(cmd)

    @pytest.mark.asyncio
    async def test_publishes_event(self, setup):
        handler, repo, publisher = setup
        skill = _make_skill()
        repo.lock_for_update.return_value = skill

        await handler.handle(PublishSkillCommand(skill_id=skill.id))
        events, _ = publisher.published[0]
        assert any(e.event_type == "capability.skill.published" for e in events)


# ===========================================================================
# Test DeprecateSkillHandler
# ===========================================================================


class TestDeprecateSkillHandler:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        handler = DeprecateSkillHandler(
            skill_repo=repo, tx_manager=tx_mgr, event_publisher=publisher
        )
        return handler, repo, publisher

    @pytest.mark.asyncio
    async def test_deprecates_skill(self, setup):
        handler, repo, publisher = setup
        skill = _make_skill(status=SkillStatus.PUBLISHED)
        repo.lock_for_update.return_value = skill

        cmd = DeprecateSkillCommand(skill_id=skill.id, reason="outdated")
        result = await handler.handle(cmd)
        assert result.status == SkillStatus.DEPRECATED

    @pytest.mark.asyncio
    async def test_publishes_deprecated_event(self, setup):
        handler, repo, publisher = setup
        skill = _make_skill(status=SkillStatus.PUBLISHED)
        repo.lock_for_update.return_value = skill

        await handler.handle(DeprecateSkillCommand(skill_id=skill.id, reason="old"))
        events, _ = publisher.published[0]
        assert any(e.event_type == "capability.skill.deprecated" for e in events)


# ===========================================================================
# Test UpdateSkillManifestHandler
# ===========================================================================


class TestUpdateSkillManifestHandler:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        handler = UpdateSkillManifestHandler(
            skill_repo=repo, tx_manager=tx_mgr, event_publisher=publisher
        )
        return handler, repo, publisher

    @pytest.mark.asyncio
    async def test_update_draft_no_constraint(self, setup):
        handler, repo, publisher = setup
        skill = _make_skill(status=SkillStatus.DRAFT)
        repo.lock_for_update.return_value = skill

        cmd = UpdateSkillManifestCommand(
            skill_id=skill.id,
            input_schema={"type": "object", "properties": {"new_field": {}}},
            output_schema={},
            side_effects=[],
            required_permissions=[],
            capability_tags=[],
        )
        result = await handler.handle(cmd)
        assert "new_field" in result.manifest.input_schema.get("properties", {})

    @pytest.mark.asyncio
    async def test_update_published_backward_compatible(self, setup):
        handler, repo, publisher = setup
        skill = _make_skill(status=SkillStatus.PUBLISHED)
        repo.lock_for_update.return_value = skill

        # 向后兼容: 添加可选字段
        cmd = UpdateSkillManifestCommand(
            skill_id=skill.id,
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "extra": {"type": "string"},
                },
            },
            output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
            side_effects=[],
            required_permissions=[],
            capability_tags=[],
        )
        result = await handler.handle(cmd)
        assert "extra" in result.manifest.input_schema.get("properties", {})

    @pytest.mark.asyncio
    async def test_update_published_incompatible_raises(self, setup):
        handler, repo, publisher = setup
        skill = _make_skill(status=SkillStatus.PUBLISHED)
        repo.lock_for_update.return_value = skill

        # 不兼容: 删除已有字段
        cmd = UpdateSkillManifestCommand(
            skill_id=skill.id,
            input_schema={"type": "object", "properties": {}},  # 删除了 text
            output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
            side_effects=[],
            required_permissions=[],
            capability_tags=[],
        )
        with pytest.raises(Exception, match="I-C-1"):
            await handler.handle(cmd)


# ===========================================================================
# Test Full Lifecycle: Register → Publish → Deprecate
# ===========================================================================


class TestSkillLifecycle:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()

        # 1. Register
        register_handler = RegisterSkillHandler(
            skill_repo=repo, tx_manager=tx_mgr, event_publisher=publisher
        )
        skill = await register_handler.handle(
            RegisterSkillCommand(
                name="lifecycle-test",
                version=SemVer(major=1, minor=0, patch=0),
                description="Test",
                domain="test",
                inputs=[],
                outputs=[],
                preconditions=[],
                input_schema={},
                output_schema={},
                side_effects=[],
                required_permissions=[],
                capability_tags=[],
                examples=[],
                references=[],
                quality_signals={},
            )
        )
        assert skill.status == SkillStatus.DRAFT

        # 2. Publish
        repo.lock_for_update.return_value = skill
        publish_handler = PublishSkillHandler(
            skill_repo=repo, tx_manager=tx_mgr, event_publisher=publisher
        )
        published = await publish_handler.handle(PublishSkillCommand(skill_id=skill.id))
        assert published.status == SkillStatus.PUBLISHED

        # 3. Deprecate
        repo.lock_for_update.return_value = published
        deprecate_handler = DeprecateSkillHandler(
            skill_repo=repo, tx_manager=tx_mgr, event_publisher=publisher
        )
        deprecated = await deprecate_handler.handle(
            DeprecateSkillCommand(skill_id=skill.id, reason="end of life")
        )
        assert deprecated.status == SkillStatus.DEPRECATED


# ===========================================================================
# Test Query Executors
# ===========================================================================


class TestListSkillsExecutor:
    @pytest.mark.asyncio
    async def test_execute(self):
        mock_repo = AsyncMock()
        mock_repo.list_skills.return_value = [
            SkillSummary(
                id=new_id(),
                name="test",
                version="1.0.0",
                description="Test skill",
                domain="test",
                status="published",
                circuit_state="closed",
                capability_tags=["test"],
                created_at=None,
            )
        ]
        executor = ListSkillsExecutor(read_repo=mock_repo)
        results = await executor.execute(ListSkillsQuery(status=SkillStatus.PUBLISHED))
        assert len(results) == 1


class TestSearchSkillsByTagExecutor:
    @pytest.mark.asyncio
    async def test_execute(self):
        mock_repo = AsyncMock()
        mock_repo.search_by_tag.return_value = [
            SkillSummary(
                id=new_id(),
                name="code-review",
                version="1.0.0",
                description="Code review skill",
                domain="review",
                status="published",
                circuit_state="closed",
                capability_tags=["review"],
                created_at=None,
            )
        ]
        executor = SearchSkillsByTagExecutor(read_repo=mock_repo)
        results = await executor.execute(SearchSkillsByTagQuery(tags=["review"]))
        assert len(results) == 1
