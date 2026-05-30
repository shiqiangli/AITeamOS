"""
API Gateway — Integration Tests (plan.md §1.5 验证标准).

验证标准:
- 所有 API 端点可通过 httpx.AsyncClient 测试调用
- OpenAPI schema 可访问 (/docs)
- 认证拦截未授权请求
"""

import os
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

# Set admin API key before importing app
os.environ["AITEAMOS_ADMIN_API_KEY"] = "test-admin-key-12345"

from aiteamos_api.composition import ServiceContainer
from aiteamos_api.main import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_container_with_mocks() -> ServiceContainer:
    """Build a ServiceContainer with all mock executors/handlers."""
    container = ServiceContainer()

    # --- Memory read mocks ---
    memory_list_exec = AsyncMock()
    memory_list_exec.execute = AsyncMock(return_value=[
        SimpleNamespace(
            id=uuid4(), tier="facts", title="Test Memory",
            lifecycle_state="active", confidence_value=0.8,
            scope_kind="global", tags=["test"], current_version=1,
            created_at=None,
        )
    ])
    container.register("memory_list_executor", memory_list_exec)

    memory_detail_exec = AsyncMock()
    mock_node = MagicMock()
    mock_node.id = uuid4()
    mock_node.tier = MagicMock(value="facts")
    mock_node.tier.value = "facts"
    mock_node.content = MagicMock(title="Test", statement="stmt")
    mock_node.lifecycle_state = MagicMock(value="active")
    mock_node.lifecycle_state.value = "active"
    mock_node.confidence = MagicMock(value=0.8)
    mock_node.created_at = None
    memory_detail_exec.execute = AsyncMock(return_value=MagicMock(
        node=mock_node, versions=[{"version": 1, "diff": {}}],
    ))
    container.register("memory_detail_executor", memory_detail_exec)

    memory_search_exec = AsyncMock()
    memory_search_exec.execute = AsyncMock(return_value=[])
    container.register("memory_search_executor", memory_search_exec)

    # --- Skill read mocks ---
    skill_list_exec = AsyncMock()
    skill_list_exec.execute = AsyncMock(return_value=[
        SimpleNamespace(
            id=uuid4(), name="test-skill", version="1.0.0",
            description="Test skill", domain="compiler",
            status="published", circuit_state="closed",
            capability_tags=["test"],
            created_at=None,
        )
    ])
    container.register("skill_list_executor", skill_list_exec)

    skill_detail_exec = AsyncMock()
    skill_detail_exec.execute = AsyncMock(return_value=MagicMock(
        id=uuid4(), name="test-skill", version="1.0.0",
        description="Test skill", domain="compiler",
        status="published", circuit_state="closed",
        inputs=["source tree"], outputs=["patch"], preconditions=[],
        side_effects=[], required_permissions=[], capability_tags=["test"],
        examples=[], references=[], quality_signals={},
        manifest={}, health={},
        created_at=None,
    ))
    container.register("skill_detail_executor", skill_detail_exec)

    # --- Workforce read mocks ---
    members_exec = AsyncMock()
    members_exec.execute = AsyncMock(return_value=[
        SimpleNamespace(
            id=uuid4(), kind="ai", display_name="Bot",
            department_id=str(uuid4()), concurrency_limit=3,
            is_archived=False, created_at=None,
        )
    ])
    container.register("members_executor", members_exec)

    departments_exec = AsyncMock()
    departments_exec.execute = AsyncMock(return_value=[
        SimpleNamespace(id=uuid4(), name="Eng", leader_member_id=None, created_at=None)
    ])
    container.register("departments_executor", departments_exec)

    projects_exec = AsyncMock()
    projects_exec.execute = AsyncMock(return_value=[
        SimpleNamespace(
            id=uuid4(), name="Alpha", department_id=str(uuid4()),
            status="active", member_count=2, created_at=None,
        )
    ])
    container.register("projects_executor", projects_exec)

    # Detail repos
    mock_member = MagicMock()
    mock_member.id = uuid4()
    mock_member.kind = MagicMock(value="ai")
    mock_member.kind.value = "ai"
    mock_member.profile = MagicMock(display_name="Bot", role="dev")
    mock_member.department_id = uuid4()
    mock_member.concurrency_limit = 3
    mock_member.base_skill_set = [uuid4()]
    mock_member.assigned_memories = [uuid4()]
    mock_member.is_archived = False
    mock_member.created_at = None
    member_repo = AsyncMock()
    member_repo.get_by_id = AsyncMock(return_value=mock_member)
    container.register("member_repo", member_repo)

    mock_project = MagicMock()
    mock_project.id = uuid4()
    mock_project.name = "Alpha"
    mock_project.description = "Test"
    mock_project.department_id = uuid4()
    mock_project.repository_refs = []
    mock_project.harness_config = {}
    mock_project.status = MagicMock(value="active")
    mock_project.status.value = "active"
    mock_project.member_ids = [uuid4()]
    mock_project.created_at = None
    mock_project.archived_at = None
    project_repo = AsyncMock()
    project_repo.get_by_id = AsyncMock(return_value=mock_project)
    container.register("project_repo", project_repo)
    container.register("db", _MemberProfileDb())

    # --- Memory write mocks ---
    mock_memory_result = MagicMock(id=uuid4())
    for name in ["memory_create_handler", "memory_update_handler",
                  "memory_version_handler", "memory_lifecycle_handler",
                  "memory_edge_handler"]:
        handler = AsyncMock()
        handler.handle = AsyncMock(return_value=mock_memory_result)
        container.register(name, handler)

    # --- Skill write mocks ---
    mock_skill_result = MagicMock(id=uuid4())
    for name in ["skill_register_handler", "skill_publish_handler", "skill_deprecate_handler"]:
        handler = AsyncMock()
        handler.handle = AsyncMock(return_value=mock_skill_result)
        container.register(name, handler)

    # --- Workforce write mocks ---
    mock_member_result = MagicMock(id=uuid4())
    mock_dept_result = MagicMock(id=uuid4())
    mock_project_result = MagicMock(id=uuid4())
    container.register("member_create_handler", _make_handler(mock_member_result))
    container.register("department_create_handler", _make_handler(mock_dept_result))
    container.register("project_create_handler", _make_handler(mock_project_result))
    container.register("project_update_handler", _make_handler(mock_project_result))
    container.register("assign_member_handler", _make_handler(mock_project_result))
    container.register("assign_skill_handler", _make_handler(mock_member_result))
    container.register("assign_memory_handler", _make_handler(mock_member_result))

    return container


class _MemberProfileDb:
    async def fetchrow(self, query, *args):
        if "FROM skill" in query:
            return {"id": uuid4()}
        return None

    async def fetch(self, query, *args):
        skill_id = uuid4()
        memory_id = uuid4()
        project_id = uuid4()
        member_id = args[0] if args else uuid4()
        if "FROM member_skill_assignment" in query:
            return [{
                "skill_id": skill_id,
                "is_base": True,
                "assigned_at": "2026-05-02T00:00:00Z",
                "name": "sv-elaboration",
                "version_major": 1,
                "version_minor": 0,
                "version_patch": 0,
                "description": "SystemVerilog elaboration capability",
                "domain": "compiler",
                "status": "published",
                "circuit_state": "closed",
                "capability_tags": ["compiler"],
                "created_at": "2026-05-01T00:00:00Z",
            }]
        if "FROM member_memory_assignment" in query:
            return [{
                "memory_id": memory_id,
                "weight": 1.0,
                "assigned_at": "2026-05-02T00:00:00Z",
                "title": "Elaboration boundary",
                "tier": "principles",
                "lifecycle_state": "active",
                "confidence_value": 0.9,
                "scope_kind": "project",
                "current_version": 1,
                "created_at": "2026-05-01T00:00:00Z",
            }]
        if "FROM project_member" in query:
            return [{
                "id": project_id,
                "name": "Compiler Core",
                "description": None,
                "department_id": uuid4(),
                "status": "active",
                "created_at": "2026-05-01T00:00:00Z",
                "role": "contributor",
                "assigned_at": "2026-05-02T00:00:00Z",
            }]
        if "FROM task" in query:
            return [{
                "id": "TASK-20260502T000000000",
                "title": "Improve parser diagnostics",
                "state": "running",
                "priority": "P1",
                "assigned_member_id": member_id,
                "department_id": uuid4(),
                "retry_count": 0,
                "review_round": 0,
                "created_at": "2026-05-02T00:00:00Z",
                "updated_at": "2026-05-02T01:00:00Z",
            }]
        if "FROM member_activity_event" in query:
            return [{
                "id": uuid4(),
                "event_kind": "task_completed",
                "event_payload": {
                    "label": "Completed parser diagnostics",
                    "target_kind": "task",
                    "target_id": "TASK-20260502T000000000",
                },
                "occurred_at": "2026-05-02T02:00:00Z",
            }]
        return []


def _make_handler(result):
    handler = AsyncMock()
    handler.handle = AsyncMock(return_value=result)
    return handler


@pytest.fixture
def app():
    container = _build_container_with_mocks()
    return create_app(container)


@pytest.fixture
def client(app):
    return TestClient(app)


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-admin-key-12345"}


# ---------------------------------------------------------------------------
# System Endpoints
# ---------------------------------------------------------------------------


class TestSystemEndpoints:
    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "database" in data

    def test_openapi_schema_accessible(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        assert "info" in schema


# ---------------------------------------------------------------------------
# Auth Tests
# ---------------------------------------------------------------------------


class TestAuth:
    def test_no_auth_returns_401(self, client):
        resp = client.get("/api/v1/memories")
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client):
        resp = client.get("/api/v1/memories", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401

    def test_missing_bearer_prefix_returns_401(self, client):
        resp = client.get("/api/v1/memories", headers={"Authorization": "test-admin-key-12345"})
        assert resp.status_code == 401

    def test_valid_token_returns_200(self, client):
        resp = client.get("/api/v1/memories", headers=_auth_headers())
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Memory Read Routes
# ---------------------------------------------------------------------------


class TestMemoryReadRoutes:
    def test_list_memories(self, client):
        resp = client.get("/api/v1/memories", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Test Memory"

    def test_list_memories_with_filters(self, client):
        resp = client.get("/api/v1/memories?tier=facts&limit=10", headers=_auth_headers())
        assert resp.status_code == 200

    def test_get_memory_detail(self, client):
        memory_id = uuid4()
        resp = client.get(f"/api/v1/memories/{memory_id}", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data

    def test_get_memory_versions(self, client):
        memory_id = uuid4()
        resp = client.get(f"/api/v1/memories/{memory_id}/versions", headers=_auth_headers())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_search_memories(self, client):
        resp = client.get("/api/v1/memories/search?keyword=test", headers=_auth_headers())
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Skill Read Routes
# ---------------------------------------------------------------------------


class TestSkillReadRoutes:
    def test_list_skills(self, client):
        resp = client.get("/api/v1/skills", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "test-skill"

    def test_get_skill_detail(self, client):
        skill_id = uuid4()
        resp = client.get(f"/api/v1/skills/{skill_id}", headers=_auth_headers())
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Member / Department / Project Read Routes
# ---------------------------------------------------------------------------


class TestWorkforceReadRoutes:
    def test_list_members(self, client):
        resp = client.get("/api/v1/members", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_member_detail(self, client):
        member_id = uuid4()
        resp = client.get(f"/api/v1/members/{member_id}", headers=_auth_headers())
        assert resp.status_code == 200

    def test_get_member_profile(self, client):
        member_id = uuid4()
        resp = client.get(f"/api/v1/members/{member_id}/profile", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "member" in data
        assert "stats" in data
        assert "activities" in data
        assert data["skills"][0]["name"] == "sv-elaboration"
        assert data["memories"][0]["title"] == "Elaboration boundary"
        assert data["projects"][0]["name"] == "Compiler Core"
        assert data["tasks"][0]["title"] == "Improve parser diagnostics"
        assert data["capability_changes"][0]["kind"] in {"skill_assigned", "memory_assigned"}

    def test_list_departments(self, client):
        resp = client.get("/api/v1/departments", headers=_auth_headers())
        assert resp.status_code == 200

    def test_list_projects(self, client):
        resp = client.get("/api/v1/projects", headers=_auth_headers())
        assert resp.status_code == 200

    def test_get_project_detail(self, client):
        project_id = uuid4()
        resp = client.get(f"/api/v1/projects/{project_id}", headers=_auth_headers())
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Memory Write Routes
# ---------------------------------------------------------------------------


class TestMemoryWriteRoutes:
    def test_create_memory(self, client):
        resp = client.post(
            "/api/v1/memories",
            json={
                "tier": "facts",
                "scope_kind": "global",
                "title": "New Memory",
                "statement": "This is a fact",
                "source_kind": "manual_input",
            },
            headers=_auth_headers(),
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "created"

    def test_update_memory(self, client):
        memory_id = uuid4()
        resp = client.put(
            f"/api/v1/memories/{memory_id}",
            json={"statement": "Updated statement"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    def test_append_version(self, client):
        memory_id = uuid4()
        resp = client.post(
            f"/api/v1/memories/{memory_id}/versions",
            json={"diff": {"added": "content"}, "reason": "improvement"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201

    def test_change_lifecycle(self, client):
        memory_id = uuid4()
        resp = client.patch(
            f"/api/v1/memories/{memory_id}/lifecycle",
            json={"new_state": "deprecated"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200

    def test_create_edge(self, client):
        resp = client.post(
            "/api/v1/memories/edges",
            json={
                "source_id": str(uuid4()),
                "target_id": str(uuid4()),
                "relation_type": "causal",
            },
            headers=_auth_headers(),
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Skill Write Routes
# ---------------------------------------------------------------------------


class TestSkillWriteRoutes:
    def test_register_skill(self, client):
        resp = client.post(
            "/api/v1/skills",
            json={
                "name": "new-skill",
                "version": "1.0.0",
                "description": "A general skill",
                "domain": "compiler",
                "inputs": ["target project"],
                "outputs": ["patch"],
                "capability_tags": ["compiler"],
            },
            headers=_auth_headers(),
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "registered"

    def test_publish_skill(self, client):
        skill_id = uuid4()
        resp = client.patch(
            f"/api/v1/skills/{skill_id}/publish",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

    def test_deprecate_skill(self, client):
        skill_id = uuid4()
        resp = client.patch(
            f"/api/v1/skills/{skill_id}/deprecate",
            json={"reason": "outdated"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deprecated"


# ---------------------------------------------------------------------------
# Member / Project Write Routes
# ---------------------------------------------------------------------------


class TestWorkforceWriteRoutes:
    def test_create_member(self, client):
        resp = client.post(
            "/api/v1/members",
            json={"kind": "ai", "department_id": str(uuid4()), "display_name": "Bot"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "created"

    def test_create_department(self, client):
        resp = client.post(
            "/api/v1/departments",
            json={"name": "Engineering"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201

    def test_create_project(self, client):
        resp = client.post(
            "/api/v1/projects",
            json={"name": "Alpha", "department_id": str(uuid4())},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201

    def test_update_project(self, client):
        project_id = uuid4()
        resp = client.put(
            f"/api/v1/projects/{project_id}",
            json={"name": "Updated Alpha"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200

    def test_assign_member_to_project(self, client):
        project_id = uuid4()
        resp = client.post(
            f"/api/v1/projects/{project_id}/members",
            json={"member_id": str(uuid4())},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201

    def test_assign_skill_to_member(self, client):
        member_id = uuid4()
        resp = client.post(
            f"/api/v1/members/{member_id}/skills",
            json={"skill_id": str(uuid4())},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201

    def test_assign_skill_to_member_by_name(self, client):
        member_id = uuid4()
        resp = client.post(
            f"/api/v1/members/{member_id}/skills",
            json={"skill_name": "sv-elaboration"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201

    def test_assign_memory_to_member(self, client):
        member_id = uuid4()
        resp = client.post(
            f"/api/v1/members/{member_id}/memories",
            json={"memory_id": str(uuid4())},
            headers=_auth_headers(),
        )
        assert resp.status_code == 201
