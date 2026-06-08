"""Reply and run metadata assembly helpers for Employee Chat."""

from __future__ import annotations

from typing import Any, Sequence

from .chat_trace_utils import collect_graphiti_episode_refs, collect_provider_refs, commands_from_trace_events


def ai_engine_event_metadata(trace_events: Sequence[Any]) -> dict[str, Any]:
    for event in reversed(trace_events):
        event_name = str(getattr(event, "event", ""))
        if event_name.startswith("ai_engine."):
            data = getattr(event, "data", {})
            event_data = dict(data) if isinstance(data, dict) else {}
            event_data["event"] = event_name
            event_data["detail"] = str(getattr(event, "detail", ""))
            return event_data
    return {}


def build_run_metadata(
    *,
    run_id: str,
    thread_id: str,
    employee_id: str,
    employee_display_name: str,
    employee_role: str,
    employee_default_ai_engine: str,
    ticket_keys: Sequence[str],
    memory_refs: Sequence[dict[str, Any]],
    selected_ai_engine: str,
    selected_model: str | None,
    engine_state: dict[str, Any],
    final_engine_thread_id: str,
    trace_events: list[Any],
    trace_relative_path: str,
    created_at: str,
) -> dict[str, Any]:
    command_calls = commands_from_trace_events(trace_events)
    ai_engine_event = ai_engine_event_metadata(trace_events)
    trace_data = [getattr(event, "data", {}) for event in trace_events]
    provider_refs = collect_provider_refs(trace_data)
    graphiti_episode_refs = collect_graphiti_episode_refs(trace_data)
    if command_calls:
        actual_ai_engine = "kernel_command"
    elif ai_engine_event.get("event") == "ai_engine.stub.completed":
        actual_ai_engine = "stub"
    else:
        actual_ai_engine = str(ai_engine_event.get("ai_engine") or engine_state.get("ai_engine") or selected_ai_engine)

    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "employee": {
            "id": employee_id,
            "display_name": employee_display_name,
            "role": employee_role,
        },
        "ticket_keys": list(ticket_keys),
        "provider_refs": provider_refs,
        "graphiti_episode_refs": graphiti_episode_refs,
        "recalled_memory_refs": list(memory_refs),
        "ai_engine": {
            "selected_ai_engine": selected_ai_engine,
            "employee_default_ai_engine": employee_default_ai_engine,
            "actual_ai_engine": actual_ai_engine,
            "model": ai_engine_event.get("model") or selected_model,
            "engine_thread_id": final_engine_thread_id,
            "event": ai_engine_event.get("event"),
        },
        "commands": command_calls,
        "trace": {
            "path": trace_relative_path,
            "event_count": len(trace_events),
        },
        "created_at": created_at,
    }


def build_stub_reply(
    *,
    employee_display_name: str,
    employee_role: str,
    employee_ai_engine_mode: str,
    employee_default_ai_engine: str,
    message_prefers_chinese: bool,
    ticket_keys: Sequence[str],
    engine_thread_id: str,
    skills: Sequence[str],
    memory_snippets: Sequence[str],
) -> str:
    ticket_text = ", ".join(ticket_keys) if ticket_keys else "not bound"
    skill_text = ", ".join(skills[:4]) if skills else "no local skills loaded"
    memory_text = f"{len(memory_snippets)} local memory snippet(s)" if memory_snippets else "no local memory snippets"

    if message_prefers_chinese:
        ticket_text_zh = ", ".join(ticket_keys) if ticket_keys else "未绑定"
        skill_text_zh = ", ".join(skills[:4]) if skills else "未加载本地技能"
        memory_text_zh = f"{len(memory_snippets)} 条本地记忆片段" if memory_snippets else "无本地记忆片段"
        return (
            f"{employee_display_name} 已收到请求。\n\n"
            f"角色：{employee_role}\n"
            f"工单：{ticket_text_zh}\n"
            f"AI Engine：{employee_ai_engine_mode}；默认：{employee_default_ai_engine}；"
            f"engine thread：{engine_thread_id}\n"
            f"上下文门控：{skill_text_zh}；{memory_text_zh}\n\n"
            "本轮回复来自本地 file-backed fallback/stub：我已加载目标员工 profile，"
            "解析可复用 AI Engine thread 映射，记录对话并写入本地 trace。"
            "本轮没有实际调用外部 Ticket、harness 或远程 AI Engine。\n\n"
            "下一步预览：读取 Ticket 上下文，选择相关 Skills 和 Memory，"
            "通过已配置的外部或本地 AI Engine 执行，并带着 trace evidence 回到这个线程汇报进展。"
        )

    return (
        f"{employee_display_name} received the request.\n\n"
        f"Role: {employee_role}\n"
        f"Ticket: {ticket_text}\n"
        f"AI Engine: {employee_ai_engine_mode}; default: {employee_default_ai_engine}; "
        f"engine thread: {engine_thread_id}\n"
        f"Context gate: {skill_text}; {memory_text}\n\n"
        "P0 file-backed run completed: I loaded the addressed employee profile, "
        "resolved the reusable AI Engine thread mapping, captured the conversation, "
        "and wrote a local trace. External Ticket, harness, and AI Engine execution are "
        "not invoked in this first slice.\n\n"
        "Next action preview: read the Ticket context, pick the relevant skills and "
        "memory, execute through the configured external or local AI Engine, "
        "and report progress back into this thread with trace evidence."
    )
