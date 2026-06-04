from __future__ import annotations

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app


def test_system_status_reports_secret_health_without_settings_compat_route(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    client = TestClient(create_app())

    status = client.get("/api/v1/system-status")
    assert status.status_code == 200
    payload = status.json()
    assert "secrets" in payload
    assert "items" not in payload

    secrets = {item["id"]: item for item in payload["secrets"]}
    assert secrets["openai_api_key"]["configured"] is True
    assert secrets["deepseek_api_key"]["configured"] is False
