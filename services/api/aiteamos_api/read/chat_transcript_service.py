"""Chat transcript, trace, and learning persistence helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .chat_response_metadata import build_visible_response_contract
from .chat_trace_utils import append_jsonl
from .memory_service import propose_memory_from_chat_turn, record_memory_recall_usage
from .skill_usage_service import record_skill_usage


def persist_chat_response(
    context: Any,
    *,
    reply: str,
    workspace_root: Path,
    workspace_dir: Path,
    trace_event_model: Callable[..., Any],
    response_model: Callable[..., Any],
    now: Callable[[], str],
    save_engine_thread_state: Callable[..., None],
    build_run_metadata: Callable[..., dict[str, Any]],
    record_chat_thread_turn: Callable[..., Any],
    thread_index_saved_path: Callable[[], str],
    engine_state: dict[str, Any] | None = None,
    engine_thread_id: str | None = None,
    extra_trace_events: list[Any] | None = None,
) -> Any:
    if engine_state is not None:
        save_engine_thread_state(workspace_dir, context.employee.id, context.thread_id, engine_state)
    final_engine_thread_id = engine_thread_id or context.engine_thread_id

    trace_events = [
        *context.trace_events,
        *(extra_trace_events or []),
        trace_event_model(event="response.created", detail="Assistant response was created."),
    ]

    conversation_path = context.run_dirs["conversations"] / f"{context.thread_id}.jsonl"
    trace_path = context.run_dirs["traces"] / f"{context.run_id}.jsonl"
    memory_usage_refs: list[dict[str, Any]] = []
    skill_usage_refs: list[dict[str, Any]] = []
    try:
        memory_usage_refs = record_memory_recall_usage(
            memory_refs=context.memory_refs,
            run_id=context.run_id,
            employee_id=context.employee.id,
            ticket_keys=context.ticket_keys,
            query=context.request.message,
            trace_path=str(trace_path.relative_to(workspace_root)),
        )
        if memory_usage_refs:
            trace_events.append(
                trace_event_model(
                    event="memory.recall.usage_recorded",
                    detail="Recorded learning-effectiveness usage refs for recalled approved Memory assets.",
                    data={
                        "usage_refs": memory_usage_refs,
                        "usage_count": len(memory_usage_refs),
                        "ticket_keys": context.ticket_keys,
                        "employee_id": context.employee.id,
                    },
                )
            )
    except Exception as exc:
        trace_events.append(
            trace_event_model(
                event="memory.recall.usage_failed",
                detail="Memory recall usage recording failed; chat response was still persisted.",
                data={"error": str(exc)[:300]},
            )
        )

    try:
        skill_usage_refs = record_skill_usage(
            workspace_dir=workspace_dir,
            skill_ids=list(context.employee.skills),
            employee_id=context.employee.id,
            run_id=context.run_id,
            thread_id=context.thread_id,
            ticket_keys=context.ticket_keys,
            trace_path=str(trace_path.relative_to(workspace_root)),
            source_kind="chat_context",
        )
        if skill_usage_refs:
            trace_events.append(
                trace_event_model(
                    event="skill.usage.recorded",
                    detail="Recorded Skill usage for the Employee context loaded into this Chat run.",
                    data={
                        "usage_refs": skill_usage_refs,
                        "usage_count": len(skill_usage_refs),
                        "ticket_keys": context.ticket_keys,
                        "employee_id": context.employee.id,
                    },
                )
            )
    except Exception as exc:
        trace_events.append(
            trace_event_model(
                event="skill.usage.failed",
                detail="Skill usage recording failed; chat response was still persisted.",
                data={"error": str(exc)[:300]},
            )
        )

    run_metadata = build_run_metadata(
        context,
        final_engine_thread_id=final_engine_thread_id,
        trace_events=trace_events,
        trace_path=trace_path,
    )
    if memory_usage_refs:
        run_metadata["memory_usage_refs"] = memory_usage_refs
        run_metadata["learning_effectiveness"] = {
            "recalled_asset_count": len(memory_usage_refs),
            "usefulness_status": "unreviewed",
            "usage_refs": memory_usage_refs,
            "source": "memory_recall_usage",
        }
        run_metadata["learning_summary"] = learning_summary_from_run(
            context,
            memory_usage_refs=memory_usage_refs,
        )
    if skill_usage_refs:
        run_metadata["skill_usage_refs"] = skill_usage_refs
    run_metadata["visible_response"] = build_visible_response_contract(
        reply=reply,
        run_metadata=run_metadata,
        ticket_keys=context.ticket_keys,
    )
    trace_events.append(
        trace_event_model(
            event="run.metadata.recorded",
            detail="Captured AI Engine, ticket, and tool metadata for this run.",
            data=run_metadata,
        )
    )

    user_timestamp = now()
    assistant_timestamp = now()
    append_jsonl(conversation_path, {
        "timestamp": user_timestamp,
        "role": "user",
        "content": context.request.message,
        "employee_id": None,
        "run_id": context.run_id,
        "metadata": {
            "aiteamos": {
                "message_kind": "user_request",
                "run_id": context.run_id,
                "thread_id": context.thread_id,
                "target_employee_id": context.employee.id,
                "ticket_keys": context.ticket_keys,
                "ai_engine": {
                    "selected_ai_engine": context.selected_ai_engine,
                    "employee_default_ai_engine": context.employee.default_ai_engine,
                },
            }
        },
    })
    append_jsonl(conversation_path, {
        "timestamp": assistant_timestamp,
        "role": "assistant",
        "content": reply,
        "employee_id": context.employee.id,
        "run_id": context.run_id,
        "metadata": {
            "aiteamos": {
                "message_kind": "assistant_response",
                **run_metadata,
            }
        },
    })
    thread_summary = record_chat_thread_turn(context, last_message_at=assistant_timestamp)

    memory_candidate = None
    try:
        ticket_report_refs = latest_ticket_report_refs(trace_events)
        memory_candidate = propose_memory_from_chat_turn(
            run_id=context.run_id,
            thread_id=context.thread_id,
            employee_id=context.employee.id,
            employee_display_name=context.employee.display_name,
            user_message=context.request.message,
            assistant_reply=reply,
            ticket_keys=context.ticket_keys,
            trace_path=str(trace_path.relative_to(workspace_root)),
            provider_refs=run_metadata.get("provider_refs") if isinstance(run_metadata.get("provider_refs"), list) else [],
            graphiti_episode_refs=run_metadata.get("graphiti_episode_refs") if isinstance(run_metadata.get("graphiti_episode_refs"), list) else [],
            source_report_id=ticket_report_refs["source_report_id"],
            evidence_id=ticket_report_refs["evidence_id"],
            recalled_memory_refs=context.memory_refs,
            action_plan=latest_chat_action_plan(trace_events),
        )
        if memory_candidate is not None:
            run_metadata["memory_candidate_refs"] = [memory_candidate_run_ref(memory_candidate)]
            run_metadata["learning_summary"] = learning_summary_from_run(
                context,
                memory_usage_refs=memory_usage_refs,
                memory_candidate=memory_candidate,
            )
            for event in trace_events:
                if event.event == "run.metadata.recorded":
                    event.data = run_metadata
                    break
            trace_events.append(
                trace_event_model(
                    event="memory.candidate.proposed",
                    detail="Proposed a ticket-aware memory candidate from this Chat run.",
                    data={
                        "candidate_id": memory_candidate.id,
                        "scope": f"{memory_candidate.scope_kind}:{memory_candidate.scope_ref}",
                        "confidence": memory_candidate.confidence,
                        "source_kind": memory_candidate.source_kind,
                        "source_ref": memory_candidate.source_ref,
                        "provenance": memory_candidate.provenance,
                    },
                )
            )
    except Exception as exc:
        trace_events.append(
            trace_event_model(
                event="memory.candidate.failed",
                detail="Memory candidate extraction failed; chat response was still persisted.",
                data={"error": str(exc)[:300]},
            )
        )

    if run_metadata.get("learning_summary"):
        trace_events.append(
            trace_event_model(
                event="learning.summary.recorded",
                detail="Recorded Clara learning summary for recalled assets and proposed candidates.",
                data=run_metadata["learning_summary"],
            )
        )

    run_metadata["visible_response"] = build_visible_response_contract(
        reply=reply,
        run_metadata=run_metadata,
        ticket_keys=context.ticket_keys,
    )
    for event in trace_events:
        if event.event == "run.metadata.recorded":
            event.data = run_metadata
            break

    for event in trace_events:
        append_jsonl(trace_path, {
            "timestamp": now(),
            "run_id": context.run_id,
            **event.model_dump(),
        })

    trace_events.append(trace_event_model(event="trace.persisted", detail="Conversation and trace were saved."))

    return response_model(
        thread_id=context.thread_id,
        run_id=context.run_id,
        target_employee=context.employee,
        engine_thread_id=final_engine_thread_id,
        ticket_keys=context.ticket_keys,
        reply=reply,
        trace_events=trace_events,
        run_metadata=run_metadata,
        saved_paths={
            "conversation": str(conversation_path.relative_to(workspace_root)),
            "trace": str(trace_path.relative_to(workspace_root)),
            "threads": thread_index_saved_path(),
            "thread": thread_summary.saved_path,
            "engine_threads": str((workspace_dir / "engine_threads.json").relative_to(workspace_root)),
            **(
                {"memory_candidate": f".aiteamos/memory/candidates.json#{memory_candidate.id}"}
                if memory_candidate is not None
                else {}
            ),
        },
    )


def latest_ticket_report_refs(trace_events: list[Any]) -> dict[str, str]:
    for event in reversed(trace_events):
        ticket_payload = event.data.get("ticket") if isinstance(event.data.get("ticket"), dict) else None
        if ticket_payload is None:
            continue
        reports = ticket_payload.get("reports")
        if not isinstance(reports, list) or not reports:
            continue
        report = reports[-1] if isinstance(reports[-1], dict) else {}
        evidence = report.get("evidence")
        evidence_id = ""
        if isinstance(evidence, list) and evidence:
            evidence_id = str(evidence[0])
        return {
            "source_report_id": str(report.get("id") or ""),
            "evidence_id": evidence_id,
        }
    return {"source_report_id": "", "evidence_id": ""}


def latest_chat_action_plan(trace_events: list[Any]) -> dict[str, Any]:
    for event in reversed(trace_events):
        if event.event == "chat.action_plan.completed":
            return dict(event.data)
        plan = event.data.get("plan")
        if isinstance(plan, dict):
            action_plan = plan.get("chat_action_plan")
            if isinstance(action_plan, dict):
                return dict(action_plan)
    return {}


def memory_candidate_run_ref(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_id": candidate.id,
        "asset_id": candidate.id,
        "asset_type": f"memory:{candidate.memory_type}",
        "asset_status": candidate.status,
        "source_kind": candidate.source_kind,
        "source_ref": candidate.source_ref,
        "scope": {"kind": candidate.scope_kind, "ref": candidate.scope_ref},
        "confidence": candidate.confidence,
        "provenance": dict(candidate.provenance),
    }


def learning_summary_from_candidate(candidate: Any) -> dict[str, Any]:
    provenance = candidate.provenance if isinstance(candidate.provenance, dict) else {}
    hints = provenance.get("future_recall_query_hints")
    return {
        "learned_facts": [candidate.content],
        "avoided_pitfalls": [],
        "reusable_decisions": [],
        "suggested_skill_doc_updates": [],
        "future_recall_query_hints": hints if isinstance(hints, list) else [],
        "candidate_id": candidate.id,
        "source_ticket_id": provenance.get("source_ticket_id", ""),
    }


def learning_summary_from_run(
    context: Any,
    *,
    memory_usage_refs: list[dict[str, Any]],
    memory_candidate: Any | None = None,
) -> dict[str, Any]:
    usage_by_memory_id = {
        str(ref.get("memory_id") or ref.get("asset_id")): ref
        for ref in memory_usage_refs
        if ref.get("memory_id") or ref.get("asset_id")
    }
    recalled_assets: list[dict[str, Any]] = []
    seen_memory_ids: set[str] = set()
    for ref in context.memory_refs:
        memory_id = str(ref.get("memory_id") or "")
        if not memory_id or memory_id in seen_memory_ids:
            continue
        seen_memory_ids.add(memory_id)
        usage_ref = usage_by_memory_id.get(memory_id, {})
        recalled_assets.append(
            {
                "memory_id": memory_id,
                "asset_id": memory_id,
                "source": ref.get("source", ""),
                "scope": ref.get("scope", {}),
                "graphiti_recalled": bool(ref.get("graphiti_recalled") or usage_ref.get("graphiti_recalled")),
                "graphiti_episode_id": ref.get("graphiti_episode_id") or usage_ref.get("graphiti_episode_id") or "",
                "usage_id": usage_ref.get("usage_id", ""),
                "usefulness_status": usage_ref.get("usefulness_status", "unreviewed") if usage_ref else "",
            }
        )

    candidate_summary = learning_summary_from_candidate(memory_candidate) if memory_candidate is not None else {}
    if not recalled_assets and not candidate_summary:
        return {}

    future_hints = candidate_summary.get("future_recall_query_hints")
    if not isinstance(future_hints, list):
        future_hints = []
    future_hints = sorted({str(item) for item in [*future_hints, *context.ticket_keys] if str(item).strip()})
    next_round_guidance: list[str] = []
    if recalled_assets:
        next_round_guidance.append("Review each recalled approved Memory as used, irrelevant, harmful, or promoted before the next similar Ticket.")
        next_round_guidance.append("Prefer approved Memories already marked used or promoted for future Ticket context.")
    if memory_candidate is not None:
        next_round_guidance.append("Review the proposed Memory candidate and approve it only if its provenance is sufficient.")
    source_ticket_id = (
        str(candidate_summary.get("source_ticket_id") or "")
        or (context.ticket_keys[0] if context.ticket_keys else "")
    )
    candidate_refs = [memory_candidate_run_ref(memory_candidate)] if memory_candidate is not None else []
    if recalled_assets and memory_candidate is not None:
        clara_summary = (
            f"本轮 AITeamOS 复用了 {len(recalled_assets)} 条 approved Memory，并提出 1 条新的 Memory candidate；"
            "下一轮应复查 recall usefulness，并优先使用已标记 used/promoted 的经验。"
        )
    elif recalled_assets:
        clara_summary = (
            f"本轮 AITeamOS 复用了 {len(recalled_assets)} 条 approved Memory；"
            "下一轮应让 Clara/PV 标记这些 recall 是 used、irrelevant、harmful 还是 promoted。"
        )
    else:
        clara_summary = "本轮 AITeamOS 提出 1 条 Memory candidate；审核通过后可在类似 Ticket 中召回。"

    return {
        "learned_facts": candidate_summary.get("learned_facts", []),
        "avoided_pitfalls": candidate_summary.get("avoided_pitfalls", []),
        "reusable_decisions": candidate_summary.get("reusable_decisions", []),
        "suggested_skill_doc_updates": candidate_summary.get("suggested_skill_doc_updates", []),
        "future_recall_query_hints": future_hints,
        "candidate_id": candidate_summary.get("candidate_id", ""),
        "memory_candidate_refs": candidate_refs,
        "source_ticket_id": source_ticket_id,
        "recalled_assets": recalled_assets,
        "used_approved_asset_count": len(recalled_assets),
        "new_candidate_count": 1 if memory_candidate is not None else 0,
        "memory_usage_refs": memory_usage_refs,
        "next_round_guidance": next_round_guidance,
        "clara_summary": clara_summary,
    }
