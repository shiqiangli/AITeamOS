from __future__ import annotations

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app


def test_system_status_reports_secret_health_without_settings_compat_route(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("PLANE_API_KEY", raising=False)
    monkeypatch.delenv("AITEAMOS_GRAPHITI_PASSWORD", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    client = TestClient(create_app())

    status = client.get("/api/v1/system-status")
    assert status.status_code == 200
    payload = status.json()
    assert "secrets" in payload
    assert "items" not in payload

    secrets = {item["id"]: item for item in payload["secrets"]}
    assert secrets["openai_api_key"]["configured"] is True
    assert secrets["deepseek_api_key"]["configured"] is False
    assert secrets["plane_api_key"]["env_vars"] == ["PLANE_API_KEY"]
    assert secrets["plane_api_key"]["configured"] is False
    assert secrets["graphiti_neo4j_password"]["configured"] is False

    assert payload["ticket_backend"]["provider"] == "plane"
    assert payload["ticket_backend"]["status"] == "setup_blocked"
    assert "PLANE_API_KEY" in payload["ticket_backend"]["setup_required"]
    assert payload["memory_backend"]["backend"] == "graphiti"
    assert payload["memory_backend"]["status"] == "disabled"
    blockers = {item["id"]: item for item in payload["blockers"]}
    assert blockers["ticket_backend"]["status"] == "setup_blocked"
    assert blockers["memory_asset_graph_backend"]["status"] == "disabled"
