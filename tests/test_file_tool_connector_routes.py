import json

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app


def test_tool_connector_registry_is_file_backed(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    registry_file = tmp_path / ".aiteamos" / "tool_connectors.json"
    registry_file.parent.mkdir(parents=True)
    registry_file.write_text(
        json.dumps(
            [
                {"id": "redmine", "name": "Redmine", "status": "planned"},
            ]
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app())

    response = client.get("/api/v1/tool-connectors/connectors")
    assert response.status_code == 200
    connectors = response.json()
    ids = {connector["id"] for connector in connectors}
    assert {"mcp-server", "github", "ci-harness"}.issubset(ids)
    assert "plane" not in ids
    assert "filesystem" not in ids
    assert "redmine" not in ids
    generic = next(connector for connector in connectors if connector["id"] == "mcp-server")
    assert generic["transport"] == "mcp"
    assert generic["required_settings"] == ["server_command_or_url"]
    assert next(connector for connector in connectors if connector["id"] == "github")["configured"] is False

    assert registry_file.exists()

    updated = client.put(
        "/api/v1/tool-connectors/connectors/github",
        json={"enabled": True, "configured": True, "status": "ready", "server": {"api_token": "secret"}},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "ready"
    assert "api_token" not in updated.json()["server"]
    assert "secret" not in json.dumps(updated.json())

    saved = json.loads(registry_file.read_text(encoding="utf-8"))
    github = next(connector for connector in saved if connector["id"] == "github")
    assert github["enabled"] is True
    assert "api_token" not in github["server"]
    assert "secret" not in json.dumps(saved)

    status = client.get("/api/v1/tool-connectors/status")
    assert status.status_code == 200
    assert status.json()["ready_count"] == 1


def test_tool_connector_settings_and_health(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_CI_HARNESS_API_TOKEN", "ci-token")
    client = TestClient(create_app())

    updated = client.put(
        "/api/v1/tool-connectors/connectors/ci-harness/settings",
        json={
            "enabled": True,
            "base_url": "http://localhost:8082/",
            "workspace_slug": "ait",
            "project_id": "AOS",
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["configured"] is True
    assert payload["api_token_configured"] is True
    assert payload["base_url"] == "http://localhost:8082"
    assert payload["workspace_slug"] == "ait"
    assert payload["project_id"] == "AOS"
    assert "ci-token" not in json.dumps(payload)

    settings_file = tmp_path / ".aiteamos" / "connectors" / "ci-harness.json"
    assert json.loads(settings_file.read_text(encoding="utf-8"))["workspace_slug"] == "ait"
    assert not (tmp_path / ".aiteamos" / "secrets.local.json").exists()

    health = client.post("/api/v1/tool-connectors/connectors/ci-harness/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ready"
    assert health.json()["data"]["workspace_slug"] == "ait"
    assert health.json()["data"]["transport"] == "mcp"
