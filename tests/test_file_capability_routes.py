from fastapi.testclient import TestClient

from aiteamos_api.main import create_app
from aiteamos_api.read.chat_governance_service import ChatGovernanceService
from aiteamos_api.read.capability_service import capability_operation_policy_for_command, capability_required_approval_for_operation


def test_capability_registry_groups_kernel_commands_and_connector_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    payload = response.json()

    capabilities = payload["capabilities"]
    ids = {item["id"] for item in capabilities}
    assert "employees.manage" in ids
    assert "tickets.manage" in ids
    assert "repositories.inspect" in ids
    assert "kernel.permissions" in ids
    assert "universal_agent.search_memory" in ids
    assert "universal_agent.search_tickets" in ids
    assert "mcp:github:repo.search" in ids
    assert "mcp:ci-harness:validation.run" in ids

    employees_manage = next(item for item in capabilities if item["id"] == "employees.manage")
    assert employees_manage["kind"] == "tool"
    assert employees_manage["source_kind"] == "kernel_command"
    assert employees_manage["status"] == "ready"
    assert employees_manage["access"] == "destructive"
    assert employees_manage["destructive"] is True
    assert "destructive_tool_call" in employees_manage["required_approval"]
    assert employees_manage["provider"] == "aiteamos_kernel"
    assert employees_manage["schema"]["properties"]["operation"]["type"] == "string"
    assert employees_manage["deep_link"] == "#/employees"
    employee_operations = employees_manage["operation_policies"]
    assert employee_operations["list"]["access"] == "read"
    assert employee_operations["list"]["required_approval"] == []
    assert employee_operations["create"]["access"] == "write"
    assert employee_operations["create"]["required_approval"] == []
    assert employee_operations["delete"]["destructive"] is True
    assert employee_operations["delete"]["required_approval"] == ["destructive_tool_call"]

    github_tool = next(item for item in capabilities if item["id"] == "mcp:github:repo.search")
    assert github_tool["kind"] == "tool"
    assert github_tool["source_kind"] == "mcp_server"
    assert github_tool["connector_id"] == "github"
    assert github_tool["provider"] == "github"
    assert github_tool["access"] == "read"
    assert github_tool["output_asset_policy"]["record_tool_call"] is True
    assert "repo:read" in github_tool["permissions"]

    terminal_run = next(item for item in capabilities if item["id"] == "terminal.run")
    assert terminal_run["access"] == "destructive"
    assert {"terminal:run", "destructive_tool_call"}.issubset(set(terminal_run["required_approval"]))
    assert "tool_call" in terminal_run["output_asset_policy"]["candidate_asset_types"]
    terminal_operation = terminal_run["operation_policies"]["run"]
    assert terminal_operation["command_id"] == "terminal.run:run"
    assert terminal_operation["access"] == "destructive"
    assert terminal_operation["required_approval"] == ["destructive_tool_call", "terminal:run"]

    assets_manage = next(item for item in capabilities if item["id"] == "assets.manage")
    assert assets_manage["operation_policies"]["list_skills"]["access"] == "read"
    assert assets_manage["operation_policies"]["create_skill"]["access"] == "write"
    assert assets_manage["operation_policies"]["delete_skill"]["destructive"] is True
    assert assets_manage["operation_policies"]["delete_skill"]["required_approval"] == ["destructive_tool_call"]

    memory_tool = next(item for item in capabilities if item["id"] == "universal_agent.search_memory")
    assert memory_tool["kind"] == "tool"
    assert memory_tool["source_kind"] == "native_api"
    assert memory_tool["provider"] == "aiteamos_langgraph"
    assert memory_tool["access"] == "read"
    assert memory_tool["destructive"] is False
    assert memory_tool["required_approval"] == []
    assert memory_tool["schema"]["properties"]["query"]["type"] == "string"
    assert "tool_call" in memory_tool["output_asset_policy"]["candidate_asset_types"]

    status = payload["status"]
    assert status["capability_count"] == len(capabilities)
    assert status["tool_count"] == len(capabilities)
    assert status["kernel_command_count"] >= 8
    assert status["mcp_tool_count"] >= 6
    assert status["native_api_tool_count"] >= 6
    assert status["cli_tool_count"] == 0
    assert status["ci_tool_count"] == 0
    assert payload["model"]["tool"].startswith("executable action exposed through Kernel commands")

    kernel_assets = client.get("/api/v1/assets/capabilities/kernel-commands")
    assert kernel_assets.status_code == 200
    assert "employees.manage" in {item["id"] for item in kernel_assets.json()}
    assert "kernel.permissions" in {item["id"] for item in kernel_assets.json()}
    assert all(item["metadata"]["asset_type"] == "kernel-commands" for item in kernel_assets.json())

    mcp_assets = client.get("/api/v1/assets/capabilities/mcp-tools")
    assert mcp_assets.status_code == 200
    assert "mcp:github:repo.search" in {item["id"] for item in mcp_assets.json()}
    assert all(item["metadata"]["asset_type"] == "mcp-tools" for item in mcp_assets.json())

    assert client.get("/api/v1/assets/capabilities/tools").status_code == 404

    assert capability_operation_policy_for_command("employees.manage:list")["access"] == "read"
    assert capability_required_approval_for_operation("employees.manage", "create") == []
    assert capability_required_approval_for_operation("employees.manage", "delete") == ["destructive_tool_call"]
    assert capability_required_approval_for_operation("terminal.run", "run") == ["destructive_tool_call", "terminal:run"]


def test_capability_status_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/api/v1/capabilities/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["capability_count"] > 0
    assert payload["ready_count"] > 0
    assert payload["saved_paths"]["registry"] == ".aiteamos/tool_connectors.json"


def test_chat_governance_approval_policy_uses_operation_level_capability_policy(tmp_path):
    service = ChatGovernanceService(workspace_dir=tmp_path / ".aiteamos")

    list_policy = service._approval_policy("list_employees")
    delete_policy = service._approval_policy("delete_employee")
    terminal_policy = service._approval_policy("terminal_run")

    assert "destructive_tool_call" not in list_policy["require_approval_for"]
    assert "destructive_tool_call" in delete_policy["require_approval_for"]
    assert {"destructive_tool_call", "terminal:run"}.issubset(set(terminal_policy["require_approval_for"]))
