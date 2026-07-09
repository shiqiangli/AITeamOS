"""Chat context enrichment helpers owned outside the route boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .knowledge_service import knowledge_snippets
from .memory_service import recall_memory_records, search_memory


def recalled_memory_ref(result: Any) -> dict[str, Any]:
    provenance = result.provenance if isinstance(result.provenance, dict) else {}
    memory_id = str(provenance.get("asset_id") or result.id)
    ref: dict[str, Any] = {
        "memory_id": memory_id,
        "source": result.source,
        "source_kind": result.source_kind,
        "source_ref": result.source_ref,
        "scope": {"kind": result.scope_kind, "ref": result.scope_ref},
        "memory_type": result.memory_type,
        "employee_ids": list(result.employee_ids),
        "tags": list(result.tags),
    }
    if provenance:
        ref["provenance"] = dict(provenance)
    if result.graphiti_episode_id:
        ref["graphiti_episode_id"] = result.graphiti_episode_id
    return ref


def memory_snippet_from_result(result: Any) -> str:
    return (
        f"[memory:{result.id}] {result.content} "
        f"(scope={result.scope_kind}:{result.scope_ref}; source={result.source_kind}:{result.source_ref})"
    )


def build_initial_chat_context_assets(
    *,
    message: str,
    employee_id: str,
    ticket_keys: list[str],
    knowledge_limit: int = 3,
) -> dict[str, Any]:
    recalled_memory_records = recall_memory_records(
        employee_id=employee_id,
        query=message,
        ticket_keys=ticket_keys,
    )
    recalled_memories = [memory_snippet_from_result(result) for result in recalled_memory_records]
    memory_refs = [recalled_memory_ref(result) for result in recalled_memory_records]
    memories = list(recalled_memories)
    recalled_knowledge: list[str] = []
    for snippet in knowledge_snippets(message, limit=knowledge_limit):
        if snippet.startswith("[memory:"):
            continue
        if snippet not in memories:
            memories.append(snippet)
            recalled_knowledge.append(snippet)
    return {
        "memories": memories,
        "memory_refs": memory_refs,
        "memory_count": len(recalled_memories),
        "knowledge_count": len(recalled_knowledge),
    }


async def enrich_chat_context_with_graphiti_recall(
    context: Any,
    *,
    workspace_root: Path,
) -> list[dict[str, Any]]:
    response = await search_memory(
        query=context.request.message,
        employee_id=context.employee.id,
        ticket_key=context.ticket_keys[0] if context.ticket_keys else None,
        limit=5,
        include_graphiti=True,
    )
    graphiti_results = [result for result in response.results if result.source == "graphiti"]
    added = 0
    for result in graphiti_results:
        if _merge_recalled_memory_result(context, result):
            added += 1
    if not graphiti_results:
        return []

    _update_context_loaded_memory_counts(context)
    trace_path = context.run_dirs["traces"] / f"{context.run_id}.jsonl"
    return [
        {
            "event": "memory.recall.completed",
            "detail": "Recalled approved durable Memory through Graphiti for this Chat run.",
            "data": {
                "query": context.request.message,
                "employee_id": context.employee.id,
                "ticket_keys": context.ticket_keys,
                "scopes": [
                    {"kind": ref.get("scope", {}).get("kind"), "ref": ref.get("scope", {}).get("ref")}
                    for ref in context.memory_refs
                    if isinstance(ref.get("scope"), dict)
                ],
                "source_trace": str(trace_path.relative_to(workspace_root)),
                "graphiti_result_count": len(graphiti_results),
                "added_result_count": added,
                "recalled_memory_refs": context.memory_refs,
                "graphiti_recalled_memory_refs": [recalled_memory_ref(result) for result in graphiti_results],
                "backend": response.backend.model_dump(mode="json"),
            },
        }
    ]


def _merge_recalled_memory_result(context: Any, result: Any) -> bool:
    ref = recalled_memory_ref(result)
    for existing_ref in context.memory_refs:
        if existing_ref.get("memory_id") != ref.get("memory_id"):
            continue
        if ref.get("graphiti_episode_id") and not existing_ref.get("graphiti_episode_id"):
            existing_ref["graphiti_episode_id"] = ref["graphiti_episode_id"]
        if result.source == "graphiti":
            existing_ref["graphiti_recalled"] = True
            existing_ref["graphiti_result_id"] = result.id
        if ref.get("provenance") and not existing_ref.get("provenance"):
            existing_ref["provenance"] = ref["provenance"]
        return False
    key = json.dumps(ref, ensure_ascii=False, sort_keys=True, default=str)
    existing = {
        json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        for item in context.memory_refs
    }
    if key in existing:
        return False
    snippet = memory_snippet_from_result(result)
    if snippet not in context.memories:
        context.memories.append(snippet)
    context.memory_refs.append(ref)
    return True


def _update_context_loaded_memory_counts(context: Any) -> None:
    memory_count = len([item for item in context.memories if item.startswith("[memory:")])
    for event in context.trace_events:
        if event.event != "context.loaded":
            continue
        event.data["memory_count"] = memory_count
        event.data["memory_and_knowledge_count"] = len(context.memories)
        event.data["recalled_memory_refs"] = context.memory_refs
        return
