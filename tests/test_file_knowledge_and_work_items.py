from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app
from aiteamos_api.read import chat_routes


def _write_member(path, *, member_id: str, name: str, role: str) -> None:
    path.write_text(
        f"""
id: {member_id}
display_name: {name}
kind: ai
role: {role}
summary: {role}
skills: []
runtime:
  mode: external_or_file_stub
  provider_identity: {member_id}
  preserve_provider_thread: true
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
            "content": "Clara should delegate repo inspection to RD members.",
            "source_kind": "manual",
            "scope_kind": "project",
            "scope_ref": "aiteamos",
            "member_ids": ["clara"],
        },
    )
    assert candidate.status_code == 200
    approved = client.post(f"/api/v1/memory/candidates/{candidate.json()['id']}/approve")
    assert approved.status_code == 200

    decision = client.post(
        "/api/v1/knowledge/decisions",
        json={
            "title": "Clara stays control plane",
            "context": "Clara coordinates members.",
            "decision": "Clara delegates code work to RD and PV.",
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


def test_work_item_routes_create_and_record_reports(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    client = TestClient(create_app())

    created = client.post(
        "/api/v1/work-items",
        json={
            "title": "Implement Knowledge flow",
            "description": "Create docs, memories, decisions and review queue views.",
            "assigned_member_id": "alex",
            "validation_member_id": "peter",
            "knowledge_refs": ["doc:product-direction"],
            "code_repository_ids": ["repo-aiteamos"],
        },
    )
    assert created.status_code == 200
    work_item_id = created.json()["id"]
    assert created.json()["status"] == "assigned"
    assert created.json()["code_repository_ids"] == ["repo-aiteamos"]

    reported = client.post(
        f"/api/v1/work-items/{work_item_id}/reports",
        json={
            "reporter_member_id": "peter",
            "reporter_role": "AI PV",
            "content": "Validation passed.",
            "report_type": "validation",
            "evidence": ["pytest passed"],
        },
    )
    assert reported.status_code == 200
    assert reported.json()["status"] == "validated"
    assert reported.json()["reports"][0]["evidence"] == ["pytest passed"]

    index = json.loads((workspace / ".aiteamos" / "work_items" / "index.json").read_text(encoding="utf-8"))
    assert index[0]["id"] == work_item_id


def test_clara_can_search_knowledge_and_create_local_work_item(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    (workspace / "PRODUCT_DIRECTION.md").write_text(
        "# Product Direction\n\nKnowledge contains Docs, Memories, Decisions, and Review Queue.\n",
        encoding="utf-8",
    )

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    _write_member(members_dir / "clara.yaml", member_id="clara", name="Clara", role="AI Team Lead")
    _write_member(members_dir / "alex.yaml", member_id="alex", name="Alex", role="AI RD / Implementer")
    _write_member(members_dir / "peter.yaml", member_id="peter", name="Peter", role="AI PV")

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote provider should not be called for local Knowledge/WorkItem tools")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    repo_dir = workspace / "repo"
    (repo_dir / ".git").mkdir(parents=True)
    (repo_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    work_page = repo_dir / "apps" / "dashboard" / "src" / "pages" / "work" / "index.tsx"
    work_page.parent.mkdir(parents=True)
    work_page.write_text(
        "export function WorkPage() {\n  return <section>Work page repo context implementation</section>;\n}\n",
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
            "target_member_id": "clara",
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
            "target_member_id": "clara",
        },
    )
    assert search.status_code == 200
    assert "我搜索了 Knowledge" in search.json()["reply"]
    assert any(event["event"] == "tool.search_knowledge.completed" for event in search.json()["trace_events"])

    create = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请创建本地 WorkItem，交给 Alex 完善 AITeamOS 代码仓库中的 Knowledge flow，并由 Peter 验证。",
            "thread_id": "work-item-tool-test",
            "target_member_id": "clara",
        },
    )
    assert create.status_code == 200
    payload = create.json()
    assert "已创建本地 Work Item" in payload["reply"]
    completed = next(event for event in payload["trace_events"] if event["event"] == "tool.create_work_item.completed")
    work_item = completed["data"]["work_item"]
    assert work_item["assigned_member_id"] == "alex"
    assert work_item["validation_member_id"] == "peter"
    assert work_item["knowledge_refs"]
    assert work_item["code_repository_ids"] == ["repo-aiteamos"]

    inspect = client.post(
        "/api/v1/chat/messages",
        json={
            "message": f"Alex，请检查 {work_item['id']} 里的 Work 页面实现。",
            "thread_id": "repo-inspect-tool-test",
            "target_member_id": "alex",
        },
    )
    assert inspect.status_code == 200
    inspect_payload = inspect.json()
    assert "已检查代码仓库" in inspect_payload["reply"]
    inspect_event = next(event for event in inspect_payload["trace_events"] if event["event"] == "tool.inspect_code_repository.completed")
    assert inspect_event["data"]["matches"]
    assert inspect_event["data"]["work_item"]["reports"][-1]["report_type"] == "repo_inspection"
