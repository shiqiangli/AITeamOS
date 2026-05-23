from __future__ import annotations

from pathlib import Path
from typing import Any

from aiteamos_schema import ModelCostSummaryRecord

from .loader import WorkspaceIndex, load_workspace
from .model_pricing import estimate_profile_call_cost_usd


def summarize_model_costs(workspace_or_index: str | Path | WorkspaceIndex) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    totals = _empty_totals()
    by_model: dict[tuple[str, str], dict[str, Any]] = {}
    by_run: dict[str, dict[str, Any]] = {}

    for run_id, events in sorted(index.run_events.items()):
        run = index.runs.get(run_id)
        run_row = {
            **_empty_totals(),
            "run": run_id,
            "task": run.spec.task if run else None,
            "member": run.spec.member if run else None,
            "assignment": run.spec.assignment if run else None,
            "profile": run.spec.modelProfile if run else None,
            "lastEventTs": None,
        }
        for event in events:
            event_type = str(event.get("type") or "")
            if not event_type.startswith("model.call"):
                continue
            provider = str(event.get("provider") or "unknown")
            model = str(event.get("model") or run_row["profile"] or "unknown")
            profile = index.model_profiles.get(run.spec.modelProfile or "") if run else None
            model_row = by_model.setdefault(
                (provider, model),
                {**_empty_totals(), "provider": provider, "model": model, "lastEventTs": None},
            )
            _apply_event(totals, event, profile)
            _apply_event(model_row, event, profile)
            _apply_event(run_row, event, profile)
        if run_row["attempts"] or run_row["calls"] or run_row["failures"]:
            by_run[run_id] = _finalize_row(run_row)

    summary = {
        "source": "workspace-event-ledger",
        "totals": _finalize_row(totals),
        "byModel": [_finalize_row(row) for _, row in sorted(by_model.items())],
        "byRun": [by_run[run_id] for run_id in sorted(by_run)],
    }
    return ModelCostSummaryRecord.model_validate(summary).model_dump(mode="json")


def _empty_totals() -> dict[str, Any]:
    return {
        "attempts": 0,
        "calls": 0,
        "failures": 0,
        "fallbacks": 0,
        "inputTokens": 0,
        "outputTokens": 0,
        "totalTokens": 0,
        "costUsd": 0.0,
        "latencyMsTotal": 0.0,
        "latencyMsAvg": None,
    }


def _apply_event(row: dict[str, Any], event: dict[str, Any], profile: Any = None) -> None:
    event_type = str(event.get("type") or "")
    if event_type == "model.call.started":
        row["attempts"] += 1
        if _is_fallback_event(event):
            row["fallbacks"] += 1
    elif event_type == "model.call.failed":
        row["failures"] += 1
        if _is_fallback_event(event):
            row["fallbacks"] += 1
    elif event_type == "model.call.completed":
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        row["calls"] += 1
        if _is_fallback_event(event):
            row["fallbacks"] += 1
        input_tokens = _int_from(usage, "input_tokens", "prompt_tokens", "inputTokens", "promptTokens") or 0
        output_tokens = _int_from(usage, "output_tokens", "completion_tokens", "outputTokens", "completionTokens") or 0
        row["inputTokens"] += input_tokens
        row["outputTokens"] += output_tokens
        total = _int_from(usage, "total_tokens", "totalTokens")
        if total is None:
            total = input_tokens + output_tokens
        row["totalTokens"] += total
        cost = _float_from(event, "cost_usd", "costUsd") or _float_from(usage, "cost_usd", "costUsd")
        if cost is None:
            cost = estimate_profile_call_cost_usd(profile, input_tokens=input_tokens, output_tokens=output_tokens)
        row["costUsd"] += cost or 0.0
        latency = _float_from(event, "latency_ms", "latencyMs")
        if latency is not None:
            row["latencyMsTotal"] += latency
    if event.get("ts"):
        row["lastEventTs"] = event["ts"]


def _finalize_row(row: dict[str, Any]) -> dict[str, Any]:
    finalized = dict(row)
    finalized["costUsd"] = round(float(finalized.get("costUsd") or 0.0), 8)
    if finalized.get("calls"):
        finalized["latencyMsAvg"] = round(float(finalized.get("latencyMsTotal") or 0.0) / int(finalized["calls"]), 3)
    completed = int(finalized.get("calls") or 0)
    failed = int(finalized.get("failures") or 0)
    finalized["successRate"] = round(completed / (completed + failed), 4) if completed or failed else None
    finalized.pop("latencyMsTotal", None)
    return finalized


def _is_fallback_event(event: dict[str, Any]) -> bool:
    return event.get("fallback") is True or event.get("isFallback") is True or bool(event.get("fallbackFrom"))


def _int_from(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _float_from(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None
