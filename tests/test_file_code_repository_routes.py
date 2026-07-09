from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app
from aiteamos_api.read import ticket_service


def test_code_repository_registry_tracks_local_and_remote_repositories(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    repo_path = workspace / "repo"
    (repo_path / ".git").mkdir(parents=True)
    (repo_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    client = TestClient(create_app())

    local = client.post(
        "/api/v1/code-repositories",
        json={
            "name": "AITeamOS",
            "provider": "local",
            "location": str(repo_path),
            "default_branch": "main",
            "plane_workspace_slug": "ait",
            "plane_project_id": "aiteamos",
            "description": "Main local checkout.",
        },
    )
    assert local.status_code == 200
    assert local.json()["status"] == "ready"
    assert local.json()["git_detected"] is True
    assert local.json()["current_branch"] == "main"

    remote = client.post(
        "/api/v1/code-repositories",
        json={
            "name": "Shared Lib",
            "provider": "gitea",
            "location": "https://gitea.example.com/team/shared-lib.git",
            "default_branch": "main",
        },
    )
    assert remote.status_code == 200
    assert remote.json()["status"] == "configured"

    listed = client.get("/api/v1/code-repositories")
    assert listed.status_code == 200
    assert {item["name"] for item in listed.json()} == {"AITeamOS", "Shared Lib"}

    status = client.get("/api/v1/code-repositories/status")
    assert status.status_code == 200
    assert status.json()["repository_count"] == 2
    assert status.json()["ready_count"] == 2
    assert status.json()["plane_scope_status"] == "available"
    assert status.json()["plane_scope_candidate_count"] == 1
    assert status.json()["plane_scope_missing_count"] == 1
    assert status.json()["plane_scope_candidates"][0]["repository_name"] == "AITeamOS"
    assert status.json()["plane_scope_candidates"][0]["plane_workspace_slug"] == "ait"
    assert status.json()["plane_scope_candidates"][0]["plane_project_id"] == "aiteamos"
    assert status.json()["plane_scope_setup_action"] == "apply_code_repository_plane_scope_to_ticket_backend"

    ticket_status = client.get("/api/v1/tickets/status")
    assert ticket_status.status_code == 200
    plane_setup = ticket_status.json()["plane_setup"]
    assert plane_setup["code_repository_scope_status"] == "available"
    assert plane_setup["code_repository_scope_candidate_count"] == 1
    assert plane_setup["code_repository_scope_candidates"][0]["repository_name"] == "AITeamOS"
    assert plane_setup["code_repository_scope_candidates"][0]["plane_workspace_slug"] == "ait"
    assert plane_setup["code_repository_scope_candidates"][0]["plane_project_id"] == "aiteamos"
    release_target = ticket_status.json()["release_target"]
    assert release_target["status"] == "blocked"
    assert release_target["ready"] is False
    assert release_target["code_repository_scope_status"] == "available"
    assert "plane_workspace_slug_missing" in release_target["blockers"]
    assert "plane_project_id_missing" in release_target["blockers"]

    updated = client.put(
        f"/api/v1/code-repositories/{remote.json()['id']}",
        json={
            "name": "Shared Library",
            "provider": "github",
            "location": "https://github.com/example/shared-lib.git",
            "default_branch": "trunk",
            "enabled": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "disabled"

    deleted = client.delete(f"/api/v1/code-repositories/{remote.json()['id']}")
    assert deleted.status_code == 204

    registry = json.loads((workspace / ".aiteamos" / "code_repositories.json").read_text(encoding="utf-8"))
    assert [item["name"] for item in registry] == ["AITeamOS"]


def test_code_repository_status_suggests_ticket_backend_plane_scope(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    repo_path = workspace / "repo"
    (repo_path / ".git").mkdir(parents=True)
    (repo_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    backend_path = workspace / ".aiteamos" / "tickets" / "backend.json"
    backend_path.parent.mkdir(parents=True)
    backend_path.write_text(
        json.dumps(
            {
                "mode": "plane",
                "local_file_path": ".aiteamos/tickets/index.json",
                "plane_api_base_url": "https://api.plane.so",
                "plane_web_base_url": "https://app.plane.so",
                "plane_workspace_slug": "ait",
                "plane_project_id": "aiteamos",
                "plane_api_key_env": "PLANE_API_KEY",
            }
        ),
        encoding="utf-8",
    )

    client = TestClient(create_app())

    created = client.post(
        "/api/v1/code-repositories",
        json={
            "name": "AITeamOS",
            "provider": "local",
            "location": str(repo_path),
            "default_branch": "main",
            "description": "Main local checkout.",
        },
    )
    assert created.status_code == 200

    status = client.get("/api/v1/code-repositories/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["plane_scope_status"] == "incomplete"
    assert payload["plane_scope_setup_action"] == "copy_ticket_backend_plane_scope_to_code_repository"
    assert payload["plane_scope_candidate_count"] == 0
    assert payload["plane_scope_missing_count"] == 1
    assert payload["plane_scope_suggestions"][0]["source"] == "ticket_backend"
    assert payload["plane_scope_suggestions"][0]["plane_workspace_slug"] == "ait"
    assert payload["plane_scope_suggestions"][0]["plane_project_id"] == "aiteamos"
    assert payload["plane_scope_suggestions"][0]["settings_path"] == ".aiteamos/tickets/backend.json"

    ticket_status = client.get("/api/v1/tickets/status")
    assert ticket_status.status_code == 200
    plane_setup = ticket_status.json()["plane_setup"]
    assert plane_setup["code_repository_scope_status"] == "incomplete"
    assert plane_setup["code_repository_scope_setup_action"] == "copy_ticket_backend_plane_scope_to_code_repository"
    assert plane_setup["code_repository_scope_suggestions"][0]["source"] == "ticket_backend"


def test_ticket_backend_plane_scope_discovery_requires_plane_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("PLANE_API_KEY", raising=False)

    client = TestClient(create_app())

    response = client.get("/api/v1/tickets/backend/plane-scope/discovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["api_key_env"] == "PLANE_API_KEY"
    assert payload["api_key_configured"] is False
    assert payload["external_calls"] is False
    assert payload["setup_required"] == ["PLANE_API_KEY"]
    assert payload["suggestions"] == []


def test_ticket_backend_plane_scope_discovery_lists_workspace_project_candidates(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("PLANE_API_KEY", "plane-test-key")
    monkeypatch.setenv("AITEAMOS_PLANE_WORKSPACE_SLUG", "ait")
    calls: list[dict] = []

    class FakePlaneResponse:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    class FakePlaneClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, url, headers, json):
            calls.append({"method": method, "url": url, "headers": headers, "json": json})
            if method == "GET" and url == "https://plane.test/api/v1/workspaces/":
                return FakePlaneResponse(200, {"results": [{"slug": "ait", "name": "AITeamOS"}]})
            if method == "GET" and url == "https://plane.test/api/v1/workspaces/ait/projects/":
                return FakePlaneResponse(
                    200,
                    {"results": [{"id": "plane-project-1", "name": "Core Loop", "identifier": "CORE"}]},
                )
            return FakePlaneResponse(404, {"detail": "unexpected call"})

    monkeypatch.setattr(ticket_service.httpx, "Client", FakePlaneClient)

    client = TestClient(create_app())
    backend = client.put(
        "/api/v1/tickets/backend",
        json={
            "mode": "local_file",
            "plane_api_base_url": "https://plane.test",
            "plane_web_base_url": "https://app.plane.test",
            "plane_api_key_env": "PLANE_API_KEY",
        },
    )
    assert backend.status_code == 200

    response = client.get("/api/v1/tickets/backend/plane-scope/discovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["api_key_configured"] is True
    assert payload["external_calls"] is True
    assert payload["checks"] == ["plane_workspace_slug_configured", "plane_project_list_requested"]
    assert payload["setup_required"] == []
    assert payload["evidence"]["workspace_count"] == 1
    assert payload["evidence"]["project_count"] == 1
    assert payload["suggestions"][0]["source"] == "plane_discovery"
    assert payload["suggestions"][0]["plane_workspace_slug"] == "ait"
    assert payload["suggestions"][0]["plane_project_id"] == "plane-project-1"
    assert payload["suggestions"][0]["workspace_name"] == "ait"
    assert payload["suggestions"][0]["project_name"] == "Core Loop"
    assert calls[0]["url"] == "https://plane.test/api/v1/workspaces/ait/projects/"
    assert all(call["url"] != "https://plane.test/api/v1/workspaces/" for call in calls)
    assert all(call["headers"]["X-API-Key"] == "plane-test-key" for call in calls)
