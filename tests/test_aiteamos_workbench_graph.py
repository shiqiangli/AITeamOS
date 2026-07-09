from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from aiteamos_api.agents import aiteamos_workbench_graph
from aiteamos_api.agents.workbench import approval_fixture_graph
from aiteamos_api.agents.workbench.nodes.approval import route_after_workbench_state, should_interrupt_for_approval
from aiteamos_api.agents.workbench.nodes.response import final_response, update_workbench_state
from aiteamos_api.read import asset_candidate_service, memory_service
from aiteamos_api.read.asset_candidate_service import AssetCandidateReviewRequest
from aiteamos_api.read.chat_governance_service import ChatGovernanceService
from aiteamos_api.read.execution_approval_service import (
    ExecutionApprovalReviewRequest,
    get_execution_approval,
    list_execution_approvals,
    review_execution_approval,
)
from aiteamos_api.read.execution_contract import ExecutionRequest, ExecutionResult
from aiteamos_api.read.execution_dispatch_service import ExecutionDispatchService
from aiteamos_api.read.execution_result_ingestion_service import ExecutionResultIngestionService
from aiteamos_api.read.workbench_runtime_context_service import WorkbenchRuntimeContextService
from aiteamos_api.read.ticket_service import (
    TicketBackendSettingsUpdateRequest,
    TicketCreateRequest,
    TicketReportRequest,
    TicketStateTransitionRequest,
    add_ticket_report,
    get_ticket,
    create_ticket,
    transition_ticket_state,
    update_ticket_backend_settings,
)
from aiteamos_api.read.ticket_loop_service import (
    TicketAutonomousLoopService,
    TicketLoopPolicyUpdateRequest,
    TicketLoopQueueWorker,
    TicketLoopQueueWorkerControlRequest,
    update_ticket_loop_policy,
)


def _use_local_ticket_backend() -> None:
    update_ticket_backend_settings(
        TicketBackendSettingsUpdateRequest(mode="local_file", local_file_path=".aiteamos/tickets/index.json")
    )


def _create_fixture_ticket() -> str:
    ticket = create_ticket(
        TicketCreateRequest(
            title="Approval fixture dogfood Ticket",
            description="Deterministic LangGraph approval fixture for AITeamOS Workbench dogfood.",
            ticket_type="rd",
            assigned_employee_id="clara",
            assigned_role="AI Team OS Manager",
            source_thread_id="employee-clara-approval-fixture",
            source_run_id="fixture-needs-approval",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    return ticket.id


def _write_alex_profile(tmp_path) -> None:
    employees_dir = tmp_path / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True, exist_ok=True)
    (employees_dir / "alex.yaml").write_text(
        "\n".join(
            [
                "id: alex",
                "display_name: Alex",
                "kind: ai",
                "role: AI RD / Implementer",
                "summary: Runtime implementation owner.",
                "skills:",
                "  - runtime-engineering",
                "  - backend-api-implementation",
                "capability_tags:",
                "  - runtime",
                "  - backend-api-implementation",
                "permission_policy:",
                "  permissions:",
                "    - repo:read",
                "    - repo:write",
                "handoff_policy:",
                "  can_receive_handoffs: true",
                "  accepts_lanes:",
                "    - rd",
                "  preferred_lanes:",
                "    - rd",
                "current_load:",
                "  active_ticket_count: 0",
                "  status: available",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_workbench_approval_route_node_detects_pending_approval() -> None:
    state = {
        "approval_requests": [{"approval_ref": "approval-route-1", "required_capability": "repo:write"}],
        "runtime_status": {"status": "needs_approval"},
    }

    assert should_interrupt_for_approval(state) is True
    assert route_after_workbench_state(state) == "approval_interrupt"
    assert route_after_workbench_state({**state, "approval_ref": "approval-route-1"}) == "final_response"
    assert route_after_workbench_state({"runtime_status": {"status": "completed"}}) == "final_response"


def test_workbench_response_nodes_project_runtime_state() -> None:
    response = approval_fixture_graph.fixture_response(
        approval_requests=[
            {
                "approval_ref": "approval-response-1",
                "ticket_id": "rd-response-node",
                "required_capability": "repo:write",
            }
        ],
        reply="Approval is required.",
        run_id="run-response-node",
        status="needs_approval",
        ticket_id="rd-response-node",
    )
    response["run_metadata"]["scoped_context"]["setup_blockers"] = [
        {"reason": "provider_setup_blocker", "detail": "Provider is not configured."}
    ]

    projection = update_workbench_state(
        {
            "aiteamos_chat_response": response,
            "context_bundle": {"source": "langgraph_context_node"},
            "runtime_status": {"executor": "langgraph"},
            "workbench_panels": {"employee": False},
            "handoff_decision": {"target_employee_id": "alex", "lane": "rd"},
            "handoff_summary": {"status": "durable_handoff_recorded", "to_employee_id": "alex"},
            "ticket_handoff_refs": [{"kind": "ticket_handoff", "to_employee_id": "alex"}],
        }
    )
    final = final_response(
        {
            "aiteamos_chat_response": response,
            "final_response": "Projected final response.",
            "runtime_status": projection["runtime_status"],
            "approval_requests": projection["approval_requests"],
            "provider_blockers": projection["provider_blockers"],
            "handoff_decision": projection["handoff_decision"],
            "handoff_summary": projection["handoff_summary"],
            "ticket_handoff_refs": projection["ticket_handoff_refs"],
        }
    )

    assert projection["active_ticket"]["id"] == "rd-response-node"
    assert projection["ticket_binding"]["ticket_id"] == "rd-response-node"
    assert projection["approval_requests"][0]["approval_ref"] == "approval-response-1"
    assert projection["provider_blockers"][0]["reason"] == "provider_setup_blocker"
    assert projection["handoff_decision"]["target_employee_id"] == "alex"
    assert projection["handoff_summary"]["status"] == "durable_handoff_recorded"
    assert projection["ticket_handoff_refs"][0]["to_employee_id"] == "alex"
    assert projection["workbench_panels"]["approval"] is True
    assert projection["workbench_panels"]["provider_blockers"] is True
    assert projection["runtime_status"]["current_node"] == "update_workbench_state"
    assert projection["runtime_status"]["status"] == "needs_approval"
    assert isinstance(final["messages"][0], AIMessage)
    assert final["messages"][0].content == "Projected final response."
    assert final["messages"][0].response_metadata["visible_response"]["display_state"] == "needs_approval"
    assert final["messages"][0].response_metadata["aiteamos"]["run_metadata"]["visible_response"]["blocked_reason"] == "Provider is not configured."
    assert final["runtime_status"]["current_node"] == "final_response"
    assert final["runtime_status"]["status"] == "needs_approval"


@pytest.mark.asyncio
async def test_aiteamos_workbench_graph_emits_structured_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")
    _use_local_ticket_backend()

    state = await aiteamos_workbench_graph.graph.ainvoke(
        {
            "messages": [HumanMessage(content="List employees")],
            "thread_id": "employee-clara-default",
            "employee_id": "clara",
        },
        config={
            "configurable": {
                "thread_id": "employee-clara-default",
                "target_employee_id": "clara",
            }
        },
    )

    assert state["active_ticket"] is None
    assert state["employee_identity"]["summary"]["id"] == "clara"
    assert state["ticket_binding"]["mode"] == "none"
    assert state["context_bundle"]["source"] == "langgraph_context_node"
    assert state["action_plan"]["action"] == "list_employees"
    assert state["governance_summary"]["node"] == "governance_gate"
    assert state["governance_summary"]["action"] == "list_employees"
    assert state["execution_request"]["action_plan"]["action"] == "list_employees"
    assert state["execution_request"]["task_context"]["universal_context"]["summary"]["employee_id"] == "clara"
    assert state["execution_request"]["trace_context"]["graph_governance_node"] == "governance_gate"
    assert state["aiteamos_chat_response"]["run_id"] == state["execution_request"]["request_id"]
    assert state["execution_result"]["executor_id"] == "local_tool"
    assert state["execution_result"]["status"] == "completed"
    assert state["execution_summary"]["dispatch_node"] == "dispatch_runtime_executor"
    assert state["execution_summary"]["execution_contract"] == "ExecutionRequest/ExecutionResult"
    assert state["execution_summary"]["runtime_context_service"] == "WorkbenchRuntimeContextService"
    assert "compatibility_runtime" not in state["execution_summary"]
    assert state["execution_summary"]["ingestion_node"] == "ingest_ticket_report_evidence"
    assert state["approval_requests"] == []
    assert state["asset_proposal_summary"]["node"] == "propose_asset_candidates"
    assert state["runtime_status"]["executor_id"] == "local_tool"
    assert state["aiteamos_chat_response"]["run_metadata"]["execution"]["request_id"] == state["execution_request"]["request_id"]
    assistant_messages = [message for message in state["messages"] if isinstance(message, AIMessage)]
    assert any("我找到了" in message.content for message in assistant_messages)
    final_message = assistant_messages[-1]
    visible_response = final_message.response_metadata["visible_response"]
    assert visible_response["version"] == "chat_visible_response.v1"
    assert visible_response["display_state"] == "completed"
    assert visible_response["assistant_message"]["content"] == final_message.content
    assert final_message.response_metadata["aiteamos"]["run_id"] == state["aiteamos_chat_response"]["run_id"]
    assert state["aiteamos_chat_response"]["run_metadata"]["visible_response"]["assistant_message"]["content"] == final_message.content


@pytest.mark.asyncio
async def test_aiteamos_workbench_graph_records_employee_handoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")
    _use_local_ticket_backend()
    _write_alex_profile(tmp_path)
    ticket = create_ticket(
        TicketCreateRequest(
            title="Workbench handoff Ticket",
            description="Clara should hand backend runtime coordination to Alex.",
            ticket_type="rd",
            assigned_employee_id="clara",
            assigned_role="AI Team OS Manager",
            source_thread_id="employee-clara-handoff",
            source_run_id="seed-workbench-handoff",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    update_ticket_loop_policy(
        ticket.id,
        TicketLoopPolicyUpdateRequest(
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
                "require_validation_evidence": True,
                "asset_types": ["ticket_closeout", "solution"],
            },
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Graph should read Ticket loop policy before close/continue decision.",
        ),
        workspace_dir=tmp_path / ".aiteamos",
    )

    class HandoffExecutor:
        id = "universal_employee_agent"
        display_name = "Handoff Fixture"
        capabilities = {"answer_only"}

        async def run(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id=self.id,
                status="completed",
                report=(
                    "Prepared Employee handoff for Ticket "
                    f"{request.ticket_id}: clara -> alex. Reason: backend runtime work needs RD ownership."
                ),
                output_ticket_id=request.ticket_id,
                artifacts=[
                    {
                        "kind": "employee_handoff_request",
                        "ticket_id": request.ticket_id,
                        "from_employee_id": "clara",
                        "from_role": "AI Team OS Manager",
                        "to_employee_id": "alex",
                        "to_role": "AI RD / Implementer",
                        "content": "Goal asks for implementation or engineering work. Selected under handoff_policy.",
                        "lane": "rd",
                        "confidence": 0.82,
                        "policy": {"policy_aware": True, "score": 8, "active_ticket_count": 0, "load_status": "available"},
                        "provenance": {
                            "source_kind": "langgraph_handoff_decision",
                            "source_ref": request.request_id,
                            "scope_kind": "ticket",
                            "scope_ref": request.ticket_id,
                        },
                    }
                ],
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                tool_events=[
                    {
                        "event": "universal_agent.handoff.proposed",
                        "detail": "Universal Employee Agent proposed a governed Employee handoff.",
                        "data": {"ticket_id": request.ticket_id, "from_employee_id": "clara", "to_employee_id": "alex", "lane": "rd"},
                    }
                ],
            )

    service = ChatGovernanceService(
        workspace_dir=tmp_path / ".aiteamos",
        dispatch_service=ExecutionDispatchService(executors=[HandoffExecutor()]),
        ingestion_service=ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos"),
    )
    monkeypatch.setattr(WorkbenchRuntimeContextService, "chat_governance_service", lambda self: service)
    graph = aiteamos_workbench_graph.build_graph(checkpointer=InMemorySaver())

    state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content=f"Coordinate backend runtime loop for {ticket.id}")],
            "thread_id": "employee-clara-handoff",
            "employee_id": "clara",
            "ticket_key": ticket.id,
        },
        config={
            "configurable": {
                "thread_id": "employee-clara-handoff",
                "target_employee_id": "clara",
                "ticket_key": ticket.id,
            }
        },
    )

    updated = get_ticket(ticket.id)
    assert updated is not None
    assert updated.assigned_employee_id == "alex"
    assert any(event.type == "handoff_requested" for event in updated.events)
    assert any(report.report_type == "employee_handoff" for report in updated.reports)
    assert state["execution_request"]["action_plan"]["action"] == "answer_only"
    assert state["execution_result"]["learning_delta"]["employee_handoff"]["to_employee_id"] == "alex"
    assert state["handoff_decision"]["target_employee_id"] == "alex"
    assert state["handoff_decision"]["source"] == "execution_result_artifact"
    assert state["handoff_summary"]["node"] == "maybe_handoff_employee"
    assert state["handoff_summary"]["status"] == "durable_handoff_recorded"
    assert state["ticket_handoff_refs"][0]["to_employee_id"] == "alex"
    assert state["ticket_loop_summary"]["ticket_id"] == ticket.id
    assert state["ticket_loop_policy"]["source"] == "policy_registry"
    assert state["ticket_loop_policy"]["configured"] == {"sla": True, "recurrence": True, "closeout": True}
    assert state["ticket_loop_policy"]["sla"]["review_due_seconds"] == 7200
    assert state["ticket_loop_policy"]["recurrence"]["next_run_at"] == "2026-06-20T09:00:00+00:00"
    assert state["ticket_loop_policy"]["closeout"]["asset_types"] == ["ticket_closeout", "solution"]
    assert state["ticket_loop_decision"]["node"] == "close_or_continue_ticket_loop"
    assert state["ticket_loop_decision"]["action"] == "recurrence_scheduled"
    assert state["ticket_loop_decision"]["ticket_id"] == ticket.id
    assert state["selected_employee"]["id"] == "alex"
    assert state["workbench_panels"]["handoff"] is True
    assert state["workbench_panels"]["ticket_loop"] is True
    assert state["runtime_status"]["handoff_to_employee_id"] == "alex"
    assert any(
        isinstance(message, AIMessage) and "Prepared Employee handoff" in message.content
        for message in state["messages"]
    )


@pytest.mark.asyncio
async def test_aiteamos_workbench_graph_applies_closeout_decision_through_assets_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Workbench closeout Ticket",
            description="Validated Ticket closeout should propose governed Asset candidates from the graph.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_thread_id="employee-clara-closeout",
            source_run_id="seed-workbench-closeout",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content="Implemented the closeout-ready runtime behavior.",
            report_type="result",
            evidence=["pytest::workbench-closeout::result"],
            source_run_id="run-workbench-closeout-result",
        ),
    )
    transition_ticket_state(
        ticket.id,
        TicketStateTransitionRequest(
            status="validated",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            source_run_id="run-workbench-closeout-validated",
        ),
    )
    pre_graph_candidates = asset_candidate_service.list_asset_candidates(workspace_dir=tmp_path)
    assert {candidate.asset_type for candidate in pre_graph_candidates} == {"ticket_closeout", "solution"}
    update_ticket_loop_policy(
        ticket.id,
        TicketLoopPolicyUpdateRequest(
            closeout={
                "auto_propose_assets": True,
                "require_validation_evidence": False,
                "asset_types": ["ticket_closeout", "solution"],
            },
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Allow graph closeout proposal without validation evidence for this fixture.",
        ),
        workspace_dir=tmp_path / ".aiteamos",
    )

    class CloseoutExecutor:
        id = "universal_employee_agent"
        display_name = "Closeout Fixture"
        capabilities = {"answer_only"}

        async def run(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id=self.id,
                status="completed",
                report="Closeout policy inspection completed.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
            )

    service = ChatGovernanceService(
        workspace_dir=tmp_path / ".aiteamos",
        dispatch_service=ExecutionDispatchService(executors=[CloseoutExecutor()]),
        ingestion_service=ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos"),
    )
    monkeypatch.setattr(WorkbenchRuntimeContextService, "chat_governance_service", lambda self: service)
    graph = aiteamos_workbench_graph.build_graph(checkpointer=InMemorySaver())

    state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content=f"Inspect closeout readiness for {ticket.id}")],
            "thread_id": "employee-clara-closeout",
            "employee_id": "clara",
            "ticket_key": ticket.id,
        },
        config={
            "configurable": {
                "thread_id": "employee-clara-closeout",
                "target_employee_id": "clara",
                "ticket_key": ticket.id,
            }
        },
    )

    candidates = asset_candidate_service.list_asset_candidates(workspace_dir=tmp_path)
    closeout_candidates = [
        candidate for candidate in candidates if candidate.asset_type in {"ticket_closeout", "solution"}
    ]
    candidate_types = {candidate.asset_type for candidate in closeout_candidates}
    updated = get_ticket(ticket.id)

    assert state["ticket_loop_decision"]["action"] == "propose_closeout_assets"
    assert state["ticket_loop_decision"]["applied_action"]["kind"] == "closeout_asset_candidates"
    assert state["ticket_loop_decision"]["applied_action"]["status"] == "skipped"
    assert set(state["ticket_loop_decision"]["applied_action"]["candidate_ids"]) == {
        candidate.id for candidate in closeout_candidates
    }
    assert candidate_types == {"ticket_closeout", "solution"}
    assert {candidate.get("asset_type") for candidate in state["asset_candidates"]} >= {"ticket_closeout", "solution"}
    assert state["ticket_loop_policy"]["closeout"]["require_validation_evidence"] is False
    assert state["workbench_panels"]["assets"] is True
    assert updated is not None
    assert any(report.report_type == "ticket_closeout_candidates" for report in updated.reports)


@pytest.mark.asyncio
async def test_aiteamos_workbench_graph_auto_settles_closeout_assets_through_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Workbench auto settlement Ticket",
            description="Validated Ticket closeout should settle governed Assets from explicit policy.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            validation_employee_id="peter",
            validation_role="AI PV",
            source_thread_id="employee-clara-closeout-settlement",
            source_run_id="seed-workbench-closeout-settlement",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
        )
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="alex",
            reporter_role="AI RD / Implementer",
            content="Implemented the settlement-ready behavior.",
            report_type="result",
            evidence=["pytest::workbench-closeout-settlement::result"],
            source_run_id="run-workbench-closeout-settlement-result",
        ),
    )
    add_ticket_report(
        ticket.id,
        TicketReportRequest(
            reporter_employee_id="peter",
            reporter_role="AI PV",
            content="Validation passed for graph-driven closeout settlement.",
            report_type="validation",
            evidence=["pytest::workbench-closeout-settlement::validation"],
            source_run_id="run-workbench-closeout-settlement-validation",
        ),
    )
    transition_ticket_state(
        ticket.id,
        TicketStateTransitionRequest(
            status="validated",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            source_run_id="run-workbench-closeout-settlement-validated",
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
    memory_service.update_graphiti_settings(
        memory_service.GraphitiSettingsUpdateRequest(
            enabled=True,
            graph_database="neo4j",
            uri="bolt://localhost:7687",
            user="neo4j",
            group_id="aiteamos-test",
            llm_ai_engine="openai",
        )
    )
    update_ticket_loop_policy(
        ticket.id,
        TicketLoopPolicyUpdateRequest(
            closeout={
                "auto_propose_assets": True,
                "auto_settle_assets": True,
                "auto_approve_candidates": True,
                "project_graphiti": True,
                "project_relationships": False,
                "require_validation_evidence": True,
                "asset_types": ["ticket_closeout", "solution"],
            },
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            reason="Allow graph closeout settlement through explicit governed policy.",
        ),
        workspace_dir=tmp_path / ".aiteamos",
    )

    class CloseoutSettlementExecutor:
        id = "universal_employee_agent"
        display_name = "Closeout Settlement Fixture"
        capabilities = {"answer_only"}

        async def run(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id=self.id,
                status="completed",
                report="Closeout settlement policy inspection completed.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
            )

    service = ChatGovernanceService(
        workspace_dir=tmp_path / ".aiteamos",
        dispatch_service=ExecutionDispatchService(executors=[CloseoutSettlementExecutor()]),
        ingestion_service=ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos"),
    )
    monkeypatch.setattr(WorkbenchRuntimeContextService, "chat_governance_service", lambda self: service)
    graph = aiteamos_workbench_graph.build_graph(checkpointer=InMemorySaver())

    state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content=f"Inspect closeout settlement readiness for {ticket.id}")],
            "thread_id": "employee-clara-closeout-settlement",
            "employee_id": "clara",
            "ticket_key": ticket.id,
        },
        config={
            "configurable": {
                "thread_id": "employee-clara-closeout-settlement",
                "target_employee_id": "clara",
                "ticket_key": ticket.id,
            }
        },
    )

    records = asset_candidate_service.list_asset_records(workspace_dir=tmp_path)
    reviews = asset_candidate_service.list_asset_reviews(workspace_dir=tmp_path)
    updated = get_ticket(ticket.id)
    applied = state["ticket_loop_decision"]["applied_action"]

    assert state["ticket_loop_decision"]["action"] == "settle_closeout_assets"
    assert applied["kind"] == "closeout_settlement"
    assert applied["status"] == "projected"
    assert applied["review_status"] == "completed"
    assert applied["reviewed_count"] == 2
    assert len(applied["asset_ids"]) == 2
    assert set(applied["asset_ids"]) == {record.id for record in records}
    assert {item["status"] for item in applied["projection_statuses"]} == {"ingested"}
    assert {candidate.get("asset_type") for candidate in state["asset_candidates"]} == {"ticket_closeout", "solution"}
    assert not [
        blocker for blocker in state.get("provider_blockers", [])
        if blocker.get("reason") == "closeout_settlement_projection_blocked"
    ]
    assert {record.status for record in records} == {"approved"}
    assert {record.asset_type for record in records} == {"ticket_closeout", "solution"}
    assert all(record.provenance["graphiti_status"]["status"] == "ingested" for record in records)
    assert len(reviews) == 2
    assert {item["provenance"]["asset_type"] for item in FakeGraphiti.indexed_episodes} == {"ticket_closeout", "solution"}
    assert updated is not None
    assert len([report for report in updated.reports if report.report_type == "ticket_closeout_settlement"]) == 1


@pytest.mark.asyncio
async def test_aiteamos_workbench_graph_projects_ticket_loop_policy_actions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")
    _use_local_ticket_backend()
    ticket = create_ticket(
        TicketCreateRequest(
            title="Workbench policy action Ticket",
            description="Worker policy actions should appear in Workbench graph state.",
            ticket_type="ops",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            source_thread_id="employee-clara-policy-actions",
            source_run_id="seed-workbench-policy-actions",
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
            reason="Enable graph-visible Ticket loop policy actions.",
        ),
        workspace_dir=tmp_path / ".aiteamos",
    )

    class WorkerDispatch:
        async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id="universal_employee_agent",
                status="completed",
                report="Recurring worker run completed before Workbench projection.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
            )

    worker = TicketLoopQueueWorker(
        workspace_dir=tmp_path / ".aiteamos",
        service=TicketAutonomousLoopService(
            workspace_dir=tmp_path / ".aiteamos",
            dispatch_service=WorkerDispatch(),  # type: ignore[arg-type]
        ),
    )
    tick = await worker.tick(
        TicketLoopQueueWorkerControlRequest(
            interval_seconds=5,
            max_items=1,
            reason="Create policy action refs for Workbench graph projection.",
        )
    )
    assert [action.kind for action in tick.pump.policy_actions] == ["sla_escalation_handoff", "recurrence_auto_enqueued"]

    class PolicyActionExecutor:
        id = "universal_employee_agent"
        display_name = "Policy Action Fixture"
        capabilities = {"answer_only"}

        async def run(self, request: ExecutionRequest) -> ExecutionResult:
            return ExecutionResult(
                request_id=request.request_id,
                executor_id=self.id,
                status="completed",
                report="Policy actions inspected.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
            )

    service = ChatGovernanceService(
        workspace_dir=tmp_path / ".aiteamos",
        dispatch_service=ExecutionDispatchService(executors=[PolicyActionExecutor()]),
        ingestion_service=ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos"),
    )
    monkeypatch.setattr(WorkbenchRuntimeContextService, "chat_governance_service", lambda self: service)
    graph = aiteamos_workbench_graph.build_graph(checkpointer=InMemorySaver())

    state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content=f"Inspect Ticket loop policy actions for {ticket.id}")],
            "thread_id": "employee-clara-policy-actions",
            "employee_id": "clara",
            "ticket_key": ticket.id,
        },
        config={
            "configurable": {
                "thread_id": "employee-clara-policy-actions",
                "target_employee_id": "clara",
                "ticket_key": ticket.id,
            }
        },
    )

    assert [action["kind"] for action in state["ticket_loop_policy_actions"]] == [
        "sla_escalation_handoff",
        "recurrence_auto_enqueued",
    ]
    assert state["ticket_loop_decision"]["policy_action_count"] == 2
    assert state["ticket_loop_decision"]["policy_action_kinds"] == [
        "sla_escalation_handoff",
        "recurrence_auto_enqueued",
    ]
    assert any(ref["kind"] == "ticket_handoff" for ref in state["ticket_loop_decision"]["policy_action_refs"])
    assert any(ref["kind"] == "ticket_loop_queue" for ref in state["ticket_loop_decision"]["policy_action_refs"])
    assert any(ref["kind"] == "ticket_loop_run" for ref in state["ticket_loop_decision"]["policy_action_refs"])
    assert state["ticket_handoff_refs"][0]["source"] == "ticket_loop_policy_action"
    assert state["ticket_handoff_refs"][0]["to_employee_id"] == "clara"
    assert state["workbench_panels"]["handoff"] is True
    assert state["runtime_status"]["ticket_loop_policy_action_count"] == 2
    assert state["runtime_status"]["ticket_loop_policy_action_kinds"] == [
        "sla_escalation_handoff",
        "recurrence_auto_enqueued",
    ]


@pytest.mark.asyncio
async def test_aiteamos_workbench_graph_interrupts_for_direct_execution_approval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_CHAT_KERNEL_COMMANDS", "legacy")
    _use_local_ticket_backend()
    ticket_id = _create_fixture_ticket()

    class NeedsApprovalExecutor:
        id = "universal_employee_agent"
        display_name = "Needs Approval Fixture"
        capabilities = {"implement_ticket"}

        async def run(self, request: ExecutionRequest) -> ExecutionResult:
            approved_refs = request.approval_policy.get("approval_refs")
            if isinstance(approved_refs, list) and approved_refs:
                approval_ref = str(approved_refs[0])
                return ExecutionResult(
                    request_id=request.request_id,
                    executor_id=self.id,
                    status="completed",
                    report="Approved runtime mutation completed.",
                    output_ticket_id=request.ticket_id,
                    artifacts=[
                        {
                            "kind": "external_runtime_cli_execution",
                            "repo_mutation": True,
                            "executor_id": self.id,
                            "mode": "fixture",
                            "changed_files": ["services/api/example.py"],
                            "approval_refs": [approval_ref],
                            "trace_ref": str(request.trace_context.get("trace_ref") or ""),
                        }
                    ],
                    evidence=[
                        {
                            "kind": "test_evidence",
                            "ref": "pytest::fixture",
                            "summary": "test evidence for approved mutation",
                        }
                    ],
                    trace_ref=str(request.trace_context.get("trace_ref") or ""),
                    executor_session_ref=f"lg-{request.request_id}",
                    checkpoint_ref=f"langgraph:{request.request_id}",
                )
            approval_ref = f"approval-{request.request_id}-1"
            return ExecutionResult(
                request_id=request.request_id,
                executor_id=self.id,
                status="needs_approval",
                report="Approval is required before the runtime mutation.",
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                approval_requests=[
                    {
                        "approval_ref": approval_ref,
                        "kind": "repo_mutation",
                        "ticket_id": request.ticket_id,
                        "executor_id": self.id,
                        "required_capability": "repo:write",
                        "risk_level": "high",
                        "reason": "repo:write requires human approval.",
                        "checkpoint_ref": f"langgraph:{request.request_id}",
                        "executor_session_ref": f"lg-{request.request_id}",
                        "source_state_ref": f"state://aiteamos_workbench/{request.request_id}/governance_gate",
                        "current_graph_node": "governance_gate",
                    }
                ],
                errors=[{"reason": "repo_mutation_approval_required", "detail": "approval required"}],
            )

    service = ChatGovernanceService(
        workspace_dir=tmp_path / ".aiteamos",
        dispatch_service=ExecutionDispatchService(executors=[NeedsApprovalExecutor()]),
        ingestion_service=ExecutionResultIngestionService(workspace_dir=tmp_path / ".aiteamos"),
    )
    monkeypatch.setattr(WorkbenchRuntimeContextService, "chat_governance_service", lambda self: service)
    graph = aiteamos_workbench_graph.build_graph(checkpointer=InMemorySaver())
    config = {
        "configurable": {
            "thread_id": "employee-clara-approval",
            "target_employee_id": "clara",
            "ticket_key": ticket_id,
        }
    }
    first_state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content=f"Implement ticket {ticket_id} code change")],
            "thread_id": "employee-clara-approval",
            "employee_id": "clara",
            "ticket_key": ticket_id,
        },
        config=config,
    )

    interrupts = first_state["__interrupt__"]
    interrupt_value = interrupts[0].value
    assert interrupt_value["source"] == "aiteamos_workbench_graph"
    approval_ref = first_state["approval_requests"][0]["approval_ref"]
    assert interrupt_value["approval_ref"] == approval_ref
    assert interrupt_value["approval_requests"][0]["required_capability"] == "repo:write"
    assert first_state["execution_request"]["action_plan"]["action"] == "implement_ticket"
    assert first_state["governance_summary"]["node"] == "governance_gate"
    assert first_state["governance_summary"]["action"] == "implement_ticket"
    assert first_state["execution_summary"]["execution_contract"] == "ExecutionRequest/ExecutionResult"
    approvals = list_execution_approvals(workspace_dir=tmp_path, status="requested")
    assert [item.id for item in approvals] == [approval_ref]
    assert approvals[0].source_request["request_id"] == first_state["execution_request"]["request_id"]
    assert approvals[0].source_state_snapshot_ref
    assert "Approval is required" in first_state["final_response"]

    reviewed = review_execution_approval(
        workspace_dir=tmp_path,
        approval_id=approval_ref,
        review=ExecutionApprovalReviewRequest(
            status="approved",
            reviewer_employee_id="clara",
            reason="Approve fixture main graph resume.",
        ),
    )
    assert reviewed.status == "approved"

    resumed_state = await graph.ainvoke(
        Command(
            resume={
                "approval_ref": approval_ref,
                "approval_refs": [approval_ref],
                "approved_capabilities": ["repo:write"],
            }
        ),
        config=config,
    )

    assert resumed_state["approval_resume"]["status"] == "approved"
    assert resumed_state["governance_summary"]["approval_resume_status"] == "approved"
    assert resumed_state["runtime_status"]["status"] == "completed"
    assert resumed_state["execution_result"]["status"] == "completed"
    assert resumed_state["execution_result"]["artifacts"][0]["approval_refs"] == [approval_ref]
    assert resumed_state["approval_requests"] == []
    assert resumed_state["linked_assets"][0]["kind"] == "external_runtime_cli_execution"
    assert any(
        isinstance(message, AIMessage) and "Approved runtime mutation completed" in message.content
        for message in resumed_state["messages"]
    )


@pytest.mark.asyncio
async def test_aiteamos_workbench_approval_fixture_graph_supports_agent_server_resume(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    _use_local_ticket_backend()
    ticket_id = _create_fixture_ticket()

    graph = approval_fixture_graph.build_approval_fixture_graph(checkpointer=InMemorySaver())
    config = {
        "configurable": {
            "thread_id": "fixture-browser-approval-thread",
            "ticket_key": ticket_id,
        }
    }

    first_state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="Trigger deterministic approval fixture")],
            "ticket_key": ticket_id,
        },
        config=config,
    )

    assert first_state["runtime_status"]["status"] == "needs_approval"
    assert first_state["approval_requests"][0]["approval_ref"] == "approval-fixture-1"
    assert first_state["approval_requests"][0]["ticket_id"] == ticket_id
    assert first_state["approval_records"][0]["id"] == "approval-fixture-1"
    assert first_state["approval_records"][0]["status"] == "requested"
    assert first_state["approval_records"][0]["ticket_id"] == ticket_id
    assert first_state["approval_records"][0]["source_state_snapshot_ref"]
    assert first_state["__interrupt__"][0].value["approval_ref"] == "approval-fixture-1"
    assert first_state["__interrupt__"][0].value["ticket_id"] == ticket_id

    approvals = list_execution_approvals(workspace_dir=tmp_path, status="requested")
    assert [item.id for item in approvals] == ["approval-fixture-1"]
    assert approvals[0].ticket_id == ticket_id

    resumed_state = await graph.ainvoke(
        Command(
            resume={
                "approval_ref": "approval-fixture-1",
                "approval_refs": ["approval-fixture-1"],
                "approved_capabilities": ["repo:write"],
            }
        ),
        config=config,
    )

    assert resumed_state["runtime_status"]["status"] == "completed"
    assert resumed_state["runtime_status"]["ticket_report_id"].startswith("report-")
    assert resumed_state["approval_resume"]["approval_ref"] == "approval-fixture-1"
    assert resumed_state["approval_records"][0]["status"] == "approved"
    assert resumed_state["approval_requests"] == []
    assert resumed_state["linked_assets"][0]["ref"] == "artifact-approved-fixture"
    assert resumed_state["asset_candidates"][0]["kind"] == "memory_candidate"
    assert resumed_state["asset_candidates"][0]["candidate_id"].startswith("mem-")
    assert resumed_state["asset_candidates"][0]["source_ticket_id"] == ticket_id
    assert resumed_state["asset_candidates"][0]["source_report_id"] == resumed_state["runtime_status"]["ticket_report_id"]
    assert not resumed_state.get("provider_blockers")
    approval = get_execution_approval(workspace_dir=tmp_path, approval_id="approval-fixture-1")
    assert approval is not None
    assert approval.status == "approved"
    assert approval.ticket_id == ticket_id
    ticket = get_ticket(ticket_id)
    assert ticket is not None
    assert any(
        report.report_type == "approval_resumed" and "LangGraph approval resumed" in report.content
        for report in ticket.reports
    )
    assert any(
        isinstance(message, AIMessage) and message.content == "Approved fixture resume completed."
        for message in resumed_state["messages"]
    )


@pytest.mark.asyncio
async def test_approval_fixture_dogfoods_assets_graphiti_and_recall(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AITEAMOS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AITEAMOS_GRAPHITI_ENABLED", "true")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_URI", "bolt://localhost:7687")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_USER", "neo4j")
    monkeypatch.setenv("AITEAMOS_GRAPHITI_PASSWORD", "neo4j-test-password")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    _use_local_ticket_backend()
    ticket_id = _create_fixture_ticket()

    class FakeEpisodeType:
        message = "message"
        text = "text"

    class FakeEpisode:
        def __init__(self, uuid: str) -> None:
            self.uuid = uuid

    class FakeAddResult:
        def __init__(self, episode_id: str) -> None:
            self.episode = FakeEpisode(episode_id)

    class FakeSearchResult:
        def __init__(self, *, fact: str, episode_uuid: str) -> None:
            self.uuid = "graphiti-result-fixture-dogfood"
            self.source_node_uuid = self.uuid
            self.episode_uuid = episode_uuid
            self.fact = fact
            self.score = 0.99

    class FakeGraphiti:
        episodes: list[dict[str, str]] = []

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def build_indices_and_constraints(self):
            return None

        async def add_episode(self, **kwargs):
            episode_id = f"episode-fixture-dogfood-{len(self.episodes) + 1}"
            self.episodes.append(
                {
                    "episode_id": episode_id,
                    "name": str(kwargs.get("name") or ""),
                    "episode_body": str(kwargs.get("episode_body") or ""),
                }
            )
            return FakeAddResult(episode_id)

        async def search(self, query, **kwargs):
            durable_episode = next(
                (episode for episode in reversed(self.episodes) if episode["name"].startswith("AITeamOS durable asset")),
                self.episodes[-1],
            )
            return [
                FakeSearchResult(
                    fact=durable_episode["episode_body"],
                    episode_uuid=durable_episode["episode_id"],
                )
            ]

        async def close(self):
            return None

    monkeypatch.setattr(memory_service, "Graphiti", FakeGraphiti)
    monkeypatch.setattr(memory_service, "EpisodeType", FakeEpisodeType)

    graph = approval_fixture_graph.build_approval_fixture_graph(checkpointer=InMemorySaver())
    config = {
        "configurable": {
            "thread_id": "fixture-dogfood-thread",
            "ticket_key": ticket_id,
        }
    }

    first_state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="Trigger deterministic approval fixture")],
            "ticket_key": ticket_id,
        },
        config=config,
    )
    assert first_state["__interrupt__"][0].value["approval_ref"] == "approval-fixture-1"
    assert first_state["approval_records"][0]["status"] == "requested"
    assert first_state["approval_records"][0]["ticket_id"] == ticket_id
    assert first_state["approval_records"][0]["source_state_snapshot_ref"]

    resumed_state = await graph.ainvoke(
        Command(
            resume={
                "approval_ref": "approval-fixture-1",
                "approval_refs": ["approval-fixture-1"],
                "approved_capabilities": ["repo:write"],
            }
        ),
        config=config,
    )
    assert resumed_state["runtime_status"]["ticket_report_id"].startswith("report-")
    approval = get_execution_approval(workspace_dir=tmp_path, approval_id="approval-fixture-1")
    assert approval is not None
    assert approval.status == "approved"
    ticket = get_ticket(ticket_id)
    assert ticket is not None
    assert any(
        report.report_type == "approval_resumed" and "LangGraph approval resumed" in report.content
        for report in ticket.reports
    )

    memory_candidate_id = resumed_state["asset_candidates"][0]["candidate_id"]
    asset_candidate_id = resumed_state["asset_candidates"][0]["id"]
    memory_candidate = next(item for item in memory_service.list_memory_candidates() if item.id == memory_candidate_id)
    assert memory_candidate.status == "proposed"
    assert memory_candidate.provenance["source_ticket_id"] == ticket_id
    assert memory_candidate.provenance["source_report_id"] == resumed_state["runtime_status"]["ticket_report_id"]
    assert memory_candidate.provenance["source_run_id"] == f"fixture-approved-resume-{ticket_id}"

    reviewed = asset_candidate_service.review_asset_candidate(
        asset_candidate_id,
        AssetCandidateReviewRequest(
            status="approved",
            reviewer_employee_id="clara",
            reason="Dogfood approval proves fixture memory can become a governed AssetRecord.",
        ),
    )
    assert reviewed.asset is not None
    assert reviewed.asset.id == memory_candidate_id
    assert reviewed.asset.status == "approved"

    approved_memory = await memory_service.approve_memory_candidate(memory_candidate_id)
    assert approved_memory.status == "approved"
    assert approved_memory.graphiti_episode_id == "episode-fixture-dogfood-1"

    projected_asset = await asset_candidate_service.project_asset_record_to_graphiti(reviewed.asset.id)
    assert projected_asset.status == "ingested"
    assert projected_asset.ingested_asset is not None
    assert projected_asset.ingested_asset["episode_id"] == "episode-fixture-dogfood-2"

    recalled = await memory_service.search_memory(
        query="approval fixture durable asset",
        employee_id="clara",
        ticket_key=ticket_id,
        limit=5,
        include_graphiti=True,
    )
    graphiti_result = next(item for item in recalled.results if item.source == "graphiti")
    assert graphiti_result.provenance["asset_id"] == reviewed.asset.id
    assert graphiti_result.provenance["source_ticket_id"] == ticket_id
    assert graphiti_result.graphiti_episode_id == "episode-fixture-dogfood-2"

    recall_state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="Recall approved asset fixture")],
            "ticket_key": ticket_id,
        },
        config=config,
    )

    assert recall_state["runtime_status"]["status"] == "completed"
    assert recall_state["runtime_status"]["run_id"] == "fixture-asset-recall"
    assert recall_state["runtime_status"]["recalled_asset_count"] == 1
    assert recall_state["recalled_memory_refs"][0]["asset_id"] == reviewed.asset.id
    assert recall_state["recalled_memory_refs"][0]["source_ticket_id"] == ticket_id
    assert recall_state["recalled_memory_refs"][0]["graphiti_recalled"] is True
    assert recall_state["recalled_memory_refs"][0]["graphiti_episode_id"] == "episode-fixture-dogfood-2"
    assert recall_state["asset_candidates"][0]["id"] == asset_candidate_id
    assert recall_state["asset_candidates"][0]["review_state"] == "approved"
    assert any(
        event["kind"] == "asset_recall" and event["source_ref"] == reviewed.asset.id
        for event in recall_state["provenance_events"]
    )
    assert any(
        isinstance(message, AIMessage) and message.content == "Recalled approved fixture Asset from Assets registry."
        for message in recall_state["messages"]
    )
