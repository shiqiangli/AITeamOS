"""Read-only Chat visible-response contract matrix for Plan v8 evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .chat_response_metadata import build_visible_response_contract

CHAT_VISIBLE_RESPONSE_MATRIX_VERSION = "aiteamos_chat_visible_response_matrix.v1"
REQUIRED_VISIBLE_RESPONSE_STATES = (
    "completed",
    "blocked",
    "needs_approval",
    "handoff",
    "provider_blocker",
)


class ChatVisibleResponseMatrixCase(BaseModel):
    id: str
    expected_display_state: str
    status: str
    assistant_reply_visible: bool = False
    runtime_status_visible: bool = False
    required_evidence: list[str] = Field(default_factory=list)
    observed_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    visible_response: dict[str, Any] = Field(default_factory=dict)


class ChatVisibleResponseMatrixSummary(BaseModel):
    case_count: int = 0
    passed_case_count: int = 0
    failed_case_count: int = 0
    required_states: list[str] = Field(default_factory=list)
    observed_states: list[str] = Field(default_factory=list)
    missing_states: list[str] = Field(default_factory=list)
    assistant_reply_visible_count: int = 0
    runtime_status_visible_count: int = 0
    blocked_reason_visible_count: int = 0
    retry_cause_visible_count: int = 0
    approval_request_visible_count: int = 0
    handoff_visible_count: int = 0
    provider_blocker_visible_count: int = 0
    contract_version: str = CHAT_VISIBLE_RESPONSE_MATRIX_VERSION


class ChatVisibleResponseMatrixResponse(BaseModel):
    contract_version: str = CHAT_VISIBLE_RESPONSE_MATRIX_VERSION
    status: str
    detail: str
    summary: ChatVisibleResponseMatrixSummary = Field(default_factory=ChatVisibleResponseMatrixSummary)
    cases: list[ChatVisibleResponseMatrixCase] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)


def chat_visible_response_matrix_report(*, workspace_dir: Path | None = None) -> ChatVisibleResponseMatrixResponse:
    """Build deterministic contract fixtures for every user-visible Chat state."""

    del workspace_dir
    cases = [_build_case(fixture) for fixture in _fixtures()]
    observed_states = _unique([case.visible_response.get("display_state", "") for case in cases])
    missing_states = [state for state in REQUIRED_VISIBLE_RESPONSE_STATES if state not in observed_states]
    blockers = _unique([blocker for case in cases for blocker in case.blockers])
    if missing_states:
        blockers.extend([f"missing_state:{state}" for state in missing_states])
    status = "passed" if not blockers and all(case.status == "passed" for case in cases) else "blocked"
    summary = ChatVisibleResponseMatrixSummary(
        case_count=len(cases),
        passed_case_count=sum(1 for case in cases if case.status == "passed"),
        failed_case_count=sum(1 for case in cases if case.status != "passed"),
        required_states=list(REQUIRED_VISIBLE_RESPONSE_STATES),
        observed_states=observed_states,
        missing_states=missing_states,
        assistant_reply_visible_count=sum(1 for case in cases if case.assistant_reply_visible),
        runtime_status_visible_count=sum(1 for case in cases if case.runtime_status_visible),
        blocked_reason_visible_count=sum(1 for case in cases if "blocked_reason" in case.observed_evidence),
        retry_cause_visible_count=sum(1 for case in cases if "retry_cause" in case.observed_evidence),
        approval_request_visible_count=sum(1 for case in cases if "approval_request" in case.observed_evidence),
        handoff_visible_count=sum(1 for case in cases if "handoff_summary" in case.observed_evidence),
        provider_blocker_visible_count=sum(1 for case in cases if "provider_blocker" in case.observed_evidence),
    )
    return ChatVisibleResponseMatrixResponse(
        status=status,
        detail=(
            "Chat visible-response matrix covers completed, blocked, approval, handoff, and provider-blocker states."
            if status == "passed"
            else "Chat visible-response matrix is missing required user-visible state evidence."
        ),
        summary=summary,
        cases=cases,
        blockers=_unique(blockers),
        commands=[
            "python scripts/chat_visible_response_matrix.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-a-chat-visible-response-matrix.json"
        ],
    )


def _build_case(fixture: dict[str, Any]) -> ChatVisibleResponseMatrixCase:
    expected_state = str(fixture["expected_display_state"])
    reply = str(fixture["reply"])
    visible_response = build_visible_response_contract(
        reply=reply,
        run_metadata=_record(fixture.get("run_metadata")),
        ticket_keys=_strings(fixture.get("ticket_keys")),
        provider_blockers=_records(fixture.get("provider_blockers")),
        approval_requests=_records(fixture.get("approval_requests")),
        approval_records=_records(fixture.get("approval_records")),
        handoff_summary=_record(fixture.get("handoff_summary")),
        handoff_decision=_record(fixture.get("handoff_decision")),
        ticket_handoff_refs=_records(fixture.get("ticket_handoff_refs")),
        asset_candidates=_records(fixture.get("asset_candidates")),
        runtime_status=_record(fixture.get("runtime_status")),
    )
    observed = _observed_evidence(visible_response, expected_state=expected_state, expected_reply=reply)
    required = list(fixture["required_evidence"])
    missing = [item for item in required if item not in observed]
    blockers: list[str] = []
    if visible_response.get("version") != "chat_visible_response.v1":
        blockers.append("visible_response_contract_version_missing")
    if visible_response.get("display_state") != expected_state:
        blockers.append(f"visible_response_state_mismatch:{expected_state}")
    blockers.extend([f"missing_evidence:{item}" for item in missing])
    return ChatVisibleResponseMatrixCase(
        id=str(fixture["id"]),
        expected_display_state=expected_state,
        status="passed" if not blockers else "blocked",
        assistant_reply_visible="assistant_message" in observed,
        runtime_status_visible="runtime_status" in observed,
        required_evidence=required,
        observed_evidence=observed,
        missing_evidence=missing,
        blockers=blockers,
        visible_response=visible_response,
    )


def _observed_evidence(visible_response: dict[str, Any], *, expected_state: str, expected_reply: str) -> list[str]:
    evidence: list[str] = []
    assistant_message = _record(visible_response.get("assistant_message"))
    runtime_status = _record(visible_response.get("runtime_status"))
    if assistant_message.get("role") == "assistant" and assistant_message.get("content") == expected_reply:
        evidence.append("assistant_message")
    if visible_response.get("display_state") == expected_state:
        evidence.append("display_state")
    if runtime_status.get("display_state") == expected_state and runtime_status.get("status"):
        evidence.append("runtime_status")
    if _records(visible_response.get("ticket_refs")):
        evidence.append("ticket_refs")
    if _records(visible_response.get("asset_refs")):
        evidence.append("asset_refs")
    if str(visible_response.get("blocked_reason") or "").strip():
        evidence.append("blocked_reason")
    if str(visible_response.get("retry_cause") or "").strip():
        evidence.append("retry_cause")
    if _records(visible_response.get("approval_requests")) or _record(visible_response.get("approval_request")):
        evidence.append("approval_request")
    if _record(visible_response.get("handoff_summary")) or _records(visible_response.get("ticket_handoff_refs")):
        evidence.append("handoff_summary")
    if _records(visible_response.get("provider_blockers")):
        evidence.append("provider_blocker")
    return evidence


def _fixtures() -> list[dict[str, Any]]:
    return [
        {
            "id": "completed",
            "expected_display_state": "completed",
            "reply": "Completed visible reply.",
            "required_evidence": ["assistant_message", "display_state", "runtime_status", "ticket_refs"],
            "ticket_keys": ["rd-visible-completed"],
            "runtime_status": {"status": "completed", "current_node": "final_response", "executor_id": "langgraph"},
            "run_metadata": {
                "run_id": "run-visible-completed",
                "execution": {
                    "status": "completed",
                    "executor_id": "langgraph",
                    "request_id": "exec-visible-completed",
                    "ticket_binding": {"ticket_id": "rd-visible-completed"},
                    "result": {
                        "output_ticket_id": "rd-visible-completed",
                        "artifact_refs": [{"kind": "ticket_report", "ref": "report-visible-completed"}],
                    },
                },
            },
        },
        {
            "id": "blocked",
            "expected_display_state": "blocked",
            "reply": "Blocked visible reply.",
            "required_evidence": [
                "assistant_message",
                "display_state",
                "runtime_status",
                "blocked_reason",
                "retry_cause",
                "ticket_refs",
            ],
            "ticket_keys": ["rd-visible-blocked"],
            "runtime_status": {"status": "blocked", "current_node": "provider_write", "executor_id": "langgraph"},
            "run_metadata": {
                "run_id": "run-visible-blocked",
                "execution": {
                    "status": "blocked",
                    "executor_id": "langgraph",
                    "request_id": "exec-visible-blocked",
                    "ticket_binding": {"ticket_id": "rd-visible-blocked"},
                    "result": {
                        "output_ticket_id": "rd-visible-blocked",
                        "errors": [{"reason": "plane_write_failed", "detail": "Plane write failed."}],
                    },
                },
            },
        },
        {
            "id": "needs_approval",
            "expected_display_state": "needs_approval",
            "reply": "Approval visible reply.",
            "required_evidence": [
                "assistant_message",
                "display_state",
                "runtime_status",
                "approval_request",
                "ticket_refs",
            ],
            "ticket_keys": ["rd-visible-approval"],
            "runtime_status": {"status": "needs_approval", "current_node": "human_approval", "executor_id": "langgraph"},
            "approval_requests": [
                {
                    "approval_ref": "approval-visible-1",
                    "reason": "Approval required for repo:write.",
                    "scope": "repo_write",
                }
            ],
            "run_metadata": {
                "run_id": "run-visible-approval",
                "execution": {
                    "status": "needs_approval",
                    "executor_id": "langgraph",
                    "request_id": "exec-visible-approval",
                    "ticket_binding": {"ticket_id": "rd-visible-approval"},
                },
            },
        },
        {
            "id": "handoff",
            "expected_display_state": "handoff",
            "reply": "Handoff visible reply.",
            "required_evidence": [
                "assistant_message",
                "display_state",
                "runtime_status",
                "handoff_summary",
                "ticket_refs",
            ],
            "ticket_keys": ["rd-visible-handoff"],
            "runtime_status": {"status": "completed", "current_node": "handoff", "executor_id": "langgraph"},
            "handoff_summary": {
                "status": "handoff_ready",
                "from_employee_id": "clara",
                "to_employee_id": "alex",
                "reason": "Specialist implementation follow-up.",
            },
            "ticket_handoff_refs": [{"kind": "ticket_handoff", "ref": "handoff-visible-1"}],
            "run_metadata": {
                "run_id": "run-visible-handoff",
                "execution": {
                    "status": "completed",
                    "executor_id": "langgraph",
                    "request_id": "exec-visible-handoff",
                    "ticket_binding": {"ticket_id": "rd-visible-handoff"},
                },
            },
        },
        {
            "id": "provider_blocker",
            "expected_display_state": "provider_blocker",
            "reply": "Provider visible reply.",
            "required_evidence": [
                "assistant_message",
                "display_state",
                "runtime_status",
                "blocked_reason",
                "provider_blocker",
                "ticket_refs",
            ],
            "ticket_keys": ["rd-visible-provider"],
            "runtime_status": {"status": "completed", "current_node": "context_retrieval", "executor_id": "langgraph"},
            "provider_blockers": [
                {
                    "reason": "graphiti_setup_blocker",
                    "detail": "Graphiti setup is missing.",
                    "scope": "memory_provider",
                }
            ],
            "run_metadata": {
                "run_id": "run-visible-provider",
                "execution": {
                    "status": "completed",
                    "executor_id": "langgraph",
                    "request_id": "exec-visible-provider",
                    "ticket_binding": {"ticket_id": "rd-visible-provider"},
                },
            },
        },
    ]


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []


def _unique(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
