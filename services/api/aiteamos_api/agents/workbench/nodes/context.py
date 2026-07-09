"""Context and identity nodes for the AITeamOS Workbench graph."""

import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Any

from langchain_core.runnables.config import RunnableConfig

from aiteamos_api.agents.workbench.state import AITeamOSWorkbenchState, configurable, latest_human_text, record, records, text
from aiteamos_api.read.execution_context_service import ExecutionContextService
from aiteamos_api.read.chat_models import ChatMessageRequest, ChatRunContext
from aiteamos_api.read.chat_run_preparation_service import ChatRunPreparationService
from aiteamos_api.read.employee_profile_service import load_employee_profiles
from aiteamos_api.read.memory_service import MemorySearchResult, search_memory


async def load_employee_identity(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(_load_employee_identity_sync, state, config)


def _load_employee_identity_sync(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    cfg = configurable(config)
    runtime_status = record(state.get("runtime_status"))
    message = latest_human_text(list(state.get("messages") or [])) or text(cfg.get("message"))
    provider_blockers = records(state.get("provider_blockers"))
    try:
        workspace_root = _workspace_root()
        profiles = load_employee_profiles(workspace_root=workspace_root)
        run_context = _chat_run_preparation_service(workspace_root).prepare(
            ChatMessageRequest(
                message=message,
                target_employee_id=(
                    text(state.get("employee_id"))
                    or text(cfg.get("target_employee_id"))
                    or text(cfg.get("employee_id"))
                    or None
                ),
                thread_id=text(state.get("thread_id")) or text(cfg.get("thread_id")) or None,
                ticket_key=text(state.get("ticket_key")) or text(cfg.get("ticket_key")) or None,
                runtime_config={
                    **record(cfg.get("runtime_config")),
                    "source": "aiteamos_workbench_graph",
                    "graph_node": "load_employee_identity",
                },
            )
        )
        employee = run_context.employee
        employee_payload = employee.model_dump(mode="json")
        employee_payload["permissions"] = [
            str(permission)
            for permission in run_context.selected_profile.get("permissions", [])
            if str(permission).strip()
        ]
        employee_payload["skill_titles"] = list(run_context.skills)
        context_assets = _initial_context_assets(run_context)
        return {
            "thread_id": run_context.thread_id,
            "employee_id": employee.id,
            "selected_employee": employee_payload,
            "employee_identity": {
                "profile": run_context.selected_profile,
                "summary": employee_payload,
                "source": "employee_profile",
            },
            "employee_profiles": profiles,
            "selected_ai_engine": run_context.selected_ai_engine,
            "ticket_key": run_context.ticket_keys[0] if run_context.ticket_keys else text(state.get("ticket_key")) or text(cfg.get("ticket_key")),
            "ticket_keys": run_context.ticket_keys,
            "recent_messages": [item.model_dump(mode="json") for item in run_context.recent_messages],
            "recalled_memory_refs": records(context_assets.get("memory_refs")),
            "context_bundle": {
                **record(state.get("context_bundle")),
                "initial_context_assets": context_assets,
            },
            "runtime_status": {
                **runtime_status,
                "current_node": "load_employee_identity",
                "employee_id": employee.id,
                "selected_ai_engine": run_context.selected_ai_engine,
                "ticket_keys": run_context.ticket_keys,
            },
        }
    except Exception as exc:
        provider_blockers.append(
            {
                "kind": "employee_context",
                "reason": "employee_identity_load_failed",
                "detail": str(exc)[:500],
                "provider": "chat_run_preparation_service",
            }
        )
        return {
            "provider_blockers": provider_blockers,
            "runtime_status": {
                **runtime_status,
                "current_node": "load_employee_identity",
                "status": "context_blocked",
            },
        }


async def retrieve_context(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    graphiti_recall = await _graphiti_recall_for_context(state, config)
    return await asyncio.to_thread(_retrieve_context_sync, state, config, graphiti_recall)


def _retrieve_context_sync(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None = None,
    graphiti_recall: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = configurable(config)
    runtime_status = record(state.get("runtime_status"))
    context_bundle = record(state.get("context_bundle"))
    initial_assets = record(context_bundle.get("initial_context_assets"))
    provider_blockers = records(state.get("provider_blockers"))
    graphiti_recall = record(graphiti_recall)
    try:
        message = latest_human_text(list(state.get("messages") or [])) or text(cfg.get("message"))
        employee = record(state.get("selected_employee"))
        memory_refs = _dedupe_memory_refs(
            [
                *(records(initial_assets.get("memory_refs")) or records(state.get("recalled_memory_refs"))),
                *records(graphiti_recall.get("memory_refs")),
            ]
        )
        scoped_context = ExecutionContextService().build(
            message=message,
            employee=employee,
            employee_profiles=list(state.get("employee_profiles") or []),
            recent_messages=list(state.get("recent_messages") or []),
            ticket_keys=list(state.get("ticket_keys") or []),
            memory_refs=memory_refs,
            selected_ai_engine=text(state.get("selected_ai_engine")) or "system",
            stale_memory_refs=records(graphiti_recall.get("stale_memory_refs")),
        )
        payload = scoped_context.model_dump(mode="json")
        universal_context = record(payload.get("universal_context"))
        provider_blockers = [
            *provider_blockers,
            *records(graphiti_recall.get("provider_blockers")),
            *records(payload.get("setup_blockers")),
        ]
        return {
            "context_bundle": {
                "source": "langgraph_context_node",
                "scoped_context": payload,
                "universal_context": universal_context,
                "initial_context_assets": {
                    **initial_assets,
                    "memory_refs": memory_refs,
                },
                "graphiti_recall": record(graphiti_recall.get("summary")),
            },
            "active_ticket": _active_ticket_from_context(universal_context, state),
            "linked_assets": records(record(universal_context.get("asset_context")).get("relevant_assets")),
            "recalled_memory_refs": records(payload.get("recalled_memories")),
            "provider_blockers": provider_blockers,
            "provenance_events": records(universal_context.get("provenance_summary")),
            "workbench_panels": {
                **record(state.get("workbench_panels")),
                "employee": True,
                "active_ticket": bool(record(universal_context.get("summary")).get("ticket_id")),
                "assets": bool(records(record(universal_context.get("asset_context")).get("relevant_assets")) or records(payload.get("recalled_memories"))),
                "provider_blockers": bool(provider_blockers),
                "provenance": True,
            },
            "runtime_status": {
                **runtime_status,
                "current_node": "retrieve_context",
                "context_source": "execution_context_service",
                "setup_blocker_count": len(provider_blockers),
                "graphiti_recall_count": int(record(graphiti_recall.get("summary")).get("graphiti_result_count") or 0),
            },
        }
    except Exception as exc:
        provider_blockers.append(
            {
                "kind": "context",
                "reason": "execution_context_build_failed",
                "detail": str(exc)[:500],
                "provider": "execution_context_service",
            }
        )
        return {
            "provider_blockers": provider_blockers,
            "context_bundle": {
                **context_bundle,
                "source": "langgraph_context_node",
                "status": "blocked",
            },
            "runtime_status": {
                **runtime_status,
                "current_node": "retrieve_context",
                "status": "context_blocked",
            },
        }


async def _graphiti_recall_for_context(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None,
) -> dict[str, Any]:
    cfg = configurable(config)
    message = latest_human_text(list(state.get("messages") or [])) or text(cfg.get("message"))
    employee = record(state.get("selected_employee"))
    employee_id = text(employee.get("id") or employee.get("employee_id") or state.get("employee_id") or cfg.get("employee_id"))
    ticket_keys = [item for item in [*list(state.get("ticket_keys") or []), text(state.get("ticket_key")) or text(cfg.get("ticket_key"))] if text(item)]
    if not message or not employee_id:
        return {
            "summary": {
                "status": "skipped",
                "reason": "message_or_employee_missing",
                "graphiti_result_count": 0,
            }
        }
    try:
        response = await search_memory(
            query=message,
            employee_id=employee_id,
            ticket_key=ticket_keys[0] if ticket_keys else None,
            limit=5,
            include_graphiti=True,
        )
    except Exception as exc:
        return {
            "summary": {
                "status": "failed",
                "reason": "graphiti_recall_failed",
                "graphiti_result_count": 0,
            },
            "provider_blockers": [
                {
                    "kind": "memory",
                    "reason": "graphiti_recall_failed",
                    "detail": str(exc)[:500],
                    "provider": "graphiti",
                }
            ],
        }

    backend = response.backend.model_dump(mode="json")
    graphiti_results = [result for result in response.results if result.source == "graphiti"]
    blockers: list[dict[str, Any]] = []
    if response.backend.enabled and response.backend.status != "ready":
        blockers.append(
            {
                "kind": "memory",
                "reason": "graphiti_recall_not_ready",
                "detail": response.backend.detail,
                "provider": "graphiti",
                "backend_status": response.backend.status,
            }
        )
    return {
        "memory_refs": [
            _memory_ref_from_graphiti_result(result)
            for result in graphiti_results
        ],
        "stale_memory_refs": [
            _stale_memory_ref_from_graphiti_exclusion(item)
            for item in records(response.excluded_results)
        ],
        "provider_blockers": blockers,
        "summary": {
            "status": "ready" if response.backend.status == "ready" else response.backend.status,
            "backend": backend,
            "query": response.query,
            "employee_id": employee_id,
            "ticket_keys": ticket_keys[:1],
            "graphiti_result_count": len(graphiti_results),
            "graphiti_excluded_result_count": len(response.excluded_results),
            "memory_ref_count": len(graphiti_results),
        },
    }


def _memory_ref_from_graphiti_result(result: MemorySearchResult) -> dict[str, Any]:
    provenance = result.provenance if isinstance(result.provenance, dict) else {}
    scope = provenance.get("scope") if isinstance(provenance.get("scope"), dict) else {}
    memory_id = text(provenance.get("asset_id") or provenance.get("memory_id") or result.id)
    source_ticket_id = text(provenance.get("source_ticket_id") or (scope.get("ref") if scope.get("kind") == "ticket" else ""))
    return {
        "memory_id": memory_id,
        "asset_id": memory_id,
        "content": result.content,
        "source": result.source,
        "source_kind": result.source_kind,
        "source_ref": result.source_ref or text(provenance.get("source_ref")),
        "scope_kind": result.scope_kind or text(scope.get("kind")),
        "scope_ref": result.scope_ref or text(scope.get("ref")),
        "memory_type": result.memory_type,
        "employee_ids": list(result.employee_ids),
        "tags": list(result.tags),
        "confidence": result.score if result.score is not None else 0.78,
        "provenance": provenance,
        "source_ticket_id": source_ticket_id,
        "graphiti_episode_id": result.graphiti_episode_id or "",
        "graphiti_recalled": True,
        "graphiti_backed": bool(result.graphiti_episode_id),
        "graphiti_result_id": result.id,
        "recall_reason": "Graphiti recalled an approved Asset for this LangGraph context",
    }


def _stale_memory_ref_from_graphiti_exclusion(item: dict[str, Any]) -> dict[str, Any]:
    provenance = record(item.get("provenance"))
    memory_id = text(item.get("memory_id") or item.get("asset_id") or item.get("id"))
    return {
        "memory_id": memory_id,
        "asset_id": text(item.get("asset_id") or memory_id),
        "content": text(item.get("content")),
        "status": text(item.get("status") or "excluded"),
        "source": text(item.get("source") or "graphiti"),
        "source_kind": text(item.get("source_kind") or provenance.get("source_kind")),
        "source_ref": text(item.get("source_ref") or provenance.get("source_ref") or memory_id),
        "scope_kind": text(item.get("scope_kind")),
        "scope_ref": text(item.get("scope_ref")),
        "memory_type": text(item.get("memory_type")),
        "employee_ids": [text(value) for value in item.get("employee_ids", []) if text(value)] if isinstance(item.get("employee_ids"), list) else [],
        "tags": [text(value) for value in item.get("tags", []) if text(value)] if isinstance(item.get("tags"), list) else [],
        "exclusion_reason": text(item.get("exclusion_reason")),
        "superseded_by_candidate_id": text(item.get("superseded_by_candidate_id")),
        "provenance": provenance,
        "source_confidence": float(item.get("score") or 0.2),
        "graphiti_episode_id": text(item.get("graphiti_episode_id")),
        "graphiti_result_id": text(item.get("graphiti_result_id") or item.get("id")),
        "graphiti_backed": bool(item.get("graphiti_backed") or item.get("graphiti_episode_id")),
    }


def _initial_context_assets(context: ChatRunContext) -> dict[str, Any]:
    loaded_event = next(
        (
            event
            for event in context.trace_events
            if event.event == "context.loaded" and isinstance(event.data, dict)
        ),
        None,
    )
    data = loaded_event.data if loaded_event is not None else {}
    return {
        "memories": list(context.memories),
        "memory_refs": list(context.memory_refs),
        "memory_count": int(data.get("memory_count") or 0),
        "knowledge_count": int(data.get("knowledge_count") or 0),
    }


def _chat_run_preparation_service(workspace_root: Path) -> ChatRunPreparationService:
    workspace_dir = workspace_root / ".aiteamos"
    return ChatRunPreparationService(
        workspace_root=workspace_root,
        workspace_dir=workspace_dir,
        now=_now,
        allow_runtime_config_run_id=True,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_root() -> Path:
    explicit = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[6]


def _dedupe_memory_refs(memory_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in memory_refs:
        if not isinstance(ref, dict):
            continue
        key = text(ref.get("asset_id") or ref.get("memory_id") or ref.get("graphiti_result_id") or ref.get("source_ref"))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def _active_ticket_from_context(
    universal_context: dict[str, Any],
    state: AITeamOSWorkbenchState,
) -> dict[str, Any] | None:
    summary = record(universal_context.get("summary"))
    ticket_id = text(summary.get("ticket_id"))
    if not ticket_id:
        return state.get("active_ticket") if isinstance(state.get("active_ticket"), dict) else None
    return {
        "id": ticket_id,
        "source": "execution_context_service",
        "ticket_keys": list(state.get("ticket_keys") or []),
    }
