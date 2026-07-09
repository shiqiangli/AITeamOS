"""Action planning node for the AITeamOS Workbench graph."""

from typing import Any

from langchain_core.runnables.config import RunnableConfig

from aiteamos_api.agents.workbench.state import AITeamOSWorkbenchState, configurable, latest_human_text, record, text
from aiteamos_api.read.chat_action_planning_service import ChatActionPlanningService


async def plan_next_action(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    cfg = configurable(config)
    runtime_status = record(state.get("runtime_status"))
    message = latest_human_text(list(state.get("messages") or [])) or text(cfg.get("message"))
    employee = record(state.get("selected_employee"))
    employee_id = text(employee.get("id")) or text(state.get("employee_id")) or "clara"
    action_plan, planning_events = await ChatActionPlanningService().plan_async(
        message=message,
        ticket_keys=list(state.get("ticket_keys") or []),
        employee_id=employee_id,
        selected_ai_engine=text(state.get("selected_ai_engine")) or "system",
        workspace_id=text(cfg.get("workspace_id")) or "local",
        employee=employee,
        employee_profiles=list(state.get("employee_profiles") or []),
        recent_messages=list(state.get("recent_messages") or []),
    )
    return {
        "action_plan": action_plan.model_dump(mode="json"),
        "planning_events": planning_events,
        "runtime_status": {
            **runtime_status,
            "current_node": "plan_next_action",
            "planned_action": action_plan.action,
            "planning_source": action_plan.source,
            "planning_confidence": action_plan.confidence,
        },
    }
