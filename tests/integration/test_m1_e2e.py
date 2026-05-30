"""
M1 End-to-End Integration Tests (plan.md §1.7).

Uses **real command handlers** + **in-memory repositories** to validate the full
M1 delivery checklist through the API Gateway HTTP layer.

验证标准 (M1 完成条件):
- 可创建/编辑/分配 Memory，Memory 有版本历史
- 可注册 Skill 并分配给 AI Member
- 可创建 Member、Department、Project 并建立映射关系
- 所有跨上下文通信走领域事件
- Outbox 表正确记录所有事件
- Project 可关联 Repository 和成员
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

E2E_ADMIN_KEY = "e2e-test-key-m1-2026"

from aiteamos_api.composition import ServiceContainer
from aiteamos_api.main import create_app


# ---------------------------------------------------------------------------
# In-Memory Infrastructure
# ---------------------------------------------------------------------------


class InMemoryRepo:
    """Dict-backed repository implementing the common repo protocol."""

    def __init__(self):
        self._store: dict[UUID, Any] = {}

    async def get_by_id(self, id: UUID, *, tx: Any = None) -> Any:
        return self._store.get(id)

    async def save(self, aggregate: Any, *, tx: Any = None) -> None:
        key = getattr(aggregate, "id", None) or getattr(aggregate, "edge_id", None)
        self._store[key] = aggregate

    async def lock_for_update(self, id: UUID, *, tx: Any = None) -> Any:
        return self._store.get(id)

    async def delete(self, edge_id: UUID, *, tx: Any = None) -> None:
        self._store.pop(edge_id, None)

    def all(self) -> list[Any]:
        return list(self._store.values())


class InMemoryTxManager:
    """No-op transaction manager for testing."""

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        yield object()  # dummy tx handle


class RecordingEventPublisher:
    """Records all published events for later assertion."""

    def __init__(self):
        self.events: list[Any] = []
        self.partitions: list[str] = []

    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None:
        self.events.extend(events)
        self.partitions.extend([partition_key] * len(events))


# ---------------------------------------------------------------------------
# Container Factory — wires real handlers with in-memory infra
# ---------------------------------------------------------------------------


def _build_e2e_container() -> tuple[ServiceContainer, dict[str, Any]]:
    """Build a ServiceContainer with REAL handlers + in-memory repos.

    Returns (container, infra_dict) where infra_dict holds repos and
    publishers for test-level assertions.
    """
    container = ServiceContainer()

    # -- Shared infra --
    tx_mgr = InMemoryTxManager()

    # -- Knowledge BC --
    memory_node_repo = InMemoryRepo()
    memory_edge_repo = InMemoryRepo()
    memory_publisher = RecordingEventPublisher()

    from aiteamos_knowledge.application.handlers import (
        AppendMemoryVersionHandler,
        ChangeLifecycleHandler,
        CreateMemoryEdgeHandler,
        CreateMemoryNodeHandler,
        UpdateMemoryContentHandler,
    )

    container.register("memory_create_handler", CreateMemoryNodeHandler(
        node_repo=memory_node_repo, tx_manager=tx_mgr, event_publisher=memory_publisher,
    ))
    container.register("memory_update_handler", UpdateMemoryContentHandler(
        node_repo=memory_node_repo, tx_manager=tx_mgr, event_publisher=memory_publisher,
    ))
    container.register("memory_version_handler", AppendMemoryVersionHandler(
        node_repo=memory_node_repo, tx_manager=tx_mgr, event_publisher=memory_publisher,
    ))
    container.register("memory_lifecycle_handler", ChangeLifecycleHandler(
        node_repo=memory_node_repo, tx_manager=tx_mgr, event_publisher=memory_publisher,
    ))
    container.register("memory_edge_handler", CreateMemoryEdgeHandler(
        edge_repo=memory_edge_repo, tx_manager=tx_mgr, event_publisher=memory_publisher,
    ))

    # -- Capability BC --
    skill_repo = InMemoryRepo()
    skill_publisher = RecordingEventPublisher()

    from aiteamos_capability.application.handlers import (
        DeprecateSkillHandler,
        PublishSkillHandler,
        RegisterSkillHandler,
    )

    container.register("skill_register_handler", RegisterSkillHandler(
        skill_repo=skill_repo, tx_manager=tx_mgr, event_publisher=skill_publisher,
    ))
    container.register("skill_publish_handler", PublishSkillHandler(
        skill_repo=skill_repo, tx_manager=tx_mgr, event_publisher=skill_publisher,
    ))
    container.register("skill_deprecate_handler", DeprecateSkillHandler(
        skill_repo=skill_repo, tx_manager=tx_mgr, event_publisher=skill_publisher,
    ))

    # -- Workforce BC --
    member_repo = InMemoryRepo()
    dept_repo = InMemoryRepo()
    project_repo = InMemoryRepo()
    workforce_publisher = RecordingEventPublisher()

    from aiteamos_workforce.application.handlers import (
        AssignMemberToProjectHandler,
        AssignMemoryToMemberHandler,
        AssignSkillToMemberHandler,
        CreateDepartmentHandler,
        CreateMemberHandler,
        CreateProjectHandler,
        UpdateProjectHandler,
    )

    container.register("member_create_handler", CreateMemberHandler(
        repo=member_repo, tx_manager=tx_mgr, event_publisher=workforce_publisher,
    ))
    container.register("department_create_handler", CreateDepartmentHandler(
        repo=dept_repo, tx_manager=tx_mgr, event_publisher=workforce_publisher,
    ))
    container.register("project_create_handler", CreateProjectHandler(
        repo=project_repo, tx_manager=tx_mgr, event_publisher=workforce_publisher,
    ))
    container.register("project_update_handler", UpdateProjectHandler(
        repo=project_repo, tx_manager=tx_mgr, event_publisher=workforce_publisher,
    ))
    container.register("assign_member_handler", AssignMemberToProjectHandler(
        repo=project_repo, tx_manager=tx_mgr, event_publisher=workforce_publisher,
    ))
    container.register("assign_skill_handler", AssignSkillToMemberHandler(
        repo=member_repo, tx_manager=tx_mgr, event_publisher=workforce_publisher,
    ))
    container.register("assign_memory_handler", AssignMemoryToMemberHandler(
        repo=member_repo, tx_manager=tx_mgr, event_publisher=workforce_publisher,
    ))

    # -- Read-side: mock executors returning stored data --
    from unittest.mock import AsyncMock
    from types import SimpleNamespace

    memory_list_exec = AsyncMock()
    memory_list_exec.execute = AsyncMock(side_effect=lambda *a, **kw: _mock_memory_list(memory_node_repo))
    container.register("memory_list_executor", memory_list_exec)

    memory_detail_exec = AsyncMock()
    memory_detail_exec.execute = AsyncMock(side_effect=lambda *a, **kw: _mock_memory_detail(memory_node_repo))
    container.register("memory_detail_executor", memory_detail_exec)

    memory_search_exec = AsyncMock()
    memory_search_exec.execute = AsyncMock(return_value=[])
    container.register("memory_search_executor", memory_search_exec)

    skill_list_exec = AsyncMock()
    skill_list_exec.execute = AsyncMock(side_effect=lambda *a, **kw: _mock_skill_list(skill_repo))
    container.register("skill_list_executor", skill_list_exec)

    skill_detail_exec = AsyncMock()
    skill_detail_exec.execute = AsyncMock(side_effect=lambda *a, **kw: _mock_skill_detail(skill_repo))
    container.register("skill_detail_executor", skill_detail_exec)

    members_exec = AsyncMock()
    members_exec.execute = AsyncMock(return_value=[])
    container.register("members_executor", members_exec)

    departments_exec = AsyncMock()
    departments_exec.execute = AsyncMock(return_value=[])
    container.register("departments_executor", departments_exec)

    projects_exec = AsyncMock()
    projects_exec.execute = AsyncMock(return_value=[])
    container.register("projects_executor", projects_exec)

    member_repo_mock = AsyncMock()
    member_repo_mock.get_by_id = AsyncMock(side_effect=member_repo.get_by_id)
    container.register("member_repo", member_repo_mock)

    project_repo_mock = AsyncMock()
    project_repo_mock.get_by_id = AsyncMock(side_effect=project_repo.get_by_id)
    container.register("project_repo", project_repo_mock)

    infra = {
        "memory_node_repo": memory_node_repo,
        "memory_edge_repo": memory_edge_repo,
        "skill_repo": skill_repo,
        "member_repo": member_repo,
        "dept_repo": dept_repo,
        "project_repo": project_repo,
        "memory_publisher": memory_publisher,
        "skill_publisher": skill_publisher,
        "workforce_publisher": workforce_publisher,
    }
    return container, infra


# ---------------------------------------------------------------------------
# Read-side helpers (return simple mock data for list/detail queries)
# ---------------------------------------------------------------------------


def _mock_memory_list(repo: InMemoryRepo):
    results = []
    for node in repo.all():
        results.append(SimpleNamespace(
            id=node.id, tier=node.tier.value, title=node.title,
            lifecycle_state=node.lifecycle.value,
            confidence_value=float(node.confidence.value),
            scope_kind=node.scope.kind.value, tags=node.content.tags,
            current_version=node.current_version, created_at=node.created_at,
        ))
    return results


def _mock_memory_detail(repo: InMemoryRepo):
    from unittest.mock import MagicMock
    nodes = repo.all()
    if not nodes:
        return MagicMock(node=None, versions=[])
    node = nodes[0]
    mock = MagicMock()
    mock.id = node.id
    mock.tier = MagicMock(value=node.tier.value)
    mock.tier.value = node.tier.value
    mock.content = MagicMock(title=node.title, statement=node.content.statement)
    mock.lifecycle_state = MagicMock(value=node.lifecycle.value)
    mock.lifecycle_state.value = node.lifecycle.value
    mock.confidence = MagicMock(value=float(node.confidence.value))
    mock.created_at = node.created_at
    return MagicMock(
        node=mock,
        versions=[{"version": v.version_no, "diff": v.diff} for v in node.versions],
    )


def _mock_skill_list(repo: InMemoryRepo):
    from types import SimpleNamespace
    results = []
    for skill in repo.all():
        results.append(SimpleNamespace(
            id=skill.id, name=skill.name, version=str(skill.version),
            description=skill.manifest.description,
            domain=skill.manifest.domain,
            status=skill.status.value,
            circuit_state=skill.health.circuit_state.value,
            capability_tags=skill.manifest.capability_tags,
            created_at=skill.created_at,
        ))
    return results


def _mock_skill_detail(repo: InMemoryRepo):
    from unittest.mock import MagicMock
    skills = repo.all()
    if not skills:
        return MagicMock()
    s = skills[0]
    mock = MagicMock()
    mock.id = s.id
    mock.name = s.name
    mock.version = str(s.version)
    mock.description = s.manifest.description
    mock.domain = s.manifest.domain
    mock.status = s.status.value
    mock.circuit_state = s.health.circuit_state.value
    mock.inputs = s.manifest.inputs
    mock.outputs = s.manifest.outputs
    mock.preconditions = s.manifest.preconditions
    mock.side_effects = [se.__dict__ for se in s.manifest.side_effects]
    mock.required_permissions = s.manifest.required_permissions
    mock.capability_tags = s.manifest.capability_tags
    mock.examples = s.manifest.examples
    mock.references = s.manifest.references
    mock.quality_signals = s.manifest.quality_signals
    mock.manifest = {}
    mock.health = {}
    mock.created_at = s.created_at
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_admin_key(monkeypatch):
    """Ensure our admin key is active for every test, even when other
    test modules overwrite the env var in the same pytest session."""
    monkeypatch.setenv("AITEAMOS_ADMIN_API_KEY", E2E_ADMIN_KEY)


@pytest.fixture
def e2e_env():
    container, infra = _build_e2e_container()
    app = create_app(container)
    client = TestClient(app)
    return client, infra


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {E2E_ADMIN_KEY}"}


# ===========================================================================
# M1 Verification: Memory CRUD + Version History
# ===========================================================================


class TestM1MemoryLifecycle:
    """验证标准: 可创建/编辑/分配 Memory，Memory 有版本历史"""

    def test_create_memory(self, e2e_env):
        client, infra = e2e_env
        resp = client.post("/api/v1/memories", json={
            "tier": "facts", "scope_kind": "global",
            "title": "Project Convention",
            "statement": "Always use type hints",
            "source_kind": "manual_input",
        }, headers=_h())
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "created"
        memory_id = data["id"]

        # Verify aggregate stored in-memory
        node = infra["memory_node_repo"].all()[0]
        assert str(node.id) == memory_id
        assert node.title == "Project Convention"
        assert node.content.statement == "Always use type hints"

    def test_create_then_update_memory(self, e2e_env):
        client, infra = e2e_env
        # Create
        resp = client.post("/api/v1/memories", json={
            "tier": "patterns", "scope_kind": "global",
            "title": "Pattern A",
            "statement": "Use factory pattern",
            "source_kind": "manual_input",
        }, headers=_h())
        assert resp.status_code == 201
        memory_id = resp.json()["id"]

        # Update
        resp = client.put(f"/api/v1/memories/{memory_id}", json={
            "statement": "Use abstract factory pattern",
            "reason": "More specific",
        }, headers=_h())
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

        # Verify version history exists on aggregate
        node = infra["memory_node_repo"].all()[0]
        assert node.current_version == 2
        assert len(node.versions) == 1
        assert node.versions[0].reason == "More specific"

    def test_create_memory_emits_event(self, e2e_env):
        client, infra = e2e_env
        resp = client.post("/api/v1/memories", json={
            "tier": "facts", "scope_kind": "global",
            "title": "Event Test",
            "statement": "Events should be emitted",
            "source_kind": "manual_input",
        }, headers=_h())
        assert resp.status_code == 201

        pub = infra["memory_publisher"]
        assert len(pub.events) >= 1
        event_types = [e.event_type for e in pub.events]
        assert "knowledge.memory_node.created" in event_types

    def test_memory_lifecycle_change(self, e2e_env):
        client, infra = e2e_env
        # Create
        resp = client.post("/api/v1/memories", json={
            "tier": "facts", "scope_kind": "global",
            "title": "Lifecycle Test",
            "statement": "Will be deprecated",
            "source_kind": "manual_input",
        }, headers=_h())
        memory_id = resp.json()["id"]

        # Deprecate
        resp = client.patch(f"/api/v1/memories/{memory_id}/lifecycle", json={
            "new_state": "deprecated",
        }, headers=_h())
        assert resp.status_code == 200

        node = infra["memory_node_repo"].all()[0]
        assert node.lifecycle.value == "deprecated"

    def test_memory_version_append(self, e2e_env):
        client, infra = e2e_env
        resp = client.post("/api/v1/memories", json={
            "tier": "patterns", "scope_kind": "global",
            "title": "Version Test",
            "statement": "Initial statement",
            "source_kind": "manual_input",
        }, headers=_h())
        memory_id = resp.json()["id"]

        # Append version
        resp = client.post(f"/api/v1/memories/{memory_id}/versions", json={
            "diff": {"field": "confidence"},
            "reason": "Metadata enrichment",
        }, headers=_h())
        assert resp.status_code == 201

        node = infra["memory_node_repo"].all()[0]
        assert node.current_version >= 2

    def test_memory_edge_creation(self, e2e_env):
        client, infra = e2e_env
        src_id = str(uuid4())
        tgt_id = str(uuid4())
        resp = client.post("/api/v1/memories/edges", json={
            "source_id": src_id,
            "target_id": tgt_id,
            "relation_type": "causal",
        }, headers=_h())
        assert resp.status_code == 201
        assert len(infra["memory_edge_repo"].all()) == 1


# ===========================================================================
# M1 Verification: Skill Register + Assign
# ===========================================================================


class TestM1SkillLifecycle:
    """验证标准: 可注册 Skill 并分配给 AI Member"""

    def test_register_skill(self, e2e_env):
        client, infra = e2e_env
        resp = client.post("/api/v1/skills", json={
            "name": "code-review",
            "version": "1.0.0",
            "description": "Review code for correctness and maintainability",
            "domain": "code-review",
            "inputs": ["source tree", "review scope"],
            "outputs": ["review findings"],
            "capability_tags": ["review", "code"],
        }, headers=_h())
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "registered"

        skill = infra["skill_repo"].all()[0]
        assert skill.name == "code-review"
        assert skill.status.value == "draft"

    def test_register_and_publish_skill(self, e2e_env):
        client, infra = e2e_env
        # Register
        resp = client.post("/api/v1/skills", json={
            "name": "deploy-skill",
            "version": "0.1.0",
            "domain": "deployment",
        }, headers=_h())
        skill_id = resp.json()["id"]

        # Publish
        resp = client.patch(f"/api/v1/skills/{skill_id}/publish", headers=_h())
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

        skill = infra["skill_repo"].all()[0]
        assert skill.status.value == "published"

    def test_register_and_deprecate_skill(self, e2e_env):
        client, infra = e2e_env
        resp = client.post("/api/v1/skills", json={
            "name": "old-skill",
            "version": "2.0.0",
            "domain": "legacy",
        }, headers=_h())
        skill_id = resp.json()["id"]

        resp = client.patch(f"/api/v1/skills/{skill_id}/deprecate", json={
            "reason": "Replaced by new-skill",
        }, headers=_h())
        assert resp.status_code == 200
        assert resp.json()["status"] == "deprecated"

    def test_skill_events_emitted(self, e2e_env):
        client, infra = e2e_env
        resp = client.post("/api/v1/skills", json={
            "name": "event-test-skill",
            "version": "1.0.0",
            "domain": "test",
        }, headers=_h())
        assert resp.status_code == 201

        pub = infra["skill_publisher"]
        event_types = [e.event_type for e in pub.events]
        assert "capability.skill.registered" in event_types


# ===========================================================================
# M1 Verification: Member / Department / Project + Mappings
# ===========================================================================


class TestM1WorkforceMappings:
    """验证标准: 可创建 Member、Department、Project 并建立映射关系"""

    def test_create_department(self, e2e_env):
        client, infra = e2e_env
        resp = client.post("/api/v1/departments", json={
            "name": "Engineering",
        }, headers=_h())
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "created"

        dept = infra["dept_repo"].all()[0]
        assert dept.name == "Engineering"

    def test_create_member(self, e2e_env):
        client, infra = e2e_env
        dept_id = str(uuid4())
        resp = client.post("/api/v1/members", json={
            "kind": "ai",
            "department_id": dept_id,
            "display_name": "CodeBot",
            "concurrency_limit": 3,
        }, headers=_h())
        assert resp.status_code == 201
        assert resp.json()["status"] == "created"

        member = infra["member_repo"].all()[0]
        assert member.profile.display_name == "CodeBot"
        assert member.concurrency_limit == 3

    def test_create_project_with_repos(self, e2e_env):
        """验证标准: Project 可关联 Repository"""
        client, infra = e2e_env
        dept_id = str(uuid4())
        resp = client.post("/api/v1/projects", json={
            "name": "Alpha",
            "description": "Core platform",
            "department_id": dept_id,
            "repository_refs": ["github.com/org/alpha"],
        }, headers=_h())
        assert resp.status_code == 201

        project = infra["project_repo"].all()[0]
        assert project.name == "Alpha"
        assert "github.com/org/alpha" in project.repository_refs

    def test_assign_member_to_project(self, e2e_env):
        """验证标准: Project 可关联成员"""
        client, infra = e2e_env
        dept_id = str(uuid4())

        # Create project (seed in-memory for lock_for_update)
        resp = client.post("/api/v1/projects", json={
            "name": "Beta", "department_id": dept_id,
        }, headers=_h())
        project_id = resp.json()["id"]

        # Assign member
        member_id = str(uuid4())
        resp = client.post(f"/api/v1/projects/{project_id}/members", json={
            "member_id": member_id,
        }, headers=_h())
        assert resp.status_code == 201
        assert resp.json()["status"] == "member_assigned"

        project = infra["project_repo"].all()[0]
        assert UUID(member_id) in project.member_ids

    def test_assign_skill_to_member(self, e2e_env):
        """验证标准: 可分配 Skill 给 Member"""
        client, infra = e2e_env
        dept_id = str(uuid4())

        # Create member (seed in-memory)
        resp = client.post("/api/v1/members", json={
            "kind": "ai", "department_id": dept_id,
            "display_name": "SkillBot",
        }, headers=_h())
        member_id = resp.json()["id"]

        # Assign skill
        skill_id = str(uuid4())
        resp = client.post(f"/api/v1/members/{member_id}/skills", json={
            "skill_id": skill_id,
        }, headers=_h())
        assert resp.status_code == 201
        assert resp.json()["status"] == "skill_assigned"

        member = infra["member_repo"].all()[0]
        assert UUID(skill_id) in member.base_skill_set

    def test_assign_memory_to_member(self, e2e_env):
        """验证标准: 可分配 Memory 给 Member"""
        client, infra = e2e_env
        dept_id = str(uuid4())

        # Create member
        resp = client.post("/api/v1/members", json={
            "kind": "ai", "department_id": dept_id,
            "display_name": "MemBot",
        }, headers=_h())
        member_id = resp.json()["id"]

        # Assign memory
        memory_id = str(uuid4())
        resp = client.post(f"/api/v1/members/{member_id}/memories", json={
            "memory_id": memory_id,
        }, headers=_h())
        assert resp.status_code == 201
        assert resp.json()["status"] == "memory_assigned"

        member = infra["member_repo"].all()[0]
        assert UUID(memory_id) in member.assigned_memories


# ===========================================================================
# M1 Verification: Cross-BC Event Communication
# ===========================================================================


class TestM1CrossBCEvents:
    """验证标准: 所有跨上下文通信走领域事件, Outbox 正确记录"""

    def test_all_writes_emit_domain_events(self, e2e_env):
        """Every write operation should emit at least one domain event."""
        client, infra = e2e_env
        dept_id = str(uuid4())

        # 1. Create Memory
        resp = client.post("/api/v1/memories", json={
            "tier": "facts", "scope_kind": "global",
            "title": "Event Verification",
            "statement": "All writes emit events",
            "source_kind": "manual_input",
        }, headers=_h())
        assert resp.status_code == 201

        # 2. Register Skill
        resp = client.post("/api/v1/skills", json={
            "name": "event-skill",
            "version": "1.0.0",
            "domain": "eventing",
        }, headers=_h())
        assert resp.status_code == 201

        # 3. Create Department
        resp = client.post("/api/v1/departments", json={
            "name": "EventDept",
        }, headers=_h())
        assert resp.status_code == 201

        # 4. Create Member
        resp = client.post("/api/v1/members", json={
            "kind": "ai", "department_id": dept_id,
            "display_name": "EventBot",
        }, headers=_h())
        assert resp.status_code == 201

        # 5. Create Project
        resp = client.post("/api/v1/projects", json={
            "name": "EventProject", "department_id": dept_id,
        }, headers=_h())
        assert resp.status_code == 201

        # Verify events across all BCs
        memory_events = [e.event_type for e in infra["memory_publisher"].events]
        skill_events = [e.event_type for e in infra["skill_publisher"].events]
        workforce_events = [e.event_type for e in infra["workforce_publisher"].events]

        assert "knowledge.memory_node.created" in memory_events
        assert "capability.skill.registered" in skill_events
        assert "workforce.department.created" in workforce_events
        assert "workforce.member.created" in workforce_events
        assert "workforce.project.created" in workforce_events

    def test_events_have_versioning(self, e2e_env):
        """验证标准: 事件继承 VersionedDomainEvent"""
        client, infra = e2e_env
        resp = client.post("/api/v1/memories", json={
            "tier": "facts", "scope_kind": "global",
            "title": "Versioned Event Test",
            "statement": "Events should have event_version",
            "source_kind": "manual_input",
        }, headers=_h())
        assert resp.status_code == 201

        event = infra["memory_publisher"].events[0]
        assert hasattr(event, "event_version")
        assert event.event_version == 1
        assert hasattr(event, "correlation_id")
        assert hasattr(event, "timestamp")

    def test_workforce_events_have_partition_keys(self, e2e_env):
        """验证标准: Outbox 事件有 partition_key"""
        client, infra = e2e_env
        resp = client.post("/api/v1/departments", json={
            "name": "PartitionTest",
        }, headers=_h())
        assert resp.status_code == 201

        pub = infra["workforce_publisher"]
        assert len(pub.partitions) >= 1
        # Partition key should be the department ID
        assert len(pub.partitions[0]) == 36  # UUID string length


# ===========================================================================
# M1 Full E2E Story: Department → Member → Skill → Project → Assign
# ===========================================================================


class TestM1FullE2EStory:
    """End-to-end story validating the complete M1 delivery."""

    def test_full_team_setup_story(self, e2e_env):
        """
        Complete story:
        1. Create Department
        2. Create Memory (team knowledge)
        3. Register Skill (team capability)
        4. Create AI Member in the Department
        5. Assign Skill to Member
        6. Assign Memory to Member
        7. Create Project with Repository refs
        8. Assign Member to Project
        """
        client, infra = e2e_env

        # Step 1: Department
        resp = client.post("/api/v1/departments", json={
            "name": "Platform Engineering",
        }, headers=_h())
        assert resp.status_code == 201
        dept_id = resp.json()["id"]

        # Step 2: Memory
        resp = client.post("/api/v1/memories", json={
            "tier": "patterns", "scope_kind": "global",
            "title": "Architecture Decision",
            "statement": "Use CQRS for read/write separation",
            "source_kind": "manual_input",
            "tags": ["architecture", "cqrs"],
        }, headers=_h())
        assert resp.status_code == 201
        memory_id = resp.json()["id"]

        # Step 3: Skill
        resp = client.post("/api/v1/skills", json={
            "name": "architecture-review",
            "version": "1.0.0",
            "description": "Review architecture decisions and boundaries",
            "domain": "architecture",
            "inputs": ["architecture proposal", "repo constraints"],
            "outputs": ["review findings", "risk notes"],
            "capability_tags": ["architecture", "review"],
        }, headers=_h())
        assert resp.status_code == 201
        skill_id = resp.json()["id"]

        # Step 4: Member
        resp = client.post("/api/v1/members", json={
            "kind": "ai",
            "department_id": dept_id,
            "display_name": "ArchBot",
            "concurrency_limit": 2,
        }, headers=_h())
        assert resp.status_code == 201
        member_id = resp.json()["id"]

        # Step 5: Assign Skill to Member
        resp = client.post(f"/api/v1/members/{member_id}/skills", json={
            "skill_id": skill_id,
        }, headers=_h())
        assert resp.status_code == 201

        # Step 6: Assign Memory to Member
        resp = client.post(f"/api/v1/members/{member_id}/memories", json={
            "memory_id": memory_id,
        }, headers=_h())
        assert resp.status_code == 201

        # Step 7: Project with repos
        resp = client.post("/api/v1/projects", json={
            "name": "Platform Core",
            "description": "Core platform services",
            "department_id": dept_id,
            "repository_refs": [
                "github.com/org/platform-core",
                "github.com/org/platform-api",
            ],
        }, headers=_h())
        assert resp.status_code == 201
        project_id = resp.json()["id"]

        # Step 8: Assign Member to Project
        resp = client.post(f"/api/v1/projects/{project_id}/members", json={
            "member_id": member_id,
        }, headers=_h())
        assert resp.status_code == 201

        # ---- Final Verification ----

        # Member has skill and memory assigned
        member = list(infra["member_repo"].all())[0]
        assert UUID(skill_id) in member.base_skill_set
        assert UUID(memory_id) in member.assigned_memories

        # Project has member and repository refs
        project = list(infra["project_repo"].all())[0]
        assert UUID(member_id) in project.member_ids
        assert len(project.repository_refs) == 2

        # All BCs emitted events
        total_events = (
            len(infra["memory_publisher"].events)
            + len(infra["skill_publisher"].events)
            + len(infra["workforce_publisher"].events)
        )
        assert total_events >= 7  # At least one per write operation

        # Department exists with correct name
        dept = list(infra["dept_repo"].all())[0]
        assert dept.name == "Platform Engineering"


# ===========================================================================
# M1 Verification: OpenAPI Schema
# ===========================================================================


class TestM1OpenAPI:
    """验证标准: API 文档自动生成"""

    def test_openapi_schema_has_all_bc_paths(self, e2e_env):
        client, _ = e2e_env
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        paths = list(schema["paths"].keys())

        # Knowledge BC
        assert "/api/v1/memories" in paths
        # Capability BC
        assert "/api/v1/skills" in paths
        # Workforce BC
        assert "/api/v1/members" in paths
        assert "/api/v1/departments" in paths
        assert "/api/v1/projects" in paths

    def test_openapi_schema_has_write_operations(self, e2e_env):
        client, _ = e2e_env
        schema = client.get("/openapi.json").json()
        paths = schema["paths"]

        # Memory write operations
        assert "post" in paths["/api/v1/memories"]
        assert "patch" in paths["/api/v1/memories/{memory_id}/lifecycle"]

        # Skill write operations
        assert "post" in paths["/api/v1/skills"]
        assert "patch" in paths["/api/v1/skills/{skill_id}/publish"]

        # Workforce write operations
        assert "post" in paths["/api/v1/members"]
        assert "post" in paths["/api/v1/departments"]
        assert "post" in paths["/api/v1/projects"]

    def test_docs_endpoint_accessible(self, e2e_env):
        client, _ = e2e_env
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_health_endpoint(self, e2e_env):
        client, _ = e2e_env
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "database" in data

    def test_openapi_info_section(self, e2e_env):
        client, _ = e2e_env
        schema = client.get("/openapi.json").json()
        assert schema["info"]["title"] == "AITeamOS API"
        assert "version" in schema["info"]
