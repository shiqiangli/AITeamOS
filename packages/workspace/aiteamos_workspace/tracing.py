from __future__ import annotations

from pathlib import Path
from typing import Any
import re
import secrets

from .loader import WorkspaceIndex, load_workspace


TRACE_COMPONENTS = ("dashboard", "api", "worker", "model_gateway", "git_provider")
TRACEPARENT_HEADER = "traceparent"
TRACE_ID_HEADER = "x-aiteamos-trace-id"
_TRACE_FLAGS = "01"
_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


def parse_traceparent(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    match = _TRACEPARENT_RE.match(value.strip())
    if match is None:
        return None
    trace_id, span_id, trace_flags = match.groups()
    if trace_id == "0" * 32 or span_id == "0" * 16:
        return None
    return {
        "traceId": trace_id,
        "spanId": span_id,
        "traceFlags": trace_flags,
        "traceparent": f"00-{trace_id}-{span_id}-{trace_flags}",
    }


def is_valid_traceparent(value: str | None) -> bool:
    return parse_traceparent(value) is not None


def new_trace_context(
    parent_traceparent: str | None = None,
    *,
    component: str = "api",
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parent = parse_traceparent(parent_traceparent)
    trace_id = parent["traceId"] if parent else _non_zero_hex(16)
    span_id = _non_zero_hex(8)
    trace_flags = parent["traceFlags"] if parent else _TRACE_FLAGS
    return {
        "traceparent": _format_traceparent(trace_id, span_id, trace_flags),
        "traceId": trace_id,
        "spanId": span_id,
        "parentSpanId": parent["spanId"] if parent else None,
        "traceFlags": trace_flags,
        "component": component,
        "attributes": _string_attributes(attributes or {}),
    }


def trace_response_headers(context: dict[str, Any]) -> dict[str, str]:
    return {
        TRACEPARENT_HEADER: str(context["traceparent"]),
        TRACE_ID_HEADER: str(context["traceId"]),
    }


def run_trace_context(
    workspace_or_index: str | Path | WorkspaceIndex,
    run_id: str,
    *,
    api_context: dict[str, Any] | None = None,
    parent_traceparent: str | None = None,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    attributes = {
        "runId": run_id,
        "taskId": run.spec.task,
        "memberId": run.spec.member,
        "assignmentId": run.spec.assignment or "",
        "projectId": run.spec.project,
    }
    context = api_context or new_trace_context(parent_traceparent, component="api", attributes=attributes)
    context = {**context, "attributes": _string_attributes({**attributes, **dict(context.get("attributes") or {})})}
    parent = parse_traceparent(parent_traceparent)
    dashboard_span = _dashboard_span(context, parent, attributes)
    api_span = _span_from_context(context, attributes)
    worker_span = _child_span(context, "worker", api_span["spanId"], attributes)
    model_span = _child_span(context, "model_gateway", worker_span["spanId"], attributes)
    git_span = _child_span(context, "git_provider", worker_span["spanId"], attributes)
    return {
        "traceparent": context["traceparent"],
        "traceId": context["traceId"],
        "spanId": context["spanId"],
        "parentSpanId": context.get("parentSpanId"),
        "traceFlags": context["traceFlags"],
        "attributes": context["attributes"],
        "requiredAttributes": ["runId", "taskId", "memberId"],
        "components": list(TRACE_COMPONENTS),
        "spans": [dashboard_span, api_span, worker_span, model_span, git_span],
    }


def _dashboard_span(
    context: dict[str, Any],
    parent: dict[str, str] | None,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    if parent:
        return _span(
            context["traceId"],
            "dashboard",
            parent["spanId"],
            None,
            context["traceFlags"],
            attributes,
            traceparent=parent["traceparent"],
        )
    span_id = _non_zero_hex(8)
    return _span(context["traceId"], "dashboard", span_id, None, context["traceFlags"], attributes)


def _span_from_context(context: dict[str, Any], attributes: dict[str, Any]) -> dict[str, Any]:
    return _span(
        context["traceId"],
        str(context.get("component") or "api"),
        str(context["spanId"]),
        context.get("parentSpanId"),
        str(context["traceFlags"]),
        attributes,
        traceparent=str(context["traceparent"]),
    )


def _child_span(
    context: dict[str, Any],
    component: str,
    parent_span_id: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    span_id = _non_zero_hex(8)
    return _span(context["traceId"], component, span_id, parent_span_id, context["traceFlags"], attributes)


def _span(
    trace_id: str,
    component: str,
    span_id: str,
    parent_span_id: str | None,
    trace_flags: str,
    attributes: dict[str, Any],
    *,
    traceparent: str | None = None,
) -> dict[str, Any]:
    return {
        "component": component,
        "traceId": trace_id,
        "spanId": span_id,
        "parentSpanId": parent_span_id,
        "traceparent": traceparent or _format_traceparent(trace_id, span_id, trace_flags),
        "attributes": _string_attributes(attributes),
    }


def _format_traceparent(trace_id: str, span_id: str, trace_flags: str) -> str:
    return f"00-{trace_id}-{span_id}-{trace_flags}"


def _non_zero_hex(num_bytes: int) -> str:
    while True:
        value = secrets.token_hex(num_bytes)
        if set(value) != {"0"}:
            return value


def _string_attributes(attributes: dict[str, Any]) -> dict[str, str]:
    return {str(key): "" if value is None else str(value) for key, value in attributes.items()}
