"""
Knowledge Context — 应用层测试。

验证标准 (plan.md §1.2):
- Memory CRUD 全流程测试通过
- Outbox 表正确写入事件
- Edge 独立 CRUD 不触发 Node 锁
"""

import pytest
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from aiteamos_shared.types import new_id
from aiteamos_knowledge.domain.models import (
    Confidence,
    ConfidenceState,
    LifecycleState,
    MemoryContent,
    MemoryEdge,
    MemoryNode,
    Provenance,
    RelationType,
    Scope,
    ScopeKind,
    SourceKind,
    Tier,
)
from aiteamos_knowledge.application.commands import (
    AppendMemoryVersionCommand,
    ChangeLifecycleCommand,
    CreateMemoryEdgeCommand,
    CreateMemoryNodeCommand,
    DeprecateMemoryNodeCommand,
    RemoveMemoryEdgeCommand,
    UpdateMemoryContentCommand,
)
from aiteamos_knowledge.application.handlers import (
    AppendMemoryVersionHandler,
    ChangeLifecycleHandler,
    CreateMemoryEdgeHandler,
    CreateMemoryNodeHandler,
    DeprecateMemoryNodeHandler,
    RemoveMemoryEdgeHandler,
    UpdateMemoryContentHandler,
)
from aiteamos_knowledge.application.queries import (
    GetMemoryNodeDetailQuery,
    ListMemoryNodesExecutor,
    ListMemoryNodesQuery,
    MemoryNodeSummary,
    SearchMemoryByKeywordExecutor,
    SearchMemoryByKeywordQuery,
)


# ---------------------------------------------------------------------------
# Mock Infrastructure
# ---------------------------------------------------------------------------


class MockTransactionManager:
    """Mock transaction manager that yields a mock transaction."""

    def __init__(self):
        self.tx = MagicMock()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        yield self.tx


class MockEventPublisher:
    """Collects published events for assertion."""

    def __init__(self):
        self.published: list[tuple[list, str]] = []

    async def publish_events(
        self, events: list, *, partition_key: str, tx: Any
    ) -> None:
        self.published.append((events, partition_key))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(
    *,
    node_id: UUID | None = None,
    tier: Tier = Tier.PATTERNS,
) -> MemoryNode:
    return MemoryNode(
        id=node_id or new_id(),
        tier=tier,
        scope=Scope(kind=ScopeKind.GLOBAL),
        title="Test Memory",
        content=MemoryContent(statement="Test statement", tags=["test"]),
        confidence=Confidence(value=Decimal("0.5")),
        provenance=Provenance(source_kind=SourceKind.MANUAL_INPUT),
        lifecycle=LifecycleState.ACTIVE,
    )


# ===========================================================================
# Test CreateMemoryNodeHandler
# ===========================================================================


class TestCreateMemoryNodeHandler:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        handler = CreateMemoryNodeHandler(
            node_repo=repo,
            tx_manager=tx_mgr,
            event_publisher=publisher,
        )
        return handler, repo, publisher

    @pytest.mark.asyncio
    async def test_creates_node(self, setup):
        handler, repo, publisher = setup
        cmd = CreateMemoryNodeCommand(
            tier=Tier.PATTERNS,
            scope_kind=ScopeKind.GLOBAL,
            scope_ref=None,
            title="Test Memory",
            statement="Test statement",
            applicable_when="",
            counter_example="",
            tags=["test"],
            source_kind=SourceKind.MANUAL_INPUT,
        )
        node = await handler.handle(cmd)
        assert node.id is not None
        assert node.tier == Tier.PATTERNS
        assert node.title == "Test Memory"
        repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_publishes_event(self, setup):
        handler, repo, publisher = setup
        cmd = CreateMemoryNodeCommand(
            tier=Tier.FACTS,
            scope_kind=ScopeKind.PROJECT,
            scope_ref=new_id(),
            title="Project Rule",
            statement="Always use type hints",
            applicable_when="Python code",
            counter_example="",
            tags=["python", "typing"],
            source_kind=SourceKind.REVIEW,
        )
        node = await handler.handle(cmd)
        assert len(publisher.published) == 1
        events, partition_key = publisher.published[0]
        assert partition_key == str(node.id)
        assert any(e.event_type == "knowledge.memory_node.created" for e in events)


# ===========================================================================
# Test UpdateMemoryContentHandler
# ===========================================================================


class TestUpdateMemoryContentHandler:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        handler = UpdateMemoryContentHandler(
            node_repo=repo,
            tx_manager=tx_mgr,
            event_publisher=publisher,
        )
        return handler, repo, publisher

    @pytest.mark.asyncio
    async def test_updates_content(self, setup):
        handler, repo, publisher = setup
        node = _make_node()
        repo.lock_for_update.return_value = node

        member_id = new_id()
        cmd = UpdateMemoryContentCommand(
            memory_id=node.id,
            statement="Updated statement",
            applicable_when="always",
            counter_example="",
            tags=["updated"],
            reason="Content correction",
            author_member_id=member_id,
        )
        result = await handler.handle(cmd)
        assert result.content.statement == "Updated statement"
        assert result.current_version == 2
        repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found_raises(self, setup):
        handler, repo, publisher = setup
        repo.lock_for_update.return_value = None

        cmd = UpdateMemoryContentCommand(
            memory_id=new_id(),
            statement="x",
            applicable_when="",
            counter_example="",
            tags=[],
            reason="test",
            author_member_id=new_id(),
        )
        with pytest.raises(ValueError, match="not found"):
            await handler.handle(cmd)


# ===========================================================================
# Test AppendMemoryVersionHandler
# ===========================================================================


class TestAppendMemoryVersionHandler:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        handler = AppendMemoryVersionHandler(
            node_repo=repo,
            tx_manager=tx_mgr,
            event_publisher=publisher,
        )
        return handler, repo, publisher

    @pytest.mark.asyncio
    async def test_appends_version(self, setup):
        handler, repo, publisher = setup
        node = _make_node()
        repo.lock_for_update.return_value = node

        cmd = AppendMemoryVersionCommand(
            memory_id=node.id,
            diff={"field": "value"},
            reason="Metadata change",
            author_member_id=new_id(),
        )
        result = await handler.handle(cmd)
        assert result.current_version == 2
        assert len(result.versions) == 1
        assert result.versions[0].reason == "Metadata change"


# ===========================================================================
# Test ChangeLifecycleHandler
# ===========================================================================


class TestChangeLifecycleHandler:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        handler = ChangeLifecycleHandler(
            node_repo=repo,
            tx_manager=tx_mgr,
            event_publisher=publisher,
        )
        return handler, repo, publisher

    @pytest.mark.asyncio
    async def test_changes_lifecycle(self, setup):
        handler, repo, publisher = setup
        node = _make_node()
        repo.lock_for_update.return_value = node

        cmd = ChangeLifecycleCommand(
            memory_id=node.id,
            new_state=LifecycleState.STALE,
        )
        result = await handler.handle(cmd)
        assert result.lifecycle == LifecycleState.STALE

    @pytest.mark.asyncio
    async def test_quarantine_emits_event(self, setup):
        handler, repo, publisher = setup
        node = _make_node()
        repo.lock_for_update.return_value = node

        cmd = ChangeLifecycleCommand(
            memory_id=node.id,
            new_state=LifecycleState.QUARANTINED,
        )
        await handler.handle(cmd)
        events, _ = publisher.published[0]
        event_types = [e.event_type for e in events]
        assert "knowledge.memory_node.lifecycle_changed" in event_types
        assert "knowledge.memory_node.quarantined" in event_types


# ===========================================================================
# Test DeprecateMemoryNodeHandler
# ===========================================================================


class TestDeprecateMemoryNodeHandler:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        handler = DeprecateMemoryNodeHandler(
            node_repo=repo,
            tx_manager=tx_mgr,
            event_publisher=publisher,
        )
        return handler, repo, publisher

    @pytest.mark.asyncio
    async def test_deprecates_node(self, setup):
        handler, repo, publisher = setup
        node = _make_node()
        repo.lock_for_update.return_value = node

        cmd = DeprecateMemoryNodeCommand(memory_id=node.id)
        result = await handler.handle(cmd)
        assert result.lifecycle == LifecycleState.DEPRECATED
        assert result.confidence.state == ConfidenceState.DEPRECATED


# ===========================================================================
# Test CreateMemoryEdgeHandler (I-K-5)
# ===========================================================================


class TestCreateMemoryEdgeHandler:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        handler = CreateMemoryEdgeHandler(
            edge_repo=repo,
            tx_manager=tx_mgr,
            event_publisher=publisher,
        )
        return handler, repo, publisher

    @pytest.mark.asyncio
    async def test_creates_edge(self, setup):
        handler, repo, publisher = setup
        src = new_id()
        tgt = new_id()
        creator = new_id()

        cmd = CreateMemoryEdgeCommand(
            source_id=src,
            target_id=tgt,
            relation_type=RelationType.CAUSAL,
            created_by=creator,
        )
        edge = await handler.handle(cmd)
        assert edge.source_id == src
        assert edge.target_id == tgt
        assert edge.relation_type == RelationType.CAUSAL
        repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_edge_publishes_event(self, setup):
        handler, repo, publisher = setup
        cmd = CreateMemoryEdgeCommand(
            source_id=new_id(),
            target_id=new_id(),
            relation_type=RelationType.DEPENDS,
            created_by=new_id(),
        )
        edge = await handler.handle(cmd)
        assert len(publisher.published) == 1
        events, pk = publisher.published[0]
        assert events[0].event_type == "knowledge.memory_edge.added"


# ===========================================================================
# Test RemoveMemoryEdgeHandler (I-K-5)
# ===========================================================================


class TestRemoveMemoryEdgeHandler:
    @pytest.fixture
    def setup(self):
        repo = AsyncMock()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        handler = RemoveMemoryEdgeHandler(
            edge_repo=repo,
            tx_manager=tx_mgr,
            event_publisher=publisher,
        )
        return handler, repo, publisher

    @pytest.mark.asyncio
    async def test_removes_edge(self, setup):
        handler, repo, publisher = setup
        edge = MemoryEdge(
            source_id=new_id(),
            target_id=new_id(),
            relation_type=RelationType.DERIVED,
            created_by=new_id(),
        )
        repo.get_by_id.return_value = edge

        cmd = RemoveMemoryEdgeCommand(edge_id=edge.edge_id)
        await handler.handle(cmd)
        repo.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_edge_not_found_raises(self, setup):
        handler, repo, publisher = setup
        repo.get_by_id.return_value = None

        cmd = RemoveMemoryEdgeCommand(edge_id=new_id())
        with pytest.raises(ValueError, match="not found"):
            await handler.handle(cmd)


# ===========================================================================
# Test Query Executors (with mock read repo)
# ===========================================================================


class TestListMemoryNodesExecutor:
    @pytest.mark.asyncio
    async def test_execute(self):
        mock_repo = AsyncMock()
        mock_repo.list_nodes.return_value = [
            MemoryNodeSummary(
                id=new_id(),
                tier="patterns",
                title="Test",
                lifecycle_state="active",
                confidence_value=0.5,
                scope_kind="global",
                tags=["test"],
                current_version=1,
                created_at=None,
            )
        ]

        executor = ListMemoryNodesExecutor(read_repo=mock_repo)
        query = ListMemoryNodesQuery(tier=Tier.PATTERNS, limit=10)
        results = await executor.execute(query)
        assert len(results) == 1
        assert results[0].tier == "patterns"


class TestSearchMemoryByKeywordExecutor:
    @pytest.mark.asyncio
    async def test_execute(self):
        mock_repo = AsyncMock()
        mock_repo.search_by_keyword.return_value = [
            MemoryNodeSummary(
                id=new_id(),
                tier="facts",
                title="Python Guide",
                lifecycle_state="active",
                confidence_value=0.8,
                scope_kind="global",
                tags=["python"],
                current_version=1,
                created_at=None,
            )
        ]

        executor = SearchMemoryByKeywordExecutor(read_repo=mock_repo)
        query = SearchMemoryByKeywordQuery(keyword="python")
        results = await executor.execute(query)
        assert len(results) == 1
        assert results[0].title == "Python Guide"
