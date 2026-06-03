from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app


def test_memory_candidate_approval_and_search_are_file_backed(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("AITEAMOS_GRAPHITI_ENABLED", raising=False)
    monkeypatch.delenv("AITEAMOS_GRAPHITI_URI", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)

    client = TestClient(create_app())

    status = client.get("/api/v1/memory/status")
    assert status.status_code == 200
    assert status.json()["backend"]["backend"] == "graphiti"
    assert status.json()["backend"]["status"] == "disabled"
    assert status.json()["candidate_count"] == 0

    candidate = client.post(
        "/api/v1/memory/candidates",
        json={
            "content": "Coding style: keep AITeamOS memory candidates evidence-backed.",
            "source_kind": "decision",
            "source_ref": "DEC-1",
            "scope_kind": "project",
            "scope_ref": "aiteamos",
            "memory_type": "principle",
            "confidence": 0.9,
            "employee_ids": ["clara"],
            "tags": ["coding-style"],
        },
    )
    assert candidate.status_code == 200
    candidate_id = candidate.json()["id"]

    approved = client.post(f"/api/v1/memory/candidates/{candidate_id}/approve")
    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["status"] == "approved"
    assert approved_payload["graphiti_status"]["status"] == "skipped_disabled"

    search = client.get("/api/v1/memory/search?q=evidence-backed")
    assert search.status_code == 200
    assert search.json()["results"][0]["id"] == candidate_id
    assert search.json()["results"][0]["source"] == "file"

    candidates_file = workspace / ".aiteamos" / "memory" / "candidates.json"
    approved_file = workspace / ".aiteamos" / "memory" / "approved.json"
    assert candidates_file.exists()
    assert approved_file.exists()
    assert json.loads(approved_file.read_text(encoding="utf-8"))[0]["id"] == candidate_id


def test_graphiti_settings_are_file_backed_and_keep_secrets_local(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("AITEAMOS_GRAPHITI_ENABLED", raising=False)
    monkeypatch.delenv("AITEAMOS_GRAPHITI_URI", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = TestClient(create_app())

    initial = client.get("/api/v1/memory/graphiti/settings")
    assert initial.status_code == 200
    assert initial.json()["enabled"] is False
    assert initial.json()["password_configured"] is False

    updated = client.put(
        "/api/v1/memory/graphiti/settings",
        json={
            "enabled": True,
            "graph_database": "neo4j",
            "uri": "bolt://localhost:7687",
            "user": "neo4j",
            "password": "neo4j-test-password",
            "group_id": "aiteamos-test",
            "llm_provider": "openai",
            "openai_api_key": "openai-test-key",
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["enabled"] is True
    assert payload["password_configured"] is True
    assert payload["openai_api_key_configured"] is True
    assert payload["backend"]["graph_configured"] is True
    assert payload["backend"]["llm_configured"] is True
    assert payload["backend"]["status"] in {"ready", "package_missing"}
    assert "neo4j-test-password" not in json.dumps(payload)
    assert "openai-test-key" not in json.dumps(payload)

    settings_file = workspace / ".aiteamos" / "graphiti.json"
    secrets_file = workspace / ".aiteamos" / "secrets.local.json"
    settings_payload = json.loads(settings_file.read_text(encoding="utf-8"))
    secrets_payload = json.loads(secrets_file.read_text(encoding="utf-8"))
    assert settings_payload["uri"] == "bolt://localhost:7687"
    assert settings_payload["group_id"] == "aiteamos-test"
    assert "password" not in settings_payload
    assert secrets_payload["graphiti_neo4j_password"] == "neo4j-test-password"
    assert secrets_payload["graphiti_openai_api_key"] == "openai-test-key"


def test_chat_proposes_memory_candidate_and_recalls_approved_memory(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "stub")

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team OS Manager
summary: Coordinator
skills: []
runtime:
  mode: external_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(create_app())
    first = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请推进 Ticket SV-4321，并把 root cause 和验证结论沉淀下来。",
            "thread_id": "memory-chat-test",
            "target_employee_id": "clara",
        },
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert any(event["event"] == "memory.candidate.proposed" for event in first_payload["trace_events"])

    candidates = client.get("/api/v1/memory/candidates")
    assert candidates.status_code == 200
    assert len(candidates.json()) == 1
    candidate_id = candidates.json()[0]["id"]
    assert candidates.json()[0]["scope_kind"] == "ticket"
    assert candidates.json()[0]["scope_ref"] == "SV-4321"

    approved = client.post(f"/api/v1/memory/candidates/{candidate_id}/approve")
    assert approved.status_code == 200

    second = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，继续处理 SV-4321。",
            "thread_id": "memory-chat-test",
            "target_employee_id": "clara",
        },
    )
    assert second.status_code == 200
    assert "1 local memory snippet(s)" in second.json()["reply"]
    context_loaded = next(event for event in second.json()["trace_events"] if event["event"] == "context.loaded")
    assert context_loaded["data"]["memory_count"] == 1
