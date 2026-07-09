"""LangGraph runtime adapter for AITeamOS execution requests."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ..ai_engine_config_store import ai_engine_secrets, load_ai_engine_config
from ..ai_engine_context import response_language_instruction
from ..ai_engine_errors import build_ai_engine_configuration_reply
from ..chat_kernel_permission_utils import command_access_rows
from ..ai_engine_runtime_config import AiEngineRuntimeConfig
from ..employee_handoff_service import choose_employee_for_goal
from ..execution_contract import ExecutionEvent, ExecutionRequest, ExecutionResult
from ..langchain_model_provider import LangChainModelProvider
from ..universal_agent_tools import UniversalAgentToolRegistry
from .base import blocked_result, utc_now

try:  # Keep lightweight dev checkouts bootable if sqlite checkpoint extra is absent.
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    aiosqlite = None  # type: ignore[assignment]
    AsyncSqliteSaver = None  # type: ignore[assignment]


class LangGraphExecutionState(TypedDict, total=False):
    execution_request: dict[str, Any]
    messages: list[dict[str, Any]]
    current_step: str
    tool_events: list[dict[str, Any]]
    tool_outputs: dict[str, Any]
    artifacts: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    approval_requests: list[dict[str, Any]]
    memory_candidates: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    usage: dict[str, Any]
    status: str
    loop_state: dict[str, Any]
    handoff_decision: dict[str, Any]
    approval_interrupt: dict[str, Any]
    final_report: str


class LangGraphExecutor:
    id = "langgraph"
    display_name = "LangGraph Executor"
    capabilities = {
        "answer_only",
        "create_ticket",
        "append_report",
        "record_validation",
        "record_failure",
        "request_validation",
        "request_human_review",
        "implement_ticket",
        "stream",
    }

    def __init__(
        self,
        *,
        async_client_factory: Any | None = None,
        workspace_dir: Path | None = None,
        model_provider: LangChainModelProvider | None = None,
    ) -> None:
        _ = async_client_factory  # Kept for constructor compatibility; model calls go through LangChainModelProvider.
        self._model_provider = model_provider or LangChainModelProvider()
        self._tools = UniversalAgentToolRegistry()
        self.workspace_dir = self._aiteamos_workspace_dir(workspace_dir or Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".")).resolve())
        self._checkpoint_connection: Any | None = None
        self._checkpoint_status: dict[str, Any] = {"mode": "uninitialized"}
        self._graph: Any | None = None

    async def health(self) -> dict:
        await self._ensure_graph()
        return {
            "executor_id": self.id,
            "status": "ready",
            "detail": "LangGraph executor is available for runtime-first dispatch.",
            "capabilities": sorted(self.capabilities),
            "checkpoint": self._checkpoint_status,
        }

    async def aclose(self) -> None:
        if self._checkpoint_connection is not None:
            await self._checkpoint_connection.close()
            self._checkpoint_connection = None
        self._graph = None
        self._checkpoint_status = {"mode": "uninitialized"}

    async def stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionEvent]:
        yield ExecutionEvent(event="started", request_id=request.request_id, data={"executor_id": self.id})
        result = await self.run(request)
        for evidence in result.evidence:
            yield ExecutionEvent(event="evidence_produced", request_id=request.request_id, data=evidence)
        for artifact in result.artifacts:
            yield ExecutionEvent(event="artifact_produced", request_id=request.request_id, data=artifact)
        if result.status == "blocked":
            yield ExecutionEvent(event="blocked", request_id=request.request_id, data={"errors": result.errors, "report": result.report})
        elif result.status == "failed":
            yield ExecutionEvent(event="error", request_id=request.request_id, data={"errors": result.errors})
        else:
            yield ExecutionEvent(event="delta", request_id=request.request_id, data={"text": result.report})
        yield ExecutionEvent(event="completed", request_id=request.request_id, data=result.model_dump(mode="json"))

    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        if request.action_plan.action not in self.capabilities:
            return blocked_result(
                request,
                executor_id=self.id,
                reason="unsupported_action",
                detail=f"LangGraphExecutor does not support action '{request.action_plan.action}'.",
            )

        setup_blockers = request.task_context.get("setup_blockers")
        if request.action_plan.action not in {"answer_only", "implement_ticket"} and isinstance(setup_blockers, list) and setup_blockers:
            return blocked_result(
                request,
                executor_id=self.id,
                reason="setup_blocker",
                detail=str(setup_blockers[0].get("detail") or setup_blockers[0].get("reason") or "Required setup is incomplete."),
            )

        if self._pre_graph_remote_answer_enabled() and request.action_plan.action == "answer_only":
            remote_result = await self._maybe_run_remote_answer(request)
            if remote_result is not None:
                return remote_result

        graph = await self._ensure_graph()
        started_at = utc_now()
        graph_config = {"configurable": {"thread_id": self._graph_thread_id(request)}}
        graph_input: LangGraphExecutionState | Command
        resume_checkpoint_state = (
            await graph.aget_state(graph_config)
            if self._should_resume_native_checkpoint(request)
            else None
        )
        if resume_checkpoint_state is not None and self._checkpoint_has_pending_interrupt(resume_checkpoint_state):
            graph_input = Command(resume=self._resume_command_value(request))
        else:
            graph_input = self._initial_graph_state(request)
        state: LangGraphExecutionState = await graph.ainvoke(graph_input, config=graph_config)
        checkpoint_state = await graph.aget_state(graph_config)
        state = self._apply_native_interrupt_result(state, request=request, checkpoint_state=checkpoint_state)
        finished_at = utc_now()
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status=str(state.get("status") or "completed"),
            report=str(state.get("final_report") or "Execution completed."),
            output_ticket_id=request.ticket_id,
            artifacts=list(state.get("artifacts") or []),
            evidence=list(state.get("evidence") or []),
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"lg-{request.request_id}",
            checkpoint_ref=f"langgraph:{request.request_id}",
            tool_events=list(state.get("tool_events") or []),
            approval_requests=list(state.get("approval_requests") or []),
            memory_candidates=list(state.get("memory_candidates") or []),
            errors=list(state.get("errors") or []),
            learning_delta={
                "action": request.action_plan.action,
                "executor": self.id,
                "source": "langgraph_executor",
                "tool_outputs": state.get("tool_outputs") or {},
                "approval_interrupt": state.get("approval_interrupt") or {},
                "loop_state": state.get("loop_state") or {},
                "current_graph_node": state.get("current_step") or "",
                "native_interrupts": self._snapshot_interrupts(checkpoint_state),
                "checkpoint": self._checkpoint_metadata(checkpoint_state),
                "checkpoint_status": self._checkpoint_status,
            },
            usage={
                **dict(state.get("usage") or {}),
                "runtime_steps": 4,
                "checkpoint_mode": self._checkpoint_status.get("mode") or "unknown",
                "universal_agent_tool_count": len(
                    [
                        event for event in list(state.get("tool_events") or [])
                        if str(event.get("event") or "").startswith("universal_agent.tool.")
                    ]
                ),
            },
            started_at=started_at,
            finished_at=finished_at,
        )

    async def _ensure_graph(self) -> Any:
        if self._graph is None:
            self._graph = self._build_graph(await self._build_checkpointer())
        return self._graph

    def _build_graph(self, checkpointer: Any):
        graph = StateGraph(LangGraphExecutionState)
        graph.add_node("load_request", self._load_request)
        graph.add_node("plan_runtime_steps", self._plan_runtime_steps)
        graph.add_node("read_context_tools", self._read_context_tools)
        graph.add_node("decide_handoff", self._decide_handoff)
        graph.add_node("governance_gate", self._governance_gate)
        graph.add_node("request_approval_interrupt", self._request_approval_interrupt)
        graph.add_node("resume_after_approval", self._resume_after_approval)
        graph.add_node("produce_result", self._produce_result)
        graph.add_edge(START, "load_request")
        graph.add_edge("load_request", "plan_runtime_steps")
        graph.add_edge("plan_runtime_steps", "read_context_tools")
        graph.add_edge("read_context_tools", "decide_handoff")
        graph.add_edge("decide_handoff", "governance_gate")
        graph.add_conditional_edges(
            "governance_gate",
            self._route_after_governance_gate,
            {
                "request_approval_interrupt": "request_approval_interrupt",
                "resume_after_approval": "resume_after_approval",
                "produce_result": "produce_result",
            },
        )
        graph.add_edge("request_approval_interrupt", "resume_after_approval")
        graph.add_edge("resume_after_approval", "produce_result")
        graph.add_edge("produce_result", END)
        return graph.compile(checkpointer=checkpointer)

    def _checkpoint_path(self) -> Path:
        return self.workspace_dir / "langgraph" / f"{self.id}_checkpoints.sqlite"

    def _aiteamos_workspace_dir(self, path: Path) -> Path:
        resolved = path.expanduser().resolve()
        if resolved.name == ".aiteamos":
            return resolved
        return resolved / ".aiteamos"

    async def _build_checkpointer(self) -> Any:
        if AsyncSqliteSaver is None or aiosqlite is None:
            self._checkpoint_status = {
                "mode": "memory_fallback",
                "detail": "langgraph-checkpoint-sqlite is not installed",
            }
            return InMemorySaver()

        path = self._checkpoint_path()
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        if self._checkpoint_connection is not None:
            await self._checkpoint_connection.close()
        self._checkpoint_connection = await aiosqlite.connect(path)
        saver = AsyncSqliteSaver(self._checkpoint_connection)
        await saver.setup()
        self._checkpoint_status = {"mode": "sqlite", "path": str(path)}
        return saver

    def _initial_graph_state(self, request: ExecutionRequest) -> LangGraphExecutionState:
        return {
            "execution_request": request.model_dump(mode="json"),
            "messages": [{"role": "user", "content": request.task_context.get("task_summary") or ""}],
            "current_step": "load_request",
            "tool_events": [],
            "tool_outputs": {},
            "artifacts": [],
            "evidence": [],
            "approval_requests": [],
            "memory_candidates": [],
            "errors": [],
            "usage": {},
            "status": "completed",
            "loop_state": self._initial_loop_state(request),
            "handoff_decision": {},
            "approval_interrupt": {},
        }

    def _graph_thread_id(self, request: ExecutionRequest) -> str:
        if request.trace_context.get("approval_resume"):
            source_request_id = str(request.trace_context.get("source_request_id") or "").strip()
            if source_request_id:
                return source_request_id
        return request.request_id

    def _should_resume_native_checkpoint(self, request: ExecutionRequest) -> bool:
        if not request.trace_context.get("approval_resume"):
            return False
        return bool(str(request.trace_context.get("source_request_id") or "").strip())

    def _resume_command_value(self, request: ExecutionRequest) -> dict[str, Any]:
        return {
            "approved": True,
            "execution_request": request.model_dump(mode="json"),
            "approval_refs": list(request.approval_policy.get("approval_refs") or []),
            "approved_capabilities": list(request.approval_policy.get("approved_capabilities") or []),
            "resume_checkpoint_state": request.task_context.get("resume_checkpoint_state")
            if isinstance(request.task_context.get("resume_checkpoint_state"), dict)
            else {},
            "trace_context": request.trace_context,
        }

    def _checkpoint_has_pending_interrupt(self, checkpoint_state: Any) -> bool:
        if self._snapshot_interrupts(checkpoint_state):
            return True
        next_nodes = getattr(checkpoint_state, "next", ()) or ()
        return bool(next_nodes)

    def _apply_native_interrupt_result(
        self,
        state: LangGraphExecutionState,
        *,
        request: ExecutionRequest,
        checkpoint_state: Any,
    ) -> LangGraphExecutionState:
        interrupt_items = self._interrupt_items_from_state(state) or self._snapshot_interrupts(checkpoint_state)
        if not interrupt_items:
            return state
        first = interrupt_items[0]
        approval = first.get("value") if isinstance(first.get("value"), dict) else {}
        if not approval:
            approval = state.get("approval_interrupt") if isinstance(state.get("approval_interrupt"), dict) else {}
        approval = self._approval_from_interrupt_payload(approval, request=request)
        current_events = list(state.get("tool_events") or [])
        current_errors = list(state.get("errors") or [])
        normalized_state = {key: value for key, value in dict(state).items() if key != "__interrupt__"}
        normalized_state["status"] = "needs_approval"
        normalized_state["approval_requests"] = [*list(state.get("approval_requests") or []), approval]
        normalized_state["tool_events"] = [
            *current_events,
            {
                "event": "langgraph.approval.interrupted",
                "detail": "LangGraph interrupted execution for governed human approval.",
                "data": {
                    "approval_request": approval,
                    "native_interrupt_id": first.get("id") or "",
                    "checkpoint_ref": approval["checkpoint_ref"],
                    "source_state_ref": approval["source_state_ref"],
                    "current_graph_node": approval["current_graph_node"],
                },
            },
        ]
        normalized_state["errors"] = [
            *current_errors,
            {"reason": "repo_mutation_approval_required", "detail": str(approval["reason"])},
        ]
        normalized_state["final_report"] = str(approval["reason"])
        normalized_state["current_step"] = "request_approval_interrupt"
        normalized_state["approval_interrupt"] = {
            **approval,
            "native_interrupt": True,
            "native_interrupt_id": first.get("id") or "",
        }
        return normalized_state

    def _approval_from_interrupt_payload(self, payload: dict[str, Any], *, request: ExecutionRequest) -> dict[str, Any]:
        return {
            "kind": str(payload.get("kind") or "repo_mutation"),
            "ticket_id": str(payload.get("ticket_id") or request.ticket_id or request.ticket_binding.ticket_id or ""),
            "executor_id": str(payload.get("executor_id") or self._target_runtime_executor(request.model_dump(mode="json"))),
            "required_capability": str(payload.get("required_capability") or "repo:write"),
            "risk_level": str(payload.get("risk_level") or "high"),
            "reason": str(payload.get("reason") or "Human approval is required."),
            "proposed_action": payload.get("proposed_action") if isinstance(payload.get("proposed_action"), dict) else {},
            "checkpoint_ref": str(payload.get("checkpoint_ref") or f"langgraph:{request.request_id}"),
            "executor_session_ref": str(payload.get("executor_session_ref") or f"lg-{request.request_id}"),
            "source_state_ref": str(payload.get("source_state_ref") or f"state://{self.id}/{request.request_id}/governance_gate"),
            "current_graph_node": str(payload.get("current_graph_node") or "governance_gate"),
        }

    def _interrupt_items_from_state(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        raw_items = state.get("__interrupt__") if isinstance(state, dict) else []
        return self._normalize_interrupt_items(raw_items)

    def _snapshot_interrupts(self, checkpoint_state: Any) -> list[dict[str, Any]]:
        return self._normalize_interrupt_items(getattr(checkpoint_state, "interrupts", ()) or ())

    def _normalize_interrupt_items(self, raw_items: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_items, (list, tuple)):
            return []
        items: list[dict[str, Any]] = []
        for item in raw_items:
            value = getattr(item, "value", None)
            interrupt_id = str(getattr(item, "id", "") or "")
            if isinstance(item, dict):
                value = item.get("value", value)
                interrupt_id = str(item.get("id") or interrupt_id)
            items.append({"id": interrupt_id, "value": value if isinstance(value, dict) else {}})
        return items

    def _checkpoint_metadata(self, checkpoint_state: Any) -> dict[str, Any]:
        config = getattr(checkpoint_state, "config", {}) or {}
        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        return {
            "thread_id": str(configurable.get("thread_id") or ""),
            "checkpoint_id": str(configurable.get("checkpoint_id") or ""),
            "checkpoint_ns": str(configurable.get("checkpoint_ns") or ""),
            "next": [str(item) for item in getattr(checkpoint_state, "next", ()) or ()],
        }

    async def _load_request(self, state: LangGraphExecutionState) -> LangGraphExecutionState:
        request = state["execution_request"]
        loop_state = dict(state.get("loop_state") or {})
        state["tool_events"] = [
            *list(state.get("tool_events") or []),
            {
                "event": "runtime.load_request",
                "executor_id": self.id,
                "action": request.get("action_plan", {}).get("action"),
                "data": {"loop_state": loop_state} if loop_state.get("loop_kind") else {},
            },
        ]
        state["current_step"] = "plan_runtime_steps"
        return state

    async def _plan_runtime_steps(self, state: LangGraphExecutionState) -> LangGraphExecutionState:
        request = state["execution_request"]
        action = request.get("action_plan", {}).get("action") or "answer_only"
        state["tool_events"] = [
            *list(state.get("tool_events") or []),
            {"event": "runtime.plan", "executor_id": self.id, "action": action},
        ]
        state["current_step"] = "read_context_tools"
        return state

    async def _read_context_tools(self, state: LangGraphExecutionState) -> LangGraphExecutionState:
        request = ExecutionRequest.model_validate(state["execution_request"])
        task_context = request.task_context if isinstance(request.task_context, dict) else {}
        query = str(task_context.get("task_summary") or "").strip()
        requested_tool_specs = [
            (
                "search_tickets",
                {
                    "query": query,
                    "employee_id": request.employee_id,
                    "limit": 5,
                },
            ),
            (
                "search_memory",
                {
                    "query": query,
                    "employee_id": request.employee_id,
                    "ticket_key": request.ticket_id,
                    "limit": 5,
                    "include_graphiti": True,
                },
            ),
            (
                "search_assets",
                {
                    "query": query,
                    "employee_id": request.employee_id,
                    "ticket_id": request.ticket_id,
                    "limit": 5,
                },
            ),
        ]
        available_tools = await asyncio.to_thread(self._tools.available_tools)
        available_tool_names = {
            str(tool.get("tool_name") or "")
            for tool in available_tools
            if isinstance(tool, dict) and str(tool.get("tool_name") or "").strip()
        }
        tool_specs = [
            (tool_name, tool_input)
            for tool_name, tool_input in requested_tool_specs
            if tool_name in available_tool_names
        ]
        tool_outputs = dict(state.get("tool_outputs") or {})
        tool_events = [
            *list(state.get("tool_events") or []),
            {
                "event": "runtime.load_tools",
                "executor_id": self.id,
                "detail": "LangGraph loaded Universal Agent tools from the governed capability registry.",
                "data": {
                    "source": "capability_registry",
                    "tool_count": len(available_tools),
                    "requested_tool_names": [tool_name for tool_name, _tool_input in requested_tool_specs],
                    "loaded_tool_names": [tool_name for tool_name, _tool_input in tool_specs],
                    "tools": available_tools,
                },
            },
        ]
        errors = list(state.get("errors") or [])
        for tool_name, tool_input in tool_specs:
            result = await self._tools.run(tool_name, tool_input, request=request)
            tool_outputs[tool_name] = result.output
            tool_events.append(result.event())
            errors.extend(result.errors)
        state["tool_outputs"] = tool_outputs
        state["tool_events"] = tool_events
        state["errors"] = errors
        state["current_step"] = "decide_handoff"
        return state

    async def _decide_handoff(self, state: LangGraphExecutionState) -> LangGraphExecutionState:
        request = state["execution_request"]
        action = str(request.get("action_plan", {}).get("action") or "answer_only")
        task_context = request.get("task_context") if isinstance(request.get("task_context"), dict) else {}
        employee_id = str(request.get("employee_id") or "")
        ticket_id = str(request.get("ticket_id") or "")
        if action not in {"answer_only", "append_report", "request_validation"} or employee_id != "clara" or not ticket_id:
            state["current_step"] = "produce_result"
            return state

        required_memory_scopes = (
            [
                str(item)
                for item in task_context.get("required_memory_scopes", [])
                if str(item).strip()
            ]
            if isinstance(task_context.get("required_memory_scopes"), list)
            else None
        )
        decision = choose_employee_for_goal(
            str(task_context.get("task_summary") or ""),
            task_context.get("employee_profiles") if isinstance(task_context.get("employee_profiles"), list) else [],
            current_employee_id=employee_id,
            required_memory_scopes=required_memory_scopes,
            risk_level=str(task_context.get("risk_level") or task_context.get("risk") or ""),
        )
        state["handoff_decision"] = decision
        if not decision.get("should_handoff"):
            state["current_step"] = "produce_result"
            return state

        artifact = {
            "kind": "employee_handoff_request",
            "ticket_id": ticket_id,
            "from_employee_id": employee_id,
            "from_role": str(task_context.get("employee", {}).get("role") or "") if isinstance(task_context.get("employee"), dict) else "",
            "to_employee_id": str(decision.get("target_employee_id") or ""),
            "to_role": str(decision.get("target_role") or ""),
            "content": str(decision.get("reason") or "Universal Employee Agent proposed a handoff."),
            "lane": str(decision.get("lane") or ""),
            "confidence": decision.get("confidence"),
            "policy": decision.get("policy") if isinstance(decision.get("policy"), dict) else {},
            "provenance": {
                "source_kind": "langgraph_handoff_decision",
                "source_ref": str(request.get("request_id") or ""),
                "scope_kind": "ticket",
                "scope_ref": ticket_id,
            },
        }
        state["artifacts"] = [*list(state.get("artifacts") or []), artifact]
        state["tool_events"] = [
            *list(state.get("tool_events") or []),
            {
                "event": "universal_agent.handoff.proposed",
                "detail": "Universal Employee Agent proposed a governed Employee handoff.",
                "data": {
                    "ticket_id": ticket_id,
                    "from_employee_id": employee_id,
                    "to_employee_id": artifact["to_employee_id"],
                    "to_role": artifact["to_role"],
                    "lane": artifact["lane"],
                    "confidence": artifact["confidence"],
                    "policy": artifact["policy"],
                    "provenance": artifact["provenance"],
                },
            },
        ]
        state["current_step"] = "produce_result"
        return state

    async def _governance_gate(self, state: LangGraphExecutionState) -> LangGraphExecutionState:
        request = state["execution_request"]
        action = str(request.get("action_plan", {}).get("action") or "answer_only")
        if action != "implement_ticket" or "repo:write" not in {str(item) for item in request.get("capability_grants", [])}:
            state["current_step"] = "produce_result"
            return state
        if self._has_repo_write_approval(request):
            state["current_step"] = "resume_after_approval"
            return state

        target_executor = self._target_runtime_executor(request)
        executor_session_ref = f"lg-{request.get('request_id')}"
        checkpoint_ref = f"langgraph:{request.get('request_id')}"
        source_state_ref = f"state://{self.id}/{request.get('request_id')}/governance_gate"
        ticket_id = str(request.get("ticket_id") or request.get("ticket_binding", {}).get("ticket_id") or "")
        proposed_action = {
            "action": action,
            "ticket_id": ticket_id,
            "executor_id": target_executor,
            "capability": "repo:write",
            "summary": str(request.get("task_context", {}).get("task_summary") or ""),
        }
        interrupt = {
            "source": "langgraph_governance_gate",
            "kind": "repo_mutation",
            "ticket_id": ticket_id,
            "executor_id": target_executor,
            "required_capability": "repo:write",
            "risk_level": "high",
            "reason": "LangGraph approval interrupt: repo:write requires human approval before runtime dispatch.",
            "proposed_action": proposed_action,
            "checkpoint_ref": checkpoint_ref,
            "executor_session_ref": executor_session_ref,
            "source_state_ref": source_state_ref,
            "current_graph_node": "governance_gate",
        }
        state["approval_interrupt"] = interrupt
        state["status"] = "needs_approval"
        state["current_step"] = "request_approval_interrupt"
        return state

    async def _request_approval_interrupt(self, state: LangGraphExecutionState) -> LangGraphExecutionState:
        interrupt_payload = state.get("approval_interrupt") or {}
        approval = {
            "kind": interrupt_payload.get("kind") or "repo_mutation",
            "ticket_id": interrupt_payload.get("ticket_id") or "",
            "executor_id": interrupt_payload.get("executor_id") or self.id,
            "required_capability": interrupt_payload.get("required_capability") or "repo:write",
            "risk_level": interrupt_payload.get("risk_level") or "high",
            "reason": interrupt_payload.get("reason") or "Human approval is required.",
            "proposed_action": (
                interrupt_payload.get("proposed_action") if isinstance(interrupt_payload.get("proposed_action"), dict) else {}
            ),
            "checkpoint_ref": interrupt_payload.get("checkpoint_ref") or "",
            "executor_session_ref": interrupt_payload.get("executor_session_ref") or "",
            "source_state_ref": interrupt_payload.get("source_state_ref") or "",
            "current_graph_node": interrupt_payload.get("current_graph_node") or "governance_gate",
        }
        resume_value = interrupt(approval)
        if isinstance(resume_value, dict) and isinstance(resume_value.get("execution_request"), dict):
            state["execution_request"] = resume_value["execution_request"]
        if isinstance(resume_value, dict):
            state["approval_interrupt"] = {**interrupt_payload, "resume_command": resume_value}
        state["tool_events"] = [
            *list(state.get("tool_events") or []),
            {
                "event": "langgraph.approval.resume_command",
                "detail": "LangGraph received a native resume command for governed approval.",
                "data": {
                    "approval_refs": resume_value.get("approval_refs") if isinstance(resume_value, dict) else [],
                    "approved_capabilities": resume_value.get("approved_capabilities") if isinstance(resume_value, dict) else [],
                    "checkpoint_ref": approval["checkpoint_ref"],
                    "source_state_ref": approval["source_state_ref"],
                    "current_graph_node": approval["current_graph_node"],
                },
            },
        ]
        state["current_step"] = "resume_after_approval"
        return state

    async def _resume_after_approval(self, state: LangGraphExecutionState) -> LangGraphExecutionState:
        request = state["execution_request"]
        state["tool_events"] = [
            *list(state.get("tool_events") or []),
            {
                "event": "langgraph.approval.resumed",
                "detail": "LangGraph resumed execution after governed approval.",
                "data": {
                    "approval_refs": request.get("approval_policy", {}).get("approval_refs") or [],
                    "approved_capabilities": request.get("approval_policy", {}).get("approved_capabilities") or [],
                    "resume_from_checkpoint_ref": request.get("trace_context", {}).get("resume_from_checkpoint_ref") or "",
                    "source_state_ref": request.get("trace_context", {}).get("source_state_ref") or "",
                    "current_graph_node": request.get("trace_context", {}).get("resume_graph_node") or "",
                },
            },
        ]
        state["current_step"] = "produce_result"
        return state

    def _route_after_governance_gate(self, state: LangGraphExecutionState) -> str:
        current_step = str(state.get("current_step") or "produce_result")
        if current_step in {"request_approval_interrupt", "resume_after_approval"}:
            return current_step
        return "produce_result"

    async def _produce_result(self, state: LangGraphExecutionState) -> LangGraphExecutionState:
        request = state["execution_request"]
        action_plan = request.get("action_plan", {})
        action = str(action_plan.get("action") or "answer_only")
        task_context = request.get("task_context", {})
        task_summary = str(task_context.get("task_summary") or "").strip()
        ticket_id = str(request.get("ticket_id") or "")
        employee_id = str(request.get("employee_id") or "")

        if action == "create_ticket":
            report = f"Prepared Ticket creation request for {employee_id}: {task_summary}"
            state["artifacts"] = [
                *list(state.get("artifacts") or []),
                {
                    "kind": "ticket_create_request",
                    "title": action_plan.get("arguments", {}).get("title") or task_summary[:120] or "New Ticket",
                    "description": action_plan.get("arguments", {}).get("description") or task_summary,
                    "ticket_type": action_plan.get("arguments", {}).get("ticket_type") or "",
                    "assigned_employee_id": action_plan.get("arguments", {}).get("assigned_employee_id") or employee_id,
                    "assigned_role": action_plan.get("arguments", {}).get("assigned_role") or "",
                    "validation_employee_id": action_plan.get("arguments", {}).get("validation_employee_id") or "",
                    "validation_role": action_plan.get("arguments", {}).get("validation_role") or "",
                    "knowledge_refs": action_plan.get("arguments", {}).get("knowledge_refs") or [],
                    "code_repository_ids": action_plan.get("arguments", {}).get("code_repository_ids") or [],
                    "acceptance_criteria": action_plan.get("arguments", {}).get("acceptance_criteria") or [],
                },
            ]
        elif action in {"append_report", "record_validation", "record_failure"}:
            report = action_plan.get("arguments", {}).get("content") or f"{employee_id} report: {task_summary}"
            evidence_kind = "validation_evidence" if action == "record_validation" else "execution_trace"
            report_type = (
                "validation" if action == "record_validation"
                else "validation_failed" if action == "record_failure"
                else str(action_plan.get("arguments", {}).get("report_type") or "progress")
            )
            state["evidence"] = [
                *list(state.get("evidence") or []),
                {"kind": evidence_kind, "ticket_id": ticket_id, "source": "langgraph", "summary": task_summary[:240]},
            ]
            state["artifacts"] = [
                *list(state.get("artifacts") or []),
                {
                    "kind": "ticket_report_request",
                    "ticket_id": ticket_id,
                    "content": report,
                    "report_type": report_type,
                    "reporter_employee_id": employee_id,
                    "evidence_refs": [task_summary[:240]] if task_summary else [],
                    "provenance": {
                        "source_kind": "langgraph_runtime",
                        "source_ref": request.get("request_id") or "",
                        "scope_kind": "ticket",
                        "scope_ref": ticket_id,
                    },
                },
            ]
        elif action == "request_validation":
            report = f"Requested validation for Ticket {ticket_id}: {task_summary}"
            validation_employee_id = str(action_plan.get("arguments", {}).get("validation_employee_id") or "")
            validation_role = str(action_plan.get("arguments", {}).get("validation_role") or "PV Validation")
            state["artifacts"] = [
                *list(state.get("artifacts") or []),
                {
                    "kind": "validation_request",
                    "ticket_id": ticket_id,
                    "validation_employee_id": validation_employee_id,
                    "validation_role": validation_role,
                    "content": report,
                    "actor_employee_id": employee_id,
                    "provenance": {
                        "source_kind": "langgraph_runtime",
                        "source_ref": request.get("request_id") or "",
                        "scope_kind": "ticket",
                        "scope_ref": ticket_id,
                    },
                },
            ]
            state["approval_requests"] = [
                *list(state.get("approval_requests") or []),
                {"kind": "validation_request", "ticket_id": ticket_id, "requested_by": employee_id},
            ]
        elif action == "request_human_review":
            report = action_plan.get("arguments", {}).get("content") or f"Human Review requested for Ticket {ticket_id}: {task_summary}"
            state["approval_requests"] = [
                *list(state.get("approval_requests") or []),
                {"kind": "human_review_request", "ticket_id": ticket_id, "requested_by": employee_id},
            ]
        elif action == "implement_ticket":
            target_executor = self._target_runtime_executor(request)
            approval_refs = request.get("approval_policy", {}).get("approval_refs") if isinstance(request.get("approval_policy"), dict) else []
            report = (
                f"Approved Ticket implementation request is ready for runtime executor {target_executor}. "
                "AITeamOS did not fake repository mutation inside LangGraph."
            )
            state["status"] = "partial"
            state["artifacts"] = [
                *list(state.get("artifacts") or []),
                {
                    "kind": "external_runtime_resume_request",
                    "ticket_id": ticket_id,
                    "executor_id": target_executor,
                    "approval_refs": approval_refs if isinstance(approval_refs, list) else [],
                    "checkpoint_ref": request.get("trace_context", {}).get("resume_from_checkpoint_ref") or "",
                    "source_state_ref": request.get("trace_context", {}).get("source_state_ref") or "",
                    "provenance": {
                        "source_kind": "langgraph_resume_after_approval",
                        "source_ref": request.get("request_id") or "",
                        "scope_kind": "ticket",
                        "scope_ref": ticket_id,
                    },
                },
            ]
        elif state.get("handoff_decision", {}).get("should_handoff"):
            decision = state.get("handoff_decision") or {}
            report = (
                "Prepared Employee handoff for Ticket "
                f"{ticket_id}: {employee_id} -> {decision.get('target_employee_id') or decision.get('target_role')}. "
                f"Reason: {decision.get('reason') or 'handoff requested'}"
            )
        else:
            remote_result = await self._maybe_run_agent_remote_answer(request, state.get("tool_outputs") or {})
            if remote_result is not None:
                state["tool_events"] = [
                    *list(state.get("tool_events") or []),
                    *remote_result.tool_events,
                ]
                state["errors"] = [
                    *list(state.get("errors") or []),
                    *remote_result.errors,
                ]
                state["usage"] = {
                    **dict(state.get("usage") or {}),
                    **remote_result.usage,
                }
                state["status"] = remote_result.status
                report = remote_result.report
            else:
                report = self._answer_only_report(request, task_summary, state.get("tool_outputs") or {})

        state["messages"] = [
            *list(state.get("messages") or []),
            AIMessage(content=report).model_dump(mode="json"),
        ]
        state["final_report"] = report
        if state.get("loop_state"):
            state["loop_state"] = {
                **dict(state.get("loop_state") or {}),
                "runtime_status": str(state.get("status") or "completed"),
                "current_graph_node": "produce_result",
                "next_stop_reason": self._loop_stop_reason_for_state(state),
            }
        return state

    def _initial_loop_state(self, request: ExecutionRequest) -> dict[str, Any]:
        trace_context = request.trace_context if isinstance(request.trace_context, dict) else {}
        loop_kind = str(trace_context.get("loop_kind") or "").strip()
        if not loop_kind:
            return {}
        validation_gate = trace_context.get("validation_gate") if isinstance(trace_context.get("validation_gate"), dict) else {}
        return {
            "loop_kind": loop_kind,
            "loop_step": self._loop_step(trace_context.get("loop_step")),
            "stop_condition": str(trace_context.get("stop_condition") or ""),
            "ticket_status_before": str(trace_context.get("ticket_status_before") or ""),
            "ticket_status_after": str(trace_context.get("ticket_status_after") or ""),
            "validation_gate": validation_gate,
            "thread_id": str(trace_context.get("thread_id") or ""),
        }

    def _loop_step(self, value: Any) -> int:
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return 1

    def _loop_stop_reason_for_state(self, state: LangGraphExecutionState) -> str:
        status = str(state.get("status") or "completed")
        if status == "needs_approval":
            return "approval_required"
        if status in {"blocked", "failed"}:
            return "blocked_or_failed"
        return "single_step_completed"

    def _answer_only_report(self, request: dict[str, Any], task_summary: str, tool_outputs: dict[str, Any] | None = None) -> str:
        employee = request.get("task_context", {}).get("employee", {})
        display_name = employee.get("display_name") or request.get("employee_id") or "Employee"
        skill_titles = employee.get("skill_titles")
        recalled_memories = request.get("task_context", {}).get("recalled_memories")
        skill_text = ""
        if isinstance(skill_titles, list) and skill_titles:
            skill_text = " Loaded skills: " + ", ".join(str(item) for item in skill_titles[:4] if str(item).strip()) + "."
        memory_text = ""
        if isinstance(recalled_memories, list) and recalled_memories:
            memory_count = len(recalled_memories)
            memory_text = f" Recalled {memory_count} local memory snippet(s)."
        tool_context_text = ""
        if isinstance(tool_outputs, dict) and tool_outputs:
            ticket_count = self._tool_output_count(tool_outputs, "search_tickets", "tickets")
            memory_tool_count = self._tool_output_count(tool_outputs, "search_memory", "memories")
            tool_context_text = f" Tool context: {ticket_count} ticket hit(s), {memory_tool_count} memory hit(s)."
        if task_summary:
            return f"{display_name} received the request. AITeamOS execution dispatch handled: {task_summary}{skill_text}{memory_text}{tool_context_text}"
        return f"{display_name} received the request. AITeamOS execution dispatch handled this turn.{skill_text}{memory_text}{tool_context_text}"

    def _tool_output_count(self, tool_outputs: dict[str, Any], tool_name: str, list_key: str) -> int:
        output = tool_outputs.get(tool_name) if isinstance(tool_outputs.get(tool_name), dict) else {}
        items = output.get(list_key) if isinstance(output.get(list_key), list) else []
        return len(items)

    def _target_runtime_executor(self, request: dict[str, Any]) -> str:
        policy = request.get("permission_policy") if isinstance(request.get("permission_policy"), dict) else {}
        requested = str(
            policy.get("requested_runtime_executor")
            or policy.get("target_runtime_executor")
            or policy.get("selected_executor")
            or policy.get("selected_ai_engine")
            or self.id
        ).strip()
        aliases = {
            "claude-code": "claude_code",
            "claude_agent": "claude_agent_sdk",
            "claude-agent-sdk": "claude_agent_sdk",
            "open-hands": "openhands",
            "open-code": "opencode",
        }
        return aliases.get(requested, requested) or self.id

    def _has_repo_write_approval(self, request: dict[str, Any]) -> bool:
        policy = request.get("approval_policy") if isinstance(request.get("approval_policy"), dict) else {}
        approved = policy.get("approved_capabilities")
        if isinstance(approved, list) and "repo:write" in {str(item) for item in approved}:
            return True
        approval_refs = policy.get("approval_refs")
        return isinstance(approval_refs, list) and bool(approval_refs)

    def _pre_graph_remote_answer_enabled(self) -> bool:
        return False

    def _agent_remote_answer_enabled(self) -> bool:
        return False

    async def _maybe_run_agent_remote_answer(
        self,
        request: dict[str, Any],
        tool_outputs: dict[str, Any] | None,
    ) -> ExecutionResult | None:
        if not self._agent_remote_answer_enabled():
            return None
        execution_request = ExecutionRequest.model_validate(request)
        task_context = {
            **execution_request.task_context,
            "universal_agent_tool_outputs": tool_outputs or {},
        }
        return await self._maybe_run_remote_answer(execution_request.model_copy(update={"task_context": task_context}))

    async def _maybe_run_remote_answer(self, request: ExecutionRequest) -> ExecutionResult | None:
        selected_engine = self._selected_engine(request)
        if selected_engine not in {"deepseek", "openai"}:
            return None

        runtime = self._remote_runtime(request)
        if runtime is None:
            return None
        if not runtime.remote_ai_engine_available(selected_engine):
            error = RuntimeError(f"{selected_engine} api key is not configured")
            timestamp = utc_now()
            return ExecutionResult(
                request_id=request.request_id,
                executor_id=self.id,
                status="blocked",
                report=build_ai_engine_configuration_reply(
                    user_message=str(request.action_plan.arguments.get("message") or request.task_context.get("task_summary") or ""),
                    ai_engine_id=selected_engine,
                    error=error,
                ),
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                errors=[{"reason": "ai_engine_configuration_blocker", "detail": str(error), "ai_engine": selected_engine}],
                usage={"runtime_steps": 1},
                started_at=timestamp,
                finished_at=timestamp,
            )

        started_at = utc_now()
        try:
            model_result = await self._model_provider.ainvoke(
                selected_engine=selected_engine,
                runtime=runtime,
                messages=self._chat_messages(request),
            )
            reply = model_result.content or f"{selected_engine.title()} AI Engine returned an empty response."
            provider_ref = model_result.provider_ref
            usage = model_result.usage
            event_id = f"ai_engine.{selected_engine}.completed"
        except Exception as exc:
            timestamp = utc_now()
            return ExecutionResult(
                request_id=request.request_id,
                executor_id=self.id,
                status="blocked",
                report=build_ai_engine_configuration_reply(
                    user_message=str(request.action_plan.arguments.get("message") or request.task_context.get("task_summary") or ""),
                    ai_engine_id=selected_engine,
                    error=RuntimeError(str(exc)),
                ),
                output_ticket_id=request.ticket_id,
                trace_ref=str(request.trace_context.get("trace_ref") or ""),
                executor_session_ref=f"lg-{request.request_id}",
                checkpoint_ref=f"langgraph:{request.request_id}",
                errors=[{"reason": "ai_engine_configuration_blocker", "detail": str(exc), "ai_engine": selected_engine}],
                usage={"runtime_steps": 1},
                started_at=started_at,
                finished_at=timestamp,
            )

        finished_at = utc_now()
        return ExecutionResult(
            request_id=request.request_id,
            executor_id=self.id,
            status="completed",
            report=reply,
            output_ticket_id=request.ticket_id,
            trace_ref=str(request.trace_context.get("trace_ref") or ""),
            executor_session_ref=f"lg-{request.request_id}",
            checkpoint_ref=f"langgraph:{request.request_id}",
            tool_events=[
                {
                    "event": event_id,
                    "detail": f"{selected_engine} AI Engine completed answer-only execution.",
                    "data": {
                        "ai_engine": selected_engine,
                        "model": provider_ref.get("model", ""),
                        "provider_ref": provider_ref,
                        "usage": usage,
                    },
                }
            ],
            learning_delta={"action": "answer_only", "executor": self.id, "source": "langchain_model_provider"},
            usage={"runtime_steps": 1, **usage},
            started_at=started_at,
            finished_at=finished_at,
        )

    def _chat_messages(self, request: ExecutionRequest) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self._system_prompt(request)},
            *self._recent_messages(request),
            {"role": "user", "content": str(request.task_context.get("task_summary") or "")},
        ]

    def _recent_messages(self, request: ExecutionRequest) -> list[dict[str, str]]:
        history = request.task_context.get("recent_messages")
        if not isinstance(history, list):
            return []
        messages: list[dict[str, str]] = []
        for item in history[-12:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            messages.append({"role": role, "content": content})
        return messages

    def _system_prompt(self, request: ExecutionRequest) -> str:
        employee = request.task_context.get("employee") if isinstance(request.task_context.get("employee"), dict) else {}
        display_name = str(employee.get("display_name") or request.employee_id or "Employee")
        role = str(employee.get("role") or "")
        summary = str(employee.get("summary") or "")
        skill_titles = employee.get("skill_titles") if isinstance(employee.get("skill_titles"), list) else []
        skill_ids = employee.get("skills") if isinstance(employee.get("skills"), list) else []
        permissions = employee.get("permissions") if isinstance(employee.get("permissions"), list) else []
        skill_rows = []
        for index, skill_id in enumerate(skill_ids):
            title = str(skill_titles[index]) if index < len(skill_titles) else str(skill_id)
            skill_rows.append(f"- {title} ({skill_id})")
        command_rows = command_access_rows([str(item) for item in permissions])
        allowed_commands = [str(row.get("id") or "") for row in command_rows if row.get("status") == "allowed"]
        recalled = request.task_context.get("recalled_memories")
        memory_count = len(recalled) if isinstance(recalled, list) else 0
        task_summary = str(request.task_context.get("task_summary") or "")
        tool_context = self._tool_context_prompt(request.task_context.get("universal_agent_tool_outputs"))
        return (
            f"You are {display_name} in AITeamOS.\n"
            f"Display name: {display_name}\n"
            f"Role: {role}\n"
            f"Summary: {summary}\n"
            "Agent context bundle:\n"
            "Skill context:\n"
            f"{chr(10).join(skill_rows) if skill_rows else '- none'}\n\n"
            "Capability and permission context:\n"
            f"- Raw permissions: {', '.join(str(item) for item in permissions) if permissions else 'none'}\n"
            f"- Allowed commands: {', '.join(command for command in allowed_commands if command) if allowed_commands else 'none'}\n\n"
            "Runtime policy:\n"
            "- Treat Kernel commands as governance capability facts, not proof that work already ran.\n"
            "AITeamOS is Ticket-flow-centered and Runtime-first. Answer concisely from the scoped task context.\n"
            f"Scoped recalled memories: {memory_count}.\n"
            "LangGraph read-tool context:\n"
            f"{tool_context}\n"
            f"{response_language_instruction(task_summary)}"
        )

    def _tool_context_prompt(self, value: Any) -> str:
        if not isinstance(value, dict) or not value:
            return "- none"
        rows: list[str] = []
        tickets = value.get("search_tickets", {}).get("tickets") if isinstance(value.get("search_tickets"), dict) else []
        if isinstance(tickets, list):
            for item in tickets[:5]:
                if not isinstance(item, dict):
                    continue
                rows.append(
                    "- Ticket "
                    f"{str(item.get('ticket_id') or '').strip()}: "
                    f"{str(item.get('title') or '').strip()} "
                    f"[{str(item.get('status') or '').strip()}]"
                )
        memories = value.get("search_memory", {}).get("memories") if isinstance(value.get("search_memory"), dict) else []
        if isinstance(memories, list):
            for item in memories[:5]:
                if not isinstance(item, dict):
                    continue
                rows.append(
                    "- Memory "
                    f"{str(item.get('memory_id') or '').strip()}: "
                    f"{str(item.get('content') or '').strip()[:180]}"
                )
        return "\n".join(row for row in rows if row.strip()) or "- none"

    def _selected_engine(self, request: ExecutionRequest) -> str:
        return str(
            request.permission_policy.get("selected_ai_engine")
            or request.task_context.get("approval_policy_summary", {}).get("selected_ai_engine")
            or ""
        ).strip()

    def _remote_runtime(self, request: ExecutionRequest) -> AiEngineRuntimeConfig | None:
        workspace = Path(str(request.workspace_id or "") or ".").resolve()
        settings_path = workspace / ".aiteamos" / "ai_engines.json"
        config = load_ai_engine_config(settings_path)
        return AiEngineRuntimeConfig(config=config, secrets=ai_engine_secrets(config))
