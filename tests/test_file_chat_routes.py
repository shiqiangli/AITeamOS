from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiteamos_api.read import chat_routes
from aiteamos_api.main import create_app


def test_file_backed_member_chat_roundtrip(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "stub")

    members_dir = workspace / ".aiteamos" / "members"
    skills_dir = workspace / ".aiteamos" / "skills" / "test-engineering"
    members_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)

    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: external_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )
    (members_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills:
  - test-engineering
runtime:
  mode: external_or_file_stub
  provider_identity: alex
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )
    (skills_dir / "SKILL.md").write_text("# Test Engineering\n", encoding="utf-8")

    client = TestClient(create_app())

    members = client.get("/api/v1/chat/members")
    assert members.status_code == 200
    assert [member["id"] for member in members.json()] == ["alex", "clara"]

    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Alex, please move Jira SV-1234 forward and report back.",
            "thread_id": "thread-test",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["target_member"]["id"] == "alex"
    assert payload["jira_keys"] == ["SV-1234"]
    assert payload["provider_thread_id"] == "provider-alex-thread-t"
    assert "Test Engineering" in payload["reply"]

    provider_threads = json.loads((workspace / ".aiteamos" / "provider_threads.json").read_text())
    assert provider_threads["alex::thread-test"] == "provider-alex-thread-t"

    conversation = workspace / payload["saved_paths"]["conversation"]
    trace = workspace / payload["saved_paths"]["trace"]
    assert conversation.exists()
    assert trace.exists()
    assert "member.selected" in trace.read_text(encoding="utf-8")


def test_chat_runtime_settings_are_file_backed(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    client = TestClient(create_app())

    initial = client.get("/api/v1/chat/runtime")
    assert initial.status_code == 200
    assert initial.json()["provider"] == "stub"
    assert initial.json()["api_keys_configured"]["deepseek"] is False

    updated = client.put(
        "/api/v1/chat/runtime",
        json={
            "provider": "deepseek",
            "deepseek_model": "deepseek-v4-flash",
            "deepseek_thinking": "disabled",
            "openai_model": "gpt-5-nano",
            "fallback_on_error": True,
            "deepseek_api_key": "secret-test-key",
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["provider"] == "deepseek"
    assert payload["api_keys_configured"]["deepseek"] is True
    assert "secret-test-key" not in json.dumps(payload)

    runtime_file = workspace / ".aiteamos" / "runtime.json"
    secrets_file = workspace / ".aiteamos" / "secrets.local.json"
    assert json.loads(runtime_file.read_text())["provider"] == "deepseek"
    assert json.loads(secrets_file.read_text())["deepseek_api_key"] == "secret-test-key"


def test_member_chat_streams_sse_events(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "stub")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
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
    with client.stream(
        "POST",
        "/api/v1/chat/messages/stream",
        json={
            "message": "Who are you?",
            "thread_id": "stream-test",
            "target_member_id": "clara",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert "event: start" in body
    assert "event: delta" in body
    assert "event: final" in body
    assert "Clara received the request." in body


def test_member_chat_agui_agent_endpoint_roundtrip(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "stub")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
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
    with client.stream(
        "POST",
        "/api/v1/chat/agent?target_member_id=clara",
        json={
            "threadId": "agui-thread-test",
            "runId": "agui-run-test",
            "state": {},
            "messages": [{"id": "agui-user-1", "role": "user", "content": "Who are you?"}],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert "RUN_STARTED" in body
    assert "TEXT_MESSAGE_START" in body
    assert "TEXT_MESSAGE_CONTENT" in body
    assert "TEXT_MESSAGE_END" in body
    assert "MESSAGES_SNAPSHOT" in body
    assert "STATE_SNAPSHOT" in body
    assert body.index("TEXT_MESSAGE_CONTENT") < body.index("MESSAGES_SNAPSHOT")
    assert "Clara received the request." in body
    assert "aiteamos_chat_response" in body
    assert (workspace / ".aiteamos" / "conversations" / "agui-thread-test.jsonl").exists()


def test_member_chat_streams_deepseek_native_chunks(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))

    runtime_dir = workspace / ".aiteamos"
    members_dir = runtime_dir / "members"
    members_dir.mkdir(parents=True)
    (runtime_dir / "runtime.json").write_text(
        json.dumps({
            "provider": "deepseek",
            "deepseek_model": "deepseek-v4-flash",
            "deepseek_thinking": "disabled",
            "fallback_on_error": True,
        }),
        encoding="utf-8",
    )
    (runtime_dir / "secrets.local.json").write_text(
        json.dumps({"deepseek_api_key": "test-key"}),
        encoding="utf-8",
    )
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )

    calls = []

    class FakeStreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_lines(self):
            yield 'data: {"id":"ds-stream-1","model":"deepseek-v4-flash","choices":[{"delta":{"content":"我是 "}}]}'
            yield 'data: {"id":"ds-stream-1","model":"deepseek-v4-flash","choices":[{"delta":{"content":"Clara"}}]}'
            yield 'data: {"id":"ds-stream-1","model":"deepseek-v4-flash","choices":[],"usage":{"total_tokens":42}}'
            yield "data: [DONE]"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, headers, json):
            calls.append({"method": method, "url": url, "headers": headers, "json": json})
            return FakeStreamResponse()

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FakeAsyncClient)

    client = TestClient(create_app())
    with client.stream(
        "POST",
        "/api/v1/chat/messages/stream",
        json={
            "message": "你是谁？",
            "thread_id": "deepseek-native-stream",
            "target_member_id": "clara",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert calls[0]["url"] == "https://api.deepseek.com/chat/completions"
    assert calls[0]["json"]["stream"] is True
    assert calls[0]["json"]["stream_options"] == {"include_usage": True}
    assert 'event: delta\ndata: {"text": "我是 "}' in body
    assert 'event: delta\ndata: {"text": "Clara"}' in body
    assert "runtime.deepseek.stream_completed" in body

    provider_threads = json.loads((workspace / ".aiteamos" / "provider_threads.json").read_text())
    state = provider_threads["clara::deepseek-native-stream"]
    assert state["provider"] == "deepseek_chat_completions"
    assert state["deepseek_last_response_id"] == "ds-stream-1"


def test_member_chat_lists_members_with_local_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )
    (members_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills:
  - test-engineering
runtime:
  mode: external_or_file_stub
  provider_identity: alex
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote provider should not be called for list_members")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "列出所有成员列表",
            "thread_id": "list-members-test",
            "target_member_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_member"]["id"] == "clara"
    assert "我找到了 2 个成员" in payload["reply"]
    assert "Clara" in payload["reply"]
    assert "Alex" in payload["reply"]
    assert "#/members" in payload["reply"]
    assert any(event["event"] == "tool.list_members.called" for event in payload["trace_events"])
    assert any(event["event"] == "tool.list_members.completed" for event in payload["trace_events"])

    trace = workspace / payload["saved_paths"]["trace"]
    assert "tool.list_members.completed" in trace.read_text(encoding="utf-8")


def test_chat_lists_file_backed_skills(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))

    members_dir = workspace / ".aiteamos" / "members"
    skills_dir = workspace / ".aiteamos" / "skills" / "test-engineering"
    members_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    (members_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills:
  - test-engineering
runtime:
  mode: external_or_file_stub
  provider_identity: alex
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )
    (skills_dir / "SKILL.md").write_text(
        """
# Test Engineering

> Test execution and validation evidence.

## Procedure
1. Run tests.
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(create_app())
    response = client.get("/api/v1/chat/skills")

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "id": "test-engineering",
            "title": "Test Engineering",
            "description": "Test execution and validation evidence.",
            "assigned_members": ["alex"],
            "resources": [],
            "saved_path": ".aiteamos/skills/test-engineering/SKILL.md",
        }
    ]


def test_member_chat_creates_and_assigns_skill_with_local_tools(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )
    (members_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills: []
runtime:
  mode: external_or_file_stub
  provider_identity: alex
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote provider should not be called for skill tools")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    create_response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请创建一个 Skill，名字叫 nightly-regression-log-triage，用于分析 nightly regression log。",
            "thread_id": "create-skill-test",
            "target_member_id": "clara",
        },
    )

    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert "已创建 Skill" in create_payload["reply"]
    assert any(event["event"] == "tool.create_skill.completed" for event in create_payload["trace_events"])
    skill_path = workspace / ".aiteamos" / "skills" / "nightly-regression-log-triage" / "SKILL.md"
    assert skill_path.exists()

    assign_response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请把 nightly-regression-log-triage 分配给 Alex。",
            "thread_id": "assign-skill-test",
            "target_member_id": "clara",
        },
    )

    assert assign_response.status_code == 200
    assign_payload = assign_response.json()
    assert "已把 Skill" in assign_payload["reply"]
    assert any(event["event"] == "tool.assign_skill_to_member.completed" for event in assign_payload["trace_events"])
    profile = chat_routes.yaml.safe_load((members_dir / "alex.yaml").read_text(encoding="utf-8"))
    assert profile["skills"] == ["nightly-regression-log-triage"]

    delete_response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请删除 Skill nightly-regression-log-triage。",
            "thread_id": "delete-skill-test",
            "target_member_id": "clara",
        },
    )

    assert delete_response.status_code == 200
    delete_payload = delete_response.json()
    assert "已删除 Skill" in delete_payload["reply"]
    assert any(event["event"] == "tool.delete_skill.completed" for event in delete_payload["trace_events"])
    assert not skill_path.exists()
    profile = chat_routes.yaml.safe_load((members_dir / "alex.yaml").read_text(encoding="utf-8"))
    assert profile["skills"] == []


def test_member_chat_streams_list_members_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )
    (members_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills:
  - test-engineering
runtime:
  mode: external_or_file_stub
  provider_identity: alex
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote provider should not be called for list_members")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    with client.stream(
        "POST",
        "/api/v1/chat/messages/stream",
        json={
            "message": "Clara，请列出团队成员",
            "thread_id": "list-members-stream",
            "target_member_id": "clara",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert "event: start" in body
    assert "event: delta" in body
    assert "event: final" in body
    assert "Clara" in body
    assert "Alex" in body
    assert "tool.list_members.completed" in body


def test_member_chat_creates_member_with_local_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote provider should not be called for create_member")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": (
                "Clara，请创建一个 AI PV 成员，名字叫 Victor，"
                "负责 regression 和 harness fail triage，技能为 test-engineering, validation-strategy。"
            ),
            "thread_id": "create-member-test",
            "target_member_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "已创建成员 Victor" in payload["reply"]
    assert "#/members/victor" in payload["reply"]
    assert any(event["event"] == "tool.create_member.completed" for event in payload["trace_events"])

    profile_path = members_dir / "victor.yaml"
    assert profile_path.exists()
    profile = chat_routes.yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    assert profile["id"] == "victor"
    assert profile["display_name"] == "Victor"
    assert profile["role"] == "AI PV"
    assert profile["summary"] == "Victor focuses on regression 和 harness fail triage."
    assert profile["skills"] == ["test-engineering", "validation-strategy"]

    members = client.get("/api/v1/chat/members")
    assert members.status_code == 200
    assert "victor" in {member["id"] for member in members.json()}


def test_member_chat_creates_member_from_ai_employee_phrase(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote provider should not be called for create_member")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "请创建一个AI员工，名字叫Peter，职责是PV",
            "thread_id": "create-ai-employee-test",
            "target_member_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "已创建成员 Peter" in payload["reply"]
    assert any(event["event"] == "tool.create_member.completed" for event in payload["trace_events"])

    profile = chat_routes.yaml.safe_load((members_dir / "peter.yaml").read_text(encoding="utf-8"))
    assert profile["id"] == "peter"
    assert profile["display_name"] == "Peter"
    assert profile["kind"] == "ai"
    assert profile["role"] == "AI PV"
    assert profile["skills"] == ["test-engineering", "validation-strategy"]


def test_member_chat_uses_deepseek_tool_planner_for_create_member(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )

    calls = []

    class FakePlannerResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "tool": "create_member",
                                "arguments": {
                                    "display_name": "Nora",
                                    "kind": "ai",
                                    "role": "AI PV",
                                    "summary": "Nightly regression triage owner.",
                                    "skills": ["test-engineering", "validation-strategy"],
                                },
                                "confidence": 0.94,
                                "reason": "The user wants to add a verification specialist to the team.",
                            })
                        }
                    }
                ]
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, json):
            calls.append({"url": url, "headers": headers, "json": json})
            return FakePlannerResponse()

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FakeAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "帮团队补一个叫 Nora 的验证专家，她负责 nightly regression triage",
            "thread_id": "planner-create-member-test",
            "target_member_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(calls) == 1
    assert calls[0]["url"] == "https://api.deepseek.com/chat/completions"
    assert "local tool planner" in calls[0]["json"]["messages"][0]["content"].lower()
    assert "已创建成员 Nora" in payload["reply"]
    assert any(event["event"] == "tool.intent_planner.completed" for event in payload["trace_events"])
    assert any(event["event"] == "tool.create_member.completed" for event in payload["trace_events"])

    profile = chat_routes.yaml.safe_load((members_dir / "nora.yaml").read_text(encoding="utf-8"))
    assert profile["id"] == "nora"
    assert profile["role"] == "AI PV"
    assert profile["summary"] == "Nightly regression triage owner."


def test_member_chat_edits_member_profile_with_local_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )
    (members_dir / "victor.yaml").write_text(
        """
id: victor
display_name: Victor
kind: ai
role: AI PV
summary: Initial PV member.
skills:
  - test-engineering
runtime:
  mode: external_or_file_stub
  provider_identity: victor
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote provider should not be called for edit_member_profile")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": (
                "Clara，请把 Victor 的 summary 改成 Owns PV triage，"
                "并添加技能 validation-strategy。"
            ),
            "thread_id": "edit-member-test",
            "target_member_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "已更新成员 Victor 的 profile" in payload["reply"]
    assert "summary: Owns PV triage" in payload["reply"]
    assert "#/members/victor" in payload["reply"]
    assert any(event["event"] == "tool.edit_member_profile.completed" for event in payload["trace_events"])

    profile = chat_routes.yaml.safe_load((members_dir / "victor.yaml").read_text(encoding="utf-8"))
    assert profile["summary"] == "Owns PV triage"
    assert profile["skills"] == ["test-engineering", "validation-strategy"]


def test_member_chat_deletes_member_with_local_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    runtime_dir = workspace / ".aiteamos"
    members_dir = runtime_dir / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )
    (members_dir / "victor.yaml").write_text(
        """
id: victor
display_name: Victor
kind: ai
role: AI PV
summary: Initial PV member.
skills:
  - test-engineering
runtime:
  mode: external_or_file_stub
  provider_identity: victor
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )
    (runtime_dir / "provider_threads.json").write_text(
        json.dumps({
            "victor::thread-1": "provider-victor-thread-1",
            "clara::thread-1": "provider-clara-thread-1",
        }),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote provider should not be called for delete_member")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请删除成员 Victor。",
            "thread_id": "delete-member-test",
            "target_member_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "已删除成员 Victor" in payload["reply"]
    assert any(event["event"] == "tool.delete_member.completed" for event in payload["trace_events"])
    assert not (members_dir / "victor.yaml").exists()

    provider_threads = json.loads((runtime_dir / "provider_threads.json").read_text(encoding="utf-8"))
    assert "victor::thread-1" not in provider_threads
    assert provider_threads["clara::thread-1"] == "provider-clara-thread-1"


def test_member_chat_blocks_deleting_clara(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote provider should not be called for delete_member")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请删除成员 clara。",
            "thread_id": "delete-clara-test",
            "target_member_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "没有删除 Clara" in payload["reply"]
    assert any(event["event"] == "tool.delete_member.blocked" for event in payload["trace_events"])
    assert (members_dir / "clara.yaml").exists()


def test_member_chat_streams_create_member_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote provider should not be called for create_member streaming")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    with client.stream(
        "POST",
        "/api/v1/chat/messages/stream",
        json={
            "message": "create_member name=Riley, role=AI Release, skills=validation-strategy",
            "thread_id": "create-member-stream",
            "target_member_id": "clara",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert "event: start" in body
    assert "event: delta" in body
    assert "event: final" in body
    assert "tool.create_member.completed" in body
    assert (members_dir / "riley.yaml").exists()


def test_member_chat_can_use_openai_runtime(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("AITEAMOS_OPENAI_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_OPENAI_MODEL", "gpt-test")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
personality: Calm and explicit
responsibilities:
  - Explain AITeamOS and route work
skills: []
runtime:
  mode: openai_responses
  provider_identity: clara
  preserve_provider_thread: true
handoff_rules:
  - Ask for human approval before external actions
""".strip(),
        encoding="utf-8",
    )

    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "id": "resp-test-1",
                "model": "gpt-test",
                "output_text": "我是 AITeamOS 的 Clara。",
                "usage": {"input_tokens": 12, "output_tokens": 8},
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, json):
            calls.append({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FakeAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "你是谁？",
            "thread_id": "who-are-you",
            "target_member_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "我是 AITeamOS 的 Clara。"
    assert payload["provider_thread_id"] == "provider-clara-who-are-"
    assert any(event["event"] == "runtime.openai.completed" for event in payload["trace_events"])
    assert calls[0]["url"] == "https://api.openai.com/v1/responses"
    assert calls[0]["json"]["model"] == "gpt-test"
    assert "Role: AI Team Lead" in calls[0]["json"]["instructions"]

    provider_threads = json.loads((workspace / ".aiteamos" / "provider_threads.json").read_text())
    state = provider_threads["clara::who-are-you"]
    assert state["provider"] == "openai_responses"
    assert state["openai_previous_response_id"] == "resp-test-1"


def test_member_chat_can_use_deepseek_runtime(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("AITEAMOS_DEEPSEEK_THINKING", "disabled")

    members_dir = workspace / ".aiteamos" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team Lead
summary: Coordinator
personality: Calm and explicit
responsibilities:
  - Explain AITeamOS and route work
skills: []
runtime:
  mode: deepseek_chat_or_file_stub
  provider_identity: clara
  preserve_provider_thread: true
handoff_rules:
  - Ask for human approval before external actions
""".strip(),
        encoding="utf-8",
    )

    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "id": "ds-test-1",
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "我是 AITeamOS 的 Clara。",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, json):
            calls.append({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FakeAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "你是谁？",
            "thread_id": "deepseek-who-are-you",
            "target_member_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "我是 AITeamOS 的 Clara。"
    assert payload["provider_thread_id"] == "provider-clara-deepseek"
    assert any(event["event"] == "runtime.deepseek.completed" for event in payload["trace_events"])
    assert calls[0]["url"] == "https://api.deepseek.com/chat/completions"
    assert calls[0]["json"]["model"] == "deepseek-v4-flash"
    assert calls[0]["json"]["thinking"] == {"type": "disabled"}
    assert calls[0]["json"]["messages"][0]["role"] == "system"
    assert "Role: AI Team Lead" in calls[0]["json"]["messages"][0]["content"]

    provider_threads = json.loads((workspace / ".aiteamos" / "provider_threads.json").read_text())
    state = provider_threads["clara::deepseek-who-are-you"]
    assert state["provider"] == "deepseek_chat_completions"
    assert state["deepseek_last_response_id"] == "ds-test-1"
    assert state["assumed_agent_session"] is True
