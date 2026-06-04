from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app


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
