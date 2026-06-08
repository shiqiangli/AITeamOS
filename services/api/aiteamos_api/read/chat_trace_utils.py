"""Trace and provenance utility helpers for Employee Chat."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def commands_from_trace_events(trace_events: list[Any]) -> list[dict[str, Any]]:
    calls: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    terminal_phases = {"completed", "blocked", "failed"}
    for event in trace_events:
        event_name = str(getattr(event, "event", ""))
        event_data = getattr(event, "data", {})
        event_data = event_data if isinstance(event_data, dict) else {}
        parts = event_name.split(".")
        if len(parts) < 2 or parts[0] != "command":
            continue
        phase = ".".join(parts[1:])
        if phase.startswith("intent_planner"):
            continue
        if phase not in {"called", *terminal_phases}:
            continue
        command_data = event_data.get("command") if isinstance(event_data.get("command"), dict) else {}
        command_id = str(command_data.get("id") or event_data.get("command_id") or "unknown")

        if command_id not in calls:
            order.append(command_id)
            calls[command_id] = {
                "id": command_id,
                "capability": command_data.get("capability", ""),
                "operation": command_data.get("operation", ""),
                "status": "planned",
                "events": [],
            }
        call = calls[command_id]
        model_dump = getattr(event, "model_dump", None)
        call["events"].append(model_dump(mode="json") if callable(model_dump) else {"event": event_name, "data": event_data})
        if phase == "called" and call.get("status") == "planned":
            call["status"] = "called"
        if phase in terminal_phases:
            call["status"] = phase
            call["result"] = event_data
    return [calls[command_id] for command_id in order]


def collect_provider_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            provider_ref = item.get("provider_ref")
            if isinstance(provider_ref, dict):
                compact = _compact_ref_dict(provider_ref)
                if compact.get("provider") and compact.get("provider_record_id"):
                    refs.append(compact)
            provider_refs = item.get("provider_refs")
            if isinstance(provider_refs, list):
                for ref in provider_refs:
                    if isinstance(ref, dict):
                        compact = _compact_ref_dict(ref)
                        if compact.get("provider") and compact.get("provider_record_id"):
                            refs.append(compact)
            for nested in item.values():
                visit(nested)
            return
        if isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return _dedupe_ref_dicts(refs)


def collect_graphiti_episode_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []

    def append_ref(item: dict[str, Any], episode_id: Any) -> None:
        if not isinstance(episode_id, str) or not episode_id.strip():
            return
        ref: dict[str, Any] = {"graphiti_episode_id": episode_id.strip()}
        for key in ("memory_id", "asset_id", "source", "source_kind", "source_ref", "scope"):
            if item.get(key) not in (None, "", [], {}):
                ref[key] = item[key]
        refs.append(ref)

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            append_ref(item, item.get("graphiti_episode_id"))
            graphiti_status = item.get("graphiti_status")
            if isinstance(graphiti_status, dict):
                append_ref(item, graphiti_status.get("episode_id"))
            for nested in item.values():
                visit(nested)
            return
        if isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return _dedupe_ref_dicts(refs)


def _dedupe_ref_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _compact_ref_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(key, str) and item not in (None, "", [], {})
    }
