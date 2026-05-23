from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from aiteamos_schema import GitActivity

from ..audit import decision_audit_record
from ..io import write_yaml
from ..loader import WorkspaceIndex, load_workspace, manifest_to_record
from ..permissions import explain_effective_permissions
from .common import (
    GIT_ACTIVITY_EXPORT_POLICIES,
    GIT_ACTIVITY_LIFECYCLES,
    GIT_ACTIVITY_REDACTION_POLICIES,
    GIT_ACTIVITY_RETENTION_TARGETS,
    _evidence_ref,
    _is_sensitive_ref,
    _normalize_retention_now,
    _parse_git_activity_timestamp,
    _recommended_retention_lifecycle,
    _redacted_identifier,
    _redacted_ref_value,
    _unique,
)


def git_activity_retention_candidates(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """Return expired GitActivity retention candidates without mutating workspace state."""

    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    observed_now = _normalize_retention_now(now)
    candidates: list[dict[str, Any]] = []
    scoped_activities = [
        activity
        for activity in index.git_activities.values()
        if (project is None or activity.spec.project == project)
        and (member is None or activity.spec.member == member)
        and (assignment is None or activity.spec.assignment == assignment)
    ]
    for activity in sorted(scoped_activities, key=lambda item: item.object_id):
        retained_until = _parse_git_activity_timestamp(activity.spec.retainedUntil)
        if activity.spec.lifecycle != "active" or retained_until is None or retained_until > observed_now:
            continue
        recommended_lifecycle = _recommended_retention_lifecycle(activity)
        recommended_export_policy = "exclude" if recommended_lifecycle == "redacted" else "sanitize"
        warnings: list[str] = []
        if activity.spec.exportPolicy == "include":
            warnings.append("active include export policy should be reduced after retention expiry")
        if any(_is_sensitive_ref(ref) for ref in activity.spec.refs):
            warnings.append("refs contain sensitive or redacted metadata; redaction may be preferred")
        candidates.append(
            {
                "id": f"retention:{activity.object_id}",
                "kind": "GitActivityRetentionCandidate",
                "spec": {
                    "activity": activity.object_id,
                    "member": activity.spec.member,
                    "project": activity.spec.project,
                    "repository": activity.spec.repository,
                    "assignment": activity.spec.assignment,
                    "activityType": activity.spec.activityType,
                    "provider": activity.spec.provider,
                    "occurredAt": activity.spec.occurredAt,
                    "lifecycle": activity.spec.lifecycle,
                    "retainedUntil": activity.spec.retainedUntil,
                    "retentionExpiredAt": observed_now.isoformat(timespec="milliseconds"),
                    "retentionAgeHours": round(max(0.0, (observed_now - retained_until).total_seconds() / 3600.0), 3),
                    "exportPolicy": activity.spec.exportPolicy,
                    "redactionPolicy": activity.spec.redactionPolicy,
                    "recommendedLifecycle": recommended_lifecycle,
                    "recommendedExportPolicy": recommended_export_policy,
                    "recommendedRedactionPolicy": "redacted-summary" if recommended_lifecycle == "redacted" else None,
                    "eligible": True,
                    "blockers": [],
                    "warnings": warnings,
                    "evidence": activity.spec.evidence,
                },
            }
        )
    return {
        "kind": "GitActivityRetentionCandidates",
        "filters": {"project": project, "member": member, "assignment": assignment},
        "evaluatedAt": observed_now.isoformat(timespec="milliseconds"),
        "summary": {
            "scannedActivities": len(scoped_activities),
            "expiredCandidates": len(candidates),
            "redactionPreferred": sum(1 for item in candidates if item["spec"]["recommendedLifecycle"] == "redacted"),
            "archivePreferred": sum(1 for item in candidates if item["spec"]["recommendedLifecycle"] == "archived"),
        },
        "candidates": candidates,
    }

def sweep_git_activity_retention(
    workspace_path: str | Path,
    *,
    actor_member: str,
    target_lifecycle: str | None = None,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    now: str | datetime | None = None,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Archive or redact expired GitActivity evidence through the normal lifecycle gate."""

    index = load_workspace(workspace_path)
    actor = index.members.get(actor_member)
    if actor is None:
        raise KeyError(f"unknown actor member {actor_member}")
    if target_lifecycle is not None and target_lifecycle not in GIT_ACTIVITY_RETENTION_TARGETS:
        raise ValueError("targetLifecycle must be archived or redacted")
    candidate_set = git_activity_retention_candidates(index, project=project, member=member, assignment=assignment, now=now)
    selected_candidates = list(candidate_set["candidates"])
    if limit is not None:
        selected_candidates = selected_candidates[: max(0, int(limit))]
    updated: list[str] = []
    updated_records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for candidate in selected_candidates:
        spec = candidate["spec"]
        activity_id = str(spec["activity"])
        lifecycle = target_lifecycle or str(spec["recommendedLifecycle"])
        export_policy = "exclude" if lifecycle == "redacted" else "sanitize"
        redaction_policy = "redacted-summary" if lifecycle == "redacted" else None
        if dry_run:
            continue
        try:
            result = update_git_activity_evidence_lifecycle(
                workspace_path,
                activity_id,
                actor_member=actor_member,
                lifecycle=lifecycle,
                reason=f"GitActivity evidence reached retainedUntil {spec.get('retainedUntil')}; retention sweep changed lifecycle to {lifecycle}.",
                redaction_policy=redaction_policy,
                export_policy=export_policy,
            )
        except (KeyError, ValueError) as exc:
            errors.append({"activity": activity_id, "error": str(exc)})
            continue
        updated.append(activity_id)
        updated_records.append(manifest_to_record(result["activity"]))
    return {
        "dryRun": dry_run,
        "actorMember": actor_member,
        "targetLifecycle": target_lifecycle,
        "updated": updated,
        "updatedCount": len(updated),
        "errors": errors,
        "candidateSummary": candidate_set["summary"],
        "candidates": selected_candidates,
        "activities": updated_records,
    }

def update_git_activity_evidence_lifecycle(
    workspace_path: str | Path,
    activity_id: str,
    *,
    actor_member: str,
    lifecycle: str,
    reason: str | None = None,
    redaction_policy: str | None = None,
    export_policy: str | None = None,
    retained_until: str | None = None,
) -> dict[str, Any]:
    """Archive or redact durable GitActivity evidence without deleting lineage."""

    index = load_workspace(workspace_path)
    activity = index.git_activities.get(activity_id)
    if activity is None:
        raise KeyError(f"unknown GitActivity {activity_id}")
    actor = index.members.get(actor_member)
    if actor is None:
        raise KeyError(f"unknown actor member {actor_member}")
    if actor.spec.kind not in {"human", "hybrid", "service"}:
        raise ValueError("GitActivity evidence lifecycle changes require a human, hybrid, or governed service member")
    if lifecycle not in GIT_ACTIVITY_LIFECYCLES:
        raise ValueError(f"unsupported GitActivity lifecycle {lifecycle}")
    if redaction_policy is not None and redaction_policy not in GIT_ACTIVITY_REDACTION_POLICIES:
        raise ValueError(f"unsupported GitActivity redaction policy {redaction_policy}")
    if export_policy is not None and export_policy not in GIT_ACTIVITY_EXPORT_POLICIES:
        raise ValueError(f"unsupported GitActivity export policy {export_policy}")
    if activity.spec.lifecycle == "redacted" and lifecycle != "redacted":
        raise ValueError("redacted GitActivity evidence cannot be restored to active or archived")

    permission = explain_effective_permissions(
        index,
        member=actor_member,
        project=activity.spec.project,
        action={"tool": "Edit", "path": f"/.aiteamos/git_activity/{activity_id}.yaml", "operation": "update"},
        non_interactive=actor.spec.kind == "service",
    )
    if permission["decision"] == "deny" or permission.get("blockers"):
        raise ValueError(f"GitActivity lifecycle update is denied by effective permissions: {permission.get('reason')}; blockers={permission.get('blockers')}")

    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    payload = activity.model_dump(mode="json", exclude_none=True)
    spec = payload.setdefault("spec", {})
    previous_lifecycle = activity.spec.lifecycle
    spec["lifecycle"] = lifecycle
    if retained_until is not None:
        spec["retainedUntil"] = retained_until

    selected_redaction_policy = redaction_policy or activity.spec.redactionPolicy
    selected_export_policy = export_policy or activity.spec.exportPolicy
    if lifecycle == "active":
        spec.pop("archivedAt", None)
        if previous_lifecycle != "active":
            selected_export_policy = export_policy or selected_export_policy or "sanitize"
    elif lifecycle == "archived":
        spec["archivedAt"] = spec.get("archivedAt") or now
        selected_export_policy = export_policy or selected_export_policy or "sanitize"
    else:
        selected_redaction_policy = redaction_policy or selected_redaction_policy or "redacted-summary"
        selected_export_policy = export_policy or selected_export_policy or "exclude"
        spec["redactedAt"] = spec.get("redactedAt") or now
        spec["summary"] = f"Redacted GitActivity evidence {activity_id}; lineage is preserved through evidence and decisionAudit."
        spec["url"] = None
        spec["externalId"] = _redacted_identifier(activity.spec.externalId)
        spec["refs"] = _unique([_redacted_ref_value(ref) for ref in activity.spec.refs])

    if selected_redaction_policy:
        spec["redactionPolicy"] = selected_redaction_policy
    if selected_export_policy:
        spec["exportPolicy"] = selected_export_policy

    audit = decision_audit_record(
        index,
        decision_kind="service_policy_decision" if actor.spec.kind == "service" else "human_approval",
        decision=f"git-activity-evidence-{lifecycle}",
        actor_member=actor_member,
        authority="enforce" if actor.spec.kind == "service" else "approve",
        reason=reason or f"GitActivity evidence lifecycle changed from {previous_lifecycle} to {lifecycle}.",
        source="git-activity-evidence-lifecycle",
        decided_at=now,
        policy_refs=permission.get("selectedPolicyIds", []),
        evidence=[{"kind": "GitActivity", "id": activity_id}, *(_evidence_ref(item) for item in activity.spec.evidence)],
        requires_human_review=False,
        risk_assessment=permission.get("riskAssessment"),
        metadata={
            "previousLifecycle": previous_lifecycle,
            "lifecycle": lifecycle,
            "redactionPolicy": selected_redaction_policy,
            "exportPolicy": selected_export_policy,
            "retainedUntil": retained_until,
        },
    )
    spec.setdefault("decisionAudit", [])
    spec["decisionAudit"].append(audit)

    updated = GitActivity.model_validate(payload)
    write_yaml(index.workspace_root / "git_activity" / f"{activity_id}.yaml", updated.model_dump(mode="json", exclude_none=True))
    return {"activity": updated, "updated": True}


__all__ = [
    "git_activity_retention_candidates",
    "sweep_git_activity_retention",
    "update_git_activity_evidence_lifecycle",
]
