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


def _trace_event_data(trace_events: Sequence[Any], event_name: str) -> dict[str, Any]:
    for event in reversed(trace_events):
        if str(getattr(event, "event", "")) != event_name:
            continue
        data = getattr(event, "data", {})
        return dict(data) if isinstance(data, dict) else {}
    return {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _artifact_string_refs(artifacts: list[Any], key: str) -> list[str]:
    refs: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        refs.extend(_string_list(artifact.get(key)))
    return refs


def _compact_ref_items(items: Any, *, limit: int = 6) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    refs: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(
            item.get("ref")
            or item.get("evidence_ref")
            or item.get("artifact_ref")
            or item.get("diff_ref")
            or item.get("id")
            or item.get("path")
            or item.get("kind")
            or ""
        ).strip()
        if not label:
            changed_files = item.get("changed_files")
            if isinstance(changed_files, list) and changed_files:
                label = str(changed_files[0]).strip()
        if not label:
            continue
        refs.append(
            {
                "kind": str(item.get("kind") or item.get("type") or "").strip(),
                "ref": label[:220],
            }
        )
        if len(refs) >= limit:
            break
    return refs


def _compact_error_items(items: Any, *, limit: int = 4) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    errors: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or item.get("code") or "error").strip()
        detail = str(item.get("detail") or item.get("message") or "").strip()
        errors.append({"reason": reason[:120], "detail": detail[:240]})
        if len(errors) >= limit:
            break
    return errors


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _metadata_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return str(value).strip() if value is not None and str(value).strip() else ""


def _first_metadata_text(values: Sequence[Any]) -> str:
    for value in values:
        text = _metadata_text(value)
        if text:
            return text
    return ""


def _compact_visible_refs(items: Sequence[dict[str, Any]], *, limit: int = 8) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        kind = _metadata_text(item.get("kind") or item.get("type") or item.get("source_kind"))
        ref = _metadata_text(
            item.get("ref")
            or item.get("id")
            or item.get("asset_id")
            or item.get("candidate_id")
            or item.get("source_ref")
            or item.get("provider_ref")
            or item.get("report_id")
            or item.get("evidence_id")
            or item.get("memory_id")
        )
        if not ref:
            continue
        key = (kind, ref)
        if key in seen:
            continue
        seen.add(key)
        refs.append({"kind": kind, "ref": ref[:220]})
        if len(refs) >= limit:
            break
    return refs


def _compact_ticket_refs(values: Sequence[Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        text = _metadata_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        refs.append({"kind": "ticket", "ref": text[:220]})
    return refs


def _primary_blocker(blockers: Sequence[dict[str, Any]], errors: Sequence[dict[str, Any]]) -> str:
    for item in blockers:
        detail = _first_metadata_text([item.get("detail"), item.get("message"), item.get("reason")])
        if detail:
            return detail
    for item in errors:
        detail = _first_metadata_text([item.get("detail"), item.get("message"), item.get("reason")])
        if detail:
            return detail
    return ""


def _has_visible_handoff(handoff: dict[str, Any], ticket_handoff_refs: Sequence[dict[str, Any]]) -> bool:
    if ticket_handoff_refs:
        return True
    if not handoff:
        return False
    target = _first_metadata_text([
        handoff.get("to_employee_id"),
        handoff.get("target_employee_id"),
        handoff.get("employee_id"),
    ])
    if target:
        return True
    should_handoff = handoff.get("should_handoff")
    if should_handoff is True:
        return True
    status = _first_metadata_text([handoff.get("status"), handoff.get("decision")]).lower()
    if not status:
        return False
    return status not in {"not_applicable", "none", "no_handoff", "skipped", "false"}


def build_visible_response_contract(
    *,
    reply: str,
    run_metadata: dict[str, Any],
    ticket_keys: Sequence[str] = (),
    provider_blockers: Sequence[dict[str, Any]] = (),
    approval_requests: Sequence[dict[str, Any]] = (),
    approval_records: Sequence[dict[str, Any]] = (),
    handoff_summary: dict[str, Any] | None = None,
    handoff_decision: dict[str, Any] | None = None,
    ticket_handoff_refs: Sequence[dict[str, Any]] = (),
    asset_candidates: Sequence[dict[str, Any]] = (),
    runtime_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the single backend-owned contract the Chat main thread renders."""

    metadata = _record(run_metadata)
    execution = _record(metadata.get("execution"))
    result = _record(execution.get("result"))
    approval = _record(metadata.get("approval"))
    scoped_context = _record(metadata.get("scoped_context"))
    universal_context = _record(scoped_context.get("universal_context"))
    status_payload = _record(runtime_status)
    ticket_binding = _record(execution.get("ticket_binding"))
    approval_items = [
        *approval_requests,
        *_records(approval.get("approval_requests")),
    ]
    approval_record_items = [
        *approval_records,
        *_records(approval.get("approval_records")),
    ]
    errors = _records(result.get("errors"))
    blockers = [
        *provider_blockers,
        *_records(scoped_context.get("setup_blockers")),
        *_records(universal_context.get("setup_blockers")),
    ]
    ticket_refs = _compact_ticket_refs([
        *ticket_keys,
        *_string_list(metadata.get("ticket_keys")),
        ticket_binding.get("ticket_id"),
        result.get("output_ticket_id"),
        scoped_context.get("ticket_id"),
        universal_context.get("ticket_id"),
    ])
    asset_refs = _compact_visible_refs([
        *_records(result.get("artifact_refs")),
        *_records(result.get("evidence_refs")),
        *_records(result.get("ticket_report_refs")),
        *_records(metadata.get("memory_candidate_refs")),
        *asset_candidates,
    ])
    memory_refs = _compact_visible_refs([
        *_records(metadata.get("recalled_memory_refs")),
        *_records(universal_context.get("recalled_memory_refs")),
    ])
    handoff = _record(handoff_summary)
    handoff = handoff if handoff else _record(handoff_decision)
    status = _first_metadata_text([
        status_payload.get("status"),
        execution.get("status"),
        metadata.get("status"),
    ]) or "completed"
    status_key = status.lower()
    approval_required = bool(approval_items) or status_key in {"needs_approval", "waiting_approval", "approval_required"}
    blocker_reason = _primary_blocker(blockers, errors)
    if approval_required:
        display_state = "needs_approval"
    elif status_key in {"blocked", "failed", "error"}:
        display_state = "blocked"
    elif blockers:
        display_state = "provider_blocker"
    elif _has_visible_handoff(handoff, ticket_handoff_refs):
        display_state = "handoff"
    else:
        display_state = status_key or "completed"
    retry_cause = _primary_blocker([], errors) if status_key in {"blocked", "failed", "error"} or errors else ""
    return {
        "version": "chat_visible_response.v1",
        "assistant_message": {
            "role": "assistant",
            "content": reply,
        },
        "display_state": display_state,
        "runtime_status": {
            "status": status,
            "display_state": display_state,
            "run_id": _metadata_text(metadata.get("run_id")),
            "request_id": _metadata_text(execution.get("request_id")),
            "executor_id": _metadata_text(execution.get("executor_id") or status_payload.get("executor_id")),
            "current_node": _metadata_text(status_payload.get("current_node")),
        },
        "blocked_reason": blocker_reason,
        "retry_cause": retry_cause,
        "approval_request": approval_items[0] if approval_items else {},
        "approval_requests": approval_items[:4],
        "approval_records": approval_record_items[:4],
        "handoff_summary": handoff,
        "ticket_handoff_refs": list(ticket_handoff_refs)[:4],
        "ticket_refs": ticket_refs,
        "asset_refs": asset_refs,
        "memory_refs": memory_refs,
        "provider_blockers": list(blockers)[:6],
    }


def _universal_context_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    summary = value.get("summary") if isinstance(value.get("summary"), dict) else {}
    backend_context = value.get("backend_context") if isinstance(value.get("backend_context"), dict) else {}
    ticket_backend = backend_context.get("ticket_backend") if isinstance(backend_context.get("ticket_backend"), dict) else {}
    provenance_summary = value.get("provenance_summary") if isinstance(value.get("provenance_summary"), list) else []

    def safe_int(raw: Any) -> int:
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0

    return {
        "version": str(value.get("version") or ""),
        "employee_id": str(summary.get("employee_id") or ""),
        "ticket_id": str(summary.get("ticket_id") or ""),
        "selected_ai_engine": str(summary.get("selected_ai_engine") or ""),
        "related_ticket_count": safe_int(summary.get("related_ticket_count")),
        "relevant_asset_count": safe_int(summary.get("relevant_asset_count")),
        "recalled_memory_count": safe_int(summary.get("recalled_memory_count")),
        "prior_evidence_count": safe_int(summary.get("prior_evidence_count")),
        "setup_blocker_count": safe_int(summary.get("setup_blocker_count")),
        "ticket_backend_status": str(ticket_backend.get("status") or ""),
        "provenance_summary": [
            {
                "kind": str(item.get("kind") or ""),
                "source_kind": str(item.get("source_kind") or ""),
                "source_ref": str(item.get("source_ref") or ""),
                "scope_kind": str(item.get("scope_kind") or ""),
                "scope_ref": str(item.get("scope_ref") or ""),
                "source_confidence": str(item.get("source_confidence") or ""),
            }
            for item in provenance_summary[:8]
            if isinstance(item, dict)
        ],
    }


def _compact_ticket_report_refs(tool_events: Any, *, limit: int = 4) -> list[dict[str, str]]:
    if not isinstance(tool_events, list):
        return []
    refs: list[dict[str, str]] = []
    for event in reversed(tool_events):
        if not isinstance(event, dict):
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        ticket = data.get("ticket") if isinstance(data.get("ticket"), dict) else {}
        reports = ticket.get("reports") if isinstance(ticket.get("reports"), list) else []
        if not reports:
            continue
        report = reports[-1] if isinstance(reports[-1], dict) else {}
        report_id = str(report.get("id") or "").strip()
        if not report_id or any(item["ref"] == report_id for item in refs):
            continue
        evidence = report.get("evidence") if isinstance(report.get("evidence"), list) else []
        refs.append(
            {
                "kind": str(report.get("report_type") or report.get("type") or "ticket_report").strip(),
                "ref": report_id[:220],
                "evidence_count": str(len(evidence)),
            }
        )
        if len(refs) >= limit:
            break
    return list(reversed(refs))


def _execution_metadata(trace_events: Sequence[Any]) -> dict[str, Any]:
    request = _trace_event_data(trace_events, "execution.request.created")
    result = _trace_event_data(trace_events, "execution.dispatch.completed")
    if not request and not result:
        return {}

    action_plan = request.get("action_plan") if isinstance(request.get("action_plan"), dict) else {}
    ticket_binding = request.get("ticket_binding") if isinstance(request.get("ticket_binding"), dict) else {}
    task_context = request.get("task_context") if isinstance(request.get("task_context"), dict) else {}
    capability_grants = _string_list(request.get("capability_grants"))
    approval_policy = request.get("approval_policy") if isinstance(request.get("approval_policy"), dict) else {}
    expected_outputs = request.get("expected_outputs") if isinstance(request.get("expected_outputs"), dict) else {}
    trace_context = request.get("trace_context") if isinstance(request.get("trace_context"), dict) else {}
    approval_requests = result.get("approval_requests") if isinstance(result.get("approval_requests"), list) else []
    errors = result.get("errors") if isinstance(result.get("errors"), list) else []
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
    evidence = result.get("evidence") if isinstance(result.get("evidence"), list) else []
    tool_events = result.get("tool_events") if isinstance(result.get("tool_events"), list) else []
    learning_delta = result.get("learning_delta") if isinstance(result.get("learning_delta"), dict) else {}
    approval_records = learning_delta.get("approval_records") if isinstance(learning_delta.get("approval_records"), list) else []
    approval_record_refs = [
        str(item.get("id") or "").strip()
        for item in approval_records
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    approval_request_refs = [
        str(item.get("approval_ref") or item.get("approval_id") or item.get("id") or "").strip()
        for item in approval_requests
        if isinstance(item, dict) and str(item.get("approval_ref") or item.get("approval_id") or item.get("id") or "").strip()
    ]
    approval_refs = _unique_strings(
        [
            *_string_list(approval_policy.get("approval_refs")),
            *_artifact_string_refs(artifacts, "approval_refs"),
            *approval_request_refs,
            *approval_record_refs,
        ]
    )
    approved_capabilities = _unique_strings(
        [
            *_string_list(approval_policy.get("approved_capabilities")),
            *_artifact_string_refs(artifacts, "approved_capabilities"),
        ]
    )
    ticket_report_refs = _compact_ticket_report_refs(tool_events)

    def count_list(key: str) -> int:
        value = task_context.get(key)
        return len(value) if isinstance(value, list) else 0

    ticket = task_context.get("ticket") if isinstance(task_context.get("ticket"), dict) else {}
    setup_blockers = task_context.get("setup_blockers") if isinstance(task_context.get("setup_blockers"), list) else []
    universal_context = _universal_context_metadata(task_context.get("universal_context"))
    return {
        "request_id": str(result.get("request_id") or request.get("request_id") or trace_context.get("run_id") or ""),
        "executor_id": str(result.get("executor_id") or ""),
        "status": str(result.get("status") or ""),
        "action": str(action_plan.get("action") or ""),
        "ticket_binding": {
            "mode": str(ticket_binding.get("mode") or ""),
            "ticket_id": str(ticket_binding.get("ticket_id") or request.get("ticket_id") or ""),
            "required": bool(ticket_binding.get("required")),
        },
        "capability_grants": capability_grants,
        "expected_outputs": expected_outputs,
        "trace": {
            "trace_ref": str(result.get("trace_ref") or trace_context.get("trace_ref") or ""),
            "executor_session_ref": str(result.get("executor_session_ref") or ""),
            "checkpoint_ref": str(result.get("checkpoint_ref") or ""),
        },
        "result": {
            "output_ticket_id": str(result.get("output_ticket_id") or ""),
            "artifact_count": len(artifacts),
            "artifact_refs": _compact_ref_items(artifacts),
            "evidence_count": len(evidence),
            "evidence_refs": _compact_ref_items(evidence),
            "ticket_report_count": len(ticket_report_refs),
            "ticket_report_refs": ticket_report_refs,
            "tool_event_count": len(tool_events),
            "memory_candidate_count": len(result.get("memory_candidates")) if isinstance(result.get("memory_candidates"), list) else 0,
            "approval_request_count": len(approval_requests),
            "error_count": len(errors),
            "errors": _compact_error_items(errors),
            "usage": result.get("usage") if isinstance(result.get("usage"), dict) else {},
        },
        "scoped_context": {
            "task_summary": str(task_context.get("task_summary") or "")[:240],
            "ticket_id": str(ticket.get("id") or request.get("ticket_id") or ""),
            "employee_id": str(request.get("employee_id") or ""),
            "relevant_asset_count": count_list("relevant_assets"),
            "recalled_memory_count": count_list("recalled_memories"),
            "prior_evidence_count": count_list("prior_evidence"),
            "recent_message_count": count_list("recent_messages"),
            "recall_trace_count": count_list("recall_trace"),
            "setup_blocker_count": len(setup_blockers),
            "setup_blockers": setup_blockers[:3],
            "exclusions": _string_list(task_context.get("exclusions")),
            "universal_context": universal_context,
        },
        "approval": {
            "require_approval_for": _string_list(approval_policy.get("require_approval_for")),
            "on_missing_approval": str(approval_policy.get("on_missing_approval") or ""),
            "approval_refs": approval_refs,
            "approved_capabilities": approved_capabilities,
            "approval_requests": approval_requests[:3],
            "approval_records": approval_records[:3],
        },
        "governance": {
            "approval_refs": approval_refs,
            "approved_capabilities": approved_capabilities,
            "ticket_report_refs": ticket_report_refs,
            "ticket_bound": bool(request.get("ticket_id") or ticket_binding.get("ticket_id")),
            "approval_bound": bool(approval_refs),
            "evidence_bound": bool(evidence),
        },
    }


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
    execution = _execution_metadata(trace_events)
    trace_data = [getattr(event, "data", {}) for event in trace_events]
    provider_refs = collect_provider_refs(trace_data)
    graphiti_episode_refs = collect_graphiti_episode_refs(trace_data)
    if command_calls:
        actual_ai_engine = "kernel_command"
    elif ai_engine_event.get("event") == "ai_engine.stub.completed":
        actual_ai_engine = "stub"
    elif selected_ai_engine == "stub" and engine_state.get("ai_engine") == "file_stub":
        actual_ai_engine = "stub"
    else:
        actual_ai_engine = str(ai_engine_event.get("ai_engine") or engine_state.get("ai_engine") or selected_ai_engine)

    metadata = {
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
    if execution:
        metadata["execution"] = {
            key: value
            for key, value in execution.items()
            if key not in {"scoped_context", "approval"}
        }
        metadata["scoped_context"] = execution["scoped_context"]
        metadata["approval"] = execution["approval"]
    return metadata


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
