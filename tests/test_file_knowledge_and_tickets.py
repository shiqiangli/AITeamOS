from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app
from aiteamos_api.read import chat_routes


def _write_employee(path, *, employee_id: str, name: str, role: str) -> None:
    path.write_text(
        f"""
id: {employee_id}
display_name: {name}
kind: ai
role: {role}
summary: {role}
skills: []
ai_engine:
  mode: external_or_file_stub
  engine_identity: {employee_id}
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )


def test_knowledge_routes_search_docs_memories_and_decisions(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    (workspace / "PRODUCT_DIRECTION.md").write_text(
        "# Product Direction\n\nAITeamOS uses Clara as control-plane manager.\n",
        encoding="utf-8",
    )

    client = TestClient(create_app())

    docs = client.get("/api/v1/knowledge/docs")
    assert docs.status_code == 200
    assert docs.json()[0]["path"] == "PRODUCT_DIRECTION.md"

    candidate = client.post(
        "/api/v1/memory/candidates",
        json={
            "content": "Clara should delegate repo inspection to RD employees.",
            "source_kind": "manual",
            "scope_kind": "project",
            "scope_ref": "aiteamos",
            "employee_ids": ["clara"],
        },
    )
    assert candidate.status_code == 200
    approved = client.post(f"/api/v1/memory/candidates/{candidate.json()['id']}/approve")
    assert approved.status_code == 200

    decision = client.post(
        "/api/v1/knowledge/decisions",
        json={
            "title": "Clara stays control plane",
            "context": "Clara coordinates employees.",
            "decision": "Clara delegates code Tickets to RD and PV.",
            "consequences": "Clara reads Knowledge, not repository state.",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["saved_path"].startswith(".aiteamos/knowledge/decisions/")

    search = client.get("/api/v1/knowledge/search?q=Clara control-plane delegate")
    assert search.status_code == 200
    source_types = {item["source_type"] for item in search.json()["results"]}
    assert {"doc", "memory", "decision"}.issubset(source_types)

    review = client.get("/api/v1/knowledge/review-queue")
    assert review.status_code == 200
    assert review.json() == []


def test_ticket_routes_create_and_record_reports(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    client = TestClient(create_app())

    backend = client.get("/api/v1/tickets/backend")
    assert backend.status_code == 200
    assert backend.json()["mode"] == "local_file"
    assert backend.json()["local_file_path"] == ".aiteamos/tickets/index.json"

    created = client.post(
        "/api/v1/tickets",
        json={
            "title": "Implement Knowledge flow",
            "description": "Create docs, memories, decisions and review queue views.",
            "ticket_type": "rd",
            "assigned_employee_id": "alex",
            "assigned_role": "AI RD / Implementer",
            "validation_employee_id": "peter",
            "validation_role": "AI PV",
            "knowledge_refs": ["doc:product-direction"],
            "code_repository_ids": ["repo-aiteamos"],
        },
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]
    assert ticket_id == "rd-0001"
    assert created.json()["ticket_type"] == "rd"
    assert created.json()["status"] == "assigned"
    assert created.json()["code_repository_ids"] == ["repo-aiteamos"]

    reported = client.post(
        f"/api/v1/tickets/{ticket_id}/reports",
        json={
            "reporter_employee_id": "peter",
            "reporter_role": "AI PV",
            "content": "Validation passed.",
            "report_type": "validation",
            "evidence": ["pytest passed"],
        },
    )
    assert reported.status_code == 200
    assert reported.json()["status"] == "validated"
    assert reported.json()["reports"][0]["evidence"] == ["pytest passed"]

    event_file = workspace / ".aiteamos" / "tickets" / "rd" / f"{ticket_id}.ticket.jsonl"
    assert event_file.exists()
    event_lines = [json.loads(line) for line in event_file.read_text(encoding="utf-8").splitlines()]
    assert [event["type"] for event in event_lines[:3]] == ["created", "assigned", "validation_requested"]

    events = client.get(f"/api/v1/tickets/{ticket_id}/events")
    assert events.status_code == 200
    event_types = [event["type"] for event in events.json()]
    assert "validated" in event_types
    assert "status_changed" in event_types
    assert any(event["type"] == "asset_linked" and event["data"]["target_kind"] == "evidence" for event in events.json())

    peter_work = client.get("/api/v1/tickets/employees/peter/work")
    assert peter_work.status_code == 200
    assert peter_work.json()["contribution"]["validation_count"] == 1
    assert peter_work.json()["validations"][0]["ticket_id"] == ticket_id

    alex_work = client.get("/api/v1/tickets/employees/alex/work")
    assert alex_work.status_code == 200
    assert alex_work.json()["historical_tickets"][0]["ticket_id"] == ticket_id

    ticket_assets = client.get("/api/v1/tickets/assets")
    assert ticket_assets.status_code == 200
    assert {item["kind"] for item in ticket_assets.json()} == {"report", "evidence"}
    assert {item["source_ticket_id"] for item in ticket_assets.json()} == {ticket_id}

    all_assets = client.get("/api/v1/assets")
    assert all_assets.status_code == 200
    evidence_asset = next(item for item in all_assets.json() if item["kind"] == "evidence")
    assert evidence_asset["source_ticket"] == ticket_id
    assert evidence_asset["source_employee"] == "peter"

    knowledge_docs = client.get("/api/v1/assets/knowledge/docs")
    assert knowledge_docs.status_code == 200
    assert all(item["metadata"]["asset_domain"] == "knowledge" for item in knowledge_docs.json())

    forbidden = client.post(
        "/api/v1/tickets",
        json={
            "title": "PV-only namespace",
            "description": "RD employee should not create PV Tickets.",
            "ticket_type": "pv",
            "actor_employee_id": "alex",
            "actor_role": "AI RD / Implementer",
        },
    )
    assert forbidden.status_code == 400
    assert "cannot create pv Tickets" in forbidden.json()["detail"]

    unassigned = client.post(
        "/api/v1/tickets",
        json={
            "title": "Detached work record",
            "description": "A Ticket without an assignee would bypass Clara-led flow.",
            "ticket_type": "rd",
        },
    )
    assert unassigned.status_code == 400
    assert "requires an assignee" in unassigned.json()["detail"]

    status = client.get("/api/v1/tickets/status")
    assert status.status_code == 200
    assert status.json()["status"] == "ready"
    assert status.json()["ticket_count"] == 1

    index = json.loads((workspace / ".aiteamos" / "tickets" / "index.json").read_text(encoding="utf-8"))
    assert index[0]["id"] == ticket_id

    updated_backend = client.put(
        "/api/v1/tickets/backend",
        json={
            "mode": "local_file",
            "local_file_path": "tickets/self-improvement.json",
        },
    )
    assert updated_backend.status_code == 200
    assert updated_backend.json()["local_file_path"] == "tickets/self-improvement.json"


def test_clara_can_search_knowledge_and_create_local_ticket(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    (workspace / "PRODUCT_DIRECTION.md").write_text(
        "# Product Direction\n\nKnowledge contains Docs, Memories, Decisions, and Review Queue.\n",
        encoding="utf-8",
    )

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    _write_employee(employees_dir / "clara.yaml", employee_id="clara", name="Clara", role="AI Team OS Manager")
    _write_employee(employees_dir / "alex.yaml", employee_id="alex", name="Alex", role="AI RD / Implementer")
    _write_employee(employees_dir / "peter.yaml", employee_id="peter", name="Peter", role="AI PV")

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for local Knowledge/Ticket tools")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    repo_dir = workspace / "repo"
    (repo_dir / ".git").mkdir(parents=True)
    (repo_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    tickets_page = repo_dir / "apps" / "dashboard" / "src" / "pages" / "tickets" / "index.tsx"
    tickets_page.parent.mkdir(parents=True)
    tickets_page.write_text(
        "export function TicketsPage() {\n  return <section>Tickets 页面实现 repo context implementation</section>;\n}\n",
        encoding="utf-8",
    )
    repo = client.post(
        "/api/v1/code-repositories",
        json={
            "id": "repo-aiteamos",
            "name": "AITeamOS",
            "provider": "local",
            "location": str(repo_dir),
            "default_branch": "main",
            "plane_workspace_slug": "ait",
            "plane_project_id": "aiteamos",
        },
    )
    assert repo.status_code == 200

    list_repos = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请列出所有代码仓库。",
            "thread_id": "repo-tool-test",
            "target_employee_id": "clara",
        },
    )
    assert list_repos.status_code == 200
    assert "代码仓库" in list_repos.json()["reply"]
    assert any(event["event"] == "tool.list_code_repositories.completed" for event in list_repos.json()["trace_events"])

    search = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请搜索知识库 Knowledge flow。",
            "thread_id": "knowledge-tool-test",
            "target_employee_id": "clara",
        },
    )
    assert search.status_code == 200
    assert "我搜索了 Knowledge" in search.json()["reply"]
    assert any(event["event"] == "tool.search_knowledge.completed" for event in search.json()["trace_events"])

    create = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请创建本地 Ticket，交给 Alex 完善 AITeamOS 代码仓库中的 Knowledge flow，并由 Peter 验证。",
            "thread_id": "ticket-tool-test",
            "target_employee_id": "clara",
        },
    )
    assert create.status_code == 200
    payload = create.json()
    assert "已创建本地 Ticket" in payload["reply"]
    completed = next(event for event in payload["trace_events"] if event["event"] == "tool.create_ticket.completed")
    ticket = completed["data"]["ticket"]
    assert ticket["id"].startswith("rd-")
    assert ticket["ticket_type"] == "rd"
    assert ticket["assigned_employee_id"] == "alex"
    assert ticket["validation_employee_id"] == "peter"
    assert ticket["knowledge_refs"]
    assert ticket["code_repository_ids"] == ["repo-aiteamos"]

    inspect = client.post(
        "/api/v1/chat/messages",
        json={
            "message": f"Alex，请检查 {ticket['id']} 里的 Tickets 页面实现。",
            "thread_id": "repo-inspect-tool-test",
            "target_employee_id": "alex",
        },
    )
    assert inspect.status_code == 200
    inspect_payload = inspect.json()
    assert "已检查代码仓库" in inspect_payload["reply"]
    inspect_event = next(event for event in inspect_payload["trace_events"] if event["event"] == "tool.inspect_code_repository.completed")
    assert inspect_event["data"]["matches"]
    assert inspect_event["data"]["ticket"]["reports"][-1]["report_type"] == "repo_inspection"
    assert inspect_event["data"]["ticket"]["events"][-1]["type"] == "asset_linked"
