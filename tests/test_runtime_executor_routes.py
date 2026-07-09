from __future__ import annotations

import json
from pathlib import Path
import stat
from urllib.parse import quote

from fastapi.testclient import TestClient

from aiteamos_api.main import create_app
from aiteamos_api.read.chat_action_plan import ChatActionPlan
from aiteamos_api.read.execution_contract import ExecutionRequest, ExecutionResult, TicketBinding
from aiteamos_api.read.execution_result_ingestion_service import ExecutionResultIngestionService
from aiteamos_api.read.memory_service import (
    MemoryCandidateCreateRequest,
    create_memory_candidate,
    list_memory_candidates,
)
from aiteamos_api.read.runtime_executor_smoke_service import (
    RuntimeExecutorDogfoodRequest,
    RuntimeExecutorSmokeRequest,
    RuntimeExecutorSmokeResponse,
    RuntimeExecutorSmokeService,
)
from aiteamos_api.read.runtime_executors.codex_cli_executor import CodexCliExecutor
from aiteamos_api.read.runtime_executors.langgraph_executor import LangGraphExecutor
from aiteamos_api.read.ticket_service import (
    TicketBackendSettingsUpdateRequest,
    TicketCreateRequest,
    create_ticket,
    employee_work_ledger,
    get_ticket,
    get_ticket_events,
    update_ticket_backend_settings,
)


def _use_local_ticket_backend() -> None:
    update_ticket_backend_settings(
        TicketBackendSettingsUpdateRequest(mode="local_file", local_file_path=".aiteamos/tickets/index.json")
    )


def _write_fake_runtime(path, body: str) -> str:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


class _FakeHttpResponse:
    status_code = 200
    text = ""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.content = str(payload).encode("utf-8")

    def json(self):
        return self._payload


def test_runtime_executor_registry_lists_backends_capabilities_and_setup_blockers(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)

    response = TestClient(create_app()).get("/api/v1/runtime-executors")

    assert response.status_code == 200
    payload = response.json()
    executors = {item["executor_id"]: item for item in payload["executors"]}

    assert payload["summary"]["runtime_boundary"] == "RuntimeExecutor"
    assert "direct_llm" not in executors
    assert executors["langgraph"]["status"] == "ready"
    assert "answer_only" in executors["langgraph"]["capabilities"]
    assert executors["langgraph"]["setup_required"] == []
    assert "claude_code" in executors
    assert "repo:write" in executors["claude_code"]["capabilities"]
    assert executors["claude_code"]["diagnostics"]["mutation_guard"]["required"] == [
        "ticket_bound",
        "approval_bound",
        "evidence_bound",
    ]
    assert not any(blocker["executor_id"] == "direct_llm" for blocker in payload["blockers"])
    live_readiness = payload["live_provider_readiness"]
    assert live_readiness["status"] == "blocked"
    assert live_readiness["profile"] == "core_loop"
    assert live_readiness["selected_executor_id"] == "langgraph"
    assert live_readiness["require_repo_write_executor"] is False
    assert live_readiness["mutation_gate"]["open"] is False
    assert "runtime_executor_lacks_repo_write" not in live_readiness["reasons"]
    assert "live_provider_dogfood_not_confirmed" in live_readiness["reasons"]
    assert "select a ready RuntimeExecutor with repo:write" not in live_readiness["setup_required"]
    assert payload["summary"]["live_provider_status"] == "blocked"
    assert payload["summary"]["live_provider_blocker_count"] == len(live_readiness["blockers"])


def test_runtime_smoke_chooses_executor_compatible_action_for_deepseek_backends(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    service = RuntimeExecutorSmokeService(workspace_dir=tmp_path)

    universal_request = service._build_execution_request(
        "universal_employee_agent",
        RuntimeExecutorSmokeRequest(
            message="Run DeepSeek-backed employee agent smoke.",
            workspace_id=str(tmp_path),
            ticket_id="rd-smoke-1",
        ),
    )
    codex_request = service._build_execution_request(
        "codex_cli",
        RuntimeExecutorSmokeRequest(
            message="Run repo runtime smoke.",
            workspace_id=str(tmp_path),
            ticket_id="rd-smoke-1",
        ),
    )

    assert universal_request.action_plan.action == "answer_only"
    assert universal_request.permission_policy["selected_executor"] == "universal_employee_agent"
    assert universal_request.permission_policy["selected_ai_engine"] == "deepseek"
    assert codex_request.action_plan.action == "inspect_code_repository"


def test_runtime_dogfood_accepts_ingested_needs_approval_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    service = RuntimeExecutorSmokeService(workspace_dir=tmp_path)

    ingested_smoke = RuntimeExecutorSmokeResponse(
        executor_id="codex_cli",
        request={},
        result={"status": "needs_approval"},
        ingested=True,
    )
    non_ingested_smoke = ingested_smoke.model_copy(update={"ingested": False})

    assert service._smoke_passed_for_dogfood(ingested_smoke) is True
    assert service._smoke_passed_for_dogfood(non_ingested_smoke) is False


def test_runtime_dogfood_approved_run_message_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    service = RuntimeExecutorSmokeService(workspace_dir=tmp_path)
    message = service._dogfood_approved_run_message(
        RuntimeExecutorDogfoodRequest(
            executor_id="codex_cli",
            repository_ids=["repo-aiteamos"],
        ),
        "codex_cli",
        "ops-1234",
    )

    assert ".aiteamos/artifacts/runtime_dogfood/ops-1234-codex_cli.md" in message
    assert "Do not run scripts/live_provider_dogfood.py" in message
    assert "recursive dogfood/readiness command" in message
    assert "changed_files or repo_patch" in message
    assert "test or validation" in message


def test_external_runtime_repo_mutation_accepts_validation_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    request = ExecutionRequest(
        request_id="validation-evidence-contract",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id="ops-validation",
        ticket_binding=TicketBinding(mode="existing", ticket_id="ops-validation", required=True),
        action_plan=ChatActionPlan(action="implement_ticket", arguments={"message": "Implement approved mutation."}),
        capability_grants=["repo:read", "repo:write", "ticket:evidence:write"],
        approval_policy={"approved_capabilities": ["repo:write"], "approval_refs": ["approval-validation"]},
        expected_outputs={"evidence": True, "artifacts": True},
    )
    result = ExecutionResult(
        request_id=request.request_id,
        executor_id="codex_cli",
        status="completed",
        report="Approved mutation completed with validation evidence.",
        output_ticket_id="ops-validation",
        artifacts=[
            {
                "kind": "changed_files",
                "changed_files": [".aiteamos/artifacts/runtime_dogfood/ops-validation-codex_cli.md"],
            }
        ],
        evidence=[
            {
                "kind": "validation",
                "ref": "py_compile:runtime_executor_smoke_service.py",
                "summary": "Validation passed.",
            }
        ],
    )

    validated = CodexCliExecutor()._validate_repo_mutation_result(request, result)

    assert validated.status == "completed"
    assert validated.errors == []


def test_runtime_executor_config_is_saved_and_used_by_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-configured-smoke",
        """#!/usr/bin/env python3
import json
import sys
payload = json.loads(sys.stdin.read())
print(json.dumps({
    "report": "Configured smoke used " + payload["execution_request"]["request_id"],
    "artifacts": [{"kind": "configured_smoke_artifact"}],
    "evidence": [{"kind": "configured_smoke_evidence", "ref": "smoke://configured/claude-code"}],
    "usage": {"configured_smoke_steps": 1}
}))
""",
    )

    config_response = TestClient(create_app()).put(
        "/api/v1/runtime-executors/claude_code/config",
        json={
            "binary_path": fake_cli,
            "working_dir": str(tmp_path),
            "model": "deepseek-coder",
            "api_base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "mode": "non_destructive_inspect_and_report",
            "timeout_seconds": 60,
        },
    )

    assert config_response.status_code == 200
    saved = config_response.json()
    assert saved["executor_id"] == "claude_code"
    assert saved["binary_path"] == fake_cli
    assert saved["saved_path"].endswith("runtime_executors.json")

    registry_response = TestClient(create_app()).get("/api/v1/runtime-executors")
    executors = {item["executor_id"]: item for item in registry_response.json()["executors"]}
    assert executors["claude_code"]["status"] == "ready"
    assert executors["claude_code"]["health"]["config"]["model"] == "deepseek-coder"

    smoke_response = TestClient(create_app()).post(
        "/api/v1/runtime-executors/claude_code/smoke",
        json={
            "message": "Smoke must use saved RuntimeExecutor config",
            "employee_id": "alex",
        },
    )

    assert smoke_response.status_code == 200
    payload = smoke_response.json()
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["report"].startswith("Configured smoke used smoke-claude_code")
    assert payload["result"]["artifacts"][0]["model"] == "deepseek-coder"
    assert payload["result"]["evidence"][1]["ref"] == "smoke://configured/claude-code"


def test_claude_code_compatible_smoke_runs_cli_and_can_ingest_ticket_report(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-smoke",
        """#!/usr/bin/env python3
import json
import os
import sys
payload = json.loads(sys.stdin.read())
print(json.dumps({
    "report": "Smoke inspected " + payload["execution_request"]["employee_id"],
    "artifacts": [{"kind": "smoke_artifact", "request_id": payload["execution_request"]["request_id"]}],
    "evidence": [{"kind": "smoke_evidence", "ref": "smoke://claude-code-compatible"}],
    "tool_events": [{"event": "smoke.step", "summary": os.environ.get("AITEAMOS_RUNTIME_MODE", "")}],
    "usage": {"smoke_steps": 1}
}))
""",
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Runtime smoke ticket",
            assigned_employee_id="alex",
            source_run_id="seed-runtime-smoke",
        )
    )

    response = TestClient(create_app()).post(
        "/api/v1/runtime-executors/claude_code/smoke",
        json={
            "message": "Smoke test Claude Code-compatible runtime",
            "employee_id": "alex",
            "workspace_id": str(tmp_path),
            "ticket_id": ticket.id,
            "runtime_config": {
                "binary_path": fake_cli,
                "working_dir": str(tmp_path),
                "mode": "non_destructive_inspect_and_report",
            },
            "ingest_result": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    result = payload["result"]
    updated = get_ticket(ticket.id)

    assert payload["executor_id"] == "claude_code"
    assert payload["ingested"] is True
    assert payload["request"]["permission_policy"]["selected_executor"] == "claude_code"
    assert payload["request"]["approval_policy"]["require_approval_for"] == ["repo:write"]
    assert result["status"] == "completed"
    assert result["artifacts"][0]["kind"] == "external_runtime_cli_execution"
    assert result["artifacts"][1]["kind"] == "smoke_artifact"
    assert result["evidence"][1]["ref"] == "smoke://claude-code-compatible"
    assert any(event["event"] == "smoke.step" for event in result["tool_events"])
    assert updated is not None
    assert any(report.report_type == "external_runtime_report" for report in updated.reports)
    assert any("smoke://claude-code-compatible" in evidence for report in updated.reports for evidence in report.evidence)


def test_runtime_execution_sessions_list_checkpoint_and_replay_refs(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    trace_path = tmp_path / ".aiteamos" / "traces" / "exec-runtime-session.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(
        '{"event":"trace.step","authorization":"Bearer secret","data":{"token":"secret-token","visible":"yes"}}\n',
        encoding="utf-8",
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Runtime replay session",
            assigned_employee_id="alex",
            source_run_id="seed-runtime-session",
        )
    )
    request = ExecutionRequest(
        request_id="exec-runtime-session",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="append_report", arguments={"content": "Runtime report"}),
        task_context={
            "universal_context": {
                "provenance_summary": [
                    {
                        "kind": "ticket",
                        "source_kind": "ticket_service",
                        "source_ref": ticket.id,
                        "scope_kind": "ticket",
                        "scope_ref": ticket.id,
                    }
                ]
            }
        },
    )
    result = ExecutionResult(
        request_id=request.request_id,
        executor_id="claude_code",
        status="completed",
        report="Runtime report completed.",
        output_ticket_id=ticket.id,
        executor_session_ref="claude_code-exec-runtime-session",
        checkpoint_ref="claude_code:exec-runtime-session",
        trace_ref=".aiteamos/traces/exec-runtime-session.jsonl",
        artifacts=[
            {"kind": "runtime_session_artifact", "ref": "artifact://runtime-session", "api_key": "secret"},
            {
                "kind": "employee_handoff_request",
                "ticket_id": ticket.id,
                "from_employee_id": "alex",
                "from_role": "AI RD / Implementer",
                "to_employee_id": "victor",
                "to_role": "AI Runtime Owner",
                "content": "Production runtime ownership requires Victor scoped context.",
                "lane": "rd",
                "confidence": 0.91,
                "policy": {
                    "policy_aware": True,
                    "required_memory_scopes": ["employee:victor"],
                    "matched_memory_scopes": ["employee:victor"],
                    "available_memory_scopes": ["aiteamos", "employee:victor"],
                    "memory_scope_match": "matched",
                    "risk_level": "critical",
                    "max_risk_level": "critical",
                    "risk_allowed": True,
                },
                "provenance": {
                    "source_kind": "langgraph_handoff_decision",
                    "source_ref": "exec-runtime-session",
                    "scope_kind": "ticket",
                    "scope_ref": ticket.id,
                },
            },
        ],
        evidence=[{"kind": "test_evidence", "ref": "pytest::runtime-session::passed"}],
        tool_events=[
            {
                "event": "universal_agent.tool.completed",
                "data": {
                    "output_refs": [{"kind": "ticket", "ref": ticket.id}, {"kind": "memory", "ref": "mem-runtime-session"}],
                    "provenance": [{"source_kind": "aiteamos_service", "source_ref": "list_tickets"}],
                },
            }
        ],
    )

    ExecutionResultIngestionService(workspace_dir=tmp_path).ingest(request, result)
    source_work = employee_work_ledger("alex")
    target_work = employee_work_ledger("victor")

    assert source_work.handoffs and source_work.handoffs[0]["relation"] == "source"
    assert target_work.handoffs and target_work.handoffs[0]["relation"] == "target"

    client = TestClient(create_app())
    response = client.get("/api/v1/runtime-executors/sessions?executor_id=claude_code")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["executor_id"] == "claude_code"
    assert payload[0]["employee_id"] == "alex"
    assert payload[0]["ticket_id"] == ticket.id
    assert payload[0]["checkpoint_ref"] == "claude_code:exec-runtime-session"
    assert payload[0]["tool_events"][0]["event"] == "universal_agent.tool.completed"
    assert payload[0]["ticket_refs"] == [ticket.id]
    assert payload[0]["memory_refs"] == ["mem-runtime-session"]
    assert any(ref["source_ref"] == "list_tickets" for ref in payload[0]["context_refs"])

    session_key = quote(payload[0]["session_key"], safe="")
    replay_response = client.get(f"/api/v1/runtime-executors/sessions/{session_key}")
    timeline_response = client.get(f"/api/v1/runtime-executors/sessions/{session_key}/timeline")

    assert replay_response.status_code == 200
    replay = replay_response.json()
    assert replay["session"]["session_key"] == payload[0]["session_key"]
    assert replay["execution_artifacts"]["request_id"] == "exec-runtime-session"
    assert replay["execution_artifacts"]["artifacts"][0]["api_key"] == "[redacted]"
    assert replay["trace_events"][0]["authorization"] == "[redacted]"
    assert replay["trace_events"][0]["data"]["token"] == "[redacted]"
    assert replay["trace_events"][0]["data"]["visible"] == "yes"
    handoff_summary = replay["handoff_summary"]
    assert handoff_summary["schema"] == "execution_replay_handoff_policy.v1"
    assert handoff_summary["status"] == "employee_handoff_recorded"
    assert handoff_summary["source_kind"] == "execution_artifact"
    assert handoff_summary["target_employee_id"] == "victor"
    assert handoff_summary["required_memory_scopes"] == ["employee:victor"]
    assert handoff_summary["matched_memory_scopes"] == ["employee:victor"]
    assert handoff_summary["memory_scope_match"] == "matched"
    assert handoff_summary["risk_level"] == "critical"
    assert handoff_summary["max_risk_level"] == "critical"
    assert handoff_summary["risk_allowed"] is True
    assert {"kind": "employee", "ref": "victor"} in handoff_summary["refs"]
    assert replay["state_transitions"][0]["event"] == "execution.state_transition"
    assert replay["state_transitions"][0]["source_kind"] == "session"
    assert replay["state_transitions"][0]["from"] == "execution_request"
    assert replay["state_transitions"][0]["to"] == "completed"
    assert replay["state_transitions"][0]["checkpoint_ref"] == "claude_code:exec-runtime-session"
    coverage = replay["coverage_summary"]
    assert coverage["schema"] == "execution_replay_coverage.v1"
    assert coverage["required_chain_complete"] is True
    assert coverage["gaps"] == []
    assert coverage["coverage"]["ticket"] is True
    assert coverage["coverage"]["employee"] is True
    assert coverage["coverage"]["runtime"] is True
    assert coverage["coverage"]["evidence"] is True
    assert coverage["coverage"]["trace"] is True
    assert coverage["coverage"]["state"] is True
    assert coverage["coverage"]["checkpoint"] is True
    assert coverage["coverage"]["approval"] is True
    assert coverage["coverage"]["handoff"] is True
    assert coverage["coverage"]["handoff_policy"] is True
    assert coverage["counts"]["handoff_ref_count"] >= 3
    assert coverage["refs"]["ticket_refs"] == [ticket.id]
    assert coverage["refs"]["employee_refs"] == ["alex"]
    assert "pytest::runtime-session::passed" in coverage["refs"]["evidence_refs"]
    assert coverage["counts"]["timeline_event_count"] == len(replay["timeline"])
    assert coverage["counts"]["trace_event_count"] == 1
    assert coverage["counts"]["state_transition_count"] == len(replay["state_transitions"])

    timeline = replay["timeline"]
    assert [item["index"] for item in timeline] == list(range(len(timeline)))
    assert any(item["event"] == "universal_agent.tool.completed" for item in timeline)
    assert any(item["event"] == "runtime_session_artifact" for item in timeline)
    assert any(item["event"] == "employee_handoff_request" for item in timeline)
    assert any(item["event"] == "test_evidence" for item in timeline)
    assert any(item["event"] == "execution.state_transition" for item in timeline)
    assert any(item["event"] == "trace.step" for item in timeline)

    assert timeline_response.status_code == 200
    assert timeline_response.json()["session"]["session_key"] == payload[0]["session_key"]
    assert timeline_response.json()["timeline"] == timeline

    missing = client.get("/api/v1/runtime-executors/sessions/missing-session")
    assert missing.status_code == 404


async def test_runtime_replay_includes_native_langgraph_checkpoint_history(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Native checkpoint replay",
            assigned_employee_id="alex",
            source_run_id="seed-native-checkpoint-replay",
        )
    )
    request = ExecutionRequest(
        request_id="exec-native-checkpoint-replay",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="implement_ticket", arguments={"ticket_id": ticket.id}),
        task_context={"task_summary": "Implement through LangGraph and stop at approval."},
        capability_grants=["repo:write", "ticket:evidence:write"],
        permission_policy={
            "selected_executor": "universal_employee_agent",
            "requested_runtime_executor": "claude_code",
        },
        approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
        trace_context={
            "run_id": "exec-native-checkpoint-replay",
            "thread_id": "thread-native-checkpoint-replay",
            "trace_ref": ".aiteamos/traces/exec-native-checkpoint-replay.jsonl",
        },
    )
    executor = LangGraphExecutor(workspace_dir=tmp_path / ".aiteamos")

    result = await executor.run(request)
    ExecutionResultIngestionService(workspace_dir=tmp_path).ingest(request, result)
    if executor._checkpoint_connection is not None:
        await executor._checkpoint_connection.close()

    session_key = quote(f"alex::thread-native-checkpoint-replay::{ticket.id}", safe="")
    response = TestClient(create_app()).get(f"/api/v1/runtime-executors/sessions/{session_key}")

    assert response.status_code == 200
    replay = response.json()
    assert result.status == "needs_approval"
    assert replay["native_checkpoint_history"]
    assert any(
        item["state_summary"]["current_step"] == "request_approval_interrupt"
        for item in replay["native_checkpoint_history"]
    )
    assert any(
        item["source_kind"] == "native_checkpoint"
        and item["to"] == "request_approval_interrupt"
        for item in replay["state_transitions"]
    )
    assert any(item["event"] == "execution.native_checkpoint" for item in replay["timeline"])
    assert any(
        item["event"] == "execution.state_transition" and item["data"]["source_kind"] == "native_checkpoint"
        for item in replay["timeline"]
    )


def test_runtime_smoke_records_ingestion_blocker_for_invalid_result(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-invalid-smoke",
        """#!/usr/bin/env python3
import json
import sys
json.loads(sys.stdin.read())
print(json.dumps({"artifacts": [{"kind": "smoke_artifact_without_report"}]}))
""",
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Runtime smoke invalid result ticket",
            assigned_employee_id="alex",
            source_run_id="seed-runtime-smoke-invalid",
        )
    )

    response = TestClient(create_app()).post(
        "/api/v1/runtime-executors/claude_code/smoke",
        json={
            "message": "Smoke test invalid runtime result contract",
            "employee_id": "alex",
            "workspace_id": str(tmp_path),
            "ticket_id": ticket.id,
            "runtime_config": {
                "binary_path": fake_cli,
                "working_dir": str(tmp_path),
            },
            "ingest_result": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    updated = get_ticket(ticket.id)

    assert payload["executor_id"] == "claude_code"
    assert payload["ingested"] is False
    assert payload["result"]["status"] == "blocked"
    assert payload["result"]["errors"][-1]["reason"] == "runtime_result_contract_missing_report"
    assert "report/summary/message/text" in payload["ingestion_blocker"]
    assert updated is not None
    assert not any(report.report_type == "external_runtime_report" for report in updated.reports)


def test_cursor_smoke_runs_configured_http_adapter_without_ticket_ingestion(monkeypatch):
    calls: list[dict] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, json):
            calls.append({"url": url, "headers": headers, "json": json})
            return _FakeHttpResponse(
                {
                    "report": "Cursor smoke completed",
                    "artifacts": [{"kind": "cursor_smoke_artifact"}],
                    "evidence": [{"kind": "cursor_smoke_evidence", "ref": "smoke://cursor"}],
                    "usage": {"cursor_smoke_steps": 1},
                }
            )

    monkeypatch.setenv("CURSOR_API_KEY", "cursor-test-key")
    monkeypatch.setattr(
        "aiteamos_api.read.runtime_executors.external_runtime_executor.httpx.AsyncClient",
        FakeAsyncClient,
    )

    response = TestClient(create_app()).post(
        "/api/v1/runtime-executors/cursor/smoke",
        json={
            "message": "Smoke test Cursor HTTP adapter",
            "employee_id": "alex",
            "runtime_config": {
                "api_base_url": "https://cursor.example",
                "http_endpoint_path": "/agent/inspect",
                "api_key_env": "CURSOR_API_KEY",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    result = payload["result"]

    assert payload["executor_id"] == "cursor"
    assert payload["ingested"] is False
    assert result["status"] == "completed"
    assert result["artifacts"][0]["kind"] == "external_runtime_http_execution"
    assert result["artifacts"][1]["kind"] == "cursor_smoke_artifact"
    assert result["evidence"][1]["ref"] == "smoke://cursor"
    assert calls[0]["url"] == "https://cursor.example/agent/inspect"
    assert calls[0]["headers"]["Authorization"] == "Bearer cursor-test-key"
    assert calls[0]["json"]["execution_request"]["task_context"]["diagnostic"]["kind"] == "runtime_executor_smoke"


def test_runtime_smoke_batch_summarizes_success_and_setup_blockers(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-batch-smoke",
        """#!/usr/bin/env python3
import json
import sys
payload = json.loads(sys.stdin.read())
print(json.dumps({
    "report": "Batch smoke inspected " + payload["execution_request"]["employee_id"],
    "artifacts": [{"kind": "batch_smoke_artifact"}],
    "evidence": [{"kind": "batch_smoke_evidence", "ref": "smoke://batch/claude-code-compatible"}],
    "usage": {"batch_smoke_steps": 1}
}))
""",
    )

    response = TestClient(create_app()).post(
        "/api/v1/runtime-executors/smoke-batch",
        json={
            "message": "Run runtime smoke batch",
            "employee_id": "alex",
            "executor_ids": ["claude_code", "cursor"],
            "runtime_config_by_executor": {
                "claude_code": {
                    "binary_path": fake_cli,
                    "working_dir": str(tmp_path),
                }
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    results = {item["executor_id"]: item for item in payload["results"]}

    assert payload["status"] == "blocked"
    assert payload["summary"]["executor_count"] == 2
    assert payload["summary"]["completed_count"] == 1
    assert payload["summary"]["blocked_count"] == 1
    assert payload["summary"]["blocked_executor_ids"] == ["cursor"]
    assert payload["learning_delta"]["action"] == "runtime_executor_smoke_batch"
    assert payload["learning_delta"]["executor_ids"] == ["claude_code", "cursor"]
    assert payload["learning_delta"]["ticket_bound"] is False
    assert results["claude_code"]["result"]["status"] == "completed"
    assert results["claude_code"]["result"]["evidence"][1]["ref"] == "smoke://batch/claude-code-compatible"
    assert results["cursor"]["result"]["status"] == "blocked"
    assert results["cursor"]["result"]["errors"][-1]["reason"] == "executor_setup_blocker"
    assert results["claude_code"]["ingested"] is False


def test_runtime_dogfood_harness_creates_ticket_approval_and_ingests_approved_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-dogfood",
        """#!/usr/bin/env python3
import json
import sys
payload = json.loads(sys.stdin.read())
request = payload["execution_request"]
action = request["action_plan"]["action"]
if action == "inspect_code_repository":
    print(json.dumps({
        "report": "Dogfood smoke completed for " + request["ticket_id"],
        "artifacts": [{"kind": "dogfood_smoke_artifact"}],
        "evidence": [{"kind": "smoke_evidence", "ref": "smoke://dogfood/claude-code-compatible"}],
        "usage": {"dogfood_smoke_steps": 1}
    }))
else:
    print(json.dumps({
        "report": "Dogfood approved mutation executed for " + request["ticket_id"],
        "artifacts": [{
            "kind": "repo_patch",
            "changed_files": ["services/api/aiteamos_api/read/runtime_executor_smoke_service.py"],
            "diff_ref": "artifact://diff/runtime-dogfood.patch"
        }],
        "evidence": [{"kind": "test_evidence", "ref": "pytest::runtime-dogfood::passed"}],
        "usage": {"dogfood_approved_steps": 2}
    }))
""",
    )
    create_memory_candidate(
        MemoryCandidateCreateRequest(
            content="Old blocked RuntimeExecutor dogfood summary that used the legacy global dedupe key.",
            source_kind="runtime_executor_dogfood",
            source_ref="dogfood-claude_code",
            scope_kind="ticket",
            scope_ref="old-ticket",
            memory_type="summary",
            confidence=0.62,
            employee_ids=["clara"],
            tags=["runtime-executor-dogfood", "claude_code", "blocked"],
            provenance={
                "action": "runtime_executor_dogfood",
                "source_run_id": "dogfood-claude_code",
                "execution_candidate_index": "runtime_executor_dogfood_summary",
            },
        )
    )

    response = TestClient(create_app()).post(
        "/api/v1/runtime-executors/dogfood",
        json={
            "executor_id": "claude_code",
            "message": "Dogfood approved runtime mutation from a governed Ticket.",
            "employee_id": "alex",
            "reviewer_employee_id": "clara",
            "workspace_id": str(tmp_path),
            "runtime_config": {
                "binary_path": fake_cli,
                "working_dir": str(tmp_path),
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    ticket_id = payload["ticket"]["id"]
    updated = get_ticket(ticket_id)
    approval = payload["approval"]
    approved_run = payload["approved_run"]
    candidates = list_memory_candidates(status="proposed")
    dogfood_candidate = next(
        candidate
        for candidate in candidates
        if candidate.provenance.get("action") == "runtime_executor_dogfood"
        and candidate.provenance.get("source_ticket_id") == ticket_id
    )

    assert payload["status"] == "completed"
    assert payload["learning_delta"]["action"] == "runtime_executor_dogfood"
    assert payload["learning_delta"]["ticket_id"] == ticket_id
    assert payload["learning_delta"]["memory_candidate_ids"] == [dogfood_candidate.id]
    assert payload["learning_delta"]["memory_candidate_count"] == 1
    assert payload["smoke_batch"]["status"] == "completed"
    assert approval["status"] == "approved"
    assert approval["ticket_id"] == ticket_id
    assert approved_run["ingested"] is True
    assert approved_run["request"]["approval_policy"]["approval_refs"] == [approval["id"]]
    approved_message = approved_run["request"]["action_plan"]["arguments"]["message"]
    assert "Do not run scripts/live_provider_dogfood.py" in approved_message
    assert f".aiteamos/artifacts/runtime_dogfood/{ticket_id}-claude_code.md" in approved_message
    assert approved_run["result"]["status"] == "completed"
    assert approved_run["result"]["artifacts"][1]["changed_files"] == [
        "services/api/aiteamos_api/read/runtime_executor_smoke_service.py"
    ]
    assert updated is not None
    report_types = [report.report_type for report in updated.reports]
    assert "external_runtime_report" in report_types
    assert "external_runtime_repo_mutation" in report_types
    assert "runtime_dogfood_summary" in report_types
    mutation_report = next(report for report in updated.reports if report.report_type == "external_runtime_repo_mutation")
    assert "Ticket-bound, approval-bound, and evidence-bound" in mutation_report.content
    summary_report = updated.reports[-1]
    assert summary_report.report_type == "runtime_dogfood_summary"
    assert "pytest::runtime-dogfood::passed" in summary_report.evidence
    assert "smoke://dogfood/claude-code-compatible" in summary_report.evidence
    assert dogfood_candidate.scope_kind == "ticket"
    assert dogfood_candidate.scope_ref == ticket_id
    assert dogfood_candidate.memory_type == "summary"
    assert dogfood_candidate.provenance["source_ticket_id"] == ticket_id
    assert dogfood_candidate.provenance["source_employee_id"] == "clara"
    assert dogfood_candidate.provenance["source_run_id"].startswith(f"dogfood-claude_code-{ticket_id}-")
    assert dogfood_candidate.provenance["source_run_id"].endswith(f"-{summary_report.id}")
    assert dogfood_candidate.provenance["executor_id"] == "claude_code"
    assert dogfood_candidate.provenance["approval_id"] == approval["id"]
    assert "pytest::runtime-dogfood::passed" in dogfood_candidate.provenance["summary_report"]["evidence"]

    second_response = TestClient(create_app()).post(
        "/api/v1/runtime-executors/dogfood",
        json={
            "executor_id": "claude_code",
            "message": "Repeat dogfood approved runtime mutation against the same governed Ticket.",
            "employee_id": "alex",
            "reviewer_employee_id": "clara",
            "workspace_id": str(tmp_path),
            "ticket_id": ticket_id,
            "create_ticket_if_missing": False,
            "runtime_config": {
                "binary_path": fake_cli,
                "working_dir": str(tmp_path),
            },
        },
    )

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["status"] == "completed"
    assert second_payload["approval"]["id"] == approval["id"]
    assert second_payload["learning_delta"]["memory_candidate_count"] == 1
    assert second_payload["learning_delta"]["reused_completed_approval"] is True


def test_approved_claude_code_runtime_run_uses_approval_ref_and_ingests_repo_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-approved-run",
        """#!/usr/bin/env python3
import json
import os
import sys
payload = json.loads(sys.stdin.read())
print(json.dumps({
    "report": "Approved runtime mutation executed for " + payload["execution_request"]["ticket_id"],
    "artifacts": [{
        "kind": "repo_patch",
        "changed_files": ["services/api/aiteamos_api/read/runtime_executor_routes.py"],
        "diff_ref": "artifact://diff/approved-runtime.patch",
        "model": os.environ.get("AITEAMOS_LLM_MODEL", "")
    }],
    "evidence": [{"kind": "test_evidence", "ref": "pytest::approved-runtime::passed"}],
    "usage": {"approved_runtime_steps": 2}
}))
""",
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Approved runtime route ticket",
            assigned_employee_id="alex",
            source_run_id="seed-runtime-approved-route",
        )
    )
    source_request = ExecutionRequest(
        request_id="exec-route-approval",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(
            action="implement_ticket",
            arguments={"message": "Implement approved route mutation."},
        ),
        capability_grants=["repo:write", "ticket:evidence:write"],
        permission_policy={"selected_ai_engine": "claude_code", "selected_executor": "claude_code"},
        approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
        expected_outputs={"report": True, "evidence": True, "artifacts": True},
        trace_context={"run_id": "exec-route-approval", "trace_ref": ".aiteamos/traces/exec-route-approval.jsonl"},
    )
    source_result = ExecutionResult(
        request_id=source_request.request_id,
        executor_id="claude_code",
        status="needs_approval",
        report="External repo mutation needs approval before execution.",
        output_ticket_id=ticket.id,
        executor_session_ref="lg-exec-route-approval",
        checkpoint_ref="langgraph:exec-route-approval",
        approval_requests=[
            {
                "kind": "repo_mutation",
                "ticket_id": ticket.id,
                "executor_id": "claude_code",
                "required_capability": "repo:write",
                "risk_level": "high",
                "reason": "External runtime repo mutation requires approval before execution.",
                "proposed_action": {
                    "action": "implement_ticket",
                    "ticket_id": ticket.id,
                    "executor_id": "claude_code",
                    "capability": "repo:write",
                },
                "checkpoint_ref": "langgraph:exec-route-approval",
                "executor_session_ref": "lg-exec-route-approval",
                "source_state_ref": "state://universal_employee_agent/exec-route-approval/governance_gate",
                "current_graph_node": "governance_gate",
            }
        ],
        errors=[{"reason": "repo_mutation_approval_required", "detail": "approval required"}],
    )
    ExecutionResultIngestionService(workspace_dir=tmp_path).ingest(source_request, source_result)
    client = TestClient(create_app())

    approvals = client.get("/api/v1/runtime-executors/claude_code/approvals")
    assert approvals.status_code == 200
    approval_payload = approvals.json()[0]
    approval_id = approval_payload["id"]
    waiting_ticket = get_ticket(ticket.id)
    waiting_events = get_ticket_events(ticket.id)
    assert waiting_ticket is not None
    assert waiting_ticket.status == "waiting_approval"
    assert any(
        event.type == "status_changed"
        and event.data.get("to") == "waiting_approval"
        and event.data.get("source_run_id") == approval_id
        for event in waiting_events
    )
    snapshot_ref = approval_payload["source_state_snapshot_ref"]
    snapshot_path = Path(snapshot_ref) if Path(snapshot_ref).is_absolute() else tmp_path / snapshot_ref
    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert "/execution_state_snapshots/" in f"/{snapshot_ref}"
    assert snapshot_ref.endswith(".json")
    assert snapshot_payload["snapshot_schema"] == "execution_state_snapshot.v1"
    assert snapshot_payload["source_state_ref"] == "state://universal_employee_agent/exec-route-approval/governance_gate"
    assert snapshot_payload["source_state_snapshot_ref"] == snapshot_ref
    assert snapshot_payload["checkpoint_ref"] == "langgraph:exec-route-approval"
    assert snapshot_payload["executor_session_ref"] == "lg-exec-route-approval"
    assert snapshot_payload["current_graph_node"] == "governance_gate"

    review = client.post(
        f"/api/v1/runtime-executors/claude_code/approvals/{approval_id}/review",
        json={"status": "approved", "reviewer_employee_id": "clara", "reason": "Approved for route test."},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "approved"
    reviewed_ticket = get_ticket(ticket.id)
    reviewed_events = get_ticket_events(ticket.id)
    assert reviewed_ticket is not None
    assert reviewed_ticket.status == "ready_to_resume"
    assert any(
        event.type == "status_changed"
        and event.data.get("to") == "ready_to_resume"
        and event.data.get("source_run_id") == approval_id
        for event in reviewed_events
    )

    run = client.post(
        f"/api/v1/runtime-executors/claude_code/approvals/{approval_id}/run",
        json={
            "employee_id": "clara",
            "workspace_id": str(tmp_path),
            "runtime_config": {
                "binary_path": fake_cli,
                "working_dir": str(tmp_path),
                "model": "deepseek-reasoner",
                "api_base_url": "https://api.deepseek.com",
                "api_key_env": "",
            },
        },
    )

    assert run.status_code == 200
    payload = run.json()
    result = payload["result"]
    updated = get_ticket(ticket.id)

    assert payload["ingested"] is True
    assert payload["request"]["employee_id"] == "alex"
    assert payload["request"]["request_id"].endswith("-attempt-1")
    assert payload["request"]["approval_policy"]["approved_capabilities"] == ["repo:write"]
    assert payload["request"]["approval_policy"]["approval_refs"] == [approval_id]
    assert payload["request"]["permission_policy"]["runtime_config"]["claude_code"]["model"] == "deepseek-reasoner"
    assert payload["request"]["trace_context"]["resume_from_checkpoint_ref"] == "langgraph:exec-route-approval"
    assert payload["request"]["trace_context"]["resume_from_executor_session_ref"] == "lg-exec-route-approval"
    assert payload["request"]["trace_context"]["source_state_ref"] == "state://universal_employee_agent/exec-route-approval/governance_gate"
    assert payload["request"]["trace_context"]["resume_source"] == "checkpoint_state"
    assert payload["request"]["trace_context"]["resume_snapshot_schema"] == "execution_state_snapshot.v1"
    assert payload["request"]["trace_context"]["resume_source_state_snapshot_ref"] == snapshot_ref
    assert payload["request"]["trace_context"]["resume_graph_node"] == "governance_gate"
    assert payload["request"]["task_context"]["resume_checkpoint_state"]["source_state_ref"] == (
        "state://universal_employee_agent/exec-route-approval/governance_gate"
    )
    assert payload["request"]["task_context"]["resume_checkpoint_state"]["source_state_snapshot_ref"] == snapshot_ref
    assert payload["request"]["task_context"]["resume_checkpoint_state"]["checkpoint_ref"] == "langgraph:exec-route-approval"
    assert payload["request"]["task_context"]["resume_checkpoint_state"]["current_graph_node"] == "governance_gate"
    assert result["status"] == "completed"
    assert result["artifacts"][0]["repo_mutation"] is True
    assert result["artifacts"][0]["approval_refs"] == [approval_id]
    assert result["artifacts"][0]["trace_ref"] == ".aiteamos/traces/exec-route-approval.jsonl"
    assert result["artifacts"][1]["changed_files"] == ["services/api/aiteamos_api/read/runtime_executor_routes.py"]
    assert result["evidence"][1]["ref"] == "pytest::approved-runtime::passed"
    assert payload["approval"]["last_run_status"] == "completed"
    assert payload["approval"]["last_run_request_id"].endswith("-attempt-1")
    assert len(payload["approval"]["run_history"]) == 1
    assert payload["approval"]["run_history"][0]["run_request_id"] == payload["request"]["request_id"]
    assert payload["approval"]["run_history"][0]["approval_refs"] == [approval_id]
    assert payload["approval"]["run_history"][0]["approved_capabilities"] == ["repo:write"]
    assert payload["approval"]["run_history"][0]["checkpoint_ref"] == result["checkpoint_ref"]
    assert payload["approval"]["run_history"][0]["resume_source"] == "checkpoint_state"
    assert payload["approval"]["run_history"][0]["resume_source_state_snapshot_ref"] == snapshot_ref
    assert payload["approval"]["resume_result"]["resumed_from_checkpoint_ref"] == "langgraph:exec-route-approval"
    assert payload["approval"]["resume_result"]["source_state_ref"] == "state://universal_employee_agent/exec-route-approval/governance_gate"
    assert payload["approval"]["resume_result"]["source_state_snapshot_ref"] == snapshot_ref
    assert payload["approval"]["resume_result"]["resume_source"] == "checkpoint_state"
    assert payload["approval"]["run_history"][0]["artifact_count"] >= 2
    assert payload["approval"]["run_history"][0]["evidence_count"] >= 2
    assert updated is not None
    mutation_reports = [report for report in updated.reports if report.report_type == "external_runtime_repo_mutation"]
    assert mutation_reports
    assert "Ticket-bound, approval-bound, and evidence-bound" in mutation_reports[-1].content
    assert f"Approval refs: {approval_id}." in mutation_reports[-1].content
    assert "Trace ref: .aiteamos/traces/exec-route-approval.jsonl." in mutation_reports[-1].content
    assert any("pytest::approved-runtime::passed" in evidence for evidence in mutation_reports[-1].evidence)

    sessions = client.get("/api/v1/runtime-executors/sessions?executor_id=claude_code")
    assert sessions.status_code == 200
    session_payload = next(item for item in sessions.json() if item["ticket_id"] == ticket.id)
    replay_response = client.get(f"/api/v1/runtime-executors/sessions/{quote(session_payload['session_key'], safe='')}")
    assert replay_response.status_code == 200
    replay = replay_response.json()
    assert replay["state_snapshots"][0]["source_state_snapshot_ref"] == snapshot_ref
    assert replay["state_snapshots"][0]["graph_state"]["execution_request"]["request_id"] == "exec-route-approval"
    assert replay["state_snapshots"][0]["state_summary"]["request_id"] == "exec-route-approval"
    assert replay["state_snapshots"][0]["state_summary"]["action"] == "implement_ticket"
    assert replay["state_snapshots"][0]["state_summary"]["current_step"] == "governance_gate"
    assert replay["state_snapshots"][0]["state_summary"]["error_count"] == 1
    assert replay["state_snapshots"][0]["state_delta"]["to"] == "governance_gate"
    assert "errors" in replay["state_snapshots"][0]["state_delta"]["changed_keys"]
    snapshot_transition = next(item for item in replay["state_transitions"] if item["source_kind"] == "state_snapshot")
    assert snapshot_transition["from"] == "execution_request"
    assert snapshot_transition["to"] == "governance_gate"
    assert snapshot_transition["source_state_snapshot_ref"] == snapshot_ref
    assert snapshot_transition["checkpoint_ref"] == "langgraph:exec-route-approval"
    assert "errors" in snapshot_transition["changed_keys"]
    timeline_events = [item["event"] for item in replay["timeline"]]
    assert "execution.state_snapshot" in timeline_events
    assert "execution.state_transition" in timeline_events
    assert "approval.run.completed" in timeline_events
    snapshot_item = next(item for item in replay["timeline"] if item["event"] == "execution.state_snapshot")
    assert snapshot_item["data"]["snapshot_schema"] == "execution_state_snapshot.v1"
    assert snapshot_item["data"]["checkpoint_ref"] == "langgraph:exec-route-approval"
    assert {"kind": "state", "ref": "state://universal_employee_agent/exec-route-approval/governance_gate"} in snapshot_item["refs"]
    transition_item = next(
        item
        for item in replay["timeline"]
        if item["event"] == "execution.state_transition" and item["data"]["source_kind"] == "state_snapshot"
    )
    assert transition_item["title"] == "execution_request -> governance_gate"
    assert transition_item["data"]["source_state_snapshot_ref"] == snapshot_ref
    run_item = next(item for item in replay["timeline"] if item["event"] == "approval.run.completed")
    assert run_item["data"]["approval_id"] == approval_id
    assert run_item["data"]["source_state_snapshot_ref"] == snapshot_ref
    assert run_item["data"]["resume_source"] == "checkpoint_state"
    assert {"kind": "state_snapshot", "ref": snapshot_ref} in run_item["refs"]

    retry = client.post(
        f"/api/v1/runtime-executors/claude_code/approvals/{approval_id}/run",
        json={
            "employee_id": "clara",
            "workspace_id": str(tmp_path),
            "runtime_config": {
                "binary_path": fake_cli,
                "working_dir": str(tmp_path),
                "model": "deepseek-reasoner",
            },
        },
    )
    assert retry.status_code == 200
    retry_payload = retry.json()
    assert retry_payload["request"]["request_id"].endswith("-attempt-2")
    assert retry_payload["approval"]["last_run_request_id"].endswith("-attempt-2")
    assert len(retry_payload["approval"]["run_history"]) == 2
    assert [item["status"] for item in retry_payload["approval"]["run_history"]] == ["completed", "completed"]


def test_rejected_runtime_approval_writes_ticket_and_employee_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Rejected runtime approval ticket",
            assigned_employee_id="alex",
            source_run_id="seed-runtime-rejected-route",
        )
    )
    source_request = ExecutionRequest(
        request_id="exec-route-rejected-approval",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(
            action="implement_ticket",
            arguments={"message": "Implement rejected route mutation."},
        ),
        capability_grants=["repo:write", "ticket:evidence:write"],
        permission_policy={"selected_ai_engine": "universal_employee_agent", "requested_runtime_executor": "claude_code"},
        approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
        expected_outputs={"report": True, "evidence": True, "artifacts": True},
        trace_context={"run_id": "exec-route-rejected-approval", "trace_ref": ".aiteamos/traces/exec-route-rejected-approval.jsonl"},
    )
    source_result = ExecutionResult(
        request_id=source_request.request_id,
        executor_id="universal_employee_agent",
        status="needs_approval",
        report="LangGraph approval interrupt: repo:write requires human approval before runtime dispatch.",
        output_ticket_id=ticket.id,
        executor_session_ref="lg-exec-route-rejected-approval",
        checkpoint_ref="langgraph:exec-route-rejected-approval",
        approval_requests=[
            {
                "kind": "repo_mutation",
                "ticket_id": ticket.id,
                "executor_id": "claude_code",
                "required_capability": "repo:write",
                "risk_level": "high",
                "reason": "External runtime repo mutation requires approval before execution.",
                "proposed_action": {
                    "action": "implement_ticket",
                    "ticket_id": ticket.id,
                    "executor_id": "claude_code",
                    "capability": "repo:write",
                },
                "checkpoint_ref": "langgraph:exec-route-rejected-approval",
                "executor_session_ref": "lg-exec-route-rejected-approval",
                "source_state_ref": "state://universal_employee_agent/exec-route-rejected-approval/governance_gate",
                "current_graph_node": "governance_gate",
            }
        ],
        errors=[{"reason": "repo_mutation_approval_required", "detail": "approval required"}],
    )
    ExecutionResultIngestionService(workspace_dir=tmp_path).ingest(source_request, source_result)
    client = TestClient(create_app())
    approval_id = client.get("/api/v1/runtime-executors/claude_code/approvals").json()[0]["id"]

    review = client.post(
        f"/api/v1/runtime-executors/claude_code/approvals/{approval_id}/review",
        json={"status": "rejected", "reviewer_employee_id": "clara", "reason": "Risk is too high for this run."},
    )

    updated = get_ticket(ticket.id)
    clara_work = employee_work_ledger("clara")
    assert review.status_code == 200
    assert review.json()["status"] == "rejected"
    assert review.json()["run_history"] == []
    assert updated is not None
    assert updated.status == "blocked"
    assert any(
        event.type == "status_changed"
        and event.data.get("to") == "blocked"
        and event.data.get("source_run_id") == approval_id
        for event in get_ticket_events(ticket.id)
    )
    rejected_reports = [report for report in updated.reports if report.report_type == "approval_rejected"]
    assert rejected_reports
    assert "No external runtime mutation was executed." in rejected_reports[-1].content
    assert clara_work.reports and clara_work.reports[0].report_type == "approval_rejected"


def test_runtime_approval_request_changes_and_evidence_reviews_write_ticket_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Runtime approval needs changes ticket",
            assigned_employee_id="alex",
            source_run_id="seed-runtime-changes-route",
        )
    )
    source_request = ExecutionRequest(
        request_id="exec-route-changes-approval",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(
            action="implement_ticket",
            arguments={"message": "Implement route mutation after changes."},
        ),
        capability_grants=["repo:write", "ticket:evidence:write"],
        permission_policy={"selected_ai_engine": "universal_employee_agent", "requested_runtime_executor": "claude_code"},
        approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
        expected_outputs={"report": True, "evidence": True, "artifacts": True},
        trace_context={"run_id": "exec-route-changes-approval", "trace_ref": ".aiteamos/traces/exec-route-changes-approval.jsonl"},
    )
    source_result = ExecutionResult(
        request_id=source_request.request_id,
        executor_id="universal_employee_agent",
        status="needs_approval",
        report="LangGraph approval interrupt: repo:write requires human approval before runtime dispatch.",
        output_ticket_id=ticket.id,
        executor_session_ref="lg-exec-route-changes-approval",
        checkpoint_ref="langgraph:exec-route-changes-approval",
        approval_requests=[
            {
                "kind": "repo_mutation",
                "ticket_id": ticket.id,
                "executor_id": "claude_code",
                "required_capability": "repo:write",
                "risk_level": "high",
                "reason": "External runtime repo mutation requires approval before execution.",
                "proposed_action": {
                    "action": "implement_ticket",
                    "ticket_id": ticket.id,
                    "executor_id": "claude_code",
                    "capability": "repo:write",
                },
                "checkpoint_ref": "langgraph:exec-route-changes-approval",
                "executor_session_ref": "lg-exec-route-changes-approval",
                "source_state_ref": "state://universal_employee_agent/exec-route-changes-approval/governance_gate",
                "current_graph_node": "governance_gate",
            }
        ],
        errors=[{"reason": "repo_mutation_approval_required", "detail": "approval required"}],
    )
    ExecutionResultIngestionService(workspace_dir=tmp_path).ingest(source_request, source_result)
    client = TestClient(create_app())
    approval_id = client.get("/api/v1/runtime-executors/claude_code/approvals").json()[0]["id"]

    changes = client.post(
        f"/api/v1/runtime-executors/claude_code/approvals/{approval_id}/review",
        json={"status": "request_changes", "reviewer_employee_id": "clara", "reason": "Please narrow the patch and add tests."},
    )
    changes_ticket = get_ticket(ticket.id)
    blocked_run = client.post(
        f"/api/v1/runtime-executors/claude_code/approvals/{approval_id}/run",
        json={"employee_id": "clara", "workspace_id": str(tmp_path), "ingest_result": True},
    )
    evidence = client.post(
        f"/api/v1/runtime-executors/claude_code/approvals/{approval_id}/review",
        json={"status": "ask_evidence", "reviewer_employee_id": "clara", "reason": "Attach test output before approval."},
    )

    updated = get_ticket(ticket.id)
    assert changes.status_code == 200
    assert changes.json()["status"] == "changes_requested"
    assert changes_ticket is not None
    assert changes_ticket.status == "waiting_changes"
    assert blocked_run.status_code == 200
    assert blocked_run.json()["result"]["status"] == "blocked"
    assert blocked_run.json()["result"]["errors"][0]["reason"] == "runtime_approval_not_approved"
    assert evidence.status_code == 200
    assert evidence.json()["status"] == "evidence_requested"
    assert updated is not None
    assert updated.status == "waiting_evidence"
    ticket_events = get_ticket_events(ticket.id)
    assert any(
        event.type == "status_changed"
        and event.data.get("to") == "waiting_changes"
        and event.data.get("source_run_id") == approval_id
        for event in ticket_events
    )
    assert any(
        event.type == "status_changed"
        and event.data.get("to") == "waiting_evidence"
        and event.data.get("source_run_id") == approval_id
        for event in ticket_events
    )
    changes_reports = [report for report in updated.reports if report.report_type == "approval_changes_requested"]
    evidence_reports = [report for report in updated.reports if report.report_type == "approval_evidence_requested"]
    assert changes_reports and "Please narrow the patch and add tests." in changes_reports[-1].content
    assert evidence_reports and "Attach test output before approval." in evidence_reports[-1].content
    assert "No external runtime mutation was executed." in evidence_reports[-1].content


def test_approved_cursor_http_runtime_run_uses_approval_ref_and_ingests_repo_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("CURSOR_API_KEY", "cursor-test-key")
    _use_local_ticket_backend()
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
                    "report": "Cursor approved runtime mutation executed.",
                    "artifacts": [
                        {
                            "kind": "repo_patch",
                            "changed_files": ["apps/dashboard/src/pages/assets/index.tsx"],
                            "diff_ref": "artifact://diff/cursor-approved-runtime.patch",
                        }
                    ],
                    "evidence": [{"kind": "test_evidence", "ref": "npm:test:assets-page:passed"}],
                    "usage": {"cursor_approved_steps": 3},
                }
            )

    monkeypatch.setattr(
        "aiteamos_api.read.runtime_executors.external_runtime_executor.httpx.AsyncClient",
        FakeAsyncClient,
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Approved Cursor runtime mutation",
            assigned_employee_id="alex",
            source_run_id="seed-cursor-approved-route",
        )
    )
    source_request = ExecutionRequest(
        request_id="exec-cursor-route-approval",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(
            action="implement_ticket",
            arguments={"message": "Implement approved dashboard mutation through Cursor."},
        ),
        capability_grants=["repo:write", "ticket:evidence:write"],
        permission_policy={"selected_ai_engine": "cursor", "selected_executor": "cursor"},
        approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
        expected_outputs={"report": True, "evidence": True, "artifacts": True},
        trace_context={"run_id": "exec-cursor-route-approval", "trace_ref": ".aiteamos/traces/exec-cursor-route-approval.jsonl"},
    )
    source_result = ExecutionResult(
        request_id=source_request.request_id,
        executor_id="cursor",
        status="needs_approval",
        report="Cursor repo mutation needs approval before execution.",
        output_ticket_id=ticket.id,
        approval_requests=[
            {
                "kind": "repo_mutation",
                "ticket_id": ticket.id,
                "executor_id": "cursor",
                "required_capability": "repo:write",
                "reason": "Cursor runtime repo mutation requires approval before execution.",
            }
        ],
        errors=[{"reason": "repo_mutation_approval_required", "detail": "approval required"}],
    )
    ExecutionResultIngestionService(workspace_dir=tmp_path).ingest(source_request, source_result)
    client = TestClient(create_app())

    approvals = client.get("/api/v1/runtime-executors/cursor/approvals")
    assert approvals.status_code == 200
    approval_id = approvals.json()[0]["id"]

    review = client.post(
        f"/api/v1/runtime-executors/cursor/approvals/{approval_id}/review",
        json={"status": "approved", "reviewer_employee_id": "clara", "reason": "Approved Cursor route mutation."},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "approved"

    run = client.post(
        f"/api/v1/runtime-executors/cursor/approvals/{approval_id}/run",
        json={
            "workspace_id": str(tmp_path),
            "runtime_config": {
                "api_base_url": "https://cursor.example",
                "http_endpoint_path": "/agent/implement",
                "api_key_env": "CURSOR_API_KEY",
                "model": "cursor-agent",
                "timeout_seconds": 33,
            },
        },
    )

    assert run.status_code == 200
    payload = run.json()
    result = payload["result"]
    updated = get_ticket(ticket.id)

    assert payload["ingested"] is True
    assert payload["request"]["approval_policy"]["approved_capabilities"] == ["repo:write"]
    assert payload["request"]["approval_policy"]["approval_refs"] == [approval_id]
    assert payload["request"]["permission_policy"]["runtime_config"]["cursor"]["http_endpoint_path"] == "/agent/implement"
    assert result["status"] == "completed"
    assert result["artifacts"][0]["kind"] == "external_runtime_http_execution"
    assert result["artifacts"][0]["repo_mutation"] is True
    assert result["artifacts"][0]["approval_refs"] == [approval_id]
    assert result["artifacts"][1]["changed_files"] == ["apps/dashboard/src/pages/assets/index.tsx"]
    assert result["evidence"][1]["ref"] == "npm:test:assets-page:passed"
    assert payload["approval"]["last_run_status"] == "completed"
    assert calls[0]["url"] == "https://cursor.example/agent/implement"
    assert calls[0]["headers"]["Authorization"] == "Bearer cursor-test-key"
    assert calls[0]["json"]["execution_request"]["approval_policy"]["approval_refs"] == [approval_id]
    assert calls[0]["json"]["execution_request"]["permission_policy"]["runtime_config"]["cursor"]["model"] == "cursor-agent"
    assert calls[0]["timeout"] == 33.0
    assert updated is not None
    mutation_reports = [report for report in updated.reports if report.report_type == "external_runtime_repo_mutation"]
    assert mutation_reports
    assert "Ticket-bound, approval-bound, and evidence-bound" in mutation_reports[-1].content
    assert "apps/dashboard/src/pages/assets/index.tsx" in mutation_reports[-1].content
    assert any("npm:test:assets-page:passed" in evidence for evidence in mutation_reports[-1].evidence)


def test_approved_openhands_http_runtime_run_uses_approval_ref_and_ingests_repo_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENHANDS_API_TOKEN", "openhands-test-key")
    _use_local_ticket_backend()
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
                    "report": "OpenHands approved runtime mutation executed.",
                    "artifacts": [
                        {
                            "kind": "repo_patch",
                            "changed_files": ["services/api/aiteamos_api/read/chat_routes.py"],
                            "diff_ref": "artifact://diff/openhands-approved-runtime.patch",
                        }
                    ],
                    "evidence": [{"kind": "test_evidence", "ref": "pytest::openhands-approved-runtime::passed"}],
                    "usage": {"openhands_approved_steps": 4},
                }
            )

    monkeypatch.setattr(
        "aiteamos_api.read.runtime_executors.external_runtime_executor.httpx.AsyncClient",
        FakeAsyncClient,
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Approved OpenHands runtime mutation",
            assigned_employee_id="alex",
            source_run_id="seed-openhands-approved-route",
        )
    )
    source_request = ExecutionRequest(
        request_id="exec-openhands-route-approval",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(
            action="implement_ticket",
            arguments={"message": "Implement approved API mutation through OpenHands."},
        ),
        capability_grants=["repo:write", "ticket:evidence:write"],
        permission_policy={"selected_ai_engine": "openhands", "selected_executor": "openhands"},
        approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
        expected_outputs={"report": True, "evidence": True, "artifacts": True},
        trace_context={
            "run_id": "exec-openhands-route-approval",
            "trace_ref": ".aiteamos/traces/exec-openhands-route-approval.jsonl",
        },
    )
    source_result = ExecutionResult(
        request_id=source_request.request_id,
        executor_id="openhands",
        status="needs_approval",
        report="OpenHands repo mutation needs approval before execution.",
        output_ticket_id=ticket.id,
        approval_requests=[
            {
                "kind": "repo_mutation",
                "ticket_id": ticket.id,
                "executor_id": "openhands",
                "required_capability": "repo:write",
                "reason": "OpenHands runtime repo mutation requires approval before execution.",
            }
        ],
        errors=[{"reason": "repo_mutation_approval_required", "detail": "approval required"}],
    )
    ExecutionResultIngestionService(workspace_dir=tmp_path).ingest(source_request, source_result)
    client = TestClient(create_app())

    approvals = client.get("/api/v1/runtime-executors/openhands/approvals")
    assert approvals.status_code == 200
    approval_id = approvals.json()[0]["id"]

    review = client.post(
        f"/api/v1/runtime-executors/openhands/approvals/{approval_id}/review",
        json={"status": "approved", "reviewer_employee_id": "clara", "reason": "Approved OpenHands route mutation."},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "approved"

    run = client.post(
        f"/api/v1/runtime-executors/openhands/approvals/{approval_id}/run",
        json={
            "workspace_id": str(tmp_path),
            "runtime_config": {
                "api_base_url": "https://openhands.example",
                "http_endpoint_path": "/api/agent/execute",
                "api_key_env": "OPENHANDS_API_TOKEN",
                "model": "deepseek-reasoner",
                "timeout_seconds": 44,
            },
        },
    )

    assert run.status_code == 200
    payload = run.json()
    result = payload["result"]
    updated = get_ticket(ticket.id)

    assert payload["ingested"] is True
    assert payload["request"]["approval_policy"]["approved_capabilities"] == ["repo:write"]
    assert payload["request"]["approval_policy"]["approval_refs"] == [approval_id]
    assert payload["request"]["permission_policy"]["runtime_config"]["openhands"]["http_endpoint_path"] == "/api/agent/execute"
    assert payload["request"]["permission_policy"]["runtime_config"]["openhands"]["model"] == "deepseek-reasoner"
    assert result["status"] == "completed"
    assert result["artifacts"][0]["kind"] == "external_runtime_http_execution"
    assert result["artifacts"][0]["repo_mutation"] is True
    assert result["artifacts"][0]["approval_refs"] == [approval_id]
    assert result["artifacts"][1]["changed_files"] == ["services/api/aiteamos_api/read/chat_routes.py"]
    assert result["evidence"][1]["ref"] == "pytest::openhands-approved-runtime::passed"
    assert payload["approval"]["last_run_status"] == "completed"
    assert calls[0]["url"] == "https://openhands.example/api/agent/execute"
    assert calls[0]["headers"]["Authorization"] == "Bearer openhands-test-key"
    assert calls[0]["json"]["execution_request"]["approval_policy"]["approval_refs"] == [approval_id]
    assert calls[0]["json"]["execution_request"]["permission_policy"]["runtime_config"]["openhands"]["model"] == "deepseek-reasoner"
    assert calls[0]["timeout"] == 44.0
    assert updated is not None
    mutation_reports = [report for report in updated.reports if report.report_type == "external_runtime_repo_mutation"]
    assert mutation_reports
    assert "Ticket-bound, approval-bound, and evidence-bound" in mutation_reports[-1].content
    assert "services/api/aiteamos_api/read/chat_routes.py" in mutation_reports[-1].content
    assert any("pytest::openhands-approved-runtime::passed" in evidence for evidence in mutation_reports[-1].evidence)


def test_approved_opencode_cli_runtime_run_uses_approval_ref_and_ingests_repo_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    fake_cli = _write_fake_runtime(
        tmp_path / "opencode-compatible-approved-run",
        """#!/usr/bin/env python3
import json
import os
import sys
payload = json.loads(sys.stdin.read())
print(json.dumps({
    "report": "OpenCode approved runtime mutation executed by " + os.environ.get("AITEAMOS_EMPLOYEE_ID", ""),
    "artifacts": [{
        "kind": "repo_patch",
        "changed_files": ["apps/dashboard/src/pages/chat/index.tsx"],
        "diff_ref": "artifact://diff/opencode-approved-runtime.patch"
    }],
    "evidence": [{"kind": "test_evidence", "ref": "vitest::chat-page::passed"}],
    "usage": {"opencode_approved_steps": 2}
}))
""",
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Approved OpenCode runtime mutation",
            assigned_employee_id="alex",
            source_run_id="seed-opencode-approved-route",
        )
    )
    source_request = ExecutionRequest(
        request_id="exec-opencode-route-approval",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(
            action="implement_ticket",
            arguments={"message": "Implement approved dashboard mutation through OpenCode."},
        ),
        capability_grants=["repo:write", "ticket:evidence:write"],
        permission_policy={"selected_ai_engine": "opencode", "selected_executor": "opencode"},
        approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
        expected_outputs={"report": True, "evidence": True, "artifacts": True},
        trace_context={"run_id": "exec-opencode-route-approval", "trace_ref": ".aiteamos/traces/exec-opencode-route-approval.jsonl"},
    )
    source_result = ExecutionResult(
        request_id=source_request.request_id,
        executor_id="opencode",
        status="needs_approval",
        report="OpenCode repo mutation needs approval before execution.",
        output_ticket_id=ticket.id,
        approval_requests=[
            {
                "kind": "repo_mutation",
                "ticket_id": ticket.id,
                "executor_id": "opencode",
                "required_capability": "repo:write",
                "reason": "OpenCode runtime repo mutation requires approval before execution.",
            }
        ],
        errors=[{"reason": "repo_mutation_approval_required", "detail": "approval required"}],
    )
    ExecutionResultIngestionService(workspace_dir=tmp_path).ingest(source_request, source_result)
    client = TestClient(create_app())

    approvals = client.get("/api/v1/runtime-executors/opencode/approvals")
    assert approvals.status_code == 200
    approval_id = approvals.json()[0]["id"]

    review = client.post(
        f"/api/v1/runtime-executors/opencode/approvals/{approval_id}/review",
        json={"status": "approved", "reviewer_employee_id": "clara", "reason": "Approved OpenCode route mutation."},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "approved"

    run = client.post(
        f"/api/v1/runtime-executors/opencode/approvals/{approval_id}/run",
        json={
            "workspace_id": str(tmp_path),
            "runtime_config": {
                "binary_path": fake_cli,
                "working_dir": str(tmp_path),
                "model": "deepseek-reasoner",
                "api_base_url": "https://api.deepseek.com",
                "api_key_env": "",
            },
        },
    )

    assert run.status_code == 200
    payload = run.json()
    result = payload["result"]
    updated = get_ticket(ticket.id)

    assert payload["ingested"] is True
    assert payload["request"]["employee_id"] == "alex"
    assert payload["request"]["approval_policy"]["approved_capabilities"] == ["repo:write"]
    assert payload["request"]["approval_policy"]["approval_refs"] == [approval_id]
    assert payload["request"]["permission_policy"]["runtime_config"]["opencode"]["model"] == "deepseek-reasoner"
    assert result["status"] == "completed"
    assert result["artifacts"][0]["kind"] == "external_runtime_cli_execution"
    assert result["artifacts"][0]["repo_mutation"] is True
    assert result["artifacts"][0]["approval_refs"] == [approval_id]
    assert result["artifacts"][1]["changed_files"] == ["apps/dashboard/src/pages/chat/index.tsx"]
    assert result["evidence"][1]["ref"] == "vitest::chat-page::passed"
    assert payload["approval"]["last_run_status"] == "completed"
    assert updated is not None
    mutation_reports = [report for report in updated.reports if report.report_type == "external_runtime_repo_mutation"]
    assert mutation_reports
    assert "Ticket-bound, approval-bound, and evidence-bound" in mutation_reports[-1].content
    assert f"Approval refs: {approval_id}." in mutation_reports[-1].content
    assert "apps/dashboard/src/pages/chat/index.tsx" in mutation_reports[-1].content
    assert any("vitest::chat-page::passed" in evidence for evidence in mutation_reports[-1].evidence)


def test_approved_cli_runtime_run_records_ingestion_blocker_without_success_report(tmp_path, monkeypatch):
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    fake_cli = _write_fake_runtime(
        tmp_path / "claude-code-compatible-missing-evidence",
        """#!/usr/bin/env python3
import json
import sys
json.loads(sys.stdin.read())
print(json.dumps({
    "report": "Runtime returned a patch but forgot test evidence.",
    "artifacts": [{
        "kind": "repo_patch",
        "changed_files": ["services/api/aiteamos_api/read/execution_approval_service.py"],
        "diff_ref": "artifact://diff/missing-evidence.patch"
    }],
    "evidence": []
}))
""",
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Approved runtime missing evidence",
            assigned_employee_id="alex",
            source_run_id="seed-runtime-missing-evidence",
        )
    )
    source_request = ExecutionRequest(
        request_id="exec-missing-evidence-approval",
        workspace_id=str(tmp_path),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(
            action="implement_ticket",
            arguments={"message": "Implement approved mutation but require evidence."},
        ),
        capability_grants=["repo:write", "ticket:evidence:write"],
        permission_policy={"selected_ai_engine": "claude_code", "selected_executor": "claude_code"},
        approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
        expected_outputs={"report": True, "evidence": True, "artifacts": True},
        trace_context={
            "run_id": "exec-missing-evidence-approval",
            "trace_ref": ".aiteamos/traces/exec-missing-evidence-approval.jsonl",
        },
    )
    source_result = ExecutionResult(
        request_id=source_request.request_id,
        executor_id="claude_code",
        status="needs_approval",
        report="External repo mutation needs approval before execution.",
        output_ticket_id=ticket.id,
        approval_requests=[
            {
                "kind": "repo_mutation",
                "ticket_id": ticket.id,
                "executor_id": "claude_code",
                "required_capability": "repo:write",
                "reason": "External runtime repo mutation requires approval before execution.",
            }
        ],
        errors=[{"reason": "repo_mutation_approval_required", "detail": "approval required"}],
    )
    ExecutionResultIngestionService(workspace_dir=tmp_path).ingest(source_request, source_result)
    client = TestClient(create_app())

    approvals = client.get("/api/v1/runtime-executors/claude_code/approvals")
    assert approvals.status_code == 200
    approval_id = approvals.json()[0]["id"]

    review = client.post(
        f"/api/v1/runtime-executors/claude_code/approvals/{approval_id}/review",
        json={"status": "approved", "reviewer_employee_id": "clara", "reason": "Approved for missing evidence guard."},
    )
    assert review.status_code == 200

    run = client.post(
        f"/api/v1/runtime-executors/claude_code/approvals/{approval_id}/run",
        json={
            "workspace_id": str(tmp_path),
            "runtime_config": {
                "binary_path": fake_cli,
                "working_dir": str(tmp_path),
            },
        },
    )

    assert run.status_code == 200
    payload = run.json()
    updated = get_ticket(ticket.id)

    assert payload["ingested"] is False
    assert "test evidence" in payload["ingestion_blocker"]
    assert payload["approval"]["last_run_status"] == "blocked"
    assert "test evidence" in payload["approval"]["last_ingestion_blocker"]
    assert payload["result"]["errors"][-1]["reason"] == "repo_mutation_test_evidence_required"
    assert updated is not None
    mutation_reports = [report for report in updated.reports if report.report_type == "external_runtime_repo_mutation"]
    assert not mutation_reports
