from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from aiteamos_schema import (
    API_VERSION,
    GitActivity,
    GitActivityCorrelationPreviewRecord,
    GitActivityCorrelationReview,
    GitActivityImportReceipt,
)

from ..audit import decision_audit_record
from ..connector_health import connector_health_admission_decision
from ..io import write_yaml
from ..loader import WorkspaceIndex, load_workspace
from ..permissions import explain_effective_permissions
from .common import (
    GIT_ACTIVITY_TYPES,
    _correlation_group_summary,
    _correlation_risk_flags,
    _find_correlation_preview_group,
    _common_normalized_value,
    _common_promoted_activity,
    _common_receipt_value,
    _correlation_promotion_audit,
    _correlation_promotion_permissions,
    _first_string_value,
    _promotion_float,
    _promotion_int,
    _mark_correlation_review_promoted,
    _selected_correlation_activity_type,
    _next_git_activity_correlation_review_id,
    _next_git_activity_id,
    _parse_git_activity_timestamp,
    _pull_request_identifier,
    _receipt_correlation_key_and_signals,
    _receipt_matches_member_assignment,
    _string_list,
    _string_value,
    _unique,
)


def git_activity_correlation_preview(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    project: str | None = None,
    repository: str | None = None,
    provider: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Build a read-only explanation of Git import receipts that may represent the same work."""

    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    provider_filter = provider.strip().lower() if provider else None
    filters = {
        "project": project,
        "repository": repository,
        "provider": provider_filter,
        "member": member,
        "assignment": assignment,
        "status": status,
    }
    groups: dict[str, dict[str, Any]] = {}
    for receipt in sorted(index.git_activity_import_receipts.values(), key=lambda item: item.object_id):
        if project and receipt.spec.project != project:
            continue
        if repository and receipt.spec.repository != repository:
            continue
        if provider_filter and receipt.spec.provider != provider_filter:
            continue
        if status and receipt.spec.status != status:
            continue
        if (member or assignment) and not _receipt_matches_member_assignment(index, receipt, member=member, assignment=assignment):
            continue

        correlation_key, signals = _receipt_correlation_key_and_signals(receipt)
        group = groups.setdefault(
            correlation_key,
            {
                "correlationKey": correlation_key,
                "project": receipt.spec.project,
                "repository": receipt.spec.repository,
                "provider": receipt.spec.provider,
                "connector": receipt.spec.connector,
                "receipts": [],
                "importedActivities": [],
                "eventFamilies": [],
                "members": [],
                "assignments": [],
                "refs": [],
                "commits": [],
                "pullRequests": [],
                "externalIds": [],
                "signals": [],
                "forcePushRisk": False,
                "squashMergeRisk": False,
                "multiEventRisk": False,
                "summary": "",
                "blockers": [],
                "warnings": [],
            },
        )
        normalized = receipt.spec.normalized
        activity_type = _string_value(normalized.get("activityType")) or _string_value(normalized.get("eventType")) or "event"
        group["receipts"] = _unique([*group["receipts"], receipt.object_id])
        group["importedActivities"] = _unique([*group["importedActivities"], *receipt.spec.importedActivities])
        group["eventFamilies"] = _unique([*group["eventFamilies"], activity_type])
        group["refs"] = _unique([*group["refs"], *receipt.spec.refs])
        if normalized.get("commit"):
            group["commits"] = _unique([*group["commits"], str(normalized["commit"])])
        pull_request = _pull_request_identifier(normalized)
        if pull_request:
            group["pullRequests"] = _unique([*group["pullRequests"], pull_request])
        if normalized.get("externalId"):
            group["externalIds"] = _unique([*group["externalIds"], str(normalized["externalId"])])
        if normalized.get("member"):
            group["members"] = _unique([*group["members"], str(normalized["member"])])
        if normalized.get("assignment"):
            group["assignments"] = _unique([*group["assignments"], str(normalized["assignment"])])
        group["signals"] = _unique([*group["signals"], *signals])
        group["blockers"] = _unique([*group["blockers"], *receipt.spec.blockers])
        group["warnings"] = _unique([*group["warnings"], *receipt.spec.warnings])

        for activity_id in receipt.spec.importedActivities:
            activity = index.git_activities.get(activity_id)
            if not activity:
                continue
            group["members"] = _unique([*group["members"], activity.spec.member])
            if activity.spec.assignment:
                group["assignments"] = _unique([*group["assignments"], activity.spec.assignment])
            group["refs"] = _unique([*group["refs"], *activity.spec.refs])
            if activity.spec.externalId:
                group["externalIds"] = _unique([*group["externalIds"], activity.spec.externalId])
            group["eventFamilies"] = _unique([*group["eventFamilies"], activity.spec.activityType])

    normalized_groups = []
    for group in groups.values():
        refs = [value for value in group["refs"] if isinstance(value, str) and value.startswith("ref:")]
        commits = [value for value in group["commits"] if isinstance(value, str)]
        event_families = set(group["eventFamilies"])
        group["multiEventRisk"] = len(group["receipts"]) > 1 or len(group["importedActivities"]) > 1
        group["forcePushRisk"] = len(set(refs)) == 1 and len(set(commits)) > 1
        group["squashMergeRisk"] = bool(event_families.intersection({"pull-request", "merge", "review-comment"})) and len(set(commits)) > 1
        if group["multiEventRisk"]:
            group["warnings"] = _unique([*group["warnings"], "multiple import receipts may describe the same Git work; review before promotion"])
        if group["forcePushRisk"]:
            group["warnings"] = _unique([*group["warnings"], "same ref appears with multiple commits; possible force-push or branch rewrite"])
        if group["squashMergeRisk"]:
            group["warnings"] = _unique([*group["warnings"], "pull-request or review events reference multiple commits; possible squash/merge reconciliation needed"])
        group["summary"] = _correlation_group_summary(group)
        normalized_groups.append(group)

    payload = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "filters": {key: value for key, value in filters.items() if value not in {None, ""}},
        "groups": sorted(normalized_groups, key=lambda item: (item["project"], item.get("repository") or "", item["correlationKey"])),
    }
    return GitActivityCorrelationPreviewRecord.model_validate(payload).model_dump(mode="json")

def review_git_activity_correlation(
    workspace_path: str | Path,
    *,
    correlation_key: str,
    receipts: list[str],
    reviewer_member: str,
    decision: str = "approved",
    summary: str | None = None,
    recommended_member: str | None = None,
    recommended_assignment: str | None = None,
    recommended_activity_type: str | None = None,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    """Record a reviewed, non-promoting Git import correlation decision."""

    index = load_workspace(workspace_path)
    selected_receipts = _unique([receipt.strip() for receipt in receipts if receipt.strip()])
    if not correlation_key:
        raise ValueError("correlation_key is required")
    if not selected_receipts:
        raise ValueError("at least one receipt is required")
    if reviewer_member not in index.members:
        raise KeyError(f"unknown reviewer member {reviewer_member}")
    if decision not in {"approved", "rejected", "needs-changes", "archived"}:
        raise ValueError(f"unsupported correlation review decision {decision}")

    reviewer = index.members[reviewer_member]
    if decision == "approved" and reviewer.spec.kind not in {"human", "hybrid"}:
        raise ValueError("approved correlation review requires a human or hybrid reviewer")

    receipt_records = []
    for receipt_id in selected_receipts:
        receipt = index.git_activity_import_receipts.get(receipt_id)
        if not receipt:
            raise KeyError(f"unknown git activity import receipt {receipt_id}")
        receipt_records.append(receipt)
    project_ids = {receipt.spec.project for receipt in receipt_records}
    if len(project_ids) != 1:
        raise ValueError("correlation review receipts must target one project")
    repository_ids = {receipt.spec.repository for receipt in receipt_records if receipt.spec.repository}
    provider_ids = {receipt.spec.provider for receipt in receipt_records if receipt.spec.provider}
    connector_ids = {receipt.spec.connector for receipt in receipt_records if receipt.spec.connector}
    if decision == "approved" and any(receipt.spec.status == "blocked" for receipt in receipt_records):
        raise ValueError("blocked receipts cannot be approved as a correlation group")

    preview = git_activity_correlation_preview(
        index,
        project=next(iter(project_ids)),
        repository=next(iter(repository_ids)) if len(repository_ids) == 1 else None,
        provider=next(iter(provider_ids)) if len(provider_ids) == 1 else None,
    )
    group = _find_correlation_preview_group(preview, correlation_key)
    if not group:
        raise KeyError(f"unknown correlation group {correlation_key}")
    group_receipts = {str(receipt_id) for receipt_id in group.get("receipts", [])}
    missing_from_group = [receipt_id for receipt_id in selected_receipts if receipt_id not in group_receipts]
    if missing_from_group:
        raise ValueError(f"receipts are not part of correlation group {correlation_key}: {', '.join(missing_from_group)}")

    for existing in index.git_activity_correlation_reviews.values():
        if (
            existing.spec.correlationKey == correlation_key
            and set(existing.spec.receipts) == set(selected_receipts)
            and existing.spec.decision == decision
        ):
            return {"review": existing, "created": False, "duplicateOf": existing.object_id}

    permission = explain_effective_permissions(
        index,
        member=reviewer_member,
        project=next(iter(project_ids)),
        action={"tool": "Edit", "path": "/.aiteamos/git_activity/correlations/GITCORR-*.yaml", "operation": "create"},
        non_interactive=reviewer.spec.kind in {"digital", "service"},
    )
    if permission["decision"] == "deny" or permission.get("blockers"):
        raise ValueError(f"correlation review creation is denied by effective permissions: {permission.get('reason')}; blockers={permission.get('blockers')}")

    now = reviewed_at or datetime.now().astimezone().isoformat(timespec="milliseconds")
    risk_flags = _correlation_risk_flags(group, receipt_records)
    recommended_promotion = {
        key: value
        for key, value in {
            "member": recommended_member,
            "assignment": recommended_assignment,
            "activityType": recommended_activity_type,
        }.items()
        if value
    }
    audit = decision_audit_record(
        index,
        decision_kind="human_approval" if decision == "approved" and reviewer.spec.kind in {"human", "hybrid"} else f"{reviewer.spec.kind}_review",
        decision=f"correlation-{decision}",
        actor_member=reviewer_member,
        authority="approve" if decision == "approved" and reviewer.spec.kind in {"human", "hybrid"} else "review",
        reason="Reviewed Git import receipts were recorded as a durable correlation decision without promoting them into GitActivity.",
        source="git-activity-correlation-review",
        decided_at=now,
        policy_refs=permission.get("selectedPolicyIds", []),
        evidence=[{"kind": "GitActivityImportReceipt", "id": receipt_id} for receipt_id in selected_receipts],
        requires_human_review=False,
        risk_assessment=permission.get("riskAssessment"),
        metadata={
            "correlationKey": correlation_key,
            "decision": decision,
            "riskFlags": risk_flags,
        },
    )
    review_id = _next_git_activity_correlation_review_id(index.workspace_root)
    payload = {
        "apiVersion": API_VERSION,
        "kind": "GitActivityCorrelationReview",
        "metadata": {"id": review_id, "createdAt": now},
        "spec": {
            "project": next(iter(project_ids)),
            "repository": next(iter(repository_ids)) if len(repository_ids) == 1 else None,
            "provider": next(iter(provider_ids)) if len(provider_ids) == 1 else None,
            "connector": next(iter(connector_ids)) if len(connector_ids) == 1 else None,
            "correlationKey": correlation_key,
            "receipts": selected_receipts,
            "importedActivities": _unique([str(activity_id) for activity_id in group.get("importedActivities", [])]),
            "decision": decision,
            "reviewerMember": reviewer_member,
            "reviewerMemberKind": reviewer.spec.kind,
            "reviewedAt": now,
            "eventFamilies": _unique([str(value) for value in group.get("eventFamilies", [])]),
            "members": _unique([str(value) for value in group.get("members", [])]),
            "assignments": _unique([str(value) for value in group.get("assignments", [])]),
            "refs": _unique([str(value) for value in group.get("refs", [])]),
            "commits": _unique([str(value) for value in group.get("commits", [])]),
            "pullRequests": _unique([str(value) for value in group.get("pullRequests", [])]),
            "externalIds": _unique([str(value) for value in group.get("externalIds", [])]),
            "signals": group.get("signals", []),
            "riskFlags": risk_flags,
            "recommendedPromotion": recommended_promotion,
            "summary": summary or f"Reviewed Git import correlation group {correlation_key} as {decision}.",
            "evidence": _unique([f"git_activity/imports/{receipt_id}.yaml" for receipt_id in selected_receipts]),
            "decisionAudit": [audit],
        },
    }
    review = GitActivityCorrelationReview.model_validate(payload)
    write_yaml(index.workspace_root / "git_activity" / "correlations" / f"{review_id}.yaml", review.model_dump(mode="json", exclude_none=True))
    return {"review": review, "created": True, "duplicateOf": None}

def git_activity_correlation_promotion_candidates(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    project: str | None = None,
    automation: str | None = None,
    service_member: str | None = None,
    include_blocked: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Explain which approved correlation reviews a service-policy automation may promote."""

    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    current_time = now or datetime.now().astimezone()
    automation_record = None
    target_config: dict[str, Any] = {}
    warnings: list[str] = []
    blockers: list[str] = []
    if automation:
        automation_record = index.automations.get(automation)
        if automation_record is None:
            raise KeyError(f"unknown automation {automation}")
        if automation_record.spec.targetType != "git_activity_correlation_promotion":
            raise ValueError(f"automation {automation} targets {automation_record.spec.targetType}, not git_activity_correlation_promotion")
        target_config = dict(automation_record.spec.target or {})
        service_member = service_member or automation_record.spec.serviceMember
        project = project or automation_record.spec.project

    project_id = project or index.project.object_id
    if project_id != index.project.object_id:
        raise KeyError(f"unknown project {project_id}")

    service_permission: dict[str, Any] | None = None
    if service_member:
        service = index.members.get(service_member)
        if service is None:
            raise KeyError(f"unknown service member {service_member}")
        if service.spec.kind != "service":
            raise ValueError(f"promotion service member {service_member} is {service.spec.kind}, not service")
        if automation:
            service_permission = explain_effective_permissions(
                index,
                member=service_member,
                project=project_id,
                action={"tool": "Automation", "target": f"git_activity_correlation_promotion:{automation}"},
                non_interactive=True,
            )
            if service_permission.get("decision") != "allow" or service_permission.get("blockers"):
                blockers.append(
                    f"service member {service_member} cannot execute Automation(git_activity_correlation_promotion:{automation})"
                )

    requested_reviews = set(_string_list(target_config.get("reviewIds") or target_config.get("reviews")))
    allowed_risk_flags = set(_string_list(target_config.get("allowRiskFlags") or target_config.get("allowedRiskFlags")))
    max_age_hours = _promotion_float(target_config, "maxApprovalAgeHours", "approvalMaxAgeHours")
    if max_age_hours is None:
        max_age_hours = 24.0
    require_health = bool(
        target_config.get("requireHealthyConnector")
        or target_config.get("requireConnectorHealth")
        or str(target_config.get("connectorHealthPolicy") or "").lower()
        in {"strict", "require", "required", "require_healthy", "block_unhealthy"}
    )
    connector_health_max_age_seconds = _promotion_int(
        target_config,
        "connectorHealthMaxAgeSeconds",
        "healthMaxAgeSeconds",
    )
    if connector_health_max_age_seconds is None:
        connector_health_max_age_minutes = _promotion_int(
            target_config,
            "connectorHealthMaxAgeMinutes",
            "healthMaxAgeMinutes",
        )
        if connector_health_max_age_minutes is not None:
            connector_health_max_age_seconds = connector_health_max_age_minutes * 60
    max_promotions = _promotion_int(target_config, "maxPromotionsPerRun", "max_promotions_per_run") or 1

    candidate_records: list[dict[str, Any]] = []
    eligible_count = 0
    for review in sorted(index.git_activity_correlation_reviews.values(), key=lambda item: item.object_id):
        if requested_reviews and review.object_id not in requested_reviews:
            continue
        if review.spec.project != project_id:
            continue
        candidate_blockers = list(blockers)
        candidate_warnings: list[str] = []
        if review.spec.decision != "approved":
            candidate_blockers.append(f"correlation review decision is {review.spec.decision}, not approved")
        if review.spec.importedActivities:
            candidate_blockers.append("correlation review already links imported GitActivity records")

        receipts: list[GitActivityImportReceipt] = []
        for receipt_id in review.spec.receipts:
            receipt = index.git_activity_import_receipts.get(receipt_id)
            if receipt is None:
                candidate_blockers.append(f"missing receipt {receipt_id}")
                continue
            receipts.append(receipt)
            if receipt.spec.project != review.spec.project:
                candidate_blockers.append(f"receipt {receipt_id} targets project {receipt.spec.project}")
            if receipt.spec.status not in {"candidate", "needs-review"}:
                candidate_blockers.append(f"receipt {receipt_id} is {receipt.spec.status}, not candidate/needs-review")
            if receipt.spec.importedActivities:
                candidate_blockers.append(f"receipt {receipt_id} already links GitActivity records")
            if receipt.spec.importPolicy != "service-policy-import":
                candidate_blockers.append(f"receipt {receipt_id} importPolicy is {receipt.spec.importPolicy}, not service-policy-import")
            if receipt.spec.blockers:
                candidate_blockers.extend([f"receipt {receipt_id}: {blocker}" for blocker in receipt.spec.blockers])

        reviewed_at = _parse_git_activity_timestamp(review.spec.reviewedAt or review.metadata.createdAt)
        approval_age_hours: float | None = None
        if reviewed_at is None:
            candidate_blockers.append("correlation review has no parseable reviewedAt timestamp")
        else:
            approval_age_hours = max(0.0, (current_time - reviewed_at).total_seconds() / 3600)
            if max_age_hours is not None and approval_age_hours > max_age_hours:
                candidate_blockers.append(
                    f"correlation review approval is stale: {approval_age_hours:.2f}h exceeds {max_age_hours:.2f}h"
                )

        disallowed_risks = sorted(set(review.spec.riskFlags).difference({"manual-review-required"}).difference(allowed_risk_flags))
        if disallowed_risks:
            candidate_blockers.append(f"risk flags are not allowed for service promotion: {', '.join(disallowed_risks)}")

        connector_id = _string_value(target_config.get("connector")) or review.spec.connector or _common_receipt_value(receipts, "connector")
        connector_health = None
        if connector_id:
            health_config = dict(target_config)
            if connector_health_max_age_seconds is not None:
                health_config["connectorHealthMaxAgeSeconds"] = connector_health_max_age_seconds
            if require_health:
                health_config["requireHealthyConnector"] = True
            connector_health = connector_health_admission_decision(index, connector_id, config=health_config, now=current_time)
            candidate_blockers.extend(connector_health["blockers"])
            candidate_warnings.extend(connector_health["warnings"])
        elif require_health:
            candidate_blockers.append("requireHealthyConnector is set but the review/receipts have no connector")

        recommended = review.spec.recommendedPromotion
        target_member = (
            _string_value(target_config.get("member"))
            or _string_value(target_config.get("targetMember"))
            or _string_value(recommended.get("member"))
            or _common_normalized_value(receipts, "member")
        )
        target_assignment = (
            _string_value(target_config.get("assignment"))
            or _string_value(target_config.get("targetAssignment"))
            or _string_value(recommended.get("assignment"))
            or _common_normalized_value(receipts, "assignment")
        )
        if not target_member:
            candidate_blockers.append("no target member can be resolved from automation target, review recommendation, or receipts")
        elif target_member not in index.members:
            candidate_blockers.append(f"target member {target_member} does not exist")
        if target_assignment:
            assignment_record = index.assignments.get(target_assignment)
            if assignment_record is None:
                candidate_blockers.append(f"target assignment {target_assignment} does not exist")
            else:
                if target_member and assignment_record.spec.member != target_member:
                    candidate_blockers.append(
                        f"target assignment {target_assignment} belongs to member {assignment_record.spec.member}, not {target_member}"
                    )
                if assignment_record.spec.project != review.spec.project:
                    candidate_blockers.append(
                        f"target assignment {target_assignment} belongs to project {assignment_record.spec.project}, not {review.spec.project}"
                    )

        target_activity_type = _string_value(target_config.get("activityType")) or _selected_correlation_activity_type(
            review,
            receipts,
            _string_value(target_config.get("activity_type")),
        )
        eligible = not candidate_blockers
        if eligible:
            eligible_count += 1
        if eligible or include_blocked:
            candidate_records.append(
                {
                    "id": review.object_id,
                    "review": review.object_id,
                    "project": review.spec.project,
                    "repository": review.spec.repository,
                    "provider": review.spec.provider,
                    "connector": connector_id,
                    "correlationKey": review.spec.correlationKey,
                    "receipts": list(review.spec.receipts),
                    "riskFlags": list(review.spec.riskFlags),
                    "allowedRiskFlags": sorted(allowed_risk_flags),
                    "targetMember": target_member,
                    "targetAssignment": target_assignment,
                    "activityType": target_activity_type,
                    "reviewedAt": review.spec.reviewedAt,
                    "approvalAgeHours": round(approval_age_hours, 4) if approval_age_hours is not None else None,
                    "maxApprovalAgeHours": max_age_hours,
                    "importPolicies": sorted({receipt.spec.importPolicy for receipt in receipts}),
                    "receiptStatuses": {receipt.object_id: receipt.spec.status for receipt in receipts},
                    "connectorHealth": connector_health["record"] if connector_health else None,
                    "serviceMember": service_member,
                    "automation": automation,
                    "eligible": eligible,
                    "blockers": _unique(candidate_blockers),
                    "warnings": _unique(candidate_warnings),
                    "promotionPreview": {
                        "reviewId": review.object_id,
                        "reviewerMember": service_member,
                        "member": target_member,
                        "assignment": target_assignment,
                        "activityType": target_activity_type,
                        "visibility": _string_value(target_config.get("visibility")) or "project",
                    },
                }
            )

    return {
        "generatedAt": current_time.isoformat(timespec="milliseconds"),
        "filters": {
            "project": project_id,
            "automation": automation,
            "serviceMember": service_member,
            "includeBlocked": include_blocked,
        },
        "policy": {
            "maxApprovalAgeHours": max_age_hours,
            "connectorHealthMaxAgeSeconds": connector_health_max_age_seconds,
            "requireHealthyConnector": require_health,
            "allowRiskFlags": sorted(allowed_risk_flags),
            "maxPromotionsPerRun": max_promotions,
            "requestedReviews": sorted(requested_reviews),
        },
        "servicePermission": service_permission,
        "summary": {
            "candidates": len(candidate_records),
            "eligible": eligible_count,
            "blocked": len(candidate_records) - eligible_count,
        },
        "blockers": blockers,
        "warnings": warnings,
        "candidates": candidate_records,
    }

def promote_git_activity_correlation_review(
    workspace_path: str | Path,
    review_id: str,
    *,
    reviewer_member: str,
    member: str | None = None,
    assignment: str | None = None,
    activity_type: str | None = None,
    summary: str | None = None,
    occurred_at: str | None = None,
    visibility: str = "project",
    refs: list[str] | None = None,
) -> dict[str, Any]:
    """Promote an approved correlation review into one durable GitActivity."""

    index = load_workspace(workspace_path)
    if review_id not in index.git_activity_correlation_reviews:
        raise KeyError(f"unknown git activity correlation review {review_id}")
    if reviewer_member not in index.members:
        raise KeyError(f"unknown reviewer member {reviewer_member}")
    reviewer = index.members[reviewer_member]
    review = index.git_activity_correlation_reviews[review_id]
    if review.spec.decision != "approved":
        raise ValueError(f"correlation review {review_id} cannot be promoted from decision {review.spec.decision}")
    if review.spec.project != index.project.object_id:
        raise ValueError(f"correlation review {review_id} targets project {review.spec.project}, not {index.project.object_id}")
    if reviewer.spec.kind == "service" and not all(
        index.git_activity_import_receipts.get(receipt_id)
        and index.git_activity_import_receipts[receipt_id].spec.importPolicy == "service-policy-import"
        for receipt_id in review.spec.receipts
    ):
        raise ValueError("service reviewers can promote only correlation groups whose receipts use service-policy-import")
    if reviewer.spec.kind not in {"human", "hybrid", "service"}:
        raise ValueError("git activity correlation promotion requires a human, hybrid, or governed service reviewer")

    receipts = []
    for receipt_id in review.spec.receipts:
        receipt = index.git_activity_import_receipts.get(receipt_id)
        if not receipt:
            raise KeyError(f"unknown git activity import receipt {receipt_id}")
        if receipt.spec.project != review.spec.project:
            raise ValueError(f"receipt {receipt_id} targets project {receipt.spec.project}, not {review.spec.project}")
        receipts.append(receipt)
    if not receipts:
        raise ValueError("correlation promotion requires at least one receipt")

    already_promoted = _common_promoted_activity(index, review, receipts)
    if already_promoted:
        updated_review = _mark_correlation_review_promoted(
            index,
            review,
            receipts,
            already_promoted,
            reviewer_member=reviewer_member,
            permission_decisions=[],
            idempotent=True,
        )
        return {
            "review": updated_review,
            "receipts": receipts,
            "activities": [already_promoted],
            "created": False,
            "alreadyPromoted": True,
        }

    for receipt in receipts:
        if receipt.spec.status not in {"candidate", "needs-review"}:
            raise ValueError(f"receipt {receipt.object_id} cannot be group-promoted from status {receipt.spec.status}")
        if receipt.spec.importedActivities:
            raise ValueError(f"receipt {receipt.object_id} already links GitActivity records; group promotion would double-count evidence")
        if receipt.spec.status in {"blocked", "duplicate", "archived"}:
            raise ValueError(f"receipt {receipt.object_id} cannot be group-promoted from status {receipt.spec.status}")

    recommended = review.spec.recommendedPromotion
    target_member = member or _string_value(recommended.get("member")) or _common_normalized_value(receipts, "member")
    if not target_member:
        raise ValueError("correlation promotion requires a target member")
    if target_member not in index.members:
        raise KeyError(f"unknown target member {target_member}")
    target_assignment = assignment or _string_value(recommended.get("assignment")) or _common_normalized_value(receipts, "assignment")
    if target_assignment:
        if target_assignment not in index.assignments:
            raise KeyError(f"unknown assignment {target_assignment}")
        assignment_record = index.assignments[target_assignment]
        if assignment_record.spec.member != target_member:
            raise ValueError(f"assignment {target_assignment} belongs to member {assignment_record.spec.member}, not {target_member}")
        if assignment_record.spec.project != review.spec.project:
            raise ValueError(f"assignment {target_assignment} belongs to project {assignment_record.spec.project}, not {review.spec.project}")
    if review.spec.repository and review.spec.repository not in index.repositories:
        raise KeyError(f"unknown repository {review.spec.repository}")

    permission_decisions = _correlation_promotion_permissions(index, review, receipts, reviewer_member=reviewer_member)
    for label, decision in permission_decisions:
        if decision["decision"] == "deny" or decision.get("blockers"):
            raise ValueError(f"{label} is denied by effective permissions: {decision.get('reason')}; blockers={decision.get('blockers')}")

    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    git_activity_id = _next_git_activity_id(index.workspace_root)
    selected_activity_type = _selected_correlation_activity_type(review, receipts, activity_type)
    selected_refs = refs if refs is not None else _unique([*review.spec.refs, *(ref for receipt in receipts for ref in receipt.spec.refs)])
    selected_external_id = _first_string_value(
        *review.spec.pullRequests,
        *review.spec.externalIds,
        *(_string_value(receipt.spec.normalized.get("externalId")) for receipt in receipts),
        *(_string_value(receipt.spec.normalized.get("commit")) for receipt in receipts),
    )
    selected_url = _first_string_value(*(_string_value(receipt.spec.normalized.get("url")) for receipt in receipts))
    selected_occurred_at = occurred_at or _first_string_value(
        *(_string_value(receipt.spec.normalized.get("authoredAt")) for receipt in receipts),
        *(_string_value(receipt.spec.receivedAt) for receipt in receipts),
    )
    evidence = _unique(
        [
            f"git_activity/correlations/{review_id}.yaml",
            *review.spec.evidence,
            *(f"git_activity/imports/{receipt.object_id}.yaml" for receipt in receipts),
            *(evidence_item for receipt in receipts for evidence_item in receipt.spec.evidence),
        ]
    )
    activity = GitActivity.model_validate(
        {
            "apiVersion": API_VERSION,
            "kind": "GitActivity",
            "metadata": {"id": git_activity_id, "createdAt": now},
            "spec": {
                "member": target_member,
                "project": review.spec.project,
                "repository": review.spec.repository or receipts[0].spec.repository,
                "assignment": target_assignment,
                "activityType": selected_activity_type,
                "provider": review.spec.provider or receipts[0].spec.provider,
                "externalId": selected_external_id,
                "url": selected_url,
                "occurredAt": selected_occurred_at or now,
                "summary": summary or review.spec.summary or f"Promoted reviewed Git import correlation {review_id}.",
                "refs": selected_refs,
                "evidence": evidence,
                "visibility": visibility,
            },
        }
    )

    audit = _correlation_promotion_audit(
        index,
        review,
        receipts,
        activity,
        reviewer_member=reviewer_member,
        permission_decisions=permission_decisions,
        idempotent=False,
    )
    updated_receipts = []
    for receipt in receipts:
        receipt_payload = receipt.model_dump(mode="json", exclude_none=True)
        receipt_spec = receipt_payload.setdefault("spec", {})
        receipt_spec["status"] = "imported"
        receipt_spec["reviewedByMember"] = reviewer_member
        receipt_spec["reviewedAt"] = now
        receipt_spec["importedActivities"] = _unique([*receipt.spec.importedActivities, git_activity_id])
        receipt_spec["evidence"] = _unique(
            [
                *receipt.spec.evidence,
                f"git_activity/correlations/{review_id}.yaml",
                f"git_activity/{git_activity_id}.yaml",
            ]
        )
        receipt_spec.setdefault("decisionAudit", [])
        receipt_spec["decisionAudit"].append(audit)
        updated_receipts.append(GitActivityImportReceipt.model_validate(receipt_payload))

    review_payload = review.model_dump(mode="json", exclude_none=True)
    review_spec = review_payload.setdefault("spec", {})
    review_spec["importedActivities"] = _unique([*review.spec.importedActivities, git_activity_id])
    review_spec["members"] = _unique([*review.spec.members, target_member])
    if target_assignment:
        review_spec["assignments"] = _unique([*review.spec.assignments, target_assignment])
    review_spec["eventFamilies"] = _unique([*review.spec.eventFamilies, selected_activity_type])
    review_spec["refs"] = _unique([*review.spec.refs, *selected_refs])
    review_spec["evidence"] = _unique([*review.spec.evidence, f"git_activity/{git_activity_id}.yaml"])
    review_spec.setdefault("decisionAudit", [])
    review_spec["decisionAudit"].append(audit)
    updated_review = GitActivityCorrelationReview.model_validate(review_payload)

    write_yaml(index.workspace_root / "git_activity" / f"{git_activity_id}.yaml", activity.model_dump(mode="json", exclude_none=True))
    for receipt in updated_receipts:
        write_yaml(index.workspace_root / "git_activity" / "imports" / f"{receipt.object_id}.yaml", receipt.model_dump(mode="json", exclude_none=True))
    write_yaml(index.workspace_root / "git_activity" / "correlations" / f"{review_id}.yaml", updated_review.model_dump(mode="json", exclude_none=True))
    return {
        "review": updated_review,
        "receipts": updated_receipts,
        "activities": [activity],
        "created": True,
        "alreadyPromoted": False,
    }
