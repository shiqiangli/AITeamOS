"""LangGraph-native Agent Workbench graph for AITeamOS Chat.

This graph is the primary LangGraph entrypoint for the plan_v6 Chat Workbench.
It deliberately keeps durable product writes behind the existing AITeamOS
governance and ingestion path, while exposing Workbench-shaped state for the
frontend runtime.
"""

from typing import Any

from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import END, START, StateGraph

from aiteamos_api.agents.workbench.nodes.approval import (
    approval_interrupt as _approval_interrupt,
    route_after_governance as _route_after_governance,
    route_after_workbench_state as _route_after_workbench_state,
)
from aiteamos_api.agents.workbench.nodes.assets import propose_asset_candidates as _propose_asset_candidates
from aiteamos_api.agents.workbench.nodes.bootstrap import (
    bind_or_create_ticket as _bind_or_create_ticket,
    bootstrap_request as _bootstrap_request,
    execute_read_tools as _execute_read_tools,
)
from aiteamos_api.agents.workbench.nodes.context import (
    load_employee_identity as _load_employee_identity,
    retrieve_context as _retrieve_context,
)
from aiteamos_api.agents.workbench.nodes.execution import (
    dispatch_runtime_executor as _dispatch_runtime_executor_node,
    ingest_ticket_report_evidence as _ingest_ticket_report_evidence,
)
from aiteamos_api.agents.workbench.nodes.governance import governance_gate as _governance_gate
from aiteamos_api.agents.workbench.nodes.handoff import maybe_handoff_employee as _maybe_handoff_employee
from aiteamos_api.agents.workbench.nodes.planning import plan_next_action as _plan_next_action
from aiteamos_api.agents.workbench.nodes.response import (
    final_response as _final_response,
    update_workbench_state as _update_workbench_state,
)
from aiteamos_api.agents.workbench.nodes.ticket_loop import (
    close_or_continue_ticket_loop as _close_or_continue_ticket_loop,
)
from aiteamos_api.agents.workbench.state import AITeamOSWorkbenchState


async def _dispatch_runtime_executor(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    return await _dispatch_runtime_executor_node(
        state,
        config,
    )


def build_graph(checkpointer: Any | None = None):
    builder = StateGraph(AITeamOSWorkbenchState)
    builder.add_node("bootstrap_request", _bootstrap_request)
    builder.add_node("load_employee_identity", _load_employee_identity)
    builder.add_node("bind_or_create_ticket", _bind_or_create_ticket)
    builder.add_node("retrieve_context", _retrieve_context)
    builder.add_node("plan_next_action", _plan_next_action)
    builder.add_node("execute_read_tools", _execute_read_tools)
    builder.add_node("governance_gate", _governance_gate)
    builder.add_node("dispatch_runtime_executor", _dispatch_runtime_executor)
    builder.add_node("approval_interrupt", _approval_interrupt)
    builder.add_node("maybe_handoff_employee", _maybe_handoff_employee)
    builder.add_node("ingest_ticket_report_evidence", _ingest_ticket_report_evidence)
    builder.add_node("propose_asset_candidates", _propose_asset_candidates)
    builder.add_node("close_or_continue_ticket_loop", _close_or_continue_ticket_loop)
    builder.add_node("update_workbench_state", _update_workbench_state)
    builder.add_node("final_response", _final_response)
    builder.add_edge(START, "bootstrap_request")
    builder.add_edge("bootstrap_request", "load_employee_identity")
    builder.add_edge("load_employee_identity", "bind_or_create_ticket")
    builder.add_edge("bind_or_create_ticket", "retrieve_context")
    builder.add_edge("retrieve_context", "plan_next_action")
    builder.add_edge("plan_next_action", "execute_read_tools")
    builder.add_edge("execute_read_tools", "governance_gate")
    builder.add_conditional_edges(
        "governance_gate",
        _route_after_governance,
        {
            "approval_interrupt": "approval_interrupt",
            "dispatch_runtime_executor": "dispatch_runtime_executor",
        },
    )
    builder.add_edge("dispatch_runtime_executor", "maybe_handoff_employee")
    builder.add_edge("maybe_handoff_employee", "ingest_ticket_report_evidence")
    builder.add_edge("ingest_ticket_report_evidence", "propose_asset_candidates")
    builder.add_edge("propose_asset_candidates", "close_or_continue_ticket_loop")
    builder.add_edge("close_or_continue_ticket_loop", "update_workbench_state")
    builder.add_conditional_edges(
        "update_workbench_state",
        _route_after_workbench_state,
        {
            "approval_interrupt": "approval_interrupt",
            "final_response": "final_response",
        },
    )
    builder.add_edge("approval_interrupt", "governance_gate")
    builder.add_edge("final_response", END)
    return builder.compile(checkpointer=checkpointer) if checkpointer is not None else builder.compile()


graph = build_graph()
