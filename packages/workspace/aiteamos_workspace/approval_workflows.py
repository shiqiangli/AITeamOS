from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Any

from aiteamos_schema import ApprovalWorkflow

from .io import read_yaml, write_yaml
from .loader import load_workspace


DEFAULT_APPROVAL_SLA_SECONDS = 86_400
APPROVAL_WORKFLOW_ESCALATION_SOURCE = "approval-workflow-sla-escalation"
OPEN_ESCALATION_MESSAGE_STATUSES = {"open", "acknowledged"}
RISK_QUORUM_STAGE_ID = "risk-quorum"
RISK_QUORUM_SIZE = 2
RISK_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def approval_workflow_id(subject_kind: str, subject_ref: str) -> str:
    return f"AWF-{_safe_fragment(subject_kind)}-{_safe_fragment(subject_ref)}"


def write_subject_approval_workflow(
    index: Any,
    *,
    subject_kind: str,
    subject_ref: str,
    project: str | None,
    requester_member: str | None = None,
    owner_member: str | None = None,
    status: str = "pending",
    stage_id: str = "approval-review",
    stage_kind: str = "any-of",
    reviewer_members: list[str] | None = None,
    reviewer_kinds: list[str] | None = None,
    approvals: list[str] | None = None,
    decision_audit: list[dict[str, Any]] | None = None,
    subject_record: dict[str, Any] | None = None,
    escalation_target_member: str | None = None,
    reason: str | None = None,
    decided_at: str | None = None,
) -> ApprovalWorkflow:
    workflow_id = approval_workflow_id(subject_kind, subject_ref)
    workflow_path = index.workspace_root / "approval_workflows" / f"{workflow_id}.yaml"
    existing = _read_existing(workflow_path)
    created_at = existing.get("metadata", {}).get("createdAt") or datetime.now().astimezone().isoformat(timespec="milliseconds")
    risk_assessment = _highest_risk_assessment(decision_audit or [])
    risk_quorum = _requires_risk_quorum(risk_assessment)
    if risk_quorum:
        stage_id = RISK_QUORUM_STAGE_ID
        stage_kind = "quorum"
        reviewer_kinds = reviewer_kinds or ["human", "hybrid"]
        reviewer_members = _quorum_reviewer_members(index, reviewer_members, reviewer_kinds)
        escalation_target_member = escalation_target_member or _default_escalation_target(index)
    stage_status = _stage_status(status)
    stage: dict[str, Any] = {
        "id": stage_id,
        "kind": stage_kind,
        "reviewerMembers": reviewer_members or [],
        "reviewerKinds": reviewer_kinds or ["human", "hybrid"],
        "sla": {
            "durationSeconds": DEFAULT_APPROVAL_SLA_SECONDS,
            "startsAt": "stage-entered",
        },
        "approvals": approvals or [],
        "status": stage_status,
    }
    if stage_kind == "quorum":
        stage["quorum"] = RISK_QUORUM_SIZE
    if escalation_target_member:
        stage["escalation"] = {
            "targetMember": escalation_target_member,
            "afterSlaBreach": True,
            "messageType": "review-request",
            "reason": "SLA breach requires manager review.",
        }
    spec: dict[str, Any] = {
        "project": project,
        "subjectKind": subject_kind,
        "subjectRef": subject_ref,
        "requesterMember": requester_member,
        "ownerMember": owner_member,
        "status": _workflow_status(status),
        "stages": [stage],
        "createdAt": created_at,
        "updatedAt": decided_at or datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "decisionAudit": decision_audit or [],
        "audit": {
            "source": "approval-workflow-api",
            "subjectKind": subject_kind,
            "subjectRef": subject_ref,
        },
    }
    if subject_record:
        spec["audit"]["subjectRecord"] = subject_record
    if spec["status"] in {"pending", "draft", "escalated"}:
        spec["currentStage"] = stage_id
    else:
        spec["completedAt"] = decided_at or spec["updatedAt"]
    if reason:
        spec["audit"]["reason"] = reason
    if risk_quorum and risk_assessment:
        spec["audit"]["riskRouting"] = {
            "rule": "risk-level-quorum",
            "riskLevel": risk_assessment.get("riskLevel"),
            "recommendedDecision": risk_assessment.get("recommendedDecision"),
            "stageId": stage_id,
            "stageKind": stage_kind,
            "quorum": RISK_QUORUM_SIZE,
        }

    workflow = ApprovalWorkflow.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "ApprovalWorkflow",
            "metadata": {
                "id": workflow_id,
                "title": f"{subject_kind} approval workflow for {subject_ref}",
                "createdAt": created_at,
            },
            "spec": spec,
        }
    )
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(workflow_path, workflow.model_dump(mode="json", exclude_none=True))
    return workflow


def escalate_overdue_approval_workflows(
    workspace_path: str | Path,
    *,
    now: str | None = None,
    actor_member: str | None = None,
) -> list[dict[str, Any]]:
    index = load_workspace(workspace_path)
    now_dt = _current_time(now)
    now_iso = now_dt.isoformat(timespec="milliseconds")
    escalations: list[dict[str, Any]] = []

    for workflow_id, workflow in sorted(index.approval_workflows.items()):
        if workflow.spec.status != "pending" or not workflow.spec.currentStage:
            continue
        workflow_path = index.workspace_root / "approval_workflows" / f"{workflow_id}.yaml"
        workflow_data = _read_existing(workflow_path)
        spec = workflow_data.get("spec", {})
        stage = _current_stage_data(spec, workflow.spec.currentStage)
        if not stage or stage.get("status", "pending") != "pending":
            continue
        escalation = _plain_dict(stage.get("escalation"))
        if not escalation.get("afterSlaBreach", True):
            continue
        target_member = str(escalation.get("targetMember") or "")
        if target_member not in index.members:
            continue
        due_at = _stage_due_at(workflow_data, stage, now_dt)
        if due_at is None or now_dt < due_at:
            continue

        dedupe_key = f"approval-workflow:{workflow_id}:{workflow.spec.currentStage}:sla"
        existing_message = _existing_open_escalation_message(index, dedupe_key)
        if existing_message:
            message_id = existing_message
            created_message = None
        else:
            from_member = _escalation_actor_member(index, actor_member, spec, target_member)
            created_message = _record_escalation_message(
                workspace_path,
                from_member=from_member,
                target_member=target_member,
                workflow_id=workflow_id,
                workflow_spec=spec,
                stage_id=workflow.spec.currentStage,
                due_at=due_at.isoformat(timespec="milliseconds"),
                now=now_iso,
                dedupe_key=dedupe_key,
            )
            message_id = created_message.object_id

        stage["status"] = "escalated"
        escalation.setdefault("reason", "SLA breach requires manager review.")
        stage["escalation"] = escalation
        spec["status"] = "escalated"
        spec["currentStage"] = workflow.spec.currentStage
        spec["updatedAt"] = now_iso
        spec.setdefault("audit", {})["slaEscalation"] = {
            "message": message_id,
            "stageId": workflow.spec.currentStage,
            "targetMember": target_member,
            "dueAt": due_at.isoformat(timespec="milliseconds"),
            "escalatedAt": now_iso,
            "dedupeKey": dedupe_key,
        }
        audit_actor = _escalation_actor_member(index, actor_member, spec, target_member)
        spec.setdefault("decisionAudit", []).append(
            {
                "decisionKind": "system_check",
                "decision": "escalated",
                "actorMember": audit_actor,
                "actorMemberKind": _member_kind(index, audit_actor),
                "authority": "record",
                "decidedAt": now_iso,
                "reason": "Approval workflow SLA breached; manager review request routed.",
                "source": APPROVAL_WORKFLOW_ESCALATION_SOURCE,
                "evidence": [
                    {
                        "kind": "ApprovalWorkflow",
                        "id": workflow_id,
                        "stageId": workflow.spec.currentStage,
                        "dueAt": due_at.isoformat(timespec="milliseconds"),
                        "message": message_id,
                    }
                ],
                "requiresHumanReview": True,
                "metadata": {"approvalWorkflowEscalationDedupeKey": dedupe_key},
            }
        )
        updated_workflow = ApprovalWorkflow.model_validate(workflow_data)
        write_yaml(workflow_path, updated_workflow.model_dump(mode="json", exclude_none=True))
        escalations.append(
            {
                "workflow": workflow_id,
                "stage": workflow.spec.currentStage,
                "message": message_id,
                "targetMember": target_member,
                "dueAt": due_at.isoformat(timespec="milliseconds"),
                "createdMessage": created_message is not None,
            }
        )

    return escalations


def _read_existing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = read_yaml(path)
    return data if isinstance(data, dict) else {}


def _workflow_status(status: str) -> str:
    if status in {"approved", "rejected", "expired", "cancelled", "escalated", "draft", "pending"}:
        return status
    if status in {"queued", "running", "succeeded"}:
        return "approved"
    if status in {"blocked", "failed"}:
        return "rejected"
    return "pending"


def _stage_status(status: str) -> str:
    if status == "approved":
        return "satisfied"
    if status in {"rejected", "blocked", "failed"}:
        return "rejected"
    if status == "expired":
        return "expired"
    if status == "escalated":
        return "escalated"
    return "pending"


def _safe_fragment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return cleaned or "unknown"


def _highest_risk_assessment(decision_audit: list[dict[str, Any]]) -> dict[str, Any] | None:
    selected: dict[str, Any] | None = None
    selected_score = -1
    for record in decision_audit:
        payload = _plain_dict(record)
        risk = _plain_dict(payload.get("riskAssessment"))
        risk_level = str(risk.get("riskLevel") or "").lower()
        score = RISK_SEVERITY_ORDER.get(risk_level, -1)
        if score > selected_score:
            selected = risk
            selected_score = score
    return selected


def _requires_risk_quorum(risk_assessment: dict[str, Any] | None) -> bool:
    if not risk_assessment:
        return False
    risk_level = str(risk_assessment.get("riskLevel") or "").lower()
    return RISK_SEVERITY_ORDER.get(risk_level, -1) >= RISK_SEVERITY_ORDER["high"]


def _quorum_reviewer_members(index: Any, reviewer_members: list[str] | None, reviewer_kinds: list[str] | None) -> list[str]:
    selected = list(dict.fromkeys(reviewer_members or []))
    if len(selected) >= RISK_QUORUM_SIZE:
        return selected
    allowed_kinds = set(reviewer_kinds or ["human", "hybrid"])
    for member_id, member in sorted(getattr(index, "members", {}).items()):
        if member_id in selected:
            continue
        if getattr(member.spec, "kind", None) in allowed_kinds:
            selected.append(member_id)
        if len(selected) >= RISK_QUORUM_SIZE:
            return selected
    return selected if len(selected) >= RISK_QUORUM_SIZE else []


def _default_escalation_target(index: Any) -> str | None:
    for member_id in ["manager", "aiteamos-manager"]:
        if member_id in getattr(index, "members", {}):
            return member_id
    return None


def _current_stage_data(spec: dict[str, Any], stage_id: str) -> dict[str, Any] | None:
    for stage in spec.get("stages", []):
        if isinstance(stage, dict) and stage.get("id") == stage_id:
            return stage
    return None


def _stage_due_at(workflow_data: dict[str, Any], stage: dict[str, Any], now: datetime) -> datetime | None:
    sla = _plain_dict(stage.get("sla"))
    if sla.get("dueAt"):
        due_at = _parse_datetime(str(sla["dueAt"]))
        return _with_fallback_timezone(due_at, now)
    started_at = _stage_started_at(workflow_data, stage, str(sla.get("startsAt") or "stage-entered"), now)
    if started_at is None:
        return None
    return started_at + timedelta(seconds=int(sla.get("durationSeconds") or DEFAULT_APPROVAL_SLA_SECONDS))


def _stage_started_at(workflow_data: dict[str, Any], stage: dict[str, Any], starts_at: str, now: datetime) -> datetime | None:
    spec = workflow_data.get("spec", {})
    metadata = workflow_data.get("metadata", {})
    if starts_at == "workflow-created":
        candidates = [spec.get("createdAt"), metadata.get("createdAt")]
    elif starts_at == "previous-stage-completed":
        candidates = [stage.get("previousStageCompletedAt"), spec.get("updatedAt"), spec.get("createdAt"), metadata.get("createdAt")]
    else:
        candidates = [stage.get("enteredAt"), spec.get("updatedAt"), spec.get("createdAt"), metadata.get("createdAt")]
    for candidate in candidates:
        if not candidate:
            continue
        return _with_fallback_timezone(_parse_datetime(str(candidate)), now)
    return None


def _existing_open_escalation_message(index: Any, dedupe_key: str) -> str | None:
    for message in getattr(index, "member_messages", {}).values():
        if message.spec.audit.get("approvalWorkflowEscalationDedupeKey") != dedupe_key:
            continue
        if message.spec.status in OPEN_ESCALATION_MESSAGE_STATUSES:
            return message.object_id
    return None


def _record_escalation_message(
    workspace_path: str | Path,
    *,
    from_member: str,
    target_member: str,
    workflow_id: str,
    workflow_spec: dict[str, Any],
    stage_id: str,
    due_at: str,
    now: str,
    dedupe_key: str,
) -> Any:
    from .mutations import record_member_message

    subject_kind = workflow_spec.get("subjectKind")
    subject_ref = workflow_spec.get("subjectRef")
    return record_member_message(
        workspace_path,
        from_member=from_member,
        to_members=[target_member],
        message_type="review-request",
        priority="high",
        project=workflow_spec.get("project"),
        attachments=[workflow_id, str(subject_ref)],
        body=(
            f"Approval workflow {workflow_id} stage {stage_id} breached its SLA at {due_at}. "
            f"Please review {subject_kind} {subject_ref}."
        ),
        audit={
            "approvalWorkflowEscalationDedupeKey": dedupe_key,
            "approvalWorkflow": workflow_id,
            "approvalWorkflowStage": stage_id,
            "subjectKind": subject_kind,
            "subjectRef": subject_ref,
            "targetMember": target_member,
            "slaDueAt": due_at,
            "escalatedAt": now,
        },
        source=APPROVAL_WORKFLOW_ESCALATION_SOURCE,
    )


def _escalation_actor_member(index: Any, actor_member: str | None, spec: dict[str, Any], target_member: str) -> str:
    for member_id in [actor_member, spec.get("ownerMember"), spec.get("requesterMember"), target_member]:
        if member_id and member_id in getattr(index, "members", {}):
            return str(member_id)
    return target_member


def _member_kind(index: Any, member_id: str | None) -> str | None:
    if not member_id:
        return None
    member = getattr(index, "members", {}).get(member_id)
    return getattr(getattr(member, "spec", None), "kind", None)


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _current_time(value: str | None) -> datetime:
    current = _parse_datetime(value) if value else datetime.now().astimezone()
    return _with_fallback_timezone(current, datetime.now().astimezone())


def _with_fallback_timezone(value: datetime, fallback: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=fallback.tzinfo)
    return value


def _plain_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return dict(value)
    return {}
