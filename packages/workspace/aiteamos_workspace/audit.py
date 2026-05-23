from __future__ import annotations

from datetime import datetime
from typing import Any


def decision_audit_record(
    index: Any,
    *,
    decision_kind: str,
    decision: str,
    actor_member: str | None = None,
    authority: str = "record",
    reason: str | None = None,
    source: str | None = None,
    decided_at: str | None = None,
    policy_refs: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    requires_human_review: bool = False,
    risk: dict[str, Any] | None = None,
    risk_assessment: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actor_kind = None
    if actor_member:
        member = getattr(index, "members", {}).get(actor_member)
        actor_kind = member.spec.kind if member else None
    record: dict[str, Any] = {
        "decisionKind": decision_kind,
        "decision": decision,
        "actorMember": actor_member,
        "actorMemberKind": actor_kind,
        "authority": authority,
        "decidedAt": decided_at or datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "reason": reason,
        "source": source,
        "policyRefs": policy_refs or [],
        "evidence": evidence or [],
        "requiresHumanReview": requires_human_review,
        "riskAssessment": risk_assessment,
        "risk": risk or {},
        "metadata": metadata or {},
    }
    return {
        key: value
        for key, value in record.items()
        if value is not None and value != [] and value != {}
    }


def latest_decision_audit(records: list[Any]) -> dict[str, Any]:
    if not records:
        return {}
    last = records[-1]
    if hasattr(last, "model_dump"):
        return last.model_dump(mode="json", exclude_none=True)
    if isinstance(last, dict):
        return dict(last)
    return {}
