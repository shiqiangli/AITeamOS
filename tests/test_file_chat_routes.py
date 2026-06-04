from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiteamos_api.read import chat_routes
from aiteamos_api.main import create_app


def _has_command_event(payload: dict, command_id: str, phase: str = "completed") -> bool:
    return any(
        event["event"] == f"command.{phase}"
        and event.get("data", {}).get("command", {}).get("id") == command_id
        for event in payload["trace_events"]
    )


def test_chat_employees_bootstraps_protected_clara_system_employee(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))

    client = TestClient(create_app())
    response = client.get("/api/v1/chat/employees")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == "clara"
    assert payload[0]["display_name"] == "Clara"
    assert payload[0]["role"] == "AI Team OS Manager"

    profile_path = workspace / ".aiteamos" / "employees" / "clara.yaml"
    assert profile_path.exists()
    profile_text = profile_path.read_text(encoding="utf-8")
    assert "role: AI Team OS Manager" in profile_text
    assert "protected: true" in profile_text


def test_existing_clara_profile_is_normalized_to_system_role(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: Obsolete Clara Role
summary: Obsolete Clara summary.
responsibilities:
  - Obsolete Clara responsibility.
ai_engine:
  mode: external_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(create_app())
    response = client.get("/api/v1/chat/employees")

    assert response.status_code == 200
    assert response.json()[0]["role"] == "AI Team OS Manager"
    profile_text = (employees_dir / "clara.yaml").read_text(encoding="utf-8")
    assert "Obsolete Clara Role" not in profile_text
    assert "Obsolete Clara summary" not in profile_text
    assert "Obsolete Clara responsibility" not in profile_text
    assert "role: AI Team OS Manager" in profile_text


def test_file_backed_employee_chat_roundtrip(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "stub")

    employees_dir = workspace / ".aiteamos" / "employees"
    skills_dir = workspace / ".aiteamos" / "skills" / "test-engineering"
    employees_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)

    (employees_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team OS Manager
summary: Coordinator
skills: []
ai_engine:
  mode: external_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills:
  - test-engineering
ai_engine:
  mode: external_or_file_stub
  engine_identity: alex
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )
    (skills_dir / "SKILL.md").write_text("# Test Engineering\n", encoding="utf-8")

    client = TestClient(create_app())

    employees = client.get("/api/v1/chat/employees")
    assert employees.status_code == 200
    assert [employee["id"] for employee in employees.json()] == ["alex", "clara"]
    assert employees.json()[0]["default_thread_id"] == "employee-alex-default"

    default_thread_response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Alex, please keep this default thread.",
            "target_employee_id": "alex",
        },
    )
    assert default_thread_response.status_code == 200
    default_thread_payload = default_thread_response.json()
    assert default_thread_payload["thread_id"] == "employee-alex-default"

    default_thread = client.get("/api/v1/chat/threads/employee-alex-default")
    assert default_thread.status_code == 200
    assert [message["role"] for message in default_thread.json()["messages"]] == ["user", "assistant"]
    assert default_thread.json()["messages"][0]["content"] == "Alex, please keep this default thread."
    assert default_thread.json()["thread"]["id"] == "employee-alex-default"

    thread_list = client.get("/api/v1/chat/threads?employee_id=alex")
    assert thread_list.status_code == 200
    thread_payload = thread_list.json()
    assert thread_payload["active_thread_id"] == "employee-alex-default"
    assert thread_payload["threads"][0]["id"] == "employee-alex-default"
    assert thread_payload["threads"][0]["message_count"] == 2
    assert thread_payload["threads"][0]["title"] == "Alex, please keep this default thread."

    new_thread = client.post("/api/v1/chat/threads", json={"employee_id": "alex", "title": "Fresh Alex thread"})
    assert new_thread.status_code == 200
    assert new_thread.json()["employee_id"] == "alex"
    assert new_thread.json()["title"] == "Fresh Alex thread"

    thread_list = client.get("/api/v1/chat/threads?employee_id=alex")
    assert thread_list.status_code == 200
    assert thread_list.json()["active_thread_id"] == new_thread.json()["id"]

    activate_default = client.post(
        "/api/v1/chat/threads/employee-alex-default/activate",
        json={"employee_id": "alex"},
    )
    assert activate_default.status_code == 200
    assert activate_default.json()["id"] == "employee-alex-default"

    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Alex, please move Ticket SV-1234 forward and report back.",
            "ticket_key": "SV-1234",
            "thread_id": "thread-test",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["target_employee"]["id"] == "alex"
    assert payload["ticket_keys"] == ["SV-1234"]
    assert payload["engine_thread_id"] == "engine-alex-thread-t"
    assert payload["run_metadata"]["ticket_keys"] == ["SV-1234"]
    assert payload["run_metadata"]["ai_engine"]["actual_ai_engine"] == "stub"
    assert "Test Engineering" in payload["reply"]

    engine_threads = json.loads((workspace / ".aiteamos" / "engine_threads.json").read_text())
    assert engine_threads["alex::thread-test"] == "engine-alex-thread-t"

    conversation = workspace / payload["saved_paths"]["conversation"]
    trace = workspace / payload["saved_paths"]["trace"]
    assert conversation.exists()
    assert trace.exists()
    assert "employee.selected" in trace.read_text(encoding="utf-8")
    conversation_messages = [json.loads(line) for line in conversation.read_text(encoding="utf-8").splitlines()]
    assert conversation_messages[-1]["metadata"]["aiteamos"]["ai_engine"]["actual_ai_engine"] == "stub"
    assert conversation_messages[-1]["metadata"]["aiteamos"]["ticket_keys"] == ["SV-1234"]

    chinese_response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请说明你具备哪些权限？",
            "target_employee_id": "clara",
            "thread_id": "chinese-stub-test",
        },
    )
    assert chinese_response.status_code == 200
    chinese_payload = chinese_response.json()
    assert "这是 Kernel 根据 Clara 当前 profile 生成的权限事实" in chinese_payload["reply"]
    assert "Profile 原始权限" in chinese_payload["reply"]
    assert "Kernel 展开权限" in chinese_payload["reply"]
    assert "Raw permissions" not in chinese_payload["reply"]
    assert "Expanded Kernel permissions" not in chinese_payload["reply"]
    assert _has_command_event(chinese_payload, "kernel.permissions:inspect")
    assert chinese_payload["run_metadata"]["ai_engine"]["actual_ai_engine"] == "kernel_command"

    tool_response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "请列出所有成员列表",
            "target_employee_id": "clara",
            "thread_id": "tool-thread",
        },
    )
    assert tool_response.status_code == 200
    tool_payload = tool_response.json()
    assert _has_command_event(tool_payload, "employees.manage:list", "called")
    assert _has_command_event(tool_payload, "employees.manage:list")
    assert tool_payload["run_metadata"]["commands"][0]["id"] == "employees.manage:list"
    assert tool_payload["run_metadata"]["commands"][0]["status"] == "completed"

    tool_trace = workspace / tool_payload["saved_paths"]["trace"]
    assert "employees.manage:list" in tool_trace.read_text(encoding="utf-8")


def test_chat_ai_engine_settings_are_file_backed(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    client = TestClient(create_app())

    initial = client.get("/api/v1/chat/ai-engines")
    assert initial.status_code == 200
    assert initial.json()["active_engine"] == "stub"
    assert initial.json()["api_keys_configured"]["deepseek"] is False
    assert initial.json()["deepseek_thinking"] == "enabled"
    assert initial.json()["engines"]["deepseek"]["thinking"] == "enabled"
    assert initial.json()["engines"]["deepseek"]["context_window"] == 1000000
    assert initial.json()["engines"]["deepseek"]["max_tokens"] == 384000

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-test-key")
    updated = client.put(
        "/api/v1/chat/ai-engines",
        json={
            "active_engine": "deepseek",
            "deepseek_model": "deepseek-v4-flash",
            "deepseek_thinking": "disabled",
            "openai_model": "gpt-5-nano",
            "fallback_on_error": True,
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["active_engine"] == "deepseek"
    assert payload["api_keys_configured"]["deepseek"] is True
    assert "secret-test-key" not in json.dumps(payload)

    ai_engines_file = workspace / ".aiteamos" / "ai_engines.json"
    saved = json.loads(ai_engines_file.read_text())
    assert saved["active_engine"] == "deepseek"
    assert saved["engines"]["deepseek"]["model"] == "deepseek-v4-flash"
    assert saved["engines"]["deepseek"]["thinking"] == "disabled"
    assert saved["engines"]["deepseek"]["context_window"] == 1000000
    assert saved["engines"]["deepseek"]["max_tokens"] == 384000
    assert not (workspace / ".aiteamos" / "secrets.local.json").exists()


def test_chat_ai_engine_settings_can_be_updated_independently(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = TestClient(create_app())

    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    updated = client.put(
        "/api/v1/chat/ai-engines/openai",
        json={"model": "gpt-5-mini", "activate": True},
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["active_engine"] == "openai"
    assert payload["openai_model"] == "gpt-5-mini"
    assert payload["engines"]["openai"]["active"] is True
    assert payload["engines"]["openai"]["api_key_configured"] is True
    assert "openai-test-key" not in json.dumps(payload)

    ai_engines_file = workspace / ".aiteamos" / "ai_engines.json"
    saved = json.loads(ai_engines_file.read_text(encoding="utf-8"))
    assert saved["active_engine"] == "openai"
    assert saved["engines"]["openai"]["model"] == "gpt-5-mini"
    assert not (workspace / ".aiteamos" / "secrets.local.json").exists()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    updated_deepseek = client.put(
        "/api/v1/chat/ai-engines/deepseek",
        json={
            "context_window": 200000,
            "max_tokens": 8192,
            "thinking": "enabled",
            "activate": True,
        },
    )
    assert updated_deepseek.status_code == 200
    deepseek_payload = updated_deepseek.json()
    deepseek = deepseek_payload["engines"]["deepseek"]
    assert deepseek_payload["active_engine"] == "deepseek"
    assert deepseek["context_window"] == 200000
    assert deepseek["max_tokens"] == 8192
    assert deepseek["thinking"] == "enabled"
    assert "deepseek-test-key" not in json.dumps(deepseek_payload)

    saved = json.loads(ai_engines_file.read_text(encoding="utf-8"))
    assert saved["active_engine"] == "deepseek"
    assert saved["engines"]["deepseek"]["context_window"] == 200000
    assert saved["engines"]["deepseek"]["max_tokens"] == 8192
    assert saved["engines"]["deepseek"]["thinking"] == "enabled"


def test_employee_default_ai_engine_settings_are_file_backed(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills: []
ai_engine:
  mode: external_or_file_stub
  engine_identity: alex
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(create_app())
    initial = client.get("/api/v1/chat/employees")
    assert initial.status_code == 200
    alex = next(employee for employee in initial.json() if employee["id"] == "alex")
    assert alex["default_ai_engine"] == "system"

    updated = client.put("/api/v1/chat/employees/alex/ai-engine", json={"default_ai_engine": "openai"})
    assert updated.status_code == 200
    assert updated.json()["default_ai_engine"] == "openai"

    profile_text = (employees_dir / "alex.yaml").read_text(encoding="utf-8")
    assert "default_engine: openai" in profile_text

    invalid = client.put("/api/v1/chat/employees/alex/ai-engine", json={"default_ai_engine": "not-a-real-engine"})
    assert invalid.status_code == 400


def test_employee_default_ai_engine_overrides_global_engine_for_chat(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills: []
ai_engine:
  mode: external_or_file_stub
  engine_identity: alex
  default_engine: stub
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={"message": "Help with rd-1", "target_employee_id": "alex", "thread_id": "alex-default-engine"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_employee"]["default_ai_engine"] == "stub"
    assert payload["run_metadata"]["ai_engine"]["selected_ai_engine"] == "stub"
    assert payload["run_metadata"]["ai_engine"]["actual_ai_engine"] == "stub"


def test_employee_chat_streams_sse_events(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "stub")

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
ai_engine:
  mode: external_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
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
            "target_employee_id": "clara",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert "event: start" in body
    assert "event: delta" in body
    assert "event: final" in body
    assert "Clara received the request." in body


def test_employee_chat_agui_agent_endpoint_roundtrip(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "stub")

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
ai_engine:
  mode: external_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(create_app())
    with client.stream(
        "POST",
        "/api/v1/chat/agent?target_employee_id=clara",
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
    assert "langgraph_checkpoint" in body
    assert body.index("TEXT_MESSAGE_CONTENT") < body.index("MESSAGES_SNAPSHOT")
    assert "Clara received the request." in body
    assert "aiteamos_chat_response" in body
    assert (workspace / ".aiteamos" / "conversations" / "agui-thread-test.jsonl").exists()
    assert (workspace / ".aiteamos" / "langgraph" / "checkpoints.sqlite").exists()

    health = client.get("/api/v1/chat/agent/health")
    assert health.status_code == 200
    assert health.json()["checkpoint"]["mode"] == "sqlite"


def test_employee_chat_streams_deepseek_native_chunks(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("AITEAMOS_DEEPSEEK_THINKING", "disabled")

    ai_engine_dir = workspace / ".aiteamos"
    employees_dir = ai_engine_dir / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team OS Manager
summary: Coordinator
skills: []
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
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
            "target_employee_id": "clara",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert calls[0]["url"] == "https://api.deepseek.com/chat/completions"
    assert calls[0]["json"]["stream"] is True
    assert calls[0]["json"]["stream_options"] == {"include_usage": True}
    assert calls[0]["json"]["max_tokens"] == 384000
    assert "Language: Reply in concise Simplified Chinese" in calls[0]["json"]["messages"][0]["content"]
    assert 'event: delta\ndata: {"text": "我是 "}' in body
    assert 'event: delta\ndata: {"text": "Clara"}' in body
    assert "ai_engine.deepseek.stream_completed" in body

    engine_threads = json.loads((workspace / ".aiteamos" / "engine_threads.json").read_text())
    state = engine_threads["clara::deepseek-native-stream"]
    assert state["ai_engine"] == "deepseek_chat_completions"
    assert state["deepseek_last_response_id"] == "ds-stream-1"


def test_employee_chat_lists_employees_with_local_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

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
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills:
  - test-engineering
ai_engine:
  mode: external_or_file_stub
  engine_identity: alex
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for list_employees")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "列出所有成员列表",
            "thread_id": "list-employees-test",
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_employee"]["id"] == "clara"
    assert "我找到了 2 个成员" in payload["reply"]
    assert "Clara" in payload["reply"]
    assert "Alex" in payload["reply"]
    assert "#/employees" in payload["reply"]
    assert _has_command_event(payload, "employees.manage:list", "called")
    assert _has_command_event(payload, "employees.manage:list")

    trace = workspace / payload["saved_paths"]["trace"]
    assert "employees.manage:list" in trace.read_text(encoding="utf-8")


def test_chat_lists_file_backed_skills(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))

    employees_dir = workspace / ".aiteamos" / "employees"
    skills_dir = workspace / ".aiteamos" / "skills" / "test-engineering"
    employees_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills:
  - test-engineering
ai_engine:
  mode: external_or_file_stub
  engine_identity: alex
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )
    skill_content = """
# Test Engineering

> Test execution and validation evidence.

## Procedure
1. Run tests.
""".strip()
    (skills_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")

    client = TestClient(create_app())
    response = client.get("/api/v1/chat/skills")

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "id": "test-engineering",
            "title": "Test Engineering",
            "description": "Test execution and validation evidence.",
            "content": skill_content,
            "assigned_employees": ["alex"],
            "resources": [],
            "saved_path": ".aiteamos/skills/test-engineering/SKILL.md",
        }
    ]


def test_employee_chat_creates_and_assigns_skill_with_local_tools(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

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
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills: []
ai_engine:
  mode: external_or_file_stub
  engine_identity: alex
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for skill tools")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    create_response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请创建一个 Skill，名字叫 nightly-regression-log-triage，用于分析 nightly regression log。",
            "thread_id": "create-skill-test",
            "target_employee_id": "clara",
        },
    )

    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert "已创建 Skill" in create_payload["reply"]
    assert _has_command_event(create_payload, "assets.manage:create_skill")
    skill_path = workspace / ".aiteamos" / "skills" / "nightly-regression-log-triage" / "SKILL.md"
    assert skill_path.exists()

    assign_response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请把 nightly-regression-log-triage 分配给 Alex。",
            "thread_id": "assign-skill-test",
            "target_employee_id": "clara",
        },
    )

    assert assign_response.status_code == 200
    assign_payload = assign_response.json()
    assert "已把 Skill" in assign_payload["reply"]
    assert _has_command_event(assign_payload, "assets.manage:assign_skill")
    profile = chat_routes.yaml.safe_load((employees_dir / "alex.yaml").read_text(encoding="utf-8"))
    assert profile["skills"] == ["nightly-regression-log-triage"]

    delete_response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请删除 Skill nightly-regression-log-triage。",
            "thread_id": "delete-skill-test",
            "target_employee_id": "clara",
        },
    )

    assert delete_response.status_code == 200
    delete_payload = delete_response.json()
    assert "已删除 Skill" in delete_payload["reply"]
    assert _has_command_event(delete_payload, "assets.manage:delete_skill")
    assert not skill_path.exists()
    profile = chat_routes.yaml.safe_load((employees_dir / "alex.yaml").read_text(encoding="utf-8"))
    assert profile["skills"] == []


def test_employee_chat_streams_list_employees_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

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
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementer
skills:
  - test-engineering
ai_engine:
  mode: external_or_file_stub
  engine_identity: alex
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for list_employees")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    with client.stream(
        "POST",
        "/api/v1/chat/messages/stream",
        json={
            "message": "Clara，请列出团队成员",
            "thread_id": "list-employees-stream",
            "target_employee_id": "clara",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert "event: start" in body
    assert "event: delta" in body
    assert "event: final" in body
    assert "Clara" in body
    assert "Alex" in body
    assert "command.completed" in body
    assert "employees.manage:list" in body


def test_employee_chat_creates_employee_with_local_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

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
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for create_employee")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": (
                "Clara，请创建一个 AI PV 成员，名字叫 Victor，"
                "负责 regression 和 harness fail triage，技能为 test-engineering, validation-strategy。"
            ),
            "thread_id": "create-employee-test",
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "已创建成员 Victor" in payload["reply"]
    assert "#/employees/victor" in payload["reply"]
    assert _has_command_event(payload, "employees.manage:create")

    profile_path = employees_dir / "victor.yaml"
    assert profile_path.exists()
    profile = chat_routes.yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    assert profile["id"] == "victor"
    assert profile["display_name"] == "Victor"
    assert profile["role"] == "AI PV"
    assert profile["summary"] == "Victor focuses on regression 和 harness fail triage."
    assert profile["skills"] == ["test-engineering", "validation-strategy"]

    employees = client.get("/api/v1/chat/employees")
    assert employees.status_code == 200
    assert "victor" in {employee["id"] for employee in employees.json()}


def test_employee_chat_creates_employee_from_ai_employee_phrase(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

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
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for create_employee")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "请创建一个AI员工，名字叫Peter，职责是PV",
            "thread_id": "create-ai-employee-test",
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "已创建成员 Peter" in payload["reply"]
    assert _has_command_event(payload, "employees.manage:create")

    profile = chat_routes.yaml.safe_load((employees_dir / "peter.yaml").read_text(encoding="utf-8"))
    assert profile["id"] == "peter"
    assert profile["display_name"] == "Peter"
    assert profile["kind"] == "ai"
    assert profile["role"] == "AI PV"
    assert profile["skills"] == ["test-engineering", "validation-strategy"]


def test_employee_chat_uses_deepseek_tool_planner_for_create_employee(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

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
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
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
                                "command": "employees.manage:create",
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
            "thread_id": "planner-create-employee-test",
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(calls) == 1
    assert calls[0]["url"] == "https://api.deepseek.com/chat/completions"
    assert "kernel command planner" in calls[0]["json"]["messages"][0]["content"].lower()
    assert "已创建成员 Nora" in payload["reply"]
    assert any(event["event"] == "command.intent_planner.completed" for event in payload["trace_events"])
    assert _has_command_event(payload, "employees.manage:create")

    profile = chat_routes.yaml.safe_load((employees_dir / "nora.yaml").read_text(encoding="utf-8"))
    assert profile["id"] == "nora"
    assert profile["role"] == "AI PV"
    assert profile["summary"] == "Nightly regression triage owner."


def test_employee_chat_edits_employee_profile_with_local_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

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
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )
    (employees_dir / "victor.yaml").write_text(
        """
id: victor
display_name: Victor
kind: ai
role: AI PV
summary: Initial PV employee.
skills:
  - test-engineering
ai_engine:
  mode: external_or_file_stub
  engine_identity: victor
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for edit_employee_profile")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": (
                "Clara，请把 Victor 的 summary 改成 Owns PV triage，"
                "并添加技能 validation-strategy。"
            ),
            "thread_id": "edit-employee-test",
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "已更新成员 Victor 的 profile" in payload["reply"]
    assert "summary: Owns PV triage" in payload["reply"]
    assert "#/employees/victor" in payload["reply"]
    assert _has_command_event(payload, "employees.manage:update")

    profile = chat_routes.yaml.safe_load((employees_dir / "victor.yaml").read_text(encoding="utf-8"))
    assert profile["summary"] == "Owns PV triage"
    assert profile["skills"] == ["test-engineering", "validation-strategy"]


def test_employee_chat_deletes_employee_with_local_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

    runtime_dir = workspace / ".aiteamos"
    employees_dir = runtime_dir / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team OS Manager
summary: Coordinator
skills: []
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )
    (employees_dir / "victor.yaml").write_text(
        """
id: victor
display_name: Victor
kind: ai
role: AI PV
summary: Initial PV employee.
skills:
  - test-engineering
ai_engine:
  mode: external_or_file_stub
  engine_identity: victor
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )
    (runtime_dir / "engine_threads.json").write_text(
        json.dumps({
            "victor::thread-1": "engine-victor-thread-1",
            "clara::thread-1": "engine-clara-thread-1",
        }),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for delete_employee")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请删除成员 Victor。",
            "thread_id": "delete-employee-test",
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "已删除成员 Victor" in payload["reply"]
    assert _has_command_event(payload, "employees.manage:delete")
    assert not (employees_dir / "victor.yaml").exists()

    engine_threads = json.loads((runtime_dir / "engine_threads.json").read_text(encoding="utf-8"))
    assert "victor::thread-1" not in engine_threads
    assert engine_threads["clara::thread-1"] == "engine-clara-thread-1"


def test_employee_chat_blocks_deleting_clara(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

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
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for delete_employee")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请删除成员 clara。",
            "thread_id": "delete-clara-test",
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "没有删除 Clara" in payload["reply"]
    assert "系统默认 Employee" in payload["reply"]
    assert _has_command_event(payload, "employees.manage:delete", "blocked")
    assert (employees_dir / "clara.yaml").exists()


def test_employee_chat_streams_create_employee_tool(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

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
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for create_employee streaming")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    with client.stream(
        "POST",
        "/api/v1/chat/messages/stream",
        json={
            "message": "create_employee name=Riley, role=AI Release, skills=validation-strategy",
            "thread_id": "create-employee-stream",
            "target_employee_id": "clara",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert "event: start" in body
    assert "event: delta" in body
    assert "event: final" in body
    assert "command.completed" in body
    assert "employees.manage:create" in body
    assert (employees_dir / "riley.yaml").exists()


def test_clara_can_run_allowlisted_terminal_command(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，请执行命令 `pwd`。",
            "thread_id": "terminal-command-test",
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "terminal.run completed" in payload["reply"]
    assert str(workspace) in payload["reply"]
    assert _has_command_event(payload, "terminal.run:run")
    assert payload["run_metadata"]["commands"][0]["id"] == "terminal.run:run"
    assert payload["run_metadata"]["ai_engine"]["actual_ai_engine"] == "kernel_command"


def test_clara_reports_kernel_permissions_from_profile(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Remote AI Engine should not be called for permission inspection")

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FailingAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Clara，你具备哪些权限？你能不能创建或删除 Employee？",
            "thread_id": "permissions-inspect-test",
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "不是模型猜测" in payload["reply"]
    assert "Profile 原始权限" in payload["reply"]
    assert "Kernel 展开权限" in payload["reply"]
    assert "manage_employees" in payload["reply"]
    assert "employees.manage:create" in payload["reply"]
    assert "employees.manage:delete" in payload["reply"]
    assert "destructive / execution command" in payload["reply"]
    assert "Raw permissions" not in payload["reply"]
    assert "Expanded Kernel permissions" not in payload["reply"]
    assert _has_command_event(payload, "kernel.permissions:inspect")
    completed = next(
        event
        for event in payload["trace_events"]
        if event["event"] == "command.completed"
        and event["data"]["command"]["id"] == "kernel.permissions:inspect"
    )
    assert "employees:write" in completed["data"]["expanded_permissions"]
    assert any(
        command["id"] == "employees.manage:create" and command["status"] == "allowed"
        for command in completed["data"]["commands"]
    )


def test_clara_can_inspect_named_employee_permissions(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "stub")

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementation owner.
skills: []
permissions:
  - chat
  - read_local_assets
  - write_trace
  - propose_code_change
""".strip(),
        encoding="utf-8",
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "Alex 有哪些权限？",
            "thread_id": "alex-permissions-inspect-test",
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "员工：Alex (alex)" in payload["reply"]
    assert "repositories.inspect:inspect" in payload["reply"]
    assert "terminal.run:run；缺失权限=terminal:run" in payload["reply"]
    assert _has_command_event(payload, "kernel.permissions:inspect")


def test_terminal_command_streams_progress(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")

    client = TestClient(create_app())
    with client.stream(
        "POST",
        "/api/v1/chat/messages/stream",
        json={
            "message": "terminal.run `pwd`",
            "thread_id": "terminal-stream-test",
            "target_employee_id": "clara",
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert "event: start" in body
    assert "event: delta" in body
    assert "$ pwd" in body
    assert str(workspace) in body
    assert "command.completed" in body
    assert "terminal.run:run" in body


def test_employee_chat_can_use_openai_ai_engine(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "openai")
    monkeypatch.setenv("AITEAMOS_OPENAI_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_OPENAI_MODEL", "gpt-test")

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team OS Manager
summary: Coordinator
personality: Calm and explicit
responsibilities:
  - Explain AITeamOS and route Tickets
skills: []
ai_engine:
  mode: openai_responses
  engine_identity: clara
  preserve_engine_thread: true
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
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "我是 AITeamOS 的 Clara。"
    assert payload["engine_thread_id"] == "engine-clara-who-are-"
    assert any(event["event"] == "ai_engine.openai.completed" for event in payload["trace_events"])
    assert calls[0]["url"] == "https://api.openai.com/v1/responses"
    assert calls[0]["json"]["model"] == "gpt-test"
    assert "Role: AI Team OS Manager" in calls[0]["json"]["instructions"]

    engine_threads = json.loads((workspace / ".aiteamos" / "engine_threads.json").read_text())
    state = engine_threads["clara::who-are-you"]
    assert state["ai_engine"] == "openai_responses"
    assert state["openai_previous_response_id"] == "resp-test-1"


def test_employee_capability_question_uses_openai_agent_bundle_without_kernel_intercept(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "openai")
    monkeypatch.setenv("AITEAMOS_OPENAI_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_OPENAI_MODEL", "gpt-test")

    employees_dir = workspace / ".aiteamos" / "employees"
    skills_dir = workspace / ".aiteamos" / "skills" / "test-engineering"
    employees_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementation owner
personality: Direct and evidence-driven
responsibilities:
  - Implement delegated Tickets and report verification evidence.
skills:
  - test-engineering
permissions:
  - chat
  - manage_tickets
  - read_local_assets
  - write_trace
ai_engine:
  mode: openai_responses
  engine_identity: alex
  preserve_engine_thread: true
handoff_rules:
  - Escalate unclear scope to Clara.
""".strip(),
        encoding="utf-8",
    )
    (skills_dir / "SKILL.md").write_text(
        """
# Test Engineering

> Test execution and validation evidence.

## Procedure
Run focused tests and report evidence.
""".strip(),
        encoding="utf-8",
    )
    calls = []

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "id": "resp-capability-1",
                "model": "gpt-test",
                "output_text": "可以。我可以围绕 Ticket 做实现、证据整理和汇报，但实际 Kernel 执行要有 trace。",
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
            "message": "你能处理tickets吗",
            "thread_id": "alex-capability-question",
            "target_employee_id": "alex",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_employee"]["id"] == "alex"
    assert payload["reply"].startswith("可以。")
    assert payload["run_metadata"]["commands"] == []
    assert any(event["event"] == "command.intercept.skipped" for event in payload["trace_events"])
    assert not _has_command_event(payload, "kernel.permissions:inspect")
    assert calls[0]["url"] == "https://api.openai.com/v1/responses"
    instructions = calls[0]["json"]["instructions"]
    assert "Display name: Alex" in instructions
    assert "Agent context bundle" in instructions
    assert "Skill context:" in instructions
    assert "Test Engineering (test-engineering)" in instructions
    assert "Capability and permission context:" in instructions
    assert "tickets.manage:create" in instructions
    assert "Runtime policy:" in instructions


def test_openai_auth_error_returns_configuration_blocker_without_stub_reply(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "openai")
    monkeypatch.setenv("AITEAMOS_OPENAI_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "bad-test-key")
    monkeypatch.setenv("AITEAMOS_OPENAI_MODEL", "gpt-test")

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
ai_engine:
  mode: openai_responses
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FakeResponse:
        status_code = 401
        text = '{"error":{"message":"Incorrect API key provided: sk-proj-secret","type":"invalid_request_error","code":"invalid_api_key"}}'

        def json(self):
            return {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, json):
            return FakeResponse()

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FakeAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "message": "你具备哪些能力，可以管理ticket, skills, employees吗",
            "thread_id": "openai-auth-error-test",
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "远程调用被配置问题阻止" in payload["reply"]
    assert "file-backed fallback/stub" not in payload["reply"]
    assert "Clara 已收到请求" not in payload["reply"]
    assert payload["run_metadata"]["commands"] == []
    assert payload["run_metadata"]["ai_engine"]["actual_ai_engine"] == "openai_configuration_blocked"
    assert any(event["event"] == "command.intercept.skipped" for event in payload["trace_events"])
    assert any(event["event"] == "ai_engine.remote.configuration_blocked" for event in payload["trace_events"])
    assert not any(event["event"] == "ai_engine.stub.completed" for event in payload["trace_events"])


def test_openai_quota_error_returns_configuration_blocker_without_stub_reply(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "openai")
    monkeypatch.setenv("AITEAMOS_OPENAI_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "quota-test-key")
    monkeypatch.setenv("AITEAMOS_OPENAI_MODEL", "gpt-test")

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
ai_engine:
  mode: openai_responses
  engine_identity: clara
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    class FakeResponse:
        status_code = 429
        text = '{"error":{"message":"You exceeded your current quota, please check your plan and billing details.","type":"insufficient_quota","code":"insufficient_quota"}}'

        def json(self):
            return {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, json):
            return FakeResponse()

    monkeypatch.setattr(chat_routes.httpx, "AsyncClient", FakeAsyncClient)

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/chat/messages",
        json={"message": "你是谁", "thread_id": "openai-quota-error-test", "target_employee_id": "clara"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "远程调用被配置问题阻止" in payload["reply"]
    assert "quota" in payload["reply"] or "额度" in payload["reply"]
    assert "Clara 已收到请求" not in payload["reply"]
    assert payload["run_metadata"]["ai_engine"]["actual_ai_engine"] == "openai_configuration_blocked"
    assert any(event["event"] == "ai_engine.remote.configuration_blocked" for event in payload["trace_events"])
    assert not any(event["event"] == "ai_engine.stub.completed" for event in payload["trace_events"])


def test_employee_chat_can_use_deepseek_ai_engine(tmp_path, monkeypatch):
    workspace = tmp_path
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("AITEAMOS_AI_ENGINE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AITEAMOS_DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("AITEAMOS_DEEPSEEK_THINKING", "disabled")

    employees_dir = workspace / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "clara.yaml").write_text(
        """
id: clara
display_name: Clara
kind: ai
role: AI Team OS Manager
summary: Coordinator
personality: Calm and explicit
responsibilities:
  - Explain AITeamOS and route Tickets
skills: []
ai_engine:
  mode: deepseek_chat_or_file_stub
  engine_identity: clara
  preserve_engine_thread: true
handoff_rules:
  - Ask for human approval before external actions
""".strip(),
        encoding="utf-8",
    )
    conversations_dir = workspace / ".aiteamos" / "conversations"
    conversations_dir.mkdir(parents=True)
    (conversations_dir / "deepseek-who-are-you.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-03T00:00:00+00:00",
                        "role": "user",
                        "content": "上一轮问题",
                        "employee_id": None,
                        "run_id": "run-prev",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-03T00:00:01+00:00",
                        "role": "assistant",
                        "content": "上一轮回答",
                        "employee_id": "clara",
                        "run_id": "run-prev",
                    }
                ),
            ]
        )
        + "\n",
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
                        },
                        "finish_reason": "stop",
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
            "target_employee_id": "clara",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "我是 AITeamOS 的 Clara。"
    assert payload["engine_thread_id"] == "engine-clara-deepseek"
    assert any(event["event"] == "ai_engine.deepseek.completed" for event in payload["trace_events"])
    assert calls[0]["url"] == "https://api.deepseek.com/chat/completions"
    assert calls[0]["json"]["model"] == "deepseek-v4-flash"
    assert calls[0]["json"]["thinking"] == {"type": "disabled"}
    assert calls[0]["json"]["max_tokens"] == 384000
    assert calls[0]["json"]["messages"][0]["role"] == "system"
    assert "Role: AI Team OS Manager" in calls[0]["json"]["messages"][0]["content"]
    assert calls[0]["json"]["messages"][1:4] == [
        {"role": "user", "content": "上一轮问题"},
        {"role": "assistant", "content": "上一轮回答"},
        {"role": "user", "content": "你是谁？"},
    ]

    engine_threads = json.loads((workspace / ".aiteamos" / "engine_threads.json").read_text())
    state = engine_threads["clara::deepseek-who-are-you"]
    assert state["ai_engine"] == "deepseek_chat_completions"
    assert state["deepseek_last_response_id"] == "ds-test-1"
    assert state["assumed_agent_session"] is True
