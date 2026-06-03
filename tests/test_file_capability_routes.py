from fastapi.testclient import TestClient

from aiteamos_api.main import create_app


def test_capability_registry_groups_local_tools_mcp_and_executors(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    payload = response.json()

    capabilities = payload["capabilities"]
    ids = {item["id"] for item in capabilities}
    assert "list_members" in ids
    assert "create_work_item" in ids
    assert "inspect_code_repository" in ids
    assert "mcp:plane:work_items.create" in ids
    assert "mcp:plane:knowledge.docs.read" in ids
    assert "executor:codex" in ids

    list_members = next(item for item in capabilities if item["id"] == "list_members")
    assert list_members["kind"] == "local_tool"
    assert list_members["status"] == "ready"
    assert list_members["deep_link"] == "#/members"

    plane_capability = next(item for item in capabilities if item["id"] == "mcp:plane:work_items.create")
    assert plane_capability["kind"] == "mcp_capability"
    assert plane_capability["connector_id"] == "plane"
    assert "work_items:write" in plane_capability["permissions"]

    status = payload["status"]
    assert status["capability_count"] == len(capabilities)
    assert status["local_tool_count"] >= 14
    assert status["mcp_capability_count"] >= 9
    assert status["agent_executor_count"] == 4
    assert payload["model"]["tool"].startswith("deterministic executable action")


def test_capability_status_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/api/v1/capabilities/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["capability_count"] > 0
    assert payload["ready_count"] > 0
    assert payload["saved_paths"]["registry"] == ".aiteamos/mcp_connectors.json"
