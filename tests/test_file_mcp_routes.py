import json

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app
from aiteamos_api.read import mcp_service


def test_mcp_connector_registry_is_file_backed(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/api/v1/mcp/connectors")
    assert response.status_code == 200
    connectors = response.json()
    ids = {connector["id"] for connector in connectors}
    assert {"plane", "filesystem", "github", "ci-harness"}.issubset(ids)
    assert "redmine" not in ids
    plane = next(connector for connector in connectors if connector["id"] == "plane")
    assert plane["transport"] == "rest"
    assert "work_items.comment" in plane["capabilities"]
    assert "knowledge.docs.read" in plane["capabilities"]
    assert next(connector for connector in connectors if connector["id"] == "filesystem")["configured"] is True

    registry_file = tmp_path / ".aiteamos" / "mcp_connectors.json"
    assert registry_file.exists()

    updated = client.put(
        "/api/v1/mcp/connectors/plane",
        json={"enabled": True, "configured": True, "status": "ready", "server": {"api_token": "secret"}},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "ready"
    assert updated.json()["server"]["api_token"] == "***"

    saved = json.loads(registry_file.read_text(encoding="utf-8"))
    plane = next(connector for connector in saved if connector["id"] == "plane")
    assert plane["enabled"] is True
    assert plane["server"]["api_token"] == "***"

    status = client.get("/api/v1/mcp/status")
    assert status.status_code == 200
    assert status.json()["ready_count"] >= 2


def test_plane_connector_settings_and_health(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    client = TestClient(create_app())

    updated = client.put(
        "/api/v1/mcp/connectors/plane/settings",
        json={
            "enabled": True,
            "base_url": "http://localhost:8082/",
            "workspace_slug": "ait",
            "project_id": "AOS",
            "api_token": "plane-token",
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["configured"] is True
    assert payload["api_token_configured"] is True
    assert payload["base_url"] == "http://localhost:8082"
    assert payload["workspace_slug"] == "ait"
    assert payload["project_id"] == "AOS"
    assert "plane-token" not in json.dumps(payload)

    settings_file = tmp_path / ".aiteamos" / "connectors" / "plane.json"
    secrets_file = tmp_path / ".aiteamos" / "secrets.local.json"
    assert json.loads(settings_file.read_text(encoding="utf-8"))["workspace_slug"] == "ait"
    assert json.loads(secrets_file.read_text(encoding="utf-8"))["connector_plane_api_token"] == "plane-token"

    class FakeResponse:
        text = "{}"
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "u-1", "email": "human@example.com", "display_name": "Human"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.requests = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, **kwargs):
            self.requests.append((url, kwargs))
            assert url == "http://localhost:8082/api/v1/users/me/"
            assert kwargs["headers"]["X-API-Key"] == "plane-token"
            return FakeResponse()

    monkeypatch.setattr(mcp_service.httpx, "Client", FakeClient)

    health = client.post("/api/v1/mcp/connectors/plane/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ready"
    assert health.json()["data"]["workspace_slug"] == "ait"
    assert health.json()["data"]["user"]["email"] == "human@example.com"
