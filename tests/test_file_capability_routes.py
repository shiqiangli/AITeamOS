from fastapi.testclient import TestClient

from aiteamos_api.main import create_app


def test_capability_registry_groups_built_in_and_connector_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    payload = response.json()

    capabilities = payload["capabilities"]
    ids = {item["id"] for item in capabilities}
    assert "list_employees" in ids
    assert "create_ticket" in ids
    assert "inspect_code_repository" in ids
    assert "mcp:github:repo.search" in ids
    assert "mcp:ci-harness:validation.run" in ids

    list_employees = next(item for item in capabilities if item["id"] == "list_employees")
    assert list_employees["kind"] == "tool"
    assert list_employees["source_kind"] == "built_in"
    assert list_employees["status"] == "ready"
    assert list_employees["deep_link"] == "#/employees"

    github_tool = next(item for item in capabilities if item["id"] == "mcp:github:repo.search")
    assert github_tool["kind"] == "tool"
    assert github_tool["source_kind"] == "mcp_server"
    assert github_tool["connector_id"] == "github"
    assert "repo:read" in github_tool["permissions"]

    status = payload["status"]
    assert status["capability_count"] == len(capabilities)
    assert status["tool_count"] == len(capabilities)
    assert status["built_in_tool_count"] >= 14
    assert status["mcp_tool_count"] >= 6
    assert status["native_api_tool_count"] == 0
    assert status["cli_tool_count"] == 0
    assert status["ci_tool_count"] == 0
    assert payload["model"]["tool"].startswith("executable action normalized")

    built_in_assets = client.get("/api/v1/assets/capabilities/built-in-tools")
    assert built_in_assets.status_code == 200
    assert "list_employees" in {item["id"] for item in built_in_assets.json()}
    assert all(item["metadata"]["asset_type"] == "built-in-tools" for item in built_in_assets.json())

    mcp_assets = client.get("/api/v1/assets/capabilities/mcp-tools")
    assert mcp_assets.status_code == 200
    assert "mcp:github:repo.search" in {item["id"] for item in mcp_assets.json()}
    assert all(item["metadata"]["asset_type"] == "mcp-tools" for item in mcp_assets.json())

    assert client.get("/api/v1/assets/capabilities/tools").status_code == 404


def test_capability_status_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/api/v1/capabilities/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["capability_count"] > 0
    assert payload["ready_count"] > 0
    assert payload["saved_paths"]["registry"] == ".aiteamos/tool_connectors.json"
