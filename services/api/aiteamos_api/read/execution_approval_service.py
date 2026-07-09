"""Governed approval records for runtime execution requests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .chat_action_plan import ChatActionPlan
from .execution_contract import ExecutionRequest, ExecutionResult
from .execution_dispatch_service import ExecutionDispatchService
from .execution_session_store import load_execution_state_snapshot, save_execution_state_snapshot
from .runtime_executors.base import blocked_result, utc_now
from .ticket_service import TicketReportRequest, add_ticket_report


class ExecutionApprovalRecord(BaseModel):
    id: str
    status: str = "requested"
    kind: str = "runtime_approval"
    ticket_id: str = ""
    employee_id: str = ""
    executor_id: str = ""
    required_capability: str = ""
    risk_level: str = ""
    reason: str = ""
    proposed_action: dict[str, Any] = Field(default_factory=dict)
    source_state_ref: str = ""
    source_state_snapshot_ref: str = ""
    current_graph_node: str = ""
    checkpoint_ref: str = ""
    executor_session_ref: str = ""
    approval_request: dict[str, Any] = Field(default_factory=dict)
    source_request: dict[str, Any] = Field(default_factory=dict)
    source_result: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    reviewed_at: str = ""
    reviewer_employee_id: str = ""
    review_reason: str = ""
    last_run_request_id: str = ""
    last_run_status: str = ""
    last_ingestion_blocker: str = ""
    last_result: dict[str, Any] = Field(default_factory=dict)
    resume_result: dict[str, Any] = Field(default_factory=dict)
    run_history: list[dict[str, Any]] = Field(default_factory=list)


class ExecutionApprovalReviewRequest(BaseModel):
    status: str = "approved"
    reviewer_employee_id: str = "clara"
    reason: str = ""


class ExecutionApprovalRunRequest(BaseModel):
    employee_id: str = ""
    workspace_id: str = ""
    message: str = ""
    runtime_config: dict[str, Any] = Field(default_factory=dict)
    ingest_result: bool = True


class ExecutionApprovalRunResponse(BaseModel):
    approval: dict[str, Any]
    request: dict[str, Any]
    result: dict[str, Any]
    ingested: bool = False
    ingestion_blocker: str = ""


_REVIEW_STATUS_ALIASES = {
    "approved": "approved",
    "approve": "approved",
    "rejected": "rejected",
    "reject": "rejected",
    "request_changes": "changes_requested",
    "changes_requested": "changes_requested",
    "needs_changes": "changes_requested",
    "ask_evidence": "evidence_requested",
    "request_evidence": "evidence_requested",
    "evidence_requested": "evidence_requested",
    "needs_evidence": "evidence_requested",
}


def list_execution_approvals(*, workspace_dir: Path, status: str = "") -> list[ExecutionApprovalRecord]:
    records = _load_records(workspace_dir)
    normalized = status.strip().lower()
    if normalized:
        records = [record for record in records if record.status == normalized]
    return sorted(records, key=lambda item: item.updated_at or item.created_at, reverse=True)


def get_execution_approval(*, workspace_dir: Path, approval_id: str) -> ExecutionApprovalRecord | None:
    normalized = approval_id.strip()
    return next((record for record in _load_records(workspace_dir) if record.id == normalized), None)


def record_execution_approval_requests(
    *,
    workspace_dir: Path,
    request: ExecutionRequest,
    result: ExecutionResult,
) -> list[ExecutionApprovalRecord]:
    if not result.approval_requests:
        return []
    records = _load_records(workspace_dir)
    by_id = {record.id: record for record in records}
    timestamp = utc_now()
    created: list[ExecutionApprovalRecord] = []
    for index, approval_request in enumerate(result.approval_requests):
        if not isinstance(approval_request, dict):
            continue
        record_id = _approval_record_id(request.request_id, index)
        current = by_id.get(record_id)
        payload = _approval_record_payload(record_id, approval_request, request, result, timestamp, workspace_dir)
        if current is not None:
            payload["status"] = current.status
            payload["created_at"] = current.created_at
            payload["reviewed_at"] = current.reviewed_at
            payload["reviewer_employee_id"] = current.reviewer_employee_id
            payload["review_reason"] = current.review_reason
            payload["last_run_request_id"] = current.last_run_request_id
            payload["last_run_status"] = current.last_run_status
            payload["last_ingestion_blocker"] = current.last_ingestion_blocker
            payload["last_result"] = current.last_result
            payload["resume_result"] = current.resume_result
            payload["source_state_snapshot_ref"] = current.source_state_snapshot_ref or payload.get("source_state_snapshot_ref", "")
            payload["run_history"] = current.run_history
        record = ExecutionApprovalRecord(**payload)
        by_id[record_id] = record
        created.append(record)
    _save_records(workspace_dir, list(by_id.values()))
    for record in created:
        if record.status == "requested":
            _sync_ticket_loop_after_approval_request(record, workspace_dir=workspace_dir)
    return created


def review_execution_approval(
    *,
    workspace_dir: Path,
    approval_id: str,
    review: ExecutionApprovalReviewRequest,
) -> ExecutionApprovalRecord:
    status = _normalize_review_status(review.status)
    if not status:
        raise ValueError("Execution approval review status must be approved, rejected, changes_requested, or evidence_requested.")
    records = _load_records(workspace_dir)
    timestamp = utc_now()
    for index, record in enumerate(records):
        if record.id != approval_id:
            continue
        reviewed = record.model_copy(
            update={
                "status": status,
                "reviewed_at": timestamp,
                "updated_at": timestamp,
                "reviewer_employee_id": review.reviewer_employee_id,
                "review_reason": review.reason,
            }
        )
        records[index] = reviewed
        _save_records(workspace_dir, records)
        _record_approval_review_report(reviewed)
        _sync_ticket_loop_after_approval_review(reviewed, workspace_dir=workspace_dir)
        return reviewed
    raise KeyError(approval_id)


class ExecutionApprovalRunService:
    def __init__(
        self,
        *,
        workspace_dir: Path,
        dispatch_service: ExecutionDispatchService | None = None,
        ingestion_service: Any | None = None,
    ) -> None:
        from .execution_result_ingestion_service import ExecutionResultIngestionService

        self.workspace_dir = workspace_dir
        self.dispatch_service = dispatch_service or ExecutionDispatchService()
        self.ingestion_service = ingestion_service or ExecutionResultIngestionService(workspace_dir=workspace_dir)

    async def run(self, executor_id: str, approval_id: str, run_request: ExecutionApprovalRunRequest) -> ExecutionApprovalRunResponse:
        executor_id = executor_id.strip().replace("-", "_")
        approval = await asyncio.to_thread(get_execution_approval, workspace_dir=self.workspace_dir, approval_id=approval_id)
        if approval is None:
            result = self._blocked_result(executor_id, approval_id, "runtime_approval_not_found", f"Execution approval was not found: {approval_id}")
            return ExecutionApprovalRunResponse(approval={}, request={}, result=result.model_dump(mode="json"))
        if approval.executor_id != executor_id:
            result = self._blocked_result(
                executor_id,
                approval_id,
                "runtime_approval_executor_mismatch",
                f"Approval {approval_id} belongs to executor {approval.executor_id}, not {executor_id}.",
            )
            return ExecutionApprovalRunResponse(approval=approval.model_dump(mode="json"), request={}, result=result.model_dump(mode="json"))
        if approval.status != "approved":
            result = self._blocked_result(
                executor_id,
                approval_id,
                "runtime_approval_not_approved",
                f"Execution approval {approval_id} must be approved before runtime dispatch.",
            )
            return ExecutionApprovalRunResponse(approval=approval.model_dump(mode="json"), request={}, result=result.model_dump(mode="json"))

        request = self._approved_execution_request(approval, run_request)
        result = await self.dispatch_service.dispatch(request)
        ingested = False
        ingestion_blocker = ""
        if run_request.ingest_result:
            result = await asyncio.to_thread(self.ingestion_service.ingest, request, result)
            ingested = result.status in {"completed", "partial", "needs_approval"}
            if not ingested:
                ingestion_blocker = result.errors[-1]["detail"] if result.errors else result.report
        approval = await asyncio.to_thread(self._record_run_result, approval.id, request, result, ingestion_blocker=ingestion_blocker)
        return ExecutionApprovalRunResponse(
            approval=approval.model_dump(mode="json"),
            request=request.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
            ingested=ingested,
            ingestion_blocker=ingestion_blocker,
        )

    def _approved_execution_request(self, approval: ExecutionApprovalRecord, run_request: ExecutionApprovalRunRequest) -> ExecutionRequest:
        source_request = ExecutionRequest.model_validate(approval.source_request)
        required_capability = approval.required_capability or "repo:write"
        runtime_config = dict(run_request.runtime_config)
        permission_policy = dict(source_request.permission_policy)
        permission_policy["selected_ai_engine"] = approval.executor_id
        permission_policy["selected_executor"] = approval.executor_id
        if runtime_config:
            permission_policy["runtime_config"] = {approval.executor_id: runtime_config}

        approval_policy = dict(source_request.approval_policy)
        approved_capabilities = set(str(item) for item in approval_policy.get("approved_capabilities") or [])
        approved_capabilities.add(required_capability)
        approval_refs = set(str(item) for item in approval_policy.get("approval_refs") or [])
        approval_refs.add(approval.id)
        approval_policy["approved_capabilities"] = sorted(approved_capabilities)
        approval_policy["approval_refs"] = sorted(approval_refs)

        capability_grants = set(source_request.capability_grants)
        capability_grants.add(required_capability)
        capability_grants.add("ticket:evidence:write")
        capability_grants.add("repo:read")
        action_plan = source_request.action_plan
        if run_request.message.strip():
            arguments = dict(action_plan.arguments)
            arguments["message"] = run_request.message.strip()
            action_plan = action_plan.model_copy(update={"arguments": arguments})

        trace_context = dict(source_request.trace_context)
        attempt_number = len(approval.run_history) + 1
        trace_context["approval_ref"] = approval.id
        trace_context["source_request_id"] = source_request.request_id
        trace_context["run_id"] = f"{source_request.request_id}-approved-attempt-{attempt_number}"
        trace_context["trace_ref"] = trace_context.get("trace_ref") or f".aiteamos/traces/{source_request.request_id}-approved.jsonl"
        trace_context["resume_from_checkpoint_ref"] = approval.checkpoint_ref
        trace_context["resume_from_executor_session_ref"] = approval.executor_session_ref
        trace_context["source_state_ref"] = approval.source_state_ref
        trace_context["resume_source_state_snapshot_ref"] = approval.source_state_snapshot_ref
        trace_context["resume_graph_node"] = approval.current_graph_node
        trace_context["approval_resume"] = True
        snapshot = load_execution_state_snapshot(self.workspace_dir, approval.source_state_ref)
        if snapshot is not None:
            trace_context["resume_source"] = "checkpoint_state"
            trace_context["resume_snapshot_schema"] = str(snapshot.get("snapshot_schema") or "")
        else:
            trace_context["resume_source"] = "checkpoint_ref"
        task_context = dict(source_request.task_context)
        if snapshot is not None:
            task_context["resume_checkpoint_state"] = _compact_state_snapshot(snapshot)
        return source_request.model_copy(
            update={
                "request_id": f"{source_request.request_id}-approved-{approval.id}-attempt-{attempt_number}",
                "workspace_id": run_request.workspace_id.strip() or source_request.workspace_id,
                "employee_id": source_request.employee_id,
                "action_plan": action_plan,
                "capability_grants": sorted(capability_grants),
                "permission_policy": permission_policy,
                "approval_policy": approval_policy,
                "expected_outputs": {**source_request.expected_outputs, "evidence": True, "artifacts": True},
                "task_context": task_context,
                "trace_context": trace_context,
            }
        )

    def _record_run_result(
        self,
        approval_id: str,
        request: ExecutionRequest,
        result: ExecutionResult,
        *,
        ingestion_blocker: str = "",
    ) -> ExecutionApprovalRecord:
        records = _load_records(self.workspace_dir)
        timestamp = utc_now()
        for index, record in enumerate(records):
            if record.id != approval_id:
                continue
            history_item = {
                "run_request_id": request.request_id,
                "status": result.status,
                "ingested": not ingestion_blocker and result.status in {"completed", "partial", "needs_approval"},
                "ingestion_blocker": ingestion_blocker,
                "executor_id": result.executor_id,
                "trace_ref": result.trace_ref or str(request.trace_context.get("trace_ref") or ""),
                "resume_source": str(request.trace_context.get("resume_source") or ""),
                "resume_source_state_snapshot_ref": str(request.trace_context.get("resume_source_state_snapshot_ref") or ""),
                "executor_session_ref": result.executor_session_ref,
                "checkpoint_ref": result.checkpoint_ref,
                "approval_refs": list(request.approval_policy.get("approval_refs") or []),
                "approved_capabilities": list(request.approval_policy.get("approved_capabilities") or []),
                "artifact_count": len(result.artifacts),
                "evidence_count": len(result.evidence),
                "error_count": len(result.errors),
                "report": result.report[:600],
                "result": result.model_dump(mode="json"),
                "created_at": timestamp,
            }
            records[index] = record.model_copy(
                update={
                    "updated_at": timestamp,
                    "last_run_request_id": request.request_id,
                "last_run_status": result.status,
                "last_ingestion_blocker": ingestion_blocker,
                "last_result": result.model_dump(mode="json"),
                "resume_result": {
                    "run_request_id": request.request_id,
                    "status": result.status,
                    "resumed_from_checkpoint_ref": record.checkpoint_ref,
                    "resumed_from_executor_session_ref": record.executor_session_ref,
                    "source_state_ref": record.source_state_ref,
                    "source_state_snapshot_ref": record.source_state_snapshot_ref,
                    "resume_source": str(request.trace_context.get("resume_source") or ""),
                    "current_graph_node": record.current_graph_node,
                    "result_checkpoint_ref": result.checkpoint_ref,
                    "ingestion_blocker": ingestion_blocker,
                },
                "run_history": [*record.run_history, history_item],
            }
            )
            _save_records(self.workspace_dir, records)
            return records[index]
        raise KeyError(approval_id)

    def _blocked_result(self, executor_id: str, approval_id: str, reason: str, detail: str) -> ExecutionResult:
        request = ExecutionRequest(
            request_id=f"approval-{approval_id}",
            employee_id="system",
            action_plan=ChatActionPlan(action="implement_ticket", arguments={}),
        )
        return blocked_result(request, executor_id=executor_id, reason=reason, detail=detail)


def _approval_record_id(request_id: str, index: int) -> str:
    return f"approval-{request_id}-{index + 1}"


def _approval_record_payload(
    record_id: str,
    approval_request: dict[str, Any],
    request: ExecutionRequest,
    result: ExecutionResult,
    timestamp: str,
    workspace_dir: Path,
) -> dict[str, Any]:
    source_state_ref = str(approval_request.get("source_state_ref") or "")
    checkpoint_ref = str(approval_request.get("checkpoint_ref") or result.checkpoint_ref or "")
    executor_session_ref = str(approval_request.get("executor_session_ref") or result.executor_session_ref or "")
    current_graph_node = str(approval_request.get("current_graph_node") or "")
    source_request_payload = request.model_dump(mode="json")
    source_result_payload = result.model_dump(mode="json")
    snapshot_ref = save_execution_state_snapshot(
        workspace_dir,
        source_state_ref=source_state_ref,
        checkpoint_ref=checkpoint_ref,
        executor_session_ref=executor_session_ref,
        current_graph_node=current_graph_node,
        request=source_request_payload,
        result=source_result_payload,
        approval_request=approval_request,
    )
    return {
        "id": record_id,
        "status": "requested",
        "kind": str(approval_request.get("kind") or "runtime_approval"),
        "ticket_id": str(approval_request.get("ticket_id") or request.ticket_id or request.ticket_binding.ticket_id or ""),
        "employee_id": request.employee_id,
        "executor_id": str(approval_request.get("executor_id") or result.executor_id),
        "required_capability": str(approval_request.get("required_capability") or "repo:write"),
        "risk_level": str(approval_request.get("risk_level") or "high"),
        "reason": str(approval_request.get("reason") or result.report),
        "proposed_action": approval_request.get("proposed_action") if isinstance(approval_request.get("proposed_action"), dict) else {},
        "source_state_ref": source_state_ref,
        "source_state_snapshot_ref": snapshot_ref,
        "current_graph_node": current_graph_node,
        "checkpoint_ref": checkpoint_ref,
        "executor_session_ref": executor_session_ref,
        "approval_request": approval_request,
        "source_request": source_request_payload,
        "source_result": source_result_payload,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _normalize_review_status(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return _REVIEW_STATUS_ALIASES.get(normalized, "")


def _compact_state_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    graph_state = snapshot.get("graph_state") if isinstance(snapshot.get("graph_state"), dict) else {}
    return {
        "source_state_ref": str(snapshot.get("source_state_ref") or ""),
        "source_state_snapshot_ref": str(snapshot.get("source_state_snapshot_ref") or ""),
        "checkpoint_ref": str(snapshot.get("checkpoint_ref") or ""),
        "executor_session_ref": str(snapshot.get("executor_session_ref") or ""),
        "current_graph_node": str(snapshot.get("current_graph_node") or ""),
        "snapshot_schema": str(snapshot.get("snapshot_schema") or ""),
        "approval_interrupt": graph_state.get("approval_interrupt") if isinstance(graph_state.get("approval_interrupt"), dict) else {},
        "tool_event_count": len(graph_state.get("tool_events") or []) if isinstance(graph_state.get("tool_events"), list) else 0,
        "error_count": len(graph_state.get("errors") or []) if isinstance(graph_state.get("errors"), list) else 0,
        "request_id": str(snapshot.get("request_id") or ""),
    }


def _record_approval_review_report(record: ExecutionApprovalRecord) -> None:
    if not record.ticket_id:
        return
    status_label = {
        "approved": "approved",
        "rejected": "rejected",
        "changes_requested": "sent back for changes",
        "evidence_requested": "sent back for more evidence",
    }.get(record.status, record.status or "reviewed")
    no_mutation_line = (
        "No external runtime mutation was executed. This review action only records governance state."
        if record.status != "approved"
        else "External runtime mutation is approved but still requires the governed resume/run path."
    )
    content = "\n".join(
        line
        for line in [
            f"Runtime approval {status_label}: {record.id}.",
            f"Capability: {record.required_capability or '-'}; executor: {record.executor_id or '-'}.",
            f"Reason: {record.review_reason or record.reason or 'No review reason recorded.'}",
            f"Checkpoint ref: {record.checkpoint_ref or '-'}.",
            f"State ref: {record.source_state_ref or '-'}.",
            no_mutation_line,
        ]
        if line
    )
    try:
        add_ticket_report(
            record.ticket_id,
            TicketReportRequest(
                reporter_employee_id=record.reviewer_employee_id or "clara",
                reporter_role="AI Team OS Manager",
                content=content,
                evidence=[ref for ref in [record.checkpoint_ref, record.source_state_ref] if ref],
                report_type=f"approval_{record.status}",
                source_run_id=record.id,
            ),
        )
    except Exception:
        # Approval review must remain durable even if the Ticket provider is temporarily unavailable.
        return


def _sync_ticket_loop_after_approval_review(record: ExecutionApprovalRecord, *, workspace_dir: Path) -> None:
    try:
        from .ticket_loop_service import sync_ticket_loop_after_approval_review

        sync_ticket_loop_after_approval_review(record, workspace_dir=workspace_dir)
    except Exception:
        # Approval review must remain durable even if Ticket loop state sync is temporarily unavailable.
        return


def _sync_ticket_loop_after_approval_request(record: ExecutionApprovalRecord, *, workspace_dir: Path) -> None:
    try:
        from .ticket_loop_service import sync_ticket_loop_after_approval_request

        sync_ticket_loop_after_approval_request(record, workspace_dir=workspace_dir)
    except Exception:
        # Approval records must remain durable even if Ticket loop state sync is temporarily unavailable.
        return


def _approval_path(workspace_dir: Path) -> Path:
    return workspace_dir / "execution_approvals.json"


def _load_records(workspace_dir: Path) -> list[ExecutionApprovalRecord]:
    path = _approval_path(workspace_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload if isinstance(payload, list) else payload.get("approvals", []) if isinstance(payload, dict) else []
    return [ExecutionApprovalRecord.model_validate(item) for item in items if isinstance(item, dict)]


def _save_records(workspace_dir: Path, records: list[ExecutionApprovalRecord]) -> None:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    path = _approval_path(workspace_dir)
    payload = [record.model_dump(mode="json") for record in sorted(records, key=lambda item: item.created_at)]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
