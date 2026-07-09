"""Golden-query evaluation helpers for AITeamOS context retrieval."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .execution_contract import ScopedTaskContext


class ContextRetrievalExpectedRef(BaseModel):
    kind: str
    ref: str


class ContextRetrievalEvalCase(BaseModel):
    id: str
    query: str
    expected_refs: list[ContextRetrievalExpectedRef] = Field(default_factory=list)


class ContextRetrievalEvalResult(BaseModel):
    case_id: str
    query: str
    matched_refs: list[dict[str, str]] = Field(default_factory=list)
    missing_refs: list[dict[str, str]] = Field(default_factory=list)
    retrieved_refs: list[dict[str, str]] = Field(default_factory=list)
    expected_count: int = 0
    retrieved_count: int = 0
    matched_count: int = 0
    recall: float = 0.0
    precision_like: float = 0.0
    audit: dict[str, Any] = Field(default_factory=dict)


def evaluate_context_retrieval(
    context: ScopedTaskContext | dict[str, Any],
    case: ContextRetrievalEvalCase,
) -> ContextRetrievalEvalResult:
    payload = context.model_dump(mode="json") if isinstance(context, ScopedTaskContext) else context
    universal_context = payload.get("universal_context") if isinstance(payload.get("universal_context"), dict) else {}
    retrieved = _retrieved_refs(universal_context)
    retrieved_keys = {(item["kind"], item["ref"]) for item in retrieved}
    expected = [
        {"kind": item.kind.strip(), "ref": item.ref.strip()}
        for item in case.expected_refs
        if item.kind.strip() and item.ref.strip()
    ]
    matched = [item for item in expected if (item["kind"], item["ref"]) in retrieved_keys]
    missing = [item for item in expected if (item["kind"], item["ref"]) not in retrieved_keys]
    expected_count = len(expected)
    retrieved_count = len(retrieved)
    matched_count = len(matched)
    return ContextRetrievalEvalResult(
        case_id=case.id,
        query=case.query,
        matched_refs=matched,
        missing_refs=missing,
        retrieved_refs=retrieved,
        expected_count=expected_count,
        retrieved_count=retrieved_count,
        matched_count=matched_count,
        recall=matched_count / expected_count if expected_count else 1.0,
        precision_like=matched_count / retrieved_count if retrieved_count else (1.0 if expected_count == 0 else 0.0),
        audit=universal_context.get("retrieval_audit") if isinstance(universal_context.get("retrieval_audit"), dict) else {},
    )


def _retrieved_refs(universal_context: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    employee_context = _record(universal_context.get("employee_context"))
    selected_employee = _record(employee_context.get("selected_employee"))
    _append(refs, "employee", selected_employee.get("employee_id"))
    work_history = _record(employee_context.get("work_history"))
    work_history_summary = _record(work_history.get("summary"))
    work_history_provenance = _record(work_history.get("provenance"))
    _append(
        refs,
        "employee_work_history",
        work_history_provenance.get("source_ref") or work_history_summary.get("employee_id"),
    )
    work_history_refs = _record(work_history.get("refs"))
    for item in _records(work_history_refs.get("current_tickets")):
        _append(refs, "work_ticket", item.get("ticket_id"))
    for item in _records(work_history_refs.get("historical_tickets")):
        _append(refs, "work_ticket", item.get("ticket_id"))
    for item in _records(work_history_refs.get("recent_reports")):
        _append(refs, "work_report", item.get("report_id"))
        _append(refs, "evidence", item.get("report_id"))
    for item in _records(work_history_refs.get("blocked_records")):
        _append(refs, "blocked_work_report", item.get("report_id"))
    for item in _records(work_history_refs.get("handoffs")):
        _append(refs, "handoff", item.get("ticket_id"))
    for item in _records(work_history_refs.get("asset_candidates")):
        _append(refs, "asset_candidate", item.get("candidate_id"))
    for item in _records(work_history_refs.get("approved_assets")):
        _append(refs, "asset", item.get("asset_id"))
    for item in _records(work_history_refs.get("asset_reviews")):
        _append(refs, "asset_review", item.get("review_id"))
    for item in _records(work_history_refs.get("runtime_runs")):
        _append(refs, "runtime_run", item.get("request_id") or item.get("run_id"))
    for item in _records(work_history_refs.get("quality_feedback")):
        _append(refs, "quality_feedback", item.get("id"))

    ticket_context = _record(universal_context.get("ticket_context"))
    current_ticket = _record(ticket_context.get("current_ticket"))
    _append(refs, "ticket", current_ticket.get("ticket_id"))
    for item in _records(ticket_context.get("related_tickets")):
        _append(refs, "related_ticket", item.get("ticket_id"))
        _append(refs, "ticket", item.get("ticket_id"))
    for item in _records(ticket_context.get("prior_evidence")):
        _append(refs, "evidence", item.get("report_id"))

    asset_context = _record(universal_context.get("asset_context"))
    for item in _records(asset_context.get("relevant_assets")):
        _append(refs, "asset", item.get("asset_id"))

    memory_context = _record(universal_context.get("memory_context"))
    for item in _records(memory_context.get("recalled_memories")):
        _append(refs, "memory", item.get("memory_id") or item.get("asset_id"))
        _append(refs, "asset", item.get("asset_id"))
    return _dedupe_refs(refs)


def _append(refs: list[dict[str, str]], kind: str, ref: Any) -> None:
    normalized = str(ref or "").strip()
    if normalized:
        refs.append({"kind": kind, "ref": normalized})


def _dedupe_refs(refs: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in refs:
        key = (item["kind"], item["ref"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
