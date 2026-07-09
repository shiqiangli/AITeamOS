from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

from fastapi.testclient import TestClient
import yaml

from aiteamos_api.main import create_app
from aiteamos_api.read.asset_candidate_service import (
    AssetCandidateRecord,
    list_asset_candidates,
    list_asset_records,
    list_asset_reviews,
    upsert_asset_candidate,
)
from aiteamos_api.read import memory_service
from aiteamos_api.read.chat_action_plan import ChatActionPlan
from aiteamos_api.read.chat_governance_service import (
    ChatGovernanceInput,
    ChatGovernanceService,
    build_chat_governance_input,
)
from aiteamos_api.read.chat_models import (
    ChatEmployeeSummary,
    ChatMessageRequest,
    ChatRunContext,
    ChatTraceEvent,
    ConversationMessage,
)
from aiteamos_api.read.chat_response_metadata import build_run_metadata
from aiteamos_api.read.employee_handoff_service import choose_employee_for_goal
from aiteamos_api.read.execution_contract import ExecutionRequest, ExecutionResult, TicketBinding
from aiteamos_api.read.execution_context_service import ExecutionContextService
from aiteamos_api.read.execution_session_store import load_execution_sessions, save_execution_session
from aiteamos_api.read.execution_approval_service import ExecutionApprovalReviewRequest, list_execution_approvals, review_execution_approval
from aiteamos_api.read.execution_dispatch_service import ExecutionDispatchService
from aiteamos_api.read.execution_result_ingestion_service import ExecutionResultIngestionService
from aiteamos_api.read.langchain_model_provider import LangChainModelResult
from aiteamos_api.read.memory_service import (
    GraphitiSettingsUpdateRequest,
    MemoryCandidateCreateRequest,
    approve_memory_candidate,
    create_memory_candidate,
    list_memory_candidates,
    record_memory_recall_usage,
    update_graphiti_settings,
)
from aiteamos_api.read.repository_service import CodeRepositoryUpsertRequest, upsert_code_repository
from aiteamos_api.read.runtime_executors.langgraph_executor import LangGraphExecutor
from aiteamos_api.read.ticket_service import (
    TicketCreateRequest,
    TicketBackendSettingsUpdateRequest,
    TicketReportRequest,
    TicketStateTransitionRequest,
    add_ticket_report,
    create_ticket,
    employee_analytics,
    employee_work_ledger,
    get_ticket,
    ticket_graph_projection,
    transition_ticket_state,
    update_ticket_backend_settings,
)
from aiteamos_api.read.ticket_loop_service import (
    TicketLoopControlRequest,
    TicketAutonomousLoopService,
    TicketLoopEnqueueRequest,
    TicketLoopPolicyUpdateRequest,
    TicketLoopQueuePumpRequest,
    TicketLoopQueueWorker,
    TicketLoopQueueWorkerControlRequest,
    TicketLoopResumeRequest,
    TicketLoopRunRequest,
    TicketLoopStepRequest,
    control_ticket_loop,
    enqueue_ticket_loop,
    get_ticket_loop_run,
    list_ticket_loop_queue,
    list_ticket_loop_runs,
    pump_ticket_loop_queue,
    resume_ticket_loop,
    ticket_loop_timeline,
    ticket_loop_queue_status,
    update_ticket_loop_policy,
)


class _FakeLangChainModelProvider:
    def __init__(self, *, content_by_engine: dict[str, str] | None = None) -> None:
        self.content_by_engine = content_by_engine or {}
        self.calls: list[dict] = []

    async def ainvoke(self, *, selected_engine, runtime, messages, max_tokens=None):
        self.calls.append(
            {
                "selected_engine": selected_engine,
                "model": runtime.deepseek_model() if selected_engine == "deepseek" else runtime.openai_model(),
                "messages": messages,
                "max_tokens": max_tokens,
            }
        )
        content = self.content_by_engine.get(selected_engine, f"{selected_engine} LangChain response.")
        return LangChainModelResult(
            provider=selected_engine,
            content=content,
            model=self.calls[-1]["model"],
            response_id=f"lc-{selected_engine}-1",
            usage={"total_tokens": 11},
            response_metadata={"id": f"lc-{selected_engine}-1", "model_name": self.calls[-1]["model"]},
            provider_ref={
                "provider": selected_engine,
                "response_id": f"lc-{selected_engine}-1",
                "model": self.calls[-1]["model"],
                "model_provider_boundary": "langchain",
            },
        )
from aiteamos_api.read.universal_agent_tools import UniversalAgentToolRegistry


def _use_local_ticket_backend() -> None:
    update_ticket_backend_settings(
        TicketBackendSettingsUpdateRequest(mode="local_file", local_file_path=".aiteamos/tickets/index.json")
    )


def test_ticket_loop_employee_profiles_load_without_chat_route_dependency(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    employees_dir = tmp_path / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementation-focused Employee.
skills:
  - backend-api-implementation
handoff_policy:
  can_receive_handoffs: true
  accepts_lanes:
    - rd
current_load:
  active_ticket_count: 1
  status: active
""".strip(),
        encoding="utf-8",
    )

    from aiteamos_api.read import ticket_loop_service

    profiles = ticket_loop_service._employee_profiles()
    by_id = {profile["id"]: profile for profile in profiles}
    assert by_id["alex"]["handoff_policy"]["accepts_lanes"] == ["rd"]
    assert by_id["alex"]["current_load"]["status"] == "active"
    assert by_id["clara"]["system"]["protected"] is True
    assert "chat_routes" not in Path(ticket_loop_service.__file__).read_text(encoding="utf-8")


def test_chat_runtime_factory_employee_profiles_use_shared_service(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    employees_dir = tmp_path / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementation-focused Employee.
skills:
  - backend-api-implementation
ai_engine:
  mode: external_or_file_stub
  engine_identity: alex
  default_engine: claude_code
  preserve_engine_thread: true
""".strip(),
        encoding="utf-8",
    )

    from aiteamos_api.read import chat_runtime_factory

    profiles = chat_runtime_factory.load_employees()
    by_id = {profile["id"]: profile for profile in profiles}
    assert by_id["alex"]["skill_refs"] == ["backend-api-implementation"]
    assert by_id["alex"]["ai_engine"]["default_engine"] == "claude_code"
    assert by_id["alex"]["preferred_runtime"] == "claude_code"
    assert by_id["clara"]["system"]["protected"] is True

    source = Path(chat_runtime_factory.__file__).read_text(encoding="utf-8")
    assert "load_employee_profiles" in source
    assert "import yaml" not in source
    assert "def normalize_employee_profile" not in source
    assert "def ensure_clara_system_employee" not in source


def test_chat_runtime_factory_skill_titles_use_shared_service(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    skill_dir = tmp_path / ".aiteamos" / "skills" / "runtime-engineering"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Runtime Engineering\n", encoding="utf-8")

    from aiteamos_api.read import chat_runtime_factory

    assert chat_runtime_factory.skill_titles(["runtime-engineering", "missing-skill"]) == [
        "Runtime Engineering",
        "missing-skill",
    ]

    source = Path(chat_runtime_factory.__file__).read_text(encoding="utf-8")
    assert "chat_skill_titles" in source
    assert "SKILL.md" not in source
    assert "read_text" not in source


def test_chat_runtime_factory_employee_projection_uses_shared_service(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))

    from aiteamos_api.read import chat_runtime_factory

    employee = chat_runtime_factory.employee_summary(
        {
            "id": "alex",
            "display_name": "Alex",
            "kind": "ai",
            "role": "AI RD / Implementer",
            "summary": "Implementation-focused Employee.",
            "skills": ["backend-api-implementation"],
            "ai_engine": {"default_engine": "claude_code", "preserve_engine_thread": True},
            "current_load": {"status": "busy", "active_ticket_count": 1},
        }
    )

    assert employee.id == "alex"
    assert employee.default_ai_engine == "claude_code"
    assert employee.default_thread_id == "employee-alex-default"
    assert employee.current_load["status"] in {"busy", "active"}
    assert chat_runtime_factory.select_employee(
        [{"id": "alex", "display_name": "Alex"}, {"id": "clara", "display_name": "Clara"}],
        requested_employee_id=None,
        message="@alex please inspect this",
    )["id"] == "alex"

    source = Path(chat_runtime_factory.__file__).read_text(encoding="utf-8")
    assert "ChatEmployeeProjectionService" in source
    assert "employee_current_load" not in source
    assert "normalize_employee_default_ai_engine" not in source


def test_chat_runtime_factory_thread_metadata_uses_shared_service(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    employees_dir = tmp_path / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementation-focused Employee.
skills: []
""".strip(),
        encoding="utf-8",
    )
    conversations_dir = tmp_path / ".aiteamos" / "conversations"
    conversations_dir.mkdir(parents=True)
    thread_id = "employee-alex-existing"
    (conversations_dir / f"{thread_id}.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-21T00:00:00+00:00",
                        "role": "user",
                        "content": "Please continue RD-0001",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-21T00:01:00+00:00",
                        "role": "assistant",
                        "content": "Working on RD-0001.",
                        "employee_id": "alex",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    from aiteamos_api.read import chat_runtime_factory

    assert chat_runtime_factory.thread_index_path() == ".aiteamos/threads/index.json"
    assert chat_runtime_factory.conversation_path_for_thread(thread_id) == f".aiteamos/conversations/{thread_id}.jsonl"

    index = chat_runtime_factory.hydrate_thread_index()
    summary = chat_runtime_factory.thread_summary_from_record(thread_id, index["threads"][thread_id])

    assert summary.employee_id == "alex"
    assert summary.title == "Please continue RD-0001"
    assert summary.message_count == 2
    assert chat_runtime_factory.infer_thread_employee_id(
        thread_id,
        [ChatEmployeeSummary(id="alex", display_name="Alex", role="AI RD / Implementer")],
    ) == "alex"

    context = ChatRunContext(
        request=ChatMessageRequest(message="Please continue RD-0001"),
        selected_profile={"id": "alex"},
        employee=ChatEmployeeSummary(id="alex", display_name="Alex", role="AI RD / Implementer"),
        selected_ai_engine="deepseek",
        thread_id=thread_id,
        run_id="run-thread-metadata",
        ticket_keys=["RD-0001"],
        run_dirs={"traces": tmp_path / ".aiteamos" / "traces"},
        engine_state={},
        engine_thread_id="engine-thread",
        skills=[],
        memories=[],
        memory_refs=[],
        recent_messages=[],
        trace_events=[],
    )
    updated = chat_runtime_factory.record_chat_thread_turn(
        context,
        last_message_at="2026-06-21T00:02:00+00:00",
    )
    assert updated.last_message_at == "2026-06-21T00:02:00+00:00"
    assert chat_runtime_factory.hydrate_thread_index()["active_by_employee"]["alex"] == thread_id

    source = Path(chat_runtime_factory.__file__).read_text(encoding="utf-8")
    assert "ChatThreadMetadataService" in source
    assert "chat_thread_store" not in source
    assert "first_user = next(" not in source
    assert "record.update({" not in source
    assert "write_thread_index(" not in source


def test_chat_runtime_factory_ticket_keys_use_shared_service() -> None:
    from aiteamos_api.read import chat_runtime_factory

    assert chat_runtime_factory.extract_ticket_keys(
        "Link pv-1001 with ENG-42 and ticket-Release.Ready",
        "eng-42",
    ) == ["ENG-42", "pv-1001", "ticket-release.ready"]

    source = Path(chat_runtime_factory.__file__).read_text(encoding="utf-8")
    assert "chat_ticket_key_service" in source
    assert "def normalize_ticket_key" not in source
    assert "def extract_ticket_keys" not in source
    assert "TICKET_KEY_RE" not in source


def test_chat_runtime_factory_governance_input_uses_shared_builder(tmp_path) -> None:
    from aiteamos_api.read import chat_runtime_factory

    source = Path(chat_runtime_factory.__file__).read_text(encoding="utf-8")
    assert "build_chat_governance_input" in source
    assert "employee_payload = context.employee.model_dump" not in source
    assert "ChatGovernanceInput(" not in source

    context = ChatRunContext(
        request=ChatMessageRequest(
            message="Please continue RD-0001",
            target_employee_id="alex",
            thread_id="employee-alex-default",
            ticket_key="rd-0001",
            approval_ref=" approval-1 ",
            runtime_config={"source": "test"},
        ),
        selected_profile={
            "id": "alex",
            "display_name": "Alex",
            "permissions": [" tickets:write ", "", "repo:read"],
        },
        employee=ChatEmployeeSummary(
            id="alex",
            display_name="Alex",
            role="AI RD / Implementer",
            skills=["runtime-engineering"],
        ),
        selected_ai_engine="deepseek",
        thread_id="employee-alex-default",
        run_id="run-test",
        ticket_keys=["rd-0001"],
        run_dirs={"traces": tmp_path / ".aiteamos" / "traces"},
        engine_state={},
        engine_thread_id="thread-alex",
        skills=["Runtime Engineering"],
        memories=[],
        memory_refs=[{"id": "mem-1"}],
        recent_messages=[
            ConversationMessage(timestamp="2026-06-21T00:00:00+00:00", role="user", content="Earlier question"),
            ConversationMessage(timestamp="2026-06-21T00:01:00+00:00", role="tool", content="hidden tool"),
            ConversationMessage(timestamp="2026-06-21T00:02:00+00:00", role="assistant", content="   "),
            ConversationMessage(timestamp="2026-06-21T00:03:00+00:00", role="assistant", content="Earlier answer"),
        ],
        trace_events=[
            ChatTraceEvent(event="message.received", detail="ok", data={}),
        ],
    )
    trace_path = tmp_path / ".aiteamos" / "traces" / "run-test.jsonl"

    payload = build_chat_governance_input(
        context,
        trace_path=trace_path,
        workspace_root=tmp_path,
        employee_profiles=[{"id": "alex"}, {"id": "clara"}],
    )

    assert payload.message == "Please continue RD-0001"
    assert payload.employee["id"] == "alex"
    assert payload.employee["skill_titles"] == ["Runtime Engineering"]
    assert payload.employee["permissions"] == [" tickets:write ", "repo:read"]
    assert payload.employee_profiles == [{"id": "alex"}, {"id": "clara"}]
    assert payload.ticket_keys == ["rd-0001"]
    assert payload.memory_refs == [{"id": "mem-1"}]
    assert payload.trace_ref == ".aiteamos/traces/run-test.jsonl"
    assert payload.recent_messages == [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
    ]
    assert payload.workspace_id == str(tmp_path)
    assert payload.approval_ref == "approval-1"
    assert payload.runtime_config == {"source": "test"}


def test_chat_runtime_factory_prepare_chat_run_uses_shared_service(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    employees_dir = tmp_path / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        """
id: alex
display_name: Alex
kind: ai
role: AI RD / Implementer
summary: Implementation-focused Employee.
skills:
  - runtime-engineering
permissions:
  - tickets:write
ai_engine:
  default_engine: deepseek
""".strip(),
        encoding="utf-8",
    )

    from aiteamos_api.read import chat_runtime_factory

    assert chat_runtime_factory.ai_engine_runtime().selected_engine_for_employee("deepseek") == "deepseek"

    context = chat_runtime_factory.prepare_chat_run(
        ChatMessageRequest(
            message="@alex please continue rd-0001",
            ticket_key="ENG-42",
            runtime_config={
                "source": "aiteamos_workbench_graph",
                "run_id": "graph-run-42",
            },
        )
    )

    assert context.run_id == "graph-run-42"
    assert context.employee.id == "alex"
    assert context.thread_id == "employee-alex-default"
    assert context.ticket_keys == ["ENG-42", "rd-0001"]
    assert context.selected_ai_engine == "deepseek"
    assert context.engine_thread_id
    assert context.run_dirs["traces"] == tmp_path / ".aiteamos" / "traces"
    assert [event.event for event in context.trace_events] == [
        "message.received",
        "employee.selected",
        "context.loaded",
        "engine_thread.resolved",
        "ticket.detected",
    ]
    assert context.trace_events[0].data["run_id"] == "graph-run-42"
    assert context.trace_events[2].data["recent_message_count"] == 0
    assert context.trace_events[4].data["ticket_keys"] == ["ENG-42", "rd-0001"]

    source = Path(chat_runtime_factory.__file__).read_text(encoding="utf-8")
    assert "ChatRunPreparationService" in source
    assert "ChatRunContext(" not in source
    assert "context_assets = build_initial_chat_context_assets" not in source
    assert "engine_thread_state(" not in source
    assert "engine_thread_id(" not in source
    assert "event=\"message.received\"" not in source


def test_chat_runtime_factory_execution_trace_uses_shared_service(tmp_path) -> None:
    from aiteamos_api.read import chat_runtime_factory

    context = ChatRunContext(
        request=ChatMessageRequest(message="hello"),
        selected_profile={"id": "alex"},
        employee=ChatEmployeeSummary(id="alex", display_name="Alex", role="AI RD / Implementer"),
        selected_ai_engine="deepseek",
        thread_id="thread-trace",
        run_id="run-trace",
        ticket_keys=["rd-0001"],
        run_dirs={"traces": tmp_path / ".aiteamos" / "traces"},
        engine_state={},
        engine_thread_id="engine-thread",
        skills=[],
        memories=[],
        memory_refs=[],
        recent_messages=[],
        trace_events=[],
    )
    request = ExecutionRequest(
        request_id="run-trace",
        employee_id="alex",
        ticket_id="rd-0001",
        ticket_binding=TicketBinding(mode="existing", ticket_id="rd-0001", required=True),
        action_plan=ChatActionPlan(action="answer_only", arguments={"message": "hello"}),
        task_context={
            "universal_context": {
                "version": "universal_context.v1",
                "summary": {
                    "employee_id": "alex",
                    "ticket_id": "rd-0001",
                    "related_ticket_count": "2",
                    "relevant_asset_count": "3",
                    "recalled_memory_count": "4",
                    "prior_evidence_count": "5",
                    "setup_blocker_count": "6",
                },
                "backend_context": {"ticket_backend": {"status": "ready"}},
                "provenance_summary": [{"kind": "employee"}, {"kind": "ticket"}],
            }
        },
        trace_context={
            "planning_events": [
                {"event": "planner.ready", "detail": "Planner ready.", "data": {"source": "test"}},
            ]
        },
    )
    result = ExecutionResult(
        request_id="run-trace",
        executor_id="local_tool",
        status="completed",
        report="Done.",
        output_ticket_id="rd-0001",
        executor_session_ref="session-1",
        checkpoint_ref="checkpoint-1",
        tool_events=[
            {"event": "command.completed", "detail": "Command done.", "data": {"command_id": "custom.command"}},
            {"event": "ai_engine.remote.completed", "detail": "Model done.", "data": {"provider": "deepseek"}},
        ],
        errors=[
            {"reason": "ai_engine_configuration_blocker", "detail": "missing key"},
        ],
    )

    trace_data = chat_runtime_factory.universal_context_trace_data(request)
    assert trace_data["related_ticket_count"] == 2
    assert trace_data["ticket_backend_status"] == "ready"

    events = chat_runtime_factory.execution_trace_events(context, request, result)
    event_names = [event.event for event in events]
    assert event_names[:6] == [
        "planner.ready",
        "chat.action_plan.completed",
        "execution.request.created",
        "execution.context.loaded",
        "execution.dispatch.completed",
        "execution.runtime.completed",
    ]
    assert "command.intercept.skipped" in event_names
    assert "command.completed" in event_names
    assert "ai_engine.remote.completed" in event_names
    assert "ai_engine.remote.configuration_blocked" in event_names
    assert events[1].data["kernel_command"] == "none"
    assert next(event for event in events if event.event == "execution.context.loaded").data["setup_blocker_count"] == 6

    source = Path(chat_runtime_factory.__file__).read_text(encoding="utf-8")
    assert "chat_execution_trace_service" in source
    assert "task_context = execution_request.task_context" not in source
    assert "kernel_plan_from_chat_action_plan" not in source
    assert "is_result_ingestion_command" not in source
    assert "ai_engine.remote.configuration_blocked" not in source


def test_chat_runtime_factory_run_metadata_uses_shared_service(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))

    engines_path = tmp_path / ".aiteamos" / "ai_engines.json"
    engines_path.parent.mkdir(parents=True)
    engines_path.write_text(
        json.dumps(
            {
                "engines": {
                    "deepseek": {
                        "model": "deepseek-v4-flash",
                        "enabled": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    from aiteamos_api.read import chat_runtime_factory

    context = ChatRunContext(
        request=ChatMessageRequest(message="Please continue RD-0001"),
        selected_profile={"id": "alex"},
        employee=ChatEmployeeSummary(
            id="alex",
            display_name="Alex",
            role="AI RD / Implementer",
            default_ai_engine="deepseek",
        ),
        selected_ai_engine="deepseek",
        thread_id="thread-metadata",
        run_id="run-metadata",
        ticket_keys=["RD-0001"],
        run_dirs={"traces": tmp_path / ".aiteamos" / "traces"},
        engine_state={"ai_engine": "deepseek_chat_completions"},
        engine_thread_id="engine-thread-initial",
        skills=[],
        memories=[],
        memory_refs=[{"memory_id": "mem-1"}],
        recent_messages=[],
        trace_events=[],
    )
    trace_path = tmp_path / ".aiteamos" / "traces" / "run-metadata.jsonl"
    trace_events = [
        ChatTraceEvent(
            event="ai_engine.deepseek.completed",
            detail="Model completed.",
            data={"provider": "deepseek", "model": "deepseek-v4-flash"},
        )
    ]

    metadata = chat_runtime_factory.build_run_metadata(
        context,
        final_engine_thread_id="engine-thread-final",
        trace_events=trace_events,
        trace_path=trace_path,
    )

    assert metadata["run_id"] == "run-metadata"
    assert metadata["thread_id"] == "thread-metadata"
    assert metadata["employee"] == {
        "id": "alex",
        "display_name": "Alex",
        "role": "AI RD / Implementer",
    }
    assert metadata["ticket_keys"] == ["RD-0001"]
    assert metadata["recalled_memory_refs"] == [{"memory_id": "mem-1"}]
    assert metadata["ai_engine"]["selected_ai_engine"] == "deepseek"
    assert metadata["ai_engine"]["employee_default_ai_engine"] == "deepseek"
    assert metadata["ai_engine"]["actual_ai_engine"] == "deepseek_chat_completions"
    assert metadata["ai_engine"]["model"] == "deepseek-v4-flash"
    assert metadata["ai_engine"]["engine_thread_id"] == "engine-thread-final"
    assert metadata["trace"]["path"] == ".aiteamos/traces/run-metadata.jsonl"
    assert metadata["trace"]["event_count"] == 1

    source = Path(chat_runtime_factory.__file__).read_text(encoding="utf-8")
    assert "chat_run_metadata_service" in source
    assert "build_run_metadata_data" not in source
    assert "employee_display_name=context.employee.display_name" not in source
    assert "trace_relative_path=str(trace_path.relative_to" not in source


def test_chat_runtime_factory_execution_engine_state_uses_shared_service(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))

    from aiteamos_api.read import chat_runtime_factory

    context = ChatRunContext(
        request=ChatMessageRequest(message="hello"),
        selected_profile={"id": "alex"},
        employee=ChatEmployeeSummary(id="alex", display_name="Alex", role="AI RD / Implementer"),
        selected_ai_engine="deepseek",
        thread_id="thread-engine-state",
        run_id="run-engine-state",
        ticket_keys=[],
        run_dirs={"traces": tmp_path / ".aiteamos" / "traces"},
        engine_state={"engine_thread_id": "existing-engine-thread"},
        engine_thread_id="existing-engine-thread",
        skills=[],
        memories=[],
        memory_refs=[],
        recent_messages=[],
        trace_events=[],
    )
    result = ExecutionResult(
        request_id="run-engine-state",
        executor_id="local_tool",
        status="completed",
        report="Done.",
        tool_events=[
            {
                "event": "ai_engine.deepseek.completed",
                "data": {
                    "provider_ref": {
                        "provider": "deepseek",
                        "response_id": "deepseek-response-42",
                        "model": "deepseek-v4-flash",
                    }
                },
            }
        ],
    )

    engine_state = chat_runtime_factory.execution_engine_state(context, result)

    assert engine_state is not None
    assert engine_state["ai_engine"] == "deepseek_chat_completions"
    assert engine_state["engine_thread_id"] == "existing-engine-thread"
    assert engine_state["deepseek_last_response_id"] == "deepseek-response-42"
    assert engine_state["model"] == "deepseek-v4-flash"

    source = Path(chat_runtime_factory.__file__).read_text(encoding="utf-8")
    assert "chat_execution_engine_state_service" in source
    assert "employee_id=context.employee.id" not in source
    assert "current_state=context.engine_state" not in source


def _write_fake_runtime(path, body: str) -> str:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


class _FakeHttpResponse:
    def __init__(self, payload: dict | None = None, *, status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text
        self.content = (text or (str(payload) if payload is not None else "")).encode("utf-8")

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON payload")
        return self._payload


def test_execution_contract_supports_ticket_binding_modes():
    plan = ChatActionPlan(action="answer_only", arguments={"message": "hello"})
    request = ExecutionRequest(
        request_id="exec-test",
        employee_id="clara",
        ticket_id="",
        ticket_binding=TicketBinding(mode="none", required=False),
        action_plan=plan,
    )

    assert request.ticket_binding.mode == "none"
    assert request.capability_grants == []
    assert request.action_plan.action == "answer_only"


def test_execution_result_ingestion_rehydrates_idempotent_handoff_tool_event(monkeypatch, tmp_path):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Idempotent handoff Ticket",
            description="Repeated ingestion should rehydrate durable handoff refs without duplicate Ticket writes.",
            ticket_type="rd",
            assigned_employee_id="clara",
            assigned_role="AI Team OS Manager",
            source_thread_id="thread-idempotent-handoff",
            source_run_id="seed-idempotent-handoff",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    artifact = {
        "kind": "employee_handoff_request",
        "ticket_id": ticket.id,
        "from_employee_id": "clara",
        "from_role": "AI Team OS Manager",
        "to_employee_id": "victor",
        "to_role": "AI RD / Implementer",
        "content": "Policy selected Victor for runtime ownership.",
        "lane": "rd",
        "confidence": 0.95,
        "policy": {
            "policy_aware": True,
            "matched_memory_scopes": ["employee:victor"],
            "risk_level": "critical",
            "risk_allowed": True,
        },
    }
    request = ExecutionRequest(
        request_id="run-idempotent-handoff",
        employee_id="clara",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="answer_only", arguments={"ticket_id": ticket.id}),
        task_context={"employee": {"role": "AI Team OS Manager"}},
        trace_context={"thread_id": "thread-idempotent-handoff", "run_id": "run-idempotent-handoff", "trace_ref": "trace://idempotent-handoff"},
    )
    service = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos")
    first = service.ingest(
        request,
        ExecutionResult(
            request_id=request.request_id,
            executor_id="universal_employee_agent",
            status="completed",
            report="Prepared durable handoff.",
            output_ticket_id=ticket.id,
            artifacts=[artifact],
            trace_ref="trace://idempotent-handoff",
        ),
    )
    first_ticket = get_ticket(ticket.id)
    assert first_ticket is not None
    assert first_ticket.assigned_employee_id == "victor"
    assert sum(1 for report in first_ticket.reports if report.report_type == "employee_handoff") == 1
    assert _command_ids(first) == ["tickets.manage:handoff"]

    rehydrated = service.ingest(
        request,
        ExecutionResult(
            request_id=request.request_id,
            executor_id="universal_employee_agent",
            status="completed",
            report="Prepared durable handoff again.",
            output_ticket_id=ticket.id,
            artifacts=[artifact],
            trace_ref="trace://idempotent-handoff",
        ),
    )

    second_ticket = get_ticket(ticket.id)
    assert second_ticket is not None
    assert sum(1 for report in second_ticket.reports if report.report_type == "employee_handoff") == 1
    assert _command_ids(rehydrated) == ["tickets.manage:handoff"]
    assert rehydrated.learning_delta["employee_handoff"]["to_employee_id"] == "victor"
    assert rehydrated.learning_delta["idempotent_ingestion_rehydrated"] is True
    event = rehydrated.tool_events[0]
    assert event["data"]["rehydrated"] is True
    assert event["data"]["report_id"] == first_ticket.reports[-1].id


def _command_ids(result: ExecutionResult) -> list[str]:
    ids: list[str] = []
    for event in result.tool_events:
        data = event.get("data") if isinstance(event, dict) else {}
        command = data.get("command") if isinstance(data, dict) else {}
        if isinstance(command, dict) and command.get("id"):
            ids.append(str(command["id"]))
    return ids


def test_chat_run_metadata_surfaces_external_runtime_governance_refs():
    request = ExecutionRequest(
        request_id="exec-approved",
        employee_id="alex",
        ticket_id="rd-7001",
        ticket_binding=TicketBinding(mode="existing", ticket_id="rd-7001", required=True),
        action_plan=ChatActionPlan(action="implement_ticket", arguments={"ticket_id": "rd-7001"}),
        task_context={
            "task_summary": "Implement Ticket rd-7001.",
            "ticket": {"id": "rd-7001"},
            "setup_blockers": [{"reason": "graphiti_setup_blocker", "detail": "Graphiti is not configured."}],
            "exclusions": ["raw secrets"],
        },
        capability_grants=["tickets:read", "repo:read", "repo:write"],
        approval_policy={
            "require_approval_for": ["repo:write"],
            "on_missing_approval": "return_needs_approval",
            "approval_refs": ["approval-runtime-7001"],
            "approved_capabilities": ["repo:write"],
        },
        trace_context={"run_id": "exec-approved", "trace_ref": ".aiteamos/traces/exec-approved.jsonl"},
    )
    result = ExecutionResult(
        request_id="exec-approved",
        executor_id="claude_code",
        status="completed",
        report="Approved external runtime mutation completed.",
        output_ticket_id="rd-7001",
        artifacts=[
            {
                "kind": "external_runtime_cli_execution",
                "ref": "external-runtime:claude_code:cli:exec-approved",
                "approval_refs": ["approval-runtime-7001"],
                "approved_capabilities": ["repo:write"],
            },
            {"kind": "repo_patch", "changed_files": ["services/api/aiteamos_api/read/chat_response_metadata.py"]},
        ],
        evidence=[{"kind": "test_evidence", "ref": "pytest::chat-run-metadata::passed"}],
        trace_ref=".aiteamos/traces/exec-approved.jsonl",
        executor_session_ref="claude-code-session-7001",
        checkpoint_ref="checkpoint-7001",
        tool_events=[
            {
                "event": "command.completed",
                "data": {
                    "ticket": {
                        "id": "rd-7001",
                        "reports": [
                            {
                                "id": "report-runtime-7001",
                                "report_type": "external_runtime_repo_mutation",
                                "evidence": ["pytest::chat-run-metadata::passed"],
                            }
                        ],
                    }
                },
            }
        ],
    )
    events = [
        SimpleNamespace(event="execution.request.created", detail="", data=request.model_dump(mode="json")),
        SimpleNamespace(event="execution.dispatch.completed", detail="", data=result.model_dump(mode="json")),
    ]

    metadata = build_run_metadata(
        run_id="exec-approved",
        thread_id="thread-approved",
        employee_id="alex",
        employee_display_name="Alex",
        employee_role="AI RD / Implementer",
        employee_default_ai_engine="claude_code",
        ticket_keys=["rd-7001"],
        memory_refs=[],
        selected_ai_engine="claude_code",
        selected_model=None,
        engine_state={},
        final_engine_thread_id="engine-thread-approved",
        trace_events=events,
        trace_relative_path=".aiteamos/traces/exec-approved.jsonl",
        created_at="2026-06-08T00:00:00Z",
    )

    assert metadata["execution"]["executor_id"] == "claude_code"
    assert metadata["execution"]["trace"]["executor_session_ref"] == "claude-code-session-7001"
    assert metadata["execution"]["governance"]["approval_refs"] == ["approval-runtime-7001"]
    assert metadata["execution"]["governance"]["approved_capabilities"] == ["repo:write"]
    assert metadata["execution"]["governance"]["ticket_bound"] is True
    assert metadata["execution"]["governance"]["approval_bound"] is True
    assert metadata["execution"]["governance"]["evidence_bound"] is True
    assert metadata["execution"]["result"]["ticket_report_refs"] == [
        {"kind": "external_runtime_repo_mutation", "ref": "report-runtime-7001", "evidence_count": "1"}
    ]
    assert metadata["approval"]["approval_refs"] == ["approval-runtime-7001"]
    assert metadata["approval"]["approved_capabilities"] == ["repo:write"]
    assert metadata["scoped_context"]["setup_blockers"][0]["reason"] == "graphiti_setup_blocker"


async def test_langgraph_executor_runs_and_streams_execution_events():
    executor = LangGraphExecutor()
    request = ExecutionRequest(
        request_id="exec-stream",
        employee_id="clara",
        ticket_binding=TicketBinding(mode="none", required=False),
        action_plan=ChatActionPlan(action="answer_only", arguments={"message": "hello"}),
        task_context={"task_summary": "hello", "employee": {"display_name": "Clara"}},
    )

    result = await executor.run(request)
    events = [event async for event in executor.stream(request)]

    assert result.status == "completed"
    assert result.executor_id == "langgraph"
    assert result.executor_session_ref == "lg-exec-stream"
    assert [event.event for event in events] == ["started", "delta", "completed"]


async def test_langgraph_executor_native_interrupt_resumes_from_checkpoint(tmp_path):
    executor = LangGraphExecutor(workspace_dir=tmp_path / ".aiteamos")
    request = ExecutionRequest(
        request_id="exec-native-interrupt",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id="rd-native",
        ticket_binding=TicketBinding(mode="existing", ticket_id="rd-native", required=True),
        action_plan=ChatActionPlan(action="implement_ticket", arguments={"ticket_id": "rd-native"}),
        task_context={"task_summary": "Implement Ticket rd-native through a governed runtime."},
        capability_grants=["repo:write", "ticket:evidence:write"],
        permission_policy={
            "selected_executor": "universal_employee_agent",
            "requested_runtime_executor": "claude_code",
        },
        approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
        expected_outputs={"report": True, "evidence": True, "artifacts": True},
        trace_context={"run_id": "exec-native-interrupt", "trace_ref": ".aiteamos/traces/exec-native-interrupt.jsonl"},
    )

    blocked = await executor.run(request)

    assert blocked.status == "needs_approval"
    assert blocked.approval_requests[0]["required_capability"] == "repo:write"
    assert blocked.approval_requests[0]["executor_id"] == "claude_code"
    assert blocked.learning_delta["checkpoint_status"]["mode"] == "sqlite"
    assert blocked.learning_delta["native_interrupts"][0]["value"]["required_capability"] == "repo:write"
    assert (tmp_path / ".aiteamos" / "langgraph" / "langgraph_checkpoints.sqlite").exists()

    approved = request.model_copy(
        update={
            "request_id": "exec-native-interrupt-approved",
            "approval_policy": {
                "require_approval_for": ["repo:write"],
                "on_missing_approval": "return_needs_approval",
                "approval_refs": ["approval-native-interrupt-1"],
                "approved_capabilities": ["repo:write"],
            },
            "task_context": {
                **request.task_context,
                "resume_checkpoint_state": {
                    "source_state_ref": blocked.approval_requests[0]["source_state_ref"],
                    "checkpoint_ref": blocked.approval_requests[0]["checkpoint_ref"],
                    "current_graph_node": blocked.approval_requests[0]["current_graph_node"],
                },
            },
            "trace_context": {
                **request.trace_context,
                "approval_resume": True,
                "source_request_id": request.request_id,
                "resume_from_checkpoint_ref": blocked.approval_requests[0]["checkpoint_ref"],
                "source_state_ref": blocked.approval_requests[0]["source_state_ref"],
                "resume_graph_node": blocked.approval_requests[0]["current_graph_node"],
            },
        }
    )

    resumed = await executor.run(approved)

    assert resumed.status == "partial"
    assert resumed.approval_requests == []
    assert resumed.artifacts[0]["kind"] == "external_runtime_resume_request"
    assert resumed.artifacts[0]["executor_id"] == "claude_code"
    assert resumed.artifacts[0]["approval_refs"] == ["approval-native-interrupt-1"]
    assert any(event["event"] == "langgraph.approval.resume_command" for event in resumed.tool_events)
    assert any(event["event"] == "langgraph.approval.resumed" for event in resumed.tool_events)
    assert resumed.learning_delta["checkpoint"]["thread_id"] == request.request_id
    assert resumed.learning_delta["checkpoint"]["next"] == []


def test_execution_context_builds_universal_context_with_ticket_assets_and_memory_refs(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Universal context contract",
            description="LangGraph should receive compact Ticket, Asset, Memory, and Employee context.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-universal-context",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content="Universal context report with verification evidence.",
            evidence=["pytest::universal-context::passed"],
            report_type="progress",
            source_run_id="run-universal-context-report",
        ),
    )

    context = ExecutionContextService().build(
        message="Summarize the Universal context contract for LangGraph.",
        employee={
            "id": "alex",
            "display_name": "Alex",
            "role": "AI RD / Implementer",
            "summary": "Implementation owner",
            "skills": ["test-engineering"],
            "skill_titles": ["Test Engineering"],
        },
        employee_profiles=[
            {
                "id": "alex",
                "display_name": "Alex",
                "role": "AI RD / Implementer",
                "summary": "Implementation owner",
                "skills": ["test-engineering"],
                "skill_refs": ["test-engineering"],
                "capability_tags": ["backend-api-implementation", "test-engineering"],
                "permissions": ["chat", "manage_tickets"],
                "personality": "direct, evidence-driven",
                "memory_scopes": ["aiteamos", "employee:alex"],
                "preferred_runtime": "claude_code",
                "permission_policy": {"requires_approval_for": ["repo:write"]},
                "handoff_policy": {"can_receive_handoffs": True, "escalate_to": "clara"},
                "current_load": {"active_ticket_count": 2, "status": "busy"},
            }
        ],
        recent_messages=[{"role": "user", "content": "Previous context question."}],
        ticket_keys=[ticket.id],
        memory_refs=[
            {
                "memory_id": "mem-universal-context",
                "asset_id": "mem-universal-context",
                "content": "Universal context must carry provenance for LangGraph tools.",
                "confidence": 0.91,
                "provenance": {
                    "source_kind": "memory",
                    "source_ref": "mem-universal-context",
                    "scope_kind": "ticket",
                    "scope_ref": ticket.id,
                },
            }
        ],
        selected_ai_engine="deepseek",
    )

    universal = context.universal_context
    assert universal["version"] == "universal_context.v1"
    assert universal["summary"]["employee_id"] == "alex"
    assert universal["summary"]["ticket_id"] == ticket.id
    assert universal["summary"]["relevant_asset_count"] >= 2
    assert universal["summary"]["recalled_memory_count"] == 1
    selected_employee = universal["employee_context"]["selected_employee"]
    assert selected_employee["personality_tags"] == ["direct", "evidence-driven"]
    assert selected_employee["skill_refs"] == ["test-engineering"]
    assert selected_employee["capability_tags"] == ["backend-api-implementation", "test-engineering"]
    assert selected_employee["preferred_runtime"] == "claude_code"
    assert selected_employee["permission_policy"]["requires_approval_for"] == ["repo:write"]
    assert selected_employee["handoff_policy"]["escalate_to"] == "clara"
    assert selected_employee["current_load"]["active_ticket_count"] == 1
    assert selected_employee["current_load"]["assigned_ticket_count"] == 1
    assert selected_employee["current_load"]["source"] == "employee_load_service"
    assert selected_employee["work_history_summary"]["current_ticket_count"] == 1
    assert selected_employee["work_history_summary"]["report_count"] == 1
    work_history = universal["employee_context"]["work_history"]
    assert work_history["summary"]["source"] == "employee_work_ledger"
    assert work_history["summary"]["current_ticket_count"] == 1
    assert work_history["summary"]["historical_ticket_count"] == 1
    assert work_history["summary"]["report_count"] == 1
    assert work_history["refs"]["current_tickets"][0]["ticket_id"] == ticket.id
    assert work_history["refs"]["recent_reports"][0]["report_id"]
    assert work_history["provenance"]["source_kind"] == "employee_work_ledger"
    assert universal["employee_context"]["available_employee_refs"][0]["capability_tags"] == ["backend-api-implementation", "test-engineering"]
    assert universal["ticket_context"]["current_ticket"]["ticket_id"] == ticket.id
    assert universal["ticket_context"]["prior_evidence"][0]["evidence_refs"] == ["pytest::universal-context::passed"]
    assert universal["asset_context"]["relevant_assets"][0]["provenance"]["source_kind"] == "ticket_asset_record"
    assert universal["memory_context"]["recalled_memories"][0]["provenance"]["scope_ref"] == ticket.id
    assert any(item["kind"] == "employee" for item in universal["provenance_summary"])
    assert any(item["kind"] == "employee_work_history" for item in universal["provenance_summary"])
    assert any(item["kind"] == "employee_work_history" for item in universal["retrieval_audit"]["selected"])


def test_employee_current_load_uses_active_tickets_and_runtime_sessions(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    employees_dir = tmp_path / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True)
    (employees_dir / "alex.yaml").write_text(
        "\n".join(
            [
                "id: alex",
                "display_name: Alex",
                "kind: ai",
                "role: AI RD / Implementer",
                "summary: Implementation owner",
                "skills:",
                "  - test-engineering",
                "permissions:",
                "  - chat",
                "  - manage_tickets",
            ]
        ),
        encoding="utf-8",
    )

    owned = create_ticket(
        TicketCreateRequest(
            title="Implement real Employee load",
            description="Active ownership should count in current_load.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-load-owned",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    validating = create_ticket(
        TicketCreateRequest(
            title="Validate load projection",
            description="Validation assignment should count separately.",
            ticket_type="pv",
            assigned_employee_id="clara",
            assigned_role="AI Team OS Manager",
            validation_employee_id="alex",
            validation_role="AI PV",
            source_run_id="run-load-validation",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    create_ticket(
        TicketCreateRequest(
            title="Unrelated Peter task",
            description="Other Employee work must not affect Alex load.",
            ticket_type="ops",
            assigned_employee_id="peter",
            assigned_role="AI PM",
            source_run_id="run-load-unrelated",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    save_execution_session(
        tmp_path / ".aiteamos",
        employee_id="alex",
        thread_id="thread-load",
        ticket_id=owned.id,
        executor_id="langgraph-universal-employee-agent",
        executor_session_ref="session-load-1",
        checkpoint_ref="checkpoint-load-1",
        last_request_id="run-load-needs-approval",
        updated_at="2026-06-18T08:00:00Z",
        status="needs_approval",
        trace_ref=".aiteamos/traces/run-load-needs-approval.jsonl",
        current_graph_node="approval",
        ticket_refs=[owned.id],
    )
    save_execution_session(
        tmp_path / ".aiteamos",
        employee_id="alex",
        thread_id="thread-complete",
        ticket_id=owned.id,
        executor_id="langgraph-universal-employee-agent",
        executor_session_ref="session-load-2",
        checkpoint_ref="checkpoint-load-2",
        last_request_id="run-load-completed",
        updated_at="2026-06-18T08:05:00Z",
        status="completed",
        trace_ref=".aiteamos/traces/run-load-completed.jsonl",
        ticket_refs=[owned.id],
    )

    client = TestClient(create_app())
    response = client.get("/api/v1/chat/employees")
    assert response.status_code == 200, response.text
    employees = response.json()
    alex = next(item for item in employees if item["id"] == "alex")

    assert alex["current_load"]["active_ticket_count"] == 2
    assert alex["current_load"]["assigned_ticket_count"] == 1
    assert alex["current_load"]["validation_ticket_count"] == 1
    assert alex["current_load"]["active_run_count"] == 1
    assert alex["current_load"]["needs_approval_run_count"] == 1
    assert alex["current_load"]["status"] == "needs_attention"
    assert owned.id in alex["current_load"]["active_ticket_ids"]
    assert validating.id in alex["current_load"]["validation_ticket_ids"]
    assert alex["current_load"]["active_run_ids"] == ["run-load-needs-approval"]

    context = ExecutionContextService().build(
        message="Use real Employee load in LangGraph context.",
        employee={"id": "alex", "display_name": "Alex", "role": "AI RD / Implementer"},
        employee_profiles=[{**alex, "current_load": {"active_ticket_count": 99, "status": "stale"}}],
        recent_messages=[],
        ticket_keys=[],
        memory_refs=[],
        selected_ai_engine="deepseek",
    )
    selected = context.universal_context["employee_context"]["selected_employee"]
    assert selected["current_load"]["active_ticket_count"] == 2
    assert selected["current_load"]["active_run_count"] == 1
    assert selected["current_load"]["status"] == "needs_attention"


def test_execution_context_universal_context_searches_related_tickets_without_binding(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    match = create_ticket(
        TicketCreateRequest(
            title="LangGraph related context retrieval",
            description="Related ticket search should find autonomous employee context.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-related-context",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    create_ticket(
        TicketCreateRequest(
            title="Unrelated visual polish",
            description="This should not be the top related context result.",
            ticket_type="ops",
            assigned_employee_id="peter",
            assigned_role="AI PM",
            source_run_id="run-unrelated-context",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    context = ExecutionContextService().build(
        message="How should Alex approach LangGraph related context retrieval?",
        employee={"id": "alex", "display_name": "Alex", "role": "AI RD / Implementer"},
        employee_profiles=[],
        recent_messages=[],
        ticket_keys=[],
        memory_refs=[],
        selected_ai_engine="deepseek",
    )

    related = context.universal_context["ticket_context"]["related_tickets"]
    assert related[0]["ticket_id"] == match.id
    assert related[0]["provenance"]["source_kind"] == "ticket"
    assert context.universal_context["summary"]["related_ticket_count"] >= 1


def test_execution_context_degrades_when_graphiti_memory_recall_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()

    def fail_recall(**_kwargs):
        raise RuntimeError("Graphiti memory recall failed: service unavailable")

    monkeypatch.setattr(
        "aiteamos_api.read.execution_context_service.recall_memory_records",
        fail_recall,
    )

    context = ExecutionContextService().build(
        message="Recall durable memory before answering.",
        employee={"id": "alex", "display_name": "Alex", "role": "AI RD / Implementer"},
        employee_profiles=[],
        recent_messages=[],
        ticket_keys=[],
        memory_refs=[],
        selected_ai_engine="deepseek",
    )

    blockers = context.setup_blockers
    assert context.recalled_memories == []
    assert blockers[-1]["kind"] == "memory"
    assert blockers[-1]["reason"] == "graphiti_recall_failed"
    assert context.universal_context["summary"]["setup_blocker_count"] >= 1
    assert context.universal_context["backend_context"]["setup_blockers"][-1]["reason"] == "graphiti_recall_failed"


async def test_universal_agent_tool_registry_searches_tickets_with_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="LangGraph read-only tool registry",
            description="The universal employee agent should query Tickets through governed tools.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-tool-registry",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="exec-tool-registry",
        employee_id="alex",
        ticket_id="",
        ticket_binding=TicketBinding(mode="none", required=False),
        action_plan=ChatActionPlan(action="answer_only", arguments={"message": "Find LangGraph tool registry tickets."}),
        task_context={"task_summary": "Find LangGraph tool registry tickets."},
    )

    result = await UniversalAgentToolRegistry().run(
        "search_tickets",
        {"query": "LangGraph tool registry", "employee_id": "alex", "limit": 5},
        request=request,
    )

    event = result.event()
    assert result.status == "completed"
    assert result.output_refs[0]["ref"] == ticket.id
    assert result.provenance[0]["source_ref"] == "list_tickets"
    assert event["event"] == "universal_agent.tool.completed"
    assert event["data"]["tool_name"] == "search_tickets"
    assert event["data"]["capability"]["id"] == "universal_agent.search_tickets"
    assert event["data"]["capability"]["source_kind"] == "native_api"
    assert event["data"]["capability"]["access"] == "read"
    assert event["data"]["command"]["id"] == "universal_agent.search_tickets:run"
    assert event["data"]["record_as_asset"] is True
    assert event["data"]["output_refs"][0]["ref"] == ticket.id


async def test_universal_agent_tool_registry_returns_employee_work_history(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Universal employee work history tool",
            description="The employee context tool should expose compact Ticket/runtime work history.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-tool-employee-history",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content="Employee history should include this report as governed work evidence.",
            evidence=["pytest::employee-work-history-tool::passed"],
            report_type="progress",
            source_run_id="run-tool-employee-history-report",
        ),
    )
    context = ExecutionContextService().build(
        message="Inspect Alex work history.",
        employee={"id": "alex", "display_name": "Alex", "role": "AI RD / Implementer"},
        employee_profiles=[
            {
                "id": "alex",
                "display_name": "Alex",
                "role": "AI RD / Implementer",
                "skill_refs": ["backend-api-implementation"],
            }
        ],
        recent_messages=[],
        ticket_keys=[ticket.id],
        memory_refs=[],
        selected_ai_engine="deepseek",
    )
    request = ExecutionRequest(
        request_id="exec-tool-employee-history",
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="answer_only", arguments={"message": "Inspect Alex work history."}),
        task_context={"universal_context": context.universal_context},
    )

    result = await UniversalAgentToolRegistry().run(
        "get_employee_context",
        {"employee_id": "alex"},
        request=request,
    )

    assert result.status == "completed"
    assert result.output["employee_id"] == "alex"
    assert result.output["selected_employee"]["employee_id"] == "alex"
    assert result.output["work_history"]["summary"]["source"] == "employee_work_ledger"
    assert result.output["work_history"]["summary"]["report_count"] == 1
    assert result.output["work_history"]["refs"]["current_tickets"][0]["ticket_id"] == ticket.id


async def test_langgraph_executor_answer_calls_read_only_context_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="LangGraph context tool answer",
            description="Answer-only execution should call read-only Ticket and Memory tools.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-langgraph-tools",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="exec-langgraph-tools",
        employee_id="alex",
        ticket_id="",
        ticket_binding=TicketBinding(mode="none", required=False),
        action_plan=ChatActionPlan(action="answer_only", arguments={"message": "How should LangGraph context tool answer work?"}),
        task_context={
            "task_summary": "How should LangGraph context tool answer work?",
            "employee": {"id": "alex", "display_name": "Alex", "skill_titles": ["Runtime Engineering"]},
        },
        permission_policy={"selected_ai_engine": "stub"},
    )

    result = await LangGraphExecutor().run(request)

    tool_events = [
        event for event in result.tool_events
        if event.get("event") == "universal_agent.tool.completed"
    ]
    tool_names = {event.get("data", {}).get("tool_name") for event in tool_events}
    ticket_event = next(event for event in tool_events if event.get("data", {}).get("tool_name") == "search_tickets")
    load_tools_event = next(event for event in result.tool_events if event.get("event") == "runtime.load_tools")
    loaded_tools = load_tools_event["data"]["tools"]
    assert result.status == "completed"
    assert {"search_tickets", "search_memory", "search_assets"}.issubset(tool_names)
    assert load_tools_event["data"]["source"] == "capability_registry"
    assert {"search_tickets", "search_memory", "search_assets"}.issubset(set(load_tools_event["data"]["loaded_tool_names"]))
    assert "search_memory" in {tool["tool_name"] for tool in loaded_tools}
    assert all(tool["access"] == "read" for tool in loaded_tools)
    assert ticket_event["data"]["capability"]["id"] == "universal_agent.search_tickets"
    assert ticket_event["data"]["capability"]["output_asset_policy"]["record_tool_call"] is True
    assert ticket_event["data"]["record_as_asset"] is True
    assert ticket_event["data"]["output_refs"][0]["ref"] == ticket.id
    assert result.learning_delta["tool_outputs"]["search_tickets"]["tickets"][0]["ticket_id"] == ticket.id
    assert "Tool context:" in result.report


async def test_langgraph_executor_records_structured_read_tool_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()

    async def fail_memory_search(**_kwargs):
        raise RuntimeError("memory backend timed out")

    monkeypatch.setattr(
        "aiteamos_api.read.universal_agent_tools.search_memory_records",
        fail_memory_search,
    )
    request = ExecutionRequest(
        request_id="exec-langgraph-tool-failure",
        employee_id="alex",
        ticket_id="",
        ticket_binding=TicketBinding(mode="none", required=False),
        action_plan=ChatActionPlan(action="answer_only", arguments={"message": "Trigger memory search failure."}),
        task_context={"task_summary": "Trigger memory search failure.", "employee": {"id": "alex", "display_name": "Alex"}},
        permission_policy={"selected_ai_engine": "stub"},
    )

    result = await LangGraphExecutor().run(request)

    failed = [
        event for event in result.tool_events
        if event.get("event") == "universal_agent.tool.failed"
        and event.get("data", {}).get("tool_name") == "search_memory"
    ]
    assert result.status == "completed"
    assert failed
    assert result.errors[0]["reason"] == "universal_agent_tool_failed"
    assert result.errors[0]["tool_name"] == "search_memory"


async def test_langgraph_executor_projects_ticket_loop_state_into_graph_state(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="LangGraph loop state projection",
            description="Runtime graph state should carry Ticket-native loop facts.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-langgraph-loop-state",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="exec-langgraph-loop-state",
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(
            action="append_report",
            arguments={
                "ticket_id": ticket.id,
                "content": "Project loop state into LangGraph.",
                "report_type": "autonomous_loop_step",
            },
        ),
        task_context={"task_summary": "Project loop state into LangGraph.", "employee": {"id": "alex", "display_name": "Alex"}},
        trace_context={
            "run_id": "exec-langgraph-loop-state",
            "thread_id": f"ticket-loop-{ticket.id}-step-2",
            "trace_ref": ".aiteamos/traces/exec-langgraph-loop-state.jsonl",
            "loop_kind": "ticket_native_step",
            "loop_step": 2,
            "stop_condition": "single_step",
            "ticket_status_before": "assigned",
            "validation_gate": {"status": "required", "required": True, "satisfied": False},
        },
    )

    result = await LangGraphExecutor(workspace_dir=tmp_path / ".aiteamos").run(request)
    load_event = next(event for event in result.tool_events if event.get("event") == "runtime.load_request")
    loop_state = result.learning_delta["loop_state"]

    assert result.status == "completed"
    assert load_event["data"]["loop_state"]["loop_step"] == 2
    assert load_event["data"]["loop_state"]["validation_gate"]["status"] == "required"
    assert loop_state["loop_kind"] == "ticket_native_step"
    assert loop_state["loop_step"] == 2
    assert loop_state["ticket_status_before"] == "assigned"
    assert loop_state["validation_gate"]["required"] is True
    assert loop_state["runtime_status"] == "completed"
    assert loop_state["current_graph_node"] == "produce_result"
    assert loop_state["next_stop_reason"] == "single_step_completed"


async def test_dispatch_blocks_missing_existing_ticket_binding():
    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-missing-ticket",
            employee_id="alex",
            ticket_binding=TicketBinding(mode="existing", required=True),
            action_plan=ChatActionPlan(action="append_report", arguments={"content": "done"}),
        )
    )

    assert result.status == "blocked"
    assert result.executor_id == "universal_employee_agent"
    assert "Ticket binding is required" in result.report


async def test_optional_external_executor_returns_setup_blocker_without_fake_completion(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)

    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-claude-code-setup",
            employee_id="alex",
            ticket_binding=TicketBinding(mode="none", required=False),
            action_plan=ChatActionPlan(action="answer_only", arguments={"message": "Inspect this with Claude Code"}),
            permission_policy={"selected_ai_engine": "claude_code"},
        )
    )

    assert result.executor_id == "claude_code"
    assert result.status == "blocked"
    assert result.errors[0]["reason"] == "executor_setup_blocker"
    assert "CLAUDE_CODE_BIN" in result.report
    assert "will not fake" not in result.report


async def test_legacy_direct_llm_selection_falls_back_to_universal_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    provider = _FakeLangChainModelProvider(
        content_by_engine={
            "deepseek": "DeepSeek LangChain response.",
            "openai": "OpenAI LangChain response.",
        }
    )
    dispatch = ExecutionDispatchService(model_provider=provider)
    deepseek = await dispatch.dispatch(
        ExecutionRequest(
            request_id="exec-direct-deepseek",
            workspace_id=str(tmp_path),
            employee_id="clara",
            ticket_binding=TicketBinding(mode="none", required=False),
            action_plan=ChatActionPlan(action="answer_only", arguments={"message": "who are you"}),
            task_context={"task_summary": "who are you", "employee": {"display_name": "Clara"}},
            permission_policy={"executor_id": "direct_llm", "selected_ai_engine": "deepseek"},
        )
    )

    assert "direct_llm" not in dispatch.executors
    assert deepseek.executor_id == "universal_employee_agent"
    assert deepseek.status == "completed"
    assert deepseek.report == "DeepSeek LangChain response."
    assert deepseek.executor_session_ref == "lg-exec-direct-deepseek"
    assert deepseek.checkpoint_ref == "langgraph:exec-direct-deepseek"
    provider_events = [event for event in deepseek.tool_events if event.get("event") == "ai_engine.deepseek.completed"]
    assert provider_events
    assert provider_events[0]["data"]["provider_ref"]["model_provider_boundary"] == "langchain"
    assert [call["selected_engine"] for call in provider.calls] == ["deepseek"]


def test_langgraph_executors_do_not_embed_native_deepseek_http() -> None:
    root = Path(__file__).resolve().parents[1]
    source = "\n".join(
        [
            (root / "services/api/aiteamos_api/read/runtime_executors/langgraph_executor.py").read_text(encoding="utf-8"),
            (root / "services/api/aiteamos_api/read/runtime_executors/universal_employee_agent_executor.py").read_text(encoding="utf-8"),
        ]
    )

    assert "/chat/completions" not in source
    assert "call_deepseek_chat_completion" not in source
    assert "call_openai_responses" not in source
    assert "langgraph_deepseek_stream" not in source


async def test_langgraph_executor_does_not_use_pre_graph_direct_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            raise AssertionError("LangGraphExecutor must not call direct LLM before entering the graph.")

    provider = _FakeLangChainModelProvider(content_by_engine={"deepseek": "Should not be called."})
    dispatch = ExecutionDispatchService(async_client_factory=FakeAsyncClient, model_provider=provider)
    try:
        result = await dispatch.dispatch(
            ExecutionRequest(
                request_id="exec-langgraph-no-direct-llm",
                workspace_id=str(tmp_path),
                employee_id="clara",
                ticket_binding=TicketBinding(mode="none", required=False),
                action_plan=ChatActionPlan(action="answer_only", arguments={"message": "Explain core loop."}),
                task_context={
                    "task_summary": "Explain core loop.",
                    "employee": {"id": "clara", "display_name": "Clara", "role": "AI Team OS Manager"},
                },
                permission_policy={"selected_executor": "langgraph", "selected_ai_engine": "deepseek"},
            )
        )
    finally:
        await dispatch.aclose()

    event_names = [event.get("event") for event in result.tool_events]
    assert result.executor_id == "langgraph"
    assert result.status == "completed"
    assert result.learning_delta["current_graph_node"] == "produce_result"
    assert "runtime.load_request" in event_names
    assert "runtime.plan" in event_names
    assert "ai_engine.deepseek.completed" not in event_names
    assert provider.calls == []


async def test_answer_only_defaults_to_universal_employee_agent_with_read_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Universal employee agent default",
            description="Ordinary answer-only Chat should route through LangGraph read tools.",
            ticket_type="rd",
            assigned_employee_id="clara",
            assigned_role="AI Team OS Manager",
            source_run_id="run-universal-default",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    provider = _FakeLangChainModelProvider(content_by_engine={"deepseek": "Universal employee answer."})

    dispatch = ExecutionDispatchService(model_provider=provider)
    try:
        result = await dispatch.dispatch(
            ExecutionRequest(
                request_id="exec-universal-default",
                workspace_id=str(tmp_path),
                employee_id="clara",
                ticket_binding=TicketBinding(mode="none", required=False),
                action_plan=ChatActionPlan(action="answer_only", arguments={"message": "Explain universal employee agent default."}),
                task_context={
                    "task_summary": "Explain universal employee agent default.",
                    "employee": {"id": "clara", "display_name": "Clara", "role": "AI Team OS Manager"},
                },
                permission_policy={"selected_ai_engine": "deepseek"},
            )
        )
    finally:
        await dispatch.aclose()

    event_names = [event.get("event") for event in result.tool_events]
    tool_names = [
        event.get("data", {}).get("tool_name")
        for event in result.tool_events
        if str(event.get("event") or "").startswith("universal_agent.tool.")
    ]
    assert result.executor_id == "universal_employee_agent"
    assert result.status == "completed"
    assert result.report == "Universal employee answer."
    assert tool_names[:3] == ["search_tickets", "search_memory", "search_assets"]
    assert "ai_engine.deepseek.completed" in event_names
    assert result.learning_delta["tool_outputs"]["search_tickets"]["tickets"][0]["ticket_id"] == ticket.id
    assert provider.calls[0]["selected_engine"] == "deepseek"
    assert provider.calls[0]["messages"][0]["role"] == "system"
    assert "LangGraph read-tool context:" in provider.calls[0]["messages"][0]["content"]
    assert ticket.id in provider.calls[0]["messages"][0]["content"]


async def test_external_repo_mutation_requires_ticket_and_approval_before_runtime(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)

    missing_ticket = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-claude-code-missing-ticket",
            employee_id="alex",
            ticket_binding=TicketBinding(mode="none", required=False),
            action_plan=ChatActionPlan(
                action="implement_ticket",
                arguments={"message": "Implement this repo change with Claude Code"},
            ),
            capability_grants=["repo:write"],
            permission_policy={"selected_ai_engine": "claude_code"},
        )
    )
    needs_approval = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-claude-code-needs-approval",
            employee_id="alex",
            ticket_id="rd-9999",
            ticket_binding=TicketBinding(mode="existing", ticket_id="rd-9999", required=True),
            action_plan=ChatActionPlan(
                action="implement_ticket",
                arguments={"message": "Implement this repo change with Claude Code"},
            ),
            capability_grants=["repo:write", "ticket:evidence:write"],
            permission_policy={"selected_ai_engine": "claude_code"},
        )
    )

    assert missing_ticket.executor_id == "claude_code"
    assert missing_ticket.status == "blocked"
    assert missing_ticket.errors[0]["reason"] == "repo_mutation_ticket_binding_required"
    assert needs_approval.executor_id == "claude_code"
    assert needs_approval.status == "needs_approval"
    assert needs_approval.approval_requests[0]["required_capability"] == "repo:write"


async def test_cursor_executor_setup_blocker_and_repo_mutation_guard(monkeypatch):
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)

    setup_blocker = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-cursor-setup",
            employee_id="alex",
            ticket_binding=TicketBinding(mode="none", required=False),
            action_plan=ChatActionPlan(action="answer_only", arguments={"message": "Use Cursor to inspect this"}),
            permission_policy={"selected_ai_engine": "cursor"},
        )
    )
    missing_ticket = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-cursor-missing-ticket",
            employee_id="alex",
            ticket_binding=TicketBinding(mode="none", required=False),
            action_plan=ChatActionPlan(action="implement_ticket", arguments={"message": "Use Cursor to edit repo"}),
            capability_grants=["repo:write"],
            permission_policy={"selected_ai_engine": "cursor"},
        )
    )

    assert setup_blocker.executor_id == "cursor"
    assert setup_blocker.status == "blocked"
    assert setup_blocker.errors[0]["reason"] == "executor_setup_blocker"
    assert "CURSOR_API_KEY" in setup_blocker.report
    assert missing_ticket.executor_id == "cursor"
    assert missing_ticket.status == "blocked"
    assert missing_ticket.errors[0]["reason"] == "repo_mutation_ticket_binding_required"


async def test_cursor_executor_runs_configured_http_inspect(monkeypatch):
    calls: list[dict] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, json):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": self.timeout})
            return _FakeHttpResponse(
                {
                    "report": "Cursor inspect completed",
                    "artifacts": [{"kind": "cursor_artifact", "request_id": json["execution_request"]["request_id"]}],
                    "evidence": [{"kind": "cursor_evidence", "ref": "cursor-evidence-ref"}],
                    "tool_events": [{"event": "cursor.step", "summary": "Cursor indexed repository context."}],
                    "learning_delta": {"cursor_http": True},
                    "usage": {"cursor_steps": 2},
                }
            )

    monkeypatch.setenv("CURSOR_API_KEY", "cursor-test-key")
    monkeypatch.setenv("CURSOR_API_BASE_URL", "https://cursor.example")
    monkeypatch.setenv("CURSOR_INSPECT_ENDPOINT", "/agent/inspect")
    monkeypatch.setenv("CURSOR_MODEL", "cursor-agent")
    monkeypatch.setattr(
        "aiteamos_api.read.runtime_executors.external_runtime_executor.httpx.AsyncClient",
        FakeAsyncClient,
    )

    health = await ExecutionDispatchService().executors["cursor"].health()
    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-cursor-http-inspect",
            employee_id="alex",
            ticket_id="rd-6262",
            ticket_binding=TicketBinding(mode="existing", ticket_id="rd-6262", required=True),
            action_plan=ChatActionPlan(action="inspect_code_repository", arguments={"message": "Inspect through Cursor"}),
            task_context={"task_summary": "Inspect through Cursor"},
            capability_grants=["repo:read", "ticket:evidence:write"],
            permission_policy={"selected_ai_engine": "cursor"},
            trace_context={"trace_ref": ".aiteamos/traces/exec-cursor-http-inspect.jsonl"},
        )
    )

    assert health["status"] == "ready"
    assert health["config"]["api_key_env"] == "CURSOR_API_KEY"
    assert health["config"]["http_endpoint_path"] == "/agent/inspect"
    assert result.executor_id == "cursor"
    assert result.status == "completed"
    assert result.report == "Cursor inspect completed"
    assert result.artifacts[0]["kind"] == "external_runtime_http_execution"
    assert result.artifacts[1]["kind"] == "cursor_artifact"
    assert result.evidence[0]["kind"] == "external_runtime_http_evidence"
    assert result.evidence[1]["ref"] == "cursor-evidence-ref"
    assert result.learning_delta["cursor_http"] is True
    assert result.usage["cursor_steps"] == 2
    assert result.tool_events[0]["event"] == "runtime.external.http.completed"
    assert result.tool_events[1]["event"] == "cursor.step"
    assert calls[0]["url"] == "https://cursor.example/agent/inspect"
    assert calls[0]["headers"]["Authorization"] == "Bearer cursor-test-key"
    assert calls[0]["json"]["execution_request"]["ticket_id"] == "rd-6262"
    assert calls[0]["json"]["expected_output_schema"]["status"].startswith("completed")
    assert calls[0]["json"]["expected_output_schema"]["tool_events"] == "list[dict]"


async def test_external_http_runtime_request_is_cancelled_by_ticket_control_in_flight(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    state = {"cancelled": False}

    class SlowAsyncClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, json):
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                state["cancelled"] = True
                raise
            return _FakeHttpResponse({"report": "slow HTTP runtime completed too late"})

    monkeypatch.setenv("CURSOR_API_KEY", "cursor-test-key")
    monkeypatch.setenv("CURSOR_API_BASE_URL", "https://cursor.example")
    monkeypatch.setenv("CURSOR_INSPECT_ENDPOINT", "/agent/inspect")
    monkeypatch.setattr(
        "aiteamos_api.read.runtime_executors.external_runtime_executor.httpx.AsyncClient",
        SlowAsyncClient,
    )
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Cancel running external HTTP runtime",
            description="Ticket control should cancel an in-flight external HTTP runtime request.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-external-http-runtime-cancel",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="exec-external-http-cancel",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="inspect_code_repository", arguments={"message": "Inspect slowly through Cursor"}),
        capability_grants=["repo:read", "ticket:evidence:write"],
        permission_policy={"selected_ai_engine": "cursor"},
        trace_context={"trace_ref": ".aiteamos/traces/exec-external-http-cancel.jsonl", "thread_id": "external-http-cancel-thread"},
    )

    task = asyncio.create_task(ExecutionDispatchService().dispatch(request))
    for _ in range(50):
        sessions = load_execution_sessions(workspace)
        if any(session.get("last_request_id") == request.request_id and session.get("status") == "running" for session in sessions.values()):
            break
        await asyncio.sleep(0.02)

    control = control_ticket_loop(
        ticket.id,
        TicketLoopControlRequest(
            action="cancel",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Cancel the in-flight external HTTP runtime from the Ticket cockpit.",
        ),
        workspace_dir=workspace,
    )
    result = await task
    sessions_after = load_execution_sessions(workspace)
    session = next(item for item in sessions_after.values() if item["last_request_id"] == request.request_id)

    assert control.state.status == "cancelled"
    assert state["cancelled"] is True
    assert result.executor_id == "cursor"
    assert result.status == "cancelled"
    assert result.errors[0]["reason"] == "external_runtime_interrupted"
    assert result.errors[0]["action"] == "cancel"
    assert result.learning_delta["interrupt"]["request_cancelled"] is True
    assert result.tool_events[0]["event"] == "runtime.external.http.interrupted"
    assert "slow HTTP runtime completed too late" not in result.report
    assert session["status"] == "cancelled"
    assert session["control_state"]["action"] == "cancel"


async def test_cursor_http_invalid_runtime_status_is_failed_contract_result(monkeypatch):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, json):
            return _FakeHttpResponse({"status": "mystery", "report": "Cursor returned an unsupported state."})

    monkeypatch.setenv("CURSOR_API_KEY", "cursor-test-key")
    monkeypatch.setenv("CURSOR_API_BASE_URL", "https://cursor.example")
    monkeypatch.setenv("CURSOR_INSPECT_ENDPOINT", "/agent/inspect")
    monkeypatch.setattr(
        "aiteamos_api.read.runtime_executors.external_runtime_executor.httpx.AsyncClient",
        FakeAsyncClient,
    )

    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-cursor-http-invalid-status",
            employee_id="alex",
            ticket_id="rd-6464",
            ticket_binding=TicketBinding(mode="existing", ticket_id="rd-6464", required=True),
            action_plan=ChatActionPlan(action="inspect_code_repository", arguments={"message": "Inspect through Cursor"}),
            capability_grants=["repo:read", "ticket:evidence:write"],
            permission_policy={"selected_ai_engine": "cursor"},
        )
    )

    assert result.executor_id == "cursor"
    assert result.status == "failed"
    assert result.report == "Cursor returned an unsupported state."
    assert result.errors[0]["reason"] == "runtime_result_contract_invalid_status"
    assert result.learning_delta["runtime_result_contract"]["status"] == "invalid"
    assert "unknown_status:mystery" in result.learning_delta["runtime_result_contract"]["warnings"]


async def test_openhands_http_failure_returns_failed_result(monkeypatch):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, json):
            return _FakeHttpResponse(None, status_code=503, text="OpenHands unavailable")

    monkeypatch.setenv("OPENHANDS_BASE_URL", "http://openhands.local")
    monkeypatch.setenv("OPENHANDS_INSPECT_ENDPOINT", "/api/inspect")
    monkeypatch.setattr(
        "aiteamos_api.read.runtime_executors.external_runtime_executor.httpx.AsyncClient",
        FakeAsyncClient,
    )

    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-openhands-http-failed",
            employee_id="alex",
            ticket_id="rd-6363",
            ticket_binding=TicketBinding(mode="existing", ticket_id="rd-6363", required=True),
            action_plan=ChatActionPlan(action="inspect_code_repository", arguments={"message": "Inspect through OpenHands"}),
            capability_grants=["repo:read", "ticket:evidence:write"],
            permission_policy={"selected_ai_engine": "openhands"},
        )
    )

    assert result.executor_id == "openhands"
    assert result.status == "failed"
    assert result.report == "OpenHands unavailable"
    assert result.errors[0]["reason"] == "executor_http_failed"
    assert result.errors[0]["status_code"] == 503
    assert result.tool_events[0]["event"] == "runtime.external.http.failed"


async def test_optional_external_agent_executors_return_setup_blockers(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)
    monkeypatch.delenv("OPENHANDS_BASE_URL", raising=False)
    monkeypatch.delenv("OPENCODE_BIN", raising=False)

    dispatch = ExecutionDispatchService()
    cases = {
        "claude_agent_sdk": "ANTHROPIC_API_KEY",
        "claude_code": "CLAUDE_CODE_BIN",
        "openhands": "OPENHANDS_BASE_URL",
        "opencode": "OPENCODE_BIN",
    }

    for executor_id, missing_env in cases.items():
        result = await dispatch.dispatch(
            ExecutionRequest(
                request_id=f"exec-{executor_id}-setup",
                employee_id="alex",
                ticket_binding=TicketBinding(mode="none", required=False),
                action_plan=ChatActionPlan(action="answer_only", arguments={"message": f"Use {executor_id} to inspect this"}),
                permission_policy={"selected_ai_engine": executor_id},
            )
        )

        assert result.executor_id == executor_id
        assert result.status == "blocked"
        assert result.errors[0]["reason"] == "executor_setup_blocker"
        assert missing_env in result.report
        assert "will not fake" not in result.report


async def test_external_executors_prepare_non_destructive_inspect_handoff_when_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-key")
    monkeypatch.setenv("OPENHANDS_BASE_URL", "http://openhands.local")

    dispatch = ExecutionDispatchService()
    results = []
    for executor_id in ("claude_agent_sdk", "openhands"):
        results.append(
            await dispatch.dispatch(
                ExecutionRequest(
                    request_id=f"exec-{executor_id}-inspect",
                    employee_id="alex",
                    ticket_id="rd-4242",
                    ticket_binding=TicketBinding(mode="existing", ticket_id="rd-4242", required=True),
                    action_plan=ChatActionPlan(
                        action="inspect_code_repository",
                        arguments={"message": f"Inspect repository with {executor_id}", "query": "runtime adapter"},
                    ),
                    task_context={
                        "task_summary": f"Inspect repository with {executor_id}",
                        "repository_scope": {"repository_ids": ["repo-aiteamos"]},
                    },
                    capability_grants=["repo:read", "ticket:evidence:write"],
                    permission_policy={"selected_ai_engine": executor_id},
                    trace_context={"trace_ref": f".aiteamos/traces/{executor_id}.jsonl"},
                )
            )
        )

    assert [result.executor_id for result in results] == ["claude_agent_sdk", "openhands"]
    assert all(result.status == "partial" for result in results)
    assert all(result.output_ticket_id == "rd-4242" for result in results)
    assert all(result.artifacts[0]["kind"] == "external_runtime_inspect_handoff" for result in results)
    assert all(result.artifacts[0]["external_execution_status"] == "not_started" for result in results)
    assert all(result.evidence[0]["kind"] == "external_runtime_handoff_evidence" for result in results)
    assert all("no external runtime completion is being faked" in result.report for result in results)


async def test_external_repo_mutation_still_requires_evidence_after_approval(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_BIN", "/tmp/claude-code-compatible")

    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-claude-code-approved-missing-evidence",
            employee_id="alex",
            ticket_id="rd-9999",
            ticket_binding=TicketBinding(mode="existing", ticket_id="rd-9999", required=True),
            action_plan=ChatActionPlan(
                action="implement_ticket",
                arguments={"message": "Implement this repo change with Claude Code"},
            ),
            capability_grants=["repo:write"],
            approval_policy={"approved_capabilities": ["repo:write"]},
            permission_policy={"selected_ai_engine": "claude_code"},
        )
    )

    assert result.executor_id == "claude_code"
    assert result.status == "blocked"
    assert result.errors[0]["reason"] == "repo_mutation_evidence_required"


async def test_claude_code_compatible_cli_runs_non_destructive_inspect_and_receives_deepseek_config(tmp_path, monkeypatch):
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible",
        """#!/usr/bin/env python3
import json
import os
import sys
payload = json.loads(sys.stdin.read())
print(json.dumps({
    "report": "compatible inspect completed with " + os.environ.get("AITEAMOS_LLM_MODEL", ""),
    "artifacts": [{
        "kind": "fake_runtime_artifact",
        "ticket_id": os.environ.get("AITEAMOS_TICKET_ID", ""),
        "prompt_request_id": payload["execution_request"]["request_id"],
        "api_base_url": os.environ.get("AITEAMOS_LLM_BASE_URL", ""),
        "api_key_env": os.environ.get("AITEAMOS_LLM_API_KEY_ENV", "")
    }],
    "evidence": [{"kind": "fake_runtime_evidence", "ref": "fake-evidence-ref"}],
    "learning_delta": {"deepseek_model": os.environ.get("AITEAMOS_LLM_MODEL", "")},
    "usage": {"fake_runtime_steps": 1}
}))
""",
    )
    monkeypatch.setenv("CLAUDE_CODE_BIN", fake_cli)
    monkeypatch.setenv("CLAUDE_CODE_MODEL", "deepseek-reasoner")
    monkeypatch.setenv("CLAUDE_CODE_API_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("CLAUDE_CODE_API_KEY_ENV", "DEEPSEEK_API_KEY")
    monkeypatch.setenv("CLAUDE_CODE_WORKING_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")

    health = await ExecutionDispatchService().executors["claude_code"].health()
    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-claude-compatible-cli",
            workspace_id=str(tmp_path),
            employee_id="alex",
            ticket_id="rd-4242",
            ticket_binding=TicketBinding(mode="existing", ticket_id="rd-4242", required=True),
            action_plan=ChatActionPlan(
                action="inspect_code_repository",
                arguments={"message": "Inspect repo through Claude Code-compatible runtime"},
            ),
            task_context={"task_summary": "Inspect repo", "repository_scope": {"repository_ids": ["repo-aiteamos"]}},
            capability_grants=["repo:read", "ticket:evidence:write"],
            permission_policy={"selected_ai_engine": "claude_code"},
            trace_context={"trace_ref": ".aiteamos/traces/exec-claude-compatible-cli.jsonl"},
        )
    )

    assert health["status"] == "ready"
    assert health["config"]["binary_path"] == fake_cli
    assert health["config"]["api_key_env"] == "DEEPSEEK_API_KEY"
    assert result.executor_id == "claude_code"
    assert result.status == "completed"
    assert result.report == "compatible inspect completed with deepseek-reasoner"
    assert result.artifacts[0]["kind"] == "external_runtime_cli_execution"
    assert result.artifacts[1]["api_base_url"] == "https://api.deepseek.com"
    assert result.artifacts[1]["api_key_env"] == "DEEPSEEK_API_KEY"
    assert result.evidence[0]["kind"] == "external_runtime_cli_evidence"
    assert result.evidence[1]["ref"] == "fake-evidence-ref"
    assert result.learning_delta["deepseek_model"] == "deepseek-reasoner"
    assert result.tool_events[0]["event"] == "runtime.external.cli.completed"


async def test_codex_cli_executor_uses_output_schema_contract_and_path_discovery(tmp_path, monkeypatch):
    fake_codex = _write_fake_runtime(
        tmp_path / "codex",
        """#!/usr/bin/env python3
import json
import os
import sys
args = sys.argv[1:]
assert "--ask-for-approval" not in args
assert "--sandbox" in args
assert "workspace-write" in args
payload = json.loads(sys.stdin.read())
output_path = args[args.index("--output-last-message") + 1]
schema_path = args[args.index("--output-schema") + 1]
with open(schema_path, "r", encoding="utf-8") as handle:
    schema = json.load(handle)
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump({
        "status": "completed",
        "report": "Codex CLI inspected " + payload["execution_request"]["employee_id"],
        "artifacts": [{
            "kind": "codex_cli_contract_artifact",
            "schema_required": schema.get("required", []),
            "schema_strict": schema.get("additionalProperties") is False,
            "evidence_item_strict": schema["properties"]["evidence"]["items"].get("additionalProperties") is False,
            "ticket_id": os.environ.get("AITEAMOS_TICKET_ID", ""),
            "request_id": payload["execution_request"]["request_id"]
        }],
        "evidence": [{"kind": "codex_cli_evidence", "ref": "smoke://codex-cli-contract"}],
        "usage": {"codex_cli_steps": 1}
    }, handle)
print("codex event stream that should not be parsed as the result")
""",
    )
    monkeypatch.delenv("CODEX_CLI_BIN", raising=False)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")

    health = await ExecutionDispatchService().executors["codex_cli"].health()
    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-codex-cli-contract",
            workspace_id=str(tmp_path),
            employee_id="alex",
            ticket_id="rd-4242",
            ticket_binding=TicketBinding(mode="existing", ticket_id="rd-4242", required=True),
            action_plan=ChatActionPlan(
                action="inspect_code_repository",
                arguments={"message": "Inspect repo through Codex CLI runtime"},
            ),
            task_context={"task_summary": "Inspect repo", "repository_scope": {"repository_ids": ["repo-aiteamos"]}},
            capability_grants=["repo:read", "ticket:evidence:write"],
            permission_policy={"selected_ai_engine": "codex_cli"},
            trace_context={"trace_ref": ".aiteamos/traces/exec-codex-cli-contract.jsonl"},
        )
    )

    assert health["status"] == "ready"
    assert health["config"]["binary_path"] == fake_codex
    assert "repo:write" in health["capabilities"]
    assert result.executor_id == "codex_cli"
    assert result.status == "completed"
    assert result.report == "Codex CLI inspected alex"
    assert result.artifacts[0]["kind"] == "external_runtime_cli_execution"
    assert result.artifacts[0]["output_last_message_bytes"] > 0
    assert result.artifacts[1]["kind"] == "codex_cli_contract_artifact"
    assert "report" in result.artifacts[1]["schema_required"]
    assert "artifacts" in result.artifacts[1]["schema_required"]
    assert result.artifacts[1]["schema_strict"] is True
    assert result.artifacts[1]["evidence_item_strict"] is True
    assert result.evidence[1]["ref"] == "smoke://codex-cli-contract"


async def test_claude_code_compatible_cli_missing_report_is_blocked_contract_result(tmp_path, monkeypatch):
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-missing-report",
        """#!/usr/bin/env python3
import json
import sys
json.loads(sys.stdin.read())
print(json.dumps({"artifacts": [{"kind": "runtime_observation"}]}))
""",
    )
    monkeypatch.setenv("CLAUDE_CODE_BIN", fake_cli)
    monkeypatch.setenv("CLAUDE_CODE_WORKING_DIR", str(tmp_path))

    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-claude-compatible-missing-report",
            workspace_id=str(tmp_path),
            employee_id="alex",
            ticket_id="rd-4242",
            ticket_binding=TicketBinding(mode="existing", ticket_id="rd-4242", required=True),
            action_plan=ChatActionPlan(action="inspect_code_repository", arguments={"message": "Inspect repo"}),
            capability_grants=["repo:read", "ticket:evidence:write"],
            permission_policy={"selected_ai_engine": "claude_code"},
        )
    )

    assert result.executor_id == "claude_code"
    assert result.status == "blocked"
    assert "missing report" in result.report
    assert result.errors[0]["reason"] == "runtime_result_contract_missing_report"
    assert result.learning_delta["runtime_result_contract"]["status"] == "invalid"
    assert "missing_report" in result.learning_delta["runtime_result_contract"]["warnings"]


async def test_claude_code_compatible_cli_failure_returns_failed_result(tmp_path, monkeypatch):
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-fails",
        """#!/usr/bin/env python3
import sys
sys.stderr.write("runtime exploded")
raise SystemExit(7)
""",
    )
    monkeypatch.setenv("CLAUDE_CODE_BIN", fake_cli)
    monkeypatch.setenv("CLAUDE_CODE_WORKING_DIR", str(tmp_path))

    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-claude-compatible-fails",
            workspace_id=str(tmp_path),
            employee_id="alex",
            ticket_id="rd-4242",
            ticket_binding=TicketBinding(mode="existing", ticket_id="rd-4242", required=True),
            action_plan=ChatActionPlan(action="inspect_code_repository", arguments={"message": "Inspect repo"}),
            capability_grants=["repo:read", "ticket:evidence:write"],
            permission_policy={"selected_ai_engine": "claude_code"},
        )
    )

    assert result.executor_id == "claude_code"
    assert result.status == "failed"
    assert result.errors[0]["reason"] == "executor_cli_failed"
    assert result.errors[0]["exit_code"] == 7
    assert "runtime exploded" in result.report


async def test_external_cli_runtime_is_interrupted_by_ticket_control_in_flight(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-slow",
        """#!/usr/bin/env python3
import json
import sys
import time
sys.stdin.read()
time.sleep(5)
print(json.dumps({"report": "slow runtime completed too late"}))
""",
    )
    monkeypatch.setenv("CLAUDE_CODE_BIN", fake_cli)
    monkeypatch.setenv("CLAUDE_CODE_WORKING_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_TIMEOUT_SECONDS", "10")
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Interrupt running external runtime",
            description="Ticket control should stop an in-flight external CLI runtime.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-external-runtime-interrupt",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="exec-external-cli-interrupt",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="inspect_code_repository", arguments={"message": "Inspect slowly"}),
        capability_grants=["repo:read", "ticket:evidence:write"],
        permission_policy={"selected_ai_engine": "claude_code"},
        trace_context={"trace_ref": ".aiteamos/traces/exec-external-cli-interrupt.jsonl", "thread_id": "external-cli-interrupt-thread"},
    )

    task = asyncio.create_task(ExecutionDispatchService().dispatch(request))
    for _ in range(50):
        sessions = load_execution_sessions(workspace)
        if any(session.get("last_request_id") == request.request_id and session.get("status") == "running" for session in sessions.values()):
            break
        await asyncio.sleep(0.02)

    control = control_ticket_loop(
        ticket.id,
        TicketLoopControlRequest(
            action="stop",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Stop the in-flight external runtime from the Ticket cockpit.",
        ),
        workspace_dir=workspace,
    )
    result = await task
    sessions_after = load_execution_sessions(workspace)
    session = next(item for item in sessions_after.values() if item["last_request_id"] == request.request_id)

    assert control.state.status == "stopped"
    assert result.executor_id == "claude_code"
    assert result.status == "cancelled"
    assert result.errors[0]["reason"] == "external_runtime_interrupted"
    assert result.errors[0]["action"] == "stop"
    assert result.learning_delta["interrupt"]["in_flight"] is True
    assert result.tool_events[0]["event"] == "runtime.external.cli.interrupted"
    assert "slow runtime completed too late" not in result.report
    assert session["status"] == "stopped"
    assert session["control_state"]["action"] == "stop"


async def test_opencode_compatible_cli_runs_non_destructive_inspect(tmp_path, monkeypatch):
    fake_cli = _write_fake_runtime(
        tmp_path / "opencode-compatible",
        """#!/usr/bin/env python3
import json
import os
import sys
payload = json.loads(sys.stdin.read())
print(json.dumps({
    "report": "OpenCode inspect completed",
    "artifacts": [{
        "kind": "opencode_artifact",
        "request_id": payload["execution_request"]["request_id"],
        "model": os.environ.get("AITEAMOS_LLM_MODEL", ""),
        "base_url": os.environ.get("AITEAMOS_LLM_BASE_URL", "")
    }],
    "evidence": [{"kind": "opencode_evidence", "ref": "opencode-evidence-ref"}],
    "usage": {"opencode_steps": 1}
}))
""",
    )
    monkeypatch.setenv("OPENCODE_BIN", fake_cli)
    monkeypatch.setenv("OPENCODE_MODEL", "deepseek-coder")
    monkeypatch.setenv("OPENCODE_API_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("OPENCODE_API_KEY_ENV", "DEEPSEEK_API_KEY")
    monkeypatch.setenv("OPENCODE_WORKING_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-key")

    health = await ExecutionDispatchService().executors["opencode"].health()
    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-opencode-compatible-cli",
            workspace_id=str(tmp_path),
            employee_id="alex",
            ticket_id="rd-5252",
            ticket_binding=TicketBinding(mode="existing", ticket_id="rd-5252", required=True),
            action_plan=ChatActionPlan(
                action="inspect_code_repository",
                arguments={"message": "Inspect repo through OpenCode-compatible runtime"},
            ),
            task_context={"task_summary": "Inspect repo", "repository_scope": {"repository_ids": ["repo-aiteamos"]}},
            capability_grants=["repo:read", "ticket:evidence:write"],
            permission_policy={"selected_ai_engine": "opencode"},
            trace_context={"trace_ref": ".aiteamos/traces/exec-opencode-compatible-cli.jsonl"},
        )
    )

    assert health["status"] == "ready"
    assert health["config"]["binary_path"] == fake_cli
    assert health["config"]["api_key_env"] == "DEEPSEEK_API_KEY"
    assert result.executor_id == "opencode"
    assert result.status == "completed"
    assert result.report == "OpenCode inspect completed"
    assert result.artifacts[0]["kind"] == "external_runtime_cli_execution"
    assert result.artifacts[1]["kind"] == "opencode_artifact"
    assert result.artifacts[1]["model"] == "deepseek-coder"
    assert result.evidence[0]["kind"] == "external_runtime_cli_evidence"
    assert result.evidence[1]["ref"] == "opencode-evidence-ref"
    assert result.usage["opencode_steps"] == 1
    assert result.tool_events[0]["event"] == "runtime.external.cli.completed"


async def test_compatible_cli_timeout_returns_blocker(tmp_path, monkeypatch):
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-timeout",
        """#!/usr/bin/env python3
import time
time.sleep(5)
""",
    )
    monkeypatch.setenv("CLAUDE_CODE_BIN", fake_cli)
    monkeypatch.setenv("CLAUDE_CODE_WORKING_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_TIMEOUT_SECONDS", "1")

    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-claude-compatible-timeout",
            workspace_id=str(tmp_path),
            employee_id="alex",
            ticket_id="rd-4242",
            ticket_binding=TicketBinding(mode="existing", ticket_id="rd-4242", required=True),
            action_plan=ChatActionPlan(action="inspect_code_repository", arguments={"message": "Inspect repo"}),
            capability_grants=["repo:read", "ticket:evidence:write"],
            permission_policy={"selected_ai_engine": "claude_code"},
        )
    )

    assert result.executor_id == "claude_code"
    assert result.status == "blocked"
    assert result.errors[0]["reason"] == "executor_timeout"
    assert "timed out after 1 seconds" in result.report


async def test_external_inspect_handoff_ingestion_records_ticket_report(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-ingestion",
        """#!/usr/bin/env python3
import json
import sys
json.loads(sys.stdin.read())
print(json.dumps({
    "report": "Runtime adapter boundary inspected.",
    "evidence": [{"kind": "runtime_report", "ref": "runtime-report-ref"}]
}))
""",
    )
    monkeypatch.setenv("CLAUDE_CODE_BIN", fake_cli)
    monkeypatch.setenv("CLAUDE_CODE_WORKING_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="External runtime handoff provenance",
            description="Record non-destructive external runtime handoff.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-external-handoff",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="exec-claude-code-handoff",
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(
            action="inspect_code_repository",
            arguments={"message": "Ask Claude Code to inspect the runtime adapter boundary"},
        ),
        task_context={
            "task_summary": "Ask Claude Code to inspect the runtime adapter boundary",
            "employee": {"role": "AI RD / Implementer"},
            "repository_scope": {"repository_ids": ["repo-aiteamos"]},
        },
        capability_grants=["repo:read", "ticket:evidence:write"],
        permission_policy={"selected_ai_engine": "claude_code"},
        trace_context={"run_id": "exec-claude-code-handoff", "trace_ref": ".aiteamos/traces/exec-claude-code-handoff.jsonl"},
    )
    result = await ExecutionDispatchService().dispatch(request)
    ingested = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos").ingest(request, result)
    updated = get_ticket(ticket.id)

    assert result.executor_id == "claude_code"
    assert result.status == "completed"
    assert ingested.status == "completed"
    assert updated is not None
    assert any(report.report_type == "external_runtime_report" for report in updated.reports)
    assert any("external-runtime:claude_code:cli" in evidence for report in updated.reports for evidence in report.evidence)
    assert any("runtime-report-ref" in evidence for report in updated.reports for evidence in report.evidence)
    assert any(event.get("data", {}).get("command", {}).get("id") == "runtime.external:cli_report" for event in ingested.tool_events)


async def test_approved_external_repo_mutation_ingestion_records_patch_and_test_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-repo-mutation",
        """#!/usr/bin/env python3
import json
import sys
json.loads(sys.stdin.read())
print(json.dumps({
    "report": "Runtime applied approved repository mutation.",
    "artifacts": [{
        "kind": "repo_patch",
        "changed_files": ["services/api/aiteamos_api/read/example.py"],
        "diff_ref": "artifact://diff/runtime-approved.patch"
    }],
    "evidence": [{"kind": "test_evidence", "ref": "pytest::runtime-adapter::passed"}],
    "usage": {"runtime_steps": 3}
}))
""",
    )
    monkeypatch.setenv("CLAUDE_CODE_BIN", fake_cli)
    monkeypatch.setenv("CLAUDE_CODE_WORKING_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Approved runtime repo mutation",
            description="Record approved external runtime repo mutation.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-approved-mutation",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="exec-approved-runtime-mutation",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(
            action="implement_ticket",
            arguments={"message": "Use Claude Code-compatible runtime to implement the approved change."},
        ),
        task_context={
            "task_summary": "Use Claude Code-compatible runtime to implement the approved change.",
            "employee": {"role": "AI RD / Implementer"},
            "repository_scope": {"repository_ids": ["repo-aiteamos"]},
        },
        capability_grants=["repo:write", "ticket:evidence:write"],
        approval_policy={"approved_capabilities": ["repo:write"], "approval_refs": ["approval-runtime-1"]},
        permission_policy={"selected_ai_engine": "claude_code"},
        expected_outputs={"evidence": True},
        trace_context={"run_id": "exec-approved-runtime-mutation", "trace_ref": ".aiteamos/traces/exec-approved-runtime-mutation.jsonl"},
    )
    result = await ExecutionDispatchService().dispatch(request)
    ingested = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos").ingest(request, result)
    updated = get_ticket(ticket.id)

    assert result.executor_id == "claude_code"
    assert result.status == "completed"
    assert result.artifacts[0]["repo_mutation"] is True
    assert result.artifacts[1]["changed_files"] == ["services/api/aiteamos_api/read/example.py"]
    assert result.evidence[1]["ref"] == "pytest::runtime-adapter::passed"
    assert ingested.status == "completed"
    assert updated is not None
    mutation_reports = [report for report in updated.reports if report.report_type == "external_runtime_repo_mutation"]
    assert mutation_reports
    assert "Ticket-bound, approval-bound, and evidence-bound" in mutation_reports[-1].content
    assert "services/api/aiteamos_api/read/example.py" in mutation_reports[-1].content
    assert any("pytest::runtime-adapter::passed" in evidence for evidence in mutation_reports[-1].evidence)
    assert any(event.get("data", {}).get("command", {}).get("id") == "runtime.external:repo_mutation" for event in ingested.tool_events)


async def test_approved_external_repo_mutation_ingestion_accepts_validation_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Approved runtime repo mutation with validation evidence",
            assigned_employee_id="alex",
            source_run_id="seed-validation-evidence",
        )
    )
    request = ExecutionRequest(
        request_id="exec-approved-runtime-validation-evidence",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="implement_ticket", arguments={"message": "Approved mutation with validation evidence"}),
        capability_grants=["repo:write", "ticket:evidence:write"],
        approval_policy={"approved_capabilities": ["repo:write"], "approval_refs": ["approval-runtime-validation"]},
        expected_outputs={"evidence": True},
        trace_context={"run_id": "exec-approved-runtime-validation-evidence"},
    )
    result = ExecutionResult(
        request_id=request.request_id,
        executor_id="codex_cli",
        status="completed",
        report="Runtime applied approved repository mutation with validation evidence.",
        output_ticket_id=ticket.id,
        artifacts=[
            {
                "kind": "external_runtime_cli_execution",
                "executor_id": "codex_cli",
                "repo_mutation": True,
            },
            {
                "kind": "changed_files",
                "changed_files": [".aiteamos/artifacts/runtime_dogfood/ops-validation-codex_cli.md"],
                "diff_ref": "artifact://diff/runtime-validation.patch",
            },
        ],
        evidence=[
            {
                "kind": "validation",
                "ref": "python -m py_compile services/api/aiteamos_api/read/runtime_executor_smoke_service.py",
                "summary": "Validation passed for runtime executor dogfood evidence.",
            }
        ],
    )

    ingested = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos").ingest(request, result)
    updated = get_ticket(ticket.id)

    assert ingested.status == "completed"
    assert updated is not None
    mutation_reports = [report for report in updated.reports if report.report_type == "external_runtime_repo_mutation"]
    assert mutation_reports
    assert any("py_compile" in evidence for evidence in mutation_reports[-1].evidence)


async def test_external_repo_mutation_ingestion_blocks_missing_patch_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Mutation missing patch",
            assigned_employee_id="alex",
            source_run_id="seed-missing-patch",
        )
    )
    request = ExecutionRequest(
        request_id="exec-mutation-missing-patch",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="implement_ticket", arguments={"message": "Approved mutation without patch"}),
        capability_grants=["repo:write", "ticket:evidence:write"],
        approval_policy={"approved_capabilities": ["repo:write"], "approval_refs": ["approval-runtime-2"]},
        expected_outputs={"evidence": True},
        trace_context={"run_id": "exec-mutation-missing-patch"},
    )
    result = ExecutionResult(
        request_id=request.request_id,
        executor_id="claude_code",
        status="completed",
        report="Runtime claims mutation completed.",
        output_ticket_id=ticket.id,
        artifacts=[
            {
                "kind": "external_runtime_cli_execution",
                "executor_id": "claude_code",
                "repo_mutation": True,
            }
        ],
        evidence=[{"kind": "test_evidence", "ref": "pytest::runtime-adapter::passed"}],
    )

    ingested = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos").ingest(request, result)
    updated = get_ticket(ticket.id)

    assert ingested.status == "blocked"
    assert ingested.errors[-1]["reason"] == "repo_mutation_patch_required"
    assert updated is not None
    assert not [report for report in updated.reports if report.report_type == "external_runtime_repo_mutation"]


async def test_external_repo_mutation_ingestion_blocks_missing_test_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Mutation missing test evidence",
            assigned_employee_id="alex",
            source_run_id="seed-missing-test-evidence",
        )
    )
    request = ExecutionRequest(
        request_id="exec-mutation-missing-test-evidence",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="implement_ticket", arguments={"message": "Approved mutation without test evidence"}),
        capability_grants=["repo:write", "ticket:evidence:write"],
        approval_policy={"approved_capabilities": ["repo:write"], "approval_refs": ["approval-runtime-3"]},
        expected_outputs={"evidence": True},
        trace_context={"run_id": "exec-mutation-missing-test-evidence"},
    )
    result = ExecutionResult(
        request_id=request.request_id,
        executor_id="claude_code",
        status="completed",
        report="Runtime claims mutation completed.",
        output_ticket_id=ticket.id,
        artifacts=[
            {
                "kind": "external_runtime_cli_execution",
                "executor_id": "claude_code",
                "repo_mutation": True,
            },
            {
                "kind": "repo_patch",
                "changed_files": ["services/api/aiteamos_api/read/example.py"],
                "diff_ref": "artifact://diff/runtime-approved.patch",
            },
        ],
        evidence=[{"kind": "runtime_evidence", "ref": "runtime://completed-only"}],
    )

    ingested = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos").ingest(request, result)
    updated = get_ticket(ticket.id)

    assert ingested.status == "blocked"
    assert ingested.errors[-1]["reason"] == "repo_mutation_test_evidence_required"
    assert updated is not None
    assert not [report for report in updated.reports if report.report_type == "external_runtime_repo_mutation"]


async def test_chat_governance_routes_ticket_implementation_to_external_runtime_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)

    service = ChatGovernanceService(workspace_dir=tmp_path / ".aiteamos")
    request, result = await service.handle_message(
        ChatGovernanceInput(
            message="Implement Ticket rd-9999 by editing the repository code.",
            employee={"id": "alex", "display_name": "Alex", "role": "AI RD / Implementer"},
            selected_ai_engine="claude_code",
            thread_id="thread-runtime-mutation",
            run_id="exec-chat-runtime-mutation",
            ticket_keys=["rd-9999"],
            workspace_id=str(tmp_path),
        )
    )

    assert request.action_plan.action == "implement_ticket"
    assert request.ticket_binding.mode == "existing"
    assert request.ticket_id == "rd-9999"
    assert "repo:write" in request.capability_grants
    assert request.expected_outputs["evidence"] is True
    assert request.permission_policy["selected_executor"] == "universal_employee_agent"
    assert request.permission_policy["requested_runtime_executor"] == "claude_code"
    assert result.executor_id == "universal_employee_agent"
    assert result.status == "needs_approval"
    assert result.approval_requests[0]["required_capability"] == "repo:write"
    assert result.approval_requests[0]["executor_id"] == "claude_code"
    assert result.approval_requests[0]["current_graph_node"] == "governance_gate"
    assert result.approval_requests[0]["checkpoint_ref"] == result.checkpoint_ref
    assert result.approval_requests[0]["source_state_ref"].startswith("state://universal_employee_agent/")
    assert any(error["reason"] == "repo_mutation_approval_required" for error in result.errors)
    approvals = list_execution_approvals(workspace_dir=tmp_path, status="requested")
    assert len(approvals) == 1
    assert approvals[0].id == "approval-exec-chat-runtime-mutation-1"
    assert approvals[0].ticket_id == "rd-9999"
    assert approvals[0].executor_id == "claude_code"
    assert approvals[0].required_capability == "repo:write"
    assert approvals[0].risk_level == "high"
    assert approvals[0].checkpoint_ref == result.checkpoint_ref
    assert approvals[0].executor_session_ref == result.executor_session_ref
    assert approvals[0].current_graph_node == "governance_gate"
    assert approvals[0].source_state_ref == result.approval_requests[0]["source_state_ref"]
    assert approvals[0].source_state_snapshot_ref.endswith(".json")
    assert "/execution_state_snapshots/" in f"/{approvals[0].source_state_snapshot_ref}"
    snapshot_path = (
        Path(approvals[0].source_state_snapshot_ref)
        if Path(approvals[0].source_state_snapshot_ref).is_absolute()
        else tmp_path / approvals[0].source_state_snapshot_ref
    )
    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot_payload["snapshot_schema"] == "execution_state_snapshot.v1"
    assert snapshot_payload["source_state_ref"] == approvals[0].source_state_ref
    assert snapshot_payload["source_state_snapshot_ref"] == approvals[0].source_state_snapshot_ref
    assert snapshot_payload["checkpoint_ref"] == result.checkpoint_ref
    assert snapshot_payload["executor_session_ref"] == result.executor_session_ref
    assert snapshot_payload["current_graph_node"] == "governance_gate"
    assert approvals[0].proposed_action["executor_id"] == "claude_code"
    assert approvals[0].source_request["action_plan"]["action"] == "implement_ticket"
    reconstructed = ExecutionRequest.model_validate(approvals[0].source_request)
    sessions = load_execution_sessions(tmp_path / ".aiteamos")
    approval_session = next(item for item in sessions.values() if item["last_request_id"] == request.request_id)
    assert reconstructed.ticket_id == "rd-9999"
    assert approval_session["status"] == "needs_approval"
    assert approval_session["checkpoint_ref"] == result.checkpoint_ref
    assert approval_session["current_graph_node"] == "governance_gate"
    assert approval_session["source_state_ref"] == approvals[0].source_state_ref
    assert approvals[0].id in approval_session["approval_refs"]


async def test_governance_service_creates_ticket_through_dispatch_and_ingestion(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()

    service = ChatGovernanceService(workspace_dir=tmp_path / ".aiteamos")
    request, result = await service.handle_message(
        ChatGovernanceInput(
            message="Create ticket for Alex to add runtime dispatch tests",
            employee={"id": "alex", "display_name": "Alex", "role": "AI RD"},
            selected_ai_engine="stub",
            thread_id="thread-runtime",
            run_id="run-runtime-create",
            trace_ref=".aiteamos/traces/run-runtime-create.jsonl",
        )
    )

    assert request.action_plan.action == "create_ticket"
    assert result.status == "completed"
    assert result.output_ticket_id.startswith(("ops-", "rd-"))
    assert get_ticket(result.output_ticket_id) is not None


async def test_ingestion_appends_report_to_existing_ticket(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Runtime report ingestion",
            assigned_employee_id="alex",
            source_run_id="seed",
        )
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(reporter_employee_id="alex", content="seed report", source_run_id="seed"),
    )

    service = ChatGovernanceService(
        workspace_dir=tmp_path / ".aiteamos",
        ingestion_service=ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos"),
    )
    _, result = await service.handle_message(
        ChatGovernanceInput(
            message=f"Report Ticket {ticket.id}: dispatch path completed",
            employee={"id": "alex", "display_name": "Alex", "role": "AI RD"},
            selected_ai_engine="stub",
            thread_id="thread-runtime",
            run_id="run-runtime-report",
            ticket_keys=[ticket.id],
            trace_ref=".aiteamos/traces/run-runtime-report.jsonl",
        )
    )

    updated = get_ticket(ticket.id)
    report_artifact = next((item for item in result.artifacts if item.get("kind") == "ticket_report_request"), {})
    assert result.status == "completed"
    assert report_artifact["ticket_id"] == ticket.id
    assert report_artifact["report_type"] == "progress"
    assert "dispatch path completed" in report_artifact["content"]
    assert updated is not None
    assert any("dispatch path completed" in report.content for report in updated.reports)


async def test_langgraph_validation_request_artifact_is_ingested(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Runtime validation request",
            assigned_employee_id="alex",
            source_run_id="seed-validation-request",
        )
    )
    request = ExecutionRequest(
        request_id="run-validation-request",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(
            action="request_validation",
            arguments={"validation_employee_id": "peter", "validation_role": "AI PV"},
        ),
        task_context={
            "task_summary": f"Request validation for Ticket {ticket.id}.",
            "employee": {"id": "alex", "display_name": "Alex", "role": "AI RD"},
        },
        permission_policy={"selected_ai_engine": "stub"},
        trace_context={"run_id": "run-validation-request", "trace_ref": ".aiteamos/traces/run-validation-request.jsonl"},
    )

    result = await ExecutionDispatchService().dispatch(request)
    ingested = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos").ingest(request, result)
    updated = get_ticket(ticket.id)
    validation_artifact = next((item for item in result.artifacts if item.get("kind") == "validation_request"), {})

    assert result.executor_id == "universal_employee_agent"
    assert validation_artifact["ticket_id"] == ticket.id
    assert validation_artifact["validation_employee_id"] == "peter"
    assert ingested.output_ticket_id == ticket.id
    assert updated is not None
    assert updated.validation_employee_id == "peter"
    assert updated.validation_role == "AI PV"
    assert any(event.type == "validation_requested" for event in updated.events)


def test_choose_employee_for_goal_routes_to_fixed_employee_profiles():
    profiles = [
        {"id": "alex", "display_name": "Alex", "role": "AI RD / Implementer", "skills": ["runtime-engineering"]},
        {"id": "peter", "display_name": "Peter", "role": "AI PV", "skills": ["validation"]},
        {"id": "maya", "display_name": "Maya", "role": "Memory Curator", "skills": ["graphiti", "docs"]},
    ]

    rd = choose_employee_for_goal("Implement backend runtime loop", profiles, current_employee_id="clara")
    pv = choose_employee_for_goal("Validate pytest evidence", profiles, current_employee_id="clara")
    memory = choose_employee_for_goal("Recall Graphiti memory assets", profiles, current_employee_id="clara")

    assert rd["target_employee_id"] == "alex"
    assert pv["target_employee_id"] == "peter"
    assert memory["target_employee_id"] == "maya"


def test_choose_employee_for_goal_uses_handoff_policy_and_current_load():
    profiles = [
        {
            "id": "alex",
            "display_name": "Alex",
            "role": "AI RD / Implementer",
            "skill_refs": ["backend-api-implementation"],
            "capability_tags": ["backend-api-implementation", "runtime"],
            "permission_policy": {"permissions": ["repo:write", "terminal:run"]},
            "handoff_policy": {"can_receive_handoffs": False, "accepts_lanes": ["rd"]},
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
        {
            "id": "victor",
            "display_name": "Victor",
            "role": "AI RD / Implementer",
            "skill_refs": ["backend-api-implementation"],
            "capability_tags": ["backend-api-implementation", "runtime", "code"],
            "permission_policy": {"permissions": ["repo:write"]},
            "handoff_policy": {"can_receive_handoffs": True, "accepts_lanes": ["rd"], "preferred_lanes": ["rd"]},
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
        {
            "id": "peter",
            "display_name": "Peter",
            "role": "AI PV",
            "skill_refs": ["validation-strategy"],
            "capability_tags": ["validation", "evidence-review"],
            "permission_policy": {"permissions": ["read_validation_evidence"]},
            "handoff_policy": {"can_receive_handoffs": True, "accepts_lanes": ["pv"], "max_active_tickets": 1},
            "current_load": {"active_ticket_count": 1, "status": "busy"},
        },
        {
            "id": "nora",
            "display_name": "Nora",
            "role": "AI PV",
            "skill_refs": ["validation-strategy"],
            "capability_tags": ["validation", "evidence-review", "qa"],
            "permission_policy": {"permissions": ["read_validation_evidence"]},
            "handoff_policy": {"can_receive_handoffs": True, "accepts_lanes": ["pv"]},
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
    ]

    rd = choose_employee_for_goal("Implement backend runtime loop", profiles, current_employee_id="clara")
    pv = choose_employee_for_goal("Validate pytest evidence", profiles, current_employee_id="clara")

    assert rd["target_employee_id"] == "victor"
    assert rd["policy"]["policy_aware"] is True
    assert rd["policy"]["load_status"] == "available"
    assert "handoff_policy" in rd["reason"]
    assert pv["target_employee_id"] == "nora"
    assert pv["policy"]["active_ticket_count"] == 0


def test_choose_employee_for_goal_uses_profile_work_history_summary():
    profiles = [
        {
            "id": "alex",
            "display_name": "Alex",
            "role": "AI RD / Implementer",
            "skill_refs": ["backend-api-implementation"],
            "capability_tags": ["backend-api-implementation", "runtime"],
            "permission_policy": {"permissions": ["repo:write"]},
            "handoff_policy": {"can_receive_handoffs": True, "accepts_lanes": ["rd"]},
            "current_load": {"active_ticket_count": 0, "status": "available"},
            "work_history_summary": {
                "source": "employee_work_ledger",
                "report_count": 2,
                "runtime_run_count": 2,
                "approved_asset_count": 1,
            },
        },
        {
            "id": "victor",
            "display_name": "Victor",
            "role": "AI RD / Implementer",
            "skill_refs": ["backend-api-implementation"],
            "capability_tags": ["backend-api-implementation", "runtime"],
            "permission_policy": {"permissions": ["repo:write"]},
            "handoff_policy": {"can_receive_handoffs": True, "accepts_lanes": ["rd"]},
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
    ]

    decision = choose_employee_for_goal("Implement backend runtime loop", profiles, current_employee_id="clara")

    assert decision["target_employee_id"] == "alex"
    assert decision["policy"]["work_history_score"] > 0
    assert decision["policy"]["work_history_summary"]["runtime_run_count"] == 2
    assert "work_history" in decision["reason"]


def test_choose_employee_for_goal_respects_memory_scope_and_risk_boundary():
    profiles = [
        {
            "id": "alex",
            "display_name": "Alex",
            "role": "AI RD / Implementer",
            "skill_refs": ["backend-api-implementation"],
            "capability_tags": ["backend-api-implementation", "runtime", "code"],
            "permission_policy": {"permissions": ["repo:write"]},
            "memory_scopes": ["aiteamos"],
            "handoff_policy": {
                "can_receive_handoffs": True,
                "accepts_lanes": ["rd"],
                "max_risk_level": "medium",
            },
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
        {
            "id": "victor",
            "display_name": "Victor",
            "role": "AI RD / Implementer",
            "skill_refs": ["backend-api-implementation"],
            "capability_tags": ["backend-api-implementation", "runtime", "code"],
            "permission_policy": {"permissions": ["repo:write"]},
            "memory_scopes": ["aiteamos", "employee:victor"],
            "handoff_policy": {
                "can_receive_handoffs": True,
                "accepts_lanes": ["rd"],
                "preferred_lanes": ["rd"],
                "max_risk_level": "critical",
            },
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
    ]

    decision = choose_employee_for_goal(
        "Implement production migration using employee:victor scoped context",
        profiles,
        current_employee_id="clara",
    )

    assert decision["target_employee_id"] == "victor"
    assert decision["policy"]["required_memory_scopes"] == ["employee:victor"]
    assert decision["policy"]["matched_memory_scopes"] == ["employee:victor"]
    assert decision["policy"]["memory_scope_match"] == "matched"
    assert decision["policy"]["risk_level"] == "critical"
    assert decision["policy"]["max_risk_level"] == "critical"
    assert decision["policy"]["risk_allowed"] is True
    assert "memory_scope matched" in decision["reason"]
    assert "risk_boundary=critical" in decision["reason"]


def test_choose_employee_for_goal_reuses_ticket_backed_work_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Handoff work history evidence",
            description="Alex has prior implementation evidence that should affect handoff scoring.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-handoff-work-history",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content="Implemented prior runtime work with evidence.",
            evidence=["pytest::handoff-work-history::passed"],
            report_type="progress",
            source_run_id="run-handoff-work-history-report",
        ),
    )
    profiles = [
        {
            "id": "alex",
            "display_name": "Alex",
            "role": "AI RD / Implementer",
            "skill_refs": ["backend-api-implementation"],
            "capability_tags": ["backend-api-implementation", "runtime"],
            "permission_policy": {"permissions": ["repo:write"]},
            "handoff_policy": {"can_receive_handoffs": True, "accepts_lanes": ["rd"]},
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
        {
            "id": "victor",
            "display_name": "Victor",
            "role": "AI RD / Implementer",
            "skill_refs": ["backend-api-implementation"],
            "capability_tags": ["backend-api-implementation", "runtime"],
            "permission_policy": {"permissions": ["repo:write"]},
            "handoff_policy": {"can_receive_handoffs": True, "accepts_lanes": ["rd"]},
            "current_load": {"active_ticket_count": 0, "status": "available"},
        },
    ]

    decision = choose_employee_for_goal("Implement backend runtime loop", profiles, current_employee_id="clara")

    assert decision["target_employee_id"] == "alex"
    assert decision["policy"]["work_history_score"] > 0
    assert decision["policy"]["work_history_summary"]["source"] == "employee_work_ledger"
    assert decision["policy"]["work_history_summary"]["report_count"] == 1


async def test_universal_agent_handoff_artifact_records_ticket_events_and_report(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Employee handoff runtime",
            description="Clara should hand implementation work to Alex.",
            ticket_type="rd",
            assigned_employee_id="clara",
            assigned_role="AI Team OS Manager",
            source_run_id="seed-handoff",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="run-employee-handoff",
        workspace_id=str(tmp_path),
        employee_id="clara",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="answer_only", arguments={"message": "Implement the backend runtime loop."}),
        task_context={
            "task_summary": "Implement the backend runtime loop.",
            "employee": {"id": "clara", "display_name": "Clara", "role": "AI Team OS Manager"},
            "employee_profiles": [
                {"id": "clara", "display_name": "Clara", "role": "AI Team OS Manager"},
                {"id": "alex", "display_name": "Alex", "role": "AI RD / Implementer", "skills": ["runtime-engineering"]},
                {"id": "peter", "display_name": "Peter", "role": "AI PV", "skills": ["validation"]},
            ],
        },
        permission_policy={"selected_ai_engine": "stub"},
        trace_context={"run_id": "run-employee-handoff", "trace_ref": ".aiteamos/traces/run-employee-handoff.jsonl"},
    )

    result = await ExecutionDispatchService().dispatch(request)
    ingested = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos").ingest(request, result)
    updated = get_ticket(ticket.id)
    clara_work = employee_work_ledger("clara")
    sessions = load_execution_sessions(tmp_path / ".aiteamos")
    session = next(item for item in sessions.values() if item["last_request_id"] == request.request_id)
    handoff_artifact = next((item for item in result.artifacts if item.get("kind") == "employee_handoff_request"), {})

    assert result.executor_id == "universal_employee_agent"
    assert handoff_artifact["to_employee_id"] == "alex"
    assert handoff_artifact["policy"]["policy_aware"] is True
    assert any(event.get("event") == "universal_agent.handoff.proposed" for event in result.tool_events)
    assert ingested.output_ticket_id == ticket.id
    assert updated is not None
    assert updated.assigned_employee_id == "alex"
    assert any(event.type == "handoff_requested" for event in updated.events)
    assert any(report.report_type == "employee_handoff" for report in updated.reports)
    assert any(event.get("data", {}).get("command", {}).get("id") == "tickets.manage:handoff" for event in ingested.tool_events)
    assert clara_work.handoffs and clara_work.handoffs[0]["ticket_id"] == ticket.id


async def test_ticket_native_loop_step_dispatches_ticket_bound_request_and_ingests_report(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket native loop step",
            description="Autonomous loop should advance one governed Ticket-bound step.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    class FakeDispatch:
        request: ExecutionRequest | None = None

        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            self.request = request
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="completed",
                report="Ticket loop step completed with evidence.",
                output_ticket_id=request.ticket_id,
                evidence=[{"kind": "loop_evidence", "ref": "pytest::ticket-loop-step::passed"}],
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                started_at="2026-06-18T00:00:00+00:00",
                finished_at="2026-06-18T00:00:01+00:00",
            )

    fake_dispatch = FakeDispatch()
    response = await TicketAutonomousLoopService(
        workspace_dir=tmp_path / ".aiteamos",
        dispatch_service=fake_dispatch,  # type: ignore[arg-type]
    ).run_step(
        ticket.id,
        TicketLoopStepRequest(
            employee_id="alex",
            message="Advance one Ticket-native autonomous loop step.",
            selected_executor="universal_employee_agent",
            selected_ai_engine="universal_employee_agent",
        ),
    )

    updated = get_ticket(ticket.id)
    sessions = load_execution_sessions(tmp_path / ".aiteamos")
    session_key = f"alex::ticket-loop-{ticket.id}::{ticket.id}"

    assert response.status == "completed"
    assert response.stop_reason == "single_step_completed"
    assert response.ingested is True
    assert response.loop_state["step_count"] == 1
    assert fake_dispatch.request is not None
    assert fake_dispatch.request.ticket_binding.ticket_id == ticket.id
    assert fake_dispatch.request.action_plan.action == "append_report"
    assert fake_dispatch.request.trace_context["loop_kind"] == "ticket_native_step"
    assert fake_dispatch.request.trace_context["loop_step"] == 1
    assert fake_dispatch.request.trace_context["ticket_status_before"] == "assigned"
    assert fake_dispatch.request.trace_context["validation_gate"]["status"] == "not_required"
    assert fake_dispatch.request.task_context["universal_context"]["summary"]["ticket_id"] == ticket.id
    assert updated is not None
    assert updated.reports[-1].report_type == "autonomous_loop_step"
    assert "Ticket loop step completed" in updated.reports[-1].content
    assert "pytest::ticket-loop-step::passed" in updated.reports[-1].evidence
    assert response.loop_state["loop_step"] == 1
    assert response.loop_state["ticket_status_before"] == "assigned"
    assert response.loop_state["ticket_status_after"] == "assigned"
    assert response.loop_state["validation_gate"]["status"] == "not_required"
    assert response.loop_state["next_stop_reason"] == "single_step_completed"
    assert sessions[session_key]["status"] == "completed"
    assert sessions[session_key]["checkpoint_ref"].startswith("langgraph:ticket-loop-")


async def test_ticket_native_loop_run_records_each_step_until_max_steps(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket native loop run",
            description="Autonomous loop should run bounded repeated steps.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-run",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    class FakeDispatch:
        requests: list[ExecutionRequest] = []

        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            self.requests.append(request)
            step = len(self.requests)
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="completed",
                report=f"Ticket loop step {step} completed.",
                output_ticket_id=request.ticket_id,
                evidence=[{"kind": "loop_evidence", "ref": f"pytest::ticket-loop-run::{step}"}],
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                started_at=f"2026-06-18T00:00:0{step}+00:00",
                finished_at=f"2026-06-18T00:00:0{step + 1}+00:00",
            )

    fake_dispatch = FakeDispatch()
    response = await TicketAutonomousLoopService(
        workspace_dir=tmp_path / ".aiteamos",
        dispatch_service=fake_dispatch,  # type: ignore[arg-type]
    ).run_loop(
        ticket.id,
        TicketLoopRunRequest(
            employee_id="alex",
            message="Run bounded Ticket-native autonomous loop.",
            max_steps=2,
            selected_executor="universal_employee_agent",
            selected_ai_engine="universal_employee_agent",
        ),
    )

    updated = get_ticket(ticket.id)
    sessions = load_execution_sessions(tmp_path / ".aiteamos")
    runs = list_ticket_loop_runs(ticket.id, workspace_dir=tmp_path / ".aiteamos")
    run_detail = get_ticket_loop_run(ticket.id, str(response.loop_state["run_id"]), workspace_dir=tmp_path / ".aiteamos")

    assert response.status == "completed"
    assert response.stop_reason == "max_steps_reached"
    assert response.loop_state["run_id"].startswith(f"ticket-loop-run-{ticket.id}-")
    assert response.loop_state["step_count"] == 2
    assert len(response.steps) == 2
    assert len(runs) == 1
    assert runs[0].run_id == response.loop_state["run_id"]
    assert runs[0].status == "completed"
    assert runs[0].stop_reason == "max_steps_reached"
    assert runs[0].step_count == 2
    assert runs[0].active is False
    assert runs[0].response["loop_state"]["run_id"] == response.loop_state["run_id"]
    assert run_detail is not None
    assert run_detail.saved_path == ".aiteamos/ticket_loop_runs.json"
    assert len(fake_dispatch.requests) == 2
    assert fake_dispatch.requests[0].trace_context["thread_id"] == f"ticket-loop-{ticket.id}-step-1"
    assert fake_dispatch.requests[1].trace_context["thread_id"] == f"ticket-loop-{ticket.id}-step-2"
    assert fake_dispatch.requests[0].trace_context["loop_step"] == 1
    assert fake_dispatch.requests[1].trace_context["loop_step"] == 2
    assert response.steps[0].loop_state["loop_step"] == 1
    assert response.steps[1].loop_state["loop_step"] == 2
    assert updated is not None
    assert [report.content for report in updated.reports[-2:]] == [
        "Ticket loop step 1 completed.",
        "Ticket loop step 2 completed.",
    ]
    assert f"alex::ticket-loop-{ticket.id}-step-1::{ticket.id}" in sessions
    assert f"alex::ticket-loop-{ticket.id}-step-2::{ticket.id}" in sessions


async def test_ticket_native_loop_run_stops_at_approval_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket native loop approval stop",
            description="Autonomous loop should stop when runtime requests approval.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-approval",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    class FakeDispatch:
        requests: list[ExecutionRequest] = []

        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            self.requests.append(request)
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="claude_code",
                status="needs_approval",
                report="Repository mutation requires approval.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"claude-code:{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                approval_requests=[
                    {
                        "required_capability": "repo:write",
                        "executor_id": "claude_code",
                        "checkpoint_ref": f"langgraph:{request.request_id}",
                        "current_graph_node": "governance_gate",
                    }
                ],
                errors=[{"reason": "repo_mutation_approval_required", "detail": "repo:write requires approval"}],
                started_at="2026-06-18T00:00:00+00:00",
                finished_at="2026-06-18T00:00:01+00:00",
            )

    fake_dispatch = FakeDispatch()
    response = await TicketAutonomousLoopService(
        workspace_dir=tmp_path / ".aiteamos",
        dispatch_service=fake_dispatch,  # type: ignore[arg-type]
    ).run_loop(
        ticket.id,
        TicketLoopRunRequest(employee_id="alex", message="Run loop until approval gate.", max_steps=3),
    )
    approvals = list_execution_approvals(workspace_dir=tmp_path, status="requested")
    updated = get_ticket(ticket.id)

    assert response.status == "needs_approval"
    assert response.stop_reason == "approval_required"
    assert response.loop_state["step_count"] == 1
    assert len(response.steps) == 1
    assert len(fake_dispatch.requests) == 1
    assert approvals and approvals[0].ticket_id == ticket.id
    assert updated is not None
    assert updated.status == "waiting_approval"


async def test_ticket_loop_policy_registry_caps_run_and_controls_approval_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket loop policy registry",
            description="Loop policy should cap run bounds and control approval requirements.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-policy",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    policy = update_ticket_loop_policy(
        ticket.id,
        TicketLoopPolicyUpdateRequest(
            max_steps=1,
            max_runtime_seconds=10,
            approval_requirements=["repo:write", "ticket:state:transition"],
            sla={
                "response_due_seconds": 3600,
                "review_due_seconds": 7200,
                "escalation_employee_id": "clara",
                "escalation_role": "AI Team OS Manager",
            },
            recurrence={
                "enabled": True,
                "interval_seconds": 86400,
                "max_occurrences": 3,
                "next_run_at": "2026-06-20T09:00:00+00:00",
            },
            closeout={
                "auto_propose_assets": True,
                "auto_settle_assets": True,
                "auto_approve_candidates": True,
                "project_graphiti": False,
                "project_relationships": False,
                "require_validation_evidence": True,
                "asset_types": ["ticket_closeout", "solution"],
            },
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Cap loop while policy registry is under review.",
        ),
        workspace_dir=tmp_path / ".aiteamos",
    )

    class FakeDispatch:
        requests: list[ExecutionRequest] = []

        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            self.requests.append(request)
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="completed",
                report="Policy capped loop step completed.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                started_at="2026-06-18T00:00:00+00:00",
                finished_at="2026-06-18T00:00:01+00:00",
            )

    fake_dispatch = FakeDispatch()
    response = await TicketAutonomousLoopService(
        workspace_dir=tmp_path / ".aiteamos",
        dispatch_service=fake_dispatch,  # type: ignore[arg-type]
    ).run_loop(
        ticket.id,
        TicketLoopRunRequest(employee_id="alex", message="Run up to three steps, unless policy caps it.", max_steps=3),
    )
    updated = get_ticket(ticket.id)

    assert policy.source == "policy_registry"
    assert policy.sla.response_due_seconds == 3600
    assert policy.recurrence.enabled is True
    assert policy.closeout.asset_types == ["ticket_closeout", "solution"]
    assert len(fake_dispatch.requests) == 1
    assert response.loop_state["max_steps"] == 1
    assert response.loop_state["requested_max_steps"] == 3
    assert response.loop_state["policy"]["approval_requirements"] == ["repo:write", "ticket:state:transition"]
    assert response.loop_state["policy"]["sla"]["review_due_seconds"] == 7200
    assert response.loop_state["policy"]["recurrence"]["next_run_at"] == "2026-06-20T09:00:00+00:00"
    assert response.loop_state["policy"]["closeout"]["asset_types"] == ["ticket_closeout", "solution"]
    assert response.loop_state["policy"]["closeout"]["auto_settle_assets"] is True
    assert response.loop_state["policy"]["closeout"]["auto_approve_candidates"] is True
    assert fake_dispatch.requests[0].approval_policy["require_approval_for"] == ["repo:write", "ticket:state:transition"]
    assert fake_dispatch.requests[0].permission_policy["loop_policy"]["source"] == "policy_registry"
    assert fake_dispatch.requests[0].permission_policy["loop_policy"]["sla"]["response_due_seconds"] == 3600
    assert fake_dispatch.requests[0].permission_policy["loop_policy"]["recurrence"]["enabled"] is True
    assert fake_dispatch.requests[0].permission_policy["loop_policy"]["closeout"]["auto_propose_assets"] is True
    assert fake_dispatch.requests[0].permission_policy["loop_policy"]["closeout"]["auto_settle_assets"] is True
    assert updated is not None
    assert any(report.report_type == "loop_policy_updated" for report in updated.reports)
    assert any(".aiteamos/ticket_loop_policies.json" in report.evidence for report in updated.reports)


def test_ticket_loop_policy_routes_read_and_update_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    client = TestClient(create_app())
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket loop policy route",
            description="Route should expose per-Ticket loop policy.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-policy-route",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    initial = client.get(f"/api/v1/tickets/{ticket.id}/loop/policy")
    updated = client.put(
        f"/api/v1/tickets/{ticket.id}/loop/policy",
        json={
            "max_steps": 2,
            "stop_statuses": ["validated", "blocked"],
            "sla": {
                "response_due_seconds": 1800,
                "review_due_seconds": 5400,
                "escalation_employee_id": "clara",
                "escalation_role": "AI Team OS Manager",
            },
            "recurrence": {
                "enabled": True,
                "interval_seconds": 43200,
                "max_occurrences": 5,
                "next_run_at": "2026-06-20T10:00:00+00:00",
            },
            "closeout": {
                "auto_propose_assets": True,
                "auto_settle_assets": True,
                "auto_approve_candidates": True,
                "project_graphiti": True,
                "project_relationships": True,
                "require_validation_evidence": True,
                "asset_types": ["ticket_closeout", "solution", "validation_result"],
            },
            "actor_employee_id": "clara",
            "actor_role": "AI Team OS Manager",
            "reason": "Allow two bounded loop steps from dashboard policy control.",
        },
    )
    timeline = client.get(f"/api/v1/tickets/{ticket.id}/loop/timeline")
    ticket_after_update = get_ticket(ticket.id)

    assert initial.status_code == 200
    assert initial.json()["max_steps"] == 3
    assert initial.json()["sla"]["response_due_seconds"] is None
    assert initial.json()["recurrence"]["enabled"] is False
    assert updated.status_code == 200
    assert updated.json()["max_steps"] == 2
    assert updated.json()["stop_statuses"] == ["validated", "blocked"]
    assert updated.json()["sla"]["response_due_seconds"] == 1800
    assert updated.json()["recurrence"]["interval_seconds"] == 43200
    assert updated.json()["closeout"]["asset_types"] == ["ticket_closeout", "solution", "validation_result"]
    assert updated.json()["closeout"]["auto_settle_assets"] is True
    assert updated.json()["closeout"]["auto_approve_candidates"] is True
    assert updated.json()["closeout"]["project_graphiti"] is True
    assert updated.json()["closeout"]["project_relationships"] is True
    assert updated.json()["source"] == "policy_registry"
    assert timeline.status_code == 200
    policy_status = timeline.json()["summary"]["policy"]
    assert policy_status["source"] == "policy_registry"
    assert policy_status["configured"] == {"sla": True, "recurrence": True, "closeout": True}
    assert policy_status["sla"]["review_due_seconds"] == 5400
    assert policy_status["recurrence"]["next_run_at"] == "2026-06-20T10:00:00+00:00"
    assert policy_status["closeout"]["require_validation_evidence"] is True
    assert policy_status["closeout"]["auto_settle_assets"] is True
    assert policy_status["saved_path"] == ".aiteamos/ticket_loop_policies.json"
    assert ticket_after_update is not None
    assert any(report.report_type == "loop_policy_updated" for report in ticket_after_update.reports)


async def test_ticket_loop_run_routes_list_and_detail_records(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    client = TestClient(create_app())
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket loop run routes",
            description="Loop run registry should be visible through Ticket APIs.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-run-routes",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    class FakeDispatch:
        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="completed",
                report="Route-visible loop run completed.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                started_at="2026-06-18T00:00:00+00:00",
                finished_at="2026-06-18T00:00:01+00:00",
            )

    await TicketAutonomousLoopService(
        workspace_dir=tmp_path / ".aiteamos",
        dispatch_service=FakeDispatch(),  # type: ignore[arg-type]
    ).run_loop(
        ticket.id,
        TicketLoopRunRequest(
            employee_id="alex",
            message="Run one route-visible loop step.",
            max_steps=1,
            runtime_config={"loop_run_id": "ticket-loop-run-route-visible"},
        ),
    )

    listed = client.get(f"/api/v1/tickets/{ticket.id}/loop/runs")
    detail = client.get(f"/api/v1/tickets/{ticket.id}/loop/runs/ticket-loop-run-route-visible")
    missing = client.get(f"/api/v1/tickets/{ticket.id}/loop/runs/missing-run")
    runtime_evidence = client.get(f"/api/v1/tickets/{ticket.id}/runtime-evidence")

    assert listed.status_code == 200
    assert listed.json()[0]["run_id"] == "ticket-loop-run-route-visible"
    assert listed.json()[0]["ticket_id"] == ticket.id
    assert listed.json()[0]["status"] == "completed"
    assert listed.json()[0]["step_count"] == 1
    assert listed.json()[0]["saved_path"] == ".aiteamos/ticket_loop_runs.json"
    assert detail.status_code == 200
    assert detail.json()["run_id"] == "ticket-loop-run-route-visible"
    assert detail.json()["response"]["loop_state"]["run_id"] == "ticket-loop-run-route-visible"
    assert missing.status_code == 404
    assert runtime_evidence.status_code == 200
    runtime_payload = runtime_evidence.json()
    assert runtime_payload["source_counts"]["loop_runs"] == 1
    assert runtime_payload["latest_loop_run"]["run_id"] == "ticket-loop-run-route-visible"
    assert runtime_payload["latest_loop_run"]["status"] == "completed"
    assert runtime_payload["latest_loop_run"]["step_count"] == 1


def test_ticket_loop_timeline_and_resume_route_project_ticket_os_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    client = TestClient(create_app())
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket loop timeline resume",
            description="Timeline should merge Ticket facts before resume.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-timeline",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="clara",
            reporter_role="AI Team OS Manager",
            content="Approval was granted and the loop is ready to resume.",
            evidence=["pytest::ticket-loop-timeline::passed"],
            report_type="approval_approved",
            source_run_id="approval-ticket-loop-timeline",
        ),
    )
    transition_ticket_state(
        ticket.id,
        TicketStateTransitionRequest(
            status="ready_to_resume",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            source_run_id="approval-ticket-loop-timeline",
        ),
    )
    save_execution_session(
        workspace,
        employee_id="alex",
        thread_id=f"ticket-loop-{ticket.id}",
        ticket_id=ticket.id,
        executor_id="universal_employee_agent",
        executor_session_ref="lg-ticket-loop-timeline",
        checkpoint_ref="langgraph:ticket-loop-timeline",
        last_request_id="ticket-loop-timeline-request",
        status="needs_approval",
        updated_at="2026-06-19T00:00:00+00:00",
        trace_ref=".aiteamos/traces/ticket-loop-timeline.jsonl",
    )

    service_timeline = ticket_loop_timeline(ticket.id, workspace_dir=workspace)
    timeline = client.get(f"/api/v1/tickets/{ticket.id}/loop/timeline")
    resume = client.post(
        f"/api/v1/tickets/{ticket.id}/loop/resume",
        json={
            "action": "resume",
            "employee_id": "alex",
            "max_steps": 1,
            "reason": "Resume after approval from the Ticket timeline.",
        },
    )
    updated = get_ticket(ticket.id)
    queue = list_ticket_loop_queue(workspace_dir=workspace, status="queued")
    resumed_timeline = ticket_loop_timeline(ticket.id, workspace_dir=workspace)

    assert service_timeline.summary.status == "ready_to_resume"
    assert service_timeline.summary.can_resume is True
    assert {"ticket_event", "ticket_report", "runtime_session"}.issubset({item.kind for item in service_timeline.items})
    assert timeline.status_code == 200
    assert timeline.json()["summary"]["next_action"] == "Resume the governed Ticket loop."
    assert any(item["kind"] == "runtime_session" for item in timeline.json()["items"])
    runtime_items = [item for item in timeline.json()["items"] if item["kind"] == "runtime_session"]
    assert runtime_items[0]["target_route"].startswith("runtime/")
    assert any(ref["kind"] == "checkpoint" and "target_route" in ref for ref in runtime_items[0]["refs"])
    report_items = [item for item in timeline.json()["items"] if item["kind"] == "ticket_report"]
    assert report_items[0]["target_route"].startswith(f"tickets/reports/{ticket.id}::report::")
    assert any(ref["kind"] == "evidence" and "::evidence::" in ref["target_route"] for ref in report_items[0]["refs"])
    assert resume.status_code == 200
    assert resume.json()["previous_status"] == "ready_to_resume"
    assert resume.json()["status"] == "in_progress"
    assert resume.json()["queue_item"]["status"] == "queued"
    assert resume.json()["queue_item"]["request"]["max_steps"] == 1
    assert updated is not None
    assert updated.status == "in_progress"
    assert queue and queue[0].ticket_id == ticket.id
    assert resumed_timeline.summary.status == "in_progress"
    assert any(item.kind == "loop_queue" and item.source_ref == resume.json()["queue_item"]["queue_id"] for item in resumed_timeline.items)


def test_ticket_loop_retry_requires_new_evidence_and_projects_deep_links(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    client = TestClient(create_app())
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket loop retry evidence",
            description="Retry should require new Ticket evidence after evidence_requested review.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-retry-evidence",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="exec-ticket-loop-retry-evidence",
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="implement_ticket", arguments={"ticket_id": ticket.id}),
        task_context={"task_summary": "Implement the Ticket after governed evidence review.", "ticket": {"id": ticket.id}},
        capability_grants=["tickets:read", "repo:read", "repo:write"],
        approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
        trace_context={"run_id": "exec-ticket-loop-retry-evidence", "trace_ref": ".aiteamos/traces/exec-ticket-loop-retry-evidence.jsonl"},
    )
    result = ExecutionResult(
        request_id=request.request_id,
        executor_id="claude_code",
        status="needs_approval",
        report="Repository mutation needs approval and follow-up evidence.",
        output_ticket_id=ticket.id,
        approval_requests=[
            {
                "kind": "repo_mutation",
                "ticket_id": ticket.id,
                "executor_id": "claude_code",
                "required_capability": "repo:write",
                "risk_level": "high",
                "reason": "Need reviewer evidence before retry.",
                "proposed_action": {"summary": "Apply the Ticket implementation patch."},
                "checkpoint_ref": "langgraph:exec-ticket-loop-retry-evidence",
                "executor_session_ref": "lg-exec-ticket-loop-retry-evidence",
                "source_state_ref": "state://universal_employee_agent/exec-ticket-loop-retry-evidence",
                "current_graph_node": "governance_gate",
            }
        ],
        checkpoint_ref="langgraph:exec-ticket-loop-retry-evidence",
        executor_session_ref="lg-exec-ticket-loop-retry-evidence",
        trace_ref=".aiteamos/traces/exec-ticket-loop-retry-evidence.jsonl",
        started_at="2026-06-19T00:00:00+00:00",
        finished_at="2026-06-19T00:00:01+00:00",
    )
    ingested = ExecutionResultIngestionService(workspace_dir=workspace).ingest(request, result)
    approvals = list_execution_approvals(workspace_dir=tmp_path, status="requested")
    assert ingested.status == "needs_approval"
    assert len(approvals) == 1
    approval = approvals[0]

    reviewed = review_execution_approval(
        workspace_dir=tmp_path,
        approval_id=approval.id,
        review=ExecutionApprovalReviewRequest(
            status="ask_evidence",
            reviewer_employee_id="clara",
            reason="Attach validation evidence before retrying the runtime.",
        ),
    )
    save_execution_session(
        workspace,
        employee_id="alex",
        thread_id=f"ticket-loop-retry-{ticket.id}",
        ticket_id=ticket.id,
        executor_id="universal_employee_agent",
        executor_session_ref="lg-ticket-loop-retry-evidence",
        checkpoint_ref=reviewed.checkpoint_ref,
        last_request_id="ticket-loop-retry-evidence-request",
        status="needs_approval",
        updated_at="2026-06-19T00:00:02+00:00",
        trace_ref=".aiteamos/traces/ticket-loop-retry-evidence.jsonl",
        current_graph_node="governance_gate",
        source_state_ref=reviewed.source_state_ref,
        ticket_refs=[ticket.id],
        approval_refs=[approval.id],
    )
    waiting = get_ticket(ticket.id)
    blocked = client.post(
        f"/api/v1/tickets/{ticket.id}/loop/resume",
        json={
            "action": "retry_after_evidence",
            "employee_id": "alex",
            "max_steps": 1,
            "reason": "Retry without new evidence should stay blocked.",
        },
    )
    blocked_timeline = client.get(f"/api/v1/tickets/{ticket.id}/loop/timeline").json()
    retry_requirements = blocked_timeline["summary"]["retry_requirements"]

    assert reviewed.status == "evidence_requested"
    assert waiting is not None
    assert waiting.status == "waiting_evidence"
    assert blocked.status_code == 400
    assert "requires new Ticket evidence" in blocked.json()["detail"]
    assert [item["id"] for item in retry_requirements] == ["latest_evidence_requested_review", "new_evidence_after_review"]
    assert retry_requirements[0]["satisfied"] is True
    assert retry_requirements[0]["target_route"] == f"assets/review/runtime-approval:claude_code:{approval.id}"
    assert retry_requirements[1]["satisfied"] is False
    assert retry_requirements[1]["target_route"] == f"tickets/reports/{ticket.id}"

    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content="New retry evidence is attached after the evidence request.",
            evidence=["pytest::ticket-loop-retry-evidence::passed"],
            report_type="evidence",
            source_run_id="ticket-loop-retry-evidence-followup",
        ),
    )
    create_memory_candidate(
        MemoryCandidateCreateRequest(
            content="Retry after evidence_requested must include new Ticket evidence after the review timestamp.",
            source_kind="ticket_report",
            source_ref="ticket-loop-retry-evidence-followup",
            scope_kind="ticket",
            scope_ref=ticket.id,
            memory_type="fact",
            confidence=0.9,
            employee_ids=["alex"],
            tags=["ticket-loop", "retry-evidence"],
            provenance={
                "source_ticket_id": ticket.id,
                "source_employee_id": "alex",
                "source_run_id": "ticket-loop-retry-evidence-followup",
            },
        )
    )
    satisfied_timeline = client.get(f"/api/v1/tickets/{ticket.id}/loop/timeline").json()
    satisfied_retry_requirements = satisfied_timeline["summary"]["retry_requirements"]
    allowed = client.post(
        f"/api/v1/tickets/{ticket.id}/loop/resume",
        json={
            "action": "retry_after_evidence",
            "employee_id": "alex",
            "max_steps": 1,
            "reason": "Retry after evidence was attached.",
        },
    )
    timeline = client.get(f"/api/v1/tickets/{ticket.id}/loop/timeline")
    items = timeline.json()["items"]

    assert allowed.status_code == 200, allowed.text
    assert satisfied_retry_requirements[1]["satisfied"] is True
    assert satisfied_retry_requirements[1]["target_route"].startswith(f"tickets/reports/{ticket.id}::report::")
    assert allowed.json()["previous_status"] == "waiting_evidence"
    assert allowed.json()["status"] == "in_progress"
    assert timeline.status_code == 200
    assert any(
        item["kind"] == "approval"
        and item["target_route"] == f"assets/review/runtime-approval:claude_code:{approval.id}"
        for item in items
    )
    approval_resume = timeline.json()["summary"]["approval_resume"]
    queue_reliability = timeline.json()["summary"]["queue_reliability"]
    assert approval_resume[0]["approval_id"] == approval.id
    assert approval_resume[0]["status"] == "evidence_requested"
    assert approval_resume[0]["ready_to_run"] is False
    assert approval_resume[0]["target_route"] == f"assets/review/runtime-approval:claude_code:{approval.id}"
    assert queue_reliability["queued_count"] == 1
    assert queue_reliability["active_count"] == 1
    assert queue_reliability["status"] == "waiting_worker"
    assert any(item["kind"] == "runtime_session" and item["target_route"].startswith("runtime/") for item in items)
    assert any(item["kind"] == "asset" and item["target_route"].startswith("assets/asset/") for item in items)


async def test_ticket_loop_queue_enqueue_and_pump_runs_existing_loop_service(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket loop queue",
            description="Queued Ticket loop should be audited before worker execution.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-queue",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    queued = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="Run from the queue.",
            max_steps=1,
            priority=10,
            runtime_config={"loop_run_id": "ticket-loop-run-queued"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue this Ticket loop from Clara.",
        ),
        workspace_dir=workspace,
    )

    class FakeDispatch:
        requests: list[ExecutionRequest] = []

        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            self.requests.append(request)
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="completed",
                report="Queued loop step completed.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                started_at="2026-06-18T00:00:00+00:00",
                finished_at="2026-06-18T00:00:01+00:00",
            )

    fake_dispatch = FakeDispatch()
    queue_before = list_ticket_loop_queue(workspace_dir=workspace)
    run_before = get_ticket_loop_run(ticket.id, "ticket-loop-run-queued", workspace_dir=workspace)
    status_before = ticket_loop_queue_status(workspace_dir=workspace)
    ticket_after_enqueue = get_ticket(ticket.id)
    pump = await pump_ticket_loop_queue(
        TicketLoopQueuePumpRequest(max_items=1),
        workspace_dir=workspace,
        service=TicketAutonomousLoopService(
            workspace_dir=workspace,
            dispatch_service=fake_dispatch,  # type: ignore[arg-type]
        ),
    )
    queue_after = list_ticket_loop_queue(workspace_dir=workspace)
    run_after = get_ticket_loop_run(ticket.id, "ticket-loop-run-queued", workspace_dir=workspace)
    status_after = ticket_loop_queue_status(workspace_dir=workspace)

    assert queued.status == "queued"
    assert queued.run_id == "ticket-loop-run-queued"
    assert queued.report_id
    assert queue_before[0].queue_id == queued.queue_id
    assert status_before.status == "queued"
    assert status_before.queued_count == 1
    assert status_before.running_count == 0
    assert status_before.active_count == 1
    assert status_before.next_queue_id == queued.queue_id
    assert status_before.saved_paths["loop_queue"] == ".aiteamos/ticket_loop_queue.json"
    assert run_before is not None
    assert run_before.status == "queued"
    assert run_before.active is True
    assert ticket_after_enqueue is not None
    assert any(report.report_type == "loop_queued" for report in ticket_after_enqueue.reports)
    assert pump.status == "completed"
    assert pump.processed[0].queue_id == queued.queue_id
    assert pump.processed[0].status == "completed"
    assert pump.processed[0].response["loop_state"]["run_id"] == "ticket-loop-run-queued"
    assert pump.remaining_queued == 0
    assert len(fake_dispatch.requests) == 1
    assert queue_after[0].status == "completed"
    assert status_after.status == "idle"
    assert status_after.queued_count == 0
    assert status_after.completed_count == 1
    assert status_after.active_count == 0
    assert run_after is not None
    assert run_after.status == "completed"
    assert run_after.active is False
    assert run_after.step_count == 1


async def test_ticket_loop_queue_reliability_flags_duplicate_queued_work(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Duplicate queued Ticket loop",
            description="Repeated queued loop work should be visible before the worker runs.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-queue-duplicate",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="First queued loop.",
            max_steps=1,
            priority=10,
            runtime_config={"loop_run_id": "ticket-loop-run-duplicate-1"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue the first governed loop item.",
        ),
        workspace_dir=workspace,
    )
    enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="Second queued loop.",
            max_steps=1,
            priority=11,
            runtime_config={"loop_run_id": "ticket-loop-run-duplicate-2"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue the second governed loop item.",
        ),
        workspace_dir=workspace,
    )

    queue = list_ticket_loop_queue(workspace_dir=workspace)
    status = ticket_loop_queue_status(workspace_dir=workspace)
    timeline = ticket_loop_timeline(ticket.id, workspace_dir=workspace)
    reliability = timeline.summary.queue_reliability

    assert [item.status for item in queue] == ["queued", "queued"]
    assert status.status == "queued"
    assert status.queued_count == 2
    assert status.active_count == 2
    assert reliability is not None
    assert reliability.status == "duplicate_queued"
    assert reliability.queued_count == 2
    assert reliability.duplicate_queued_count == 1
    assert reliability.active_count == 2
    assert "multiple queued loop items" in reliability.detail
    assert sum(1 for item in timeline.items if item.kind == "loop_queue") == 2


async def test_ticket_loop_queue_reliability_flags_stale_running_work(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Stale running Ticket loop",
            description="Long-running queue work should be visible before operators trust the worker.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-queue-stale-running",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    queued = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="Long running queued loop.",
            max_steps=1,
            priority=10,
            runtime_config={"loop_run_id": "ticket-loop-run-stale-running"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue a loop item that will be marked stale running.",
        ),
        workspace_dir=workspace,
    )
    queue_path = workspace / "ticket_loop_queue.json"
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    payload["items"][queued.queue_id] = {
        **payload["items"][queued.queue_id],
        "status": "running",
        "started_at": "2026-06-18T00:00:00+00:00",
        "updated_at": "2026-06-18T00:00:00+00:00",
    }
    queue_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    status = ticket_loop_queue_status(workspace_dir=workspace)
    timeline = ticket_loop_timeline(ticket.id, workspace_dir=workspace)
    reliability = timeline.summary.queue_reliability

    assert status.status == "running"
    assert status.running_count == 1
    assert status.active_count == 1
    assert reliability is not None
    assert reliability.status == "stale_running"
    assert reliability.running_count == 1
    assert reliability.stale_running_count == 1
    assert reliability.stale_running_after_seconds == 900
    assert reliability.active_count == 1
    assert "stale-running threshold" in reliability.detail
    assert any(item.kind == "loop_queue" and item.status == "running" for item in timeline.items)


async def test_ticket_loop_queue_reliability_surfaces_blocked_provider_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Blocked provider Ticket loop",
            description="Provider setup blockers should remain visible on the Ticket queue timeline.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-queue-provider-blocked",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    queued = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="Run with a blocked provider.",
            max_steps=1,
            priority=10,
            runtime_config={"loop_run_id": "ticket-loop-run-provider-blocked"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue this Ticket loop against a provider that is not configured.",
        ),
        workspace_dir=workspace,
    )

    class FakeDispatch:
        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="blocked",
                report="DeepSeek provider is not configured.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                errors=[
                    {
                        "reason": "deepseek_provider_blocked",
                        "detail": "DeepSeek API key is not configured.",
                    }
                ],
                started_at="2026-06-18T00:00:00+00:00",
                finished_at="2026-06-18T00:00:01+00:00",
            )

    pump = await pump_ticket_loop_queue(
        TicketLoopQueuePumpRequest(max_items=1),
        workspace_dir=workspace,
        service=TicketAutonomousLoopService(
            workspace_dir=workspace,
            dispatch_service=FakeDispatch(),  # type: ignore[arg-type]
        ),
    )
    queue_after = list_ticket_loop_queue(workspace_dir=workspace)
    status_after = ticket_loop_queue_status(workspace_dir=workspace)
    run_after = get_ticket_loop_run(ticket.id, "ticket-loop-run-provider-blocked", workspace_dir=workspace)
    timeline = ticket_loop_timeline(ticket.id, workspace_dir=workspace)
    reliability = timeline.summary.queue_reliability

    assert pump.processed[0].queue_id == queued.queue_id
    assert pump.processed[0].status == "blocked"
    assert queue_after[0].status == "blocked"
    assert status_after.status == "needs_attention"
    assert status_after.failed_count == 1
    assert status_after.active_count == 0
    assert run_after is not None
    assert run_after.status == "blocked"
    assert run_after.stop_reason == "blocked_or_failed"
    assert reliability is not None
    assert reliability.status == "error"
    assert reliability.failed_count == 1
    assert reliability.active_count == 0
    assert reliability.detail == "At least one queued loop item failed."
    assert any(item.kind == "loop_queue" and item.status == "blocked" for item in timeline.items)


async def test_ticket_loop_queue_pump_auto_proposes_failure_retrospective_after_repeated_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Auto retrospective after repeated queue failures",
            description="The existing queue pump should trigger governed learning candidates after repeated failures.",
            ticket_type="ops",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-auto-retrospective",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    first = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="First blocked queue run.",
            max_steps=1,
            priority=10,
            runtime_config={"loop_run_id": "ticket-loop-auto-retro-1"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue first blocked run.",
        ),
        workspace_dir=workspace,
    )
    second = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="Second blocked queue run.",
            max_steps=1,
            priority=11,
            runtime_config={"loop_run_id": "ticket-loop-auto-retro-2"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue second blocked run.",
        ),
        workspace_dir=workspace,
    )

    class FakeDispatch:
        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="blocked",
                report="Provider is not configured for this queued Ticket loop.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                errors=[
                    {
                        "reason": "provider_not_configured",
                        "detail": "Provider is not configured for this queued Ticket loop.",
                    }
                ],
                started_at="2026-06-18T00:00:00+00:00",
                finished_at="2026-06-18T00:00:01+00:00",
            )

    pump = await pump_ticket_loop_queue(
        TicketLoopQueuePumpRequest(max_items=2),
        workspace_dir=workspace,
        service=TicketAutonomousLoopService(
            workspace_dir=workspace,
            dispatch_service=FakeDispatch(),  # type: ignore[arg-type]
        ),
    )

    assert [item.queue_id for item in pump.processed] == [first.queue_id, second.queue_id]
    assert [item.status for item in pump.processed] == ["blocked", "blocked"]
    assert len(pump.policy_actions) == 1
    action = pump.policy_actions[0]
    assert action.kind == "failure_retrospective_candidate"
    assert action.status == "proposed"
    assert action.report_id
    assert action.candidate_ids == [f"asset-candidate-ticket-loop-failure-retrospective-{ticket.id}"]

    candidates = list_asset_candidates(workspace_dir=tmp_path, asset_type="failure_retrospective")
    assert len(candidates) == 1
    assert candidates[0].id == action.candidate_ids[0]
    assert candidates[0].provenance["failed_item_count"] == 2
    assert candidates[0].provenance["queue_item_ids"] == [first.queue_id, second.queue_id]
    updated = get_ticket(ticket.id)
    assert updated is not None
    assert len([report for report in updated.reports if report.report_type == "ticket_loop_failure_retrospective_candidate"]) == 1


async def test_ticket_loop_queue_worker_status_records_recent_policy_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Worker records queue policy actions",
            description="Worker state should expose recent automatic governance actions.",
            ticket_type="ops",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-worker-policy-action",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    first = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="First blocked worker run.",
            max_steps=1,
            priority=10,
            runtime_config={"loop_run_id": "ticket-loop-worker-policy-1"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue first blocked worker run.",
        ),
        workspace_dir=workspace,
    )
    second = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="Second blocked worker run.",
            max_steps=1,
            priority=11,
            runtime_config={"loop_run_id": "ticket-loop-worker-policy-2"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue second blocked worker run.",
        ),
        workspace_dir=workspace,
    )

    class FakeDispatch:
        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="blocked",
                report="Provider remains blocked for worker policy action visibility.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                errors=[{"reason": "provider_blocked", "detail": "Provider remains blocked."}],
                started_at="2026-06-18T00:00:00+00:00",
                finished_at="2026-06-18T00:00:01+00:00",
            )

    worker = TicketLoopQueueWorker(
        workspace_dir=workspace,
        service=TicketAutonomousLoopService(
            workspace_dir=workspace,
            dispatch_service=FakeDispatch(),  # type: ignore[arg-type]
        ),
    )
    tick = await worker.tick(
        TicketLoopQueueWorkerControlRequest(
            interval_seconds=5,
            max_items=2,
            reason="Record recent policy action from worker tick.",
        )
    )
    worker_state_path = workspace / "ticket_loop_queue_worker.json"
    worker_state = json.loads(worker_state_path.read_text(encoding="utf-8"))["worker"]

    assert [item.queue_id for item in tick.pump.processed] == [first.queue_id, second.queue_id]
    assert len(tick.pump.policy_actions) == 1
    assert tick.status.total_policy_actions == 1
    assert tick.status.recent_policy_actions[0].kind == "failure_retrospective_candidate"
    assert tick.status.recent_policy_actions[0].report_id
    assert worker.status().recent_policy_actions[0].candidate_ids == tick.pump.policy_actions[0].candidate_ids
    assert worker_state["total_policy_actions"] == 1
    assert worker_state["recent_policy_actions"][0]["kind"] == "failure_retrospective_candidate"


async def test_ticket_loop_queue_worker_records_sla_and_auto_enqueues_recurrence(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Worker records SLA and recurrence preflight",
            description="Existing queue worker should surface policy due signals without a new scheduler.",
            ticket_type="ops",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-worker-policy-preflight",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    ticket_path = tmp_path / ticket.saved_path
    aged_events = []
    for line in ticket_path.read_text(encoding="utf-8").splitlines():
        payload = json.loads(line)
        if payload.get("type") == "created":
            payload["at"] = "2026-06-18T00:00:00+00:00"
        aged_events.append(payload)
    ticket_path.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False, sort_keys=True) for event in aged_events) + "\n",
        encoding="utf-8",
    )
    update_ticket_loop_policy(
        ticket.id,
        TicketLoopPolicyUpdateRequest(
            max_steps=1,
            sla={
                "response_due_seconds": 60,
                "review_due_seconds": None,
                "escalation_employee_id": "clara",
                "escalation_role": "AI Team OS Manager",
            },
            recurrence={
                "enabled": True,
                "interval_seconds": 3600,
                "max_occurrences": 2,
                "next_run_at": "2026-06-18T00:01:00+00:00",
            },
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Enable SLA and recurrence policy preflight.",
        ),
        workspace_dir=workspace,
    )
    class FakeDispatch:
        requests: list[ExecutionRequest] = []

        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            self.requests.append(request)
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="completed",
                report="Recurring Ticket loop run completed.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                started_at="2026-06-20T00:00:00+00:00",
                finished_at="2026-06-20T00:00:01+00:00",
            )

    fake_dispatch = FakeDispatch()
    worker = TicketLoopQueueWorker(
        workspace_dir=workspace,
        service=TicketAutonomousLoopService(
            workspace_dir=workspace,
            dispatch_service=fake_dispatch,  # type: ignore[arg-type]
        ),
    )

    tick = await worker.tick(
        TicketLoopQueueWorkerControlRequest(
            interval_seconds=5,
            max_items=2,
            reason="Run policy preflight without queued work.",
        )
    )
    second_tick = await worker.tick(
        TicketLoopQueueWorkerControlRequest(
            interval_seconds=5,
            max_items=1,
            reason="Policy preflight should be idempotent.",
        )
    )
    updated = get_ticket(ticket.id)
    timeline = ticket_loop_timeline(ticket.id, workspace_dir=workspace)
    queue = list_ticket_loop_queue(workspace_dir=workspace)
    policy = timeline.summary.policy
    report_types = [report.report_type for report in (updated.reports if updated is not None else [])]

    assert tick.pump.status == "completed"
    assert [item.status for item in tick.pump.processed] == ["completed", "completed"]
    assert [action.kind for action in tick.pump.policy_actions] == ["sla_escalation_handoff", "recurrence_auto_enqueued"]
    assert tick.pump.policy_actions[0].status == "escalated"
    assert tick.pump.policy_actions[0].handoff_refs[0]["kind"] == "handoff_requested"
    assert tick.pump.policy_actions[0].handoff_refs[0]["to_employee_id"] == "clara"
    assert tick.pump.policy_actions[0].queue_ids == [queue[0].queue_id]
    assert tick.pump.policy_actions[0].run_ids == [queue[0].run_id]
    assert tick.pump.policy_actions[1].status == "queued"
    assert tick.pump.policy_actions[1].queue_ids == [queue[1].queue_id]
    assert tick.pump.policy_actions[1].run_ids == [queue[1].run_id]
    assert tick.status.total_policy_actions == 2
    assert tick.status.recent_policy_actions[-2].kind == "sla_escalation_handoff"
    assert tick.status.recent_policy_actions[-1].kind == "recurrence_auto_enqueued"
    assert second_tick.pump.status == "idle"
    assert second_tick.pump.processed == []
    assert second_tick.pump.policy_actions == []
    assert len(fake_dispatch.requests) == 2
    assert fake_dispatch.requests[0].employee_id == "clara"
    assert fake_dispatch.requests[0].permission_policy["runtime_config"]["sla_escalation_source_run_id"] == (
        f"ticket-loop-sla-{ticket.id}-response"
    )
    assert fake_dispatch.requests[0].permission_policy["runtime_config"]["sla_due_at"] == "2026-06-18T00:01:00+00:00"
    assert fake_dispatch.requests[1].employee_id == "clara"
    assert fake_dispatch.requests[1].permission_policy["runtime_config"]["recurrence_source_run_id"].startswith(
        f"ticket-loop-recurrence-{ticket.id}-"
    )
    assert fake_dispatch.requests[1].permission_policy["runtime_config"]["recurrence_due_at"] == "2026-06-18T00:01:00+00:00"
    assert queue[0].status == "completed"
    assert queue[0].request["runtime_config"]["sla_escalation_source_run_id"] == f"ticket-loop-sla-{ticket.id}-response"
    assert queue[1].status == "completed"
    assert queue[1].request["runtime_config"]["recurrence_occurrence"] == 1
    assert updated is not None
    assert updated.assigned_employee_id == "clara"
    assert any(event.type == "handoff_requested" for event in updated.events)
    assert report_types.count("ticket_loop_sla_breach") == 1
    assert report_types.count("ticket_loop_recurrence_due") == 1
    assert report_types.count("loop_queued") == 2
    assert policy is not None
    assert policy.recurrence.enabled is True
    assert policy.recurrence.next_run_at != "2026-06-18T00:01:00+00:00"
    assert any(
        item.kind == "ticket_report" and item.status == "ticket_loop_sla_breach"
        for item in timeline.items
    )
    assert any(
        item.kind == "ticket_report" and item.status == "ticket_loop_recurrence_due"
        for item in timeline.items
    )


async def test_ticket_loop_queue_routes_enqueue_list_and_pump(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    client = TestClient(create_app())
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket loop queue route",
            description="Queue routes should expose queued loop work.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-queue-route",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    enqueued = client.post(
        f"/api/v1/tickets/{ticket.id}/loop/queue",
        json={
            "employee_id": "alex",
            "message": "Queue from HTTP.",
            "max_steps": 1,
            "priority": 20,
            "runtime_config": {"loop_run_id": "ticket-loop-run-http-queued"},
            "actor_employee_id": "clara",
            "actor_role": "AI Team OS Manager",
            "reason": "Queue from dashboard.",
        },
    )
    listed = client.get("/api/v1/tickets/loop/queue")
    status_before = client.get("/api/v1/tickets/loop/queue/status")
    pumped = client.post("/api/v1/tickets/loop/queue/pump", json={"max_items": 1})
    status_after = client.get("/api/v1/tickets/loop/queue/status")

    assert enqueued.status_code == 200
    assert enqueued.json()["run_id"] == "ticket-loop-run-http-queued"
    assert enqueued.json()["status"] == "queued"
    assert enqueued.json()["saved_path"] == ".aiteamos/ticket_loop_queue.json"
    assert listed.status_code == 200
    assert listed.json()[0]["queue_id"] == enqueued.json()["queue_id"]
    assert listed.json()[0]["ticket_id"] == ticket.id
    assert status_before.status_code == 200
    assert status_before.json()["status"] == "queued"
    assert status_before.json()["queued_count"] == 1
    assert status_before.json()["next_run_id"] == "ticket-loop-run-http-queued"
    assert status_before.json()["saved_paths"]["loop_runs"] == ".aiteamos/ticket_loop_runs.json"
    assert pumped.status_code == 200
    assert pumped.json()["processed"][0]["queue_id"] == enqueued.json()["queue_id"]
    assert pumped.json()["processed"][0]["status"] in {"completed", "partial", "needs_approval"}
    assert pumped.json()["saved_paths"]["loop_queue"] == ".aiteamos/ticket_loop_queue.json"
    assert status_after.status_code == 200
    assert status_after.json()["queued_count"] == 0
    assert status_after.json()["active_count"] == 0


async def test_ticket_loop_queue_worker_daemon_pumps_queue_and_records_status(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket loop queue worker daemon",
            description="The queue worker should daemonize existing governed queue pump behavior.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-worker",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="Run from worker daemon.",
            max_steps=1,
            priority=10,
            runtime_config={"loop_run_id": "ticket-loop-run-worker-daemon"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue this Ticket loop for the worker daemon.",
        ),
        workspace_dir=workspace,
    )

    class FakeDispatch:
        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="completed",
                report="Worker daemon loop step completed.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                started_at="2026-06-18T00:00:00+00:00",
                finished_at="2026-06-18T00:00:01+00:00",
            )

    worker = TicketLoopQueueWorker(
        workspace_dir=workspace,
        service=TicketAutonomousLoopService(
            workspace_dir=workspace,
            dispatch_service=FakeDispatch(),  # type: ignore[arg-type]
        ),
    )
    started = await worker.start(
        TicketLoopQueueWorkerControlRequest(
            interval_seconds=0.1,
            max_items=1,
            reason="Start worker daemon from test.",
        )
    )
    try:
        for _ in range(20):
            queue = list_ticket_loop_queue(workspace_dir=workspace)
            if queue and queue[0].status == "completed":
                break
            await asyncio.sleep(0.02)
    finally:
        stopped = await worker.stop("Stop worker daemon from test.")

    queue_after = list_ticket_loop_queue(workspace_dir=workspace)
    run_after = get_ticket_loop_run(ticket.id, "ticket-loop-run-worker-daemon", workspace_dir=workspace)
    worker_state_path = workspace / "ticket_loop_queue_worker.json"
    worker_state = json.loads(worker_state_path.read_text(encoding="utf-8"))["worker"]

    assert started.status == "running"
    assert started.running is True
    assert stopped.status == "stopped"
    assert stopped.running is False
    assert queue_after[0].status == "completed"
    assert run_after is not None
    assert run_after.status == "completed"
    assert worker.status().total_processed == 1
    assert worker.status().last_tick_status in {"completed", "idle"}
    assert worker_state["saved_path"] == ".aiteamos/ticket_loop_queue_worker.json"
    assert worker_state["total_processed"] == 1


async def test_ticket_loop_queue_worker_routes_status_and_tick(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    client = TestClient(create_app())
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket loop queue worker route",
            description="Worker routes should expose governed tick status.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-worker-route",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    enqueued = client.post(
        f"/api/v1/tickets/{ticket.id}/loop/queue",
        json={
            "employee_id": "alex",
            "message": "Queue from worker route.",
            "max_steps": 1,
            "priority": 10,
            "runtime_config": {"loop_run_id": "ticket-loop-run-worker-route"},
            "actor_employee_id": "clara",
            "actor_role": "AI Team OS Manager",
            "reason": "Queue from worker route test.",
        },
    )
    status_before = client.get("/api/v1/tickets/loop/queue/worker/status")
    tick = client.post(
        "/api/v1/tickets/loop/queue/worker/tick",
        json={
            "interval_seconds": 5,
            "max_items": 1,
            "reason": "Manual worker tick from test.",
        },
    )
    status_after = client.get("/api/v1/tickets/loop/queue/worker/status")

    assert enqueued.status_code == 200
    assert status_before.status_code == 200
    assert status_before.json()["saved_path"] == ".aiteamos/ticket_loop_queue_worker.json"
    assert tick.status_code == 200
    assert tick.json()["pump"]["processed"][0]["run_id"] == "ticket-loop-run-worker-route"
    assert tick.json()["status"]["last_tick_status"] in {"completed", "partial", "needs_approval"}
    assert tick.json()["status"]["saved_path"] == ".aiteamos/ticket_loop_queue_worker.json"
    assert status_after.status_code == 200
    assert status_after.json()["total_processed"] == 1


async def test_ticket_loop_control_stop_blocks_run_and_continue_unblocks_sessions(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket loop control",
            description="Human stop and continue should be governed and audited.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-control",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    session_thread_id = f"ticket-loop-{ticket.id}-step-1"
    save_execution_session(
        workspace,
        employee_id="alex",
        thread_id=session_thread_id,
        ticket_id=ticket.id,
        executor_id="universal_employee_agent",
        executor_session_ref="lg-existing-loop",
        checkpoint_ref="langgraph:existing-loop",
        last_request_id="ticket-loop-existing",
        status="running",
        updated_at="2026-06-18T00:00:00+00:00",
    )

    stop_response = control_ticket_loop(
        ticket.id,
        TicketLoopControlRequest(
            action="stop",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Human stopped this loop from the Ticket cockpit.",
        ),
        workspace_dir=workspace,
    )

    class FakeDispatch:
        requests: list[ExecutionRequest] = []

        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            self.requests.append(request)
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="completed",
                report="Loop continued after human control.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                started_at="2026-06-18T00:00:01+00:00",
                finished_at="2026-06-18T00:00:02+00:00",
            )

    fake_dispatch = FakeDispatch()
    stopped_run = await TicketAutonomousLoopService(
        workspace_dir=workspace,
        dispatch_service=fake_dispatch,  # type: ignore[arg-type]
    ).run_loop(ticket.id, TicketLoopRunRequest(employee_id="alex", message="This should not run while stopped.", max_steps=1))
    sessions_after_stop = load_execution_sessions(workspace)
    session_key = f"alex::{session_thread_id}::{ticket.id}"
    ticket_after_stop = get_ticket(ticket.id)

    assert stop_response.state.action == "stop"
    assert stop_response.state.active is True
    assert stop_response.state.updated_session_count == 1
    assert stop_response.report_id
    assert stop_response.saved_paths["loop_controls"] == ".aiteamos/ticket_loop_controls.json"
    assert sessions_after_stop[session_key]["status"] == "stopped"
    assert sessions_after_stop[session_key]["control_state"]["action"] == "stop"
    assert stopped_run.status == "stopped"
    assert stopped_run.stop_reason == "control:stop"
    assert stopped_run.loop_state["control"]["action"] == "stop"
    assert fake_dispatch.requests == []
    assert ticket_after_stop is not None
    assert any(report.report_type == "loop_control" for report in ticket_after_stop.reports)

    continue_response = control_ticket_loop(
        ticket.id,
        TicketLoopControlRequest(
            action="continue",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Human cleared the stop and continued this loop.",
        ),
        workspace_dir=workspace,
    )
    sessions_after_continue_control = load_execution_sessions(workspace)
    continued_run = await TicketAutonomousLoopService(
        workspace_dir=workspace,
        dispatch_service=fake_dispatch,  # type: ignore[arg-type]
    ).run_loop(ticket.id, TicketLoopRunRequest(employee_id="alex", message="Continue the governed loop.", max_steps=1))

    assert continue_response.state.action == "continue"
    assert continue_response.state.active is False
    assert sessions_after_continue_control[session_key]["status"] == "ready_to_continue"
    assert continued_run.status == "completed"
    assert continued_run.stop_reason == "max_steps_reached"
    assert len(fake_dispatch.requests) == 1


def test_ticket_loop_control_route_records_ticket_report_and_session_control(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    workspace = tmp_path / ".aiteamos"
    client = TestClient(create_app())
    ticket = create_ticket(
        TicketCreateRequest(
            title="Ticket loop control route",
            description="Dashboard should be able to stop a Ticket loop through HTTP.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-ticket-loop-control-route",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    save_execution_session(
        workspace,
        employee_id="alex",
        thread_id=f"ticket-loop-{ticket.id}-step-1",
        ticket_id=ticket.id,
        executor_id="universal_employee_agent",
        executor_session_ref="lg-route-loop",
        checkpoint_ref="langgraph:route-loop",
        last_request_id="ticket-loop-route",
        status="running",
        updated_at="2026-06-18T00:00:00+00:00",
    )

    response = client.post(
        f"/api/v1/tickets/{ticket.id}/loop/control",
        json={
            "action": "pause",
            "actor_employee_id": "clara",
            "actor_role": "AI Team OS Manager",
            "reason": "Pause while waiting for human review.",
        },
    )
    updated = get_ticket(ticket.id)
    sessions = load_execution_sessions(workspace)
    session = next(item for item in sessions.values() if item["ticket_id"] == ticket.id)

    assert response.status_code == 200
    assert response.json()["state"]["action"] == "pause"
    assert response.json()["state"]["active"] is True
    assert response.json()["updated_sessions"][0]["status"] == "paused"
    assert response.json()["saved_paths"]["loop_controls"] == ".aiteamos/ticket_loop_controls.json"
    assert session["control_state"]["action"] == "pause"
    assert updated is not None
    assert updated.reports[-1].report_type == "loop_control"
    assert updated.reports[-1].content == "Pause while waiting for human review."


def test_ticket_loop_step_route_returns_404_for_missing_ticket(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()

    response = TestClient(create_app()).post("/api/v1/tickets/missing-ticket/loop/step", json={})

    assert response.status_code == 404


def test_validated_ticket_closeout_generates_reviewable_asset_candidates(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    client = TestClient(create_app())
    ticket = create_ticket(
        TicketCreateRequest(
            title="Generate closeout learning candidates",
            description="A validated Ticket should propose durable learning Assets before Graphiti projection.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            validation_employee_id="peter",
            validation_role="AI PV",
            source_run_id="seed-closeout-candidates",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content="Implemented the closeout candidate generator.",
            report_type="result",
            evidence=["pytest::closeout-candidates::result"],
            source_run_id="run-closeout-result",
        ),
    )

    blocked = client.post(
        f"/api/v1/tickets/{ticket.id}/closeout-candidates",
        json={"actor_employee_id": "clara", "reason": "Closeout before validation must block."},
    )
    assert blocked.status_code == 400
    assert "Only validated" in blocked.json()["detail"]

    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="peter",
            reporter_role="AI PV",
            content="Validation passed with focused evidence.",
            report_type="validation",
            evidence=["pytest::closeout-candidates::validation"],
            source_run_id="run-closeout-validation",
        ),
    )
    auto_generated_candidates = list_asset_candidates(workspace_dir=tmp_path)
    assert {candidate.asset_type for candidate in auto_generated_candidates} == {"ticket_closeout", "solution", "validation_result"}
    auto_ticket = get_ticket(ticket.id)
    assert auto_ticket is not None
    auto_closeout_reports = [report for report in auto_ticket.reports if report.report_type == "ticket_closeout_candidates"]
    assert len(auto_closeout_reports) == 1
    assert "Auto-proposed after validation report" in auto_closeout_reports[0].content

    proposed = client.post(
        f"/api/v1/tickets/{ticket.id}/closeout-candidates",
        json={"actor_employee_id": "clara", "reason": "Validated Ticket is ready for durable learning review."},
    )
    assert proposed.status_code == 200
    payload = proposed.json()
    assert payload["status"] == "skipped"
    assert payload["ticket_id"] == ticket.id
    assert payload["report_id"]
    assert payload["saved_paths"]["asset_candidates"].endswith("assets/candidates.json")
    asset_types = {candidate["asset_type"] for candidate in payload["candidates"]}
    assert asset_types == {"ticket_closeout", "solution", "validation_result"}
    closeout = next(candidate for candidate in payload["candidates"] if candidate["asset_type"] == "ticket_closeout")
    assert closeout["scope_kind"] == "ticket"
    assert closeout["scope_ref"] == ticket.id
    assert closeout["status"] == "proposed"
    assert closeout["review_state"] == "proposed"
    assert closeout["provider"] == "local_file"
    assert closeout["provenance"]["source_ticket_id"] == ticket.id
    assert closeout["provenance"]["asset_type"] == "ticket_closeout"
    assert "pytest::closeout-candidates::validation" in closeout["provenance"]["evidence_refs"]
    assert closeout["relationships"][0]["target_ref"] == ticket.id

    candidates = list_asset_candidates(workspace_dir=tmp_path)
    assert {candidate.asset_type for candidate in candidates} == {"ticket_closeout", "solution", "validation_result"}
    solution_candidate = next(candidate for candidate in candidates if candidate.asset_type == "solution")
    approved_solution = client.post(
        f"/api/v1/assets/candidates/{solution_candidate.id}/review",
        json={
            "status": "approved",
            "reviewer_employee_id": "clara",
            "reason": "Validated Ticket solution is reusable.",
        },
    )
    assert approved_solution.status_code == 200
    assert approved_solution.json()["asset"]["asset_type"] == "solution"
    assert approved_solution.json()["asset"]["scope_ref"] == ticket.id
    assert any(record.asset_type == "solution" for record in list_asset_records(asset_type="solution", workspace_dir=tmp_path))
    updated = get_ticket(ticket.id)
    assert updated is not None
    closeout_reports = [report for report in updated.reports if report.report_type == "ticket_closeout_candidates"]
    assert len(closeout_reports) == 1
    assert all(ref.startswith("asset-candidate:") for ref in closeout_reports[0].evidence)

    repeated = client.post(
        f"/api/v1/tickets/{ticket.id}/closeout-candidates",
        json={"actor_employee_id": "clara"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "skipped"
    updated_again = get_ticket(ticket.id)
    assert updated_again is not None
    assert len([report for report in updated_again.reports if report.report_type == "ticket_closeout_candidates"]) == 1


def test_repeated_ticket_loop_failures_generate_reviewable_retrospective_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    client = TestClient(create_app())
    workspace = tmp_path / ".aiteamos"
    ticket = create_ticket(
        TicketCreateRequest(
            title="Retrospect repeated queue failures",
            description="Repeated blocked queue work should propose a reusable failure retrospective Asset.",
            ticket_type="ops",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-failure-retrospective",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    first = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="First blocked queue run.",
            max_steps=1,
            priority=10,
            runtime_config={"loop_run_id": "ticket-loop-run-retro-1"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue the first blocked run.",
        ),
        workspace_dir=workspace,
    )
    blocked = client.post(
        f"/api/v1/tickets/{ticket.id}/failure-retrospective-candidates",
        json={"actor_employee_id": "clara", "min_failed_items": 2},
    )
    assert blocked.status_code == 400
    assert "At least 2 failed or blocked loop queue items" in blocked.json()["detail"]

    second = enqueue_ticket_loop(
        ticket.id,
        TicketLoopEnqueueRequest(
            employee_id="alex",
            message="Second blocked queue run.",
            max_steps=1,
            priority=11,
            runtime_config={"loop_run_id": "ticket-loop-run-retro-2"},
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Queue the second blocked run.",
        ),
        workspace_dir=workspace,
    )
    queue_path = workspace / "ticket_loop_queue.json"
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    payload["items"][first.queue_id] = {
        **payload["items"][first.queue_id],
        "status": "blocked",
        "error": "DeepSeek provider is not configured.",
        "updated_at": "2026-06-18T00:00:00+00:00",
    }
    payload["items"][second.queue_id] = {
        **payload["items"][second.queue_id],
        "status": "failed",
        "error": "Runtime executor failed after provider retry.",
        "updated_at": "2026-06-18T00:01:00+00:00",
    }
    queue_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    proposed = client.post(
        f"/api/v1/tickets/{ticket.id}/failure-retrospective-candidates",
        json={
            "actor_employee_id": "clara",
            "actor_role": "AI Team OS Manager",
            "reason": "Repeated provider failures should become reusable operational learning.",
            "min_failed_items": 2,
        },
    )

    assert proposed.status_code == 200
    body = proposed.json()
    assert body["status"] == "proposed"
    assert body["failed_item_count"] == 2
    assert body["report_id"]
    candidate = body["candidates"][0]
    assert candidate["asset_type"] == "failure_retrospective"
    assert candidate["scope_kind"] == "ticket"
    assert candidate["scope_ref"] == ticket.id
    assert candidate["source_kind"] == "ticket_loop_failure_retrospective"
    assert candidate["provenance"]["failed_item_count"] == 2
    assert candidate["provenance"]["queue_item_ids"] == [first.queue_id, second.queue_id]
    assert candidate["provenance"]["failure_statuses"] == ["blocked", "failed"]
    assert "DeepSeek provider is not configured" in candidate["content"]
    assert body["saved_paths"]["asset_candidates"] == ".aiteamos/assets/candidates.json"
    assert any(item.id == candidate["id"] and item.asset_type == "failure_retrospective" for item in list_asset_candidates(workspace_dir=tmp_path))
    updated = get_ticket(ticket.id)
    assert updated is not None
    retro_reports = [report for report in updated.reports if report.report_type == "ticket_loop_failure_retrospective_candidate"]
    assert len(retro_reports) == 1
    assert retro_reports[0].evidence == [f"asset-candidate:{candidate['id']}"]

    repeated = client.post(
        f"/api/v1/tickets/{ticket.id}/failure-retrospective-candidates",
        json={"actor_employee_id": "clara", "min_failed_items": 2},
    )
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "skipped"
    updated_again = get_ticket(ticket.id)
    assert updated_again is not None
    assert len([report for report in updated_again.reports if report.report_type == "ticket_loop_failure_retrospective_candidate"]) == 1


def test_ticket_closeout_auto_trigger_blocks_without_validation_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Backend change without validation evidence",
            description="Backend API change must not become durable learning before evidence exists.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            validation_employee_id="peter",
            validation_role="AI PV",
            source_run_id="seed-closeout-blocker",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    transitioned = transition_ticket_state(
        ticket.id,
        TicketStateTransitionRequest(
            status="validated",
            actor_employee_id="peter",
            actor_role="AI PV",
            source_run_id="run-closeout-blocked-validation",
        ),
    )

    assert transitioned.status == "validated"
    assert list_asset_candidates(workspace_dir=tmp_path) == []
    updated = get_ticket(ticket.id)
    assert updated is not None
    blocker_reports = [report for report in updated.reports if report.report_type == "ticket_closeout_blocked"]
    assert len(blocker_reports) == 1
    assert "Auto closeout blocked" in blocker_reports[0].content
    assert "validation evidence is incomplete" in blocker_reports[0].content


async def test_plane_setup_blocker_blocks_ticket_creation_without_fake_completion(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("PLANE_API_KEY", raising=False)

    service = ChatGovernanceService(workspace_dir=tmp_path / ".aiteamos")
    request, result = await service.handle_message(
        ChatGovernanceInput(
            message="Create ticket for Alex to verify Plane setup blockers",
            employee={"id": "alex", "display_name": "Alex", "role": "AI RD"},
            selected_ai_engine="stub",
            thread_id="thread-plane-blocker",
            run_id="run-plane-blocker",
            trace_ref=".aiteamos/traces/run-plane-blocker.jsonl",
        )
    )

    assert request.action_plan.action == "create_ticket"
    assert result.status == "blocked"
    assert result.output_ticket_id == ""
    assert "Plane Ticket Backend is selected but setup is incomplete" in result.report


def test_context_records_graphiti_recall_provenance():
    context = ExecutionContextService().build(
        message="Use prior runtime dispatch lesson",
        employee={"id": "alex", "display_name": "Alex"},
        employee_profiles=[],
        ticket_keys=["rd-0001"],
        memory_refs=[
            {
                "memory_id": "mem-runtime-dispatch",
                "confidence": 0.91,
                "graphiti_recalled": True,
                "graphiti_episode_id": "episode-runtime-dispatch",
                "provenance": {
                    "asset_id": "mem-runtime-dispatch",
                    "source_ticket_id": "rd-0000",
                    "source_employee_id": "clara",
                    "source_run_id": "run-prior",
                },
            }
        ],
        selected_ai_engine="stub",
    )

    assert context.recalled_memories[0]["memory_id"] == "mem-runtime-dispatch"
    assert context.recall_trace[0]["graphiti_recalled"] is True
    assert context.recall_trace[0]["source_asset"] == "mem-runtime-dispatch"
    assert "raw secrets" in context.exclusions


async def test_clara_led_ticket_loop_records_report_validation_and_employee_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()

    service = ChatGovernanceService(workspace_dir=tmp_path / ".aiteamos")
    _, created = await service.handle_message(
        ChatGovernanceInput(
            message="Create ticket for Alex to implement Clara-led operating loop",
            employee={"id": "alex", "display_name": "Alex", "role": "AI RD"},
            selected_ai_engine="stub",
            thread_id="thread-loop",
            run_id="run-loop-create",
            trace_ref=".aiteamos/traces/run-loop-create.jsonl",
        )
    )
    ticket_id = created.output_ticket_id

    _, report = await service.handle_message(
        ChatGovernanceInput(
            message=f"Report Ticket {ticket_id}: implementation completed with evidence",
            employee={"id": "alex", "display_name": "Alex", "role": "AI RD"},
            selected_ai_engine="stub",
            thread_id="thread-loop",
            run_id="run-loop-report",
            ticket_keys=[ticket_id],
            trace_ref=".aiteamos/traces/run-loop-report.jsonl",
        )
    )
    _, validation = await service.handle_message(
        ChatGovernanceInput(
            message=f"Ticket {ticket_id} validation passed with pytest evidence",
            employee={"id": "peter", "display_name": "Peter", "role": "AI PV"},
            selected_ai_engine="stub",
            thread_id="thread-loop",
            run_id="run-loop-validation",
            ticket_keys=[ticket_id],
            trace_ref=".aiteamos/traces/run-loop-validation.jsonl",
        )
    )

    ticket = get_ticket(ticket_id)
    assert created.status == "completed"
    assert report.status == "completed"
    assert validation.status == "completed"
    assert ticket is not None
    assert ticket.assigned_employee_id == "alex"
    assert ticket.status == "validated"
    assert any(item.report_type == "progress" for item in ticket.reports)
    assert any(item.report_type == "validation" for item in ticket.reports)


async def test_local_tool_executor_lists_code_repositories_through_dispatch(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    repo_dir = tmp_path / "repo"
    (repo_dir / ".git").mkdir(parents=True)
    (repo_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    upsert_code_repository(
        CodeRepositoryUpsertRequest(
            id="repo-aiteamos",
            name="AITeamOS",
            provider="local",
            location=str(repo_dir),
            default_branch="main",
        )
    )

    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-list-repos",
            employee_id="clara",
            ticket_binding=TicketBinding(mode="none", required=False),
            action_plan=ChatActionPlan(action="list_code_repositories", arguments={"message": "列出代码仓库"}),
        )
    )

    completed = next(event for event in result.tool_events if event["event"] == "command.completed")
    assert result.executor_id == "local_tool"
    assert result.status == "completed"
    assert "代码仓库" in result.report
    assert completed["data"]["command"]["id"] == "repositories.list:list"
    assert completed["data"]["repositories"][0]["id"] == "repo-aiteamos"


async def test_local_tool_executor_searches_knowledge_through_dispatch(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "PRODUCT_DIRECTION.md").write_text(
        "# Product Direction\n\nKnowledge flow links Docs, Memories, Decisions, and Review Queue.\n",
        encoding="utf-8",
    )

    result = await ExecutionDispatchService().dispatch(
        ExecutionRequest(
            request_id="exec-search-knowledge",
            employee_id="clara",
            ticket_binding=TicketBinding(mode="none", required=False),
            action_plan=ChatActionPlan(
                action="search_knowledge",
                arguments={"message": "搜索知识库 Knowledge flow", "query": "Knowledge flow"},
            ),
        )
    )

    completed = next(event for event in result.tool_events if event["event"] == "command.completed")
    assert result.executor_id == "local_tool"
    assert result.status == "completed"
    assert "我搜索了 Knowledge" in result.report
    assert completed["data"]["command"]["id"] == "knowledge.search:search"
    assert completed["data"]["results"][0]["source_ref"] == "PRODUCT_DIRECTION.md"


async def test_chat_can_start_governed_self_bootstrap_improvement_batch(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()

    service = ChatGovernanceService(workspace_dir=tmp_path / ".aiteamos")
    request, result = await service.handle_message(
        ChatGovernanceInput(
            message="Start next self-bootstrap batch with 2 improvement Tickets",
            employee={"id": "clara", "display_name": "Clara", "role": "AI Team OS Manager"},
            selected_ai_engine="stub",
            thread_id="thread-self-bootstrap-start",
            run_id="run-self-bootstrap-start",
            trace_ref=".aiteamos/traces/run-self-bootstrap-start.jsonl",
        )
    )

    completed = next(
        event
        for event in result.tool_events
        if event.get("data", {}).get("command", {}).get("id") == "tickets.manage:self_bootstrap_start"
        and event.get("event") == "command.completed"
    )
    created_tickets = completed["data"]["tickets"]
    first_ticket = get_ticket(created_tickets[0]["id"])
    candidates = list_memory_candidates(status="proposed")

    assert request.action_plan.action == "self_bootstrap_start"
    assert request.ticket_binding.mode == "create"
    assert result.executor_id == "local_tool"
    assert result.status == "completed"
    assert result.output_ticket_id == created_tickets[0]["id"]
    assert len(created_tickets) == 2
    assert first_ticket is not None
    assert first_ticket.assigned_employee_id == "alex"
    assert first_ticket.validation_employee_id == "peter"
    assert "Acceptance Criteria" in first_ticket.description
    assert result.learning_delta["created_ticket_ids"] == [ticket["id"] for ticket in created_tickets]
    assert len(candidates) == 1
    assert candidates[0].scope_kind == "ticket"
    assert candidates[0].scope_ref == result.output_ticket_id
    assert candidates[0].provenance["action"] == "self_bootstrap_start"


async def test_terminal_run_is_ticket_bound_and_records_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()

    service = ChatGovernanceService(workspace_dir=tmp_path / ".aiteamos")
    _, blocked = await service.handle_message(
        ChatGovernanceInput(
            message="terminal.run `pwd`",
            employee={"id": "clara", "display_name": "Clara", "role": "AI Team OS Manager"},
            selected_ai_engine="stub",
            thread_id="thread-terminal-blocked",
            run_id="run-terminal-blocked",
            trace_ref=".aiteamos/traces/run-terminal-blocked.jsonl",
        )
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Terminal evidence via runtime dispatch",
            description="Run bounded terminal evidence.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="seed-terminal",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request, needs_approval = await service.handle_message(
        ChatGovernanceInput(
            message=f"terminal.run `pwd` ticket_id={ticket.id}",
            employee={"id": "alex", "display_name": "Alex", "role": "AI RD / Implementer"},
            selected_ai_engine="stub",
            thread_id="thread-terminal",
            run_id="run-terminal",
            ticket_keys=[ticket.id],
            trace_ref=".aiteamos/traces/run-terminal.jsonl",
        )
    )
    approvals = list_execution_approvals(workspace_dir=tmp_path, status="requested")
    approval_id = approvals[0].id
    approved_request = request.model_copy(
        update={
            "request_id": "run-terminal-approved",
            "approval_policy": {
                **request.approval_policy,
                "approval_refs": [approval_id],
                "approved_capabilities": ["terminal:run"],
            },
            "trace_context": {
                **request.trace_context,
                "approval_ref": approval_id,
                "approval_resume": True,
                "source_request_id": request.request_id,
                "run_id": "run-terminal-approved",
            },
        }
    )
    result = await ExecutionDispatchService().dispatch(approved_request)
    result = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos").ingest(approved_request, result)

    updated = get_ticket(ticket.id)
    graph = ticket_graph_projection(ticket.id)
    edge_types = {edge.type for edge in graph.edges} if graph else set()

    assert blocked.status == "blocked"
    assert blocked.errors[0]["reason"] == "Ticket binding is required before dispatch."
    assert request.action_plan.action == "terminal_run"
    assert request.ticket_binding.mode == "existing"
    assert "terminal:run" in request.approval_policy["require_approval_for"]
    assert needs_approval.executor_id == "local_tool"
    assert needs_approval.status == "needs_approval"
    assert needs_approval.approval_requests[0]["required_capability"] == "terminal:run"
    assert needs_approval.approval_requests[0]["current_graph_node"] == "terminal_run_approval_gate"
    assert approvals[0].ticket_id == ticket.id
    assert approvals[0].executor_id == "local_tool"
    assert approvals[0].required_capability == "terminal:run"
    assert result.executor_id == "local_tool"
    assert result.status == "completed"
    assert "terminal.run completed" in result.report
    assert updated is not None
    assert any(report.report_type == "terminal_evidence" and report.evidence[0].startswith("terminal:") for report in updated.reports)
    assert any(event.get("data", {}).get("command", {}).get("id") == "terminal.run:run" for event in result.tool_events)
    assert graph is not None
    assert "run.calls.tool" in edge_types
    assert "run.produces.evidence" in edge_types


async def test_repository_inspection_execution_artifacts_project_into_ticket_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    repo_dir = tmp_path / "repo"
    (repo_dir / ".git").mkdir(parents=True)
    (repo_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    source_file = repo_dir / "apps" / "dashboard" / "src" / "pages" / "tickets" / "index.tsx"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("export const TicketGraphEvidence = 'runtime artifact graph evidence';\n", encoding="utf-8")
    upsert_code_repository(
        CodeRepositoryUpsertRequest(
            id="repo-aiteamos",
            name="AITeamOS",
            provider="local",
            location=str(repo_dir),
            default_branch="main",
        )
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Runtime artifact graph projection",
            description="Inspect Ticket graph evidence",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            code_repository_ids=["repo-aiteamos"],
            source_run_id="run-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    service = ChatGovernanceService(workspace_dir=tmp_path / ".aiteamos")
    request, result = await service.handle_message(
        ChatGovernanceInput(
            message=f"Alex, inspect Ticket {ticket.id} implementation for TicketGraphEvidence",
            employee={"id": "alex", "display_name": "Alex", "role": "AI RD / Implementer"},
            selected_ai_engine="stub",
            thread_id="thread-artifact-graph",
            run_id="run-artifact-graph",
            ticket_keys=[ticket.id],
            trace_ref=".aiteamos/traces/run-artifact-graph.jsonl",
        )
    )

    graph = ticket_graph_projection(ticket.id)
    edge_types = {edge.type for edge in graph.edges} if graph else set()
    assert request.action_plan.action == "inspect_code_repository"
    assert result.status == "completed"
    assert graph is not None
    assert {
        "run.executed_for.ticket",
        "employee.started.run",
        "run.calls.tool",
        "run.produces.artifact",
        "run.produces.evidence",
    }.issubset(edge_types)
    assert graph.source_counts["runs"] == 1
    assert graph.source_counts["artifacts"] == 1
    assert graph.source_counts["tool_events"] >= 2


def test_execution_usage_and_blockers_feed_employee_quality_analytics(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Runtime quality analytics",
            description="Runtime usage, latency, cost, and blockers should feed Employee analytics.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-quality-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    service = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos")
    completed_request = ExecutionRequest(
        request_id="run-quality-completed",
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="append_report", arguments={"content": "runtime quality report"}),
        trace_context={
            "run_id": "run-quality-completed",
            "thread_id": "thread-quality",
            "trace_ref": ".aiteamos/traces/run-quality-completed.jsonl",
        },
    )
    completed_result = ExecutionResult(
        request_id="run-quality-completed",
        executor_id="langgraph",
        status="completed",
        report="Runtime completed with usage accounting.",
        output_ticket_id=ticket.id,
        trace_ref=".aiteamos/traces/run-quality-completed.jsonl",
        usage={"total_tokens": 42, "cost_usd": 0.12},
        started_at="2026-06-08T00:00:00+00:00",
        finished_at="2026-06-08T00:00:02+00:00",
    )
    blocked_request = completed_request.model_copy(
        update={
            "request_id": "run-quality-blocked",
            "trace_context": {
                "run_id": "run-quality-blocked",
                "thread_id": "thread-quality",
                "trace_ref": ".aiteamos/traces/run-quality-blocked.jsonl",
            },
        }
    )
    blocked_result = ExecutionResult(
        request_id="run-quality-blocked",
        executor_id="claude_code",
        status="blocked",
        report="Repo mutation requires approval and evidence.",
        output_ticket_id=ticket.id,
        trace_ref=".aiteamos/traces/run-quality-blocked.jsonl",
        errors=[{"reason": "approval_required", "detail": "repo:write requires approval"}],
        usage={"total_tokens": 12, "cost_usd": 0.03},
        started_at="2026-06-08T00:00:03+00:00",
        finished_at="2026-06-08T00:00:03.500000+00:00",
    )

    service.ingest(completed_request, completed_result)
    service.ingest(blocked_request, blocked_result)

    analytics = employee_analytics("alex")
    assert analytics is not None
    assert analytics.execution_run_count == 2
    assert analytics.blocker_count == 1
    assert analytics.total_cost == 0.15
    assert analytics.average_latency_ms == 1250
    assert analytics.source_counts["execution_runs"] == 2


def test_employee_work_ledger_v2_projects_assets_reviews_and_runtime_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    employees_dir = tmp_path / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True, exist_ok=True)
    (employees_dir / "alex.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "alex",
                "display_name": "Alex",
                "kind": "ai",
                "role": "AI RD / Implementer",
                "skills": ["backend-api-implementation"],
                "skill_refs": ["backend-api-implementation"],
                "capability_tags": ["backend-api-implementation"],
                "personality_tags": ["direct"],
                "memory_scopes": ["aiteamos", "employee:alex"],
                "permissions": ["manage_tickets"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Employee work ledger v2",
            description="Employee ledger should include proposed Assets, approved Assets, reviews, and runtime records.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-ledger-v2-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    candidate = upsert_asset_candidate(
        AssetCandidateRecord(
            id="asset-candidate-ledger-v2",
            source_candidate_id="memory-candidate-ledger-v2",
            asset_id="asset-ledger-v2",
            asset_type="solution",
            title="Ledger v2 asset projection",
            content="Employee Work Ledger v2 should show asset review provenance.",
            content_ref="memory_candidate://memory-candidate-ledger-v2",
            status="proposed",
            scope_kind="ticket",
            scope_ref=ticket.id,
            owner_employee_id="alex",
            source_kind="external_runtime_solution_candidate",
            source_ref="external-runtime:langgraph:run-ledger-v2",
            provenance={
                "source_ticket_id": ticket.id,
                "source_employee_id": "alex",
                "source_run_id": "run-ledger-v2",
                "source_report_id": "report-ledger-v2",
            },
            relationships=[{"type": "derived_from_ticket", "target_kind": "ticket", "target_ref": ticket.id}],
            created_at="2026-06-18T08:00:00+00:00",
            updated_at="2026-06-18T08:00:00+00:00",
        ),
        workspace_dir=tmp_path,
    )
    client = TestClient(create_app())
    reviewed = client.post(
        f"/api/v1/assets/candidates/{candidate.id}/review",
        json={
            "status": "approved",
            "reviewer_employee_id": "clara",
            "reason": "Asset is reusable and traceable.",
        },
    )
    assert reviewed.status_code == 200

    service = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos")
    request = ExecutionRequest(
        request_id="run-ledger-v2",
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="implement_ticket", arguments={"ticket_id": ticket.id}),
        trace_context={
            "run_id": "run-ledger-v2",
            "thread_id": "thread-ledger-v2",
            "trace_ref": ".aiteamos/traces/run-ledger-v2.jsonl",
        },
    )
    result = ExecutionResult(
        request_id="run-ledger-v2",
        executor_id="langgraph",
        status="blocked",
        report="Runtime blocked while proving ledger v2 quality feedback.",
        output_ticket_id=ticket.id,
        artifacts=[{"kind": "runtime_observation", "ref": "artifact://ledger-v2"}],
        evidence=[{"kind": "test_evidence", "ref": "pytest::ledger-v2::passed"}],
        tool_events=[{"event": "terminal.run.blocked", "data": {"command": {"id": "terminal.run:run"}}}],
        trace_ref=".aiteamos/traces/run-ledger-v2.jsonl",
        usage={"latency_ms": 1500, "cost_usd": 0.05},
        started_at="2026-06-18T08:01:00+00:00",
        finished_at="2026-06-18T08:01:02+00:00",
    )
    service.ingest(request, result)

    ledger = employee_work_ledger("alex")

    assert ledger.asset_candidates[0].candidate_id == candidate.id
    assert ledger.asset_candidates[0].source_ticket_id == ticket.id
    assert ledger.approved_assets[0].asset_id == "asset-ledger-v2"
    assert ledger.asset_reviews[0].status == "approved"
    assert ledger.asset_reviews[0].relation_to_employee == "asset_owner"
    assert ledger.runtime_runs[0].request_id == "run-ledger-v2"
    assert ledger.runtime_runs[0].session_key == f"alex::thread-ledger-v2::{ticket.id}"
    assert ledger.runtime_runs[0].status == "blocked"
    assert ledger.runtime_runs[0].tool_event_count == 1
    assert ledger.runtime_runs[0].latency_ms == 1500
    assert ledger.contribution["asset_candidate_count"] == 1
    assert ledger.contribution["approved_asset_count"] == 1
    assert ledger.contribution["asset_review_count"] == 1
    assert ledger.contribution["runtime_run_count"] == 1
    assert ledger.contribution["quality_feedback_count"] == 2
    assert {item.kind for item in ledger.quality_feedback} == {"asset_review", "runtime_result"}

    runtime_feedback = next(item for item in ledger.quality_feedback if item.kind == "runtime_result")
    improvement = client.post(
        f"/api/v1/employees/alex/quality-feedback/{runtime_feedback.id}/improvement-candidate",
        json={
            "actor_employee_id": "clara",
            "reason": "Alex should turn the blocked runtime pattern into reusable follow-up guidance.",
            "proposed_skill_refs": ["runtime-blocker-triage"],
            "proposed_memory_scopes": ["employee:alex:runtime-blockers"],
            "proposed_capability_tags": ["runtime-debugging"],
            "proposed_personality_tags": ["evidence-driven"],
        },
    )
    assert improvement.status_code == 200
    payload = improvement.json()
    candidate_payload = payload["candidate"]
    assert payload["employee_id"] == "alex"
    assert payload["feedback"]["id"] == runtime_feedback.id
    assert candidate_payload["asset_type"] == "employee_improvement"
    assert candidate_payload["scope_kind"] == "employee"
    assert candidate_payload["scope_ref"] == "alex"
    assert candidate_payload["owner_employee_id"] == "alex"
    assert candidate_payload["source_kind"] == "employee_quality_feedback"
    assert candidate_payload["provenance"]["source_feedback_id"] == runtime_feedback.id
    assert candidate_payload["provenance"]["source_ticket_id"] == ticket.id
    assert candidate_payload["provenance"]["proposed_by_employee_id"] == "clara"
    assert candidate_payload["provenance"]["proposed_profile_updates"]["skill_refs"] == ["runtime-blocker-triage"]
    assert candidate_payload["provenance"]["proposed_profile_updates"]["memory_scopes"] == ["employee:alex:runtime-blockers"]
    assert candidate_payload["relationships"][0]["target_ref"] == "alex"
    assert candidate_payload["relationships"][1]["target_ref"] == ticket.id
    assert payload["saved_paths"]["asset_candidates"].endswith("assets/candidates.json")
    improvement_candidates = list_asset_candidates(asset_type="employee_improvement", workspace_dir=tmp_path)
    assert len(improvement_candidates) == 1
    assert improvement_candidates[0].id == candidate_payload["id"]

    repeated = client.post(
        f"/api/v1/employees/alex/quality-feedback/{runtime_feedback.id}/improvement-candidate",
        json={"actor_employee_id": "clara", "reason": "Do not duplicate this improvement candidate."},
    )
    assert repeated.status_code == 200
    assert len(list_asset_candidates(asset_type="employee_improvement", workspace_dir=tmp_path)) == 1

    approved_improvement = client.post(
        f"/api/v1/assets/candidates/{candidate_payload['id']}/review",
        json={
            "status": "approved",
            "reviewer_employee_id": "clara",
            "reason": "Approved as governed Employee improvement before profile application.",
        },
    )
    assert approved_improvement.status_code == 200
    improvement_asset_id = approved_improvement.json()["asset"]["id"]

    applied = client.post(
        f"/api/v1/employees/alex/improvement-assets/{improvement_asset_id}/apply",
        json={
            "actor_employee_id": "clara",
            "reason": "Apply approved runtime blocker triage improvement to Alex.",
            "application_note": "Keep this as an explicit profile update, not an agent self-modification.",
        },
    )
    assert applied.status_code == 200
    applied_payload = applied.json()
    assert applied_payload["status"] == "applied"
    assert applied_payload["employee_id"] == "alex"
    assert applied_payload["asset_id"] == improvement_asset_id
    assert applied_payload["applied_changes"]["skill_refs"] == ["runtime-blocker-triage"]
    assert applied_payload["applied_changes"]["memory_scopes"] == ["employee:alex:runtime-blockers"]
    assert applied_payload["applied_changes"]["capability_tags"] == ["runtime-debugging"]
    assert applied_payload["applied_changes"]["personality_tags"] == ["evidence-driven"]
    assert applied_payload["ticket_report_id"]
    assert applied_payload["saved_paths"]["employee_profile"].endswith(".aiteamos/employees/alex.yaml")

    updated_profile = yaml.safe_load((employees_dir / "alex.yaml").read_text(encoding="utf-8"))
    assert "runtime-blocker-triage" in updated_profile["skill_refs"]
    assert "employee:alex:runtime-blockers" in updated_profile["memory_scopes"]
    assert "runtime-debugging" in updated_profile["capability_tags"]
    assert "evidence-driven" in updated_profile["personality_tags"]
    assert f"asset:{improvement_asset_id}" in updated_profile["work_history_refs"]
    assert updated_profile["applied_improvement_refs"][0]["asset_id"] == improvement_asset_id

    updated_ticket = get_ticket(ticket.id)
    assert updated_ticket is not None
    assert any(report.report_type == "employee_improvement_applied" for report in updated_ticket.reports)
    updated_asset = next(item for item in list_asset_records(asset_type="employee_improvement", workspace_dir=tmp_path) if item.id == improvement_asset_id)
    application = updated_asset.provenance["employee_improvement_application"]
    assert application["status"] == "applied"
    assert application["employee_id"] == "alex"
    assert application["ticket_report_id"] == applied_payload["ticket_report_id"]
    assert any(rel["type"] == "applied_to_employee" and rel["target_ref"] == "alex" for rel in updated_asset.relationships)
    applied_ledger = employee_work_ledger("alex")
    applied_ledger_asset = next(item for item in applied_ledger.approved_assets if item.asset_id == improvement_asset_id)
    assert applied_ledger_asset.application_status == "applied"
    assert applied_ledger_asset.application_employee_id == "alex"
    assert applied_ledger_asset.application_report_id == applied_payload["ticket_report_id"]

    repeated_apply = client.post(
        f"/api/v1/employees/alex/improvement-assets/{improvement_asset_id}/apply",
        json={"actor_employee_id": "clara", "reason": "Do not duplicate profile updates."},
    )
    assert repeated_apply.status_code == 200
    assert repeated_apply.json()["status"] == "already_applied"

    growth_eval = client.get("/api/v1/employees/alex/growth-eval")
    assert growth_eval.status_code == 200
    growth_payload = growth_eval.json()
    growth_summary = growth_payload["summary"]
    assert growth_payload["status"] == "passed"
    assert growth_summary["employee_id"] == "alex"
    assert growth_summary["quality_feedback_count"] >= 2
    assert growth_summary["improvement_candidate_count"] == 1
    assert growth_summary["applied_improvement_count"] == 1
    assert growth_summary["improvement_loop_proof_status"] == "passed"
    assert growth_summary["improvement_loop_application_status"] in {"applied", "already_applied"}
    assert growth_summary["improvement_loop_ticket_report_id"]
    assert growth_summary["improvement_loop_workspace"] == "temporary"


async def test_execution_result_memory_candidates_enter_review_queue_and_graphiti_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    _use_local_ticket_backend()

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-execution-candidate-1"

    class FakeAddResult:
        episode = FakeEpisode()

    class FakeGraphiti:
        last_episode: dict = {}

        def __init__(self, *args, **kwargs):
            pass

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            FakeGraphiti.last_episode = kwargs
            return FakeAddResult()

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)
    update_graphiti_settings(
        GraphitiSettingsUpdateRequest(
            enabled=True,
            graph_database="neo4j",
            uri="bolt://localhost:7687",
            user="neo4j",
            group_id="aiteamos-test",
            llm_ai_engine="openai",
        )
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Execution candidate approval",
            description="Runtime should propose governed candidates.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="run-candidate",
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="append_report", arguments={"content": "runtime candidate report"}),
        trace_context={
            "run_id": "run-candidate",
            "thread_id": "thread-candidate",
            "trace_ref": ".aiteamos/traces/run-candidate.jsonl",
        },
    )
    result = ExecutionResult(
        request_id="run-candidate",
        executor_id="langgraph",
        status="completed",
        report="Runtime completed and proposed a reusable lesson.",
        output_ticket_id=ticket.id,
        trace_ref=".aiteamos/traces/run-candidate.jsonl",
        executor_session_ref="lg-run-candidate",
        checkpoint_ref="langgraph:run-candidate",
        memory_candidates=[
            {
                "content": "When runtime execution proposes a lesson, store it as a Ticket-aware review candidate before Graphiti ingestion.",
                "memory_type": "principle",
                "confidence": 0.87,
                "tags": ["runtime-first", "review-queue"],
                "future_recall_query_hints": ["runtime candidate", "review queue", ticket.id],
            }
        ],
        started_at="2026-06-08T00:00:00+00:00",
        finished_at="2026-06-08T00:00:01+00:00",
    )

    ingested = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos").ingest(request, result)
    candidates = list_memory_candidates(status="proposed")
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.scope_kind == "ticket"
    assert candidate.scope_ref == ticket.id
    assert candidate.provenance["source_ticket_id"] == ticket.id
    assert candidate.provenance["source_run_id"] == "run-candidate"
    assert candidate.provenance["source_trace_path"] == ".aiteamos/traces/run-candidate.jsonl"
    assert candidate.provenance["action"] == "append_report"
    assert ingested.memory_candidates[-1]["id"] == candidate.id

    approved = await approve_memory_candidate(candidate.id)
    assert approved.status == "approved"
    assert approved.graphiti_episode_id == "episode-execution-candidate-1"
    assert approved.graphiti_status["provenance"]["source_ticket_id"] == ticket.id
    assert approved.graphiti_status["provenance"]["source_run_id"] == "run-candidate"
    assert '"asset_id"' in FakeGraphiti.last_episode["episode_body"]

    graph = ticket_graph_projection(ticket.id)
    edge_types = {edge.type for edge in graph.edges} if graph else set()
    assert graph is not None
    assert "run.proposes_memory_candidate" in edge_types
    assert any(
        node.kind == "asset"
        and node.metadata.get("memory_id") == candidate.id
        and node.status == "approved"
        for node in graph.nodes
    )


def test_external_runtime_durable_asset_candidates_enter_review_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="External runtime durable candidates",
            description="External runtime decisions/docs/skills must enter AITeamOS Review Queue.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-durable-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="run-durable-candidates",
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="append_report", arguments={"content": "external runtime produced candidates"}),
        trace_context={
            "run_id": "run-durable-candidates",
            "thread_id": "thread-durable-candidates",
            "trace_ref": ".aiteamos/traces/run-durable-candidates.jsonl",
        },
    )
    result = ExecutionResult(
        request_id="run-durable-candidates",
        executor_id="claude_code",
        status="completed",
        report="Claude Code-compatible runtime proposed durable learnings.",
        output_ticket_id=ticket.id,
        trace_ref=".aiteamos/traces/run-durable-candidates.jsonl",
        executor_session_ref="claude-code-run-durable-candidates",
        checkpoint_ref="claude_code:run-durable-candidates",
        artifacts=[
            {
                "kind": "decision_candidate",
                "title": "Keep external runtimes behind RuntimeExecutor",
                "content": "AITeamOS should consume external agent output as ExecutionResult instead of route-level provider helpers.",
                "confidence": 0.91,
                "relationships": [{"type": "derived_from", "target": ticket.id}],
                "tags": ["runtime-first"],
            }
        ],
        learning_delta={
            "doc_candidates": [
                {
                    "title": "Runtime adapter setup blocker note",
                    "content": "If Cursor/OpenHands/Claude Code-compatible runtime is not configured, return a setup blocker instead of fake completion.",
                    "scope_kind": "project",
                    "scope_ref": "aiteamos",
                }
            ],
            "skill_candidates": [
                {
                    "title": "Normalize external runtime outputs",
                    "content": "When an external runtime returns reusable implementation knowledge, preserve Ticket provenance before proposing it for approval.",
                    "future_recall_query_hints": ["external runtime candidates", ticket.id],
                }
            ],
        },
        started_at="2026-06-08T00:00:00+00:00",
        finished_at="2026-06-08T00:00:01+00:00",
    )

    ingested = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos").ingest(request, result)
    candidates = list_memory_candidates(status="proposed")
    by_type = {candidate.memory_type: candidate for candidate in candidates}
    asset_candidates = list_asset_candidates(status="proposed")
    asset_by_type = {candidate.asset_type: candidate for candidate in asset_candidates}

    assert len(candidates) == 3
    assert {"decision", "doc", "skill"} == set(by_type)
    assert len(asset_candidates) == 3
    assert {"decision", "doc", "skill"} == set(asset_by_type)
    assert asset_by_type["decision"].source_candidate_id == by_type["decision"].id
    assert asset_by_type["decision"].source_kind == "external_runtime_decision_candidate"
    assert asset_by_type["decision"].scope_ref == ticket.id
    assert asset_by_type["decision"].relationships[0]["type"] == "derived_from"
    assert asset_by_type["skill"].owner_employee_id == "alex"
    assert asset_by_type["skill"].provenance["source_ticket_id"] == ticket.id
    assert by_type["decision"].scope_ref == ticket.id
    assert by_type["doc"].scope_kind == "project"
    assert by_type["doc"].scope_ref == "aiteamos"
    assert by_type["skill"].provenance["source_ticket_id"] == ticket.id
    assert by_type["skill"].provenance["source_employee_id"] == "alex"
    assert by_type["skill"].provenance["source_run_id"] == "run-durable-candidates"
    assert by_type["skill"].provenance["external_runtime"] is True
    assert by_type["skill"].provenance["executor_id"] == "claude_code"
    assert by_type["decision"].provenance["relationships"][0]["type"] == "derived_from"
    assert any(event.get("data", {}).get("command", {}).get("id") == "memory.candidates:propose" for event in ingested.tool_events)
    assert any(event.get("data", {}).get("command", {}).get("id") == "asset.candidates:propose" for event in ingested.tool_events)
    assert len([item for item in ingested.memory_candidates if item.get("id")]) == 3
    assert len(ingested.learning_delta["asset_candidates"]) == 3

    client = TestClient(create_app())
    response = client.get("/api/v1/assets/candidates?status=proposed&asset_type=skill")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["asset_type"] == "skill"
    assert payload[0]["source_candidate_id"] == by_type["skill"].id

    approved = client.post(
        f"/api/v1/assets/candidates/{asset_by_type['skill'].id}/review",
        json={
            "status": "approved",
            "reviewer_employee_id": "clara",
            "reason": "Skill candidate has Ticket provenance and can be reused.",
        },
    )
    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["candidate"]["status"] == "approved"
    assert approved_payload["candidate"]["review_state"] == "approved"
    assert approved_payload["review"]["candidate_id"] == asset_by_type["skill"].id
    assert approved_payload["review"]["status"] == "approved"
    assert approved_payload["asset"]["asset_type"] == "skill"
    assert approved_payload["asset"]["status"] == "approved"
    assert approved_payload["asset"]["provenance"]["source_asset_candidate_id"] == asset_by_type["skill"].id
    assert approved_payload["saved_paths"]["asset_records"].endswith("assets/index.json")
    assert approved_payload["saved_paths"]["asset_reviews"].endswith("assets/reviews.json")

    records = list_asset_records(asset_type="skill", workspace_dir=tmp_path)
    reviews = list_asset_reviews(candidate_id=asset_by_type["skill"].id, workspace_dir=tmp_path)
    assert len(records) == 1
    assert records[0].id == approved_payload["asset"]["id"]
    assert records[0].title == "Normalize external runtime outputs"
    assert records[0].scope_ref == ticket.id
    assert len(reviews) == 1
    assert reviews[0].reviewer_employee_id == "clara"

    record_response = client.get("/api/v1/assets/records?asset_type=skill&q=Normalize")
    assert record_response.status_code == 200
    assert record_response.json()[0]["id"] == records[0].id
    review_response = client.get(f"/api/v1/assets/reviews?candidate_id={asset_by_type['skill'].id}")
    assert review_response.status_code == 200
    assert review_response.json()[0]["id"] == reviews[0].id
    search_response = client.get("/api/v1/assets/search?q=Normalize%20external%20runtime%20outputs")
    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert any(item["id"] == f"asset-registry:{records[0].id}" for item in search_payload)
    assert any(item["id"] == f"asset-candidate:{asset_by_type['skill'].id}" for item in search_payload)

    rejected = client.post(
        f"/api/v1/assets/candidates/{asset_by_type['doc'].id}/review",
        json={"status": "rejected", "reviewer_employee_id": "clara", "reason": "Doc candidate is not durable enough yet."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["candidate"]["status"] == "rejected"
    assert rejected.json()["asset"] is None


def test_asset_candidate_batch_review_uses_governed_single_review_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Batch approve durable learning candidates",
            description="Review Queue batch actions must still create review records and governed AssetRecords.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-batch-review-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    candidates = [
        upsert_asset_candidate(
            AssetCandidateRecord(
                id=f"asset-candidate-batch-{asset_type}",
                source_candidate_id=f"memory-candidate-batch-{asset_type}",
                asset_id=f"asset-batch-{asset_type}",
                asset_type=asset_type,
                title=f"Batch reviewed {asset_type}",
                content=f"Durable {asset_type} candidate should keep Ticket provenance after batch review.",
                status="proposed",
                scope_kind="ticket",
                scope_ref=ticket.id,
                owner_employee_id="alex",
                source_kind=f"batch_{asset_type}_candidate",
                source_ref="runtime:batch-review",
                provenance={
                    "source_ticket_id": ticket.id,
                    "source_employee_id": "alex",
                    "source_run_id": "run-batch-review",
                },
                relationships=[{"type": "derived_from_ticket", "target_kind": "ticket", "target_ref": ticket.id}],
                created_at="2026-06-08T00:00:00+00:00",
                updated_at="2026-06-08T00:00:00+00:00",
            ),
            workspace_dir=tmp_path,
        )
        for asset_type in ("solution", "validation_result")
    ]

    response = TestClient(create_app()).post(
        "/api/v1/assets/candidates/review-batch",
        json={
            "candidate_ids": [candidates[0].id, candidates[1].id, candidates[0].id],
            "status": "approved",
            "reviewer_employee_id": "clara",
            "reason": "Batch approve validated closeout candidates.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["requested_count"] == 2
    assert payload["reviewed_count"] == 2
    assert payload["failed_count"] == 0
    assert [item["candidate_id"] for item in payload["results"]] == [candidates[0].id, candidates[1].id]
    assert {item["response"]["candidate"]["status"] for item in payload["results"]} == {"approved"}
    assert payload["saved_paths"]["asset_candidates"].endswith("assets/candidates.json")
    assert payload["saved_paths"]["asset_records"].endswith("assets/index.json")
    assert payload["saved_paths"]["asset_reviews"].endswith("assets/reviews.json")

    records = list_asset_records(workspace_dir=tmp_path)
    reviews = list_asset_reviews(workspace_dir=tmp_path)
    assert {record.asset_type for record in records} == {"solution", "validation_result"}
    assert {record.provenance["source_asset_candidate_id"] for record in records} == {candidate.id for candidate in candidates}
    assert len(reviews) == 2
    assert {review.status for review in reviews} == {"approved"}
    assert all(review.reason == "Batch approve validated closeout candidates." for review in reviews)


def test_asset_retrieval_evaluation_records_expected_asset_recall(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Evaluate durable solution retrieval",
            description="Retrieval evaluation should record whether an expected Asset is recalled.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-retrieval-eval-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    candidate = upsert_asset_candidate(
        AssetCandidateRecord(
            id="asset-candidate-retrieval-eval-solution",
            source_candidate_id="memory-candidate-retrieval-eval-solution",
            asset_id="asset-retrieval-eval-solution",
            asset_type="solution",
            title="Retry Graphiti auth rate-limit remediation",
            content="When Neo4j returns AuthenticationRateLimit, wait for rate-limit reset and verify Graphiti credentials before rerunning external smoke.",
            status="proposed",
            scope_kind="ticket",
            scope_ref=ticket.id,
            owner_employee_id="alex",
            source_kind="ticket_closeout_solution",
            source_ref="ticket-closeout-candidates:retrieval-eval",
            provenance={
                "source_ticket_id": ticket.id,
                "source_employee_id": "alex",
                "source_run_id": "run-retrieval-eval",
            },
            relationships=[{"type": "derived_from_ticket", "target_kind": "ticket", "target_ref": ticket.id}],
            created_at="2026-06-08T00:00:00+00:00",
            updated_at="2026-06-08T00:00:00+00:00",
        ),
        workspace_dir=tmp_path,
    )

    client = TestClient(create_app())
    approved = client.post(
        f"/api/v1/assets/candidates/{candidate.id}/review",
        json={"status": "approved", "reviewer_employee_id": "clara", "reason": "Approved expected retrieval solution."},
    )
    assert approved.status_code == 200
    asset_id = approved.json()["asset"]["id"]

    evaluated = client.post(
        "/api/v1/assets/retrieval-evaluations",
        json={
            "query": "Graphiti AuthenticationRateLimit external smoke credentials",
            "expected_asset_ids": [asset_id],
            "top_k": 5,
            "source_ticket_id": ticket.id,
            "source_run_id": "run-retrieval-eval",
            "evaluator_employee_id": "clara",
            "usefulness_status": "used",
        },
    )

    assert evaluated.status_code == 200
    payload = evaluated.json()
    assert payload["record"]["query"] == "Graphiti AuthenticationRateLimit external smoke credentials"
    assert payload["record"]["expected_asset_ids"] == [asset_id]
    assert payload["record"]["matched_asset_ids"] == [asset_id]
    assert payload["record"]["missing_asset_ids"] == []
    assert payload["record"]["recall"] == 1.0
    assert payload["record"]["precision"] > 0
    assert payload["record"]["source_ticket_id"] == ticket.id
    assert payload["record"]["usefulness_status"] == "used"
    assert any(item["id"] == f"asset-registry:{asset_id}" for item in payload["retrieved_assets"])
    assert payload["saved_paths"]["retrieval_evaluations"].endswith("assets/retrieval_evaluations.json")

    history = client.get("/api/v1/assets/retrieval-evaluations")
    assert history.status_code == 200
    assert history.json()[0]["id"] == payload["record"]["id"]


def test_asset_search_downranks_irrelevant_or_harmful_recall_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Rank durable assets by recall feedback",
            description="Local Asset search should downrank irrelevant or harmful recall feedback.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-ranking-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    for asset_id, title, usefulness_stats, updated_at in (
        (
            "asset-candidate-ranking-neutral",
            "Graphiti credential remediation neutral",
            {},
            "2026-06-08T00:00:00+00:00",
        ),
        (
            "asset-candidate-ranking-harmful",
            "Graphiti credential remediation harmful",
            {"irrelevant_count": 1, "harmful_count": 1},
            "2026-06-09T00:00:00+00:00",
        ),
    ):
        upsert_asset_candidate(
            AssetCandidateRecord(
                id=asset_id,
                source_candidate_id=f"memory-{asset_id}",
                asset_id=asset_id.replace("asset-candidate", "asset"),
                asset_type="solution",
                title=title,
                content="Graphiti credential remediation for external smoke ranking evaluation.",
                status="proposed",
                scope_kind="ticket",
                scope_ref=ticket.id,
                owner_employee_id="alex",
                source_kind="ranking_feedback_candidate",
                source_ref="runtime:ranking-feedback",
                provenance={"source_ticket_id": ticket.id, "source_employee_id": "alex", "source_run_id": "run-ranking"},
                relationships=[{"type": "derived_from_ticket", "target_kind": "ticket", "target_ref": ticket.id}],
                usefulness_stats=usefulness_stats,
                created_at=updated_at,
                updated_at=updated_at,
            ),
            workspace_dir=tmp_path,
        )

    client = TestClient(create_app())
    batch = client.post(
        "/api/v1/assets/candidates/review-batch",
        json={
            "candidate_ids": ["asset-candidate-ranking-neutral", "asset-candidate-ranking-harmful"],
            "status": "approved",
            "reviewer_employee_id": "clara",
            "reason": "Approve ranking comparison fixtures.",
        },
    )
    assert batch.status_code == 200

    search = client.get("/api/v1/assets/search?q=Graphiti%20credential%20remediation")
    assert search.status_code == 200
    registry_results = [item for item in search.json() if item["id"].startswith("asset-registry:")]
    assert len(registry_results) >= 2
    assert registry_results[0]["id"] == "asset-registry:asset-ranking-neutral"
    assert registry_results[-1]["id"] == "asset-registry:asset-ranking-harmful"
    assert registry_results[-1]["metadata"]["usefulness_stats"]["harmful_count"] == 1


def test_execution_tool_events_enter_asset_candidate_review_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Tool call Asset candidate",
            description="Tool calls should become governed Asset candidates.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-tool-call-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    request = ExecutionRequest(
        request_id="run-tool-call-candidate",
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="terminal_run", arguments={"command": "pwd"}),
        trace_context={
            "run_id": "run-tool-call-candidate",
            "thread_id": "thread-tool-call-candidate",
            "trace_ref": ".aiteamos/traces/run-tool-call-candidate.jsonl",
        },
    )
    result = ExecutionResult(
        request_id="run-tool-call-candidate",
        executor_id="local_tool",
        status="completed",
        report="terminal.run completed.",
        output_ticket_id=ticket.id,
        trace_ref=".aiteamos/traces/run-tool-call-candidate.jsonl",
        tool_events=[
            {
                "event": "command.completed",
                "detail": "terminal.run completed.",
                "data": {
                    "command": {"id": "terminal.run:run", "capability": "terminal.run", "operation": "run"},
                    "status": "completed",
                    "record_as_asset": True,
                    "stdout": "/home/shiqiangli/projects/AITeamOS",
                    "secret_token": "must-not-enter-assets",
                },
            }
        ],
        started_at="2026-06-08T00:00:00+00:00",
        finished_at="2026-06-08T00:00:01+00:00",
    )

    ingested = ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos").ingest(request, result)
    candidates = list_memory_candidates(status="proposed")
    asset_candidates = list_asset_candidates(asset_type="tool_call", status="proposed")

    assert len(candidates) == 1
    assert len(asset_candidates) == 1
    tool_asset = asset_candidates[0]
    assert tool_asset.asset_type == "tool_call"
    assert tool_asset.scope_ref == ticket.id
    assert tool_asset.owner_employee_id == "alex"
    assert tool_asset.source_kind == "execution_tool_event"
    assert "terminal.run:run" in tool_asset.content
    assert "must-not-enter-assets" not in tool_asset.content
    assert "[redacted]" in tool_asset.content
    assert tool_asset.provenance["command_id"] == "terminal.run:run"
    assert tool_asset.provenance["tool_event_index"] == 0
    assert tool_asset.provenance["source_ticket_id"] == ticket.id
    assert tool_asset.relationships[0]["type"] == "derived_from_ticket"
    assert any(event.get("data", {}).get("command", {}).get("id") == "asset.candidates:propose" for event in ingested.tool_events)

    client = TestClient(create_app())
    approved = client.post(
        f"/api/v1/assets/candidates/{tool_asset.id}/review",
        json={
            "status": "approved",
            "reviewer_employee_id": "clara",
            "reason": "Tool call has bounded Ticket evidence and redacted payload.",
        },
    )
    assert approved.status_code == 200
    approved_payload = approved.json()
    assert approved_payload["asset"]["asset_type"] == "tool_call"
    assert approved_payload["asset"]["status"] == "approved"
    search = client.get("/api/v1/assets/search?q=terminal.run%3Arun")
    assert search.status_code == 200
    assert any(item["id"] == f"asset-registry:{approved_payload['asset']['id']}" for item in search.json())


def test_approved_asset_record_projects_to_graphiti_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Approved AssetRecord Graphiti projection",
            description="Approved AssetRecords should project through the Graphiti provider boundary.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-asset-projection-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    candidate = upsert_asset_candidate(
        AssetCandidateRecord(
            id="asset-candidate-graphiti-projection",
            source_candidate_id="memory-candidate-graphiti-projection",
            asset_id="asset-graphiti-projection",
            asset_type="skill",
            title="Project approved AssetRecords through Graphiti",
            content="Approved AssetRecords should be projected to Graphiti with Ticket, Employee, and review provenance.",
            content_ref="memory_candidate://memory-candidate-graphiti-projection",
            status="proposed",
            scope_kind="ticket",
            scope_ref=ticket.id,
            owner_employee_id="alex",
            source_kind="external_runtime_skill_candidate",
            source_ref="external-runtime:claude_code:run-asset-projection",
            provenance={
                "source_ticket_id": ticket.id,
                "source_employee_id": "alex",
                "source_run_id": "run-asset-projection",
                "source_report_id": "report-asset-projection",
                "evidence_id": "evidence-asset-projection",
                "source_memory_candidate_id": "memory-candidate-graphiti-projection",
            },
            relationships=[{"type": "derived_from_ticket", "target_kind": "ticket", "target_ref": ticket.id}],
            created_at="2026-06-08T00:00:00+00:00",
            updated_at="2026-06-08T00:00:00+00:00",
        ),
        workspace_dir=tmp_path,
    )

    client = TestClient(create_app())
    approved = client.post(
        f"/api/v1/assets/candidates/{candidate.id}/review",
        json={
            "status": "approved",
            "reviewer_employee_id": "clara",
            "reason": "AssetRecord has durable skill content and provenance.",
        },
    )
    assert approved.status_code == 200
    asset_id = approved.json()["asset"]["id"]

    blocked = client.post(f"/api/v1/assets/records/{asset_id}/project/graphiti")
    assert blocked.status_code == 400
    assert "Graphiti Memory / Asset Graph setup blocker" in blocked.json()["detail"]
    assert list_asset_records(asset_type="skill", workspace_dir=tmp_path)[0].provenance.get("graphiti_status") is None

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-approved-asset-record-1"

    class FakeAddResult:
        episode = FakeEpisode()

    class FakeGraphiti:
        indexed_episodes: list[dict] = []

        def __init__(self, *args, **kwargs):
            pass

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            FakeGraphiti.indexed_episodes.append(kwargs)
            return FakeAddResult()

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)
    update_graphiti_settings(
        GraphitiSettingsUpdateRequest(
            enabled=True,
            graph_database="neo4j",
            uri="bolt://localhost:7687",
            user="neo4j",
            group_id="aiteamos-test",
            llm_ai_engine="openai",
        )
    )

    projected = client.post(f"/api/v1/assets/records/{asset_id}/project/graphiti")
    assert projected.status_code == 200
    projected_payload = projected.json()
    assert projected_payload["asset_id"] == asset_id
    assert projected_payload["status"] == "ingested"
    assert projected_payload["ingested_asset"]["episode_id"] == "episode-approved-asset-record-1"
    assert projected_payload["saved_paths"]["asset_records"].endswith("assets/index.json")
    assert projected_payload["saved_paths"]["graphiti_state"].endswith("memory/graphiti_state.json")
    assert len(FakeGraphiti.indexed_episodes) == 1
    episode_body = FakeGraphiti.indexed_episodes[0]["episode_body"]
    provenance = json.loads(episode_body.split("AITeamOS provenance:\n", maxsplit=1)[1])
    assert provenance["asset_id"] == asset_id
    assert provenance["source_ticket_id"] == ticket.id
    assert provenance["source_employee_id"] == "alex"
    assert provenance["source_run_id"] == "run-asset-projection"
    assert provenance["metadata"]["asset_registry_id"] == asset_id
    assert provenance["metadata"]["source_asset_candidate_id"] == candidate.id

    records = list_asset_records(asset_type="skill", workspace_dir=tmp_path)
    assert records[0].provenance["graphiti_status"]["episode_id"] == "episode-approved-asset-record-1"
    assert records[0].provenance["graphiti_status"]["provenance"]["source_ticket_id"] == ticket.id
    assert any(item["provider"] == "graphiti" for item in records[0].provenance["provider_refs"])

    projected_again = client.post(f"/api/v1/assets/records/{asset_id}/project/graphiti")
    assert projected_again.status_code == 200
    assert projected_again.json()["status"] == "skipped"
    assert projected_again.json()["skipped_asset"]["episode_id"] == "episode-approved-asset-record-1"
    assert len(FakeGraphiti.indexed_episodes) == 1


def test_approved_closeout_and_solution_assets_project_to_graphiti_with_review_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Project closeout solution Assets",
            description="Approved closeout and solution candidates should project through AssetReviewRecord provenance.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-closeout-graphiti-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    candidates = [
        upsert_asset_candidate(
            AssetCandidateRecord(
                id=f"asset-candidate-closeout-graphiti-{asset_type}",
                source_candidate_id=f"memory-closeout-graphiti-{asset_type}",
                asset_id=f"asset-closeout-graphiti-{asset_type}",
                asset_type=asset_type,
                title=f"Graphiti projection for {asset_type}",
                content=f"Approved {asset_type} closeout learning should project with review provenance.",
                status="proposed",
                scope_kind="ticket",
                scope_ref=ticket.id,
                owner_employee_id="alex",
                source_kind=f"ticket_closeout_{asset_type}",
                source_ref=f"ticket-closeout-candidates:{ticket.id}",
                provenance={
                    "source_ticket_id": ticket.id,
                    "source_employee_id": "alex",
                    "source_run_id": "run-closeout-graphiti",
                    "source_report_id": "report-closeout-graphiti",
                    "evidence_id": f"evidence-closeout-graphiti-{asset_type}",
                },
                relationships=[{"type": "derived_from_ticket", "target_kind": "ticket", "target_ref": ticket.id}],
                created_at="2026-06-08T00:00:00+00:00",
                updated_at="2026-06-08T00:00:00+00:00",
            ),
            workspace_dir=tmp_path,
        )
        for asset_type in ("ticket_closeout", "solution")
    ]

    client = TestClient(create_app())
    approved = client.post(
        "/api/v1/assets/candidates/review-batch",
        json={
            "candidate_ids": [candidate.id for candidate in candidates],
            "status": "approved",
            "reviewer_employee_id": "clara",
            "reason": "Batch approve closeout and solution candidates for Graphiti projection.",
        },
    )
    assert approved.status_code == 200
    asset_ids = [item["response"]["asset"]["id"] for item in approved.json()["results"]]

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeGraphiti:
        indexed_episodes: list[dict] = []

        def __init__(self, *args, **kwargs):
            pass

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            provenance = json.loads(kwargs["episode_body"].split("AITeamOS provenance:\n", maxsplit=1)[1])
            FakeGraphiti.indexed_episodes.append({"kwargs": kwargs, "provenance": provenance})
            return SimpleNamespace(episode=SimpleNamespace(uuid=f"episode-{provenance['asset_id']}"))

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)
    update_graphiti_settings(
        GraphitiSettingsUpdateRequest(
            enabled=True,
            graph_database="neo4j",
            uri="bolt://localhost:7687",
            user="neo4j",
            group_id="aiteamos-test",
            llm_ai_engine="openai",
        )
    )

    for asset_id in asset_ids:
        projected = client.post(f"/api/v1/assets/records/{asset_id}/project/graphiti")
        assert projected.status_code == 200
        assert projected.json()["status"] == "ingested"
        assert projected.json()["ingested_asset"]["episode_id"] == f"episode-{asset_id}"

    assert {item["provenance"]["asset_type"] for item in FakeGraphiti.indexed_episodes} == {"ticket_closeout", "solution"}
    for item in FakeGraphiti.indexed_episodes:
        provenance = item["provenance"]
        metadata = provenance["metadata"]
        assert provenance["source_ticket_id"] == ticket.id
        assert provenance["source_employee_id"] == "alex"
        assert metadata["source_asset_candidate_id"].startswith("asset-candidate-closeout-graphiti-")
        assert metadata["asset_review_id"].startswith("asset-review-asset-candidate-closeout-graphiti-")
        assert metadata["reviewer_employee_id"] == "clara"
        assert metadata["review_reason"] == "Batch approve closeout and solution candidates for Graphiti projection."

    records = list_asset_records(workspace_dir=tmp_path)
    projected_records = [record for record in records if record.id in set(asset_ids)]
    assert len(projected_records) == 2
    assert all(record.provenance["graphiti_status"]["status"] == "ingested" for record in projected_records)
    assert all(any(ref["provider"] == "graphiti" for ref in record.provenance["provider_refs"]) for record in projected_records)


def test_ticket_closeout_settlement_approves_and_projects_assets_idempotently(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Settle closeout Assets",
            description="Closeout settlement should approve and project governed Assets through existing services.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            validation_employee_id="peter",
            validation_role="AI PV",
            source_run_id="run-closeout-settlement-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content="Implemented closeout settlement behavior.",
            report_type="result",
            evidence=["pytest::closeout-settlement::result"],
            source_run_id="run-closeout-settlement-result",
        ),
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="peter",
            reporter_role="AI PV",
            content="Validation passed for closeout settlement.",
            report_type="validation",
            evidence=["pytest::closeout-settlement::validation"],
            source_run_id="run-closeout-settlement-validation",
        ),
    )

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeGraphiti:
        indexed_episodes: list[dict] = []

        def __init__(self, *args, **kwargs):
            pass

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            provenance = json.loads(kwargs["episode_body"].split("AITeamOS provenance:\n", maxsplit=1)[1])
            FakeGraphiti.indexed_episodes.append({"kwargs": kwargs, "provenance": provenance})
            return SimpleNamespace(episode=SimpleNamespace(uuid=f"episode-{provenance['asset_id']}"))

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)
    update_graphiti_settings(
        GraphitiSettingsUpdateRequest(
            enabled=True,
            graph_database="neo4j",
            uri="bolt://localhost:7687",
            user="neo4j",
            group_id="aiteamos-test",
            llm_ai_engine="openai",
        )
    )

    client = TestClient(create_app())
    settled = client.post(
        f"/api/v1/tickets/{ticket.id}/closeout-settlement",
        json={
            "actor_employee_id": "clara",
            "actor_role": "AI Team OS Manager",
            "reviewer_employee_id": "clara",
            "reason": "Approve and project validated closeout assets.",
            "approve_candidates": True,
            "project_graphiti": True,
        },
    )

    assert settled.status_code == 200
    payload = settled.json()
    assert payload["status"] == "projected"
    assert payload["proposal"]["ticket_id"] == ticket.id
    assert payload["review"]["status"] == "completed"
    assert payload["review"]["reviewed_count"] == 3
    assert {candidate["asset_type"] for candidate in payload["candidates"]} == {"ticket_closeout", "solution", "validation_result"}
    assert len(payload["asset_ids"]) == 3
    assert {projection["status"] for projection in payload["projections"]} == {"ingested"}
    assert payload["saved_paths"]["asset_records"].endswith("assets/index.json")
    assert payload["saved_paths"]["graphiti_state"].endswith("memory/graphiti_state.json")
    assert {item["provenance"]["asset_type"] for item in FakeGraphiti.indexed_episodes} == {
        "ticket_closeout",
        "solution",
        "validation_result",
    }

    records = list_asset_records(workspace_dir=tmp_path)
    reviews = list_asset_reviews(workspace_dir=tmp_path)
    updated = get_ticket(ticket.id)
    assert {record.status for record in records} == {"approved"}
    assert all(record.provenance["graphiti_status"]["status"] == "ingested" for record in records)
    assert len(reviews) == 3
    assert updated is not None
    assert len([report for report in updated.reports if report.report_type == "ticket_closeout_settlement"]) == 1

    repeated = client.post(
        f"/api/v1/tickets/{ticket.id}/closeout-settlement",
        json={
            "actor_employee_id": "clara",
            "actor_role": "AI Team OS Manager",
            "reviewer_employee_id": "clara",
            "reason": "Repeat closeout settlement should be idempotent.",
            "approve_candidates": True,
            "project_graphiti": True,
        },
    )
    repeated_payload = repeated.json()
    repeated_updated = get_ticket(ticket.id)

    assert repeated.status_code == 200
    assert repeated_payload["status"] == "projected"
    assert repeated_payload["review"]["status"] == "skipped"
    assert {candidate["status"] for candidate in repeated_payload["candidates"]} == {"approved"}
    assert {projection["status"] for projection in repeated_payload["projections"]} == {"skipped"}
    assert len(FakeGraphiti.indexed_episodes) == 3
    assert len(list_asset_reviews(workspace_dir=tmp_path)) == 3
    assert repeated_updated is not None
    assert len([report for report in repeated_updated.reports if report.report_type == "ticket_closeout_settlement"]) == 1


def test_asset_record_review_relationship_projects_to_graphiti_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="AssetRecord relationship projection",
            description="Approved AssetRecord relationships should project through the Graphiti provider boundary.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-asset-relationship-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        def __init__(self, uuid: str):
            self.uuid = uuid

    class FakeAddResult:
        def __init__(self, episode_id: str):
            self.episode = FakeEpisode(episode_id)

    class FakeGraphiti:
        indexed_asset_ids: list[str] = []
        indexed_episodes: list[dict] = []

        def __init__(self, *args, **kwargs):
            pass

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            provenance = json.loads(kwargs["episode_body"].split("AITeamOS provenance:\n", maxsplit=1)[1])
            asset_id = provenance["asset_id"]
            FakeGraphiti.indexed_asset_ids.append(asset_id)
            FakeGraphiti.indexed_episodes.append(kwargs)
            return FakeAddResult(f"episode-{asset_id}")

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)
    update_graphiti_settings(
        GraphitiSettingsUpdateRequest(
            enabled=True,
            graph_database="neo4j",
            uri="bolt://localhost:7687",
            user="neo4j",
            group_id="aiteamos-test",
            llm_ai_engine="openai",
        )
    )

    client = TestClient(create_app())

    def approve_asset_candidate(candidate: AssetCandidateRecord, link_relationships: list[dict] | None = None) -> str:
        upsert_asset_candidate(candidate, workspace_dir=tmp_path)
        approved = client.post(
            f"/api/v1/assets/candidates/{candidate.id}/review",
            json={
                "status": "approved",
                "reviewer_employee_id": "clara",
                "reason": "Asset candidate is durable and ready for registry promotion.",
                "link_relationships": link_relationships or [],
            },
        )
        assert approved.status_code == 200
        return approved.json()["asset"]["id"]

    old_asset_id = approve_asset_candidate(
        AssetCandidateRecord(
            id="asset-candidate-relationship-old",
            source_candidate_id="memory-candidate-relationship-old",
            asset_id="asset-relationship-old",
            asset_type="skill",
            title="Old relationship guidance",
            content="Older guidance for runtime relationship projection.",
            status="proposed",
            scope_kind="ticket",
            scope_ref=ticket.id,
            owner_employee_id="alex",
            source_kind="external_runtime_skill_candidate",
            source_ref="external-runtime:claude_code:relationship-old",
            provenance={
                "source_ticket_id": ticket.id,
                "source_employee_id": "alex",
                "source_run_id": "run-asset-relationship-old",
            },
            created_at="2026-06-08T00:00:00+00:00",
            updated_at="2026-06-08T00:00:00+00:00",
        )
    )
    new_asset_id = approve_asset_candidate(
        AssetCandidateRecord(
            id="asset-candidate-relationship-new",
            source_candidate_id="memory-candidate-relationship-new",
            asset_id="asset-relationship-new",
            asset_type="skill",
            title="New relationship guidance",
            content="Newer guidance supersedes the older runtime relationship projection guidance.",
            status="proposed",
            scope_kind="ticket",
            scope_ref=ticket.id,
            owner_employee_id="alex",
            source_kind="external_runtime_skill_candidate",
            source_ref="external-runtime:claude_code:relationship-new",
            provenance={
                "source_ticket_id": ticket.id,
                "source_employee_id": "alex",
                "source_run_id": "run-asset-relationship-new",
                "source_report_id": "report-asset-relationship-new",
                "evidence_id": "evidence-asset-relationship-new",
            },
            created_at="2026-06-08T00:00:01+00:00",
            updated_at="2026-06-08T00:00:01+00:00",
        ),
        link_relationships=[
            {
                "type": "supersedes",
                "target_kind": "asset",
                "target_ref": old_asset_id,
                "reason": "New relationship projection guidance replaces the older guidance.",
                "confidence": 0.94,
            }
        ],
    )

    assert client.post(f"/api/v1/assets/records/{old_asset_id}/project/graphiti").status_code == 200
    assert client.post(f"/api/v1/assets/records/{new_asset_id}/project/graphiti").status_code == 200

    projected = client.post(f"/api/v1/assets/records/{new_asset_id}/relationships/project/graphiti")
    assert projected.status_code == 200
    payload = projected.json()
    assert payload["status"] == "ingested"
    assert len(payload["ingested_relationships"]) == 1
    relationship = payload["ingested_relationships"][0]
    assert relationship["relationship_type"] == "supersedes"
    assert relationship["source_asset_id"] == new_asset_id
    assert relationship["target_asset_id"] == old_asset_id
    relationship_id = relationship["relationship_id"]
    provenance = relationship["ingested_asset"]["provenance"]
    assert provenance["asset_id"] == relationship_id
    assert provenance["asset_type"] == "asset_relationship"
    assert provenance["source_ticket_id"] == ticket.id
    assert provenance["source_employee_id"] == "alex"
    assert provenance["source_run_id"] == "run-asset-relationship-new"
    assert provenance["metadata"]["relationship_type"] == "supersedes"
    assert provenance["metadata"]["source_asset_id"] == new_asset_id
    assert provenance["metadata"]["target_asset_id"] == old_asset_id
    assert provenance["metadata"]["confidence"] == 0.94
    assert provenance["provider_refs"]

    new_record = next(record for record in list_asset_records(asset_type="skill", workspace_dir=tmp_path) if record.id == new_asset_id)
    assert new_record.provenance["graphiti_relationships"][0]["relationship_id"] == relationship_id
    assert new_record.provenance["graphiti_relationships"][0]["episode_id"] == f"episode-{relationship_id}"
    assert len(FakeGraphiti.indexed_episodes) == 3

    projected_again = client.post(f"/api/v1/assets/records/{new_asset_id}/relationships/project/graphiti")
    assert projected_again.status_code == 200
    repeated_payload = projected_again.json()
    assert repeated_payload["status"] == "skipped"
    assert repeated_payload["skipped_relationships"][0]["asset_id"] == relationship_id
    assert len(FakeGraphiti.indexed_episodes) == 3


async def test_approved_memory_recall_records_usage_and_ticket_graph_edge(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    _use_local_ticket_backend()

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-approved-recall-1"

    class FakeAddResult:
        episode = FakeEpisode()

    class FakeGraphiti:
        def __init__(self, *args, **kwargs):
            pass

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            return FakeAddResult()

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)
    update_graphiti_settings(
        GraphitiSettingsUpdateRequest(
            enabled=True,
            graph_database="neo4j",
            uri="bolt://localhost:7687",
            user="neo4j",
            group_id="aiteamos-test",
            llm_ai_engine="openai",
        )
    )
    source_ticket = create_ticket(
        TicketCreateRequest(
            title="Source recall lesson",
            description="Source Ticket produced a durable memory.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-source-memory",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    candidate = create_memory_candidate(
        MemoryCandidateCreateRequest(
            content="Runtime recall usage applied should be recorded as Ticket graph provenance.",
            source_kind="execution_result",
            source_ref=".aiteamos/traces/run-source-memory.jsonl",
            scope_kind="project",
            scope_ref="aiteamos",
            memory_type="principle",
            confidence=0.9,
            employee_ids=["alex"],
            tags=["runtime", "recall", "usage"],
            provenance={
                "source_ticket_id": source_ticket.id,
                "source_employee_id": "alex",
                "source_run_id": "run-source-memory",
                "source_trace_path": ".aiteamos/traces/run-source-memory.jsonl",
            },
        )
    )
    approved = await approve_memory_candidate(candidate.id)
    followup_ticket = create_ticket(
        TicketCreateRequest(
            title="Followup recall usage",
            description="Followup Ticket should reuse approved memory.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-followup-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )

    service = ChatGovernanceService(workspace_dir=tmp_path / ".aiteamos")
    request, result = await service.handle_message(
        ChatGovernanceInput(
            message=f"Report Ticket {followup_ticket.id}: runtime recall usage applied",
            employee={"id": "alex", "display_name": "Alex", "role": "AI RD / Implementer"},
            selected_ai_engine="stub",
            thread_id="thread-recall-usage",
            run_id="run-recall-usage",
            ticket_keys=[followup_ticket.id],
            trace_ref=".aiteamos/traces/run-recall-usage.jsonl",
        )
    )

    recalled = request.task_context["recalled_memories"]
    updated = list_memory_candidates(status="approved")[0]
    usage_history = updated.provenance["usage_history"]
    graph = ticket_graph_projection(followup_ticket.id)
    edge_types = {edge.type for edge in graph.edges} if graph else set()

    assert result.status == "completed"
    assert recalled[0]["memory_id"] == approved.id
    assert recalled[0]["graphiti_backed"] is True
    assert usage_history[0]["source_ticket_ids"] == [followup_ticket.id]
    assert usage_history[0]["source_run_id"] == "run-recall-usage"
    assert usage_history[0]["graphiti_episode_id"] == "episode-approved-recall-1"
    assert "memory_recall_usage_refs" in result.learning_delta
    assert any(
        event.get("data", {}).get("command", {}).get("id") == "memory.recall:record_usage"
        for event in result.tool_events
    )
    assert graph is not None
    assert "run.recalls_memory" in edge_types


async def test_chat_can_close_self_bootstrap_batch_with_learning_and_recall_usefulness(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    _use_local_ticket_backend()

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        uuid = "episode-self-bootstrap-close-1"

    class FakeAddResult:
        episode = FakeEpisode()

    class FakeGraphiti:
        def __init__(self, *args, **kwargs):
            pass

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            return FakeAddResult()

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)
    update_graphiti_settings(
        GraphitiSettingsUpdateRequest(
            enabled=True,
            graph_database="neo4j",
            uri="bolt://localhost:7687",
            user="neo4j",
            group_id="aiteamos-test",
            llm_ai_engine="openai",
        )
    )
    source_ticket = create_ticket(
        TicketCreateRequest(
            title="Self-bootstrap source lesson",
            description="Source Ticket produced reusable self-bootstrap learning.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_run_id="run-bootstrap-source",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    candidate = create_memory_candidate(
        MemoryCandidateCreateRequest(
            content="Self-bootstrap closure should record recall usefulness before the next batch relies on recalled assets.",
            source_kind="execution_result",
            source_ref=".aiteamos/traces/run-bootstrap-source.jsonl",
            scope_kind="ticket",
            scope_ref=source_ticket.id,
            memory_type="principle",
            confidence=0.91,
            employee_ids=["alex", "clara"],
            tags=["self-bootstrap", "recall-usefulness"],
            provenance={
                "source_ticket_id": source_ticket.id,
                "source_employee_id": "alex",
                "source_run_id": "run-bootstrap-source",
                "source_trace_path": ".aiteamos/traces/run-bootstrap-source.jsonl",
            },
        )
    )
    approved = await approve_memory_candidate(candidate.id)
    batch_ticket = create_ticket(
        TicketCreateRequest(
            title="Self-bootstrap: improve runtime-first execution evidence",
            description="Acceptance Criteria:\n- Clara records a learning summary, proposed candidates, and recall usefulness.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            validation_employee_id="peter",
            validation_role="AI PV",
            source_run_id="run-bootstrap-batch-seed",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    record_memory_recall_usage(
        memory_refs=[
            {
                "memory_id": approved.id,
                "graphiti_recalled": True,
                "graphiti_episode_id": approved.graphiti_episode_id,
                "graphiti_result_id": "graphiti-result-close-1",
            }
        ],
        run_id="run-bootstrap-work",
        employee_id="alex",
        ticket_keys=[batch_ticket.id],
        query="self-bootstrap runtime-first execution evidence",
        trace_path=".aiteamos/traces/run-bootstrap-work.jsonl",
    )

    service = ChatGovernanceService(workspace_dir=tmp_path / ".aiteamos")
    request, result = await service.handle_message(
        ChatGovernanceInput(
            message=f"Close self-bootstrap batch for Ticket {batch_ticket.id}; recalled assets were useful.",
            employee={"id": "clara", "display_name": "Clara", "role": "AI Team OS Manager"},
            selected_ai_engine="stub",
            thread_id="thread-self-bootstrap-close",
            run_id="run-self-bootstrap-close",
            ticket_keys=[batch_ticket.id],
            trace_ref=".aiteamos/traces/run-self-bootstrap-close.jsonl",
        )
    )

    updated_ticket = get_ticket(batch_ticket.id)
    approved_memory = next(item for item in list_memory_candidates(status="approved") if item.id == approved.id)
    usage_history = approved_memory.provenance["usage_history"]
    useful_usage = next(item for item in usage_history if item["source_run_id"] == "run-bootstrap-work")
    proposed = list_memory_candidates(status="proposed")
    graph = ticket_graph_projection(batch_ticket.id)
    edge_types = {edge.type for edge in graph.edges} if graph else set()

    assert request.action_plan.action == "self_bootstrap_close"
    assert request.ticket_binding.mode == "existing"
    assert result.executor_id == "local_tool"
    assert result.status == "completed"
    assert result.output_ticket_id == batch_ticket.id
    assert result.learning_delta["action"] == "self_bootstrap_close"
    assert result.learning_delta["reviewed_recall_usages"][0]["memory_id"] == approved.id
    assert useful_usage["usefulness_status"] == "used"
    assert useful_usage["reviewer_employee_id"] == "clara"
    assert updated_ticket is not None
    assert any(report.report_type == "learning_summary" and "Recall usefulness reviews recorded: 1" in report.content for report in updated_ticket.reports)
    assert any(candidate.provenance["action"] == "self_bootstrap_close" and candidate.scope_ref == batch_ticket.id for candidate in proposed)
    assert any(
        event.get("data", {}).get("command", {}).get("id") == "tickets.manage:self_bootstrap_close"
        and event.get("event") == "command.completed"
        for event in result.tool_events
    )
    assert graph is not None
    assert "run.recalls_memory" in edge_types
